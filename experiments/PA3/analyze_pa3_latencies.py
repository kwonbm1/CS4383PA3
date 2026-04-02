"""
PA3 Milestone 3 — Comparative tail-latency analysis.

Loads raw per-request latency CSVs from both ``with_hil/`` and
``without_hil/`` result directories, computes P50/P90/P95/P99, and
generates side-by-side comparison plots.

Generated plots (saved to ``experiments/PA3/plots/``):

    cdf_<scenario>.png                Per-scenario CDF overlay (with vs without HIL)
    cdf_compare_api_order.png         Cross-scenario CDF for refrigerator requests
    cdf_compare_api_restock.png       Cross-scenario CDF for truck requests
    percentile_bars_api_order.png     Grouped bar chart (with/without HIL) — orders
    percentile_bars_api_restock.png   Grouped bar chart (with/without HIL) — restocks
    hil_overhead.png                  Delta chart showing latency increase from HIL
    cdf_combined_all.png              All modes + scenarios overlaid

Usage:
    python3 -m experiments.PA3.analyze_pa3_latencies
    python3 -m experiments.PA3.analyze_pa3_latencies --results-dir experiments/PA3/results
"""

import argparse
import csv
import glob
import os
import sys

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
PERCENTILES = [50, 90, 95, 99]
SCENARIO_ORDER = ["low_load", "medium_load", "high_load", "burst", "ramp_up"]
MODE_LABELS = {"without_hil": "Without HIL", "with_hil": "With HIL"}
MODE_STYLES = {
    "without_hil": {"linestyle": "-",  "alpha": 1.0},
    "with_hil":    {"linestyle": "--", "alpha": 1.0},
}
SCENARIO_COLORS = {
    "low_load":    "#2196F3",
    "medium_load": "#4CAF50",
    "high_load":   "#FF9800",
    "burst":       "#F44336",
    "ramp_up":     "#9C27B0",
}
REQUEST_COLORS = {
    "/api/order":   "#1565C0",
    "/api/restock": "#2E7D32",
}


# ─────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────
def load_raw_latencies(csv_path: str) -> list[dict]:
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if "[setup]" in r.get("name", ""):
                continue
            try:
                rows.append({
                    "timestamp":        float(r["timestamp"]),
                    "request_type":     r["request_type"],
                    "name":             r["name"],
                    "response_time_ms": float(r["response_time_ms"]),
                    "success":          r["success"].strip().lower() == "true",
                })
            except (KeyError, ValueError):
                continue
    return rows


def discover_modes(results_dir: str) -> dict[str, dict[str, list[dict]]]:
    """Return {mode: {scenario: [rows]}} for every mode directory found."""
    modes: dict[str, dict[str, list[dict]]] = {}

    for mode in ("without_hil", "with_hil"):
        mode_dir = os.path.join(results_dir, mode)
        if not os.path.isdir(mode_dir):
            continue
        scenarios: dict[str, list[dict]] = {}
        for subdir in sorted(os.listdir(mode_dir)):
            path = os.path.join(mode_dir, subdir)
            if not os.path.isdir(path):
                continue
            candidates = glob.glob(os.path.join(path, "*_raw_latencies.csv"))
            if candidates:
                rows = load_raw_latencies(candidates[0])
                if rows:
                    scenarios[subdir] = rows
        if scenarios:
            modes[mode] = scenarios

    return modes


# ─────────────────────────────────────────────
# Percentile helpers
# ─────────────────────────────────────────────
def compute_percentiles(latencies: list[float]) -> dict[int, float]:
    arr = np.array(latencies)
    return {p: float(np.percentile(arr, p)) for p in PERCENTILES}


def _ordered_scenarios(scenarios: dict) -> list[str]:
    ordered = [s for s in SCENARIO_ORDER if s in scenarios]
    ordered += [s for s in scenarios if s not in ordered]
    return ordered


