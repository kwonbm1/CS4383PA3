from concurrent import futures
import os
import sys
import time
import threading
import grpc
import zmq
import flatbuffers

from proto import common_pb2 as pb2
from proto import ordering_inventory_pb2_grpc as inv_from_ordering_grpc
from proto import robot_inventory_pb2_grpc as inv_from_robot_grpc
from proto import robot_inventory_pb2 as robot_pb2
from proto import inventory_pricing_pb2 as pricing_pb2
from proto import inventory_pricing_pb2_grpc as pricing_grpc

# Flatbuffers generated python (your project uses fbschemas/)
from fbschemas.grocery.fb import FetchTask, RestockTask, TaskType
from fbschemas.grocery.fb import ItemQty as FbItemQty


# ----------------------------
# Constants
# ----------------------------
NUM_ROBOTS = 5
BARRIER_TIMEOUT_SECS = 10
# PA2: Config via env for K8s multi-cluster (NodePort). Defaults = PA1 multi-VM.
PRICING_HOST = os.environ.get("PRICING_HOST", "172.16.5.214")
PRICING_GRPC_PORT = os.environ.get("PRICING_GRPC_PORT", "50052")
PRICING_GRPC_ADDR = f"{PRICING_HOST}:{PRICING_GRPC_PORT}"

AISLE_ITEMS = {
    "bread": ["bagels", "bread", "waffles", "tortillas", "buns"],
    "dairy": ["milk", "eggs", "cheese", "yogurt", "butter"],
    "meat": ["chicken", "beef", "pork", "turkey", "fish"],
    "produce": ["tomatoes", "onions", "apples", "oranges", "lettuce"],
    "party": ["soda", "paper_plates", "napkins", "chips", "cups"],
}

# Reverse lookup: item name -> aisle
ITEM_TO_AISLE = {}
for _aisle, _items in AISLE_ITEMS.items():
    for _item in _items:
        ITEM_TO_AISLE[_item] = _aisle


# ----------------------------
# Flatbuffers builders
# ----------------------------
def build_fetch_payload(task_id: str, items: list[tuple[str, float]]) -> bytes:
    b = flatbuffers.Builder(1024)

    item_offsets = []
    for name, qty in items:
        name_off = b.CreateString(name)
        FbItemQty.Start(b)
        FbItemQty.AddItem(b, name_off)
        FbItemQty.AddQty(b, float(qty))
        item_offsets.append(FbItemQty.End(b))

    FetchTask.StartItemsVector(b, len(item_offsets))
    for off in reversed(item_offsets):
        b.PrependUOffsetTRelative(off)
    items_vec = b.EndVector()

    task_id_off = b.CreateString(task_id)
    FetchTask.Start(b)
    FetchTask.AddTaskId(b, task_id_off)
    FetchTask.AddTaskType(b, TaskType.TaskType.FETCH)
    FetchTask.AddItems(b, items_vec)
    FetchTask.AddTimestampMs(b, int(time.time() * 1000))
    root = FetchTask.End(b)

    b.Finish(root)
    return bytes(b.Output())


def build_restock_payload(task_id: str, items: list[tuple[str, float]]) -> bytes:
    b = flatbuffers.Builder(1024)

    item_offsets = []
    for name, qty in items:
        name_off = b.CreateString(name)
        FbItemQty.Start(b)
        FbItemQty.AddItem(b, name_off)
        FbItemQty.AddQty(b, float(qty))
        item_offsets.append(FbItemQty.End(b))

    RestockTask.StartItemsVector(b, len(item_offsets))
    for off in reversed(item_offsets):
        b.PrependUOffsetTRelative(off)
    items_vec = b.EndVector()

    task_id_off = b.CreateString(task_id)
    RestockTask.Start(b)
    RestockTask.AddTaskId(b, task_id_off)
    RestockTask.AddTaskType(b, TaskType.TaskType.RESTOCK)
    RestockTask.AddItems(b, items_vec)
    RestockTask.AddTimestampMs(b, int(time.time() * 1000))
    root = RestockTask.End(b)

    b.Finish(root)
    return bytes(b.Output())


