"""Summarise captured npm audit JSON and verify the audited lockfile baseline.

This does not run npm audit fix or change any dependency. Original raw stdout
is retained, and the date-specific audit is not represented as the lost earlier
audit snapshot. npm's package-level findings are not a reachability analysis.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    baseline = "4a0749aceac5643e6f85a36d7420314d85e13b52"
    current = (args.checkout / "package-lock.json").read_bytes()
    original = subprocess.check_output(["rtk", "proxy", "git", "-C", str(args.checkout),
                                        "show", baseline + ":package-lock.json"])
    if current != original:
        raise ValueError("Audited lockfile differs from the report baseline")
    lock = json.loads(current)
    full = load(args.evidence / "audit-full.stdout.txt")
    production = load(args.evidence / "audit-production.stdout.txt")
    if full.get("auditReportVersion") != 2 or "error" in full or "error" in production:
        raise ValueError("Invalid/incomplete npm audit response")
    examples = []
    for name, advisory, classification, minimum in [
        ("@grpc/grpc-js", "GHSA-5375-pq7m-f5r2", "production dependency of packages/core", "1.14.4 for this advisory; audit recommends 1.14.6 for the package findings"),
        ("@eslint/plugin-kit", "GHSA-xffm-g5w8-qvg7", "development-only transitive dependency through eslint", "0.3.4 for this advisory; audit recommends eslint 9.39.5"),
    ]:
        vulnerability = full["vulnerabilities"][name]
        via = next(x for x in vulnerability["via"] if isinstance(x, dict) and advisory in x["url"])
        nodes = [{"path": node, "version": lock["packages"][node]["version"],
                  "dev": lock["packages"][node].get("dev", False)} for node in vulnerability["nodes"]]
        examples.append({"dependency": name, "classification": classification,
                         "locked_instances": nodes, "advisory": via,
                         "present_in_omit_dev_audit": name in production["vulnerabilities"],
                         "advisory_fix": minimum, "audit_fix_available": vulnerability["fixAvailable"]})
    result = {
        "original_audit_snapshot_available": False,
        "historical_report_claim_not_reproduced": {"total": 100, "low": 4, "moderate": 44, "high": 45, "critical": 7},
        "new_audit_local_date": "2026-10-24", "baseline_commit": baseline,
        "executed_checkout_commit": load(args.evidence / "audit-full.command.json")["source_commit"],
        "audited_lockfile_identical_to_baseline": True,
        "lockfile_sha256": hashlib.sha256(current).hexdigest(),
        "node_version": subprocess.check_output(["rtk", "proxy", "node", "--version"], text=True).strip(),
        "npm_version": subprocess.check_output(["rtk", "proxy", "npm", "--version"], text=True).strip(),
        "full_audit": full["metadata"], "omit_dev_audit": production["metadata"], "examples": examples,
        "vitest_classification_caveat": "Vitest 3.2.4 is declared as a devDependency in several workspaces but packages/test-utils declares it in dependencies. It remains in this root --omit=dev audit and cannot be labelled development-only for this graph.",
        "limitations": ["No dependency upgrade or post-fix audit was performed.",
                        "Audit counts depend on advisory data and npm resolution; the new 82 is not a security improvement over the historical 100.",
                        "The server-crash advisory is applicable to the package version; reachability of its vulnerable server code in Gemini CLI was not demonstrated.",
                        "The root workspace audit is not proof of exactly what ships in the published CLI package."]}
    (args.evidence / "audit-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"full": full["metadata"]["vulnerabilities"], "omit_dev": production["metadata"]["vulnerabilities"], "examples": examples}, indent=2))


if __name__ == "__main__":
    main()