# ─────────────────────────────────────────────
# Plotting helpers
# ─────────────────────────────────────────────
def _plot_cdf(latencies, label, ax, color=None, linestyle="-", linewidth=1.8):
    sorted_lat = np.sort(latencies)
    cdf = np.arange(1, len(sorted_lat) + 1) / len(sorted_lat)
    ax.plot(sorted_lat, cdf, label=label, color=color, linestyle=linestyle,
            linewidth=linewidth)


def _add_percentile_lines(ax):
    for p in [0.50, 0.90, 0.95, 0.99]:
        ax.axhline(y=p, color="gray", linestyle=":", linewidth=0.7, alpha=0.6)
        ax.text(ax.get_xlim()[1] * 0.98, p, f"P{int(p*100)}",
                ha="right", va="bottom", fontsize=8, color="gray")


def _save(fig, plots_dir, name):
    fig.savefig(os.path.join(plots_dir, name), dpi=150)
    plt.close(fig)
    print(f"  -> {name}")


# ─────────────────────────────────────────────
# 1. Per-scenario CDF: with-HIL vs without-HIL
# ─────────────────────────────────────────────
def plot_cdf_per_scenario(modes: dict, plots_dir: str):
    all_scenarios = set()
    for scenarios in modes.values():
        all_scenarios.update(scenarios.keys())

    for scen in _ordered_scenarios(dict.fromkeys(all_scenarios)):
        fig, ax = plt.subplots(figsize=(10, 6))
        has_data = False

        for mode in ("without_hil", "with_hil"):
            scenarios = modes.get(mode, {})
            rows = scenarios.get(scen, [])
            if not rows:
                continue
            ls = MODE_STYLES[mode]["linestyle"]
            mlabel = MODE_LABELS[mode]

            for req_name, req_label, color in [
                ("/api/order", "Refrigerator", REQUEST_COLORS["/api/order"]),
                ("/api/restock", "Truck", REQUEST_COLORS["/api/restock"]),
            ]:
                lats = [r["response_time_ms"] for r in rows if r["name"] == req_name]
                if lats:
                    _plot_cdf(lats, f"{req_label} — {mlabel}", ax,
                              color=color, linestyle=ls)
                    has_data = True

        if not has_data:
            plt.close(fig)
            continue

        _add_percentile_lines(ax)
        ax.set_xlabel("Response Time (ms)", fontsize=12)
        ax.set_ylabel("Cumulative Probability", fontsize=12)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_title(f"CDF — {scen.replace('_', ' ').title()}  (With vs Without HIL)",
                      fontsize=14)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        _save(fig, plots_dir, f"cdf_{scen}.png")


# ─────────────────────────────────────────────
# 2. Cross-scenario CDF per request type
# ─────────────────────────────────────────────
def plot_cdf_across_scenarios(modes: dict, plots_dir: str):
    for req_name, label in [("/api/order", "Refrigerator"), ("/api/restock", "Truck")]:
        fig, ax = plt.subplots(figsize=(11, 6))
        has_data = False

        for mode in ("without_hil", "with_hil"):
            scenarios = modes.get(mode, {})
            ls = MODE_STYLES[mode]["linestyle"]
            mlabel = MODE_LABELS[mode]

            for scen in _ordered_scenarios(scenarios):
                rows = scenarios[scen]
                lats = [r["response_time_ms"] for r in rows if r["name"] == req_name]
                if not lats:
                    continue
                color = SCENARIO_COLORS.get(scen)
                _plot_cdf(lats,
                          f"{scen.replace('_', ' ').title()} — {mlabel}",
                          ax, color=color, linestyle=ls)
                has_data = True

        if not has_data:
            plt.close(fig)
            continue

        _add_percentile_lines(ax)
        ax.set_xlabel("Response Time (ms)", fontsize=12)
        ax.set_ylabel("Cumulative Probability", fontsize=12)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_title(f"CDF Comparison — {label} Requests  (With vs Without HIL)",
                      fontsize=14)
        ax.legend(fontsize=8, ncol=2)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        safe = req_name.replace("/", "_").strip("_")
        _save(fig, plots_dir, f"cdf_compare_{safe}.png")


