"""Plot monthly first-authorship newcomer counts from the saved analysis."""

import csv
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import StrMethodFormatter


ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT / "output" / "monthly_activity.csv").open(newline="") as source:
        monthly = list(csv.DictReader(source))
    counts = [int(row["newcomers"]) for row in monthly]
    labels = [datetime.strptime(row["month"], "%Y-%m").strftime("%b")
              + ("*" if int(row["partial_month"]) else "")
              + "\n" + row["month"][:4] for row in monthly]

    fig, ax = plt.subplots(figsize=(11.8, 5.2))
    fig.subplots_adjust(left=.08, right=.98, bottom=.27, top=.78)
    fig.suptitle("Newcomers by month of first authorship", fontsize=16,
                 fontweight="bold", y=.96)
    fig.text(.5, .89, "First recorded main-branch commit, PR opening or issue opening",
             ha="center", fontsize=11)
    bars = ax.bar(range(len(monthly)), counts, color="#247c70", width=.7)
    for bar, row in zip(bars, monthly):
        if int(row["partial_month"]):
            bar.set(facecolor="#c6dfda", edgecolor="#247c70", hatch="///")
    ax.bar_label(bars, labels=[f"{value:,}" for value in counts], padding=4, fontsize=10)
    ax.set(ylabel="Number of newcomers", xlabel="Month (UTC)",
           xticks=range(len(monthly)), xticklabels=labels,
           ylim=(0, max(counts) * 1.20))
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.grid(axis="y", alpha=.2)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(handles=[Patch(facecolor="#c6dfda", edgecolor="#247c70",
                             hatch="///", label="Partial month")],
              loc="upper left", frameon=False)
    fig.text(.025, .10, f"{sum(counts):,} newcomers in total, using the same filtered population "
             "and authorship definition as the text.", fontsize=9)
    fig.text(.025, .045, "* Partial months: 17–30 Sep 2025 (14 days); 1–17 Sep 2026 (17 days). "
             "Counts are not adjusted for days observed.", fontsize=9)

    destination = ROOT / "figures"
    destination.mkdir(exist_ok=True)
    for suffix in ("png", "svg"):
        fig.savefig(destination / f"newcomers_monthly.{suffix}", dpi=200)
    plt.close(fig)
    print("Monthly newcomers:", {row["month"]: count for row, count in zip(monthly, counts)})
    print("Total newcomers:", sum(counts))


if __name__ == "__main__":
    main()
