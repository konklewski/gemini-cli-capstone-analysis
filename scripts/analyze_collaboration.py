#!/usr/bin/env python3
"""Generate candidate collaboration evidence for a selected contributor set.

The script treats shared files only as a candidate signal. Stronger signals are
comments on another contributor's item, explicit mentions, and direct replies in
inline review threads. The output still requires manual interpretation.
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import END_DATE, START_DATE  # noqa: E402
from scripts.build_contributor_profiles import changed_paths  # noqa: E402
from scripts.common import load_records, nested_get, write_csv  # noqa: E402


DEFAULT_TOP = PROJECT_ROOT / "output" / "top_10_percentile_activity.csv"
DEFAULT_COMMITS = PROJECT_ROOT / "data" / "processed" / "commits.csv"
DEFAULT_PULLS = PROJECT_ROOT / "data" / "raw" / "pull_requests.json"
DEFAULT_ISSUES = PROJECT_ROOT / "data" / "raw" / "issues.json"
DEFAULT_ISSUE_COMMENTS = PROJECT_ROOT / "data" / "raw" / "issue_comments.json"
DEFAULT_REVIEW_COMMENTS = PROJECT_ROOT / "data" / "raw" / "review_comments.json"
DEFAULT_REPOSITORY = PROJECT_ROOT.parent / "gemini-cli"
DEFAULT_INTERACTIONS = (
    PROJECT_ROOT / "data" / "processed" / "collaboration_interactions.csv"
)
DEFAULT_PAIR_METRICS = PROJECT_ROOT / "output" / "top_10_collaboration_pair_metrics.csv"
MENTION_PATTERN = re.compile(r"(?<![\w])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))")


def number_from_url(url: Any) -> int | None:
    """Extract the trailing GitHub issue/PR number from an API URL."""

    if not isinstance(url, str) or not url:
        return None
    try:
        return int(url.rstrip("/").split("/")[-1])
    except ValueError:
        return None


def in_window(value: Any) -> bool:
    """Return whether a timestamp falls in the configured inclusive window."""

    if not isinstance(value, str):
        raise ValueError(f"Comment has invalid created_at value: {value!r}")
    timestamp = pd.Timestamp(value)
    return pd.Timestamp(START_DATE) <= timestamp <= pd.Timestamp(END_DATE)


def canonical_pair(a: str, b: str) -> tuple[str, str]:
    """Return a stable case-insensitive ordering for a contributor pair."""

    return tuple(sorted((a, b), key=str.casefold))  # type: ignore[return-value]


def load_item_metadata(pulls_path: Path, issues_path: Path) -> dict[int, dict[str, Any]]:
    """Map all repository item numbers to their type, author, title, and URL."""

    metadata: dict[int, dict[str, Any]] = {}
    for record in load_records(pulls_path):
        number = record.get("number")
        if isinstance(number, int):
            metadata[number] = {
                "item_type": "pull_request",
                "item_author_login": nested_get(record.get("user"), "login"),
                "item_title": record.get("title"),
                "item_url": record.get("html_url"),
            }
    for record in load_records(issues_path):
        if "pull_request" in record:
            continue
        number = record.get("number")
        if isinstance(number, int):
            metadata[number] = {
                "item_type": "issue",
                "item_author_login": nested_get(record.get("user"), "login"),
                "item_title": record.get("title"),
                "item_url": record.get("html_url"),
            }
    return metadata


def event_row(
    *,
    event_type: str,
    actor: str,
    target: str,
    comment: dict[str, Any],
    source_dataset: str,
    item_number: int | None,
    item: dict[str, Any] | None,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one traceable interaction event row."""

    pair_a, pair_b = canonical_pair(actor, target)
    item = item or {}
    return {
        "event_type": event_type,
        "pair_a": pair_a,
        "pair_b": pair_b,
        "actor_login": actor,
        "target_login": target,
        "created_at": comment.get("created_at"),
        "source_dataset": source_dataset,
        "source_comment_id": comment.get("id"),
        "comment_url": comment.get("html_url"),
        "comment_body": comment.get("body"),
        "parent_comment_url": parent.get("html_url") if parent else None,
        "parent_comment_body": parent.get("body") if parent else None,
        "item_number": item_number,
        "item_type": item.get("item_type"),
        "item_author_login": item.get("item_author_login"),
        "item_title": item.get("item_title"),
        "item_url": item.get("item_url"),
        "review_path": comment.get("path"),
        "in_reply_to_id": comment.get("in_reply_to_id"),
    }


