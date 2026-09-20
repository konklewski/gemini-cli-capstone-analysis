#!/usr/bin/env python3
"""Add conservative, explainable bot classifications to GitHub actors."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.common import load_records, nested_get, write_csv  # noqa: E402


EXACT_AUTOMATION_NAMES = {
    "dependabot",
    "gemini-cli-robot",
    "renovate",
    "github-actions",
    "googlebot",
    "codecov",
    "release-please",
}
AUTOMATION_PATTERN = re.compile(
    r"(?:^|[-_])(dependabot|renovate|github-actions|release-please|automation|ci-bot)(?:$|[-_])",
    re.IGNORECASE,
)


def classify_actor(
    login: Any, account_type: Any = None, explicit_bot: Any = None
) -> tuple[str, str]:
    """Return ``(classification, reason)`` using conservative heuristics.

    Strong GitHub metadata and conventional ``[bot]`` names classify a bot.
    Obvious automation tokens classify a bot, but generic substrings such as
    merely containing ``bot`` do not.  Missing identities remain uncertain.
    """

    if explicit_bot is True:
        return "bot", "explicit metadata marks the actor as automated"
    if isinstance(account_type, str) and account_type.casefold() == "bot":
        return "bot", "GitHub account type is Bot"
    if not isinstance(login, str) or not login.strip():
        return "uncertain", "GitHub login is missing"

    normalized = login.strip().casefold()
    if normalized.endswith("[bot]"):
        return "bot", "username ends in [bot]"
    if normalized.endswith("-bot") or normalized.endswith("_bot"):
        return "bot", "username ends in an explicit -bot or _bot suffix"
    if normalized in EXACT_AUTOMATION_NAMES or AUTOMATION_PATTERN.search(normalized):
        return "bot", "username matches a known automation naming pattern"
    if isinstance(account_type, str) and account_type.casefold() == "user":
        return "human", "GitHub account type is User and no bot indicator matched"
    return "uncertain", "login is present but reliable account-type metadata is missing"


def json_to_frame(path: Path) -> pd.DataFrame:
    """Extract actor fields from common GitHub object shapes."""

    rows = []
    for index, record in enumerate(load_records(path)):
        user = record.get("user") or record.get("author")
        login = nested_get(user, "login") if isinstance(user, dict) else record.get("login")
        account_type = (
            nested_get(user, "type") if isinstance(user, dict) else record.get("type")
        )
        classification, reason = classify_actor(login, account_type)
        rows.append(
            {
                "source_record_index": index,
                "github_login": login,
                "account_type": account_type,
                "bot_classification": classification,
                "bot_detection_reason": reason,
            }
        )
    return pd.DataFrame(rows)


def classify_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Classify a CSV containing a recognized login column."""

    login_column = next(
        (name for name in ("github_login", "login", "author_login") if name in frame),
        None,
    )
    if login_column is None:
        raise ValueError(
            "CSV needs one of these login columns: github_login, login, author_login"
        )
    type_column = next(
        (name for name in ("account_type", "actor_type", "user_type", "type") if name in frame),
        None,
    )
    classified = [
        classify_actor(row[login_column], row[type_column] if type_column else None)
        for _, row in frame.iterrows()
    ]
    result = frame.copy()
    result["bot_classification"] = [item[0] for item in classified]
    result["bot_detection_reason"] = [item[1] for item in classified]
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Processed CSV or raw GitHub JSON")
    parser.add_argument("output", type=Path, help="Destination CSV (not data/raw)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.output.resolve().is_relative_to((PROJECT_ROOT / "data" / "raw").resolve()):
            raise ValueError("Refusing to write generated data inside data/raw/")
        if args.input.suffix.casefold() == ".csv":
            frame = classify_frame(pd.read_csv(args.input))
        else:
            frame = json_to_frame(args.input)
        write_csv(frame, args.output)
    except (OSError, ValueError, pd.errors.ParserError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Wrote {len(frame)} classified records to {args.output}")


if __name__ == "__main__":
    main()