def pb_order_to_items(order: pb2.Order) -> list[tuple[str, float]]:
    """Flatten protobuf order into list[(item, qty)] across all aisles."""
    out: list[tuple[str, float]] = []
    for aisle in [order.bread, order.meat, order.produce, order.dairy, order.party]:
        for it in aisle.items:
            if it.item and it.qty > 0:
                out.append((it.item, float(it.qty)))
    return out


# ----------------------------
# Shared State
# ----------------------------
class TaskState:
    """Tracks a single in-flight task awaiting robot responses."""

    def __init__(self, task_type: str, original_items: list[tuple[str, float]]):
        self.task_type = task_type          # "FETCH" or "RESTOCK"
        self.original_items = original_items
        self.event = threading.Event()      # signaled when all robots respond
        self.response_count = 0
        self.robot_results: list[dict] = []  # collected results from each robot


class InventoryState:
    """Centralized in-memory data store shared by both gRPC servicers."""

    def __init__(self):
        self.lock = threading.Lock()
        self.task_counter = 0

        # In-memory inventory: { aisle: { item: count } }
        self.inventory = {
            aisle: {item: 100 for item in items}
            for aisle, items in AISLE_ITEMS.items()
        }

        # Pending tasks awaiting robot responses: { task_id: TaskState }
        self.pending_tasks: dict[str, TaskState] = {}

    def next_task_id(self) -> str:
        with self.lock:
            self.task_counter += 1
            return f"task_{self.task_counter}"

    def cap_items_to_stock(self, items: list[tuple[str, float]]) -> list[tuple[str, float]]:
        """For grocery (FETCH) orders: cap each item's qty to available stock.
        Returns list of (item, capped_qty); drops items with 0 available."""
        result: list[tuple[str, float]] = []
        with self.lock:
            for item_name, qty in items:
                aisle = ITEM_TO_AISLE.get(item_name)
                if aisle is None:
                    continue
                available = self.inventory[aisle].get(item_name, 0)
                capped = min(float(qty), float(available))
                if capped > 0:
                    result.append((item_name, capped))
        return result

    def create_task(self, task_id: str, task_type: str,
                    items: list[tuple[str, float]]) -> TaskState:
        task_state = TaskState(task_type, items)
        with self.lock:
            self.pending_tasks[task_id] = task_state
        return task_state

    def record_robot_result(self, task_id: str, robot_id: str,
                            code, message: str,
                            items: list[tuple[str, float]]) -> bool:
        """Record a robot's result. Returns True if this was the last robot
        (i.e. response_count just reached NUM_ROBOTS)."""
        with self.lock:
            task_state = self.pending_tasks.get(task_id)
            if task_state is None:
                return False

            task_state.robot_results.append({
                "robot_id": robot_id,
                "code": code,
                "message": message,
                "items": items,
            })
            task_state.response_count += 1

            if task_state.response_count >= NUM_ROBOTS:
                task_state.event.set()
                return True
        return False

    def apply_inventory_updates(self, task_id: str) -> list[tuple[str, float]]:
        """After all robots respond (or timeout), apply inventory changes.
        Returns the aggregated list of successfully processed items."""
        with self.lock:
            task_state = self.pending_tasks.get(task_id)
            if task_state is None:
                return []

            all_processed: list[tuple[str, float]] = []

            for result in task_state.robot_results:
                if result["code"] == pb2.OK:
                    for item_name, qty in result["items"]:
                        aisle = ITEM_TO_AISLE.get(item_name)
                        if aisle is None:
                            continue

                        if task_state.task_type == "FETCH":
                            # Decrement inventory: never deduct more than we have
                            current = self.inventory[aisle].get(item_name, 0)
                            deduct = min(qty, current)
                            self.inventory[aisle][item_name] = current - deduct
                            all_processed.append((item_name, deduct))
                        elif task_state.task_type == "RESTOCK":
                            # Increment inventory
                            current = self.inventory[aisle].get(item_name, 0)
                            self.inventory[aisle][item_name] = current + qty
                            all_processed.append((item_name, qty))

            # Clean up pending task
            self.pending_tasks.pop(task_id, None)

        return all_processed

    def dump_inventory(self):
        """Print current inventory state (for debugging)."""
        with self.lock:
            for aisle, items in self.inventory.items():
                for item, count in items.items():
                    print(f"  {aisle}/{item}: {count}", flush=True)


