"""Existing report exports need no archive and must never be overwritten."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import snapshot


class ExistingInputs(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.raw, self.archives = root / "raw", root / "snapshot"
        self.raw.mkdir()
        self.archives.mkdir()
        self.target = self.raw / "commits.json"
        self.target.write_bytes(b"original export")
        manifest = {"files": {self.target.name: {
            "sha256": hashlib.sha256(self.target.read_bytes()).hexdigest(),
            "gzip_sha256": "archive is intentionally absent"}}}
        (self.archives / "manifest.json").write_text(json.dumps(manifest))
        for name, value in (("RAW", self.raw), ("SNAPSHOT", self.archives),
                            ("FILES", (self.target.name,))):
            patcher = patch.object(snapshot, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_matching_raw_export_needs_no_archive(self):
        snapshot.restore()
        self.assertEqual(self.target.read_bytes(), b"original export")

    def test_changed_raw_export_is_preserved_and_rejected(self):
        self.target.write_bytes(b"different export")
        with self.assertRaisesRegex(ValueError, "differs"):
            snapshot.restore()
        self.assertEqual(self.target.read_bytes(), b"different export")


if __name__ == "__main__":
    unittest.main()
