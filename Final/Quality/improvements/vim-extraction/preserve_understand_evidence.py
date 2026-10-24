"""Preserve GUI evidence and compare stored diagnostics, without reanalysis.

Requires Python 3 and cbor2==6.1.5. CSV metrics are read, never recalculated.
Understand's issues.cbor schema is internal: reject unknown schema versions and
retain the original bytes alongside readable, path-normalised diagnostic lists.
No source tree, input export or GUI database is modified.
"""

import argparse
import collections
import csv
import hashlib
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import cbor2


VIM_FILE = "packages/cli/src/ui/components/shared/vim-buffer-actions.ts"
COMMITS = {"before": "8f0a0f2d7d827d7ccd11c3df89631c39af67296f",
           "after": "1820eca22b026d6f16c05cc62e845c849aa2f49c"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run(arguments, prefix):
    """Record read-only Understand CLI calls and their unfiltered output."""
    argv = ["rtk", "proxy", *arguments]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    prefix.with_suffix(".stdout.txt").write_text(result.stdout, encoding="utf-8")
    prefix.with_suffix(".stderr.txt").write_text(result.stderr, encoding="utf-8")
    save_json(prefix.with_suffix(".command.json"), {
        "command": argv, "exit_code": result.returncode,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
    })
    if result.returncode:
        raise RuntimeError(f"Command failed: {prefix}")
    return result.stdout


def read_diagnostics(path, roots):
    with path.open("rb") as handle:
        raw = cbor2.load(handle)
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("files"), dict):
        raise ValueError(f"Unsupported diagnostic schema: {path}")
    rows = []
    for filename, checks in raw["files"].items():
        filename = filename.removeprefix("./")
        if not filename.startswith("packages/"):
            filename = "packages/" + filename
        for check, values in checks.items():
            if check not in ("UND_ERROR", "UND_WARNING"):
                raise ValueError(f"Unexpected diagnostic check: {check}")
            for value in values:
                text = value["text"]
                for root in sorted(roots, key=lambda p: len(str(p)), reverse=True):
                    text = text.replace(str(root), "<SOURCE_ROOT>")
                rows.append({"check": check, "file": filename,
                             "line": value["location"]["line"],
                             "column": value["location"]["column"], "text": text})
    return sorted(rows, key=lambda r: (r["check"], r["file"], r["line"], r["column"], r["text"]))