# ─────────────────────────────────────────────
# 3. Grouped percentile bar charts
# ─────────────────────────────────────────────
def plot_percentile_bars(modes: dict, plots_dir: str):
    all_scenarios = set()
    for scenarios in modes.values():
        all_scenarios.update(scenarios.keys())
    ordered = _ordered_scenarios(dict.fromkeys(all_scenarios))

    for req_name, label in [("/api/order", "Refrigerator"), ("/api/restock", "Truck")]:
        scen_labels = []
        # {(mode, percentile): [values per scenario]}
        data: dict[tuple[str, int], list[float]] = {}
        for mode in ("without_hil", "with_hil"):
            for p in PERCENTILES:
                data[(mode, p)] = []

        for scen in ordered:
            has_any = False
            for mode in ("without_hil", "with_hil"):
                rows = modes.get(mode, {}).get(scen, [])
                lats = [r["response_time_ms"] for r in rows if r["name"] == req_name]
                pcts = compute_percentiles(lats) if lats else {p: 0.0 for p in PERCENTILES}
                for p in PERCENTILES:
                    data[(mode, p)].append(pcts[p])
                if lats:
                    has_any = True
            if has_any:
                scen_labels.append(scen.replace("_", " ").title())
            else:
                for mode in ("without_hil", "with_hil"):
                    for p in PERCENTILES:
                        data[(mode, p)].pop()

        if not scen_labels:
            continue

        n_scen = len(scen_labels)
        n_groups = len(PERCENTILES) * 2  # 2 modes
        width = 0.8 / n_groups
        x = np.arange(n_scen)

        fig, ax = plt.subplots(figsize=(max(12, n_scen * 2.5), 6))
        bar_colors_no_hil = ["#90CAF9", "#FFCC80", "#FFAB91", "#EF9A9A"]
        bar_colors_hil    = ["#1565C0", "#E65100", "#BF360C", "#B71C1C"]

        i = 0
        for mode, colors, hatch in [
            ("without_hil", bar_colors_no_hil, ""),
            ("with_hil",    bar_colors_hil,    "//"),
        ]:
            mlabel = MODE_LABELS[mode]
            for j, p in enumerate(PERCENTILES):
                offset = (i - n_groups / 2 + 0.5) * width
                vals = data[(mode, p)]
                bars = ax.bar(x + offset, vals, width,
                              label=f"P{p} {mlabel}",
                              color=colors[j], edgecolor="black",
                              linewidth=0.5, hatch=hatch)
                for bar, val in zip(bars, vals):
                    if val > 0:
                        ax.annotate(f"{val:.0f}",
                                    (bar.get_x() + bar.get_width() / 2, val),
                                    textcoords="offset points", xytext=(0, 4),
                                    ha="center", fontsize=6)
                i += 1

        ax.set_xticks(x)
        ax.set_xticklabels(scen_labels, fontsize=10)
        ax.set_ylabel("Response Time (ms)", fontsize=12)
        ax.set_title(f"Tail Latencies — {label} Requests  (With vs Without HIL)",
                      fontsize=14)
        ax.legend(fontsize=7, ncol=4, loc="upper left")
        ax.grid(True, axis="y", alpha=0.3)
        plt.tight_layout()

        safe = req_name.replace("/", "_").strip("_")
        _save(fig, plots_dir, f"percentile_bars_{safe}.png")


