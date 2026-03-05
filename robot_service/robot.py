import argparse
import os
import time
import zmq
import grpc

from proto import common_pb2 as pb2
from proto import robot_inventory_pb2 as robot_pb2
from proto import robot_inventory_pb2_grpc as inv_robot_grpc

from fbschemas.grocery.fb import FetchTask, RestockTask
from fbschemas.grocery.fb import ItemQty, TaskType


# ----------------------------
# Constants
# ----------------------------
# PA2: Config via env for K8s multi-cluster (NodePort). Defaults = PA1 multi-VM.
_DEFAULT_INV_HOST = os.environ.get("INVENTORY_HOST", "172.16.5.69")
_DEFAULT_INV_GRPC_PORT = os.environ.get("INVENTORY_GRPC_PORT", "50051")
_DEFAULT_INV_ZMQ_PORT = os.environ.get("INVENTORY_ZMQ_PORT", "5556")
DEFAULT_INVENTORY_GRPC_ADDR = f"{_DEFAULT_INV_HOST}:{_DEFAULT_INV_GRPC_PORT}"
DEFAULT_ZMQ_SUB_ADDR = f"tcp://{_DEFAULT_INV_HOST}:{_DEFAULT_INV_ZMQ_PORT}"

AISLE_ITEMS = {
    "bread": ["bagels", "bread", "waffles", "tortillas", "buns"],
    "dairy": ["milk", "eggs", "cheese", "yogurt", "butter"],
    "meat": ["chicken", "beef", "pork", "turkey", "fish"],
    "produce": ["tomatoes", "onions", "apples", "oranges", "lettuce"],
    "party": ["soda", "paper_plates", "napkins", "chips", "cups"],
}


# ----------------------------
# gRPC reporting
# ----------------------------
def send_result(robot_id: str, task_id: str, ok: bool, msg: str,
                processed_items: list[tuple[str, float]],
                inv_grpc_addr: str):
    """Send task result back to the Inventory Service via gRPC."""
    with grpc.insecure_channel(inv_grpc_addr) as channel:
        stub = inv_robot_grpc.InventoryRobotServiceStub(channel)

        pb_items = [pb2.ItemQty(item=name, qty=qty)
                    for name, qty in processed_items]

        req = robot_pb2.RobotTaskResult(
            robot_id=robot_id,
            task_id=task_id,
            code=pb2.OK if ok else pb2.INTERNAL_ERROR,
            message=msg,
            timestamp_ms=int(time.time() * 1000),
            items=pb_items,
        )
        stub.ReportTaskResult(req, timeout=5)


# ----------------------------
# FlatBuffers decoders
# ----------------------------
def decode_fetch(payload: bytes):
    t = FetchTask.FetchTask.GetRootAsFetchTask(payload, 0)
    task_id = t.TaskId().decode()
    items = [(t.Items(i).Item().decode(), t.Items(i).Qty())
             for i in range(t.ItemsLength())]
    return task_id, items


def decode_restock(payload: bytes):
    t = RestockTask.RestockTask.GetRootAsRestockTask(payload, 0)
    task_id = t.TaskId().decode()
    items = [(t.Items(i).Item().decode(), t.Items(i).Qty())
             for i in range(t.ItemsLength())]
    return task_id, items


# ----------------------------
# Main loop
# ----------------------------
def main(robot_id: str, aisle: str, inv_grpc_addr: str, zmq_addr: str):
    my_items = set(AISLE_ITEMS[aisle])

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_addr)
    sub.setsockopt(zmq.SUBSCRIBE, b"FETCH")
    sub.setsockopt(zmq.SUBSCRIBE, b"RESTOCK")

    print(f"[robot_service] {robot_id} (aisle={aisle}) subscribed to "
          f"{zmq_addr}", flush=True)
    print(f"[robot_service] responsible for items: {sorted(my_items)}",
          flush=True)

    while True:
        topic, payload = sub.recv_multipart()
        topic = topic.decode()

        if topic == "FETCH":
            task_id, all_items = decode_fetch(payload)
        else:
            task_id, all_items = decode_restock(payload)

        # Filter to only items belonging to this robot's aisle
        my_task_items = [(name, qty) for name, qty in all_items
                         if name in my_items]

        print(f"[robot_service] {robot_id} got {topic} task_id={task_id} "
              f"all_items={all_items} my_items={my_task_items}", flush=True)

        # Simulate work only if there are items to process
        if my_task_items:
            time.sleep(1)
            msg = (f"{topic} completed by {robot_id}: "
                   f"{len(my_task_items)} items from {aisle}")
        else:
            msg = (f"{topic} completed by {robot_id}: "
                   f"0 items (no {aisle} items in order)")

        # Always report back so the barrier count reaches 5
        send_result(robot_id, task_id, ok=True, msg=msg,
                    processed_items=my_task_items,
                    inv_grpc_addr=inv_grpc_addr)
        print(f"[robot_service] {robot_id} sent result for {task_id} "
              f"({len(my_task_items)} items)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Robot Service")
    parser.add_argument(
        "--aisle", required=True,
        choices=list(AISLE_ITEMS.keys()),
        help="Aisle this robot is responsible for",
    )
    parser.add_argument(
        "--robot-id", default=None,
        help="Robot identifier (defaults to robot_<aisle>)",
    )
    parser.add_argument(
        "--inv-grpc", default=DEFAULT_INVENTORY_GRPC_ADDR,
        help=f"Inventory gRPC address (default: {DEFAULT_INVENTORY_GRPC_ADDR})",
    )
    parser.add_argument(
        "--zmq-addr", default=DEFAULT_ZMQ_SUB_ADDR,
        help=f"ZMQ SUB address (default: {DEFAULT_ZMQ_SUB_ADDR})",
    )

    args = parser.parse_args()

    rid = args.robot_id if args.robot_id else f"robot_{args.aisle}"
    main(robot_id=rid, aisle=args.aisle,
         inv_grpc_addr=args.inv_grpc, zmq_addr=args.zmq_addr)
