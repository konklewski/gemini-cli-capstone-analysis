#!/usr/bin/env python3
"""Reconcile saved outputs with source records; fail before reporting bad totals.

Run after involvement.py: .venv/bin/python scripts/validate.py
These are population/data checks, separate from synthetic definition tests.
"""
import json

import pandas as pd

from activity import CONTRIBUTIONS, KINDS, OUTPUT, PROJECT_ROOT, RAW, load_records
from config import END_DATE, START_DATE
from classify_bots import COLUMN_BY_KIND


def main():
    activity = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "activity.csv", low_memory=False)
    people = pd.read_csv(OUTPUT / "people.csv", index_col="login")
    monthly = pd.read_csv(OUTPUT / "monthly_activity.csv", index_col="month")
    summary = json.loads((OUTPUT / "summary.json").read_text())
    merge_dates = activity[activity["kind"].eq("pull_request_merged")].set_index("object_url")["created_at"].to_dict()
    reviews, merges, timelines, objects = 0, 0, 0, 0
    expected_openings = {}
    for name in ("pr_details", "issue_details"):
        details = json.loads((RAW / f"{name}.json").read_text())
        kind = "pull_request" if name == "pr_details" else "issue"
        rest_name = "pull_requests" if name == "pr_details" else "issues"
        numbers = {d["number"] for d in details if START_DATE <= d["createdAt"] <= END_DATE}
        numbers |= {d["number"] for d in load_records(RAW / f"{rest_name}.json")
                    if (kind == "pull_request" or "pull_request" not in d)
                    and START_DATE <= d["created_at"] <= END_DATE}
        expected_openings[kind] = len(numbers)
        assert len({d["number"] for d in details}) == len(details), name
        for item in details:
            objects += 1
            assert not item["timelineItems"]["pageInfo"]["hasNextPage"], item["number"]
            timelines += len(item["timelineItems"]["nodes"])
            if name == "pr_details":
                connection = item["reviews"]
                assert not connection["pageInfo"]["hasNextPage"], item["number"]
                assert len(connection["nodes"]) == connection["totalCount"], item["number"]
                reviews += sum(bool(r["submittedAt"]) and START_DATE <= r["submittedAt"] <= END_DATE for r in connection["nodes"])
                if item["mergedAt"] and START_DATE <= item["mergedAt"] <= END_DATE:
                    merges += 1
                    assert merge_dates.get(item["url"]) == str(pd.Timestamp(item["mergedAt"])), item["number"]
    assert not activity.duplicated(["kind", "url"]).any()
    assert pd.to_datetime(activity["created_at"], utc=True).max() <= pd.Timestamp(END_DATE)
    window = activity[activity["in_window"]]
    accounts = pd.read_csv(OUTPUT / "bot_classification.csv")
    named = window[window["raw_login"].notna()]
    assert set(named["raw_login"].str.casefold()) == set(accounts["github_login"].str.casefold())
    assert named["classification_source"].eq("account_classification").all()
    assert not accounts["final"].eq("borderline").any()
    for kind, column in COLUMN_BY_KIND.items():
        assert int(accounts[column].sum()) == int(named["kind"].eq(kind).sum()), (kind, "classification / activity counts")
    flow = summary["population_flow"]
    assert flow["raw_named_accounts"] - flow["bot_accounts"] - flow["spam_accounts"] - flow["organization_accounts"] == flow["retained_accounts_before_aliases"]
    assert flow["retained_accounts_before_aliases"] - flow["active_alias_accounts_merged"] - flow["placeholder_accounts_excluded"] - flow["scripted_only_people_excluded"] == len(people)
    assert pd.read_csv(OUTPUT / "monthly_activity_by_actor.csv")["events"].sum() == len(window)
    assert pd.read_csv(OUTPUT / "activity_totals.csv", index_col="kind").to_numpy().sum() == len(window)
    for kind, count in expected_openings.items():
        assert int(window["kind"].eq(kind).sum()) == count, kind
    assert len(window[window["kind"].eq("review")]) == reviews
    assert len(window[window["kind"].eq("pull_request_merged")]) == merges
    human = window[window["actor_class"].eq("human") & ~window["scripted"]]
    assert human["login"].nunique() == len(people) == summary["participants"]
    assert "ghost" not in people.index
    for kind in KINDS:
        assert int(monthly[kind].sum()) == int(people[kind].sum()) == int(human["kind"].eq(kind).sum()), kind
    assert people["contributions"].equals(people[list(CONTRIBUTIONS)].sum(axis=1))
    assert (monthly["active_people"] == monthly[["first_seen_in_window", "retained_from_previous_month", "returning_after_gap"]].sum(axis=1)).all()
    assert monthly["first_seen_in_window"].sum() == len(people)
    assert monthly["newcomers"].sum() == people["newcomer"].sum()
    assert monthly.iloc[-1]["dormant_at_boundary"] == people["dormant"].sum()
    assert monthly.iloc[0]["observed_days"] == 14 and monthly.iloc[-1]["observed_days"] == 17
    assert monthly["observed_days"].sum() == 366
    # Independently recompute returns by a vectorized join, rather than the
    # per-person loop used to generate newcomer_returns.csv.
    history = activity[activity["actor_class"].eq("human") & ~activity["scripted"]].copy()
    history["time"] = pd.to_datetime(history["created_at"], utc=True)
    first = history[history["kind"].isin(CONTRIBUTIONS)].groupby("login")["time"].min()
    first = first[first.between(pd.Timestamp(START_DATE), pd.Timestamp(END_DATE))]
    assert set(first.index) == set(people.index[people["newcomer"]])
    followups = history.join(first.rename("first"), on="login")
    followups = followups[followups["time"].dt.normalize() > followups["first"].dt.normalize()]
    for kind in ("authored", "any"):
        actions = followups[followups["kind"].isin(CONTRIBUTIONS)] if kind == "authored" else followups
        for period in ("later_day", "30d"):
            eligible = first[first + pd.Timedelta(days=30) <= pd.Timestamp(END_DATE)] if period == "30d" else first
            selected = actions[actions["time"] <= actions["first"] + pd.Timedelta(days=30)] if period == "30d" else actions
            returned = set(selected["login"]) & set(eligible.index)
            recorded = summary["return_rates"][f"{kind}_{period}"]
            assert recorded["eligible"] == len(eligible) and recorded["returned"] == len(returned), (kind, period)
    concentration = pd.read_csv(OUTPUT / "concentration.csv")
    for row in concentration.itertuples():
        counts = people[row.kind].sort_values(ascending=False).to_numpy()
        for fraction, size in ((.5, row.people_for_50pct), (.8, row.people_for_80pct)):
            if counts.sum():
                assert counts[:size].sum() >= fraction * counts.sum()
                assert counts[:size - 1].sum() < fraction * counts.sum()
    # Previously reported concrete errors must stay fixed.
    for login in ("bdmorgan", "jkcinouye"):
        assert not people.loc[login, "dormant"], login
    print(f"PASS: {objects:,} objects, {timelines:,} close/reopen events; all review pages complete.")
    print(f"PASS: {reviews:,} window reviews and {merges:,} merges reconcile before filtering.")
    print(f"PASS: population {flow['raw_named_accounts']:,} raw accounts -> {flow['retained_accounts_before_aliases']:,} retained -> {len(people):,} people.")
    print(f"PASS: {len(people):,} people; activity totals, contributor flows, return rates, cutoffs and concentration reconcile.")


if __name__ == "__main__":
    main()
