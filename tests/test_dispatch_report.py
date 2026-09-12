import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dispatch_report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dispatch_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DispatchReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.sources = {}
        values = {
            "stdout_events": (
                b'{"type":"thread.started","thread_id":"thread-123"}\n'
                b'{"type":"turn.started"}\n'
                b'{"type":"item.completed","item":{"type":"agent_message"}}\n'
                b'{"type":"turn.completed","usage":{"input_tokens":12,"cached_input_tokens":3,"output_tokens":5}}\n'
            ),
            "stderr": "diagnostic café\n".encode(),
            "last_message": "complete ☃\nVERDICT: CLEAN\n".encode(),
            "summary": b"Dispatch: fixture\n",
            "verdict": b"--- VERDICT ---\nSTATUS: pass\n---\n",
        }
        for name, data in values.items():
            path = self.root / f"{name}.data"
            path.write_bytes(data)
            self.sources[name] = path

    def tearDown(self):
        self.temp.cleanup()

    def render(self, *extra):
        args = [
            sys.executable,
            str(SCRIPT),
            "render",
            "--artifacts-dir",
            str(self.artifacts),
            "--backend-code",
            "0",
            "--dispatcher-code",
            "0",
            "--classification",
            "success",
        ]
        for name, path in self.sources.items():
            args.extend(["--artifact", f"{name}={path}"])
        args.extend(extra)
        return subprocess.run(args, check=False, capture_output=True)

    def test_render_is_bounded_deterministic_and_seals_sorted_manifest(self):
        first = self.render()
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        self.assertLessEqual(len(first.stdout), 4096)
        self.assertTrue(first.stdout.endswith(b"\n"))
        report = json.loads(first.stdout)
        self.assertEqual(report["backend_process_code"], 0)
        self.assertEqual(report["dispatcher_code"], 0)
        self.assertEqual(report["native_coverage"]["status"], "complete")
        self.assertEqual(report["native"]["thread_id"], "thread-123")
        self.assertNotIn("parent_session_id", first.stdout.decode())

        manifest_bytes = (self.artifacts / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        names = [entry["logical_name"] for entry in manifest["artifacts"]]
        self.assertEqual(names, sorted(names))
        self.assertNotIn("manifest_sha256", manifest)
        self.assertEqual(report["manifest_sha256"], hashlib.sha256(manifest_bytes).hexdigest())
        for path in self.artifacts.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_mode & 0o077, 0)

        replay = subprocess.run(
            [sys.executable, str(SCRIPT), "replay", "--artifacts-dir", str(self.artifacts)],
            check=False,
            capture_output=True,
        )
        self.assertEqual(replay.returncode, 0, replay.stderr.decode())
        self.assertEqual(replay.stdout, first.stdout)

    def test_malformed_or_contradictory_events_make_counters_unknown(self):
        self.sources["stdout_events"].write_bytes(
            b'{"type":"thread.started","thread_id":"thread-a"}\n'
            b'not-json\n'
            b'{"type":"thread.started","thread_id":"thread-b"}\n'
        )
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        report = json.loads(result.stdout)
        self.assertEqual(report["native_coverage"]["status"], "incomplete")
        self.assertNotIn("native", report)
        self.assertTrue(report["counters"])
        self.assertTrue(all(counter["value"] is None for counter in report["counters"]))
        self.assertTrue(all(counter["status"] == "unknown" for counter in report["counters"]))

    def test_duplicate_event_keys_are_not_valid_native_identity(self):
        self.sources["stdout_events"].write_bytes(
            b'{"type":"thread.started","thread_id":"thread-a","thread_id":"thread-b"}\n'
        )
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        report = json.loads(result.stdout)
        self.assertEqual(report["native_coverage"]["status"], "incomplete")
        self.assertNotIn("native", report)
        self.assertTrue(all(counter["value"] is None for counter in report["counters"]))

    def test_missing_and_nonregular_required_artifacts_are_unusable(self):
        self.sources.pop("summary")
        self.sources["verdict"].unlink()
        os.mkfifo(self.sources["verdict"])
        result = self.render()
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertTrue(report["unusable"])
        self.assertEqual(report["dispatcher_code"], 1)
        self.assertEqual(report["recovery"], "full artifacts in output parent")
        self.assertEqual(report["digests"]["summary"]["status"], "missing")
        self.assertEqual(report["digests"]["verdict"]["status"], "nonregular")

    def test_unknown_backend_status_and_process_evidence_are_preserved(self):
        process = self.root / "process.data"
        process.write_text(
            '{"backend_process_code":null,"wrapper_signal_code":143,"capture_status":"complete"}\n',
            encoding="utf-8",
        )
        result = self.render(
            "--backend-code",
            "unknown",
            "--dispatcher-code",
            "143",
            "--classification",
            "terminal_error",
            "--artifact",
            f"process={process}",
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        report = json.loads(result.stdout)
        self.assertIsNone(report["backend_process_code"])
        self.assertEqual(report["dispatcher_code"], 143)
        self.assertEqual(report["digests"]["process"]["status"], "available")
        replay = subprocess.run(
            [sys.executable, str(SCRIPT), "replay", "--artifacts-dir", str(self.artifacts)],
            check=False,
            capture_output=True,
        )
        self.assertEqual(replay.returncode, 0, replay.stderr.decode())
        self.assertEqual(replay.stdout, result.stdout)

    def test_primary_event_write_failure_terminates_and_reaps_backend(self):
        process_script = ROOT / "scripts" / "dispatch_process.py"
        spec = importlib.util.spec_from_file_location("dispatch_process", process_script)
        process_module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(process_module)
        events = self.root / "events.jsonl"
        events.touch()
        stderr = self.root / "process.stderr"
        status = self.root / "process.json"
        pid_file = self.root / "backend.pid"

        class FailingSink:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def write(self, _data):
                raise OSError("fixture event sink failure")

        original_open = Path.open

        def selective_open(path, *args, **kwargs):
            if path == events:
                return FailingSink()
            return original_open(path, *args, **kwargs)

        command = [
            sys.executable,
            "-c",
            (
                "import os,signal,time\n"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                "pid=os.fork()\n"
                "if pid:\n"
                " print('parent-event',flush=True);time.sleep(.1);os._exit(0)\n"
                f"open({str(pid_file)!r},'w').write(str(os.getpid()))\n"
                "print('child-event',flush=True);time.sleep(30)\n"
            ),
        ]
        args = argparse.Namespace(events=events, stderr=stderr, status=status, review_events=None, command=command)
        started = time.monotonic()
        with mock.patch.object(Path, "open", selective_open):
            result = process_module.run(args)
        self.assertEqual(result, 1)
        self.assertLess(time.monotonic() - started, 6)
        evidence = json.loads(status.read_text())
        self.assertEqual(evidence["backend_process_code"], 0)
        self.assertEqual(evidence["capture_status"], "failed")
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)

    def test_optional_fields_degrade_whole_without_utf8_truncation(self):
        module = load_module()
        model = module.ReportModel(
            backend_code=0,
            dispatcher_code=0,
            classification="success",
            unusable=False,
            native_coverage={"status": "complete", "reason": None},
            digests={name: {"status": "available", "sha256": "a" * 64} for name in module.DIGEST_SLOTS},
            manifest_sha256="b" * 64,
            diagnostics=["雪" * 5000],
            counters=[{"name": "turns", "value": 1, "status": "observed"}],
            native={"thread_id": "thread-123"},
            artifacts=[{"logical_name": "stdout_events", "path": "stdout.events.jsonl"}],
            recovery="full artifacts in output parent",
        )
        encoded = module.encode_bounded_report(model)
        self.assertLessEqual(len(encoded), 4096)
        self.assertTrue(encoded.endswith(b"\n"))
        decoded = json.loads(encoded)
        self.assertNotIn("diagnostics", decoded)
        self.assertIn("diagnostics", decoded["omissions"])
        encoded.decode("utf-8")

    def test_replay_detects_tampering_and_emits_unusable_report(self):
        rendered = self.render()
        self.assertEqual(rendered.returncode, 0)
        (self.artifacts / "last-message.txt").write_text("tampered", encoding="utf-8")
        replay = subprocess.run(
            [sys.executable, str(SCRIPT), "replay", "--artifacts-dir", str(self.artifacts)],
            check=False,
            capture_output=True,
        )
        self.assertEqual(replay.returncode, 2)
        report = json.loads(replay.stdout)
        self.assertTrue(report["unusable"])
        self.assertEqual(report["classification"], "presentation_failure")

    def test_replay_rejects_unmanifested_artifact(self):
        rendered = self.render()
        self.assertEqual(rendered.returncode, 0)
        (self.artifacts / "injected.txt").write_text("not sealed", encoding="utf-8")
        replay = subprocess.run(
            [sys.executable, str(SCRIPT), "replay", "--artifacts-dir", str(self.artifacts)],
            check=False,
            capture_output=True,
        )
        self.assertEqual(replay.returncode, 2)
        report = json.loads(replay.stdout)
        self.assertIn("manifest_directory_membership_mismatch", report["diagnostics"])

    def test_extremely_long_recovery_path_uses_bounded_unusable_fallback(self):
        module = load_module()
        model = module.ReportModel(
            backend_code=0,
            dispatcher_code=0,
            classification="success",
            unusable=False,
            native_coverage={"status": "complete", "reason": None},
            digests={name: {"status": "available", "sha256": "a" * 64} for name in module.DIGEST_SLOTS},
            manifest_sha256="b" * 64,
            diagnostics=[],
            counters=[],
            native=None,
            artifacts=[],
            recovery="雪" * 5000,
        )
        encoded = module.encode_bounded_report(model)
        self.assertLessEqual(len(encoded), 4096)
        report = json.loads(encoded)
        self.assertTrue(report["unusable"])
        self.assertEqual(report["recovery"], "full artifacts in output parent")
        self.assertRegex(report["manifest_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
