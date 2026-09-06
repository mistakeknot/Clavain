#!/usr/bin/env python3
"""Supervise one admitted fixed Flere RPC attempt; native entries prove execution.

The tool policy is application-level enforcement, not an OS sandbox. Receipts
contain execution evidence only and never independently accept the task.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import uuid


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_atomic(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf8") as stream:
        os.chmod(temporary, 0o600)
        stream.write(value if isinstance(value, str) else json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def artifact(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


class WorkerFailure(Exception):
    def __init__(self, message, classification="worker_outcome_indeterminate"):
        super().__init__(message)
        self.classification = classification


def supervise(args):
    executable = Path(args.executable).resolve(strict=True)
    entrypoint = Path(args.entrypoint).resolve(strict=True) if args.entrypoint else executable
    project = Path(args.project).resolve(strict=True)
    profile = Path(args.profile).resolve(strict=True)
    # Both the host and worker compare canonical identity strings, including
    # macOS /tmp and /var aliases. The new output itself need not exist yet.
    output_arg = Path(args.output).absolute()
    output = output_arg.parent.resolve(strict=True) / output_arg.name
    if not Path(args.executable).is_absolute() or (args.entrypoint and not Path(args.entrypoint).is_absolute()):
        raise ValueError("Flere executable and entrypoint must be absolute")
    if not Path(args.profile).is_absolute() or profile.is_relative_to(project) or output.resolve().is_relative_to(project):
        raise ValueError("Explicit profile and output must be outside the admitted project root")
    provider, separator, model = args.model.partition("/")
    if not separator or not provider or not model:
        raise ValueError("Flere requires explicit provider/model (model may contain slashes)")
    dispatch_id = os.environ.get("IC_DISPATCH_ID", "")
    run_id = os.environ.get("IC_RUN_ID", "")
    if not dispatch_id or not run_id:
        raise ValueError("Flere requires an Intercore-admitted run and dispatch")
    prompt = Path(args.prompt_file).read_text() if args.prompt_file else sys.stdin.read()
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    # Clavain prompt assembly may add governed instructions. Preserve both the
    # admitted source hash and the exact submitted prompt hash, never equate them.
    admitted_hash = os.environ.get("IC_PROMPT_HASH", "")
    if not prompt.strip() or not admitted_hash:
        raise ValueError("Flere requires nonempty prompt and admitted prompt identity")
    attempt_dir = Path(str(output) + ".attempt")
    if args.dry_run:
        print(json.dumps({"backend": "flere", "executable": str(executable), "entrypoint": str(entrypoint), "provider": provider, "model": model, "project": str(project), "profile": str(profile), "dispatch_id": dispatch_id, "run_id": run_id, "enforcement": "application-level-canonical-root"}, sort_keys=True))
        return 0
    if Path(str(output) + ".receipt.json").exists():
        raise ValueError("A terminal receipt already exists for this output")
    attempt_dir.mkdir(mode=0o700)
    session_id = str(uuid.uuid4())
    session_dir = attempt_dir / "session"
    home = attempt_dir / "home"; home.mkdir(mode=0o700)
    started = {
        "schema": "flere.dispatch-start.v1", "run_id": run_id, "dispatch_id": dispatch_id,
        "attempt": int(os.environ.get("IC_DISPATCH_ATTEMPT", "0")), "attempt_id": dispatch_id,
        "session_id": session_id, "provider": provider, "model": model,
        "executable": str(entrypoint), "executable_sha256": sha(entrypoint),
        "launcher": str(executable), "launcher_sha256": sha(executable),
        "profile": str(profile), "profile_sha256": sha(profile / "models.json"),
        "project": str(project), "prompt_hash": admitted_hash, "submitted_prompt_sha256": prompt_hash,
        "started_at": time.time(), "independent_acceptance": False, "retry_allowed": False,
        "enrollment_id": os.environ.get("CLAVAIN_TASK_ENROLLMENT_ID") or None,
        "manifest_sha256": os.environ.get("CLAVAIN_TASK_MANIFEST_SHA256") or None,
        "cohort_id": os.environ.get("CLAVAIN_TASK_COHORT_ID") or None,
        "parent_session_id": os.environ.get("DISPATCH_SESSION_ID") or None,
        "role": os.environ.get("CLAVAIN_DISPATCH_ROLE") or None,
        "thread_id": None, "turn_id": None, "response_id": None,
    }
    configuration = {key: started[key] for key in ("provider", "model", "executable_sha256", "launcher_sha256", "profile_sha256")}
    configuration["worker_policy"] = "read-only-v1"
    started["configuration_sha256"] = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    write_atomic(attempt_dir / "started.json", started)
    write_atomic(attempt_dir / "prompt.txt", prompt)
    child = None
    deadline = time.monotonic() + args.timeout
    events_path = attempt_dir / "rpc.jsonl"
    stderr_path = attempt_dir / "stderr.log"
    receipt = {**started, "schema": "flere.dispatch-result.v1", "outcome": "error", "failure_class": "worker_outcome_indeterminate", "prompt_accepted": False, "usage": None, "usage_semantics": "fresh_session_cumulative", "measurement_coverage": "incomplete", "sandbox_effective": {"profile": "read-only-v1", "enforcement": "application-level-canonical-root", "canonical_roots": [str(project)]}, "artifacts": {}}
    sequence = 0
    settled = False
    buffer = b""
    selector = selectors.DefaultSelector()
    interrupted = None

    def stop_handler(signum, _frame):
        nonlocal interrupted
        interrupted = signum

    previous = {sig: signal.signal(sig, stop_handler) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    with events_path.open("x", encoding="utf8") as events, stderr_path.open("xb") as errors:
        def receive():
            nonlocal buffer, settled
            while True:
                if interrupted:
                    raise WorkerFailure("Host cancelled the worker", "worker_outcome_indeterminate")
                if time.monotonic() >= deadline:
                    raise WorkerFailure("Worker deadline expired")
                if b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    events.write(line.decode("utf8", errors="replace") + "\n"); events.flush()
                    try:
                        value = json.loads(line)
                    except (ValueError, UnicodeError) as error:
                        raise WorkerFailure("Malformed worker JSON") from error
                    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
                        raise WorkerFailure("Malformed worker response")
                    if value["type"] in ("extension_ui_request", "extension_error", "auto_retry_start"):
                        raise WorkerFailure("Worker requested interaction or violated fixed policy", "worker_policy")
                    if value["type"] == "agent_settled":
                        settled = True
                    return value
                ready = selector.select(min(0.1, max(0, deadline - time.monotonic())))
                if ready:
                    data = os.read(child.stdout.fileno(), 65536)
                    if not data:
                        raise WorkerFailure("Worker exited before terminal evidence")
                    buffer += data
                    if len(buffer) > 16 * 1024 * 1024:
                        raise WorkerFailure("Worker JSON line exceeded protocol limit")
                elif child.poll() is not None:
                    raise WorkerFailure("Worker process exited")

        def command(kind, **fields):
            nonlocal sequence
            sequence += 1
            identity = f"{dispatch_id}:{sequence}"
            value = {"id": identity, "type": kind, **fields}
            child.stdin.write((json.dumps(value) + "\n").encode()); child.stdin.flush()
            while True:
                response = receive()
                if response["type"] != "response":
                    continue
                if response.get("id") != identity or response.get("command") != kind or type(response.get("success")) is not bool:
                    raise WorkerFailure("Worker reply identity or shape mismatch")
                if not response["success"]:
                    raise WorkerFailure(f"Worker rejected {kind}", "worker_prompt_rejected" if kind == "prompt" else "worker_policy")
                return response.get("data")

        def verify_state(state):
            worker = state.get("worker", {}) if isinstance(state, dict) else {}
            expected = {"profile": "read-only-v1", "singlePrompt": True, "autoRetryEnabled": False, "providerMaxRetries": 0, "sandboxEffective": "tool-policy-read-only", "enforcement": "application-level-canonical-root", "canonicalRoots": [str(project)], "executable": str(entrypoint), "executableSha256": started["executable_sha256"], "profileDir": str(profile), "profileSha256": started["profile_sha256"], "sessionDir": str(session_dir)}
            if any(type(worker.get(key)) is not type(value) or worker[key] != value for key, value in expected.items()) or sorted(worker.get("activeTools", [])) != ["find", "grep", "ls", "read"]:
                raise WorkerFailure("Worker effective executable or policy identity mismatch", "worker_identity_mismatch")
            if state.get("sessionId") != session_id or state.get("model", {}).get("provider") != provider or state.get("model", {}).get("id") != model:
                raise WorkerFailure("Worker session/model identity mismatch", "worker_identity_mismatch")
            receipt["runtime_version"] = worker.get("runtimeVersion")

        try:
            argv = [str(executable)] + ([str(entrypoint)] if args.entrypoint else []) + ["--worker-rpc", "--provider", provider, "--model", model, "--profile-dir", str(profile), "--session-id", session_id, "--session-dir", str(session_dir)]
            child = subprocess.Popen(argv, cwd=project, env={"PATH": os.environ.get("PATH", os.defpath), "HOME": str(home), "LANG": "en_US.UTF-8", "PI_OFFLINE": "1", "FLERE_CODING_AGENT_DIR": str(profile)}, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, start_new_session=True)
            selector.register(child.stdout, selectors.EVENT_READ)
            state = command("get_state"); verify_state(state)
            if state.get("messageCount", 0) or state.get("isStreaming") or state.get("pendingMessageCount"):
                raise WorkerFailure("Worker session is not fresh", "worker_identity_mismatch")
            command("set_auto_retry", enabled=False); command("set_auto_compaction", enabled=False)
            command("prompt", message=prompt); receipt["prompt_accepted"] = True
            while not settled:
                receive()
            final_state = command("get_state"); verify_state(final_state)
            if final_state.get("isStreaming") or final_state.get("isCompacting") or final_state.get("pendingMessageCount"):
                raise WorkerFailure("Worker has unsettled work")
            native = command("get_entries")
            entries = native.get("entries", [])
            users = [entry for entry in entries if entry.get("type") == "message" and entry.get("message", {}).get("role") == "user"]
            assistants = [entry for entry in entries if entry.get("type") == "message" and entry.get("message", {}).get("role") == "assistant"]
            if len(users) != 1 or not assistants:
                raise WorkerFailure("Missing native entries for the prompt")
            user_content = users[0]["message"].get("content")
            user_text = user_content if isinstance(user_content, str) else "\n".join(part.get("text", "") for part in user_content if part.get("type") == "text")
            if user_text != prompt:
                raise WorkerFailure("Native user entry does not match submitted prompt")
            assistant = assistants[-1]; message = assistant["message"]
            text = "\n".join(part.get("text", "") for part in message.get("content", []) if part.get("type") == "text")
            if message.get("provider") != provider or message.get("model") != model:
                raise WorkerFailure("Final assistant content or model identity missing")
            session_file = Path(final_state.get("sessionFile", "")).resolve(strict=True)
            if not session_file.is_relative_to(session_dir.resolve()):
                raise WorkerFailure("Native session path escaped owned session directory")
            persisted = [json.loads(line) for line in session_file.read_text().splitlines()]
            if not persisted or persisted[0].get("id") != session_id or users[0] not in persisted or assistant not in persisted:
                raise WorkerFailure("Native session did not persist matching result entries")
            stats = command("get_session_stats")
            if stats.get("sessionId") != session_id:
                raise WorkerFailure("Usage session identity mismatch")
            tokens = stats.get("tokens", {})
            if any(type(tokens.get(key)) is not int or tokens[key] < 0 for key in ("input", "output", "cacheRead", "cacheWrite")):
                raise WorkerFailure("Missing or invalid usage counters")
            totals = {key: 0 for key in ("input", "output", "cacheRead", "cacheWrite")}
            seen = set()
            for entry in entries:
                if not entry.get("id") or entry["id"] in seen:
                    raise WorkerFailure("Conflicting or duplicate native entry identity")
                seen.add(entry["id"])
                native_usage = entry.get("message", {}).get("usage") or entry.get("usage")
                if native_usage is not None:
                    if any(type(native_usage.get(key)) is not int or native_usage[key] < 0 for key in totals):
                        raise WorkerFailure("Invalid native usage counters")
                    for key in totals: totals[key] += native_usage[key]
            if any(totals[key] != tokens[key] for key in totals):
                raise WorkerFailure("Native usage does not reconcile with session totals")
            receipt.update(session_file=str(session_file), user_entry_id=users[0]["id"], final_assistant_entry_id=assistant["id"], final_leaf_id=native.get("leafId"), stop_reason=message.get("stopReason"), usage={"input":tokens["input"],"output":tokens["output"],"cache_read":tokens["cacheRead"],"cache_write":tokens["cacheWrite"],"cost":stats.get("cost")}, measurement_coverage="complete")
            receipt["artifacts"]["transcript"] = artifact(session_file)
            if message.get("stopReason") != "stop":
                raise WorkerFailure("Worker final result is not a successful stop", "worker_provider_error")
            if not text.strip():
                raise WorkerFailure("Worker final answer is empty", "worker_empty_result")
            child.stdin.close(); child.stdin = None
            trailing, _ = child.communicate(timeout=min(3, max(0.1, deadline-time.monotonic())))
            if buffer or trailing:
                for line in (buffer + trailing).splitlines():
                    events.write(line.decode("utf8", errors="replace") + "\n")
                    value = json.loads(line)
                    if value.get("type") not in ("agent_settled", "agent_end"):
                        raise WorkerFailure("Unexpected worker output during shutdown")
            if child.returncode != 0:
                raise WorkerFailure("Worker failed during final shutdown")
            write_atomic(output, text + "\n")
            write_atomic(str(output) + ".summary", f"Tokens: {tokens['input'] + tokens['cacheRead'] + tokens['cacheWrite']} in / {tokens['output']} out\n")
            write_atomic(str(output) + ".verdict", "--- VERDICT ---\nSTATUS: warn\nSUMMARY: Execution completed; independent acceptance is pending.\n---\n")
            receipt.update(outcome="success", failure_class="", side_effects="none")
            receipt["artifacts"]["output"] = artifact(output)
        except (WorkerFailure, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, subprocess.TimeoutExpired) as error:
            receipt["error_message"] = str(error)
            receipt["failure_class"] = error.classification if isinstance(error, WorkerFailure) else "worker_outcome_indeterminate"
            receipt["side_effects"] = "unknown"
        finally:
            if child is not None:
                # The host owns this process group. Killing the group also reaps
                # any descendants; no unrelated interactive Flere process is touched.
                # Reap an exited leader first: macOS may report EPERM for an
                # otherwise empty group whose leader is still a zombie.
                child.poll()
                try: os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                except OSError as error:
                    receipt.update(outcome="error", failure_class="worker_outcome_indeterminate", cleanup_error=str(error))
                try: child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    except OSError as error:
                        receipt.update(outcome="error", failure_class="worker_outcome_indeterminate", cleanup_error=str(error))
                        child.kill()
                    child.wait(timeout=1)
                # The leader may have died before its descendants. Escalate the
                # owned group even then; no process-name based killing is used.
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                except OSError as error:
                    receipt.update(outcome="error", failure_class="worker_outcome_indeterminate", cleanup_error=str(error))
            if child is not None:
                for stream in (child.stdin, child.stdout):
                    if stream and not stream.closed:
                        try: stream.close()
                        except BrokenPipeError: pass
            selector.close()
            for sig, handler in previous.items(): signal.signal(sig, handler)
            events.flush(); os.fsync(events.fileno()); errors.flush(); os.fsync(errors.fileno())
    receipt["completed_at"] = time.time()
    receipt["artifacts"].update(started=artifact(attempt_dir / "started.json"), events=artifact(events_path), stderr=artifact(stderr_path), prompt=artifact(attempt_dir / "prompt.txt"))
    # The receipt is committed last. A crash before this point leaves an
    # indeterminate attempt with started/native evidence, never an inferred pass.
    write_atomic(str(output) + ".receipt.json", receipt)
    if receipt["outcome"] != "success":
        print(receipt.get("error_message", receipt["failure_class"]), file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("executable", "profile", "model", "project", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--entrypoint")
    parser.add_argument("--prompt-file")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0: parser.error("--timeout must be positive")
    try:
        return supervise(args)
    except (OSError, ValueError) as error:
        print(f"Flere configuration: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
