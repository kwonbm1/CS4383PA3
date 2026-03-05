"""
Locust.io workload generator for the Automated Grocery Ordering System.

Simulates two types of users:
  - RefrigeratorUser (weight=7): Smart fridges placing grocery orders (POST /api/order)
  - TruckUser       (weight=3): Delivery trucks placing restock orders (POST /api/restock)

Refrigerator requests dominate (~70%) as specified in the PA2 requirements.

A custom event listener logs per-request latencies to a CSV file for accurate
CDF / tail-latency analysis (P50, P90, P95, P99).

Usage (web UI):
    locust -f experiments/locustfile.py --host http://172.16.2.136:30601

Usage (headless):
    locust -f experiments/locustfile.py --host http://172.16.2.136:30601 \
        --headless -u 20 -r 5 -t 60s --csv experiments/results/medium

If running via SSH tunnel:
    ssh -L 30601:172.16.2.136:30601 bastion
    locust -f experiments/locustfile.py --host http://localhost:30601
"""

import csv
import os
import random
import time
import threading

from locust import HttpUser, task, between, events

# ─────────────────────────────────────────────
# Item catalog (matches the 25-item system)
# ─────────────────────────────────────────────
AISLES = {
    "bread":   ["bagels", "bread", "waffles", "tortillas", "buns"],
    "dairy":   ["milk", "eggs", "cheese", "yogurt", "butter"],
    "meat":    ["chicken", "beef", "pork", "turkey", "fish"],
    "produce": ["tomatoes", "onions", "apples", "oranges", "lettuce"],
    "party":   ["soda", "paper_plates", "napkins", "chips", "cups"],
}

FLAT_ITEMS = []
for aisle, items in AISLES.items():
    for item in items:
        FLAT_ITEMS.append((aisle, item))


# ─────────────────────────────────────────────
# Payload builders
# ─────────────────────────────────────────────
def build_order_payload(items: list, qty_range=(1, 5)):
    """Build a JSON order payload from a list of (aisle, item) tuples."""
    order = {}
    for aisle, item in items:
        if aisle not in order:
            order[aisle] = []
        qty = random.randint(*qty_range)
        order[aisle].append({"item": item, "qty": qty})
    return order


def random_grocery_order():
    """Generate a random grocery order (1–10 items, qty 1–3 each)."""
    n_items = random.randint(1, 10)
    items = random.sample(FLAT_ITEMS, k=n_items)
    return build_order_payload(items, qty_range=(1, 3))


def random_restock_order():
    """Generate a random restock order (3–15 items, qty 10–50 each)."""
    n_items = random.randint(3, 15)
    items = random.sample(FLAT_ITEMS, k=n_items)
    return build_order_payload(items, qty_range=(10, 50))


def big_restock_payload():
    """Build a large restock to refill all inventory (used as setup)."""
    return build_order_payload(FLAT_ITEMS, qty_range=(200, 200))


# ─────────────────────────────────────────────
# Per-request latency logger (custom event listener)
# ─────────────────────────────────────────────
_latency_lock = threading.Lock()
_latency_rows = []
_latency_file = None
_latency_writer = None


def _get_latency_dir():
    """Resolve directory for latency logs, respecting LOCUST_CSV env var."""
    csv_prefix = os.environ.get("LOCUST_CSV", "")
    if csv_prefix:
        return os.path.dirname(csv_prefix) or "."
    return os.path.join(os.path.dirname(__file__), "results")


@events.test_start.add_listener
def _on_test_start(environment, **kwargs):
    """Open per-request CSV at test start."""
    global _latency_file, _latency_writer, _latency_rows

    out_dir = _get_latency_dir()
    os.makedirs(out_dir, exist_ok=True)

    csv_prefix = os.environ.get("LOCUST_CSV", "")
    if csv_prefix:
        path = f"{csv_prefix}_raw_latencies.csv"
    else:
        path = os.path.join(out_dir, "raw_latencies.csv")

    _latency_rows = []
    _latency_file = open(path, "w", newline="")
    _latency_writer = csv.writer(_latency_file)
    _latency_writer.writerow([
        "timestamp", "request_type", "name", "response_time_ms",
        "response_length", "success", "num_users",
    ])
    print(f"[locust] per-request latencies → {path}")


@events.test_stop.add_listener
def _on_test_stop(environment, **kwargs):
    """Flush and close the latency CSV."""
    global _latency_file
    if _latency_file:
        with _latency_lock:
            _latency_file.close()
            _latency_file = None
        print("[locust] latency CSV closed.")


@events.request.add_listener
def _on_request(request_type, name, response_time, response_length,
                exception, context, **kwargs):
    """Log every single request to CSV for CDF analysis."""
    if _latency_writer is None:
        return
    # Determine current user count from the runner
    try:
        num_users = kwargs.get("environment", context).runner.user_count
    except Exception:
        num_users = -1

    row = [
        time.time(),
        request_type,
        name,
        round(response_time, 2),
        response_length or 0,
        exception is None,
        num_users,
    ]
    with _latency_lock:
        if _latency_writer:
            _latency_writer.writerow(row)
            _latency_file.flush()


# ─────────────────────────────────────────────
# Locust User classes
# ─────────────────────────────────────────────
class RefrigeratorUser(HttpUser):
    """
    Smart refrigerator: places grocery (FETCH) orders.

    Weight=7  →  ~70 % of simulated users are refrigerators.
    Wait time: 1–3 s between requests (realistic fridge polling interval).
    """
    weight = 7
    wait_time = between(1, 3)

    def on_start(self):
        """Pre-restock inventory so orders don't fail due to empty stock."""
        self.client.post("/api/restock", json={
            "supplier_id": "locust_setup",
            "order": big_restock_payload(),
        }, name="/api/restock [setup]")

    @task
    def place_grocery_order(self):
        payload = {
            "customer_id": f"fridge_{self.environment.runner.user_count}_{random.randint(1, 9999)}",
            "order": random_grocery_order(),
        }
        self.client.post("/api/order", json=payload, name="/api/order")


class TruckUser(HttpUser):
    """
    Delivery truck: places restock orders.

    Weight=3  →  ~30 % of simulated users are trucks.
    Wait time: 2–5 s between requests (trucks arrive less frequently).
    """
    weight = 3
    wait_time = between(2, 5)

    @task
    def place_restock_order(self):
        payload = {
            "supplier_id": f"truck_{random.randint(1, 500)}",
            "order": random_restock_order(),
        }
        self.client.post("/api/restock", json=payload, name="/api/restock")
