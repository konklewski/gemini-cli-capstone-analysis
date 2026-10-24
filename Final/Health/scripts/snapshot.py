"""Verify report inputs, or freeze/restore optional local archives."""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
SNAPSHOT = ROOT / "data/snapshot"
FILES = ("commits.json", "pull_requests.json", "issues.json", "issue_comments.json",
         "review_comments.json", "pr_details.json", "issue_details.json", "labels.json")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def freeze():
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    manifest = {"source": "GitHub exports collected 14–16 October 2026", "files": {}}
    for name in FILES:
        source, archive = RAW / name, SNAPSHOT / (name + ".gz")
        if archive.exists():
            raise FileExistsError(f"Snapshot already exists: {archive}")
        with source.open("rb") as src, archive.open("wb") as dst:
            with gzip.GzipFile(filename="", mode="wb", fileobj=dst, mtime=0) as compressed:
                shutil.copyfileobj(src, compressed)
        manifest["files"][name] = {"sha256": digest(source), "gzip_sha256": digest(archive),
                                   "bytes": source.stat().st_size}
        print(f"Frozen {name}: {archive.stat().st_size / 1024**2:.1f} MiB", flush=True)
    (SNAPSHOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def restore():
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
    if set(manifest["files"]) != set(FILES):
        raise ValueError("Unexpected snapshot filenames")
    RAW.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target, archive = RAW / name, SNAPSHOT / (name + ".gz")
        expected = manifest["files"][name]
        if target.exists():
            if digest(target) != expected["sha256"]:
                raise ValueError(f"Existing {target} differs; move it aside before restoring")
            continue
        if not archive.exists():
            raise FileNotFoundError(f"Missing {target}; supply the original export or local {archive}")
        if digest(archive) != expected["gzip_sha256"]:
            raise ValueError(f"Compressed snapshot checksum mismatch: {name}")
        with tempfile.NamedTemporaryFile(dir=RAW, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            try:
                with gzip.open(archive, "rb") as src:
                    shutil.copyfileobj(src, temporary)
                temporary.flush()
                temporary.close()
                if digest(temporary_path) != expected["sha256"]:
                    raise ValueError(f"Restored snapshot checksum mismatch: {name}")
                os.replace(temporary_path, target)
            finally:
                temporary_path.unlink(missing_ok=True)
    print("Exact report inputs verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "restore"), nargs="?", default="restore")
    args = parser.parse_args()
    freeze() if args.action == "freeze" else restore()
