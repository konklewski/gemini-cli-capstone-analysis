"""Shared, deliberately small helpers for the processing scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


WRAPPER_KEYS = ("items", "nodes", "data", "results", "values")


def load_json_values(path: Path) -> list[Any]:
    """Load JSON, NDJSON, or concatenated JSON values without changing *path*.

    ``gh api --paginate`` output varies with the flags used.  It may be one
    array, an array per page, or newline-delimited objects.  ``raw_decode``
    supports all three while still rejecting malformed trailing content.
    """

    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Input file is empty: {path}")

    decoder = json.JSONDecoder()
    values: list[Any] = []
    position = 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position >= len(text):
            break
        try:
            value, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError as error:
            context = text[max(0, error.pos - 40) : error.pos + 40]
            raise ValueError(
                f"Malformed JSON in {path} at line {error.lineno}, "
                f"column {error.colno}. Context: {context!r}"
            ) from error
        values.append(value)
    return values


def records_from_values(values: list[Any], path: Path) -> list[dict[str, Any]]:
    """Convert familiar GitHub JSON containers to a flat record list.

    Unknown dictionaries are treated as a single API object.  A recognizable
    wrapper is unpacked only when its value is a list.  Non-object records fail
    explicitly instead of being silently discarded.
    """

    records: list[Any] = []
    for value in values:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, list):  # output produced by --slurp
                    records.extend(item)
                else:
                    records.append(item)
        elif isinstance(value, dict):
            wrapper = next(
                (key for key in WRAPPER_KEYS if isinstance(value.get(key), list)),
                None,
            )
            records.extend(value[wrapper] if wrapper else [value])
        else:
            raise ValueError(
                f"Unsupported top-level value {type(value).__name__} in {path}; "
                "expected a JSON object, array, or NDJSON objects."
            )

    bad = [index for index, item in enumerate(records) if not isinstance(item, dict)]
    if bad:
        preview = ", ".join(map(str, bad[:10]))
        raise ValueError(f"Non-object records in {path} at indexes: {preview}")
    return records


def load_records(path: Path) -> list[dict[str, Any]]:
    """Load records from a supported JSON representation."""

    return records_from_values(load_json_values(path), path)


def require_fields(
    record: dict[str, Any], fields: Iterable[str], *, index: int, source: Path
) -> None:
    """Raise a useful error when structural fields are absent.

    A present field may legitimately contain ``null`` (for example a deleted
    GitHub user), so this checks key presence rather than truthiness.
    """

    missing = [field for field in fields if field not in record]
    if missing:
        raise ValueError(
            f"Record {index} in {source} is missing required field(s): "
            f"{', '.join(missing)}"
        )


def require_values(
    record: dict[str, Any], fields: Iterable[str], *, index: int, source: Path
) -> None:
    """Require fields whose GitHub schema does not permit null/empty values."""

    require_fields(record, fields, index=index, source=source)
    invalid = [field for field in fields if record[field] is None or record[field] == ""]
    if invalid:
        raise ValueError(
            f"Record {index} in {source} has null/empty required value(s): "
            f"{', '.join(invalid)}"
        )


def nested_get(value: Any, *keys: str) -> Any:
    """Return a safely traversed nested value, or ``None``."""

    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def label_names(value: Any) -> str:
    """Serialize GitHub labels as a stable pipe-separated string."""

    if value is None:
        return ""
    if not isinstance(value, list):
        raise ValueError(f"Expected labels to be a list, got {type(value).__name__}")
    labels: list[str] = []
    for label in value:
        if isinstance(label, dict) and isinstance(label.get("name"), str):
            labels.append(label["name"])
        elif isinstance(label, str):
            labels.append(label)
        else:
            raise ValueError(f"Unrecognized label value: {label!r}")
    return "|".join(sorted(set(labels), key=str.casefold))


def filter_analysis_window(
    frame: pd.DataFrame, date_column: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """Keep rows inside the configured inclusive UTC analysis window."""

    parsed = pd.to_datetime(frame[date_column], utc=True, errors="coerce")
    invalid = frame[date_column].notna() & parsed.isna()
    if invalid.any():
        examples = frame.loc[invalid, date_column].head(5).tolist()
        raise ValueError(f"Invalid timestamps in {date_column}: {examples}")

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("START_DATE and END_DATE must include timezone information")
    if start > end:
        raise ValueError("START_DATE must not be after END_DATE")

    result = frame.loc[parsed.between(start, end, inclusive="both")].copy()
    result[date_column] = parsed.loc[result.index].map(
        lambda value: value.isoformat().replace("+00:00", "Z")
        if pd.notna(value)
        else None
    )
    return result.reset_index(drop=True)


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Write a generated CSV, creating only its destination directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
