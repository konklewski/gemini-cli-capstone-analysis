#!/usr/bin/env python3
"""Apply bot and identity decisions to the shared event table.

Every named actor active in the window must have an account decision. Aliases
are resolved before filtering; unknown/deleted actors remain in total counts.
Earlier-only identities stay outside window person metrics but preserve the
history of known accounts. Run classify_bots.py, identify_accounts.py, then
involvement.py, all against the same saved exports.
"""
from __future__ import annotations

import pandas as pd

from events import (CONTRIBUTIONS, KINDS, OUTPUT, PROJECT_ROOT, RAW, actor_login,
                    is_merge_closure, load_events, load_records, state_at)


def load_activity() -> pd.DataFrame:
    frame = load_events()
    accounts = pd.read_csv(OUTPUT / "bot_classification.csv")
    registry = {r.github_login.casefold(): r for r in accounts.itertuples()}
    aliases = {r.alias.casefold(): r.canonical for r in
               pd.read_csv(OUTPUT / "identity_map.csv").itertuples()}
    scripted = set(pd.read_csv(OUTPUT / "scripted_activity.csv")["url"])
    frame["raw_login"] = frame["login"]
    frame["login"] = frame["login"].map(lambda login: aliases.get(login.casefold(), login) if login else None)
    status, sources = [], []
    for row in frame.itertuples():
        record = registry.get((row.login or "").casefold()) or registry.get((row.raw_login or "").casefold())
        if row.in_window and row.raw_login and record is None:
            raise ValueError(f"Unclassified window actor {row.raw_login}; rerun classify_bots.py")
        if not row.login or row.login == "ghost":
            group = "unattributed"
        elif row.account_type == "Organization":
            group = "organization"
        elif record is not None:
            group = "human" if record.include_as_human else ("spam" if record.spam else record.final)
        else:
            group = "outside_window_population"
        status.append(group)
        sources.append("account_classification" if record is not None else "unattributed_or_historical")
    frame["actor_class"] = status
    frame["classification_source"] = sources
    frame["scripted"] = frame["url"].isin(scripted)
    return frame.drop(columns=["text", "account_type"])


def human_activity(activity: pd.DataFrame) -> pd.DataFrame:
    return activity[activity["actor_class"].eq("human") & ~activity["scripted"]].copy()


if __name__ == "__main__":
    activity = load_activity()
    activity.to_csv(PROJECT_ROOT / "data" / "processed" / "activity.csv", index=False)
    print(activity[activity["in_window"]].groupby(["kind", "actor_class"]).size().to_string())
