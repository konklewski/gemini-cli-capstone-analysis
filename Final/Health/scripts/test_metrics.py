"""Small synthetic cases for consequential date and population definitions.

Run: .venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
"""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from activity import actor_login, is_merge_closure, load_activity, state_at
from involvement import build, newcomer_returns
from classify_bots import collect_activity, iter_activity, verdict


def event(login, kind, date):
    return {"login": login, "kind": kind, "created_at": pd.Timestamp(date, tz="UTC"),
            "actor_class": "human", "scripted": False, "in_window": date >= "2025-09-17"}


class MetricDefinitions(unittest.TestCase):
    def test_reviews_and_decisions_enter_the_classification_population(self):
        frame = pd.DataFrame([
            {"login": "reviewer", "account_type": "User", "kind": "review", "in_window": True,
             "created_at": pd.Timestamp("2026-09-01", tz="UTC"), "url": "https://x/review/1", "text": ""},
            {"login": "closer", "account_type": "User", "kind": "issue_closed", "in_window": True,
             "created_at": pd.Timestamp("2026-09-01", tz="UTC"), "url": "https://x/issue/1", "text": ""}])
        with patch("classify_bots.load_events", return_value=frame):
            texts, counts, types = collect_activity(list(iter_activity()))
        self.assertEqual(set(texts), {"reviewer", "closer"})
        self.assertEqual(counts["reviewer"]["reviews"], 1)
        self.assertEqual(counts["closer"]["issues_closed"], 1)
        self.assertEqual(types["reviewer"], "User")
        self.assertEqual(verdict("organization", "type", None, False)[0], "organization")

    def test_window_actor_cannot_bypass_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame(columns=["github_login", "final", "include_as_human", "spam"]).to_csv(root / "bot_classification.csv", index=False)
            pd.DataFrame(columns=["alias", "canonical"]).to_csv(root / "identity_map.csv", index=False)
            pd.DataFrame(columns=["url"]).to_csv(root / "scripted_activity.csv", index=False)
            frame = pd.DataFrame([{"login": "new-reviewer", "account_type": "User", "in_window": True,
                                   "kind": "review", "text": "", "url": "https://x/review/1"}])
            with patch("activity.OUTPUT", root), patch("activity.load_events", return_value=frame):
                with self.assertRaisesRegex(ValueError, "new-reviewer"):
                    load_activity()

    def test_future_merge_does_not_change_cutoff_outcome(self):
        item = {"mergedAt": "2026-10-01T00:00:00Z", "timelineItems": {"nodes": []}}
        self.assertEqual(state_at(item), "open")
        item["timelineItems"]["nodes"] = [{"__typename": "ClosedEvent", "createdAt": "2026-09-01T00:00:00Z"}]
        self.assertEqual(state_at(item), "closed")

    def test_reopened_after_cutoff_was_closed_at_cutoff(self):
        item = {"timelineItems": {"nodes": [
            {"__typename": "ReopenedEvent", "createdAt": "2026-09-20T00:00:00Z"},
            {"__typename": "ClosedEvent", "createdAt": "2026-09-01T00:00:00Z"}]}}
        self.assertEqual(state_at(item), "closed")
        self.assertEqual(state_at(item, "2026-09-25T00:00:00Z"), "open")

    def test_closed_metadata_without_timeline_is_not_reported_open(self):
        item = {"closedAt": "2026-09-10T00:00:00Z", "timelineItems": {"nodes": []}}
        self.assertEqual(state_at(item), "closed")
        self.assertEqual(state_at(item, "2026-09-01T00:00:00Z"), "open")

    def test_bot_normalization_requires_bot_type(self):
        self.assertEqual(actor_login({"login": "robot", "__typename": "Bot"}), "robot[bot]")
        self.assertEqual(actor_login({"login": "robot", "__typename": "User"}), "robot")
        self.assertEqual(actor_login({"login": "robot[bot]", "__typename": "Bot"}), "robot[bot]")
        self.assertEqual(actor_login({"login": "copilot-pull-request-reviewer", "__typename": "Bot"},
                                     {"copilot-pull-request-reviewer": "Copilot"}), "Copilot")
        self.assertIsNone(actor_login(None))

    def test_merge_closure_one_second_later_is_not_a_rejection(self):
        item = {"mergedAt": "2026-06-01T12:00:00Z"}
        self.assertTrue(is_merge_closure(item, {"__typename": "ClosedEvent", "createdAt": "2026-06-01T12:00:01Z"}))
        self.assertFalse(is_merge_closure(item, {"__typename": "ClosedEvent", "createdAt": "2026-05-01T12:00:00Z"}))

    def test_reviews_and_self_merges_prevent_false_dormancy(self):
        activity = pd.DataFrame([
            event("reviewer", "issue", "2025-10-01"), event("reviewer", "review_comment", "2026-02-01"),
            event("reviewer", "review", "2026-09-03"), event("merger", "pull_request", "2025-11-01"),
            event("merger", "pull_request_merged", "2026-09-01")])
        people, monthly = build(activity)
        self.assertFalse(people.loc["reviewer", "dormant"])
        self.assertTrue(people.loc["merger", "observed_integrator"])
        self.assertEqual(monthly.loc["2026-09", "pull_request_merged"], 1)
        self.assertEqual(monthly.loc["2025-11", "pull_request_merged"], 0)
        self.assertEqual(monthly.loc["2026-09", "resumed_from_dormant"], 1)
        self.assertEqual(monthly.iloc[-1]["dormant_at_boundary"], people["dormant"].sum())

    def test_old_authorship_prevents_false_newcomer_and_returns_are_distinct(self):
        activity = pd.DataFrame([
            event("old", "commit", "2025-06-01"), event("old", "issue", "2026-08-01"),
            event("new", "comment", "2026-06-01"), event("new", "issue", "2026-07-01"),
            event("new", "pull_request", "2026-07-01T12:00:00"),
            event("new", "review", "2026-07-02"), event("late", "issue", "2026-09-10")])
        people, monthly = build(activity)
        self.assertFalse(people.loc["old", "newcomer"])
        returns = newcomer_returns(activity, people).set_index("login")
        self.assertTrue(returns.loc["new", "returned_any_later_day"])
        self.assertFalse(returns.loc["new", "returned_authored_later_day"])
        self.assertTrue(returns.loc["new", "eligible_30d"])
        self.assertFalse(returns.loc["late", "eligible_30d"])
        self.assertTrue(returns.loc["new", "prior_observed_participation"])
        self.assertEqual(int(monthly["first_seen_in_window"].sum()), len(people))
        self.assertTrue((monthly["active_people"] == monthly[["first_seen_in_window", "retained_from_previous_month", "returning_after_gap"]].sum(axis=1)).all())

    def test_alias_history_survives_filtering_and_unknown_actor_survives_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame([{"github_login": login, "include_as_human": True, "spam": False, "final": "human"}
                          for login in ("Alice", "organization")]).to_csv(root / "bot_classification.csv", index=False)
            pd.DataFrame([{"alias": "old-alice", "canonical": "Alice"}]).to_csv(root / "identity_map.csv", index=False)
            pd.DataFrame(columns=["url"]).to_csv(root / "scripted_activity.csv", index=False)
            for name in ("pr_details", "issue_details"):
                (root / f"{name}.json").write_text(json.dumps([]))
            sources = {name: [] for name in ("pull_requests", "issues", "issue_comments", "review_comments")}
            sources["commits"] = [
                {"sha": "a", "author": {"login": "old-alice", "type": "User"},
                 "commit": {"message": "Commit message", "author": {"date": "2025-06-01T00:00:00Z"}}, "html_url": "https://x/commit/a"},
                {"sha": "b", "author": None,
                 "commit": {"message": "Commit message", "author": {"date": "2026-06-01T00:00:00Z"}}, "html_url": "https://x/commit/b"},
                {"sha": "c", "author": {"login": "organization", "type": "Organization"},
                 "commit": {"message": "Commit message", "author": {"date": "2026-06-01T00:00:00Z"}}, "html_url": "https://x/commit/c"}]
            with patch("activity.OUTPUT", root), patch("events.RAW", root), \
                 patch("events.unlinked_commit_authors", return_value={}), \
                 patch("events.load_records", side_effect=lambda p: sources[p.stem]):
                result = load_activity()
            self.assertEqual(len(result), 3)
            self.assertEqual(result.iloc[0]["login"], "Alice")
            self.assertEqual(result.iloc[0]["actor_class"], "human")
            self.assertEqual(result.iloc[1]["actor_class"], "unattributed")
            self.assertEqual(result.iloc[2]["actor_class"], "organization")


if __name__ == "__main__":
    unittest.main()
