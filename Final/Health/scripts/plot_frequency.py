"""Plot exact active-month counts from the saved contributor classifications."""

import csv
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import StrMethodFormatter


ROOT = Path(__file__).resolve().parents[1]


def plot(counts, first_month=1):
    months = list(range(first_month, 14))
    colors = {1: "#7b8794", **{m: "#8bb4d4" for m in range(2, 6)},
              **{m: "#247c70" for m in range(6, 14)}}
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    fig.subplots_adjust(left=.075, right=.985, bottom=.25, top=.79, wspace=.23)
    fig.suptitle("Distribution of participation frequency", fontsize=17,
                 fontweight="bold", y=.96)
    fig.text(.5, .895, "Each bar counts participants active in exactly that many months.",
             ha="center", fontsize=11)

    overview = "All participants" if first_month == 1 else "Participants active in 2–13 months"
    for ax, shown, title in zip(axes, [months, list(range(4, 14))],
                               [overview, "Detail: 4–13 active months"]):
        values = [counts[m] for m in shown]
        bars = ax.bar(shown, values, color=[colors[m] for m in shown], width=.7)
        ax.bar_label(bars, labels=[f"{v:,}" for v in values], padding=4, fontsize=9)
        ax.set(title=title, xlabel="Number of active calendar months",
               ylabel="Number of participants",
               ylim=(0, max(values) * 1.20), xticks=shown)
        ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.axvline(5.5, color="#247c70", linestyle="--", linewidth=1.2)
        ax.text(5.65, max(values) * 1.06, "Frequent: 6+ months", fontsize=9,
                color="#185b51")

    legend = [Patch(color=colors[2], label="Occasional: 2–5 months"),
              Patch(color=colors[6], label="Frequent: 6+ months")]
    if first_month == 1:
        legend.insert(0, Patch(color=colors[1], label="Single-month"))
    axes[0].legend(handles=legend,
                   loc="upper right", bbox_to_anchor=(1, .86), frameon=False, fontsize=9)
    population = (f"{sum(counts.values()):,} filtered participants" if first_month == 1 else
                  f"{sum(counts[m] for m in months):,} participants shown; "
                  f"{counts[1]:,} single-month participants omitted")
    fig.text(.025, .12, population + " · 17 Sep 2025–17 Sep 2026 (UTC).", fontsize=9)
    fig.text(.025, .08, "Both panels use linear scales; the right panel has a smaller y-axis range.", fontsize=9)
    fig.text(.025, .04, "Active month = at least one included action; months need not be consecutive. "
             "The 13 calendar bins include two partial Septembers.", fontsize=9)

    destination = ROOT / "figures"
    destination.mkdir(exist_ok=True)
    name = "frequency_distribution" + ("_without_single_month" if first_month == 2 else "")
    for suffix in ("png", "pdf"):
        fig.savefig(destination / f"{name}.{suffix}", dpi=200)
    plt.close(fig)


def main():
    with (ROOT / "output" / "people.csv").open(newline="") as source:
        counts = Counter(int(row["months_active"]) for row in csv.DictReader(source))
    plot(counts)
    plot(counts, first_month=2)
    print("Exact-month counts:", dict(sorted(counts.items())))
    print("Frequent participants (6+ months):", sum(v for m, v in counts.items() if m >= 6))


if __name__ == "__main__":
    main()
