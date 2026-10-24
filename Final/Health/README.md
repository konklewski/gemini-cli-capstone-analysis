# gemini-cli project health analysis

Scripts, data and evidence used for the final report's Project health section.
The period in `config.py` is 17 September 2025–17 September 2026 (UTC).

- `scripts/`: collection, filtering, contributor/process metrics, sampling, plots and checks.
- `data/snapshot/`: checksums of original exports; optional local archives are ignored.
- `data/raw/`: original exports; ignored except the original fetch log.
- `data/processed/`: generated activity data; ignored.
- `evidence/`: manual decisions, ten selected conversations and v4 reference values.
- `evidence/account_checks/`: 32 bot-check records: 22 manual cases and 10 automation confirmations. Identity analysis separately has 29 flags and 28 reviewed cases.
- `output/`: result tables, the sample selection record and verification results.
- `figures/`: generated charts.

## Instructions

Run from `Final/Health/` with Python 3.11+. Helpers are reused from
`../../Interim/Contributor_Collaboration/`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/reproduce.py
```

This uses the existing original exports in `data/raw/`, runs the analysis,
regenerates figures and sampling records, runs tests, and checks v4's results.
It uses no network. Input checksums must match; differing files are not overwritten.
A fresh clone needs the original exports copied into `data/raw/` separately.
Optional local archives in `data/snapshot/` can restore missing exports.

`output/report_verification.json` records each checked value.
`output/qualitative_sample.csv` records the seed, strata, pool sizes and URLs.
`evidence/report_expectations.json` identifies v4 by checksum and records its
reference values, including a clarification of the self-declaration wording.

To also check a copy of the reference PDF:

```bash
python scripts/verify_report.py --report /path/to/Final_Group27-4.pdf
```

Collection scripts require an authenticated GitHub CLI (`gh`). New downloads
can differ from the report's frozen inputs.
