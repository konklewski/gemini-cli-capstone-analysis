#!/usr/bin/env python3
"""Create transparent contributor rankings and sensitivity-analysis tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import END_DATE, START_DATE  # noqa: E402
from scripts.common import write_csv  # noqa: E402


DEFAULT_INPUT = PROJECT_ROOT / "output" / "contributor_activity.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
METRICS = {
    "commits_authored": "commit",
    "pull_requests_opened": "pull_request",
    "issues_opened": "issue",
}
SCENARIOS = {
    "equal_weight": (1 / 3, 1 / 3, 1 / 3),
    "commit_emphasis": (0.50, 0.25, 0.25),
    "pull_request_emphasis": (0.25, 0.50, 0.25),
    "issue_emphasis": (0.25, 0.25, 0.50),
}


def validate_activity_table(frame: pd.DataFrame, source: Path) -> pd.DataFrame:
    """Validate counts and identities before computing any ranking."""

    required = {"github_login", "bot_classification", *METRICS}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{source} is missing columns: {', '.join(missing)}")
    if frame["github_login"].isna().any() or frame["github_login"].duplicated().any():
        raise ValueError(f"{source} must contain one unique, non-null github_login per row")

    result = frame.copy()
    for metric in METRICS:
        numeric = pd.to_numeric(result[metric], errors="coerce")
        invalid = numeric.isna() | numeric.lt(0) | numeric.mod(1).ne(0)
        if invalid.any():
            examples = result.loc[invalid, ["github_login", metric]].head(5)
            raise ValueError(
                f"{source} contains invalid non-negative integer values for {metric}: "
                f"{examples.to_dict(orient='records')}"
            )
        result[metric] = numeric.astype(int)
    return result


def percentile_position(values: pd.Series) -> pd.Series:
    """Return a 0–1 relative position based on the share strictly below.

    This is equivalent to SQL ``PERCENT_RANK`` with ascending, minimum ranks:
    ``(rank - 1) / (N - 1)``. It gives all minimum-count contributors zero,
    which is important for the many zero counts in these activity dimensions.
    Tied values receive the same score.
    """

    if len(values) == 1:
        return pd.Series(1.0, index=values.index)
    return (values.rank(method="min", ascending=True) - 1) / (len(values) - 1)


def add_rankings(frame: pd.DataFrame) -> pd.DataFrame:
    """Add category percentiles/ranks, combined scores, and scenario ranks."""

    ranked = frame.copy()
    percentile_columns = []
    rank_columns = []
    for metric, short_name in METRICS.items():
        percentile_column = f"{short_name}_percentile"
        rank_column = f"{short_name}_rank"
        ranked[percentile_column] = percentile_position(ranked[metric])
        ranked[rank_column] = ranked[metric].rank(
            method="min", ascending=False
        ).astype(int)
        percentile_columns.append(percentile_column)
        rank_columns.append(rank_column)

    ranked["mean_activity_rank"] = ranked[rank_columns].mean(axis=1)
    ranked["mean_rank_overall_position"] = ranked["mean_activity_rank"].rank(
        method="min", ascending=True
    ).astype(int)

    for scenario, weights in SCENARIOS.items():
        score_column = f"{scenario}_score"
        rank_column = f"{scenario}_rank"
        ranked[score_column] = sum(
            weight * ranked[column]
            for weight, column in zip(weights, percentile_columns, strict=True)
        )
        ranked[rank_column] = ranked[score_column].rank(
            method="min", ascending=False
        ).astype(int)
    return ranked


def top_percentile(ranked: pd.DataFrame, count: int = 10) -> pd.DataFrame:
    """Select a deterministic top group for the equal-percentile method."""

    return (
        ranked.sort_values(
            ["equal_weight_score", "mean_activity_rank", "github_login"],
            ascending=[False, True, True],
            kind="stable",
        )
        .head(count)
        .reset_index(drop=True)
    )


def top_mean_rank(ranked: pd.DataFrame, count: int = 10) -> pd.DataFrame:
    """Select the lowest mean category ranks, with documented tie-breakers."""

    return (
        ranked.sort_values(
            ["mean_activity_rank", "equal_weight_score", "github_login"],
            ascending=[True, False, True],
            kind="stable",
        )
        .head(count)
        .reset_index(drop=True)
    )


def sensitivity_tables(
    ranked: pd.DataFrame, count: int = 10
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return scenario top-10 rows and overlap with the equal-weight baseline."""

    scenario_tables = []
    top_sets: dict[str, set[str]] = {}
    for scenario, weights in SCENARIOS.items():
        score = f"{scenario}_score"
        selected = (
            ranked.sort_values(
                [score, "mean_activity_rank", "github_login"],
                ascending=[False, True, True],
                kind="stable",
            )
            .head(count)
            .copy()
        )
        selected.insert(0, "scenario_position", range(1, len(selected) + 1))
        selected.insert(0, "scenario", scenario)
        selected["scenario_score"] = selected[score]
        selected["commit_weight"] = weights[0]
        selected["pull_request_weight"] = weights[1]
        selected["issue_weight"] = weights[2]
        scenario_tables.append(
            selected[
                [
                    "scenario",
                    "scenario_position",
                    "github_login",
                    "scenario_score",
                    "commit_weight",
                    "pull_request_weight",
                    "issue_weight",
                    *METRICS,
                    "bot_classification",
                ]
            ]
        )
        top_sets[scenario] = set(selected["github_login"])

    baseline = top_sets["equal_weight"]
    summaries = []
    for scenario, weights in SCENARIOS.items():
        selected = top_sets[scenario]
        intersection = len(baseline & selected)
        union = len(baseline | selected)
        summaries.append(
            {
                "scenario": scenario,
                "commit_weight": weights[0],
                "pull_request_weight": weights[1],
                "issue_weight": weights[2],
                "top_10_overlap_with_equal_weight": intersection,
                "top_10_jaccard_with_equal_weight": intersection / union,
                "top_10_logins": "|".join(
                    scenario_tables[list(SCENARIOS).index(scenario)]["github_login"]
                ),
            }
        )
    return pd.concat(scenario_tables, ignore_index=True), pd.DataFrame(summaries)