# ─────────────────────────────────────────────
# 4. HIL overhead delta chart
# ─────────────────────────────────────────────
def plot_hil_overhead(modes: dict, plots_dir: str):
    if "without_hil" not in modes or "with_hil" not in modes:
        return

    common = sorted(set(modes["without_hil"]) & set(modes["with_hil"]))
    if not common:
        return

    ordered = [s for s in SCENARIO_ORDER if s in common]
    ordered += [s for s in common if s not in ordered]

    for req_name, label in [("/api/order", "Refrigerator"), ("/api/restock", "Truck")]:
        scen_labels = []
        deltas = {p: [] for p in PERCENTILES}
        pct_increases = {p: [] for p in PERCENTILES}

        for scen in ordered:
            lats_no  = [r["response_time_ms"]
                        for r in modes["without_hil"].get(scen, [])
                        if r["name"] == req_name]
            lats_hil = [r["response_time_ms"]
                        for r in modes["with_hil"].get(scen, [])
                        if r["name"] == req_name]
            if not lats_no or not lats_hil:
                continue

            p_no  = compute_percentiles(lats_no)
            p_hil = compute_percentiles(lats_hil)

            scen_labels.append(scen.replace("_", " ").title())
            for p in PERCENTILES:
                d = p_hil[p] - p_no[p]
                deltas[p].append(d)
                pct_inc = (d / p_no[p] * 100) if p_no[p] > 0 else 0
                pct_increases[p].append(pct_inc)

        if not scen_labels:
            continue

        x = np.arange(len(scen_labels))
        width = 0.18
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

        bar_colors = ["#64B5F6", "#FFB74D", "#FF8A65", "#E57373"]

        # Absolute delta (ms)
        for i, p in enumerate(PERCENTILES):
            offset = (i - len(PERCENTILES) / 2 + 0.5) * width
            bars = ax1.bar(x + offset, deltas[p], width, label=f"P{p}",
                           color=bar_colors[i], edgecolor="black", linewidth=0.5)
            for bar, val in zip(bars, deltas[p]):
                ax1.annotate(f"{val:+.0f}",
                             (bar.get_x() + bar.get_width() / 2, val),
                             textcoords="offset points",
                             xytext=(0, 4 if val >= 0 else -12),
                             ha="center", fontsize=7)

        ax1.axhline(0, color="black", linewidth=0.8)
        ax1.set_xticks(x)
        ax1.set_xticklabels(scen_labels, fontsize=10)
        ax1.set_ylabel("Latency Delta (ms)", fontsize=12)
        ax1.set_title(f"HIL Overhead — {label} (Absolute)", fontsize=13)
        ax1.legend(fontsize=9)
        ax1.grid(True, axis="y", alpha=0.3)

        # Percentage increase
        for i, p in enumerate(PERCENTILES):
            offset = (i - len(PERCENTILES) / 2 + 0.5) * width
            bars = ax2.bar(x + offset, pct_increases[p], width, label=f"P{p}",
                           color=bar_colors[i], edgecolor="black", linewidth=0.5)
            for bar, val in zip(bars, pct_increases[p]):
                ax2.annotate(f"{val:+.1f}%",
                             (bar.get_x() + bar.get_width() / 2, val),
                             textcoords="offset points",
                             xytext=(0, 4 if val >= 0 else -12),
                             ha="center", fontsize=7)

        ax2.axhline(0, color="black", linewidth=0.8)
        ax2.set_xticks(x)
        ax2.set_xticklabels(scen_labels, fontsize=10)
        ax2.set_ylabel("Latency Increase (%)", fontsize=12)
        ax2.set_title(f"HIL Overhead — {label} (Percentage)", fontsize=13)
        ax2.legend(fontsize=9)
        ax2.grid(True, axis="y", alpha=0.3)

        plt.tight_layout()
        safe = req_name.replace("/", "_").strip("_")
        _save(fig, plots_dir, f"hil_overhead_{safe}.png")


