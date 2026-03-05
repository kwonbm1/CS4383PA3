import json
import os
import time
from typing import Dict, List, Any, Tuple

import requests
import streamlit as st


# -----------------------------
# Config
# -----------------------------
# PA2: Config via env for K8s multi-cluster (NodePort). Defaults = PA1 multi-VM.
ORDERING_HOST = os.environ.get("ORDERING_HOST", "172.16.5.77")
ORDERING_HTTP_PORT = os.environ.get("ORDERING_HTTP_PORT", "5001")
DEFAULT_ORDERING_BASE_URL = f"http://{ORDERING_HOST}:{ORDERING_HTTP_PORT}"
DEFAULT_ORDER_ENDPOINT = "/api/order"
DEFAULT_RESTOCK_ENDPOINT = "/api/restock"
DEFAULT_TIMEOUT_SECS = 25  # ordering→inventory→robots+pricing can exceed 10s


# -----------------------------
# Helpers
# -----------------------------
AISLES = {
    "bread": ["bagels", "bread", "waffles", "tortillas", "buns"],
    "dairy": ["milk", "eggs", "cheese", "yogurt", "butter"],
    "meat": ["chicken", "beef", "pork", "turkey", "fish"],
    "produce": ["tomatoes", "onions", "apples", "oranges", "lettuce"],
    "party": ["soda", "paper_plates", "napkins", "chips", "cups"],
}


def init_state():
    if "order_rows" not in st.session_state:
        st.session_state.order_rows = {aisle: [new_row(aisle)] for aisle in AISLES.keys()}
    if "restock_rows" not in st.session_state:
        st.session_state.restock_rows = {aisle: [new_row(aisle)] for aisle in AISLES.keys()}


def new_row(aisle: str) -> Dict[str, Any]:
    return {"item": AISLES[aisle][0], "qty": 1}


