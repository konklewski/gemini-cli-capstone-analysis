#!/usr/bin/env python3
"""Manual-check helper: write an evidence sheet per account.

Usage (from Final/Health/): .venv/bin/python scripts/inspect_account.py LOGIN [LOGIN ...]
Writes evidence/account_checks/<login>.md with:
  - GitHub profile (and GitHub App registry entry for app accounts),
  - activity per type in the window,
  - timing: distinct UTC hours, busiest minute and second (session 5: "timing"),
  - most repeated normalized text (Measure 2) and three random sample posts,
  - public activity in other repositories (session 5: "activity across projects").
Profile and public events are live API data (events cover only the last 90 days),
so each sheet records its fetch time.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_bots import PROJECT_ROOT, iter_activity, normalize  # noqa: E402

OUT = PROJECT_ROOT / "evidence" / "account_checks"


def gh(path: str):
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return json.loads(result.stdout) if result.returncode == 0 else None


def busiest(timestamps: list[str], length: int) -> tuple[str, int]:
    """Busiest time bucket: length 16 = minute, 19 = second (ISO prefix)."""
    if not timestamps:
        return "-", 0
    return Counter(t[:length] for t in timestamps).most_common(1)[0]


def sheet(login: str, items: list[tuple]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"# {login}", "", f"Generated {now} by `scripts/inspect_account.py`.", ""]

    profile = gh(f"users/{login.removesuffix('[bot]')}") or {}
    lines += ["## Profile (live)", "",
              f"- type: {profile.get('type')}, created: {str(profile.get('created_at'))[:10]}, "
              f"public repos: {profile.get('public_repos')}, followers: {profile.get('followers')}",
              f"- name: {profile.get('name')}, bio: {profile.get('bio')}",
              f"- {profile.get('html_url', 'https://github.com/' + login)}"]
    if login.endswith("[bot]"):
        app = gh(f"apps/{login.removesuffix('[bot]')}") or {}
        lines.append(f"- GitHub App owner: {(app.get('owner') or {}).get('login')}, "
                     f"description: {str(app.get('description'))[:120]!r}")

    times = sorted(created for _, _, created, _, _ in items)
    kinds = Counter(kind for _, kind, _, _, _ in items)
    minute, per_minute = busiest(times, 16)
    second, per_second = busiest(times, 19)
    lines += ["", "## Activity in window (17 Sep 2025 – 17 Sep 2026)", "",
              f"- items: {len(items)} — {dict(kinds)}",
              f"- distinct UTC hours with activity: {len({t[11:13] for t in times})}/24",
              f"- busiest minute: {minute} ({per_minute} items); busiest second: {second} ({per_second} items)"]

    repeated = Counter(normalize(text) for *_, text in items if len(text.strip()) >= 30)
    if repeated:
        top, count = repeated.most_common(1)[0]
        example = next(url for *_, url, text in items if normalize(text) == top)
        lines += [f"- most repeated text (normalized, x{count}): {top[:150]!r}", f"  e.g. {example}"]

    lines += ["", "## Random sample (seed 1)", ""]
    for _, kind, created, url, text in random.Random(1).sample(items, min(3, len(items))):
        lines.append(f"- {created} {kind} {url}\n  {' '.join(text.split())[:200]!r}")

    events = gh(f"users/{login}/events/public?per_page=100") or []
    lines += ["", "## Public activity elsewhere (live, last 90 days)", ""]
    if events:
        ev_second, ev_per_second = busiest(sorted(e["created_at"] for e in events), 19)
        lines += [f"- {len(events)} events; types: {dict(Counter(e['type'] for e in events))}",
                  f"- repositories: {sorted({e['repo']['name'] for e in events})[:8]}",
                  f"- busiest second: {ev_second} ({ev_per_second} events)"]
    else:
        lines.append("- no public events")
    return "\n".join(lines) + "\n"


def main() -> None:
    logins = set(sys.argv[1:])
    if not logins:
        raise SystemExit(__doc__)
    items: dict[str, list[tuple]] = {login: [] for login in logins}
    for row in iter_activity():
        if row[0]["login"] in logins:
            items[row[0]["login"]].append(row)
    OUT.mkdir(parents=True, exist_ok=True)
    for login in sorted(logins):
        (OUT / f"{login}.md").write_text(sheet(login, items[login]))
        print(f"Wrote {OUT / (login + '.md')}")


if __name__ == "__main__":
    main()
