"""Reproduce the original eight stratified cases and two targeted checks."""
import json

import pandas as pd

from activity import OUTPUT, PROJECT_ROOT, RAW, load_records
from config import END_DATE

SEED = 20261016


def select(objects):
    mature = objects[objects.eligible_30d & objects.complete_history]
    prs = mature[mature.kind.eq("pull_request")]
    rows = []

    def draw(pool, stratum, selection="stratified_random"):
        row = pool.sort_values("url").sample(n=1, random_state=SEED).iloc[0].to_dict()
        row.update(selection=selection, stratum=stratum, seed=SEED, pool_size=len(pool))
        rows.append(row)

    for first in (True, False):
        for state in ("merged", "closed_unmerged", "open"):
            draw(prs[prs.first_observed_pr.eq(first) & prs.state_30d.eq(state)],
                 f"firstPR={first}; state30={state}")
    issues = mature[mature.kind.eq("issue")]
    for response in (True, False):
        draw(issues[issues.response_7d.eq(response)], f"issue_response7={response}")
    target = objects[objects.url.eq("https://github.com/google-gemini/gemini-cli/pull/16881")]
    if len(target) != 1:
        raise ValueError("Expected the recorded scripted-closure example")
    row = target.iloc[0].to_dict()
    row.update(selection="targeted", stratum="Jan23 scripted closure", seed=None, pool_size=None)
    rows.append(row)
    gap = objects[objects.kind.eq("pull_request") & objects.merged_at.notna() & ~objects.premerge_human_review]
    draw(gap, "merged PR without prior human review", "targeted_random")
    sample = pd.DataFrame(rows)
    for column in ("seed", "pool_size"):
        sample[column] = sample[column].astype("Int64")
    return sample


def conversations(sample):
    urls = set(sample.url)
    openings = {r["html_url"]: r for name in ("pull_requests", "issues")
                for r in load_records(RAW / (name + ".json")) if r["html_url"] in urls
                and (name == "pull_requests" or "pull_request" not in r)}
    details = {r["url"]: r for name in ("pr_details", "issue_details")
               for r in json.loads((RAW / (name + ".json")).read_text()) if r["url"] in urls}
    texts = {url: [] for url in urls}
    for name, kind in (("issue_comments", "comment"), ("review_comments", "inline_comment")):
        for row in load_records(RAW / (name + ".json")):
            url = row["html_url"].split("#")[0]
            if url in urls and row["created_at"] <= END_DATE:
                texts[url].append({"kind": kind, "url": row["html_url"], "date": row["created_at"],
                    "author": (row.get("user") or {}).get("login"), "body": row.get("body") or ""})
    records = []
    for url in sorted(urls):
        raw, detail = openings[url], details[url]
        for review in detail.get("reviews", {}).get("nodes", []):
            if review["submittedAt"] and review["submittedAt"] <= END_DATE:
                texts[url].append({"kind": "review:" + review["state"], "url": review["url"],
                    "date": review["submittedAt"], "author": (review.get("author") or {}).get("login"),
                    "body": review["body"]})
        records.append({"url": url, "title": raw["title"], "author": raw["user"]["login"],
            "opened_at": raw["created_at"], "body": raw.get("body") or "",
            "labels_at_collection": [label["name"] for label in raw["labels"]],
            "merged_at": detail.get("mergedAt"),
            "timeline": [e for e in detail["timelineItems"]["nodes"] if e["createdAt"] <= END_DATE],
            "conversation": sorted(texts[url], key=lambda e: (e["date"], e["kind"]))})
    return records


if __name__ == "__main__":
    sample = select(pd.read_csv(OUTPUT / "process_objects.csv"))
    sample.to_csv(OUTPUT / "qualitative_sample.csv", index=False)
    (PROJECT_ROOT / "evidence/conversations.json").write_text(
        json.dumps(conversations(sample), indent=2, ensure_ascii=False) + "\n")
    print(sample[["selection", "stratum", "pool_size", "url"]].to_string(index=False))
