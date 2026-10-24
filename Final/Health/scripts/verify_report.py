"""Check reproduced results against the explicit values and examples in v4."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from classify_bots import verdict
from activity import OUTPUT, PROJECT_ROOT, RAW, load_records
from config import START_DATE, END_DATE
from identify_accounts import SELF_DECLARATION
from process_metrics import read_activity


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(report=None):
    expected = json.loads((PROJECT_ROOT / "evidence/report_expectations.json").read_text())
    checks = []

    def check(name, actual, wanted):
        checks.append({"claim": name, "actual": actual, "expected": wanted, "pass": actual == wanted})

    if report is not None:
        check("source report checksum", sha256(report), expected["report"]["sha256"])
    manifest = json.loads((OUTPUT / "run_manifest.json").read_text())
    for name, digest in manifest["inputs_sha256"].items():
        check("input checksum: " + name, sha256(PROJECT_ROOT / name), digest)
    summary = json.loads((OUTPUT / "summary.json").read_text())
    check("analysis window", [START_DATE, END_DATE], expected["window"])
    people = pd.read_csv(OUTPUT / "people.csv", index_col="login")
    monthly = pd.read_csv(OUTPUT / "monthly_activity.csv", index_col="month")
    accounts = pd.read_csv(OUTPUT / "bot_classification.csv")
    totals = pd.read_csv(OUTPUT / "activity_totals.csv", index_col="kind")
    for key, wanted in expected["population"].items():
        check(key, summary[key], wanted)
    check("frequency bands", people.involvement_band.value_counts().to_dict(), expected["frequency_bands"])
    for kind, wanted in expected["human_activity"].items():
        check("human " + kind, int(totals.loc[kind, "human"]), wanted)
    for kind, wanted in expected["bot_shares_percent"].items():
        check("bot share " + kind, round(100 * totals.loc[kind, "bot"] / totals.loc[kind].sum()), wanted)
    bot = expected["bots"]
    check("raw accounts", len(accounts), bot["raw_accounts"])
    for group in ("human", "bot", "uncertain", "organization"):
        check(group + " accounts", int(accounts.final.eq(group).sum()), bot[group])
    check("probable bots", int((accounts.final.eq("bot") & accounts.confidence.eq("probable")).sum()), bot["probable_bots"])
    check("spam accounts", int(accounts.spam.sum()), bot["spam_accounts"])
    check("manual bot checks", len(pd.read_csv(PROJECT_ROOT / "evidence/bot_manual_decisions.csv")), bot["manual_checks"])
    eligible = accounts[accounts.account_type.eq("User") & accounts.m2_texts_considered.ge(10)]
    for name, actual in (("eligible_user_accounts", len(eligible)),
                         ("templated_median", round(eligible.m2_templated_share.median(), 2)),
                         ("templated_p95", round(eligible.m2_templated_share.quantile(.95), 2)),
                         ("templated_flags_at_0_6", int(eligible.m2_templated_share.ge(.6).sum()))):
        check(name, actual, bot[name])
    scripted = pd.read_csv(OUTPUT / "scripted_activity.csv")
    check("scripted messages", len(scripted), bot["scripted_messages"])
    check("scripted accounts", scripted.github_login.nunique(), bot["scripted_accounts"])
    by_login = accounts.set_index("github_login")
    check("robot PRs", int(by_login.loc["gemini-cli-robot", "pull_requests"]), bot["robot_prs"])
    check("robot template percent", round(100 * by_login.loc["gemini-cli-robot", "m2_templated_share"]), bot["robot_templated_percent"])
    check("google-admin PRs", int(by_login.loc["google-admin", "pull_requests"]), bot["admin_prs"])
    manual = pd.read_csv(PROJECT_ROOT / "evidence/bot_manual_decisions.csv").set_index("github_login")
    for threshold in (.7, .8):
        changes = 0
        for row in accounts.itertuples():
            m2 = None if pd.isna(row.m2_templated_share) else row.m2_templated_share >= threshold
            final = verdict(row.m1_identity, row.m1_reason, m2, row.m3_configured)[0]
            if final != "organization" and row.github_login in manual.index:
                final = manual.loc[row.github_login, "automation"]
            changes += int(final != row.final)
        check(f"classification changes at threshold {threshold}", changes, 0)
    candidates = pd.read_csv(OUTPUT / "identity_candidates.csv")
    decisions = pd.read_csv(PROJECT_ROOT / "evidence/identity_decisions.csv")
    identity = {"candidates": len(candidates), "cases": len(decisions),
        "alias_pairs": len(pd.read_csv(OUTPUT / "identity_map.csv")),
        "unlinked_commits": int(candidates.measure.eq("M1c unlinked commit").sum()),
        "different_people": int(decisions.decision.eq("different people").sum()),
        "uncertain": int(decisions.decision.eq("uncertain").sum()),
        "git_name_variants": int(decisions.decision.eq("one person").sum()),
        "placeholder": int(decisions.decision.eq("attribution placeholder").sum()),
        "git_name_groups": int(candidates.measure.eq("M1a same git name").sum()),
        "shared_email_groups": int(candidates.measure.eq("M1b same email").sum()),
        "login_similarity_groups": int(candidates.measure.eq("M2 similar login").sum()),
        "self_declaration_account_flags": int(candidates.measure.eq("M3 self-declaration").sum())}
    check("identity decisions", identity, expected["identities"])
    check("main-branch commits examined", len(load_records(RAW / "commits.json")), expected["main_commits_examined"])
    for months, wanted in expected["frequency_thresholds"].items():
        selected = people[people.months_active.ge(int(months))]
        actual = {"exact": int(people.months_active.eq(int(months)).sum()), "at_least": len(selected)}
        for key, kind in (("commit_percent", "commit"), ("pr_percent", "pull_request"), ("review_percent", "review")):
            if key in wanted:
                actual[key] = round(100 * selected[kind].sum() / people[kind].sum(), 2)
        check("frequency threshold " + months, actual, wanted)
    for days, wanted in expected["dormancy_thresholds"].items():
        check("dormancy threshold " + days, int((people.months_active.ge(2) & people.days_silent_at_end.gt(int(days))).sum()), wanted)
    for q, wanted in expected["frequent_day_gap_percentiles"].items():
        check("frequent gap percentile " + q, summary["inter_active_day_gaps"]["frequent"][q], wanted)
    check("newcomer entry types", summary["newcomer_first_kind"], expected["newcomer_first_kind"])
    check("monthly newcomers", monthly.newcomers.to_dict(), expected["monthly_newcomers"])
    top = people.commit.sort_values(ascending=False)
    check("commit concentration figure", {"authors": int(top.gt(0).sum()), "top15_commits": int(top.iloc[:15].sum()),
        "top15_percent": round(100 * top.iloc[:15].sum() / top.sum(), 2)}, expected["commit_figure"])
    concentration = pd.read_csv(OUTPUT / "concentration.csv", index_col="kind")
    for kind, wanted in expected["concentration_50pct"].items():
        check("absence factor " + kind, int(concentration.loc[kind, "people_for_50pct"]), wanted)
    for kind, wanted in expected["monthly"]["feb_march_daily_growth_percent"].items():
        check("February/March daily growth " + kind,
              round(100 * ((monthly.loc["2026-03", kind] / 31) / (monthly.loc["2026-02", kind] / 28) - 1)), wanted)
    for key, kind in (("pr_closure_peak", "pull_request_closed_unmerged"), ("issue_closure_peak", "issue_closed")):
        check(key, [monthly[kind].idxmax(), int(monthly[kind].max())], expected["monthly"][key])
    check("issue opening peak", monthly.issue.idxmax(), expected["monthly"]["issue_opening_peak"])
    check("partial September days", [int(monthly.observed_days.iloc[0]), int(monthly.observed_days.iloc[-1])], expected["monthly"]["september_observed_days"])
    check("observed dates", int(monthly.observed_days.sum()), 366)

    process = pd.read_csv(OUTPUT / "process_summary.csv", index_col="group")
    for group, values in expected["process"].items():
        for metric, wanted in values.items():
            check(group + ": " + metric, process.loc[group, metric], wanted)
    check("pre-merge review", json.loads((OUTPUT / "premerge_review.json").read_text()), expected["premerge_review"])
    closures = pd.read_csv(OUTPUT / "automated_closure_summary.csv", index_col="family")
    for family, values in expected["closure_matches"].items():
        for key, wanted in values.items():
            check(family + ": " + key, closures.loc[family, key], wanted)
    sample = pd.read_csv(OUTPUT / "qualitative_sample.csv")
    base = "https://github.com/google-gemini/gemini-cli/"
    wanted = expected["sample"]
    check("eight stratified conversations", sorted(sample.loc[sample.selection.eq("stratified_random"), "url"]),
          sorted(base + url for url in wanted["stratified_urls"]))
    for selection, key in (("targeted", "targeted_url"), ("targeted_random", "targeted_random_url")):
        check(selection + " conversation", list(sample.loc[sample.selection.eq(selection), "url"]), [base + wanted[key]])
    check("random sampling seed", list(sample.seed.dropna().unique()), [wanted["seed"]])
    check("ten frozen conversations", len(json.loads((PROJECT_ROOT / "evidence/conversations.json").read_text())), 10)
    comments = {str(c["id"]): c for c in load_records(RAW / "issue_comments.json")}
    retained = set(accounts.loc[accounts.include_as_human, "github_login"].str.casefold())
    declaration_comments = sum(bool(SELF_DECLARATION.search(c.get("body") or "")) for c in comments.values()
        if START_DATE <= c["created_at"] <= END_DATE
        and ((c.get("user") or {}).get("login") or "").casefold() in retained)
    check("raw self-declaration comments before account deduplication", declaration_comments,
          expected["raw_self_declaration_comments"])
    normalize = lambda s: " ".join(s.replace("**", "").replace("`", "").split()).casefold()
    for comment_id, quote in expected["quotes"].items():
        check("quoted comment " + comment_id, normalize(quote) in normalize(comments[comment_id].get("body") or ""), True)
    for comment_id in ("4003831080", "4003809782"):
        check("account switch date " + comment_id, comments[comment_id]["created_at"][:10], "2026-03-05")
    burst = scripted[scripted.github_login.eq("bdmorgan") & scripted.created_at.str.startswith("2026-01-15")]
    check("bdmorgan burst comments", len(burst), 283)
    dates = pd.to_datetime(burst.created_at, utc=True).dt.floor("min")
    check("bdmorgan burst minute-label span", int((dates.max() - dates.min()).total_seconds() / 60), 16)
    activity = read_activity()
    ghost = activity[activity.in_window & activity.raw_login.eq("ghost")]
    check("ghost attribution", ghost.kind.value_counts().to_dict(), expected["ghost_activity"])

    # Independently check every mature outcome against the original GraphQL timelines.
    objects = pd.read_csv(OUTPUT / "process_objects.csv")
    details = {d["url"]: d for name in ("pr_details", "issue_details")
               for d in json.loads((RAW / (name + ".json")).read_text())}
    mismatches, compared = 0, 0
    for row in objects[objects.eligible_30d & objects.complete_history].itertuples():
        doc = details[row.url]
        boundary = pd.Timestamp(row.opened_at) + pd.Timedelta(days=30)
        events = list(doc["timelineItems"]["nodes"])
        last = max(events, key=lambda e: e["createdAt"]) if events else None
        if doc.get("closedAt") and not doc.get("mergedAt") and (not last or last["__typename"] != "ClosedEvent"):
            events.append({"createdAt": doc["closedAt"], "__typename": "ClosedEvent"})
        state = "open"
        for event in sorted(events, key=lambda e: e["createdAt"]):
            if pd.Timestamp(event["createdAt"]) <= boundary:
                state = ("closed_unmerged" if row.kind == "pull_request" else "closed") if event["__typename"] == "ClosedEvent" else "open"
        if doc.get("mergedAt") and pd.Timestamp(doc["mergedAt"]) <= boundary:
            state = "merged"
        mismatches += int(state != row.state_30d)
        compared += 1
    check("independent mature outcome comparisons", compared, 17173)
    check("independent outcome mismatches", mismatches, 0)
    failed = [c["claim"] for c in checks if not c["pass"]]
    result = {"status": "fail" if failed else "pass", "report": expected["report"],
        "window": [START_DATE, END_DATE], "wording_note": expected["wording_note"], "checks": checks}
    (OUTPUT / "report_verification.json").write_text(json.dumps(result, indent=2, default=lambda v: v.item()) + "\n")
    if failed:
        raise SystemExit("Report checks failed: " + ", ".join(failed))
    print(f"PASS: {len(checks)} v4 checks; exact cohort counts, displayed percentages, sample URLs and quotes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Also verify the reference PDF's SHA-256")
    main(parser.parse_args().report)
