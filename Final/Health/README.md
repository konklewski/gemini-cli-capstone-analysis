# gemini-cli project health analysis

Scripts and evidence used for the final report's Project health section.
The analysis period is set in `config.py`: 17 September 2025–17 September 2026 (UTC).

- `scripts/`: data collection, account filtering, metrics, plots and checks.
- `evidence/`: manual bot and identity decisions, with source links.
- `evidence/account_checks/`: 32 bot-check records: 22 manual cases and 10 automation confirmations. The separate identity analysis has 29 flags and 28 reviewed cases in `identity_decisions.csv`.
- `data/raw/`: downloaded GitHub exports, excluded from Git except the fetch log.
- `data/processed/`: generated activity data, excluded from Git.
- `output/`: saved result tables and the input checksum manifest.
- `figures/`: generated charts.

## Instructions

Run from `Final/Health/`. Requires Python 3.11+ and an authenticated GitHub CLI (`gh`).
Shared helpers come from `../../Interim/Contributor_Collaboration/`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Download raw data if needed. A new download may differ from the saved results.

```bash
bash scripts/fetch_raw.sh
python scripts/fetch_graphql.py pulls issues
```

Run the analysis and checks using the downloaded exports:

```bash
python scripts/classify_bots.py
python scripts/identify_accounts.py
python scripts/involvement.py
python scripts/plot_frequency.py
python scripts/plot_newcomers.py
python scripts/plot_commit_concentration.py
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/validate.py
```