def comparison_table(
    ranked: pd.DataFrame, percentile_top: pd.DataFrame, mean_top: pd.DataFrame
) -> pd.DataFrame:
    """Compare membership in the two primary requested top-10 methods."""

    logins = set(percentile_top["github_login"]) | set(mean_top["github_login"])
    comparison = ranked.loc[ranked["github_login"].isin(logins)].copy()
    comparison["in_percentile_top_10"] = comparison["github_login"].isin(
        percentile_top["github_login"]
    )
    comparison["in_mean_rank_top_10"] = comparison["github_login"].isin(
        mean_top["github_login"]
    )
    return comparison.sort_values(
        ["in_percentile_top_10", "equal_weight_rank", "mean_activity_rank"],
        ascending=[False, True, True],
        kind="stable",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--include-bots",
        action="store_true",
        help="Include confirmed bots in ranking population (default: exclude bots)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        activity = validate_activity_table(pd.read_csv(args.input), args.input)
        excluded_bots = 0
        if not args.include_bots:
            confirmed_bot = activity["bot_classification"].eq("bot")
            excluded_bots = int(confirmed_bot.sum())
            activity = activity.loc[~confirmed_bot].copy()
        if activity.empty:
            raise ValueError("No ranking-eligible contributors remain")

        ranked = add_rankings(activity)
        percentile_top = top_percentile(ranked)
        mean_top = top_mean_rank(ranked)
        scenario_top, scenario_summary = sensitivity_tables(ranked)
        comparison = comparison_table(ranked, percentile_top, mean_top)

        args.output_dir.mkdir(parents=True, exist_ok=True)
        outputs = {
            "contributor_rankings.csv": ranked.sort_values(
                ["equal_weight_rank", "github_login"], kind="stable"
            ),
            "top_10_percentile_activity.csv": percentile_top,
            "top_10_mean_rank.csv": mean_top,
            "top_10_method_comparison.csv": comparison,
            "top_10_sensitivity.csv": scenario_top,
            "ranking_sensitivity_summary.csv": scenario_summary,
        }
        for filename, frame in outputs.items():
            write_csv(frame, args.output_dir / filename)
    except (OSError, ValueError, pd.errors.ParserError) as error:
        raise SystemExit(f"Error: {error}") from error

    print(
        f"Ranked {len(ranked)} contributors for {START_DATE} to {END_DATE}; "
        f"excluded {excluded_bots} confirmed bots"
    )
    for filename, frame in outputs.items():
        print(f"Wrote {len(frame)} rows to {args.output_dir / filename}")


if __name__ == "__main__":
    main()
