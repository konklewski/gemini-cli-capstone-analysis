"""Plot commit shares and the contributor absence factor from saved counts."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT / "output" / "people.csv").open(newline="") as source:
        authors = sorted(((row["login"], int(row["commit"]))
                          for row in csv.DictReader(source) if int(row["commit"]) > 0),
                         key=lambda item: (-item[1], item[0].casefold()))
    total = sum(count for _, count in authors)
    if not total:
        raise ValueError("No human commits to plot")
    cumulative = 0
    for factor, (_, count) in enumerate(authors, 1):
        cumulative += count
        if cumulative * 2 >= total:
            break

    palette = plt.get_cmap("tab20").colors
    colors = [palette[i % len(palette)] for i in range(factor)]
    colors.append("#cbd3d8")
    other_count = total - cumulative
    fig, ax = plt.subplots(figsize=(12, 7.3))
    fig.subplots_adjust(left=.025, right=.62, bottom=.15, top=.83)
    fig.suptitle("Commit contributions by author", fontsize=17, fontweight="bold", y=.96)
    fig.text(.5, .905, "Human main-branch commits · 17 Sep 2025–17 Sep 2026 (UTC)",
             ha="center", fontsize=11)
    wedges, _ = ax.pie([count for _, count in authors[:factor]] + [other_count], colors=colors,
                       startangle=90, counterclock=False,
                       wedgeprops={"width": .29, "edgecolor": "white", "linewidth": .8})
    ax.text(0, .23, f"{factor} authors", ha="center", fontsize=22, fontweight="bold")
    ax.text(0, .025, f"{100 * cumulative / total:.2f}%", ha="center", fontsize=26,
            color="#185b51", fontweight="bold")
    ax.text(0, -.15, "of human commits", ha="center", fontsize=12)
    ax.text(0, -.31, f"{cumulative:,} of {total:,}", ha="center", fontsize=11,
            color="#52616b")
    labels = [f"{login}  {count:,} ({100 * count / total:.2f}%)"
              for login, count in authors[:factor]]
    labels.append(f"Other {len(authors) - factor} authors  {other_count:,} "
                  f"({100 * other_count / total:.2f}%)")
    fig.legend(wedges, labels, title="Author · commits (share)", loc="center left",
               bbox_to_anchor=(.62, .49), frameon=False, fontsize=10,
               title_fontsize=11, labelspacing=.85, handlelength=1.15)
    fig.text(.04, .095, f"The top {factor} authors are shown individually; "
             f"the remaining {len(authors) - factor} are combined into one grey segment.", fontsize=10)
    fig.text(.04, .055, f"Contributor Absence Factor = {factor}: the smallest group reaching "
             "at least 50% of human commits. Confirmed aliases are merged.", fontsize=10)

    destination = ROOT / "figures"
    destination.mkdir(exist_ok=True)
    for suffix in ("png", "svg"):
        fig.savefig(destination / f"commit_concentration.{suffix}", dpi=200)
    plt.close(fig)
    print(f"{len(authors)} authors; {total} human commits; "
          f"CAF {factor}; top group {cumulative} commits ({100 * cumulative / total:.2f}%).")


if __name__ == "__main__":
    main()
