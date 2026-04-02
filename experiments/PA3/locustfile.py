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

import importlib.util
import os
import sys

# Load the PA2 locustfile by absolute path to avoid circular import
# (both files are named locustfile.py, so sys.path tricks don't work).
_pa2_locustfile = os.path.join(
    os.path.dirname(__file__), os.pardir, "PA2", "locustfile.py"
)
_pa2_locustfile = os.path.abspath(_pa2_locustfile)

_spec = importlib.util.spec_from_file_location("pa2_locustfile", _pa2_locustfile)
_pa2 = importlib.util.module_from_spec(_spec)
sys.modules["pa2_locustfile"] = _pa2
_spec.loader.exec_module(_pa2)

# Re-export everything Locust needs: user classes + event listeners
RefrigeratorUser = _pa2.RefrigeratorUser            # noqa: F811
TruckUser = _pa2.TruckUser                          # noqa: F811
