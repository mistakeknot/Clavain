"""Opt-in hermetic producer seam: actual ic, dispatcher, SDK/RPC and native tools."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest


@unittest.skipUnless(os.environ.get("INTERCORE_TEST_BIN") and os.environ.get("FLERE_TEST_SOURCE"), "requires built Intercore and Flere source")
class FlereSeamTests(unittest.TestCase):
    def test_actual_admitted_worker_and_receipt(self):
        with tempfile.TemporaryDirectory(prefix="flere-seam-") as tmp:
            root = Path(tmp)
            project = root / "project"; project.mkdir()
            profile = root / "profile"; profile.mkdir()
            (project / "evidence.txt").write_text("actual native read evidence")
            (root / "secret.txt").write_text("must remain unreadable")
            source = Path(os.environ["FLERE_TEST_SOURCE"]).resolve()
            fixture = source / "packages/coding-agent/test/fixtures/worker-faux-entry.ts"
            launcher = root / "launcher"
            launcher.write_text("#!/bin/sh\nexport TSX_TSCONFIG_PATH=" + shlex.quote(str(source / "tsconfig.json")) + "\nexec " + shlex.quote(shutil.which("node")) + " --import " + shlex.quote(str(source / "node_modules/tsx/dist/loader.mjs")) + ' "$@"\n')
            launcher.chmod(0o700)
            subprocess.run([str(launcher), str(fixture), "--write-profile", str(profile)], check=True, cwd=root, capture_output=True, text=True, timeout=30)
            env = {**os.environ, "CLAVAIN_FLERE_BIN": str(launcher), "CLAVAIN_FLERE_ENTRYPOINT": str(fixture), "CLAVAIN_FLERE_PROFILE": str(profile), "CLAVAIN_CONTEXT_GATEWAY_MODE": "off", "TMPDIR": str(root)}
            # ic's explicit database safety check requires a canonical parent.
            # Keep TMPDIR unresolved to exercise the independent output alias.
            ic = [os.environ["INTERCORE_TEST_BIN"], "--db", str(root.resolve() / "ledger.db")]
            def run(*args):
                result = subprocess.run([*ic, *args], cwd=root, env=env, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout
            run("init")
            run_id = json.loads(run("--json", "run", "create", "--project="+str(project), "--goal=hermetic worker seam", "--token-budget=50000", "--budget-enforce", "--max-agents=2"))["id"]
            prompt = root / "prompt.md"; prompt.write_text("Inspect evidence.txt and verify root confinement.\n")
            dispatcher = Path(__file__).resolve().parents[1] / "scripts/dispatch.sh"
            # Exercise Intercore's default output under the Mac temp-path alias.
            dispatched = json.loads(run("--json", "dispatch", "spawn", "--type=flere", "--run-id="+run_id, "--project="+str(project), "--prompt-file="+str(prompt), "--model=governed-fixture/fixture-model", "--sandbox=read-only", "--timeout=30s", "--dispatch-sh="+str(dispatcher)))
            output = Path(json.loads(run("--json", "dispatch", "status", dispatched["id"]))["output_file"])
            receipt_path = Path(str(output)+".receipt.json")
            until = time.monotonic()+35
            while not receipt_path.exists() and time.monotonic()<until: time.sleep(0.1)
            details = ""
            errors = Path(str(output)+".attempt/stderr.log")
            if errors.exists(): details=errors.read_text()
            self.assertTrue(receipt_path.exists(), details)
            receipt=json.loads(receipt_path.read_text())
            self.assertEqual(receipt["outcome"],"success",json.dumps(receipt)+details)
            self.assertEqual(receipt["dispatch_id"],dispatched["id"])
            self.assertIn("actual native read evidence",output.read_text())
            native=[json.loads(line) for line in Path(receipt["session_file"]).read_text().splitlines()]
            tools=[entry["message"] for entry in native if entry.get("message",{}).get("role")=="toolResult"]
            self.assertEqual([tool["isError"] for tool in tools],[False,True])
            status=json.loads(run("--json","dispatch","poll",dispatched["id"]))
            if status["status"]=="running":
                time.sleep(0.2); status=json.loads(run("--json","dispatch","poll",dispatched["id"]))
            self.assertEqual(status["status"],"completed",status)
            again=json.loads(run("--json","dispatch","poll",dispatched["id"]))
            self.assertEqual(again["in_tokens"],status["in_tokens"])
            self.assertEqual(len(json.loads(run("--json","dispatch","list"))),1)
            before=status.copy()
            run("--json","dispatch","reconcile",dispatched["id"])
            self.assertEqual(json.loads(run("--json","dispatch","status",dispatched["id"])),before)


if __name__ == "__main__": unittest.main()
