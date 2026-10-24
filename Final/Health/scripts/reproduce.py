"""Offline report reproduction from the checksummed frozen exports."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "gemini-health-matplotlib"))
    commands = [["scripts/snapshot.py", "restore"],
        *[["scripts/" + name + ".py"] for name in ("classify_bots", "identify_accounts", "involvement",
            "plot_frequency", "plot_newcomers", "plot_commit_concentration", "process_metrics",
            "match_closures", "sample_conversations")],
        ["-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py"],
        ["scripts/validate.py"], ["scripts/verify_report.py"]]
    for command in commands:
        print("RUN", " ".join(command), flush=True)
        subprocess.run([sys.executable, "-B", *command], cwd=ROOT, env=env, check=True)