def rows_to_items(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for r in rows:
        item = (r.get("item") or "").strip()
        qty = r.get("qty", 0)
        try:
            qty_num = float(qty)
        except Exception:
            qty_num = 0

        if item and qty_num > 0:
            items.append({"item": item, "qty": qty_num})
    return items


def build_payload(message_type: str, actor_id_label: str, actor_id_value: str, aisle_rows: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "message_type": message_type,                 # GROCERY_ORDER or RESTOCK_ORDER
        actor_id_label: actor_id_value,               # customer_id or supplier_id
        "timestamp_ms": int(time.time() * 1000),
        "order": {},
    }

    total_items = 0
    for aisle, rows in aisle_rows.items():
        items = rows_to_items(rows)
        if items:
            payload["order"][aisle] = items
            total_items += len(items)

    payload["num_line_items"] = total_items
    return payload


def validate_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    if payload.get("message_type") not in {"GROCERY_ORDER", "RESTOCK_ORDER"}:
        return False, "message_type must be GROCERY_ORDER or RESTOCK_ORDER"

    order_obj = payload.get("order", {})
    if not isinstance(order_obj, dict) or len(order_obj) == 0:
        return False, "You must include at least one item (order cannot be empty)."

    if payload["message_type"] == "GROCERY_ORDER":
        if not payload.get("customer_id", "").strip():
            return False, "customer_id is required."
    else:
        if not payload.get("supplier_id", "").strip():
            return False, "supplier_id is required."

    return True, ""


def post_json(url: str, payload: Dict[str, Any], timeout_s: int) -> Tuple[bool, str, Any, int]:
    """Returns (success, status_text, body, http_status_code)."""
    try:
        r = requests.post(url, json=payload, timeout=timeout_s)
        content_type = r.headers.get("content-type", "")
        if "application/json" in content_type.lower():
            body = r.json()
        else:
            body = r.text

        if r.ok:
            return True, f"HTTP {r.status_code}", body, r.status_code
        return False, f"HTTP {r.status_code}", body, r.status_code
    except requests.exceptions.RequestException as e:
        return False, "Request failed", str(e), 0


def add_row(state_key: str, aisle: str):
    st.session_state[state_key][aisle].append(new_row(aisle))


def remove_row(state_key: str, aisle: str, idx: int):
    rows = st.session_state[state_key][aisle]
    if len(rows) <= 1:
        return
    if 0 <= idx < len(rows):
        rows.pop(idx)


def aisle_editor(state_key: str, aisle: str):
    st.subheader(aisle.capitalize())

    rows = st.session_state[state_key][aisle]
    for i, row in enumerate(rows):
        c1, c2, c3 = st.columns([6, 3, 2])

        with c1:
            row["item"] = st.selectbox(
                "Item",
                options=AISLES[aisle],
                index=AISLES[aisle].index(row["item"]) if row["item"] in AISLES[aisle] else 0,
                key=f"{state_key}_{aisle}_item_{i}",
                label_visibility="collapsed",
            )

        with c2:
            row["qty"] = st.number_input(
                "Qty",
                min_value=0.0,
                value=float(row.get("qty", 1)),
                step=1.0,
                key=f"{state_key}_{aisle}_qty_{i}",
                label_visibility="collapsed",
            )

        with c3:
            if st.button("Remove", key=f"{state_key}_{aisle}_remove_{i}"):
                remove_row(state_key, aisle, i)
                st.rerun()

    if st.button(f"Add {aisle} item", key=f"{state_key}_{aisle}_add"):
        add_row(state_key, aisle)
        st.rerun()


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Grocery Client", page_icon="🛒", layout="wide")
init_state()

st.title("Automated Grocery Ordering Client (Streamlit)")
st.caption("Submit Grocery Orders (smart fridge) or Restock Orders (truck) to your Ordering Service over HTTP JSON.")

with st.sidebar:
    st.header("Connection")
    st.caption("If you see 403 in the UI but 200 in DevTools, the 403 may be from Streamlit (XSRF). Run with: streamlit run client/app.py --server.enableXsrfProtection false")
    base_url = st.text_input("Ordering Service base URL", value=DEFAULT_ORDERING_BASE_URL)
    order_path = st.text_input("Order endpoint path", value=DEFAULT_ORDER_ENDPOINT)
    restock_path = st.text_input("Restock endpoint path", value=DEFAULT_RESTOCK_ENDPOINT)
    timeout_s = st.number_input("Timeout (seconds)", min_value=1, max_value=60, value=DEFAULT_TIMEOUT_SECS)

    st.divider()
    st.write("Full URLs:")
    st.code(f"{base_url.rstrip('/')}{order_path}", language="text")
    st.code(f"{base_url.rstrip('/')}{restock_path}", language="text")

tabs = st.tabs(["Grocery Order", "Restock Order", "Raw Payload Preview"])


# -----------------------------
# Grocery Order Tab
# -----------------------------
with tabs[0]:
    st.header("Grocery Order (Customer)")
    customer_id = st.text_input("Customer ID", placeholder="e.g., cust_123")

    left, right = st.columns([1, 1], gap="large")
    with left:
        aisle_editor("order_rows", "bread")
        aisle_editor("order_rows", "dairy")
        aisle_editor("order_rows", "meat")

    with right:
        aisle_editor("order_rows", "produce")
        aisle_editor("order_rows", "party")

    payload_order = build_payload(
        message_type="GROCERY_ORDER",
        actor_id_label="customer_id",
        actor_id_value=customer_id,
        aisle_rows=st.session_state.order_rows,
    )

    ok, err = validate_payload(payload_order)

    c1, c2 = st.columns([1, 3])
    with c1:
        submit = st.button("Submit Grocery Order", type="primary", use_container_width=True, disabled=not ok)
    with c2:
        if not ok:
            st.error(err)

    if submit:
        url = f"{base_url.rstrip('/')}{order_path}"
        success, status, body, http_code = post_json(url, payload_order, int(timeout_s))
        if success:
            st.success(f"Sent successfully. {status}")
        else:
            st.error(f"Failed to send. {status} (this is the Ordering Service HTTP status)")

        st.subheader("Server Response")
        st.caption(f"HTTP status from Ordering Service: {http_code}")
        if isinstance(body, (dict, list)):
            st.json(body)
        else:
            st.code(str(body), language="text")


# -----------------------------
# Restock Tab
# -----------------------------
with tabs[1]:
    st.header("Restock Order (Supplier / Truck)")
    supplier_id = st.text_input("Supplier ID", placeholder="e.g., supplier_77")

    left, right = st.columns([1, 1], gap="large")
    with left:
        aisle_editor("restock_rows", "bread")
        aisle_editor("restock_rows", "dairy")
        aisle_editor("restock_rows", "meat")

    with right:
        aisle_editor("restock_rows", "produce")
        aisle_editor("restock_rows", "party")

    payload_restock = build_payload(
        message_type="RESTOCK_ORDER",
        actor_id_label="supplier_id",
        actor_id_value=supplier_id,
        aisle_rows=st.session_state.restock_rows,
    )

    ok2, err2 = validate_payload(payload_restock)

    c1, c2 = st.columns([1, 3])
    with c1:
        submit2 = st.button("Submit Restock Order", type="primary", use_container_width=True, disabled=not ok2)
    with c2:
        if not ok2:
            st.error(err2)

    if submit2:
        url = f"{base_url.rstrip('/')}{restock_path}"
        success, status, body, http_code = post_json(url, payload_restock, int(timeout_s))
        if success:
            st.success(f"Sent successfully. {status}")
        else:
            st.error(f"Failed to send. {status} (this is the Ordering Service HTTP status)")

        st.subheader("Server Response")
        st.caption(f"HTTP status from Ordering Service: {http_code}")
        if isinstance(body, (dict, list)):
            st.json(body)
        else:
            st.code(str(body), language="text")


# -----------------------------
# Raw Payload Preview
# -----------------------------
with tabs[2]:
    st.header("Raw Payload Preview")
    st.write("This is what your Streamlit client is sending to the Ordering Service.")
    st.subheader("Grocery Order Payload")
    st.code(json.dumps(payload_order, indent=2), language="json")

    st.subheader("Restock Order Payload")
    st.code(json.dumps(payload_restock, indent=2), language="json")

    st.info(
        "Make your Ordering service accept these JSON fields (message_type, customer_id/supplier_id, order). "
        "If your API expects different keys, change build_payload() to match."
    )
