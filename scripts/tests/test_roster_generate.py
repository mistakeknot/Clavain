"""Negative-case coverage for scripts/roster/generate.py (PLAN-M1-r5.md §P1
Acceptance): missing, corrupt, unpinned/wrong-hash, stale and
absent-generatedAt input must each produce a diagnostic, never a passing
proposal. Stale / absent-generatedAt logic itself is also covered directly
by tests/fixtures/roster/truth-table.json via --self-test; this file drives
the real CLI end-to-end so the negative paths are exercised the same way a
real run hits them.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/roster/generate.py"
ROUTING = ROOT / "config/routing.yaml"
FAMILIES = ROOT / "config/roster-families.yaml"
SLUGS = ROOT / "config/roster-slugs.yaml"

VALID_SNAPSHOT = ROOT / "trackers-test-fixture-snapshot.json"  # unused; see setUp


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def minimal_snapshot(generated_at):
    return {
        "meta": {"generatedAt": generated_at},
        "models": [
            {"id": 1, "slug": "claude-opus-5-high", "name": "Claude Opus 5 (Adaptive Reasoning, High Effort)", "providerSlug": "anthropic"},
        ],
    }


class RosterGenerateNegativeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.out = self.base / "out"

    def run_generate(self, snapshot_path, snapshot_sha256):
        return subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--routing", str(ROUTING),
                "--families", str(FAMILIES),
                "--slugs", str(SLUGS),
                "--snapshot", str(snapshot_path),
                "--snapshot-sha256", snapshot_sha256,
                "--out", str(self.out),
            ],
            capture_output=True, text=True,
        )

    def test_missing_snapshot_is_a_diagnostic(self):
        missing = self.base / "does-not-exist.json"
        result = self.run_generate(missing, "0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr)

    def test_corrupt_snapshot_is_a_diagnostic(self):
        corrupt = self.base / "corrupt.json"
        corrupt.write_bytes(b"{not valid json")
        sha = sha256_bytes(corrupt.read_bytes())
        result = self.run_generate(corrupt, sha)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("corrupt", result.stderr)

    def test_wrong_hash_is_a_diagnostic(self):
        snap = self.base / "snapshot.json"
        snap.write_text(json.dumps(minimal_snapshot("2026-09-23T12:20:44.712Z")))
        result = self.run_generate(snap, "f" * 64)  # deliberately wrong
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sha256 mismatch", result.stderr)

    def test_stale_snapshot_is_a_diagnostic(self):
        snap = self.base / "snapshot.json"
        snap.write_text(json.dumps(minimal_snapshot("2020-01-01T00:00:00Z")))
        sha = sha256_bytes(snap.read_bytes())
        result = self.run_generate(snap, sha)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale", result.stderr)

    def test_absent_generatedat_is_a_diagnostic(self):
        snap = self.base / "snapshot.json"
        payload = minimal_snapshot(None)
        del payload["meta"]["generatedAt"]
        snap.write_text(json.dumps(payload))
        sha = sha256_bytes(snap.read_bytes())
        result = self.run_generate(snap, sha)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale", result.stderr)

    def test_self_test_fixture_passes(self):
        truth_table = ROOT / "tests/fixtures/roster/truth-table.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-test", str(truth_table)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
