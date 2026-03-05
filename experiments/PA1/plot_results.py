"""
Plot latency results from load_test.py.

Reads experiments/results.csv and generates 3 graphs saved to experiments/.

Usage:
    python3 -m experiments.plot_results
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")  # non-interactive backend (works on headless VMs)
import matplotlib.pyplot as plt


def load_csv(csv_path: str) -> list[dict]:
    with open(csv_path, "r") as f:
        return list(csv.DictReader(f))


def plot_experiment_1(rows: list[dict], out_dir: str):
    """Experiment 1: Latency vs order size."""
    data = [(int(r["num_items"]), float(r["latency_ms"]))
            for r in rows if r["experiment"] == "order_size"]
    if not data:
        print("  No data for experiment 1, skipping.")
        return

    sizes, latencies = zip(*data)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(range(len(sizes)), latencies, color="#4C72B0", edgecolor="black")
    ax.set_xticks(range(len(sizes)))
    ax.set_xticklabels([str(s) for s in sizes])
    ax.set_xlabel("Number of Items in Order", fontsize=12)
    ax.set_ylabel("End-to-End Latency (ms)", fontsize=12)
    ax.set_title("Experiment 1: Latency vs Order Size", fontsize=14)

    for i, (s, l) in enumerate(zip(sizes, latencies)):
        ax.annotate(f"{l:.0f}ms", (i, l), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=9)

    plt.tight_layout()
    path = os.path.join(out_dir, "exp1_order_size.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_experiment_2(rows: list[dict], out_dir: str):
    """Experiment 2: Latency over consecutive orders."""
    data = [(int(r["label"]), float(r["latency_ms"]))
            for r in rows if r["experiment"] == "consecutive"]
    if not data:
        print("  No data for experiment 2, skipping.")
        return

    order_nums, latencies = zip(*data)
    avg = sum(latencies) / len(latencies)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(order_nums, latencies, marker="o", markersize=5,
            linewidth=1.5, color="#4C72B0", label="Latency")
    ax.axhline(y=avg, color="#DD8452", linestyle="--", linewidth=1.5,
               label=f"Avg: {avg:.0f}ms")
    ax.set_xlabel("Order Number", fontsize=12)
    ax.set_ylabel("End-to-End Latency (ms)", fontsize=12)
    ax.set_title("Experiment 2: Consecutive Orders Under Load", fontsize=14)
    ax.legend(fontsize=10)

    plt.tight_layout()
    path = os.path.join(out_dir, "exp2_consecutive.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved {path}")


def plot_experiment_3(rows: list[dict], out_dir: str):
    """Experiment 3: Orders vs Restocks comparison."""
    order_latencies = [float(r["latency_ms"]) for r in rows
                       if r["experiment"] == "order_vs_restock"
                       and r["type"] == "GROCERY_ORDER"]
    restock_latencies = [float(r["latency_ms"]) for r in rows
                         if r["experiment"] == "order_vs_restock"
                         and r["type"] == "RESTOCK_ORDER"]

    if not order_latencies or not restock_latencies:
        print("  No data for experiment 3, skipping.")
        return

    avg_order = sum(order_latencies) / len(order_latencies)
    avg_restock = sum(restock_latencies) / len(restock_latencies)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5),
                                    gridspec_kw={"width_ratios": [1, 2]})

    # Bar chart: average comparison
    bars = ax1.bar(["Grocery\nOrder", "Restock\nOrder"],
                   [avg_order, avg_restock],
                   color=["#4C72B0", "#55A868"], edgecolor="black")
    ax1.set_ylabel("Avg Latency (ms)", fontsize=12)
    ax1.set_title("Average Latency", fontsize=13)
    for bar, val in zip(bars, [avg_order, avg_restock]):
        ax1.annotate(f"{val:.0f}ms", (bar.get_x() + bar.get_width() / 2, val),
                     textcoords="offset points", xytext=(0, 8),
                     ha="center", fontsize=10)

    # Line chart: individual measurements
    ax2.plot(range(1, len(order_latencies) + 1), order_latencies,
             marker="o", markersize=5, linewidth=1.5, color="#4C72B0",
             label=f"Grocery Order (avg {avg_order:.0f}ms)")
    ax2.plot(range(1, len(restock_latencies) + 1), restock_latencies,
             marker="s", markersize=5, linewidth=1.5, color="#55A868",
             label=f"Restock Order (avg {avg_restock:.0f}ms)")
    ax2.set_xlabel("Request Number", fontsize=12)
    ax2.set_ylabel("Latency (ms)", fontsize=12)
    ax2.set_title("Individual Measurements", fontsize=13)
    ax2.legend(fontsize=10)

    fig.suptitle("Experiment 3: Grocery Orders vs Restocks", fontsize=14, y=1.02)
    plt.tight_layout()
    path = os.path.join(out_dir, "exp3_order_vs_restock.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {path}")


def main():
    out_dir = os.path.dirname(__file__)
    csv_path = os.path.join(out_dir, "results.csv")

    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        print("Run first:  python3 -m experiments.load_test")
        return

    print(f"Reading {csv_path}...")
    rows = load_csv(csv_path)
    print(f"Loaded {len(rows)} data points.\n")

    print("Generating plots...")
    plot_experiment_1(rows, out_dir)
    plot_experiment_2(rows, out_dir)
    plot_experiment_3(rows, out_dir)
    print("\nDone! Check the experiments/ folder for PNG files.")


if __name__ == "__main__":
    main()
