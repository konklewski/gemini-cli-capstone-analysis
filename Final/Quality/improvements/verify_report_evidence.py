"""Verify report-relevant metrics and inspect the available final PDF, read-only.

Requires pdfplumber. Saves derived JSON checks, not draft report paragraphs.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import pdfplumber


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    directory = args.evidence / "vim-extraction/results/understand-build-1265-completed"
    metrics = {}
    for phase in ("before", "after"):
        with (directory / f"understand-{phase}.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        # Match the original report's explicitly stated spreadsheet filters.
        selected = [r for r in rows
                    if not any(k in r["Kind"] for k in ("Ambient Module", "Class", "Enum", "File"))
                    and not any(k in r["Name"] for k in ("describe-callback", "mock-callback"))
                    and r["CountLineCode"] and int(r["CountLineCode"]) > 0 and r["Cyclomatic"]]
        maximum = max(int(r["Cyclomatic"]) for r in selected)
        metrics[phase] = {"included_entities": len(selected), "maximum_observed_cyclomatic": maximum,
                          "maximum_functions": [r["Name"] for r in selected if int(r["Cyclomatic"]) == maximum]}
    function_rows = json.loads((directory / "metric-comparison.json").read_text())["functions"]
    decisions = {phase: sum(function_rows[name][phase]["Cyclomatic"] - 1
                            for name in ("handleVimAction", "handleVimChangeMovement")
                            if function_rows[name][phase] is not None)
                 for phase in ("before", "after")}
    metrics["combined_affected_decision_count"] = {
        "definition": "Sum(Cyclomatic - 1) for the affected functions", **decisions}
    (args.evidence / "vim-extraction/results/re-evaluation-metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    with pdfplumber.open(args.report) as document:
        texts = [page.extract_text() or "" for page in document.pages]
    quality_text = "\n".join(texts[6:17])
    body = quality_text.split("Setup\n", 1)[1].split("Improvement suggestions\nTODO", 1)[0]
    report_check = {
        "source_pdf": str(args.report.resolve()), "sha256": hashlib.sha256(args.report.read_bytes()).hexdigest(),
        "pdf_modified": False, "editable_source_available": False,
        "todo_pages": [i+1 for i,t in enumerate(texts) if "TODO" in t],
        "quality_improvement_headings_still_todo": "Improvement suggestions\nTODO\nRe-evaluation after suggested changes\nTODO" in quality_text,
        "approximate_existing_quality_body_words": len(body.split()),
        "word_count_method": "Whitespace tokens in extracted pages 7-17, starting after Setup and ending before Improvement suggestions TODO; includes figure text and page numbers, so approximate.",
        "required_before_submission": [
            "Replace both quality TODOs on page 17 in the editable report and export a new PDF.",
            "Insert the rendered implemented Vim diagram and clearly label the Config diagram as a proposal.",
            "Add source permalinks, advisory citations and appendix references.",
            "Explain Build 1265 for both controlled versions and matching original Build 1264 function values.",
            "Do not claim full CLI coverage, a full repository test pass, Config implementation or a dependency fix.",
            "Move about 500-700 words of measurement commands/filtering/setup detail into the appendix before adding the new sections, then recount.",
            "Remove copied assignment instruction text and update the table of contents.",
            "Review the final exported PDF for both TODO removal and readable diagrams/citations.",
        ],
    }
    (args.evidence / "final-report-check.json").write_text(json.dumps(report_check, indent=2) + "\n")
    print(json.dumps({"metrics": metrics, "report": report_check}, indent=2))


if __name__ == "__main__":
    main()