# ─────────────────────────────────────────────
# 5. Combined CDF (all modes + scenarios)
# ─────────────────────────────────────────────
def plot_combined_cdf(modes: dict, plots_dir: str):
    fig, ax = plt.subplots(figsize=(12, 7))
    has_data = False

    linestyles_map = {
        "without_hil": "-",
        "with_hil":    "--",
    }

    for mode in ("without_hil", "with_hil"):
        scenarios = modes.get(mode, {})
        ls = linestyles_map[mode]
        mlabel = MODE_LABELS[mode]

        for scen in _ordered_scenarios(scenarios):
            rows = scenarios[scen]
            all_lats = [r["response_time_ms"] for r in rows]
            if all_lats:
                color = SCENARIO_COLORS.get(scen)
                _plot_cdf(all_lats,
                          f"{scen.replace('_', ' ').title()} — {mlabel}",
                          ax, color=color, linestyle=ls)
                has_data = True

    if has_data:
        _add_percentile_lines(ax)
        ax.set_xlabel("Response Time (ms)", fontsize=12)
        ax.set_ylabel("Cumulative Probability", fontsize=12)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_title("CDF Comparison — All Scenarios  (With vs Without HIL)", fontsize=14)
        ax.legend(fontsize=8, ncol=2)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        _save(fig, plots_dir, "cdf_combined_all.png")
    else:
        plt.close(fig)


# ─────────────────────────────────────────────
# Summary table
# ─────────────────────────────────────────────
def print_summary(modes: dict):
    print("\n" + "=" * 110)
    print("  PA3 MILESTONE 3 — TAIL LATENCY SUMMARY (ms)")
    print("=" * 110)
    header = (f"{'Scenario':<14} {'Mode':<14} {'Request':<16} "
              f"{'Count':>6} {'P50':>8} {'P90':>8} {'P95':>8} {'P99':>8}")
    print(header)
    print("-" * 110)

    all_scenarios = set()
    for scenarios in modes.values():
        all_scenarios.update(scenarios.keys())
    ordered = _ordered_scenarios(dict.fromkeys(all_scenarios))

    for scen in ordered:
        for mode in ("without_hil", "with_hil"):
            rows = modes.get(mode, {}).get(scen, [])
            if not rows:
                continue
            for req_name in ["/api/order", "/api/restock"]:
                lats = [r["response_time_ms"] for r in rows if r["name"] == req_name]
                if not lats:
                    continue
                pcts = compute_percentiles(lats)
                req_label = "Refrigerator" if req_name == "/api/order" else "Truck"
                print(f"  {scen:<12} {MODE_LABELS[mode]:<14} {req_label:<16} "
                      f"{len(lats):>6} {pcts[50]:>8.1f} {pcts[90]:>8.1f} "
                      f"{pcts[95]:>8.1f} {pcts[99]:>8.1f}")
        print()

    print("=" * 110)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="PA3 Milestone 3 — comparative tail-latency analysis")
    parser.add_argument(
        "--results-dir",
        default=os.path.join(os.path.dirname(__file__), "results"),
        help="Parent directory containing with_hil/ and without_hil/ subdirs")
    parser.add_argument(
        "--plots-dir",
        default=os.path.join(os.path.dirname(__file__), "plots"),
        help="Directory to save plot PNGs")
    args = parser.parse_args()

    if not os.path.isdir(args.results_dir):
        print(f"Error: results directory not found: {args.results_dir}")
        print("Run experiments first:")
        print("  ./experiments/PA3/run_pa3_experiments.sh --mode without_hil --host <URL>")
        print("  ./experiments/PA3/run_pa3_experiments.sh --mode with_hil    --host <URL>")
        sys.exit(1)

    os.makedirs(args.plots_dir, exist_ok=True)

    print(f"Scanning {args.results_dir} for experiment data...")
    modes = discover_modes(args.results_dir)

    if not modes:
        print("No raw_latencies.csv files found. Run experiments first.")
        sys.exit(1)

    for mode, scenarios in modes.items():
        n = sum(len(r) for r in scenarios.values())
        print(f"  {MODE_LABELS[mode]}: {len(scenarios)} scenario(s), {n} data points")

    print(f"\nGenerating plots to {args.plots_dir}/ ...")
    plot_cdf_per_scenario(modes, args.plots_dir)
    plot_cdf_across_scenarios(modes, args.plots_dir)
    plot_percentile_bars(modes, args.plots_dir)
    plot_hil_overhead(modes, args.plots_dir)
    plot_combined_cdf(modes, args.plots_dir)

    print_summary(modes)
    print(f"\nAll plots saved to {args.plots_dir}/")


if __name__ == "__main__":
    main()