# ----------------------------
# Pricing client
# ----------------------------
def call_pricing_service(items: list[tuple[str, float]],
                         addr: str = PRICING_GRPC_ADDR) -> float:
    """Call the Pricing Service to get the total cost for a list of items.
    Returns total_price on success, 0.0 on failure."""
    try:
        with grpc.insecure_channel(addr) as channel:
            stub = pricing_grpc.PricingServiceStub(channel)
            pb_items = [pb2.ItemQty(item=name, qty=qty)
                        for name, qty in items]
            resp = stub.GetTotalPrice(
                pricing_pb2.PriceRequest(items=pb_items), timeout=5
            )
            print(f"[inventory_service] pricing response: ${resp.total_price:.2f} "
                  f"({resp.message})", flush=True)
            return resp.total_price
    except Exception as e:
        print(f"[inventory_service] pricing call failed: {e}", flush=True)
        return 0.0


# ----------------------------
# Services
# ----------------------------
class InventoryService(inv_from_ordering_grpc.InventoryServiceServicer):
    def __init__(self, zmq_pub, state: InventoryState):
        self.zmq_pub = zmq_pub
        self.state = state

    def ProcessOrder(self, request: pb2.OrderRequest, context):
        original_items = pb_order_to_items(request.order)

        # Reject empty orders
        if len(original_items) == 0:
            return pb2.BasicReply(code=pb2.BAD_REQUEST,
                                  message="Order cannot be empty")

        # Determine task type
        if request.message_type == pb2.GROCERY_ORDER:
            task_type = "FETCH"
        elif request.message_type == pb2.RESTOCK_ORDER:
            task_type = "RESTOCK"
        else:
            return pb2.BasicReply(code=pb2.BAD_REQUEST,
                                  message="Unknown message_type")

        # For grocery (FETCH): cap quantities to available stock
        items = original_items
        if task_type == "FETCH":
            items = self.state.cap_items_to_stock(original_items)
            if len(items) == 0:
                # Return all requested items with qty 0 so client sees what was requested
                pb_items_zero = [pb2.ItemQty(item=name, qty=0.0)
                                 for name, _ in original_items]
                return pb2.BasicReply(
                    code=pb2.BAD_REQUEST,
                    message="No items available: requested items are out of stock or invalid",
                    items=pb_items_zero,
                )

        # Create task state for synchronization barrier
        task_id = self.state.next_task_id()
        task_state = self.state.create_task(task_id, task_type, items)

        # Build and broadcast FlatBuffers payload via ZMQ
        if task_type == "FETCH":
            payload = build_fetch_payload(task_id, items)
            self.zmq_pub.send_multipart([b"FETCH", payload])
        else:
            payload = build_restock_payload(task_id, items)
            self.zmq_pub.send_multipart([b"RESTOCK", payload])

        print(f"[inventory_service] published {task_type} {task_id} "
              f"items={items}", flush=True)

        # Block until all 5 robots respond or timeout
        all_responded = task_state.event.wait(timeout=BARRIER_TIMEOUT_SECS)

        if all_responded:
            print(f"[inventory_service] all {NUM_ROBOTS} robots responded "
                  f"for {task_id}", flush=True)
        else:
            print(f"[inventory_service] TIMEOUT waiting for robots on "
                  f"{task_id} (got {task_state.response_count}/{NUM_ROBOTS})",
                  flush=True)

        # Apply inventory updates from confirmed robot results
        processed_items = self.state.apply_inventory_updates(task_id)

        print(f"[inventory_service] {task_type} {task_id} processed "
              f"items={processed_items}", flush=True)
        print("[inventory_service] current inventory:", flush=True)
        self.state.dump_inventory()

        # Build response: for FETCH return all requested items with fulfilled qty (0 if out of stock)
        if task_type == "FETCH":
            fulfilled_map = dict(processed_items)
            response_items = [(name, fulfilled_map.get(name, 0.0)) for name, _ in original_items]
        else:
            response_items = processed_items
        pb_items = [pb2.ItemQty(item=name, qty=qty)
                    for name, qty in response_items]

        # For grocery orders (FETCH), call Pricing Service to get the bill
        total_price = 0.0
        if task_type == "FETCH" and processed_items:
            total_price = call_pricing_service(processed_items)

        if task_type == "FETCH":
            msg_note = " Fulfilled up to available stock."
        else:
            msg_note = ""

        if all_responded:
            return pb2.BasicReply(
                code=pb2.OK,
                message=f"{task_type} completed: {len(processed_items)} items processed.{msg_note}",
                items=pb_items,
                total_price=total_price,
            )
        else:
            return pb2.BasicReply(
                code=pb2.OK,
                message=(f"{task_type} partial: {task_state.response_count}/"
                         f"{NUM_ROBOTS} robots responded, "
                         f"{len(processed_items)} items processed.{msg_note}"),
                items=pb_items,
                total_price=total_price,
            )


