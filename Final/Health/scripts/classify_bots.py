#!/usr/bin/env python3
"""Classify every account active in the window as bot / human / borderline.

Three measures (session 5, "Identifying bots"; "Combination works best"):

1. Identity  - GitHub account type and bot naming conventions, reusing the
               interim report's ``detect_bots.classify_actor``.
2. Behaviour - share of an account's texts (commit messages, PR/issue bodies,
               comments) that are near-identical copies ("templated"), plus the
               number of distinct activity types.
3. Project configuration - accounts that the repository's own ``.github``
               configuration runs as automation (source paths listed below).

Accounts where the measures disagree are borderline; their final verdict comes
from ``evidence/bot_manual_decisions.csv``.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from events import PROJECT_ROOT, RAW, KINDS, load_events, load_records
from config import END_DATE, START_DATE

sys.path.insert(1, str(PROJECT_ROOT.parents[1] / "Interim" / "Contributor_Collaboration"))
from scripts.detect_bots import classify_actor

OUTPUT = PROJECT_ROOT / "output" / "bot_classification.csv"
MANUAL = PROJECT_ROOT / "evidence" / "bot_manual_decisions.csv"

# Measure 2 parameters used in the final report.
MIN_TEXT_LENGTH = 30   # shorter texts are mostly commands ("/assign") or "+1"
MIN_TEXTS = 10         # fewer texts are too little evidence to call a template
TEMPLATED_THRESHOLD = 0.6
# Scripted activity inside human accounts: the same normalized text posted at
# least this many times by one account within one minute.
BURST_SIZE = 5
SCRIPTED_OUTPUT = PROJECT_ROOT / "output" / "scripted_activity.csv"

# Measure 3: automation identities set up in the repository's own .github
# configuration at the window-end commit 9450ade797302e7c89e13423271aabdea74c7abb.
CONFIGURED_AUTOMATION = {
    "gemini-cli-robot": ".github/actions/publish-release/action.yml#L82-L83",
    "gemini-cli[bot]": ".github/workflows/gemini-cli-bot-brain.yml#L279-L280",
    "github-actions[bot]": ".github/workflows/pr-size-labeler.yml#L110",
    "dependabot[bot]": ".github/dependabot.yml",
}


def in_window(timestamp: str | None) -> bool:
    return bool(timestamp) and START_DATE <= timestamp <= END_DATE


def normalize(text: str) -> str:
    """Remove the parts that vary inside a template (links, names, numbers)."""

    text = text.lower()
    text = re.sub(r"https?://\S+", "<url>", text)
    text = re.sub(r"@[\w/-]+", "<user>", text)
    text = re.sub(r"\b[0-9a-f]{7,40}\b", "<sha>", text)
    text = re.sub(r"\d+", "<n>", text)
    return re.sub(r"\s+", " ", text).strip()[:200]


# Preserve the original column names while covering the additional activity types.
ACTIVITY_COLUMNS = ("commits", "pull_requests", "issues", "issue_comments", "review_comments",
                    "reviews", "pull_requests_merged", "pull_requests_closed_unmerged",
                    "issues_closed", "pull_requests_reopened", "issues_reopened")
COLUMN_BY_KIND = dict(zip(KINDS, ACTIVITY_COLUMNS))


def iter_activity():
    """Use the same normalized observations as the activity analysis."""
    frame = load_events()
    for row in frame[frame["in_window"] & frame["login"].notna()].itertuples():
        yield ({"login": row.login, "type": row.account_type}, COLUMN_BY_KIND[row.kind],
               row.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"), row.url, row.text)


def collect_activity(activity=None) -> tuple[dict, dict, dict]:
    """Return per-login texts, activity counts per type, and account type."""

    texts: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, Counter] = defaultdict(Counter)
    account_type: dict[str, str | None] = {}
    for user, kind, _, _, text in (activity if activity is not None else iter_activity()):
        login = user["login"]
        texts[login].append(text)
        counts[login][kind] += 1
        account_type[login] = user.get("type")
    return texts, counts, account_type


def templated_share(texts: list[str]) -> tuple[float | None, int, str]:
    """Share of long-enough texts whose normalized form occurs more than once."""

    long_texts = [normalize(t) for t in texts if len(t.strip()) >= MIN_TEXT_LENGTH]
    if len(long_texts) < MIN_TEXTS:
        return None, len(long_texts), ""
    repeated = Counter(long_texts)
    share = sum(n for n in repeated.values() if n > 1) / len(long_texts)
    return share, len(long_texts), repeated.most_common(1)[0][0]


def verdict(m1: str, m1_reason: str, m2: bool | None, m3: bool) -> tuple[str, str]:
    """Combine the measures; disagreement means borderline (manual check)."""

    if m1 == "organization":
        return "organization", "not attributable to one person"
    if m3:
        return "bot", "confirmed by repository configuration"
    if m1 == "bot" and m1_reason == "GitHub account type is Bot":
        return "bot", "GitHub marks the account as an app (type Bot)"
    if m1 == "bot" and m2:
        return "bot", "bot name and templated behaviour"
    if m1 == "bot":
        return "borderline", "bot-like name but no templated behaviour"
    if m2:
        return "borderline", "human account type but templated behaviour"
    if m1 == "uncertain":
        return "borderline", "no account metadata"
    return "human", "no measure fired"


def scripted_activity(human_logins: set[str], activity=None) -> pd.DataFrame:
    """Items a human account posted in bursts of identical text (>= BURST_SIZE per minute)."""

    rows = [
        {"github_login": user["login"], "kind": kind, "created_at": created, "url": url,
         "minute": created[:16], "normalized_text": normalize(text)}
        for user, kind, created, url, text in (activity if activity is not None else iter_activity())
        if user["login"] in human_logins and len(text.strip()) >= MIN_TEXT_LENGTH
    ]
    frame = pd.DataFrame(rows)
    size = frame.groupby(["github_login", "minute", "normalized_text"])["url"].transform("size")
    return frame[size >= BURST_SIZE].drop(columns="minute").sort_values(["github_login", "created_at"])


def main() -> None:
    activity = list(iter_activity())
    texts, counts, account_type = collect_activity(activity)
    manual = pd.read_csv(MANUAL).set_index("github_login") if MANUAL.is_file() else None

    rows = []
    for login in sorted(texts, key=str.casefold):
        m1, m1_reason = classify_actor(login, account_type[login])
        if account_type[login] == "Organization":
            m1, m1_reason = "organization", "GitHub account type is Organization"
        share, n_long, top_text = templated_share(texts[login])
        m2 = None if share is None else share >= TEMPLATED_THRESHOLD
        m3 = login in CONFIGURED_AUTOMATION
        auto, reason = verdict(m1, m1_reason, m2, m3)
        final, confidence, spam, final_reason = auto, "measures agree", False, reason
        if auto != "organization" and manual is not None and login in manual.index:
            decision = manual.loc[login]
            final = decision["automation"]
            confidence = decision["confidence"] if isinstance(decision["confidence"], str) else ""
            spam = decision["spam"] == "yes"
            final_reason = f"manual: {decision['reason']}"
        rows.append({
            "github_login": login,
            "account_type": account_type[login],
            **{k: counts[login][k] for k in ACTIVITY_COLUMNS},
            "activity_types": len(counts[login]),
            "m1_identity": m1,
            "m1_reason": m1_reason,
            "m2_texts_considered": n_long,
            "m2_templated_share": None if share is None else round(share, 3),
            "m2_templated": m2,
            "m2_most_repeated_text": top_text[:120],
            "m3_configured": m3,
            "m3_evidence": CONFIGURED_AUTOMATION.get(login, ""),
            "automatic_verdict": auto,
            "automatic_reason": reason,
            "final": final,
            "confidence": confidence,
            "spam": spam,
            "final_reason": final_reason,
            # Uncertain accounts stay in, as in the interim: only remove what is shown to be a bot.
            "include_as_human": final in ("human", "uncertain") and not spam,
        })

    frame = pd.DataFrame(rows)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(frame)} accounts to {OUTPUT}")
    print(frame["automatic_verdict"].value_counts().to_string())
    print("final:", frame["final"].value_counts().to_dict(), "| spam:", int(frame["spam"].sum()),
          "| included as human:", int(frame["include_as_human"].sum()))
    scripted = scripted_activity(set(frame.loc[frame["include_as_human"], "github_login"]), activity)
    scripted.to_csv(SCRIPTED_OUTPUT, index=False)
    print(f"Wrote {len(scripted)} scripted items from {scripted['github_login'].nunique()} "
          f"human accounts to {SCRIPTED_OUTPUT}")
    open_cases = frame[frame["final"] == "borderline"]
    if len(open_cases):
        print(f"{len(open_cases)} borderline accounts without a manual decision:")
        print(open_cases[["github_login", "account_type", "m1_identity", "m2_templated_share",
                          "activity_types", "automatic_reason"]].to_string(index=False))
        raise SystemExit("Resolve these cases in evidence/bot_manual_decisions.csv before continuing")


if __name__ == "__main__":
    main()
