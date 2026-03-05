import os
import time
import uuid
from typing import Dict, Any, List

import grpc
import zmq
import flatbuffers
from flask import Flask, request, jsonify

from proto import common_pb2 as pb2
from proto import ordering_inventory_pb2_grpc as inv_grpc

from fbschemas.grocery.fb import AnalyticsEvent as FbAnalytics

app = Flask(__name__)

# PA2: Config via env for K8s multi-cluster (NodePort). Defaults = PA1 multi-VM IPs.
INVENTORY_HOST = os.environ.get("INVENTORY_HOST", "172.16.5.69")
INVENTORY_GRPC_PORT = os.environ.get("INVENTORY_GRPC_PORT", "50051")
INVENTORY_GRPC_ADDR = f"{INVENTORY_HOST}:{INVENTORY_GRPC_PORT}"
ANALYTICS_ZMQ_BIND = os.environ.get("ANALYTICS_ZMQ_BIND", "tcp://*:5557")
HTTP_PORT = int(os.environ.get("ORDERING_HTTP_PORT", "5001"))

# ----------------------------
# ZMQ publisher for analytics (created once at module level)
# ----------------------------
_zmq_ctx = zmq.Context()
_zmq_analytics_pub = _zmq_ctx.socket(zmq.PUB)
_zmq_analytics_pub.bind(ANALYTICS_ZMQ_BIND)
print(f"[ordering_service] analytics ZMQ PUB bound at {ANALYTICS_ZMQ_BIND}",
      flush=True)


# ----------------------------
# Analytics helpers
# ----------------------------
def _build_analytics_event(event_type: str, latency_ms: float,
                           success: bool) -> bytes:
    """Build a FlatBuffers AnalyticsEvent payload."""
    b = flatbuffers.Builder(256)

    eid_off = b.CreateString(str(uuid.uuid4()))
    src_off = b.CreateString("ordering_service")
    etype_off = b.CreateString(event_type)

    FbAnalytics.Start(b)
    FbAnalytics.AddEventId(b, eid_off)
    FbAnalytics.AddSource(b, src_off)
    FbAnalytics.AddEventType(b, etype_off)
    FbAnalytics.AddTimestampMs(b, int(time.time() * 1000))
    FbAnalytics.AddLatencyMs(b, latency_ms)
    FbAnalytics.AddSuccess(b, success)
    root = FbAnalytics.End(b)

    b.Finish(root)
    return bytes(b.Output())


def _publish_analytics(event_type: str, latency_ms: float, success: bool):
    """Publish an analytics event via ZMQ."""
    payload = _build_analytics_event(event_type, latency_ms, success)
    _zmq_analytics_pub.send_multipart([b"ANALYTICS", payload])
    print(f"[ordering_service] published analytics: type={event_type} "
          f"latency={latency_ms:.1f}ms success={success}", flush=True)


# ----------------------------
# Helpers
# ----------------------------
def _items_from_json(arr: Any) -> List[pb2.ItemQty]:
    if not isinstance(arr, list):
        return []
    out = []
    for x in arr:
        if not isinstance(x, dict):
            continue
        item = str(x.get("item", "")).strip()
        qty = x.get("qty", 0)
        try:
            qty = float(qty)
        except Exception:
            qty = 0.0
        if item and qty > 0:
            out.append(pb2.ItemQty(item=item, qty=qty))
    return out


def _order_from_json(order_json: Dict[str, Any]) -> pb2.Order:
    # Expecting: order = { "bread": [{item,qty}], "produce": [...], ... }
    return pb2.Order(
        bread=pb2.AisleItems(items=_items_from_json(order_json.get("bread"))),
        meat=pb2.AisleItems(items=_items_from_json(order_json.get("meat"))),
        produce=pb2.AisleItems(items=_items_from_json(order_json.get("produce"))),
        dairy=pb2.AisleItems(items=_items_from_json(order_json.get("dairy"))),
        party=pb2.AisleItems(items=_items_from_json(order_json.get("party"))),
    )


def _count_items(o: pb2.Order) -> int:
    return (
        len(o.bread.items)
        + len(o.meat.items)
        + len(o.produce.items)
        + len(o.dairy.items)
        + len(o.party.items)
    )


