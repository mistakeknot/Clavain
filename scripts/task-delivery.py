#!/usr/bin/env python3
"""Enroll, bind, export and report measured delivery through Intercore decisions.

No task database is created. The required --db identifies the authoritative
Intercore store. JSON files are receipts or deterministic evidence exports.

  task-delivery.py --db PATH record --kind enrollment --record receipt.json
  task-delivery.py --db PATH export --cohort ID --output manifest.json
  task-delivery.py --db PATH dispatch --enrollment-id ID --role deep-execution -- ...
  task-delivery.py --db PATH report --cohort ID [--profiler PATH]

Bindings carry native identities as observed; use identity_coverage=incomplete
and missing_identity_reason when the execution adapter cannot supply one.
Acceptance records require a separate reviewer model and an authoritative
native reviewer binding. Execution adapters never create acceptance records.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

PREFIX = "measured-delivery-"
KINDS = {"enrollment", "binding", "execution", "acceptance", "intervention", "reconciliation", "dispatch-request"}
ROLES = {"main-integrator", "scout", "routine-execution", "deep-execution", "validation",
         "release-preparation", "cross-lab-review"}
CANONICAL_ROOT = Path(__file__).resolve().parent.parent
INTERSTAT_PROFILE = CANONICAL_ROOT.parent.parent / "interverse/interstat/scripts/profile.py"
DISPATCH_ENV_KEYS = frozenset({
    "PATH", "HOME", "TMPDIR", "TMP", "TEMP", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
    "TERM", "COLORTERM", "TERM_PROGRAM", "TERM_PROGRAM_VERSION", "NO_COLOR", "CLICOLOR", "SSH_AUTH_SOCK",
    "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_FEDERATION_RULE_ID", "OPENAI_IDENTITY_TOKEN_FILE", "OPENAI_WORKLOAD_IDENTITY_CONTEXT",
    "CODEX_CA_CERTIFICATE", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "KIMI_API_KEY", "KIMI_CODE_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
    "DISPATCH_SESSION_ID", "CLAUDE_SESSION_ID", "CODEX_SESSION_ID", "CODEX_THREAD_ID", "CLAVAIN_RUN_ID",
    "CODEX_CI", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED",
    "CLAVAIN_CLAUDE_PERMISSION_MODE", "CLAVAIN_429_MAX_RETRIES", "CLAVAIN_429_BACKOFF_SECONDS",
})
TASK_ENV_KEYS = frozenset({"CLAVAIN_TASK_ENROLLMENT_ID", "CLAVAIN_TASK_COHORT_ID", "CLAVAIN_TASK_MANIFEST_SHA256",
                         "CLAVAIN_TASK_INTERCORE_DB", "CLAVAIN_DISPATCH_ID", "CLAVAIN_BEAD_ID"})
# Host metadata describes the caller; it neither selects nor configures a child.
# Drop these exact names rather than forwarding them or widening prefix exceptions.
DROPPED_HOST_ENV_KEYS = frozenset({"CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PROJECT_DIR"})


def dispatch_environment():
    """Keep authentication/identity without forwarding arbitrary CLI configuration."""
    reserved = ("CODEX_", "OPENAI_", "ANTHROPIC_", "CLAUDE_", "CLAVAIN_", "KIMI_", "INTERSPECT_", "INTERFERE_")
    rejected = [key for key, value in os.environ.items() if value and key.startswith(reserved) and
                key not in DISPATCH_ENV_KEYS | TASK_ENV_KEYS | DROPPED_HOST_ENV_KEYS and
                not (key == "CLAVAIN_REQUIRE_USAGE" and value == "0")]
    if rejected:
        raise ValueError("enrolled dispatch rejects configuration environment overrides: " + ", ".join(sorted(rejected)))
    return {key: value for key, value in os.environ.items() if key in DISPATCH_ENV_KEYS or
            key.startswith("LC_") and re.fullmatch(r"LC_[A-Z_]+", key)}


def observe_execution(engine, workdir, profile):
    """Hash observed launcher/configuration sources, never credential contents.

    This is a pre-launch observation, not proof of a running process inode or
    every effective runtime setting. Full configuration coverage stays unknown.
    """
    launcher = shutil.which(engine)
    executable = str(Path(launcher).resolve()) if launcher else None
    home, workdir = Path.home(), Path(workdir).resolve()
    files = []
    if engine == "codex":
        paths = [home / ".codex/config.toml", Path("/etc/codex/config.toml"), Path("/etc/codex/requirements.toml")]
        paths += [p / ".codex/config.toml" for p in (workdir, *workdir.parents)]
    elif engine == "claude":
        paths = [home / ".claude/settings.json", Path("/Library/Application Support/ClaudeCode/managed-settings.json")]
        paths += [p / ".claude" / name for p in (workdir, *workdir.parents) for name in ("settings.json", "settings.local.json")]
    else:
        paths = []
    for path in dict.fromkeys(paths):
        item = dict(path=str(path), exists=path.exists())
        try:
            if path.exists(): item.update(resolved_path=str(path.resolve()), sha256=sha256(path))
        except OSError:
            item["unreadable"] = True
        files.append(item)
    observation = dict(files=files, resolved_profile=profile, environment_names=sorted(os.environ),
        scope="observed configuration sources and resolved profile; no credential values or full effective-config claim")
    return dict(executable=executable, executable_sha256=sha256(executable) if executable else None,
        executable_identity_basis="resolved_launcher_file_at_audit", configuration_sha256=None, configuration_coverage="partial",
        configuration_observation=observation,
        configuration_observation_sha256=hashlib.sha256(canonical(observation).encode()).hexdigest())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def context(record):
    value = record.get("context_json")
    value = json.loads(value) if isinstance(value, str) else value
    if not isinstance(value, dict):
        raise ValueError(f"decision {record.get('id')} has malformed context")
    return value


def enrolled(records):
    result = {}
    for record in sorted(records, key=lambda r: r["id"]):
        if record.get("rule_matched") != PREFIX + "enrollment":
            continue
        value = context(record)
        ident = value.get("enrollment_id")
        if not isinstance(ident, str) or not ident:
            raise ValueError("enrollment decision has no enrollment_id")
        if ident in result:
            if canonical(context(result[ident])) != canonical(value):
                raise ValueError(f"conflicting enrollment {ident}")
            continue
        result[ident] = record
    return result


def required(value, *fields):
    for field in fields:
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError(f"{field} must be a nonempty string")


def valid_hash(value, field):
    if not isinstance(value.get(field), str) or not re.fullmatch(r"[0-9a-f]{64}", value[field]):
        raise ValueError(f"{field} must be a sha256 hash")


def valid_time(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("enrolled_at must include timezone")


def invoke_profiler(profiler, manifest):
    path = Path(profiler).resolve()
    identity = dict(path=str(path), sha256=sha256(path), canonical=path == INTERSTAT_PROFILE.resolve())
    result = subprocess.run([sys.executable, str(path), "--task-manifest", str(manifest), "--json"],
                            text=True, capture_output=True, check=False)
    if sha256(path) != identity["sha256"]:
        raise ValueError("profiler source changed during invocation")
    if result.returncode not in (0, 1, 2) or not result.stdout.strip():
        raise ValueError("profiler invocation failed")
    report = json.loads(result.stdout)
    if not isinstance(report, dict):
        raise ValueError("profiler output must be an object")
    report["profiler"] = identity
    return report, result.returncode


def require_reviewer_native_evidence(enrollment, reviewer, bindings):
    """Ask the strict producer to verify native identity before recording a verdict."""
    task = context(enrollment) | dict(decision_id=enrollment["id"])
    manifest = dict(schema_version=1, cohort_id=task["cohort_id"], tasks=[task], bindings=bindings)
    with tempfile.TemporaryDirectory(prefix="task-delivery-reviewer-") as temp:
        path = Path(temp) / "manifest.json"
        path.write_text(canonical(manifest))
        report, _ = invoke_profiler(INTERSTAT_PROFILE, path)
    if not any(p.get("binding_decision_id") == reviewer["binding_decision_id"] and
               p.get("native_identity_verified") is True for p in report.get("binding_identity_evidence", [])):
        raise ValueError("independent acceptance requires valid matching reviewer native evidence")


def validate_record(kind, value, records, *, verify_native=True):
    if kind not in KINDS or not isinstance(value, dict):
        raise ValueError("unknown record kind or non-object receipt")
    canonical(value)
    required(value, "cohort_id")
    if kind == "enrollment":
        required(value, "enrollment_id", "bead_id", "objective", "enrolled_at", "role", "model", "parent_session_id")
        valid_hash(value, "manifest_sha256")
        valid_time(value["enrolled_at"])
        if value.get("implementation_dispatched") is not False:
            raise ValueError("enrollment must precede implementation dispatch")
        previous = enrolled(records).get(value["enrollment_id"])
        if previous and canonical(context(previous)) != canonical(value):
            raise ValueError("conflicting enrollment identity reuse")
        return value
    if kind == "binding" and value.get("allocation") == "cohort_shared":
        if value.get("enrollment_id"):
            raise ValueError("shared binding cannot allocate to an enrollment")
        peers = [context(r) for r in enrolled(records).values() if context(r)["cohort_id"] == value["cohort_id"]]
        if not peers:
            raise ValueError("shared binding requires an enrolled cohort")
        if value.get("manifest_sha256") not in {p["manifest_sha256"] for p in peers}:
            raise ValueError("shared binding manifest does not match cohort")
        if not isinstance(value.get("since"), str):
            raise ValueError("shared binding requires a prospective cohort boundary")
        valid_time(value["since"])
        if dt.datetime.fromisoformat(value["since"].replace("Z", "+00:00")) < min(
            dt.datetime.fromisoformat(p["enrolled_at"].replace("Z", "+00:00")) for p in peers):
            raise ValueError("shared boundary precedes prospective cohort enrollment")
    else:
        required(value, "enrollment_id")
        enrollment = enrolled(records).get(value["enrollment_id"])
        if enrollment is None:
            raise ValueError("record requires existing prospective enrollment")
        parent = context(enrollment)
        if value["cohort_id"] != parent["cohort_id"]:
            raise ValueError("record cohort differs from enrollment")
        if kind in {"binding", "dispatch-request"} and value.get("manifest_sha256", parent["manifest_sha256"]) != parent["manifest_sha256"]:
            raise ValueError("binding manifest differs from enrollment")
    if kind == "binding":
        if value.get("allocation") not in (None, "cohort_shared", value.get("enrollment_id")):
            raise ValueError("binding allocation differs from enrollment")
        required(value, "provider", "role", "model")
        if value.get("evidence_path") is not None and (not isinstance(value["evidence_path"], str) or not Path(value["evidence_path"]).is_absolute()):
            raise ValueError("binding evidence_path must be absolute")
        valid_hash(value, "manifest_sha256")
        if value.get("dispatch_id") and value["role"] not in ROLES:
            raise ValueError("canonical dispatch binding requires a governed role")
        if value.get("evidence_sha256") is not None:
            valid_hash(value, "evidence_sha256")
        supersedes = value.get("supersedes_binding_decision_id")
        if supersedes is not None:
            original = next((r for r in records if r["id"] == supersedes and r.get("rule_matched") == PREFIX + "binding"), None)
            if original is None:
                raise ValueError("binding correction requires an existing binding decision")
            before = context(original)
            if any(before.get(field) != value.get(field) for field in ("enrollment_id", "allocation", "cohort_id", "manifest_sha256")):
                raise ValueError("binding correction cannot change allocation or enrollment")
            required(value, "correction_reason")
            if not value.get("correction_evidence_refs"):
                raise ValueError("binding correction requires native correction_evidence_refs")
            if any(context(r).get("supersedes_binding_decision_id") == supersedes and
                   canonical(context(r)) != canonical(value) for r in records if r.get("rule_matched") == PREFIX + "binding"):
                raise ValueError("binding already corrected; supersede its latest correction")
        identity_fields = ("session_id", "thread_id", "attempt_id", "configuration_sha256", "executable", "executable_sha256", "evidence_path")
        missing = [field for field in identity_fields if not value.get(field)]
        if missing:
            if value.get("identity_coverage") != "incomplete":
                raise ValueError("missing native identity requires identity_coverage=incomplete")
            required(value, "missing_identity_reason")
        else:
            required(value, *identity_fields)
            valid_hash(value, "configuration_sha256")
            valid_hash(value, "executable_sha256")
    elif kind == "acceptance":
        required(value, "status", "reviewer_identity", "producer_identity", "reviewer_model", "producer_model")
        if value["reviewer_model"] == "unknown" or value["producer_model"] == "unknown":
            raise ValueError("acceptance requires known native model identity")
        if value["status"] not in {"accepted", "rejected", "needs_work"}:
            raise ValueError("unknown acceptance status")
        if value["reviewer_identity"] == value["producer_identity"] or value["reviewer_model"] == value["producer_model"]:
            raise ValueError("acceptance requires independent reviewer identity and model")
        if not isinstance(value.get("evidence_refs"), list) or not value["evidence_refs"]:
            raise ValueError("acceptance requires independent evidence_refs")
        bindings = [context(r) | dict(binding_decision_id=r["id"]) for r in records
                    if r.get("rule_matched") == PREFIX + "binding" and context(r).get("enrollment_id") == value["enrollment_id"]]
        superseded = {b.get("supersedes_binding_decision_id") for b in bindings}
        bindings = [b for b in bindings if b["binding_decision_id"] not in superseded]
        producers = [b for b in bindings if b.get("role") not in {"validation", "cross-lab-review"}] + [parent]
        producer_models = {b.get("model") for b in producers if b.get("model")}
        producer_ids = {b.get(k) for b in producers for k in ("session_id", "thread_id", "parent_session_id") if b.get(k)}
        reviewer = next((b for b in bindings if b["binding_decision_id"] == value.get("reviewer_binding_decision_id")), None)
        if (value["producer_model"] not in producer_models or value["producer_identity"] not in producer_ids or
            value["reviewer_model"] in producer_models or value["reviewer_identity"] in producer_ids or
            not reviewer or reviewer.get("role") not in {"validation", "cross-lab-review"} or
            reviewer.get("model") != value["reviewer_model"] or
            value["reviewer_identity"] not in {reviewer.get("session_id"), reviewer.get("thread_id")}):
            raise ValueError("independent acceptance must match enrolled producers and an authoritative reviewer binding")
        if verify_native:
            require_reviewer_native_evidence(enrollment, reviewer, bindings)
    elif kind == "execution":
        required(value, "execution_status", "attempt_id")
        if value["execution_status"] not in {"started", "running", "completed", "failed", "abandoned", "cancelled"}:
            raise ValueError("unknown execution status")
        if not value.get("evidence_refs"):
            raise ValueError("execution requires evidence_refs")
        for record in records:
            if record.get("rule_matched") != PREFIX + "execution":
                continue
            previous = context(record)
            if previous.get("attempt_id") == value["attempt_id"] and any(
                previous.get(field) != value.get(field) for field in ("enrollment_id", "cohort_id")):
                raise ValueError("execution attempt identity belongs to a different enrollment")
            if (previous.get("attempt_id") == value["attempt_id"] and
                previous.get("execution_status") in {"completed", "failed", "abandoned", "cancelled"} and
                canonical(previous) != canonical(value)):
                raise ValueError("terminal attempts are immutable; append reconciliation instead")
    elif kind == "intervention":
        required(value, "kind")
        minutes = value.get("active_minutes_estimate")
        if minutes is not None and (type(minutes) not in (int, float) or not math.isfinite(minutes) or minutes < 0):
            raise ValueError("active_minutes_estimate must be explicit and nonnegative")
    elif kind == "reconciliation":
        required(value, "attempt_id", "outcome")
        if type(value.get("terminal_decision_id")) is not int or not value.get("evidence_refs"):
            raise ValueError("reconciliation requires terminal_decision_id and evidence_refs")
        original = next((r for r in records if r["id"] == value["terminal_decision_id"]), None)
        if (not original or original.get("rule_matched") != PREFIX + "execution" or
            context(original).get("execution_status") not in {"completed", "failed", "abandoned", "cancelled"} or
            any(context(original).get(field) != value.get(field) for field in ("attempt_id", "enrollment_id", "cohort_id"))):
            raise ValueError("reconciliation requires its exact own terminal execution decision")
    elif kind == "dispatch-request":
        required(value, "dispatch_id", "role")
        for previous in records:
            if previous.get("rule_matched") == PREFIX + kind and context(previous).get("dispatch_id") == value["dispatch_id"]:
                if canonical(context(previous)) != canonical(value):
                    raise ValueError("conflicting dispatch request identity reuse")
    return value


def export_manifest(records, cohort):
    originals = enrolled(records)
    tasks, bindings, dispatches, used = {}, [], {}, set()
    binding_history = []
    for ident, record in originals.items():
        value = context(record)
        if value["cohort_id"] != cohort:
            continue
        tasks[ident] = value | dict(decision_id=record["id"], execution_status=value.get("execution_status", "enrolled"),
                                   decision_recorded_at=record.get("decided_at"),
                                   independent_acceptance="pending", human_interventions=[],
                                   execution_records=[], reconciliations=[])
        used.add(record["id"])
    if not tasks:
        raise ValueError(f"no enrollments found for cohort {cohort}")
    for record in sorted(records, key=lambda r: r["id"]):
        rule = record.get("rule_matched", "")
        if not rule.startswith(PREFIX) or rule == PREFIX + "enrollment":
            continue
        value = context(record)
        if value.get("cohort_id") != cohort:
            continue
        kind = rule[len(PREFIX):]
        if kind not in KINDS:
            raise ValueError(f"unknown measured-delivery decision kind {kind}")
        # Replay authoritative decisions without rewriting historical verdicts.
        # The profiler re-verifies evidence before reporting acceptance_verified.
        validate_record(kind, value, [r for r in records if r["id"] < record["id"]], verify_native=False)
        used.add(record["id"])
        value = value | dict(decision_id=record["id"])
        if kind == "binding":
            binding_history.append(value)
            supersedes = value.get("supersedes_binding_decision_id")
            if supersedes is not None:
                bindings = [b for b in bindings if b["binding_decision_id"] != supersedes]
            bindings.append(value | dict(binding_decision_id=record["id"]))
            continue
        task = tasks.get(value.get("enrollment_id"))
        if task is None:
            raise ValueError("decision points outside its enrolled cohort")
        if kind == "acceptance":
            task["independent_acceptance"] = value
        elif kind == "execution":
            task["execution_records"].append(value)
            task["execution_status"] = value["execution_status"]
        elif kind == "intervention":
            task["human_interventions"].append(value)
        elif kind == "reconciliation":
            task["reconciliations"].append(value)
        elif kind == "dispatch-request":
            dispatches[value["dispatch_id"]] = value
    # Existing execution lifecycle decisions supply attempts; they confer no
    # acceptance. A later explicit binding can repair previously absent identity.
    audit_attempts = {}
    for record in sorted(records, key=lambda r: r["id"]):
        if record.get("rule_matched") != "dispatch-profile":
            continue
        value = context(record)
        dispatch_id = value.get("dispatch_id") or record.get("dispatch_id")
        request = dispatches.get(dispatch_id)
        if request is None:
            continue
        used.add(record["id"])
        task = tasks[request["enrollment_id"]]
        if "task_envelope" in value:
            envelope = value["task_envelope"]
            if not isinstance(envelope, dict) or any(envelope.get(field) != request.get(field, task.get(field))
                for field in ("enrollment_id", "manifest_sha256", "cohort_id")):
                raise ValueError("dispatch audit task envelope differs from authoritative dispatch request")
        attempt = value.get("attempt_id")
        task["execution_records"].append(value | dict(decision_id=record["id"]))
        if value.get("state"):
            task["latest_attempt_status"] = value["state"]
        audit_attempts[(dispatch_id, attempt)] = (record, value)
    for dispatch_id, request in dispatches.items():
        if not any(key[0] == dispatch_id for key in audit_attempts):
            audit_attempts[(dispatch_id, None)] = ({"id": request["decision_id"]}, {})
    for (dispatch_id, attempt), (record, value) in audit_attempts.items():
        request = dispatches[dispatch_id]
        task = tasks[request["enrollment_id"]]
        execution, result = value.get("execution", {}), value.get("result", {})
        if attempt and any(b.get("attempt_id") == attempt and b.get("enrollment_id") == task["enrollment_id"] for b in bindings):
            continue
        bindings.append(dict(enrollment_id=task["enrollment_id"], cohort_id=cohort,
            manifest_sha256=task["manifest_sha256"], provider=execution.get("backend"),
            session_id=execution.get("session_id") or None, thread_id=execution.get("thread_id") or None,
            attempt_id=attempt, dispatch_id=dispatch_id, run_id=value.get("run_id"),
            role=value.get("role", request.get("role")), model=execution.get("model"),
            configuration_sha256=execution.get("configuration_sha256"),
            executable=execution.get("executable"), executable_sha256=execution.get("executable_sha256"),
            parent_session_id=value.get("parent_session_id"), evidence_path=execution.get("event_log") or None,
            identity_coverage="incomplete", missing_identity_reason="dispatch audit does not establish complete native usage binding",
            audit_decision_id=record["id"] if value else None,
            dispatch_request_decision_id=request["decision_id"], terminal_receipt=result.get("terminal_receipt")))
    for task in tasks.values():
        # Manual execution receipts are attempts too, including failed repairs.
        # Export missing bindings explicitly; do not invent native identities.
        for execution in task["execution_records"]:
            attempt = execution.get("attempt_id")
            if not attempt or any(b.get("attempt_id") == attempt and b.get("enrollment_id") == task["enrollment_id"] for b in bindings):
                continue
            bindings.append(dict(enrollment_id=task["enrollment_id"], cohort_id=cohort,
                manifest_sha256=task["manifest_sha256"], attempt_id=attempt,
                identity_coverage="incomplete", missing_identity_reason="execution receipt has no native usage binding",
                execution_decision_id=execution["decision_id"], evidence_refs=execution.get("evidence_refs", [])))
    return dict(schema_version=1, cohort_id=cohort, cohort_kind="internal-tooling", tasks=list(tasks.values()),
                bindings=bindings, binding_history=binding_history, authoritative_decision_ids=sorted(used),
                authority=dict(kind="intercore-routing-decisions"),
                decisions_sha256=hashlib.sha256(canonical([r for r in sorted(records, key=lambda r: r["id"]) if r["id"] in used]).encode()).hexdigest())


def prepare_dispatch(records, enrollment_id, role, arguments):
    if role not in ROLES:
        raise ValueError("dispatch requires an explicit governed role")
    env = dispatch_environment()
    for argument in arguments:
        flag = argument.split("=", 1)[0]
        if flag in {"--role", "--tier", "--to", "--engine", "-m", "--model", "--reasoning-effort", "--service-tier",
                    "-c", "--config", "--resolved-profile-ref", "--resolved-profile-json", "--resolved-route-json",
                    "--role-resolved", "--minimum-codex-version", "--fallback-reason",
                    "-p", "--profile", "--oss", "--local-provider", "--enable", "--disable"} or argument.startswith(("-m", "-c", "-p")):
            raise ValueError("enrolled dispatch uses only its explicit role; routing overrides are prohibited")
    enrollment_record = enrolled(records).get(enrollment_id)
    if enrollment_record is None:
        raise ValueError("dispatch requires an existing prospective enrollment")
    task = context(enrollment_record)
    dispatcher = CANONICAL_ROOT / "scripts/dispatch.sh"
    dispatch_id = str(uuid.uuid4())
    receipt = dict(enrollment_id=enrollment_id, cohort_id=task["cohort_id"], manifest_sha256=task["manifest_sha256"],
                   role=role, producer_model=task["model"], dispatch_id=dispatch_id,
                   dispatcher=str(dispatcher), dispatcher_sha256=sha256(dispatcher),
                   parent_session_id=task["parent_session_id"], enrollment_decision_id=enrollment_record["id"])
    env.update(CLAVAIN_TASK_ENROLLMENT_ID=enrollment_id, CLAVAIN_TASK_COHORT_ID=task["cohort_id"],
               CLAVAIN_TASK_MANIFEST_SHA256=task["manifest_sha256"], CLAVAIN_DISPATCH_ID=dispatch_id,
               CLAVAIN_BEAD_ID=task["bead_id"])
    return ["bash", str(dispatcher), "--role", role, *arguments], env, receipt


class Intercore:
    def __init__(self, executable, db):
        self.command = [executable, f"--db={Path(db).resolve()}", "--json"]
        self.directory = Path(db).resolve().parent
        self.project = str(Path.cwd().resolve())

    def invoke(self, *arguments):
        result = subprocess.run(self.command + list(arguments), cwd=self.directory,
                                text=True, capture_output=True, check=False)
        if result.returncode:
            raise ValueError(f"Intercore failed ({result.returncode}): {result.stderr.strip()}")
        return json.loads(result.stdout)

    def records(self):
        records = self.invoke("route", "list", "--limit=1000000") or []
        if not isinstance(records, list) or len(records) >= 1000000:
            raise ValueError("Intercore decision export is malformed or truncated")
        return records

    def record(self, kind, value):
        records = self.records()
        validate_record(kind, value, records)
        for previous in records:
            if previous.get("rule_matched") == PREFIX + kind and canonical(context(previous)) == canonical(value):
                return dict(id=previous["id"], reused=True)
        parent = enrolled(records).get(value.get("enrollment_id"))
        parent = context(parent) if parent else value
        args = ["route", "record", f"--rule={PREFIX}{kind}",
                f"--project={self.project}",
                f"--agent={value['reviewer_identity'] if kind == 'acceptance' else value.get('role', parent.get('role', 'main-integrator'))}",
                f"--model={'unknown' if kind == 'dispatch-request' else value.get('model', value.get('reviewer_model', parent.get('model', 'unknown')))}",
                f"--context={canonical(value)}"]
        for field, flag in (("bead_id", "bead"), ("dispatch_id", "dispatch"), ("run_id", "run"), ("session_id", "session")):
            item = value.get(field) or (parent.get("bead_id") if field == "bead_id" else None)
            if item:
                args.append(f"--{flag}={item}")
        return self.invoke(*args)


def emit(value, output=None):
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output:
        # Create exclusively: a sealed evidence export is never silently replaced.
        with Path(output).open("x") as handle:
            handle.write(payload)
    else:
        print(payload, end="")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", required=True, help="explicit authoritative Intercore database")
    parser.add_argument("--ic", default="ic", help="Intercore executable")
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe-execution", help="safe pre-launch source hashes; no database writes")
    observe.add_argument("--engine", required=True)
    observe.add_argument("--workdir", required=True)
    observe.add_argument("--profile-json", default="{}")
    record = commands.add_parser("record")
    record.add_argument("--kind", choices=sorted(KINDS), required=True)
    record.add_argument("--record", required=True, help="JSON receipt; never a task database")
    for name in ("export", "report"):
        command = commands.add_parser(name)
        command.add_argument("--cohort", required=True)
        command.add_argument("--output")
        if name == "report":
            command.add_argument("--profiler", default=str(INTERSTAT_PROFILE))
    dispatch = commands.add_parser("dispatch")
    dispatch.add_argument("--enrollment-id", required=True)
    dispatch.add_argument("--role", required=True, choices=sorted(ROLES))
    dispatch.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.command == "observe-execution":
            emit(observe_execution(args.engine, args.workdir, json.loads(args.profile_json)))
            return 0
        core = Intercore(args.ic, args.db)
        if args.command == "record":
            value = json.loads(Path(args.record).read_text())
            emit(core.record(args.kind, value))
        elif args.command == "dispatch":
            extra = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            command, env, receipt = prepare_dispatch(core.records(), args.enrollment_id, args.role, extra)
            core.record("dispatch-request", receipt)
            # The dispatcher uses the same kernel store for its lifecycle rows.
            env["CLAVAIN_TASK_INTERCORE_DB"] = str(Path(args.db).resolve())
            return subprocess.run(command, env=env, check=False).returncode
        else:
            manifest = export_manifest(core.records(), args.cohort)
            manifest["authority"]["database"] = str(Path(args.db).resolve())
            if args.command == "export":
                emit(manifest, args.output)
            else:
                with tempfile.TemporaryDirectory(prefix="task-delivery-report-") as temp:
                    path = Path(temp) / "manifest.json"
                    emit(manifest, path)
                    report, code = invoke_profiler(args.profiler, path)
                    report["exported_manifest"] = manifest
                    emit(report, args.output)
                    return code
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"task-delivery: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
