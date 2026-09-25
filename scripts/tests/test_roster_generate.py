"""CLI coverage for scripts/roster/generate.py (PLAN-M1-r5.md §P1
Acceptance): missing, corrupt, unpinned/wrong-hash, stale, absent and
future generatedAt input, a missing or mismatched --expect-base must each
produce a diagnostic, never a passing proposal. The rules themselves are
covered end to end by tests/fixtures/roster/truth-table.json via
--self-test; this file drives the real CLI so the negative paths are
exercised the same way a real run hits them.
"""
import hashlib
import json
import os
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
TRUTH_TABLE = ROOT / "tests/fixtures/roster/truth-table.json"

# The pinned evidence snapshot lives in the mk-rpnv.9 tracker, outside the repo.
EVIDENCE_SNAPSHOT = Path("/home/mk/trackers/quilan/rpnv9/evidence/agmodb-snapshot-ff3f250-20260923T122044Z.json")
EVIDENCE_SHA256 = "510dfcc8bb2243e456faa427587b29480174e8bbe16f2b9fe0deb2047b2f2bad"


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
        self.routing_sha = sha256_bytes(ROUTING.read_bytes())

    def run_generate(self, snapshot_path, snapshot_sha256, expect_base="routing"):
        cmd = [
            sys.executable, str(SCRIPT),
            "--routing", str(ROUTING),
            "--families", str(FAMILIES),
            "--slugs", str(SLUGS),
            "--snapshot", str(snapshot_path),
            "--snapshot-sha256", snapshot_sha256,
            "--out", str(self.out),
        ]
        if expect_base is not None:
            cmd += ["--expect-base", self.routing_sha if expect_base == "routing" else expect_base]
        result = subprocess.run(cmd, capture_output=True, text=True)
        # N4: routing.yaml is never touched, refusals included.
        self.assertEqual(sha256_bytes(ROUTING.read_bytes()), self.routing_sha)
        return result

    def write_snapshot(self, generated_at):
        snap = self.base / "snapshot.json"
        payload = minimal_snapshot(generated_at)
        if generated_at is None:
            del payload["meta"]["generatedAt"]
        snap.write_text(json.dumps(payload))
        return snap, sha256_bytes(snap.read_bytes())

    def assert_refused_without_patch(self, result, needle):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(needle, result.stderr)
        self.assertFalse((self.out / "routing.proposed.patch").exists())

    def test_missing_snapshot_is_a_diagnostic(self):
        result = self.run_generate(self.base / "does-not-exist.json", "0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr)

    def test_corrupt_snapshot_is_a_diagnostic(self):
        corrupt = self.base / "corrupt.json"
        corrupt.write_bytes(b"{not valid json")
        result = self.run_generate(corrupt, sha256_bytes(corrupt.read_bytes()))
        self.assert_refused_without_patch(result, "corrupt")

    def test_wrong_hash_is_a_diagnostic(self):
        snap, _ = self.write_snapshot("2026-09-23T12:20:44.712Z")
        result = self.run_generate(snap, "f" * 64)  # deliberately wrong
        self.assert_refused_without_patch(result, "sha256 mismatch")

    def test_stale_snapshot_is_a_diagnostic(self):
        snap, sha = self.write_snapshot("2020-01-01T00:00:00Z")
        result = self.run_generate(snap, sha)
        self.assert_refused_without_patch(result, "stale")
        record = json.loads((self.out / "eligibility.json").read_text())
        self.assertEqual(record["status"], "refused")
        self.assertIs(record["promotion_ready"], False)

    def test_absent_generatedat_is_a_diagnostic(self):
        snap, sha = self.write_snapshot(None)
        result = self.run_generate(snap, sha)
        self.assert_refused_without_patch(result, "stale")

    def test_future_generatedat_is_a_diagnostic(self):
        snap, sha = self.write_snapshot("2099-01-01T00:00:00Z")
        result = self.run_generate(snap, sha)
        self.assert_refused_without_patch(result, "future")

    def test_expect_base_is_required(self):
        snap, sha = self.write_snapshot("2026-09-23T12:20:44.712Z")
        result = self.run_generate(snap, sha, expect_base=None)
        self.assertEqual(result.returncode, 1)
        self.assertIn("--expect-base", result.stderr)
        self.assertFalse(self.out.exists())

    def test_expect_base_mismatch_is_a_diagnostic(self):
        snap, sha = self.write_snapshot("2026-09-23T12:20:44.712Z")
        result = self.run_generate(snap, sha, expect_base="0" * 64)
        self.assert_refused_without_patch(result, "--expect-base mismatch")

    def test_self_test_fixture_passes(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-test", str(TRUTH_TABLE)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("passed", result.stdout)

    def test_effort_parse_is_hash_seed_independent(self):
        # B3: "Xhigh Effort" must parse as xhigh under every hash seed, and the
        # whole truth table must agree across seeds.
        probe = (
            "import importlib.util, sys;"
            f"spec = importlib.util.spec_from_file_location('g', {str(SCRIPT)!r});"
            "g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g);"
            "row = g.parse_snapshot_row({'slug': 'claude-sonnet-5-xhigh', 'providerSlug': 'anthropic',"
            " 'name': 'Claude Sonnet 5 (Adaptive Reasoning, Xhigh Effort)'}, set());"
            "print(row['effort'], row['reasoning_mode'])"
        )
        for seed in ("0", "1", "2", "5", "7", "31337"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            parsed = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env)
            self.assertEqual(parsed.stdout.strip(), "xhigh reasoning", parsed.stderr)
            table = subprocess.run([sys.executable, str(SCRIPT), "--self-test", str(TRUTH_TABLE)],
                                   capture_output=True, text=True, env=env)
            self.assertEqual(table.returncode, 0, f"seed {seed}: {table.stdout}{table.stderr}")

    @unittest.skipUnless(EVIDENCE_SNAPSHOT.exists(), "pinned evidence snapshot not present on this host")
    def test_real_snapshot_keeps_validation_sol(self):
        # B1 on the real path: validation-sol is flagged, never removed.
        result = self.run_generate(EVIDENCE_SNAPSHOT, EVIDENCE_SHA256)
        if result.returncode == 2 and "stale" in result.stderr:
            self.skipTest("pinned snapshot is past its freshness deadline")
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads((self.out / "eligibility.json").read_text())
        self.assertIs(record["promotion_ready"], False)
        self.assertNotIn("validation-sol", record["removals"])
        self.assertIn("rule1/validation/sol", record["flags"]["validation-sol"])
        self.assertEqual(record["heads_changed"], [])
        self.assertTrue((self.out / "routing.proposed.patch").exists())


if __name__ == "__main__":
    unittest.main()
