#!/usr/bin/env python3
"""Inspect an unfamiliar GitHub JSON export without modifying it."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.common import load_json_values, records_from_values  # noqa: E402


def flatten_fields(value: Any, prefix: str = "", depth: int = 0) -> list[tuple[str, Any]]:
    """Collect field paths to a limited depth for a compact structural report."""

    if depth > 3:
        return []
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else key
            found.append((path, nested))
            found.extend(flatten_fields(nested, path, depth + 1))
    elif isinstance(value, list) and value:
        found.extend(flatten_fields(value[0], f"{prefix}[]", depth + 1))
    return found


def compact(value: Any, limit: int = 100) -> str:
    """Format a bounded sample value."""

    rendered = json.dumps(value, ensure_ascii=False, default=str)
    return rendered if len(rendered) <= limit else rendered[: limit - 3] + "..."


def likely_object_type(records: list[dict[str, Any]]) -> str:
    """Infer only common GitHub object shapes; otherwise report unknown."""

    if not records:
        return "unknown (no records)"
    keys = set().union(*(record.keys() for record in records[:20]))
    if {"sha", "commit"}.issubset(keys):
        return "GitHub commit"
    if "number" in keys and ({"merged_at", "head", "base"} & keys):
        return "GitHub pull request"
    if "number" in keys and "pull_request" in keys:
        return "GitHub issue-shaped pull request (Issues API result)"
    if {"number", "title", "state"}.issubset(keys):
        return "GitHub issue"
    if {"login", "contributions"}.issubset(keys):
        return "GitHub repository contributor summary"
    if {"submitted_at", "state", "user"}.issubset(keys):
        return "GitHub pull-request review"
    if {"body", "user", "created_at"}.issubset(keys):
        if "pull_request_review_id" in keys:
            return "GitHub pull-request review comment"
        return "GitHub issue or pull-request conversation comment"
    return "unknown; inspect the reported fields before choosing a processor"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="JSON/NDJSON file to inspect")
    args = parser.parse_args()

    try:
        values = load_json_values(args.path)
        records = records_from_values(values, args.path)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error

    raw_types = Counter(type(value).__name__ for value in values)
    top_level = (
        next(iter(raw_types))
        if len(values) == 1
        else f"{len(values)} concatenated/NDJSON values ({dict(raw_types)})"
    )
    field_types: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[Any]] = defaultdict(list)
    for record in records[:100]:
        for path, value in flatten_fields(record):
            field_types[path][type(value).__name__] += 1
            if value is not None and len(samples[path]) < 3:
                candidate = compact(value)
                if candidate not in samples[path]:
                    samples[path].append(candidate)

    top_fields = sorted({key for record in records for key in record})
    nested = sorted(path for path in field_types if "." in path or "[]" in path)
    dates = sorted(
        path
        for path in field_types
        if any(token in path.casefold() for token in ("date", "_at", "timestamp"))
    )
    users = sorted(
        path
        for path in field_types
        if any(token in path.casefold() for token in ("login", "user", "author", "committer"))
    )

    print(f"File: {args.path}")
    print(f"Top-level JSON type: {top_level}")
    print(f"Number of records: {len(records)}")
    print(f"Likely GitHub object type: {likely_object_type(records)}")
    print("Available top-level fields:")
    print("  " + (", ".join(top_fields) if top_fields else "(none)"))
    print("Relevant nested fields:")
    relevant_nested = [
        path
        for path in nested
        if any(
            token in path.casefold()
            for token in ("user", "author", "commit", "label", "review", "pull", "issue", "url")
        )
    ]
    for path in relevant_nested[:60]:
        print(f"  - {path} ({'/'.join(sorted(field_types[path]))})")
    if len(relevant_nested) > 60:
        print(f"  ... {len(relevant_nested) - 60} more")
    print("Date-related fields:")
    print("  " + (", ".join(dates) if dates else "(none detected)"))
    print("User/login-related fields:")
    print("  " + (", ".join(users) if users else "(none detected)"))
    print("Sample values (up to 3 per selected field):")
    selected = list(dict.fromkeys(top_fields[:15] + dates + users))[:35]
    for path in selected:
        shown = "; ".join(samples.get(path, [])) or "(only null/missing in sample)"
        print(f"  - {path}: {shown}")


if __name__ == "__main__":
    main()

