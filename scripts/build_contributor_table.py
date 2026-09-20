#!/usr/bin/env python3
"""Build per-login activity counts while keeping each metric separate."""

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


DEFAULT_COMMITS = PROJECT_ROOT / "data" / "processed" / "commits.csv"
DEFAULT_PULL_REQUESTS = PROJECT_ROOT / "data" / "processed" / "pull_requests.csv"
DEFAULT_ISSUES = PROJECT_ROOT / "data" / "processed" / "issues.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "contributor_activity.csv"
SORT_COLUMNS = (
    "github_login",
    "commits_authored",
    "pull_requests_opened",
    "issues_opened",
    "first_observed_activity",
    "last_observed_activity",
)


def read_activity(
    path: Path,
    *,
    login_column: str,
    date_column: str,
    id_column: str,
    metric: str,
) -> tuple[pd.DataFrame, int]:
    """Read and validate one processed activity table."""

    if not path.is_file():
        raise FileNotFoundError(
            f"Missing processed input: {path}. Run its processing script first."
        )
    frame = pd.read_csv(path)
    required = {login_column, date_column, id_column, "bot_classification"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(missing)}")
    duplicate = frame[id_column].notna() & frame[id_column].duplicated(keep=False)
    if duplicate.any():
        examples = frame.loc[duplicate, id_column].head(5).tolist()
        raise ValueError(f"Duplicate {id_column} values in {path}: {examples}")

    unmatched = int(frame[login_column].isna().sum())
    matched = frame.loc[frame[login_column].notna()].copy()
    matched[login_column] = matched[login_column].astype(str).str.strip()
    empty = matched[login_column].eq("")
    unmatched += int(empty.sum())
    matched = matched.loc[~empty]
    matched[date_column] = pd.to_datetime(matched[date_column], utc=True, errors="raise")
    matched = matched.rename(
        columns={login_column: "github_login", date_column: "activity_at"}
    )
    matched["metric"] = metric
    return matched[["github_login", "activity_at", "metric", "bot_classification"]], unmatched


def aggregate_bot(values: pd.Series) -> str:
    """Use conservative precedence when records disagree."""

    normalized = set(values.dropna().astype(str).str.casefold())
    if "bot" in normalized:
        return "bot"
    if "uncertain" in normalized or not normalized:
        return "uncertain"
    return "human"


def build_table(commits: Path, pulls: Path, issues: Path) -> tuple[pd.DataFrame, int]:
    """Combine activities by exact GitHub login; never guess identities."""

    specifications = (
        (commits, "github_login", "author_date", "commit_sha", "commits_authored"),
        (pulls, "author_login", "created_at", "pr_number", "pull_requests_opened"),
        (issues, "author_login", "created_at", "issue_number", "issues_opened"),
    )
    activities = []
    unmatched_total = 0
    for path, login, date, identifier, metric in specifications:
        frame, unmatched = read_activity(
            path,
            login_column=login,
            date_column=date,
            id_column=identifier,
            metric=metric,
        )
        activities.append(frame)
        unmatched_total += unmatched

    combined = pd.concat(activities, ignore_index=True)
    if combined.empty:
        raise ValueError(
            f"No matched contributor activities in window {START_DATE} to {END_DATE}"
        )
    counts = (
        combined.groupby(["github_login", "metric"], sort=True)
        .size()
        .unstack(fill_value=0)
        .reindex(
            columns=["commits_authored", "pull_requests_opened", "issues_opened"],
            fill_value=0,
        )
    )
    dates = combined.groupby("github_login")["activity_at"].agg(
        first_observed_activity="min", last_observed_activity="max"
    )
    bots = combined.groupby("github_login")["bot_classification"].agg(aggregate_bot)
    result = counts.join(dates).join(bots.rename("bot_classification")).reset_index()
    result["total_observed_activities"] = result[
        ["commits_authored", "pull_requests_opened", "issues_opened"]
    ].sum(axis=1)
    result["suspected_bot"] = result["bot_classification"].map(
        {"bot": True, "human": False, "uncertain": pd.NA}
    )
    for column in ("first_observed_activity", "last_observed_activity"):
        result[column] = result[column].map(
            lambda value: value.isoformat().replace("+00:00", "Z")
        )
    return result[
        [
            "github_login",
            "commits_authored",
            "pull_requests_opened",
            "issues_opened",
            "total_observed_activities",
            "suspected_bot",
            "bot_classification",
            "first_observed_activity",
            "last_observed_activity",
        ]
    ], unmatched_total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commits", type=Path, default=DEFAULT_COMMITS)
    parser.add_argument("--pull-requests", type=Path, default=DEFAULT_PULL_REQUESTS)
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--sort-by",
        choices=SORT_COLUMNS,
        default="github_login",
        help="Sort independently by a named metric/date; total is intentionally excluded",
    )
    parser.add_argument(
        "--ascending",
        action="store_true",
        help="Use ascending order (login is always ascending by default)",
    )
    args = parser.parse_args()
    try:
        frame, unmatched = build_table(args.commits, args.pull_requests, args.issues)
        ascending = True if args.sort_by == "github_login" else args.ascending
        frame = frame.sort_values(
            [args.sort_by, "github_login"],
            ascending=[ascending, True],
            kind="stable",
        )
        write_csv(frame, args.output)
    except (OSError, ValueError, pd.errors.ParserError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Wrote {len(frame)} matched contributors to {args.output}")
    print(f"Sorted by {args.sort_by}; activity metrics remain separate columns")
    if unmatched:
        print(
            f"Excluded {unmatched} activity records with no exact GitHub login from "
            "the contributor grouping; they remain in the processed source tables."
        )


if __name__ == "__main__":
    main()
