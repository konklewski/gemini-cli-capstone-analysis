#!/usr/bin/env python3
"""Activity volumes, contributor involvement and monthly flows.

Population: human actors, aliases merged, ghost/spam/bots and known scripted
texts excluded. Categories overlap; involvement_band alone is a partition.
Run from Final/Health/: .venv/bin/python scripts/involvement.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from activity import CONTRIBUTIONS, KINDS, OUTPUT, PROJECT_ROOT, RAW, human_activity, load_activity
from config import END_DATE, START_DATE

FREQUENT_MONTHS = 6  # break in distribution's tail; compare 5, 6 and 7
DORMANT_DAYS = 60   # observed inactivity, not evidence of permanent departure
FIGURES = PROJECT_ROOT / "figures"
START, END = pd.Timestamp(START_DATE), pd.Timestamp(END_DATE)
MONTHS = pd.period_range(START.tz_localize(None), END.tz_localize(None), freq="M").astype(str)


def dormant(people: pd.DataFrame, days: int = DORMANT_DAYS) -> pd.Series:
    return people["months_active"].ge(2) & people["days_silent_at_end"].gt(days)


def build(activity: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    history = human_activity(activity)
    window = history[history["in_window"]].copy()
    window["month"] = window["created_at"].dt.strftime("%Y-%m")
    contributions = history[history["kind"].isin(CONTRIBUTIONS)]
    first = contributions.groupby("login")["created_at"].min()
    people = window.groupby("login").agg(months_active=("month", "nunique"),
                                            first_activity=("created_at", "min"),
                                            last_activity=("created_at", "max"))
    counts = pd.crosstab(window["login"], window["kind"]).reindex(columns=KINDS, fill_value=0)
    people = people.join(counts)
    people["contributions"] = people[list(CONTRIBUTIONS)].sum(axis=1)
    people["first_contribution_observed"] = first.reindex(people.index)
    # Includes self-merges; observed integration is a role proxy, not a team roster.
    integrators = set(window.loc[window["kind"].eq("pull_request_merged"), "login"])
    people["observed_integrator"] = people.index.isin(integrators)
    people["frequent"] = people["months_active"].ge(FREQUENT_MONTHS)
    people["involvement_band"] = np.where(people["frequent"], "frequent",
                                         np.where(people["months_active"].ge(2), "occasional", "single_month"))
    people["newcomer"] = people["first_contribution_observed"].between(START, END)
    people["no_authored_contribution"] = people["contributions"].eq(0)
    people["one_authored_contribution"] = people["contributions"].eq(1)
    people["one_action"] = people[list(KINDS)].sum(axis=1).eq(1)
    people["days_silent_at_end"] = (END - people["last_activity"]).dt.total_seconds() / 86400
    people["dormant"] = dormant(people)

    monthly = window.groupby(["month", "kind"]).size().unstack(fill_value=0)
    monthly = monthly.reindex(index=MONTHS, columns=KINDS, fill_value=0)
    newcomer_month = people.loc[people["newcomer"], "first_contribution_observed"].dt.strftime("%Y-%m")
    monthly["newcomers"] = newcomer_month.value_counts().reindex(MONTHS, fill_value=0)
    previous_active, previous_dormant, seen = set(), set(), set()
    for month in MONTHS:
        period = pd.Period(month, freq="M")
        boundary = min(period.end_time.tz_localize("UTC"), END)
        current = set(window.loc[window["month"].eq(month), "login"])
        past = window[window["created_at"] <= boundary]
        states = past.groupby("login").agg(months_active=("month", "nunique"), last=("created_at", "max"))
        states["days_silent_at_end"] = (boundary - states["last"]).dt.total_seconds() / 86400
        now_dormant = set(states.index[dormant(states)])
        values = {
            "active_people": len(current), "active_frequent": len(current & set(people.index[people["frequent"]])),
            "active_integrators": len(current & integrators), "first_seen_in_window": len(current - seen),
            "retained_from_previous_month": len(current & previous_active),
            "returning_after_gap": len((current & seen) - previous_active),
            "newly_dormant_at_boundary": len(now_dormant - previous_dormant),
            "dormant_at_boundary": len(now_dormant), "resumed_from_dormant": len(current & previous_dormant),
            "observed_days": (boundary.normalize() - max(period.start_time.tz_localize("UTC"), START).normalize()).days + 1,
            "partial_month": int(month in (MONTHS[0], MONTHS[-1])),
        }
        for key, value in values.items():
            monthly.loc[month, key] = value
        seen |= current
        previous_active, previous_dormant = current, now_dormant
    return people, monthly.astype(int)


def newcomer_returns(activity: pd.DataFrame, people: pd.DataFrame) -> pd.DataFrame:
    """Later-calendar-day return; 30-day rates include only mature cohorts."""
    human = human_activity(activity).sort_values(["created_at", "kind"])
    groups = dict(tuple(human.groupby("login")))
    rows = []
    for login, person in people[people["newcomer"]].iterrows():
        first = person["first_contribution_observed"]
        events = groups[login]
        later = events[events["created_at"].dt.normalize() > first.normalize()]
        authored = later[later["kind"].isin(CONTRIBUTIONS)]
        first_kind = events.loc[events["kind"].isin(CONTRIBUTIONS), "kind"].iloc[0]
        rows.append({"login": login, "first_contribution": first, "first_kind": first_kind,
                     "prior_observed_participation": bool((events["created_at"] < first).any()),
                     "returned_authored_later_day": not authored.empty,
                     "returned_any_later_day": not later.empty,
                     "eligible_30d": first + pd.Timedelta(days=30) <= END,
                     "returned_authored_30d": bool((authored["created_at"] <= first + pd.Timedelta(days=30)).any()),
                     "returned_any_30d": bool((later["created_at"] <= first + pd.Timedelta(days=30)).any())})
    return pd.DataFrame(rows)


def diagnostics(window: pd.DataFrame, people: pd.DataFrame) -> dict:
    days = window.assign(day=window["created_at"].dt.normalize()).drop_duplicates(["login", "day"])
    days = days.sort_values(["login", "day"])
    days["gap"] = days.groupby("login")["day"].diff().dt.days
    gaps = {}
    for name, selected in (("all", days), ("frequent", days[days["login"].isin(people.index[people["frequent"]])])):
        values = selected["gap"].dropna()
        gaps[name] = {str(q): float(values.quantile(q)) for q in (.5, .9, .95, .99)}
        gaps[name]["max"] = float(values.max())
    sensitivity = []
    for months in (5, 6, 7):
        for inactivity in (30, 60, 90):
            frequent, idle = people["months_active"].ge(months), dormant(people, inactivity)
            sensitivity.append({"frequent_months": months, "dormant_days": inactivity,
                                "frequent_people": int(frequent.sum()), "dormant_people": int(idle.sum()),
                                "frequent_and_dormant": int((frequent & idle).sum())})
    pd.DataFrame(sensitivity).to_csv(OUTPUT / "threshold_sensitivity.csv", index=False)
    return {"months_active_distribution": people["months_active"].value_counts().sort_index().to_dict(),
            "inter_active_day_gaps": gaps}


def activity_tables(activity: pd.DataFrame, people: pd.DataFrame) -> None:
    window = activity[activity["in_window"]].copy()
    window["month"] = window["created_at"].dt.strftime("%Y-%m")
    window["actor_group"] = np.where(window["scripted"] & window["actor_class"].eq("human"),
                                      "human_scripted", window["actor_class"])
    by_actor = window.groupby(["month", "kind", "actor_group"]).size().rename("events").reset_index()
    by_actor.to_csv(OUTPUT / "monthly_activity_by_actor.csv", index=False)
    totals = by_actor.groupby(["kind", "actor_group"])["events"].sum().unstack(fill_value=0)
    totals.reindex(KINDS, fill_value=0).to_csv(OUTPUT / "activity_totals.csv")
    human = human_activity(window)
    human["association_group"] = human["association"].fillna("UNAVAILABLE")
    human.groupby(["kind", "association_group"]).size().rename("events").to_csv(OUTPUT / "activity_association.csv")
    concentration, shares = [], []
    for kind in KINDS:
        counts = people[kind].sort_values(ascending=False)
        total = int(counts.sum())
        row = {"kind": kind, "human_events": total}
        for fraction in (.5, .8):
            row[f"people_for_{int(fraction * 100)}pct"] = int(counts.cumsum().searchsorted(total * fraction) + 1) if total else 0
        concentration.append(row)
        for group in ("frequent", "observed_integrator"):
            count = int(people.loc[people[group], kind].sum())
            shares.append({"kind": kind, "group": group, "group_events": count, "all_human_events": total,
                           "share": count / total if total else None})
    pd.DataFrame(concentration).to_csv(OUTPUT / "concentration.csv", index=False)
    pd.DataFrame(shares).to_csv(OUTPUT / "group_activity_shares.csv", index=False)


def plot(monthly: pd.DataFrame) -> None:
    FIGURES.mkdir(exist_ok=True)
    x = np.arange(len(monthly))
    labels = [m + ("*" if monthly.loc[m, "partial_month"] else "") for m in monthly.index]
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for column, label in (("active_people", "active participants"), ("newcomers", "new authored contributors")):
        axes[0].plot(x, monthly[column], marker="o", label=label)
    for column, label in (("active_frequent", "active frequent participants"),
                          ("active_integrators", "active observed integrators")):
        axes[1].plot(x, monthly[column], marker="o", label=label)
    for ax in axes:
        ax.set_ylabel("People")
        ax.legend(frameon=False, fontsize=9)
        ax.grid(alpha=.25)
        for edge in (0, len(x) - 1):
            ax.axvspan(edge - .45, edge + .45, color="grey", alpha=.1)
    axes[1].set_xticks(x, labels, rotation=45, ha="right")
    fig.suptitle("Human participation: 17 Sep 2025 – 17 Sep 2026 (UTC)")
    fig.text(.12, .01, "* Partial month: 14 days in Sep 2025; 17 days in Sep 2026. Frequent/integrator roles use whole-window observations.", fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, .96))
    fig.savefig(FIGURES / "monthly_activity.png", dpi=180)
    plt.close(fig)
    by_actor = pd.read_csv(OUTPUT / "monthly_activity_by_actor.csv")
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    for ax, kinds, title in zip(axes.flat,
            [("commit", "pull_request", "issue"), ("pull_request_merged", "pull_request_closed_unmerged", "issue_closed"),
             ("comment", "review_comment", "review"), ("comment", "review_comment", "review")],
            ["Human authorship", "Human decisions", "Human discussion and review", "Bot discussion and review"]):
        group = "bot" if title.startswith("Bot") else "human"
        for kind in kinds:
            values = by_actor[by_actor["kind"].eq(kind) & by_actor["actor_group"].eq(group)].set_index("month")["events"]
            ax.plot(x, values.reindex(monthly.index, fill_value=0), marker=".", label=kind.replace("pull_request", "PR").replace("_", " "))
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("Actions")
        ax.legend(frameon=False, fontsize=8)
        ax.grid(alpha=.25)
        ax.set_xticks(x[::2], labels[::2], rotation=45, ha="right")
        for edge in (0, len(x) - 1):
            ax.axvspan(edge - .45, edge + .45, color="grey", alpha=.1)
    fig.suptitle("Activity mix: actions counted on their own timestamps")
    fig.text(.1, .01, "* Partial month. Scales differ. Human panels exclude known scripted texts; separate actions do not measure equal effort.", fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, .96))
    fig.savefig(FIGURES / "activity_mix.png", dpi=180)
    plt.close(fig)


def main() -> None:
    activity = load_activity()
    people, monthly = build(activity)
    people.to_csv(OUTPUT / "people.csv")
    monthly.to_csv(OUTPUT / "monthly_activity.csv", index_label="month")
    activity.to_csv(PROJECT_ROOT / "data" / "processed" / "activity.csv", index=False)
    activity_tables(activity, people)
    returns = newcomer_returns(activity, people)
    returns.to_csv(OUTPUT / "newcomer_returns.csv", index=False)
    window = human_activity(activity[activity["in_window"]])
    summary = {"window": {"start": START_DATE, "end": END_DATE}, "participants": len(people),
               "authored_contributors": int((~people["no_authored_contribution"]).sum()),
               **{name: int(people[name].sum()) for name in ("frequent", "newcomer", "dormant", "observed_integrator",
                    "no_authored_contribution", "one_authored_contribution", "one_action")},
               "frequent_and_dormant": int((people["frequent"] & people["dormant"]).sum()),
               "integrator_and_dormant": int((people["observed_integrator"] & people["dormant"]).sum()),
               "newcomer_first_kind": returns["first_kind"].value_counts().to_dict(),
               "newcomers_with_prior_observed_participation": int(returns["prior_observed_participation"].sum()),
               "return_rates": {}, **diagnostics(window, people)}
    all_window = activity[activity["in_window"]]
    summary["coverage"] = {"events_by_actor_class": all_window["actor_class"].value_counts().to_dict(),
                           "scripted_human_texts": int((all_window["actor_class"].eq("human") & all_window["scripted"]).sum()),
                           "window_named_actors_without_classification": int((all_window["raw_login"].notna() & all_window["classification_source"].ne("account_classification")).sum()),
                           "rest_only_openings_in_window": int(all_window["outcome"].eq("unknown").sum()),
                           "fallback_closures_in_window": all_window.loc[all_window["source"].isin(
                               ["rest_last_closure", "graphql_last_closure"]), "source"].value_counts().to_dict()}
    accounts = pd.read_csv(OUTPUT / "bot_classification.csv")
    mapping = dict(pd.read_csv(OUTPUT / "identity_map.csv").values)
    retained = set(accounts.loc[accounts["include_as_human"], "github_login"])
    canonical = {mapping.get(login, login) for login in retained}
    candidate_people = canonical - {"ghost"}
    summary["population_flow"] = {
        "raw_named_accounts": len(accounts), "bot_accounts": int(accounts["final"].eq("bot").sum()),
        "spam_accounts": int(accounts["spam"].sum()), "organization_accounts": int(accounts["final"].eq("organization").sum()),
        "retained_accounts_before_aliases": len(retained), "active_alias_accounts_merged": len(retained) - len(canonical),
        "placeholder_accounts_excluded": int("ghost" in canonical),
        "people_before_scripted_filter": len(candidate_people), "scripted_only_people_excluded": len(candidate_people - set(people.index)),
        "analysis_participants": len(people)}
    pd.DataFrame(summary["population_flow"].items(), columns=["stage", "count"]).to_csv(OUTPUT / "population_flow.csv", index=False)
    with_scripted, _ = build(activity.assign(scripted=False))
    summary["including_flagged_texts"] = {"participants": len(with_scripted),
        **{name: int(with_scripted[name].sum()) for name in ("frequent", "dormant")}}
    for kind in ("authored", "any"):
        for followup in ("later_day", "30d"):
            selected = returns[returns["eligible_30d"]] if followup == "30d" else returns
            count = int(selected[f"returned_{kind}_{followup}"].sum())
            summary["return_rates"][f"{kind}_{followup}"] = {"returned": count, "eligible": len(selected),
                                                           "rate": count / len(selected) if len(selected) else None}
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    # Capture exact inputs and package versions without including credentials or author emails.
    import importlib.metadata
    inputs = [p for p in RAW.glob("*.json") if "before_audit" not in p.name]
    inputs += [OUTPUT / n for n in ("bot_classification.csv", "identity_map.csv", "scripted_activity.csv")]
    inputs += [PROJECT_ROOT / "config.py", PROJECT_ROOT / "requirements.txt", PROJECT_ROOT / "evidence" / "identity_decisions.csv", PROJECT_ROOT / "evidence" / "bot_manual_decisions.csv", PROJECT_ROOT / "evidence/report_expectations.json", PROJECT_ROOT / "data/snapshot/manifest.json", *Path(__file__).parent.glob("*.py"), Path(__file__).parent / "fetch_raw.sh"]
    hashes = {}
    for path in sorted(inputs):
        with path.open("rb") as stream:
            hashes[str(path.relative_to(PROJECT_ROOT))] = hashlib.file_digest(stream, "sha256").hexdigest()
    for name in ("common.py", "detect_bots.py"):
        relative = f"../../Interim/Contributor_Collaboration/scripts/{name}"
        with (PROJECT_ROOT / relative).open("rb") as stream:
            hashes[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {"inputs_sha256": hashes,
                "python": sys.version.split()[0], "packages": {n: importlib.metadata.version(n) for n in ("pandas", "numpy", "matplotlib")}}
    (OUTPUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    plot(monthly)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
