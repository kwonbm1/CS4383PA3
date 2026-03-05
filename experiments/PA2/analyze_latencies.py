"""
Tail-latency analysis and CDF plotting for Locust experiment results.

Reads per-request raw latency CSVs produced by the custom event listener
in locustfile.py, then computes P50/P90/P95/P99 and generates CDF plots.

Usage:
    python3 -m experiments.analyze_latencies
    python3 -m experiments.analyze_latencies --results-dir experiments/results
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
COLORS = {
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
    """Load per-request latency rows from a raw_latencies.csv file."""
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Skip setup requests
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


def discover_scenarios(results_dir: str) -> dict[str, list[dict]]:
    """Walk results_dir and return {scenario_name: [rows]}."""
    scenarios = {}

    # Pattern 1: results/<scenario>/<scenario>_raw_latencies.csv
    for subdir in sorted(os.listdir(results_dir)):
        path = os.path.join(results_dir, subdir)
        if not os.path.isdir(path):
            continue
        candidates = glob.glob(os.path.join(path, "*_raw_latencies.csv"))
        if candidates:
            rows = load_raw_latencies(candidates[0])
            if rows:
                scenarios[subdir] = rows

    # Pattern 2: results/raw_latencies.csv (single run)
    single = os.path.join(results_dir, "raw_latencies.csv")
    if os.path.exists(single) and not scenarios:
        rows = load_raw_latencies(single)
        if rows:
            scenarios["single_run"] = rows

    return scenarios


# ─────────────────────────────────────────────
# Percentile computation
# ─────────────────────────────────────────────
def compute_percentiles(latencies: list[float]) -> dict[int, float]:
    """Compute P50, P90, P95, P99."""
    arr = np.array(latencies)
    return {p: float(np.percentile(arr, p)) for p in PERCENTILES}


# ─────────────────────────────────────────────
# Plotting helpers
# ─────────────────────────────────────────────
def plot_cdf(latencies: list[float], label: str, ax, color=None, linestyle="-"):
    """Plot a CDF curve on the given axes."""
    sorted_lat = np.sort(latencies)
    cdf = np.arange(1, len(sorted_lat) + 1) / len(sorted_lat)
    ax.plot(sorted_lat, cdf, label=label, color=color, linestyle=linestyle,
            linewidth=1.8)


def add_percentile_lines(ax, ymax=1.0):
    """Add horizontal dashed lines for key percentiles."""
    for p in [0.50, 0.90, 0.95, 0.99]:
        ax.axhline(y=p, color="gray", linestyle=":", linewidth=0.7, alpha=0.6)
        ax.text(ax.get_xlim()[1] * 0.98, p, f"P{int(p*100)}",
                ha="right", va="bottom", fontsize=8, color="gray")


# ─────────────────────────────────────────────
# Plot generators
# ─────────────────────────────────────────────
def plot_cdf_per_scenario(scenarios: dict, plots_dir: str):
    """CDF plot per scenario showing /api/order vs /api/restock."""
    for name, rows in scenarios.items():
        order_lats = [r["response_time_ms"] for r in rows if r["name"] == "/api/order"]
        restock_lats = [r["response_time_ms"] for r in rows if r["name"] == "/api/restock"]

        if not order_lats and not restock_lats:
            continue

        fig, ax = plt.subplots(figsize=(10, 6))

        if order_lats:
            plot_cdf(order_lats, "Refrigerator (/api/order)", ax,
                     color=REQUEST_COLORS.get("/api/order"))
        if restock_lats:
            plot_cdf(restock_lats, "Truck (/api/restock)", ax,
                     color=REQUEST_COLORS.get("/api/restock"))

        add_percentile_lines(ax)
        ax.set_xlabel("Response Time (ms)", fontsize=12)
        ax.set_ylabel("Cumulative Probability", fontsize=12)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_title(f"CDF — {name.replace('_', ' ').title()}", fontsize=14)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(os.path.join(plots_dir, f"cdf_{name}.png"), dpi=150)
        plt.close(fig)
        print(f"  ✓ cdf_{name}.png")


def plot_cdf_across_scenarios(scenarios: dict, plots_dir: str):
    """CDF comparison across all scenarios for each request type."""
    for req_name, label in [("/api/order", "Refrigerator"), ("/api/restock", "Truck")]:
        fig, ax = plt.subplots(figsize=(10, 6))
        has_data = False

        ordered = [s for s in SCENARIO_ORDER if s in scenarios]
        ordered += [s for s in scenarios if s not in ordered]

        for scen_name in ordered:
            rows = scenarios[scen_name]
            lats = [r["response_time_ms"] for r in rows if r["name"] == req_name]
            if lats:
                color = COLORS.get(scen_name, None)
                plot_cdf(lats, scen_name.replace("_", " ").title(), ax, color=color)
                has_data = True

        if not has_data:
            plt.close(fig)
            continue

        add_percentile_lines(ax)
        ax.set_xlabel("Response Time (ms)", fontsize=12)
        ax.set_ylabel("Cumulative Probability", fontsize=12)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_title(f"CDF Comparison — {label} Requests", fontsize=14)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        safe = req_name.replace("/", "_").strip("_")
        fig.savefig(os.path.join(plots_dir, f"cdf_compare_{safe}.png"), dpi=150)
        plt.close(fig)
        print(f"  ✓ cdf_compare_{safe}.png")


def plot_percentile_bars(scenarios: dict, plots_dir: str):
    """Grouped bar chart comparing P50/P90/P95/P99 across scenarios."""
    ordered = [s for s in SCENARIO_ORDER if s in scenarios]
    ordered += [s for s in scenarios if s not in ordered]

    for req_name, label in [("/api/order", "Refrigerator"), ("/api/restock", "Truck")]:
        scen_names = []
        pct_data = {p: [] for p in PERCENTILES}

        for scen_name in ordered:
            rows = scenarios[scen_name]
            lats = [r["response_time_ms"] for r in rows if r["name"] == req_name]
            if not lats:
                continue
            pcts = compute_percentiles(lats)
            scen_names.append(scen_name.replace("_", " ").title())
            for p in PERCENTILES:
                pct_data[p].append(pcts[p])

        if not scen_names:
            continue

        x = np.arange(len(scen_names))
        width = 0.18
        fig, ax = plt.subplots(figsize=(12, 6))

        bar_colors = ["#64B5F6", "#FFB74D", "#FF8A65", "#E57373"]
        for i, p in enumerate(PERCENTILES):
            offset = (i - len(PERCENTILES) / 2 + 0.5) * width
            bars = ax.bar(x + offset, pct_data[p], width, label=f"P{p}",
                          color=bar_colors[i], edgecolor="black", linewidth=0.5)
            for bar, val in zip(bars, pct_data[p]):
                ax.annotate(f"{val:.0f}", (bar.get_x() + bar.get_width() / 2, val),
                            textcoords="offset points", xytext=(0, 4),
                            ha="center", fontsize=7)

        ax.set_xticks(x)
        ax.set_xticklabels(scen_names, fontsize=10)
        ax.set_ylabel("Response Time (ms)", fontsize=12)
        ax.set_title(f"Tail Latencies — {label} Requests", fontsize=14)
        ax.legend(fontsize=10)
        ax.grid(True, axis="y", alpha=0.3)

        plt.tight_layout()
        safe = req_name.replace("/", "_").strip("_")
        fig.savefig(os.path.join(plots_dir, f"percentile_bars_{safe}.png"), dpi=150)
        plt.close(fig)
        print(f"  ✓ percentile_bars_{safe}.png")


def plot_combined_cdf(scenarios: dict, plots_dir: str):
    """Single CDF plot with all scenarios, all request types overlaid."""
    fig, ax = plt.subplots(figsize=(12, 7))
    has_data = False

    ordered = [s for s in SCENARIO_ORDER if s in scenarios]
    ordered += [s for s in scenarios if s not in ordered]

    linestyles = ["-", "--", "-.", ":", (0, (3, 1, 1, 1))]

    for i, scen_name in enumerate(ordered):
        rows = scenarios[scen_name]
        all_lats = [r["response_time_ms"] for r in rows]
        if all_lats:
            color = COLORS.get(scen_name, None)
            ls = linestyles[i % len(linestyles)]
            plot_cdf(all_lats, scen_name.replace("_", " ").title(), ax,
                     color=color, linestyle=ls)
            has_data = True

    if has_data:
        add_percentile_lines(ax)
        ax.set_xlabel("Response Time (ms)", fontsize=12)
        ax.set_ylabel("Cumulative Probability", fontsize=12)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_title("CDF Comparison — All Scenarios (Combined)", fontsize=14)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(os.path.join(plots_dir, "cdf_combined_all.png"), dpi=150)
        plt.close(fig)
        print(f"  ✓ cdf_combined_all.png")
    else:
        plt.close(fig)


# ─────────────────────────────────────────────
# Summary table
# ─────────────────────────────────────────────
def print_summary(scenarios: dict):
    """Print a formatted summary table to stdout."""
    print("\n" + "=" * 90)
    print("  TAIL LATENCY SUMMARY (ms)")
    print("=" * 90)
    header = f"{'Scenario':<16} {'Request':<18} {'Count':>6} {'P50':>8} {'P90':>8} {'P95':>8} {'P99':>8}"
    print(header)
    print("-" * 90)

    ordered = [s for s in SCENARIO_ORDER if s in scenarios]
    ordered += [s for s in scenarios if s not in ordered]

    for scen_name in ordered:
        rows = scenarios[scen_name]
        for req_name in ["/api/order", "/api/restock"]:
            lats = [r["response_time_ms"] for r in rows if r["name"] == req_name]
            if not lats:
                continue
            pcts = compute_percentiles(lats)
            label = "Refrigerator" if req_name == "/api/order" else "Truck"
            print(f"  {scen_name:<14} {label:<18} {len(lats):>6} "
                  f"{pcts[50]:>8.1f} {pcts[90]:>8.1f} {pcts[95]:>8.1f} {pcts[99]:>8.1f}")
        print()

    print("=" * 90)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Analyze Locust tail latencies")
    parser.add_argument("--results-dir",
                        default=os.path.join(os.path.dirname(__file__), "results"),
                        help="Directory containing scenario subdirectories with raw_latencies.csv")
    parser.add_argument("--plots-dir",
                        default=os.path.join(os.path.dirname(__file__), "plots"),
                        help="Directory to save plot PNGs")
    args = parser.parse_args()

    if not os.path.isdir(args.results_dir):
        print(f"Error: results directory not found: {args.results_dir}")
        print("Run experiments first:  ./experiments/run_locust_experiments.sh")
        sys.exit(1)

    os.makedirs(args.plots_dir, exist_ok=True)

    print(f"Scanning {args.results_dir} for experiment data...")
    scenarios = discover_scenarios(args.results_dir)

    if not scenarios:
        print("No raw_latencies.csv files found. Run experiments first.")
        sys.exit(1)

    print(f"Found {len(scenarios)} scenario(s): {', '.join(scenarios.keys())}")
    total_rows = sum(len(r) for r in scenarios.values())
    print(f"Total data points: {total_rows}\n")

    print("Generating plots...")
    plot_cdf_per_scenario(scenarios, args.plots_dir)
    plot_cdf_across_scenarios(scenarios, args.plots_dir)
    plot_percentile_bars(scenarios, args.plots_dir)
    plot_combined_cdf(scenarios, args.plots_dir)

    print_summary(scenarios)

    print(f"\nAll plots saved to {args.plots_dir}/")


if __name__ == "__main__":
    main()
