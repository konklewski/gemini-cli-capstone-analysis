"""Run the installed Understand CLI on the controlled before/after checkouts.

This imports the group's saved settings. Only source location, CSV location,
and two CSV identification columns change. No metrics are implemented here:
all analysis and metric calculations are performed by Understand itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def run_command(command: list[str], log_prefix: Path) -> dict:
    """Preserve the exact command, output, exit status, and timing."""
    print(f"Running {log_prefix.name}: {command[1]}", flush=True)
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    finished = datetime.now(timezone.utc).isoformat()
    log_prefix.with_suffix(".stdout.txt").write_text(result.stdout, encoding="utf-8")
    log_prefix.with_suffix(".stderr.txt").write_text(result.stderr, encoding="utf-8")
    record = {
        "command": command,
        "started_utc": started,
        "finished_utc": finished,
        "exit_code": result.returncode,
        "stdout": log_prefix.with_suffix(".stdout.txt").name,
        "stderr": log_prefix.with_suffix(".stderr.txt").name,
    }
    log_prefix.with_suffix(".command.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(
            f"Understand exited with {result.returncode}. Inspect {log_prefix}.stdout.txt "
            f"and {log_prefix}.stderr.txt. Existing outputs have been preserved."
        )
    print(f"Completed {log_prefix.name}", flush=True)
    return record


def check_checkout(root: Path, expected_commit: str) -> None:
    """Reject the wrong revision or a checkout containing installed dependencies."""
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != expected_commit:
        raise ValueError(f"Unexpected revision in {root}: {revision}")
    if (root / "node_modules").exists() or list((root / "packages").glob("*/node_modules")):
        raise ValueError(f"Use a source-only checkout without node_modules: {root}")
    if not (root / "packages/cli/src/ui/components/shared/vim-buffer-actions.ts").is_file():
        raise ValueError(f"Expected source file is missing in {root}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--und", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    settings_source = Path(__file__).resolve().parents[2] / "packages.und/settings.xml"
    phases = [
        ("before", args.before.resolve(), "8f0a0f2d7d827d7ccd11c3df89631c39af67296f"),
        ("after", args.after.resolve(), "1820eca22b026d6f16c05cc62e845c849aa2f49c"),
    ]
    for name, root, commit in phases:
        check_checkout(root, commit)
        if (root / f"vim-{name}.und").exists():
            raise FileExistsError(f"Refusing to replace {root / f'vim-{name}.und'}")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "settings_source": str(settings_source),
        "settings_source_sha256": hashlib.sha256(settings_source.read_bytes()).hexdigest(),
        "settings_changes": [
            "Absolute source root pointing at each checkout's packages directory",
            "Separate CSV output path for each version",
            "Show declared-in-file and entity unique-name CSV columns for traceability",
        ],
        "runs": [],
    }
    manifest["version_command"] = run_command(
        [str(args.und), "version"], output / "tool-version"
    )
    for name, root, commit in phases:
        database = root / f"vim-{name}.und"
        settings = ET.parse(settings_source)
        source_root = settings.getroot().find("files/dir")
        metrics = settings.getroot().find("metrics")
        if source_root is None or metrics is None:
            raise ValueError("The saved project settings have an unfamiliar structure")
        source_root.set("name", str(root / "packages"))
        metrics.set("output_file", str(output / f"understand-{name}.csv"))
        metrics.set("show_declared_in_file", "true")
        metrics.set("add_uniquename_column", "true")
        settings_path = output / f"settings-{name}.xml"
        settings.write(settings_path, encoding="utf-8", xml_declaration=True)
        commands = [
            ("create", ["create", "import", str(settings_path), str(database)]),
            ("analyze", ["analyze", "-accuracy", "-errors", "-warnings", "-sarif", str(output / f"parse-{name}.sarif"), str(database)]),
            ("files", ["list", "files", str(database)]),
            ("settings", ["list", "-all", "settings", str(database)]),
            ("metrics", ["metrics", str(database)]),
            ("projectinfo", ["projectinfo", str(database)]),
        ]
        run = {"phase": name, "source_commit": commit, "database": str(database), "commands": []}
        manifest["runs"].append(run)
        for label, command in commands:
            run["commands"].append(
                run_command([str(args.und), *command], output / f"{name}-{label}")
            )
            (output / "run-manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
        if not (output / f"understand-{name}.csv").is_file():
            raise FileNotFoundError(f"Understand did not create the {name} CSV")
    print(f"Finished. Raw results: {output}", flush=True)


if __name__ == "__main__":
    main()
