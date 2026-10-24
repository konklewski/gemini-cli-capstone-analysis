"""Run a bounded analysis command and preserve output, timing and source revision."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=480)
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Supply a command after --")
    prefix = args.output.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    record_path = prefix.with_suffix(".command.json")
    if record_path.exists():
        raise FileExistsError(f"Refusing to overwrite {record_path}")
    env = os.environ.copy()
    overrides = dict(value.split("=", 1) for value in args.env)
    env.update(overrides)
    revision = subprocess.check_output(["rtk", "proxy", "git", "rev-parse", "HEAD"],
                                       cwd=args.cwd, text=True).strip()
    record = {"command": ["rtk", "proxy", *command], "cwd": str(args.cwd.resolve()),
              "source_commit": revision, "environment_overrides": overrides,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "timeout_seconds": args.timeout, "timed_out": False}
    record_path.write_text(json.dumps(record, indent=2) + "\n")
    started = time.monotonic()
    with prefix.with_suffix(".stdout.txt").open("wb") as out, prefix.with_suffix(".stderr.txt").open("wb") as err:
        process = subprocess.Popen(record["command"], cwd=args.cwd, env=env,
                                   stdout=out, stderr=err, start_new_session=True)
        try:
            record["exit_code"] = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            record["timed_out"] = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            record["exit_code"] = process.returncode
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    for stream in ("stdout", "stderr"):
        path = prefix.with_suffix(f".{stream}.txt")
        record[f"{stream}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    record_path.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
