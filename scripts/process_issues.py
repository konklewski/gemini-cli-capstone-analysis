#!/usr/bin/env python3
"""Transform raw GitHub issue JSON, explicitly excluding pull requests."""

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
    label_names,
    load_records,
    nested_get,
    require_values,
    write_csv,
)
from scripts.detect_bots import classify_actor  # noqa: E402


DEFAULT_INPUT = PROJECT_ROOT / "data" / "raw" / "issues.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "issues.csv"


def transform(records: list[dict], source: Path) -> tuple[pd.DataFrame, int]:
    """Extract actual issues and return the number of PR-shaped exclusions.

    GitHub's Issues API intentionally includes pull requests.  Any object with
    a ``pull_request`` field is therefore excluded from the issues-opened
    metric, rather than double-counted as both an issue and a pull request.
    """

    rows = []
    excluded_pull_requests = 0
    for index, record in enumerate(records):
        if "pull_request" in record:
            excluded_pull_requests += 1
            continue
        require_values(
            record,
            ("number", "created_at", "state", "title", "html_url"),
            index=index,
            source=source,
        )
        user = record.get("user")
        if user is not None and not isinstance(user, dict):
            raise ValueError(f"Record {index} in {source}: user must be object or null")
        login = nested_get(user, "login")
        actor_type = nested_get(user, "type")
        classification, reason = classify_actor(login, actor_type)
        identifier = record.get("node_id") or record.get("id") or record["number"]
        rows.append(
            {
                "issue_number": record["number"],
                "author_login": login,
                "created_at": record["created_at"],
                "closed_at": record.get("closed_at"),
                "state": record["state"],
                "title": record["title"],
                "github_url": record["html_url"],
                "labels": label_names(record.get("labels", [])),
                "author_association": record.get("author_association"),
                "actor_type": actor_type,
                "bot_classification": classification,
                "bot_detection_reason": reason,
                "source_raw_object_identifier": identifier,
                "source_record_index": index,
                "source_file": source.name,
            }
        )
    if not rows:
        raise ValueError(
            f"No actual issue records found in {source}; "
            f"excluded {excluded_pull_requests} PR-shaped objects"
        )
    frame = filter_analysis_window(pd.DataFrame(rows), "created_at", START_DATE, END_DATE)
    return frame, excluded_pull_requests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        frame, excluded = transform(load_records(args.input), args.input)
        write_csv(frame, args.output)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(
        f"Wrote {len(frame)} issues opened within {START_DATE} to {END_DATE} "
        f"to {args.output}"
    )
    print(f"Excluded {excluded} pull-request-shaped objects returned by the Issues API")


if __name__ == "__main__":
    main()
