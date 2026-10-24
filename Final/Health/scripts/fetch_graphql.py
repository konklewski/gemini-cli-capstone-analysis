#!/usr/bin/env python3
"""Fetch complete reviews and close/reopen histories, including actor types.

Run from Final/Health/: .venv/bin/python scripts/fetch_graphql.py [pulls|issues]
Objects created by END_DATE are needed; analysis applies the event cutoff.
Outer and nested connections are paginated. Interrupted runs resume from a
checkpoint. Delete data/raw/<kind>_checkpoint.jsonl to start a fresh download.
Approving a PR does not establish maintainer status or merge permission.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import END_DATE, OWNER, REPO

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
ACTOR = "login __typename"
PAGE = "pageInfo{hasNextPage endCursor}"
REVIEW = f"id url author{{{ACTOR}}} authorAssociation state submittedAt body"
EVENT = (f"__typename ... on ClosedEvent{{id actor{{{ACTOR}}} createdAt}} "
         f"... on ReopenedEvent{{id actor{{{ACTOR}}} createdAt}}")
TIMELINE = "timelineItems(itemTypes:[CLOSED_EVENT,REOPENED_EVENT]"


def run(query: str) -> dict:
    for attempt in range(5):
        result = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"],
                                capture_output=True, text=True, timeout=120)
        payload = json.loads(result.stdout) if result.returncode == 0 else {}
        if payload.get("data") and not payload.get("errors"):
            return payload["data"]
        print(f"retry {attempt + 1}: {str(payload.get('errors') or result.stderr)[:240]}", flush=True)
        # GitHub may time out on large nested pages; smaller pages preserve coverage.
        if any(code in result.stderr for code in ("502", "504", "unexpected end")):
            query = re.sub(r"first:(\d+)", lambda m: f"first:{max(5, int(m[1]) // 2)}", query)
        if attempt < 4:
            time.sleep(min(5 * (attempt + 1), 20))
    raise RuntimeError("GraphQL query failed; existing exports remain intact")


def complete_connection(node: dict, object_name: str, field: str, selection: str, fields: str) -> None:
    block = node[field]
    while block["pageInfo"]["hasNextPage"]:
        cursor = block["pageInfo"]["endCursor"]
        if not cursor:
            raise ValueError("Pagination has no continuation cursor")
        query = (f'query{{repository(owner:"{OWNER}",name:"{REPO}"){{'
                 f'{object_name}(number:{node["number"]}){{'
                 f'{selection}first:100,after:{json.dumps(cursor)}){{{PAGE} nodes{{{fields}}}}}}}}}}}')
        extra = run(query)["repository"][object_name][field]
        block["nodes"].extend(extra["nodes"])
        block["pageInfo"] = extra["pageInfo"]
    # Timeline totalCount includes event types excluded by the itemTypes filter.
    if field == "reviews" and len(block["nodes"]) != block["totalCount"]:
        raise ValueError(f"Incomplete reviews for PR #{node['number']}")


def fetch(kind: str) -> None:
    connection = "pullRequests" if kind == "pulls" else "issues"
    object_name = "pullRequest" if kind == "pulls" else "issue"
    filename = "pr_details.json" if kind == "pulls" else "issue_details.json"
    checkpoint = RAW / f"{kind}_checkpoint.jsonl"
    nodes, cursor, done = [], None, False
    if checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            page = json.loads(line)
            nodes.extend(page["nodes"])
            cursor, done = page["cursor"], page["done"]
        print(f"{kind}: resuming with {len(nodes)} objects", flush=True)
    fields = f"number url createdAt closedAt author{{{ACTOR}}} authorAssociation "
    if kind == "pulls":
        fields += f"mergedAt mergedBy{{{ACTOR}}} reviews(first:50){{totalCount {PAGE} nodes{{{REVIEW}}}}} "
    else:
        fields += "stateReason "
    fields += f"{TIMELINE},first:10){{{PAGE} nodes{{{EVENT}}}}}"
    while not done:
        after = f",after:{json.dumps(cursor)}" if cursor else ""
        query = (f'query{{repository(owner:"{OWNER}",name:"{REPO}"){{'
                 f'{connection}(first:50,orderBy:{{field:CREATED_AT,direction:ASC}}{after})'
                 f'{{{PAGE} nodes{{{fields}}}}}}} rateLimit{{cost remaining}}}}')
        data = run(query)
        block = data["repository"][connection]
        batch = [n for n in block["nodes"] if n["createdAt"] <= END_DATE]
        done = len(batch) < len(block["nodes"]) or not block["pageInfo"]["hasNextPage"]
        for node in batch:
            if kind == "pulls":
                complete_connection(node, object_name, "reviews", "reviews(", REVIEW)
            complete_connection(node, object_name, "timelineItems", TIMELINE + ",", EVENT)
        cursor = block["pageInfo"]["endCursor"]
        with checkpoint.open("a") as stream:
            stream.write(json.dumps({"nodes": batch, "cursor": cursor, "done": done}) + "\n")
        nodes.extend(batch)
        if len(nodes) % 500 == 0 or done:
            print(f"{kind}: {len(nodes)} objects; rate limit {data['rateLimit']['remaining']}", flush=True)
    path = RAW / filename
    if path.exists() and not path.with_suffix(".before_audit.json").exists():
        path.with_suffix(".before_audit.json").write_bytes(path.read_bytes())
    temp = path.with_suffix(".json.part")
    temp.write_text(json.dumps(nodes))
    temp.replace(path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with (RAW / "fetch_log.md").open("a") as log:
        log.write(f"| `{filename}` | `fetch_graphql.py {kind}`; created <= {END_DATE}; "
                  f"all review and close/reopen pages, actor types | {len(nodes)} | {now} |\n")
    print(f"{kind}: saved {path.name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kinds", nargs="*", choices=("pulls", "issues"))
    args = parser.parse_args()
    for kind in args.kinds or ("pulls", "issues"):
        fetch(kind)
