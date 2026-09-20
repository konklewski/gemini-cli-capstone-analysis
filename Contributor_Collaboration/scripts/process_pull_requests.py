#!/usr/bin/env python3
"""Transform raw GitHub pull-request JSON into a windowed CSV."""

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


DEFAULT_INPUT = PROJECT_ROOT / "data" / "raw" / "pull_requests.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "pull_requests.csv"


def transform(records: list[dict], source: Path) -> pd.DataFrame:
    """Extract one row per pull request and retain evidence links."""

    rows = []
    for index, record in enumerate(records):
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
                "pr_number": record["number"],
                "author_login": login,
                "created_at": record["created_at"],
                "closed_at": record.get("closed_at"),
                "merged_at": record.get("merged_at"),
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
        raise ValueError(f"No pull-request records found in {source}")
    return filter_analysis_window(pd.DataFrame(rows), "created_at", START_DATE, END_DATE)


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
        f"Wrote {len(frame)} pull requests opened within {START_DATE} to "
        f"{END_DATE} to {args.output}"
    )


if __name__ == "__main__":
    main()
