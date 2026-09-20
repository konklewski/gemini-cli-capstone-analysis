# Gemini CLI empirical repository analysis

This workspace supports a reproducible analysis of
[`google-gemini/gemini-cli`](https://github.com/google-gemini/gemini-cli) for the
Activities, Contributors, and Collaboration sections of the Capstone Software
Development 2026 course report. It is separate from the cloned source repository
and must not write to that repository.

The configured observation window is **17 September 2025 through 17 September
2026, inclusive, in UTC**. Change the timezone-aware `START_DATE` and `END_DATE`
once in [`config.py`](config.py); the processing scripts read those values.

## Folder structure

```text
capstone-analysis/
├── config.py                 # repository and date-window configuration
├── data/
│   ├── raw/                  # immutable GitHub/gh exports
│   └── processed/            # cleaned, windowed tables
├── evidence/
│   ├── collaboration/        # manual pair evidence and counterexamples
│   └── contributors/         # manually verified qualitative evidence
├── figures/                  # generated plots
├── notebooks/                # optional exploratory work
├── output/                   # final tables
└── scripts/                  # inspection, cleaning, bot, and aggregation code
```

`data/raw/` is input-only. Never edit or overwrite its files. Cleaned data goes
to `data/processed/`, final tables to `output/`, and plots to `figures/`. Raw and
generated files are git-ignored because they may be large and can be regenerated;
the scripts, configuration, and evidence notes provide the audit trail.

## Setup

From this `capstone-analysis` folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
gh auth status
```

Python 3.10 or newer is recommended. The scripts use `pandas`; `requests` and
`matplotlib` are included for later API and plotting work without introducing a
larger framework.

## Inspect a raw JSON file

Before choosing a processor, inspect any new export:

```bash
python scripts/inspect_json.py data/raw/contributors.json
python scripts/inspect_json.py data/raw/some_file.json
```

The inspector is read-only. It accepts a JSON array, newline-delimited JSON,
concatenated paginated JSON values, and familiar GitHub wrapper objects. It
reports the top-level representation, record count, fields, relevant nested
fields, sample values, date and login fields, and a conservative guess of the
GitHub object type. An unfamiliar shape is reported as unknown rather than
silently interpreted.

The existing `contributors.json` came from the repository Contributors endpoint.
Its `contributions` values are repository-lifetime commit totals, not totals for
the configured year. It is useful as contextual/reference data but is **not**
used to manufacture date-windowed activity counts.

To create an explainable bot-classification reference from it:

```bash
python scripts/detect_bots.py \
  data/raw/contributors.json \
  data/processed/contributors_with_bot_classification.csv
```

## Retrieve the required activity data

Run these commands from `capstone-analysis` (not from, and without modifying,
the separate Gemini CLI checkout). `--paginate` is essential. `--slurp` makes a
single valid outer array; the loader also supports output from `gh` versions or
commands that produce consecutive page arrays.

Load the configured dates once for the shell commands and pin the supported
GitHub REST API representation:

```bash
ANALYSIS_START=$(python -c 'from config import START_DATE; print(START_DATE)')
ANALYSIS_END=$(python -c 'from config import END_DATE; print(END_DATE)')
GITHUB_API_VERSION='2026-03-10'
```

See the official [`gh api` pagination
documentation](https://cli.github.com/manual/gh_api), [GitHub REST API version
documentation](https://docs.github.com/en/rest/about-the-rest-api/api-versions),
and endpoint references for [commits](https://docs.github.com/en/rest/commits/commits),
[pull requests](https://docs.github.com/en/rest/pulls/pulls), and
[issues](https://docs.github.com/en/rest/issues/issues).

### Commits authored in the window

```bash
gh api --paginate --slurp -X GET \
  repos/google-gemini/gemini-cli/commits \
  -H "X-GitHub-Api-Version: ${GITHUB_API_VERSION}" \
  -f since="${ANALYSIS_START}" \
  -f until="${ANALYSIS_END}" \
  -f per_page=100 \
  > data/raw/commits.json
```

Keep these retrieval dates synchronized with `config.py`. The local processor
applies the configured window again.

### Pull requests

```bash
gh api --paginate --slurp -X GET \
  repos/google-gemini/gemini-cli/pulls \
  -H "X-GitHub-Api-Version: ${GITHUB_API_VERSION}" \
  -f state=all -f sort=created -f direction=desc -f per_page=100 \
  > data/raw/pull_requests.json
```

### Issues (the API also returns PR-shaped objects)

```bash
gh api --paginate --slurp -X GET \
  repos/google-gemini/gemini-cli/issues \
  -H "X-GitHub-Api-Version: ${GITHUB_API_VERSION}" \
  -f state=all -f sort=created -f direction=desc -f per_page=100 \
  > data/raw/issues.json
```

The list endpoints do not offer both a start and end filter for these complete
object shapes, so these two commands intentionally retrieve all paginated
records and filter locally. This is larger but avoids the Search API's result
cap. Preserve the commands and retrieval date in report notes. If API rate limits
interrupt a command, do not treat a partial file as complete; retrieve it again
after the limit resets.

## Process activity data

Default filenames are shown below. An explicit input path and `--output` can be
used when needed.

```bash
python scripts/process_commits.py
python scripts/process_pull_requests.py
python scripts/process_issues.py
```

Outputs are:

- `data/processed/commits.csv`
- `data/processed/pull_requests.csv`
- `data/processed/issues.csv`

The scripts validate required structural fields and stop with an error on
malformed data. A missing value that GitHub legitimately represents as `null`
(for example a deleted account) remains missing. Each row retains its raw object
identifier, raw record index, source filename, URL, actor metadata, and bot
classification for traceability.

Git commit authors and GitHub accounts are different identity systems. The
commit table retains Git author name/email separately from the API's matched
GitHub login. It never merges identities because names or emails merely look
similar; unmatched commits remain in the processed table but cannot be assigned
to a login in the contributor aggregation.

GitHub's Issues API returns pull requests as issue-shaped objects containing a
`pull_request` field. `process_issues.py` explicitly removes those objects and
prints the exclusion count so “issues opened” does not double-count PRs.

## Build and sort the contributor table

After all three processed CSVs exist:

```bash
python scripts/build_contributor_table.py
```

This writes `output/contributor_activity.csv`, grouping only exact, nonempty
GitHub logins. To produce independent views for report analysis:

```bash
python scripts/build_contributor_table.py --sort-by commits_authored
python scripts/build_contributor_table.py --sort-by pull_requests_opened
python scripts/build_contributor_table.py --sort-by issues_opened
```

Each command replaces the same reproducible final table with the selected sort.
Copy a table only if the report needs separate named snapshots. The default sort
is alphabetical. `total_observed_activities` is descriptive and deliberately is
not an allowed automatic ranking key: a raw sum assumes unlike activity types
are comparable, which has not been justified.

## Generate the requested top-10 rankings

After generating `output/contributor_activity.csv`, run:

```bash
python scripts/rank_contributors.py
```

By default, confirmed bots are excluded from the ranking population, while
`human` and `uncertain` accounts remain. No bot rows are deleted from
`contributor_activity.csv`. To run a disclosed comparison that includes bots,
use `--include-bots` and preferably a separate output directory.

The ranking script writes:

- `output/contributor_rankings.csv`: all ranking-eligible contributors, raw
  counts, percentiles, category ranks, combined scores, and sensitivity ranks;
- `output/top_10_percentile_activity.csv`: equal-weight percentile top 10;
- `output/top_10_mean_rank.csv`: top 10 by lowest mean of the three category
  ranks;
- `output/top_10_method_comparison.csv`: union/membership comparison of the two
  main methods;
- `output/top_10_sensitivity.csv`: the ten selected accounts in each weighting
  scenario;
- `output/ranking_sensitivity_summary.csv`: top-10 overlap and Jaccard similarity
  relative to equal weighting.

### Equal-weight percentile method

For each raw metric, the script calculates a relative 0–1 position as:

```text
(ascending minimum rank - 1) / (number of contributors - 1)
```

This is the SQL-style `PERCENT_RANK` definition. Tied raw values receive the
same percentile, and the minimum value receives zero. The latter is important
because many observed contributors have zero commits or zero pull requests. The
three metric percentiles are averaged with weights of one third each. A high
score means high relative observed activity across the selected dimensions; it
does not measure developer quality, productivity, importance, or contribution
quality.

Raw counts stay beside every score. Equal weighting is the least assumption-heavy
baseline in the absence of a defensible reason to privilege one activity type;
it does not assert that one commit, PR, and issue have equal substantive value.

### Mean-rank comparison method

Each contributor receives a competition rank for commits, PRs, and issues, where
rank 1 is the highest count and ties receive the same rank. The arithmetic mean
of those three ranks is then calculated, and the **lowest mean rank is best**.
The top-10 table exposes all three category ranks and raw counts. If the cutoff
is tied, the deterministic secondary order is equal-weight percentile score and
then GitHub login; this should be disclosed when it affects selection.

### Weighting sensitivity

The sensitivity output compares these percentile scenarios:

- equal: `1/3` commits, `1/3` pull requests, `1/3` issues;
- commit emphasis: `0.50`, `0.25`, `0.25`;
- pull-request emphasis: `0.25`, `0.50`, `0.25`;
- issue emphasis: `0.25`, `0.25`, `0.50`.

Stable top-10 membership supports robustness to these reasonable alternatives;
substantial membership changes indicate that “top contributor” depends on how
observed activity is operationalized. This is a sensitivity analysis, not a
search for objectively correct weights.

For this study, an observed contributor is an exact GitHub login with at least
one commit authored, PR opened, or actual issue opened inside the window. State
clearly if the report uses another definition. The Contributors endpoint's 443
records must not be presented as the last-year contributor count.

## Metric definitions

- **Commits authored:** unique commit records whose Git author timestamp is in
  the inclusive window and whose GitHub API record is present. The contributor
  table assigns one only when the API supplies an exact `author.login`.
- **Pull requests opened:** pull-request records whose `created_at` is in the
  inclusive window, regardless of later state or merge outcome.
- **Issues opened:** Issues API records whose `created_at` is in the inclusive
  window, excluding every record with a `pull_request` field.
- **Total observed activities:** the descriptive row sum of those three counts;
  it is not a quality measure or an automatically valid ranking score.

Do not interpret one commit, PR, and issue as equivalent units of work. For a
top-10 presentation, report the three metric columns together and explain the
selection rule, or present separate top lists per metric. Do not silently rank by
their sum.

## Bot detection

Every processor uses the same conservative rules in `detect_bots.py`:

1. explicit automation metadata or GitHub account `type == "Bot"` → `bot`;
2. a login ending in `[bot]`, a small exact allow-list of well-known automation
   accounts, or an unambiguous automation token such as `release-please` → `bot`;
3. a GitHub account type of `User` with no indicator → `human`;
4. no login or missing/unrecognized account-type metadata → `uncertain`.

Generic occurrence of the letters “bot” is not enough. The classification and
reason are stored in the output. Bot records are never deleted: include or
exclude them deliberately and disclose that decision.

## Collaboration evidence to retrieve

Shared files or appearance in the same thread are candidate-generation signals,
not proof of collaboration. Manual claims need interaction evidence: reviews,
comments, requested changes and responses, issue discussion, explicit references,
or coordination language. Retrieve repository-wide conversation and review
comments as additional raw evidence:

```bash
gh api --paginate --slurp -X GET \
  repos/google-gemini/gemini-cli/issues/comments \
  -H "X-GitHub-Api-Version: ${GITHUB_API_VERSION}" \
  -f since="${ANALYSIS_START}" -f per_page=100 \
  > data/raw/issue_comments.json

gh api --paginate --slurp -X GET \
  repos/google-gemini/gemini-cli/pulls/comments \
  -H "X-GitHub-Api-Version: ${GITHUB_API_VERSION}" \
  -f since="${ANALYSIS_START}" -f per_page=100 \
  > data/raw/review_comments.json
```

These `since` filters use update time and do not provide an `until`; apply the
window during analysis and verify cited interactions on GitHub. Pull-request
review summaries have no repository-wide REST endpoint. After shortlisting a PR,
retrieve its reviews with:

```bash
PR_NUMBER=12345
gh api --paginate --slurp -X GET \
  "repos/google-gemini/gemini-cli/pulls/${PR_NUMBER}/reviews" \
  -H "X-GitHub-Api-Version: ${GITHUB_API_VERSION}" \
  -f per_page=100 \
  > "data/raw/pr_${PR_NUMBER}_reviews.json"
```

Optionally retrieve issue/PR timeline events for explicit cross-references:

```bash
ITEM_NUMBER=12345
gh api --paginate --slurp -X GET \
  "repos/google-gemini/gemini-cli/issues/${ITEM_NUMBER}/timeline" \
  -H 'Accept: application/vnd.github+json' -f per_page=100 \
  -H "X-GitHub-Api-Version: ${GITHUB_API_VERSION}" \
  > "data/raw/item_${ITEM_NUMBER}_timeline.json"
```

Use `evidence/collaboration/template.md` for two supported pairs and
`counterexample-template.md` for a quantitatively plausible pair whose thread
does not demonstrate coordination. Quote only the exact exchange needed, link
the GitHub URL, distinguish coordination from awareness, and record plausible
alternative explanations.

For contributor profiles, duplicate `evidence/contributors/template.md` once per
selected login. Base skill/interest language on linked observable contributions,
using formulations such as “appears particularly active in…” rather than
asserting personal expertise.

The current top-10 evidence extraction can be regenerated against the separate,
read-only Gemini CLI checkout with:

```bash
python scripts/build_contributor_profiles.py
```

This writes `output/top_10_contributor_profile_summary.csv`, containing profile
links and the most frequently touched subsystems/files for the selected commit
set. Its counts are changed-file occurrences, not lines changed, effort, or code
quality. The manually verified interpretation is stored in
`evidence/contributors/top-10-summary.md` and one evidence sheet per selected
contributor. Each sheet cites two merged pull requests and names the involved
files/subsystems.

For collaboration analysis, after placing `issue_comments.json` and
`review_comments.json` in `data/raw/` using the commands above, run:

```bash
python scripts/analyze_collaboration.py
```

This produces `data/processed/collaboration_interactions.csv` (traceable comment,
mention, and direct-reply signals) and
`output/top_10_collaboration_pair_metrics.csv` (all 45 top-10 pairs). Shared-file
overlap and the screening score are candidate-generation aids only. The manually
verified report-ready interpretation is in
`evidence/collaboration/analysis-summary.md`, with separate sheets for the two
selected pairs and the counterexample.

## Validity threats and limitations

- **Commit identity versus GitHub identity:** Git names/emails may not map to an
  account; squash, co-authored, and rebased commits further complicate attribution.
- **Bots and automation:** metadata may be missing and naming heuristics can
  misclassify accounts. Keep the reason and manually audit influential cases.
- **GitHub API pagination:** an omitted page or interrupted export causes
  undercounting. Always use `--paginate`, inspect record counts, and retain the
  raw export and retrieval command.
- **Deleted or renamed accounts:** null users are ungrouped and renames can split
  or obscure identity across exports. No identity is invented.
- **Issues API includes PRs:** PR-shaped objects must be excluded, as this
  workspace does using the `pull_request` field.
- **Different activity types represent different participation:** commits, PRs,
  and issues have different effort, review, and social meanings.
- **Raw counts should not be combined without justification:** the descriptive
  sum is not a score and can conceal those differences.
- **GitHub-visible activity is incomplete:** design discussions, private work,
  chat, meetings, code review outside captured endpoints, and non-code work may
  be absent.
- **Analysis-window boundary effects:** work opened just before the start or
  completed just after the end may be attributed incompletely. Author and merge
  timestamps also answer different questions.
- **API representation and mutable state:** later retrieval may show edited
  titles, labels, associations, or account metadata rather than their historical
  values at the event time.
- **Collaboration inference:** co-presence, file overlap, or comment sequence does
  not alone establish coordination. Claims require manual interaction evidence,
  and counterexamples should be actively sought.

## Reproducibility checklist

1. Record the UTC window and raw retrieval date.
2. Preserve every raw response unchanged.
3. Inspect each new file before processing it.
4. Run the three processors and retain their console counts.
5. Generate the contributor table with a disclosed independent sort rule.
6. Generate both top-10 methods and inspect the sensitivity tables.
7. Manually verify top accounts, bot classifications, URLs, and qualitative
   claims against GitHub.
8. Store exact collaboration evidence and a counterexample in the templates.
9. Commit the scripts, configuration, README, evidence notes, and report-ready
   outputs/figures as appropriate; document any intentionally omitted raw data.
