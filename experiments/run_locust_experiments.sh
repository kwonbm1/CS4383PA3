#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# run_locust_experiments.sh
#
# Runs 5 Locust scenarios in headless mode, saving CSV + raw
# latency data to experiments/results/<scenario>/
#
# Usage:
#   chmod +x experiments/run_locust_experiments.sh
#   ./experiments/run_locust_experiments.sh                        # default host
#   ./experiments/run_locust_experiments.sh http://localhost:30601  # custom host
# ──────────────────────────────────────────────────────────────
set -uo pipefail

HOST="${1:-http://172.16.2.136:30601}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCUSTFILE="${SCRIPT_DIR}/locustfile.py"
RESULTS_DIR="${SCRIPT_DIR}/results"

# ── Scenario definitions ──────────────────────────────────────
#         name        users  spawn-rate  run-time
SCENARIOS=(
    "low_load        5      1           60s"
    "medium_load     20     5           90s"
    "high_load       50     10          120s"
    "burst           100    50          60s"
    "ramp_up         50     1           180s"
)

echo "=============================================="
echo "  Locust Experiment Suite — Milestone 2"
echo "  Host:    ${HOST}"
echo "  Output:  ${RESULTS_DIR}/<scenario>/"
echo "=============================================="

for entry in "${SCENARIOS[@]}"; do
    read -r name users rate duration <<< "$entry"
    out_dir="${RESULTS_DIR}/${name}"
    mkdir -p "$out_dir"
    csv_prefix="${out_dir}/${name}"

    echo ""
    echo "────────────────────────────────────────────"
    echo "  Scenario: ${name}"
    echo "  Users=${users}  SpawnRate=${rate}/s  Duration=${duration}"
    echo "────────────────────────────────────────────"

    LOCUST_CSV="${csv_prefix}" locust \
        -f "$LOCUSTFILE" \
        --host "$HOST" \
        --headless \
        -u "$users" \
        -r "$rate" \
        -t "$duration" \
        --csv "$csv_prefix" \
        --csv-full-history \
        --skip-log 2>&1 | tail -5 || true

    echo "  ✓ ${name} complete → ${out_dir}/"
done

echo ""
echo "=============================================="
echo "  All scenarios complete!"
echo "  Run analysis:  python3 -m experiments.analyze_latencies"
echo "=============================================="