class InventoryRobotService(inv_from_robot_grpc.InventoryRobotServiceServicer):
    def __init__(self, state: InventoryState):
        self.state = state

    def ReportTaskResult(self, request: robot_pb2.RobotTaskResult, context):
        # Extract processed items from the robot's report
        robot_items = [(it.item, it.qty) for it in request.items]

        print(
            f"[inventory_service] robot_result robot={request.robot_id} "
            f"task={request.task_id} code={request.code} "
            f"msg={request.message} items={robot_items}",
            flush=True,
        )

        # Record the result and potentially unblock the waiting ProcessOrder
        was_last = self.state.record_robot_result(
            task_id=request.task_id,
            robot_id=request.robot_id,
            code=request.code,
            message=request.message,
            items=robot_items,
        )

        if was_last:
            print(f"[inventory_service] all {NUM_ROBOTS} robots reported "
                  f"for {request.task_id} — unblocking", flush=True)

        return pb2.BasicReply(code=pb2.OK,
                              message="Inventory received robot result: OK")


def serve(grpc_host="0.0.0.0", grpc_port=50051, zmq_bind="tcp://*:5556"):
    # Shared state
    state = InventoryState()

    print("[inventory_service] initial inventory:", flush=True)
    state.dump_inventory()

    # ZMQ publisher
    zmq_ctx = zmq.Context()
    zmq_pub = zmq_ctx.socket(zmq.PUB)
    zmq_pub.bind(zmq_bind)
    print(f"[inventory_service] ZMQ PUB bound at {zmq_bind}", flush=True)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    inv_from_ordering_grpc.add_InventoryServiceServicer_to_server(
        InventoryService(zmq_pub, state), server
    )
    inv_from_robot_grpc.add_InventoryRobotServiceServicer_to_server(
        InventoryRobotService(state), server
    )

    server.add_insecure_port(f"{grpc_host}:{grpc_port}")
    server.start()
    print(f"[inventory_service] gRPC listening on {grpc_host}:{grpc_port}",
          flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    grpc_port = int(os.environ.get("INVENTORY_GRPC_PORT", "50051"))
    zmq_bind = os.environ.get("INVENTORY_ZMQ_BIND", "tcp://*:5556")
    serve(grpc_host="0.0.0.0", grpc_port=grpc_port, zmq_bind=zmq_bind)
