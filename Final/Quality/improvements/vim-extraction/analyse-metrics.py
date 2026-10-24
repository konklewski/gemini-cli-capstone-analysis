"""Recompute report summaries from the untouched Understand CSV exports.

Uses the report's original entity filters. Does not edit the exports or require
Understand to be installed. Output must be separate from the input directory.
"""
import argparse
import csv
import json
from pathlib import Path


VIM_FILE = "packages/cli/src/ui/components/shared/vim-buffer-actions.ts"


def summarise(path):
    """Return the filtered maximum and the affected named function metrics."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"Kind", "Name", "File", "CountLineCode", "Cyclomatic"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f"Missing required CSV columns in {path}")
        rows = list(reader)
    selected = [r for r in rows
                if not any(k in r["Kind"] for k in ("Ambient Module", "Class", "Enum", "File"))
                and not any(k in r["Name"] for k in ("describe-callback", "mock-callback"))
                and r["CountLineCode"] and int(r["CountLineCode"]) > 0 and r["Cyclomatic"]]
    maximum = max(int(r["Cyclomatic"]) for r in selected)
    affected = [r for r in rows if r["Kind"] == "Function"
                and r["File"].endswith("/" + VIM_FILE)
                and r["Name"] in ("handleVimAction", "handleVimChangeMovement")]
    names = {r["Name"] for r in affected}
    if "handleVimAction" not in names or len(names) != len(affected):
        raise ValueError(f"Missing or duplicate affected functions in {path}")
    return ({"included_entities": len(selected), "maximum_observed_cyclomatic": maximum,
             "maximum_functions": [r["Name"] for r in selected if int(r["Cyclomatic"]) == maximum]},
            sum(int(r["Cyclomatic"]) - 1 for r in affected))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", type=Path, default=Path(__file__).parent /
                        "results/understand-build-1265-completed")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.exports.resolve()):
        raise ValueError("Save derived output outside the raw export directory")
    metrics, decisions = {}, {}
    for phase in ("before", "after"):
        metrics[phase], decisions[phase] = summarise(args.exports / f"understand-{phase}.csv")
    metrics["combined_affected_decision_count"] = {
        "definition": "Sum(Cyclomatic - 1) for the affected functions", **decisions}
    args.output.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
