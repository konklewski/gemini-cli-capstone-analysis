"""Regression cases for the report's observation horizons and reopened PRs."""
import unittest

import pandas as pd

from process_metrics import measure


class ProcessDefinitions(unittest.TestCase):
    def events(self, entries):
        rows = []
        for login, kind, date, actor, scripted in entries:
            rows.append({"login": login, "kind": kind, "created_at": pd.Timestamp(date, tz="UTC"),
                "actor_class": actor, "scripted": scripted, "in_window": True,
                "object_url": "https://example.org/pull/1", "url": f"https://example.org/event/{len(rows)}",
                "outcome": "open"})
        return pd.DataFrame(rows)

    def test_review_after_reopening_counts_within_thirty_days(self):
        rows = self.events([
            ("author", "pull_request", "2026-01-01", "human", False),
            ("closer", "pull_request_closed_unmerged", "2026-01-02", "bot", False),
            ("author", "pull_request_reopened", "2026-01-03", "human", False),
            ("reviewer", "review", "2026-01-04", "human", False)])
        result = measure(rows).iloc[0]
        self.assertTrue(result.human_review_30d)
        self.assertEqual(result.state_30d, "open")

    def test_only_another_unscripted_human_can_respond(self):
        rows = self.events([
            ("author", "pull_request", "2026-01-01", "human", False),
            ("author", "comment", "2026-01-02", "human", False),
            ("robot", "review", "2026-01-03", "bot", False),
            ("maintainer", "comment", "2026-01-04", "human", True),
            ("reviewer", "review", "2026-01-09", "human", False)])
        result = measure(rows).iloc[0]
        self.assertFalse(result.response_7d)
        self.assertTrue(result.human_review_30d)
        self.assertEqual(result.first_response_at, pd.Timestamp("2026-01-09", tz="UTC"))

    def test_thirty_day_status_uses_the_boundary_and_preserves_unknown(self):
        rows = self.events([
            ("author", "pull_request", "2026-01-01", "human", False),
            ("closer", "pull_request_closed_unmerged", "2026-01-31", "bot", False),
            ("author", "pull_request_reopened", "2026-02-01", "human", False)])
        self.assertEqual(measure(rows).iloc[0].state_30d, "closed_unmerged")
        rows.loc[0, "outcome"] = "unknown"
        self.assertEqual(measure(rows).iloc[0].state_30d, "unknown")

    def test_equal_timestamp_events_keep_timeline_order(self):
        rows = self.events([
            ("author", "pull_request", "2026-01-01", "human", False),
            ("author", "pull_request_reopened", "2026-01-02", "human", False),
            ("closer", "pull_request_closed_unmerged", "2026-01-02", "bot", False)])
        self.assertEqual(measure(rows).iloc[0].state_30d, "closed_unmerged")


if __name__ == "__main__":
    unittest.main()
