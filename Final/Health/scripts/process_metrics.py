"""Reproduce v4's response coverage, review coverage and day-30 outcomes."""
import json

import pandas as pd

from activity import OUTPUT, PROJECT_ROOT, human_activity
from config import END_DATE

RESPONSES = ("comment", "review_comment", "review")


def read_activity():
    frame = pd.read_csv(PROJECT_ROOT / "data/processed/activity.csv", low_memory=False)
    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
    if frame.created_at.max() > pd.Timestamp(END_DATE):
        raise ValueError("Activity contains post-cutoff events")
    return frame


def measure(activity):
    human = human_activity(activity)
    first_pr = human[human.kind.eq("pull_request")].groupby("login").created_at.min()
    grouped = dict(tuple(activity.groupby("object_url", sort=False)))
    openings = human[human.in_window & human.kind.isin(("pull_request", "issue"))]
    rows = []
    for opening in openings.itertuples():
        events = grouped[opening.object_url].sort_values("created_at", kind="stable")
        events = events[events.created_at.ge(opening.created_at)]
        day30 = opening.created_at + pd.Timedelta(days=30)
        responses = events[events.kind.isin(RESPONSES) & events.actor_class.eq("human")
                           & ~events.scripted & events.login.ne(opening.login)]
        first = responses.iloc[0] if len(responses) else None
        reviews = responses[responses.kind.eq("review")]
        first_review = reviews.iloc[0] if len(reviews) else None
        merges = events[events.kind.eq("pull_request_merged")]
        merged_at = merges.created_at.min()
        state = "open"
        for event in events[events.created_at.le(day30)].itertuples():
            if event.kind == "pull_request_merged":
                state = "merged"
                break
            if event.kind.endswith("reopened"):
                state = "open"
            elif event.kind in ("pull_request_closed_unmerged", "issue_closed"):
                state = "closed_unmerged" if opening.kind == "pull_request" else "closed"
        complete = opening.outcome != "unknown"
        rows.append({"kind": opening.kind, "url": opening.object_url, "author": opening.login,
            "opened_at": opening.created_at, "eligible_30d": day30 <= pd.Timestamp(END_DATE),
            "first_observed_pr": opening.kind == "pull_request" and opening.created_at == first_pr.get(opening.login),
            "complete_history": complete, "state_30d": state if complete else "unknown",
            "first_response_at": first.created_at if first is not None else pd.NaT,
            "first_response_url": first.url if first is not None else "",
            "response_7d": first is not None and first.created_at <= opening.created_at + pd.Timedelta(days=7),
            # Count reviews after closure/reopening too: v4 does not censor at the first decision.
            "human_review_30d": first_review is not None and first_review.created_at <= day30,
            "first_review_at": first_review.created_at if first_review is not None else pd.NaT,
            "first_review_url": first_review.url if first_review is not None else "",
            "merged_at": merged_at,
            "premerge_human_review": bool(reviews.created_at.le(merged_at).any())})
    return pd.DataFrame(rows)


def summarize(objects):
    mature = objects[objects.eligible_30d]
    prs = mature[mature.kind.eq("pull_request")]
    groups = (("first_pr", prs[prs.first_observed_pr]), ("repeat_pr", prs[~prs.first_observed_pr]),
              ("issue", mature[mature.kind.eq("issue")]))
    rows = []
    for name, group in groups:
        row = {"group": name, "n": len(group)}
        for key in ("response_7d", "human_review_30d"):
            row[key] = int(group[key].sum())
            row[key + "_percent"] = round(100 * group[key].mean(), 1)
        for state in ("merged", "closed_unmerged", "closed", "open", "unknown"):
            count = int(group.state_30d.eq(state).sum())
            row[state + "_30d"] = count
            row[state + "_30d_percent"] = round(100 * count / len(group), 1)
        rows.append(row)
    merged = objects[objects.kind.eq("pull_request") & objects.merged_at.notna()]
    return pd.DataFrame(rows), {"merged_prs": len(merged),
        "with_prior_human_review": int(merged.premerge_human_review.sum()),
        "reviewed_percent": round(100 * merged.premerge_human_review.mean(), 1)}


def main():
    objects = measure(read_activity())
    summary, merged = summarize(objects)
    objects.to_csv(OUTPUT / "process_objects.csv", index=False)
    summary.to_csv(OUTPUT / "process_summary.csv", index=False)
    (OUTPUT / "premerge_review.json").write_text(json.dumps(merged, indent=2) + "\n")
    print(summary.to_string(index=False))
    print("Pre-merge review:", merged)


if __name__ == "__main__":
    main()
