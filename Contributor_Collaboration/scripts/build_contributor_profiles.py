#!/usr/bin/env python3
"""Summarize changed-file patterns for the selected top contributors.

This script reads commit SHAs from the processed analysis data and inspects the
separate Gemini CLI Git checkout without modifying it. Counts are changed-file
occurrences, not lines changed or claims of contribution quality.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.common import write_csv  # noqa: E402


DEFAULT_TOP = PROJECT_ROOT / "output" / "top_10_percentile_activity.csv"
DEFAULT_COMMITS = PROJECT_ROOT / "data" / "processed" / "commits.csv"
DEFAULT_REPOSITORY = PROJECT_ROOT.parent / "gemini-cli"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "top_10_contributor_profile_summary.csv"


def subsystem_for(path: str) -> str:
    """Map a repository path to a readable, deterministic subsystem prefix."""

    parts = path.split("/")
    if len(parts) >= 4 and parts[0] == "packages" and parts[2] == "src":
        return "/".join(parts[:4])
    if len(parts) >= 2 and parts[0] == "packages":
        return "/".join(parts[:2])
    return parts[0]


def changed_paths(repository: Path, shas: list[str]) -> list[str]:
    """Return changed paths for commits, failing if the checkout lacks a SHA."""

    if not shas:
        return []
    command = [
        "git",
        "-C",
        str(repository),
        "show",
        "--format=",
        "--name-only",
        "--no-renames",
        *shas,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError(
            f"Git could not inspect commits in {repository}: {result.stderr.strip()}"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def formatted_counts(values: Counter[str], limit: int) -> str:
    """Serialize the most frequent values with their occurrence counts."""

    return " | ".join(f"{name} ({count})" for name, count in values.most_common(limit))


def build_summary(top: pd.DataFrame, commits: pd.DataFrame, repository: Path) -> pd.DataFrame:
    """Build one auditable changed-file summary per selected contributor."""

    required_top = {
        "github_login",
        "commits_authored",
        "pull_requests_opened",
        "issues_opened",
        "equal_weight_rank",
    }
    missing_top = sorted(required_top - set(top.columns))
    if missing_top:
        raise ValueError(f"Top-contributor table is missing: {', '.join(missing_top)}")
    required_commits = {"github_login", "commit_sha"}
    missing_commits = sorted(required_commits - set(commits.columns))
    if missing_commits:
        raise ValueError(f"Commit table is missing: {', '.join(missing_commits)}")
    if not (repository / ".git").exists():
        raise ValueError(f"Not a Git checkout: {repository}")

    rows = []
    for position, contributor in enumerate(top.itertuples(index=False), start=1):
        shas = commits.loc[
            commits["github_login"].eq(contributor.github_login), "commit_sha"
        ].astype(str).tolist()
        paths = changed_paths(repository, shas)
        subsystems = Counter(subsystem_for(path) for path in paths)
        files = Counter(paths)
        rows.append(
            {
                "table_position": position,
                "equal_weight_rank": contributor.equal_weight_rank,
                "github_login": contributor.github_login,
                "github_profile": f"https://github.com/{contributor.github_login}",
                "commits_authored": contributor.commits_authored,
                "pull_requests_opened": contributor.pull_requests_opened,
                "issues_opened": contributor.issues_opened,
                "commit_records_inspected": len(shas),
                "changed_file_occurrences": len(paths),
                "top_subsystems": formatted_counts(subsystems, 8),
                "top_files": formatted_counts(files, 8),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=DEFAULT_TOP)
    parser.add_argument("--commits", type=Path, default=DEFAULT_COMMITS)
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        result = build_summary(
            pd.read_csv(args.top), pd.read_csv(args.commits), args.repository
        )
        write_csv(result, args.output)
    except (OSError, ValueError, pd.errors.ParserError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(
        f"Wrote changed-file profiles for {len(result)} contributors to {args.output}"
    )
    print(f"Inspected repository read-only: {args.repository}")


if __name__ == "__main__":
    main()