def extract_interactions(
    issue_comments: list[dict[str, Any]],
    review_comments: list[dict[str, Any]],
    selected_logins: list[str],
    item_metadata: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Extract cross-contributor events without inferring collaboration."""

    normalized = {login.casefold(): login for login in selected_logins}
    events: list[dict[str, Any]] = []

    def selected(value: Any) -> str | None:
        return normalized.get(value.casefold()) if isinstance(value, str) else None

    sources = (
        ("issue_comment", issue_comments, "issue_url"),
        ("review_comment", review_comments, "pull_request_url"),
    )
    for source_dataset, comments, item_url_field in sources:
        for comment in comments:
            if not in_window(comment.get("created_at")):
                continue
            actor = selected(nested_get(comment.get("user"), "login"))
            if actor is None:
                continue
            item_number = number_from_url(comment.get(item_url_field))
            item = item_metadata.get(item_number) if item_number is not None else None
            item_author = selected((item or {}).get("item_author_login"))
            if item_author is not None and item_author != actor:
                events.append(
                    event_row(
                        event_type="comment_on_authored_item",
                        actor=actor,
                        target=item_author,
                        comment=comment,
                        source_dataset=source_dataset,
                        item_number=item_number,
                        item=item,
                    )
                )
            for mention in MENTION_PATTERN.findall(comment.get("body") or ""):
                target = selected(mention)
                if target is not None and target != actor:
                    events.append(
                        event_row(
                            event_type="explicit_mention",
                            actor=actor,
                            target=target,
                            comment=comment,
                            source_dataset=source_dataset,
                            item_number=item_number,
                            item=item,
                        )
                    )

    parents = {comment.get("id"): comment for comment in review_comments}
    for comment in review_comments:
        if not in_window(comment.get("created_at")) or not comment.get("in_reply_to_id"):
            continue
        parent = parents.get(comment["in_reply_to_id"])
        actor = selected(nested_get(comment.get("user"), "login"))
        target = selected(nested_get((parent or {}).get("user"), "login"))
        if actor is None or target is None or actor == target:
            continue
        item_number = number_from_url(comment.get("pull_request_url"))
        events.append(
            event_row(
                event_type="direct_review_reply",
                actor=actor,
                target=target,
                comment=comment,
                source_dataset="review_comment",
                item_number=item_number,
                item=item_metadata.get(item_number) if item_number is not None else None,
                parent=parent,
            )
        )

    columns = [
        "event_type",
        "pair_a",
        "pair_b",
        "actor_login",
        "target_login",
        "created_at",
        "source_dataset",
        "source_comment_id",
        "comment_url",
        "comment_body",
        "parent_comment_url",
        "parent_comment_body",
        "item_number",
        "item_type",
        "item_author_login",
        "item_title",
        "item_url",
        "review_path",
        "in_reply_to_id",
    ]
    return pd.DataFrame(events, columns=columns).sort_values(
        ["pair_a", "pair_b", "created_at", "event_type"], kind="stable"
    )


def file_sets(
    selected_logins: list[str], commits: pd.DataFrame, repository: Path
) -> dict[str, set[str]]:
    """Return distinct changed-file sets for each selected contributor."""

    required = {"github_login", "commit_sha"}
    missing = sorted(required - set(commits.columns))
    if missing:
        raise ValueError(f"Commit table is missing: {', '.join(missing)}")
    result = {}
    for login in selected_logins:
        shas = commits.loc[commits["github_login"].eq(login), "commit_sha"].astype(str)
        result[login] = set(changed_paths(repository, shas.tolist()))
    return result


def build_pair_metrics(
    selected_logins: list[str], interactions: pd.DataFrame, files: dict[str, set[str]]
) -> pd.DataFrame:
    """Combine interaction counts and shared-file candidate signals."""

    rows = []
    for left, right in itertools.combinations(selected_logins, 2):
        pair_a, pair_b = canonical_pair(left, right)
        pair_events = interactions.loc[
            interactions["pair_a"].eq(pair_a) & interactions["pair_b"].eq(pair_b)
        ]
        counts = Counter(pair_events["event_type"])
        shared = files[left] & files[right]
        union = files[left] | files[right]
        item_comments = pair_events.loc[
            pair_events["event_type"].eq("comment_on_authored_item")
        ]
        directions = item_comments[["actor_login", "target_login"]].drop_duplicates()
        rows.append(
            {
                "pair_a": pair_a,
                "pair_b": pair_b,
                "comments_on_other_authored_items": counts["comment_on_authored_item"],
                "direct_review_replies": counts["direct_review_reply"],
                "explicit_mentions": counts["explicit_mention"],
                "distinct_interaction_items": pair_events["item_number"].nunique(),
                "reciprocal_authored_item_commenting": len(directions) >= 2,
                "shared_distinct_files": len(shared),
                "shared_file_jaccard": len(shared) / len(union) if union else 0.0,
                "screening_score": counts["comment_on_authored_item"]
                + 3 * counts["direct_review_reply"]
                + 2 * counts["explicit_mention"],
                "top_shared_files": "|".join(sorted(shared)[:20]),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["screening_score", "direct_review_replies", "shared_distinct_files"],
        ascending=[False, False, False],
        kind="stable",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=Path, default=DEFAULT_TOP)
    parser.add_argument("--commits", type=Path, default=DEFAULT_COMMITS)
    parser.add_argument("--pulls", type=Path, default=DEFAULT_PULLS)
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES)
    parser.add_argument("--issue-comments", type=Path, default=DEFAULT_ISSUE_COMMENTS)
    parser.add_argument("--review-comments", type=Path, default=DEFAULT_REVIEW_COMMENTS)
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument("--interactions-output", type=Path, default=DEFAULT_INTERACTIONS)
    parser.add_argument("--pair-metrics-output", type=Path, default=DEFAULT_PAIR_METRICS)
    args = parser.parse_args()

    try:
        top = pd.read_csv(args.top)
        if "github_login" not in top:
            raise ValueError(f"{args.top} has no github_login column")
        selected_logins = top["github_login"].astype(str).tolist()
        item_metadata = load_item_metadata(args.pulls, args.issues)
        issue_comments = load_records(args.issue_comments)
        review_comments = load_records(args.review_comments)
        interactions = extract_interactions(
            issue_comments, review_comments, selected_logins, item_metadata
        )
        files = file_sets(selected_logins, pd.read_csv(args.commits), args.repository)
        pair_metrics = build_pair_metrics(selected_logins, interactions, files)
        write_csv(interactions, args.interactions_output)
        write_csv(pair_metrics, args.pair_metrics_output)
    except (OSError, ValueError, pd.errors.ParserError) as error:
        raise SystemExit(f"Error: {error}") from error

    print(
        f"Analyzed {len(selected_logins)} contributors, "
        f"{len(issue_comments)} issue/PR comments, and "
        f"{len(review_comments)} inline review comments"
    )
    print(f"Wrote {len(interactions)} interaction signals to {args.interactions_output}")
    print(f"Wrote {len(pair_metrics)} pair rows to {args.pair_metrics_output}")
    print("Shared files remain a candidate signal; manually verify collaboration claims.")


if __name__ == "__main__":
    main()
