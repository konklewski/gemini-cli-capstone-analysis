# gemini-cli contributor and collaboration analysis

Scripts used for the Contributors and Collaboration parts of the report.
The analysis period is set in `config.py` and is currently 17 September 2025
through 17 September 2026 (UTC).

## Setup

Run everything from this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p data/raw data/processed output
```

The raw GitHub exports are excluded from the public repository because the
full export is large and commit records can contain author email addresses.
The scripts expect them in this folder's `data/raw/`; you can download them
again when needed. In the original local workspace, the earlier activity
exports are still in `../data/raw/` from before the folders were reorganized.

For the contributor counts and rankings, use:

- `commits.json`
- `pull_requests.json`
- `issues.json`

For the collaboration analysis, also use:

- `issue_comments.json`
- `review_comments.json`

`contributors.json` is optional background data from the GitHub Contributors
endpoint. Its counts cover the repository's lifetime, so it is not used for the
one-year ranking. The exports were downloaded from the corresponding
`google-gemini/gemini-cli` GitHub API endpoints with `gh api --paginate --slurp`.
The comment files come from `issues/comments` and `pulls/comments`.

You can inspect an export before processing it:

```bash
python scripts/inspect_json.py data/raw/commits.json
```

## Contributor analysis

```bash
python scripts/process_commits.py
python scripts/process_pull_requests.py
python scripts/process_issues.py
python scripts/build_contributor_table.py
python scripts/rank_contributors.py
```

The main results are written to `output/`. These include the full contributor
table, the equal-percentile top 10, the mean-rank top 10, and the weighting
sensitivity tables.

The contributor profiles use changed-file information from the separate local
gemini-cli checkout. In our folder layout it is two levels above this folder:

```bash
python scripts/build_contributor_profiles.py --repository ../../gemini-cli
```

GitHub logins are matched exactly. The scripts do not merge people because
their names or email addresses look similar. Confirmed bots are excluded from
the ranking by default, while uncertain accounts remain in the data.

## Collaboration analysis

After adding the two comment exports, run:

```bash
python scripts/analyze_collaboration.py --repository ../../gemini-cli
```

This creates a table of interactions and a summary for all pairs among the top
10 contributors. The numbers are only used to find useful examples. Shared
files or comments in the same thread are not automatically treated as proof of
collaboration.

The manually checked contributor and collaboration examples are in `evidence/`.
They include links to the original GitHub pull requests, issues, reviews, and
comments used in the report.

## Important details

- Pull requests returned by the Issues API are removed from the issue count.
- Raw activity counts are kept separate; they are not directly added into a
  contributor score.
- Generated files go to `data/processed/` and `output/`.
- The scripts only read from the separate gemini-cli checkout and do not modify
  it.
