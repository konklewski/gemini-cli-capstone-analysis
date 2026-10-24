#!/usr/bin/env python3
"""One row per observed action; preserve bots and unknown actors for totals.

Authorship: commits on main (author date), PR/issue opening. Participation also
includes issue/PR conversation comments, inline comments, submitted reviews,
merges, closes without merging, issue closes and reopenings. A review and its
inline comments are distinct actions, not interchangeable units of effort.
Comment collection uses updated_at >= START_DATE: window coverage plus incidental
earlier comments, not complete comment history. Other sources include earlier history.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT.parents[1] / "Interim" / "Contributor_Collaboration"))
from scripts.common import load_records
RAW = PROJECT_ROOT / "data" / "raw"
from config import END_DATE, START_DATE

OUTPUT = PROJECT_ROOT / "output"
CONTRIBUTIONS = ("commit", "pull_request", "issue")
KINDS = (*CONTRIBUTIONS, "comment", "review_comment", "review", "pull_request_merged",
         "pull_request_closed_unmerged", "issue_closed", "pull_request_reopened", "issue_reopened")


def unlinked_commit_authors() -> dict[str, str]:
    decisions = pd.read_csv(PROJECT_ROOT / "evidence" / "identity_decisions.csv").fillna("")
    rows = decisions[decisions["measure"].str.startswith("M1c")]
    return {re.search(r"commit/([0-9a-f]{40})", r.evidence).group(1): r.canonical
            for r in rows.itertuples()}


def actor_login(actor: dict | None, app_logins: dict | None = None) -> str | None:
    """GraphQL Bot.login omits REST's [bot] suffix; User logins do not."""
    if not actor:
        return None
    login = actor.get("login")
    if login and actor.get("__typename") == "Bot" and app_logins and login.casefold() in app_logins:
        return app_logins[login.casefold()]
    if login and actor.get("__typename") == "Bot" and not login.endswith("[bot]"):
        login += "[bot]"
    return login


def timeline_events(item: dict) -> list[dict]:
    """Preserve a known last closure even when GitHub omits its timeline node."""
    events = item["timelineItems"]["nodes"]
    last = max(events, key=lambda e: e["createdAt"]) if events else None
    if item.get("closedAt") and not item.get("mergedAt") and (not last or last["__typename"] != "ClosedEvent"):
        return events + [{"__typename": "ClosedEvent", "actor": None, "createdAt": item["closedAt"],
                          "id": "last-observed-close", "metadata_fallback": True}]
    return events


def state_at(item: dict, cutoff: str = END_DATE) -> str:
    """Reconstruct state at cutoff, including close/reopen cycles."""
    if item.get("mergedAt") and item["mergedAt"] <= cutoff:
        return "merged"
    state = "open"
    for event in sorted(timeline_events(item), key=lambda e: e["createdAt"]):
        if event["createdAt"] <= cutoff:
            state = "closed" if event["__typename"] == "ClosedEvent" else "open"
    return state


def is_merge_closure(item: dict, event: dict) -> bool:
    """GitHub may timestamp the merge's closure a second after mergedAt."""
    return bool(item.get("mergedAt") and event["__typename"] == "ClosedEvent"
                and event["createdAt"] >= item["mergedAt"])