def _reply_code_name(code) -> str:
    """Get string name for ReplyCode enum (works for enum member or int from gRPC)."""
    if getattr(code, "name", None):
        return code.name
    names = {0: "REPLY_CODE_UNSPECIFIED", 1: "OK", 2: "BAD_REQUEST", 3: "INTERNAL_ERROR"}
    return names.get(int(code), str(code))


def _call_inventory(req_pb: pb2.OrderRequest) -> pb2.BasicReply:
    with grpc.insecure_channel(INVENTORY_GRPC_ADDR) as channel:
        stub = inv_grpc.InventoryServiceStub(channel)
        # Timeout must exceed the inventory barrier timeout (10s) + buffer
        return stub.ProcessOrder(req_pb, timeout=20)


# ----------------------------
# Routes
# ----------------------------
@app.post("/api/order")
def grocery_order():
    t_start = time.perf_counter()

    data = request.get_json(silent=True) or {}
    customer_id = str(data.get("customer_id", "")).strip()
    order_json = data.get("order", {})

    req_pb = pb2.OrderRequest(
        message_type=pb2.MessageType.GROCERY_ORDER,
        customer_id=customer_id,
        timestamp_ms=int(time.time() * 1000),
        order=_order_from_json(order_json if isinstance(order_json, dict) else {}),
    )

    if not customer_id:
        return jsonify({"code": "BAD_REQUEST", "message": "customer_id required"}), 400
    if _count_items(req_pb.order) == 0:
        return jsonify({"code": "BAD_REQUEST", "message": "order cannot be empty"}), 400

    # Ordering -> Inventory via gRPC/Protobuf
    try:
        resp = _call_inventory(req_pb)
        success = (resp.code == pb2.ReplyCode.OK)
    except Exception as e:
        latency_ms = (time.perf_counter() - t_start) * 1000
        _publish_analytics("GROCERY_ORDER", latency_ms, False)
        return jsonify({"code": "INTERNAL_ERROR", "message": str(e)}), 500

    t_end = time.perf_counter()
    latency_ms = (t_end - t_start) * 1000

    # Publish analytics event
    _publish_analytics("GROCERY_ORDER", latency_ms, success)

    http_code = 200 if success else 400
    code_name = _reply_code_name(resp.code)
    items_list = [{"item": it.item, "qty": it.qty} for it in resp.items]
    result = {"code": code_name, "message": resp.message, "items": items_list}
    if resp.total_price > 0:
        result["total_price"] = round(resp.total_price, 2)
    return jsonify(result), http_code


@app.post("/api/restock")
def restock_order():
    t_start = time.perf_counter()

    data = request.get_json(silent=True) or {}
    supplier_id = str(data.get("supplier_id", "")).strip()
    order_json = data.get("order", {})

    req_pb = pb2.OrderRequest(
        message_type=pb2.MessageType.RESTOCK_ORDER,
        supplier_id=supplier_id,
        timestamp_ms=int(time.time() * 1000),
        order=_order_from_json(order_json if isinstance(order_json, dict) else {}),
    )

    if not supplier_id:
        return jsonify({"code": "BAD_REQUEST", "message": "supplier_id required"}), 400
    if _count_items(req_pb.order) == 0:
        return jsonify({"code": "BAD_REQUEST", "message": "restock order cannot be empty"}), 400

    try:
        resp = _call_inventory(req_pb)
        success = (resp.code == pb2.ReplyCode.OK)
    except Exception as e:
        latency_ms = (time.perf_counter() - t_start) * 1000
        _publish_analytics("RESTOCK_ORDER", latency_ms, False)
        return jsonify({"code": "INTERNAL_ERROR", "message": str(e)}), 500

    t_end = time.perf_counter()
    latency_ms = (t_end - t_start) * 1000

    # Publish analytics event
    _publish_analytics("RESTOCK_ORDER", latency_ms, success)

    http_code = 200 if success else 400
    code_name = _reply_code_name(resp.code)
    items_list = [{"item": it.item, "qty": it.qty} for it in resp.items]
    result = {"code": code_name, "message": resp.message, "items": items_list}
    if resp.total_price > 0:
        result["total_price"] = round(resp.total_price, 2)
    return jsonify(result), http_code


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    # use_reloader=False because the ZMQ PUB socket is bound at module level
    app.run(host="0.0.0.0", port=HTTP_PORT, debug=True, use_reloader=False)
