"""Record hashes and measured status for the local submission evidence bundle."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--plantuml-jar", type=Path, required=True)
    args = parser.parse_args()
    rendering = args.root / "rendering"
    images = {}
    for stem in ("vim-extraction/vim-change-movement", "config-factory/config-tool-assembly-proposal"):
        for extension in ("puml", "svg", "png"):
            path = args.root / f"{stem}.{extension}"
            if not path.is_file():
                raise FileNotFoundError(path)
            images[str(path.relative_to(args.root))] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    renderer = {
        "tool": "PlantUML", "version": "1.2026.9", "git_commit": "18d0aae",
        "jar_download_url": "https://github.com/plantuml/plantuml/releases/download/v1.2026.9/plantuml.jar",
        "jar_sha256": digest(args.plantuml_jar),
        "java_version": subprocess.run(["rtk", "proxy", "java", "-version"], capture_output=True, text=True).stderr,
        "outputs": images, "visually_inspected": True,
        "layout": "Smetana for proposed component diagram; built-in activity layout for implemented Vim diagram. Graphviz is not installed.",
        "version_command_note": "PlantUML -version reports missing Graphviz with exit 16. Actual SVG and PNG render commands both exit 0 and are retained separately.",
    }
    (rendering / "render-manifest.json").write_text(json.dumps(renderer, indent=2) + "\n")
    coverage = {}
    for phase in ("before", "after"):
        directory = args.root / f"vim-extraction/results/focused-coverage-{phase}"
        tests = json.loads((directory / "vitest.json").read_text())
        report = json.loads((directory / "report/coverage-summary.json").read_text())
        coverage[phase] = {"tests_passed": tests["numPassedTests"], "tests_failed": tests["numFailedTests"],
                           "coverage": report["total"]}
    destination = args.root / "delivery-manifest.json"
    result = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "implemented_change": "Limited Vim change-movement extraction only",
        "unimplemented_proposals": ["Config built-in tool assembly", "Dependency-security updates"],
        "focused_coverage": coverage,
        "cli_wide_coverage": "Timed out after 480 seconds; no completed report",
        "original_audit_snapshot": "Unavailable; new baseline-lockfile audit clearly dated separately",
        "final_pdf_modified": False,
        "publication_record": "vim-extraction/published-revisions.json" if (args.root / "vim-extraction/published-revisions.json").exists() else None,
        "files": {str(p.relative_to(args.root)): {"bytes": p.stat().st_size, "sha256": digest(p)}
                  for p in sorted(args.root.rglob("*")) if p.is_file() and p != destination},
    }
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Recorded {len(result['files'])} evidence-file hashes")


if __name__ == "__main__":
    main()
