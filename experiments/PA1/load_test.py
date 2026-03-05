"""
Load test script for the Automated Grocery Ordering System.

Runs 3 experiments and writes results to experiments/results.csv:
  1. Varying order size (1, 5, 10, 15, 25 items)
  2. Consecutive orders under load (20 back-to-back orders)
  3. Orders vs Restocks latency comparison

Prerequisites: all services must be running.

Usage:
    python3 -m experiments.load_test
    python3 -m experiments.load_test --base-url http://129.114.25.180:5001
"""

import argparse
import csv
import os
import time
import requests

# ----------------------------
# Item catalog (all 25 items)
# ----------------------------
ALL_ITEMS = {
    "bread": ["bagels", "bread", "waffles", "tortillas", "buns"],
    "dairy": ["milk", "eggs", "cheese", "yogurt", "butter"],
    "meat": ["chicken", "beef", "pork", "turkey", "fish"],
    "produce": ["tomatoes", "onions", "apples", "oranges", "lettuce"],
    "party": ["soda", "paper_plates", "napkins", "chips", "cups"],
}

# Flat list for easy slicing
FLAT_ITEMS = []
for aisle, items in ALL_ITEMS.items():
    for item in items:
        FLAT_ITEMS.append((aisle, item))


def build_order_payload(items: list[tuple[str, str]], qty: int = 1) -> dict:
    """Build a JSON order payload from a list of (aisle, item) tuples."""
    order = {}
    for aisle, item in items:
        if aisle not in order:
            order[aisle] = []
        order[aisle].append({"item": item, "qty": qty})
    return order


def send_order(base_url: str, order_payload: dict,
               customer_id: str = "loadtest") -> tuple[float, bool, dict]:
    """Send a grocery order. Returns (latency_ms, success, response_body)."""
    url = f"{base_url}/api/order"
    body = {
        "customer_id": customer_id,
        "order": order_payload,
    }
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=body, timeout=30)
        latency_ms = (time.perf_counter() - t0) * 1000
        return latency_ms, r.ok, r.json()
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        return latency_ms, False, {"error": str(e)}


def send_restock(base_url: str, order_payload: dict,
                 supplier_id: str = "loadtest_supplier") -> tuple[float, bool, dict]:
    """Send a restock order. Returns (latency_ms, success, response_body)."""
    url = f"{base_url}/api/restock"
    body = {
        "supplier_id": supplier_id,
        "order": order_payload,
    }
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=body, timeout=30)
        latency_ms = (time.perf_counter() - t0) * 1000
        return latency_ms, r.ok, r.json()
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        return latency_ms, False, {"error": str(e)}


def experiment_1_order_size(base_url: str, writer, sizes=None):
    """Experiment 1: Varying order sizes."""
    if sizes is None:
        sizes = [1, 5, 10, 15, 25]

    print("\n" + "=" * 60)
    print("EXPERIMENT 1: Varying Order Size")
    print("=" * 60)

    for n in sizes:
        items = FLAT_ITEMS[:n]
        payload = build_order_payload(items, qty=1)

        # Do a restock first so we don't run out of inventory
        send_restock(base_url, build_order_payload(FLAT_ITEMS[:25], qty=100))

        latency, success, resp = send_order(base_url, payload)
        status = "OK" if success else "FAIL"
        print(f"  {n:2d} items -> {latency:7.1f} ms  [{status}]")

        writer.writerow({
            "experiment": "order_size",
            "label": str(n),
            "type": "GROCERY_ORDER",
            "num_items": n,
            "latency_ms": round(latency, 1),
            "success": success,
        })


def experiment_2_consecutive(base_url: str, writer, count=20):
    """Experiment 2: Consecutive orders under load."""
    print("\n" + "=" * 60)
    print(f"EXPERIMENT 2: {count} Consecutive Orders")
    print("=" * 60)

    # Restock heavily first
    send_restock(base_url, build_order_payload(FLAT_ITEMS[:25], qty=500))

    for i in range(1, count + 1):
        # 3-item order each time
        items = [FLAT_ITEMS[i % 25], FLAT_ITEMS[(i + 7) % 25], FLAT_ITEMS[(i + 14) % 25]]
        payload = build_order_payload(items, qty=1)

        latency, success, resp = send_order(base_url, payload)
        status = "OK" if success else "FAIL"
        print(f"  order {i:2d}/{count} -> {latency:7.1f} ms  [{status}]")

        writer.writerow({
            "experiment": "consecutive",
            "label": str(i),
            "type": "GROCERY_ORDER",
            "num_items": 3,
            "latency_ms": round(latency, 1),
            "success": success,
        })


def experiment_3_order_vs_restock(base_url: str, writer, count=10):
    """Experiment 3: Orders vs Restocks latency comparison."""
    print("\n" + "=" * 60)
    print(f"EXPERIMENT 3: Orders vs Restocks ({count} each)")
    print("=" * 60)

    # Restock heavily first so orders don't fail
    send_restock(base_url, build_order_payload(FLAT_ITEMS[:25], qty=500))

    items_5 = FLAT_ITEMS[:5]
    payload = build_order_payload(items_5, qty=1)

    print("  --- Grocery Orders ---")
    for i in range(1, count + 1):
        latency, success, resp = send_order(base_url, payload)
        status = "OK" if success else "FAIL"
        print(f"    order {i:2d}/{count} -> {latency:7.1f} ms  [{status}]")

        writer.writerow({
            "experiment": "order_vs_restock",
            "label": f"order_{i}",
            "type": "GROCERY_ORDER",
            "num_items": 5,
            "latency_ms": round(latency, 1),
            "success": success,
        })

    print("  --- Restock Orders ---")
    restock_payload = build_order_payload(items_5, qty=10)
    for i in range(1, count + 1):
        latency, success, resp = send_restock(base_url, restock_payload)
        status = "OK" if success else "FAIL"
        print(f"    restock {i:2d}/{count} -> {latency:7.1f} ms  [{status}]")

        writer.writerow({
            "experiment": "order_vs_restock",
            "label": f"restock_{i}",
            "type": "RESTOCK_ORDER",
            "num_items": 5,
            "latency_ms": round(latency, 1),
            "success": success,
        })


def main():
    parser = argparse.ArgumentParser(description="Load Test")
    parser.add_argument("--base-url", default="http://localhost:5001",
                        help="Ordering service base URL")
    args = parser.parse_args()

    out_dir = os.path.join(os.path.dirname(__file__))
    csv_path = os.path.join(out_dir, "results.csv")

    fieldnames = ["experiment", "label", "type", "num_items",
                  "latency_ms", "success"]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        experiment_1_order_size(args.base_url, writer)
        experiment_2_consecutive(args.base_url, writer)
        experiment_3_order_vs_restock(args.base_url, writer)

    print(f"\nResults written to {csv_path}")
    print("Run:  python3 -m experiments.plot_results")


if __name__ == "__main__":
    main()
