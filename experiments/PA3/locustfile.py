"""
PA3 Milestone 3 — Locust workload generator.

Thin wrapper that re-exports the PA2 RefrigeratorUser / TruckUser classes
and their latency-logging event listeners so the same workload profile is
used for both "with HIL" and "without HIL" experiments.

Usage (headless, example):
    LOCUST_CSV=experiments/PA3/results/with_hil/low_load/low_load \
    locust -f experiments/PA3/locustfile.py --host http://localhost:30601 \
        --headless -u 5 -r 1 -t 60s \
        --csv experiments/PA3/results/with_hil/low_load/low_load
"""

import os
import sys

# Ensure the PA2 directory is on sys.path so Locust discovers user classes
_pa2_dir = os.path.join(os.path.dirname(__file__), os.pardir, "PA2")
_pa2_dir = os.path.abspath(_pa2_dir)
if _pa2_dir not in sys.path:
    sys.path.insert(0, _pa2_dir)

# Re-export everything Locust needs: user classes + event listeners
from locustfile import (          # noqa: F401, E402
    RefrigeratorUser,
    TruckUser,
    AISLES,
    FLAT_ITEMS,
    build_order_payload,
    random_grocery_order,
    random_restock_order,
    big_restock_payload,
)