def load_events() -> pd.DataFrame:
    """Shared unfiltered observations for bot checks, identities and metrics."""
    attributed = unlinked_commit_authors()
    app_logins = {}
    rows = []

    def add(actor, kind, timestamp, url, object_url, association=None, outcome=None, source="rest", text=""):
        if not timestamp:  # pending (unsubmitted) reviews are not actions
            return
        if kind == "pull_request" and outcome == "closed":
            outcome = "closed_unmerged"
        if actor and actor.get("type") == "Bot" and "/apps/" in actor.get("html_url", ""):
            app_logins[actor["html_url"].rsplit("/", 1)[-1].casefold()] = actor["login"]
        login = actor_login(actor, app_logins)
        account_type = (actor or {}).get("type") or (actor or {}).get("__typename")
        rows.append((login, kind, timestamp, url, object_url, association,
                     outcome, account_type, text or "", source))

    for c in load_records(RAW / "commits.json"):
        actor = c.get("author")
        if not actor and c["sha"] in attributed:
            actor = {"login": attributed[c["sha"]], "type": "User"}
        add(actor, "commit", c["commit"]["author"]["date"], c["html_url"], c["html_url"], text=c["commit"]["message"])

    # Read comments before GraphQL to map app slugs to REST logins (notably Copilot).
    for name, kind in (("issue_comments", "comment"), ("review_comments", "review_comment")):
        for c in load_records(RAW / f"{name}.json"):
            add(c.get("user"), kind, c["created_at"], c["html_url"], c["html_url"].split("#")[0],
                c.get("author_association"), text=c["body"])

    # REST supplies original associations and preserves items subsequently deleted.
    # GraphQL supplements missing openings and supplies all decision events.
    for filename, rest_name, kind in (("pr_details", "pull_requests", "pull_request"),
                                      ("issue_details", "issues", "issue")):
        details = json.loads((RAW / f"{filename}.json").read_text())
        by_number = {d["number"]: d for d in details}
        seen = set()
        for item in load_records(RAW / f"{rest_name}.json"):
            if kind == "issue" and "pull_request" in item:
                continue
            seen.add(item["number"])
            detail = by_number.get(item["number"])
            outcome = state_at(detail) if detail else "unknown"
            add(item.get("user"), kind, item["created_at"], item["html_url"], item["html_url"],
                item.get("author_association"), outcome, text=item.get("body"))
            # A few objects disappeared between snapshots. Keep their recorded last
            # closure, while leaving cutoff state unknown (earlier cycles unavailable).
            if detail is None and item.get("closed_at"):
                fallback_kind = "issue_closed" if kind == "issue" else (
                    "pull_request_merged" if item.get("merged_at") else "pull_request_closed_unmerged")
                add(item.get("closed_by"), fallback_kind, item.get("merged_at") or item["closed_at"],
                    item["html_url"] + "#last-observed-close", item["html_url"], source="rest_last_closure")
        for item in details:
            if "pageInfo" not in item["timelineItems"] or item["timelineItems"]["pageInfo"]["hasNextPage"]:
                raise ValueError("Incomplete timelines: run scripts/fetch_graphql.py first")
            url = item["url"]
            if item["number"] not in seen:
                add(item["author"], kind, item["createdAt"], url, url,
                    item["authorAssociation"], state_at(item), "graphql_supplement")
            if kind == "pull_request":
                reviews = item["reviews"]
                if reviews["pageInfo"]["hasNextPage"] or len(reviews["nodes"]) != reviews["totalCount"]:
                    raise ValueError(f"Incomplete reviews: PR #{item['number']}")
                for r in reviews["nodes"]:
                    add(r["author"], "review", r["submittedAt"], r["url"], url,
                        r["authorAssociation"], r["state"], "graphql", text=r["body"])
                if item["mergedAt"]:
                    add(item["mergedBy"], "pull_request_merged", item["mergedAt"],
                        url + "#merged", url, source="graphql")
            for event in timeline_events(item):
                # Merging closes a PR too: count that action once, as a merge.
                if kind == "pull_request" and is_merge_closure(item, event):
                    continue
                suffix = "reopened" if event["__typename"] == "ReopenedEvent" else (
                    "closed_unmerged" if kind == "pull_request" else "closed")
                add(event["actor"], f"{kind}_{suffix}", event["createdAt"],
                    url + "#" + event["id"], url,
                    source="graphql_last_closure" if event.get("metadata_fallback") else "graphql")

    frame = pd.DataFrame(rows, columns=["login", "kind", "created_at", "url", "object_url",
                                        "association", "outcome", "account_type", "text", "source"])
    # GitHub logins are case-insensitive. Preserve one display spelling per account.
    spelling = {}
    frame["login"] = frame["login"].map(lambda login: spelling.setdefault(login.casefold(), login) if login else None)
    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
    frame["in_window"] = frame["created_at"].between(pd.Timestamp(START_DATE), pd.Timestamp(END_DATE))
    # Post-cutoff decisions must not influence any derived category or history.
    frame = frame[frame["created_at"] <= pd.Timestamp(END_DATE)].copy()
    if frame.duplicated(["kind", "url"]).any():
        raise ValueError("Duplicate activity IDs in source data")
    return frame.reset_index(drop=True)
