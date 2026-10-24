#!/usr/bin/env python3
"""Find accounts that may belong to the same person, and accounts used by several people.

Measures (session 5, "Do these accounts belong to the same person?"):

M1 Name/email similarity (git identities in all commits on main):
   a) one normalized git author name used by >= 2 logins
   b) one email used by >= 2 logins (GitHub links an email to one account, so expected 0)
   c) window commits without a GitHub login, matched to a login by name or email
M2 Login similarity: logins that are equal after removing separators, trailing
   digits and suffixes such as -alt / -google (human accounts active in the window).
M3 Self-declaration: texts in which someone says they use another GitHub account.
Shared-account candidates: logins whose commits carry >= 2 different emails and
   names. Separately flag `ghost`, an attribution placeholder for deleted users;
   it does not establish shared operation of an ordinary account.

Candidates are decided manually in evidence/identity_decisions.csv; confirmed
"same" decisions are written to output/identity_map.csv (alias -> canonical login).
"""

from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_bots import PROJECT_ROOT, RAW, in_window, iter_activity, load_records  # noqa: E402

CANDIDATES = PROJECT_ROOT / "output" / "identity_candidates.csv"
DECISIONS = PROJECT_ROOT / "evidence" / "identity_decisions.csv"
IDENTITY_MAP = PROJECT_ROOT / "output" / "identity_map.csv"

SUFFIX = re.compile(r"(google|goog|alt|work|dev|personal|official|gh|github)$")
SELF_DECLARATION = re.compile(
    r"(my (other|old|new|previous|personal|work|second|alt(ernate)?) github account"
    r"|github account,? not my|this account is no longer active|my previous account"
    r"|my new github account|alt(ernate)? account|opened accidentally from)",
    re.IGNORECASE,
)


def name_key(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", text)


def login_core(login: str) -> str:
    core = re.sub(r"[-_.]", "", login.lower())
    for _ in range(2):
        core = re.sub(r"\d+$", "", SUFFIX.sub("", core))
    return core


def main() -> None:
    accounts = pd.read_csv(PROJECT_ROOT / "output" / "bot_classification.csv")
    humans = set(accounts.loc[accounts["include_as_human"], "github_login"])
    commits = load_records(RAW / "commits.json")
    rows = []

    # M1 a/b: git identities per login over the full history of main.
    logins_by_name, logins_by_email = defaultdict(set), defaultdict(set)
    names_by_login, emails_by_login = defaultdict(set), defaultdict(set)
    unlinked = []
    for commit in commits:
        author = commit["commit"]["author"]
        login = (commit.get("author") or {}).get("login")
        if not login:
            if in_window(author["date"]):
                unlinked.append((author["name"], author["email"], commit["html_url"]))
            continue
        logins_by_name[name_key(author["name"])].add(login)
        logins_by_email[author["email"].lower()].add(login)
        names_by_login[login].add(author["name"])
        emails_by_login[login].add(author["email"].lower())
    for key, logins in logins_by_name.items():
        if len(logins) > 1 and len(key) > 3:
            rows.append({"measure": "M1a same git name", "logins": ";".join(sorted(logins)),
                         "evidence": key})
    for email, logins in logins_by_email.items():
        if len(logins) > 1:
            rows.append({"measure": "M1b same email", "logins": ";".join(sorted(logins)),
                         "evidence": email.split("@")[-1]})

    # M1 c: window commits whose email is not linked to any GitHub account.
    known = {login.lower(): login for login in accounts["github_login"]}
    for name, email, url in unlinked:
        local, domain = email.lower().split("@")
        surname = name_key(name.split()[-1]) if name.split() else ""
        matches = sorted({known[k] for k in known
                          if (len(surname) > 4 and surname in k) or k in (local, domain.split(".")[0])})
        rows.append({"measure": "M1c unlinked commit", "logins": ";".join(matches),
                     "evidence": f"{name} <@{domain}> {url}"})

    # M2: similar logins among human accounts active in the window.
    groups = defaultdict(list)
    for login in humans:
        groups[login_core(login)].append(login)
    for core, logins in groups.items():
        if len(logins) > 1 and len(core) >= 5:
            rows.append({"measure": "M2 similar login", "logins": ";".join(sorted(logins)),
                         "evidence": core})

    # M3: self-declared other accounts.
    for user, _, _, url, text in iter_activity():
        if user["login"] in humans and (match := SELF_DECLARATION.search(text)):
            rows.append({"measure": "M3 self-declaration", "logins": user["login"],
                         "evidence": f"{url} | ...{text[max(0, match.start() - 60):match.end() + 60]}..."})

    # Shared accounts.
    for login in humans & set(names_by_login):
        names = {name_key(n) for n in names_by_login[login]} - {name_key(login)}
        if len(names) > 1 and len(emails_by_login[login]) > 1:
            rows.append({"measure": "S shared: several names and emails", "logins": login,
                         "evidence": " | ".join(sorted(names_by_login[login]))})
    if "ghost" in humans:
        rows.append({"measure": "S shared: deleted users", "logins": "ghost",
                     "evidence": "GitHub placeholder for deleted accounts"})

    frame = pd.DataFrame(rows).drop_duplicates(["measure", "logins"]).sort_values(
        ["measure", "logins"], kind="stable").reset_index(drop=True)
    frame.to_csv(CANDIDATES, index=False)
    print(f"Wrote {len(frame)} candidates to {CANDIDATES}")
    print(frame["measure"].value_counts().to_string())

    if DECISIONS.is_file():
        decisions = pd.read_csv(DECISIONS)
        same = decisions[decisions["decision"] == "same person"]
        mapping = [{"alias": alias, "canonical": row["canonical"]}
                   for _, row in same.iterrows()
                   for alias in row["logins"].split(";") if alias != row["canonical"]]
        pd.DataFrame(mapping).to_csv(IDENTITY_MAP, index=False)
        print(f"Wrote {len(mapping)} alias mappings to {IDENTITY_MAP}")
        print(decisions["decision"].value_counts().to_string())


if __name__ == "__main__":
    main()
