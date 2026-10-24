"""Match the report's policy and stale messages to closures within two minutes."""
import pandas as pd

from activity import OUTPUT, RAW, human_activity, load_records
from config import START_DATE, END_DATE
from process_metrics import read_activity

PATTERNS = {
    "help_wanted_policy": ("pull_request", "This pull request is being closed as it has been open for 14 days without a 'help wanted' designation."),
    "stale_issue": ("issue", "closed due to 14 additional days of inactivity"),
}


def match(activity, objects, comments):
    openings = objects.set_index("url")
    authors = openings.author.to_dict()
    kinds = openings.kind.to_dict()
    closes = activity[activity.kind.isin(("pull_request_closed_unmerged", "issue_closed"))]
    closing = dict(tuple(closes.groupby("object_url")))
    human = human_activity(activity)
    replies = human[human.kind.isin(("comment", "review_comment", "review"))]
    responses = dict(tuple(replies.groupby("object_url")))
    rows = []
    for comment in comments:
        date = pd.Timestamp(comment["created_at"])
        if not pd.Timestamp(START_DATE) <= date <= pd.Timestamp(END_DATE):
            continue
        url = comment["html_url"].split("#")[0]
        if url not in authors or url not in closing:
            continue
        for family, (kind, text) in PATTERNS.items():
            if kinds[url] != kind or text not in (comment.get("body") or ""):
                continue
            candidates = closing[url]
            near = candidates[candidates.created_at.between(date, date + pd.Timedelta(seconds=120))]
            if near.empty:
                continue
            event = near.sort_values("created_at", kind="stable").iloc[0]
            prior = responses.get(url)
            has_response = prior is not None and bool((prior.login.ne(authors[url])
                & prior.created_at.ge(openings.loc[url, "opened_at"])
                & prior.created_at.lt(event.created_at)).any())
            rows.append({"family": family, "url": url, "comment_url": comment["html_url"],
                "comment_at": date, "close_event_url": event.url, "closed_at": event.created_at,
                "closer": event.login, "closer_class": event.actor_class,
                "without_prior_human_response": not has_response})
    return pd.DataFrame(rows).drop_duplicates(["family", "url", "closed_at"])


def main():
    objects = pd.read_csv(OUTPUT / "process_objects.csv")
    objects["opened_at"] = pd.to_datetime(objects.opened_at, utc=True)
    matched = match(read_activity(), objects, load_records(RAW / "issue_comments.json"))
    matched.to_csv(OUTPUT / "automated_closure_matches.csv", index=False)
    summary = matched.groupby("family").agg(events=("url", "size"), objects=("url", "nunique"),
        without_prior_human_response=("without_prior_human_response", "sum"))
    summary["without_prior_human_response_percent"] = (100 * summary.without_prior_human_response / summary.events).round(1)
    summary.to_csv(OUTPUT / "automated_closure_summary.csv")
    print(summary.to_string())


if __name__ == "__main__":
    main()
