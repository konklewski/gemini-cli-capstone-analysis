#!/usr/bin/env python3
"""Transform raw GitHub commit JSON into a windowed, traceable CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import END_DATE, START_DATE  # noqa: E402
from scripts.common import (  # noqa: E402
    filter_analysis_window,
    load_records,
    nested_get,
    require_fields,
    require_values,
    write_csv,
)
from scripts.detect_bots import classify_actor  # noqa: E402


DEFAULT_INPUT = PROJECT_ROOT / "data" / "raw" / "commits.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "commits.csv"


def transform(records: list[dict], source: Path) -> pd.DataFrame:
    """Extract commit identity and evidence fields without identity guessing."""

    rows = []
    for index, record in enumerate(records):
        require_fields(record, ("sha", "commit"), index=index, source=source)
        require_values(record, ("sha",), index=index, source=source)
        commit = record["commit"]
        if not isinstance(commit, dict):
            raise ValueError(f"Record {index} in {source}: commit must be an object")
        git_author = commit.get("author")
        if not isinstance(git_author, dict):
            raise ValueError(f"Record {index} in {source}: commit.author must be an object")
        require_values(
            git_author, ("name", "email", "date"), index=index, source=source
        )
        github_author = record.get("author")
        if github_author is not None and not isinstance(github_author, dict):
            raise ValueError(f"Record {index} in {source}: author must be object or null")

        login = nested_get(github_author, "login")
        actor_type = nested_get(github_author, "type")
        classification, reason = classify_actor(login, actor_type)
        sha = record["sha"]
        rows.append(
            {
                "github_login": login,
                "git_author_name": git_author.get("name"),
                "git_author_email": git_author.get("email"),
                "commit_sha": sha,
                "author_date": git_author.get("date"),
                "commit_message": commit.get("message"),
                "github_url": record.get("html_url"),
                "author_association": record.get("author_association"),
                "actor_type": actor_type,
                "bot_classification": classification,
                "bot_detection_reason": reason,
                "source_raw_object_identifier": sha,
                "source_record_index": index,
                "source_file": source.name,
            }
        )
    if not rows:
        raise ValueError(f"No commit records found in {source}")
    return filter_analysis_window(pd.DataFrame(rows), "author_date", START_DATE, END_DATE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        frame = transform(load_records(args.input), args.input)
        write_csv(frame, args.output)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(
        f"Wrote {len(frame)} commits within {START_DATE} to {END_DATE} "
        f"to {args.output}"
    )
    missing = int(frame["github_login"].isna().sum())
    if missing:
        print(
            f"Note: {missing} commits have no matched GitHub login; their Git author "
            "identity was retained but not guessed."
        )


if __name__ == "__main__":
    main()