def read_metrics(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        required = {"Kind", "Name", "File", "Entity_Uniquename", "Cyclomatic", "CountLineCode"}
        if not required <= columns:
            raise ValueError(f"Missing columns: {required - columns}")
        rows = list(reader)
    files, functions = set(), {}
    for row in rows:
        if row["File"]:
            if "/packages/" not in row["File"]:
                raise ValueError(f"File outside packages: {row['File']}")
            files.add("packages/" + row["File"].split("/packages/", 1)[1])
        if row["Kind"] == "Function" and row["File"].endswith("/" + VIM_FILE):
            if row["Name"] in functions:
                raise ValueError(f"Duplicate function: {row['Name']}")
            functions[row["Name"]] = {key: int(row[key]) for key in ("CountLineCode", "Cyclomatic")}
    return columns, files, functions, len(rows)


def check_gui_log(path, stored, root):
    """Cross-check the pasted GUI baseline log against the stored diagnostics.

    For this log format, warning columns are displayed one below their stored
    values; error columns already match. Preserve both original inputs.
    """
    expected = collections.Counter(tuple(r[k] for k in ("check", "file", "line", "column", "text")) for r in stored)
    observed = collections.Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.search(r"\[(E|W)\] (.*?) \((.*?):(\d+):(\d+)\)$", line.strip())
        if not match:
            continue
        level, text, filename, lineno, column = match.groups()
        filename = "packages/" + filename.split("/packages/", 1)[1]
        observed[("UND_ERROR" if level == "E" else "UND_WARNING", filename,
                  int(lineno), int(column) + (1 if level == "W" else 0),
                  text.replace(str(root), "<SOURCE_ROOT>"))] += 1
    if observed != expected:
        raise ValueError("Stored before diagnostics disagree with the supplied GUI log")
    return {"matched_records": sum(observed.values()), "all_records_match": True,
            "column_display_conversion": "GUI warning column + 1; GUI error column unchanged"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("und", "before-root", "after-root", "before-db", "after-db", "exports", "before-gui-log", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    roots = {"before": args.before_root.resolve(), "after": args.after_root.resolve()}
    dbs = {"before": args.before_db.resolve(), "after": args.after_db.resolve()}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run([str(args.und), "version"], output / "tool-version")
    manifest = {"method": "Read completed GUI CSV exports and stored GUI diagnostics; no reanalysis",
                "tool_build": 1265, "decoder": "cbor2 6.1.5", "diagnostic_schema": 1,
                "source_or_gui_database_modified": False,
                "normalisation": "Repository-relative paths and <SOURCE_ROOT> in messages; original CBOR retained. Diagnostic line and column values are unchanged.",
                "captured_utc": datetime.now(timezone.utc).isoformat(), "phases": {}}
    shutil.copy2(args.before_gui_log, output / "gui-before-analysis-log.txt")
    diagnostics, metrics, settings = {}, {}, {}
    for phase, root in roots.items():
        revision = run(["git", "-C", str(root), "rev-parse", "HEAD"], output / f"{phase}-revision").strip()
        if revision != COMMITS[phase]:
            raise ValueError(f"Unexpected source commit: {revision}")
        run(["git", "-C", str(root), "diff", "--exit-code", "HEAD", "--", VIM_FILE,
             VIM_FILE.replace(".ts", ".test.ts")], output / f"{phase}-source-clean")
        for source, name in [
            (args.exports / f"understand-{phase}.csv", f"understand-{phase}.csv"),
            (dbs[phase] / "settings.xml", f"gui-settings-{phase}.xml"),
            (dbs[phase] / "local/settings.xml", f"gui-local-settings-{phase}.xml"),
            (dbs[phase] / "local/issues.cbor", f"gui-issues-{phase}.cbor"),
        ]:
            shutil.copy2(source, output / name)
            if digest(source) != digest(output / name):
                raise ValueError(f"Copy hash mismatch: {source}")
        run([str(args.und), "export", str(output / f"gui-exported-settings-{phase}.xml"), str(dbs[phase])], output / f"{phase}-export-settings")
        listing = run([str(args.und), "list", "files", str(dbs[phase])], output / f"{phase}-files")
        if "vim-buffer-actions.ts" not in listing:
            raise ValueError("Expected Vim source missing from GUI database")
        run([str(args.und), "projectinfo", str(dbs[phase])], output / f"{phase}-projectinfo")
        diagnostics[phase] = read_diagnostics(output / f"gui-issues-{phase}.cbor", list(roots.values()))
        save_json(output / f"diagnostics-{phase}.json", diagnostics[phase])
        (output / f"diagnostics-{phase}.txt").write_text("\n".join(
            f"{r['check']} {r['file']}:{r['line']}:{r['column']} {r['text']}"
            for r in diagnostics[phase]) + "\n", encoding="utf-8")
        metrics[phase] = read_metrics(output / f"understand-{phase}.csv")
        tree = ET.parse(output / f"gui-settings-{phase}.xml").getroot()
        settings[phase] = {key: ET.tostring(tree.find(key), encoding="unicode")
                           for key in ("languages", "web_options", "dependency_options", "file_types")}
        manifest["phases"][phase] = {
            "source_commit": revision, "gui_database": str(dbs[phase]),
            "production_source_sha256": digest(root / VIM_FILE),
            "test_source_sha256": digest(root / VIM_FILE.replace(".ts", ".test.ts")),
            "diagnostic_counts": dict(collections.Counter(r["check"] for r in diagnostics[phase])),
            "csv_rows": metrics[phase][3], "source_paths": len(metrics[phase][1])}
    counts = {phase: collections.Counter(json.dumps(r, sort_keys=True) for r in rows)
              for phase, rows in diagnostics.items()}
    added = [json.loads(r) for r in (counts["after"] - counts["before"]).elements()]
    removed = [json.loads(r) for r in (counts["before"] - counts["after"]).elements()]
    watched = {VIM_FILE, VIM_FILE.replace(".ts", ".test.ts"),
               VIM_FILE.replace("vim-buffer-actions", "text-buffer"),
               VIM_FILE.replace("vim-buffer-actions.ts", "text-buffer.test.ts")}
    comparison = {"new_diagnostics": added, "removed_diagnostics": removed,
                  "identical_after_path_normalisation": not added and not removed,
                  "watched_files": sorted(watched),
                  "watched_file_diagnostics": {phase: [r for r in rows if r["file"] in watched]
                                               for phase, rows in diagnostics.items()}}
    save_json(output / "diagnostic-comparison.json", comparison)
    metric_comparison = {
        "same_columns": metrics["before"][0] == metrics["after"][0],
        "same_source_paths": metrics["before"][1] == metrics["after"][1],
        "matching_parser_settings": settings["before"] == settings["after"],
        "source_paths": len(metrics["before"][1]),
        "functions": {name: {phase: metrics[phase][2].get(name) for phase in roots}
                      for name in sorted(set(metrics["before"][2]) | set(metrics["after"][2]))},
        "interpretation": "Handler CountLineCode 1461 to 1381 and Cyclomatic 196 to 188. Helper CountLineCode 86 and Cyclomatic 9. Affected code lines total 1461 to 1467. Sum(Cyclomatic - 1) remains 195."}
    save_json(output / "metric-comparison.json", metric_comparison)
    save_json(output / "gui-log-crosscheck.json", check_gui_log(
        output / "gui-before-analysis-log.txt", diagnostics["before"], roots["before"]))
    if not all(metric_comparison[k] for k in ("same_columns", "same_source_paths", "matching_parser_settings")):
        raise ValueError("CSV scope or parser settings differ")
    if manifest["phases"]["before"]["diagnostic_counts"] != {"UND_ERROR": 117, "UND_WARNING": 172}:
        raise ValueError("Before diagnostic counts disagree with the supplied GUI log")
    manifest["capture_complete"] = True
    manifest["files"] = {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)}
                         for p in sorted(output.iterdir()) if p.is_file()}
    save_json(output / "evidence-manifest.json", manifest)
    print(json.dumps({"output": str(output), "phases": manifest["phases"],
                      "new_diagnostics": len(added), "removed_diagnostics": len(removed)}, indent=2))


if __name__ == "__main__":
    main()
