#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# run_pa3_experiments.sh
#
# Runs 5 Locust scenarios in headless mode for PA3 Milestone 3.
# Results are bucketed by mode ("with_hil" or "without_hil") so
# the analysis script can compare latencies side by side.
#
# Usage:
#   chmod +x experiments/PA3/run_pa3_experiments.sh
#
#   # Without ContainerLab HIL (direct K8s NodePort path):
#   ./experiments/PA3/run_pa3_experiments.sh --mode without_hil --host http://localhost:30601
#
#   # With ContainerLab HIL deployed (traffic routed through HIL1+HIL2):
#   ./experiments/PA3/run_pa3_experiments.sh --mode with_hil --host http://localhost:30601
#
#   # Defaults: mode=without_hil, host=http://172.16.2.136:30601
#   ./experiments/PA3/run_pa3_experiments.sh
# ──────────────────────────────────────────────────────────────
set -uo pipefail

# ── Defaults ──────────────────────────────────────────────────
MODE="without_hil"
HOST="http://172.16.2.136:30601"

# ── Parse CLI flags ───────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            MODE="$2"; shift 2 ;;
        --host)
            HOST="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--mode with_hil|without_hil] [--host URL]"
            exit 0 ;;
        *)
            echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ "$MODE" != "with_hil" && "$MODE" != "without_hil" ]]; then
    echo "Error: --mode must be 'with_hil' or 'without_hil' (got '${MODE}')"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCUSTFILE="${SCRIPT_DIR}/locustfile.py"
RESULTS_DIR="${SCRIPT_DIR}/results/${MODE}"

# ── Scenario definitions ─────────────────────────────────────
#         name        users  spawn-rate  run-time
SCENARIOS=(
    "low_load        5      1           60s"
    "medium_load     20     5           90s"
    "high_load       50     10          120s"
    "burst           100    50          60s"
    "ramp_up         50     1           180s"
)

echo "=============================================="
echo "  PA3 Milestone 3 — Locust Experiment Suite"
echo "  Mode:    ${MODE}"
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
    echo "  Scenario: ${name}  [${MODE}]"
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

    echo "  -> ${name} complete -> ${out_dir}/"
done

echo ""
echo "=============================================="
echo "  All scenarios complete for mode: ${MODE}"
echo "  Run analysis:  python3 -m experiments.PA3.analyze_pa3_latencies"
echo "=============================================="
