"""Three-label, revision-backed advisory checks. Labels never authorize action."""
from __future__ import annotations
from dataclasses import dataclass
import datetime as dt
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import stat
import subprocess
import time
import uuid

from clavain_selector import contract, credentials, egress, flags, records
from clavain_selector import jev_client as j
from clavain_selector.accounting import AttemptLog, digest, safe_class, stamp, valid_usage

LABELS = ("supported", "not_supported", "unclear")
ID_GRAMMAR = r"^[A-Za-z0-9_-]{1,64}$"
ADAPTER_VERSION = "1"
WIRE_SCHEMA = "clavain-support-v1"
MAX_SOURCE_BYTES = 1024 * 1024

class SupportInvalid(ValueError):
    pass

class AdmissionFailure(Exception):
    def __init__(self, outcome, reason):
        self.outcome, self.reason = outcome, reason

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

def number(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1

def hash_string(value, width=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % width, value) is not None

def validate_request(obj):
    keys = {"schema", "schema_version", "run_id", "case_id", "claim", "project_root", "revision", "sections", "label_descriptions", "abstain_below", "deadline_ms"}
    if not isinstance(obj, dict) or set(obj) != keys: raise SupportInvalid("request_schema")
    if obj["schema"] != "clavain.selector.support_request" or type(obj["schema_version"]) is not int or obj["schema_version"] != 1: raise SupportInvalid("request_schema")
    if not all(isinstance(obj[k], str) and re.fullmatch(ID_GRAMMAR, obj[k]) for k in ("run_id", "case_id")): raise SupportInvalid("request_schema")
    if not number(obj["abstain_below"]) or type(obj["deadline_ms"]) is not int or not 1 <= obj["deadline_ms"] <= j.MAX_DEADLINE_MS: raise SupportInvalid("request_schema")
    claim = obj["claim"]
    if not isinstance(claim, dict) or set(claim) != {"text", "sha256"} or not isinstance(claim["text"], str) or not hash_string(claim["sha256"]): raise SupportInvalid("request_schema")
    descriptions = obj["label_descriptions"]
    if not isinstance(descriptions, dict) or set(descriptions) != set(LABELS) or any(not isinstance(v, str) or len(v) > 500 for v in descriptions.values()): raise SupportInvalid("request_schema")
    if not isinstance(obj["project_root"], str) or not hash_string(obj["revision"], 40): raise SupportInvalid("request_schema")
    sections = obj["sections"]
    if not isinstance(sections, list) or not 1 <= len(sections) <= 16: raise SupportInvalid("request_schema")
    for section in sections:
        if not isinstance(section, dict) or set(section) != {"path", "start_line", "end_line", "text", "sha256"}: raise SupportInvalid("request_schema")
        if not isinstance(section["path"], str) or not isinstance(section["text"], str) or not hash_string(section["sha256"]): raise SupportInvalid("request_schema")
        if any(type(section[k]) is not int for k in ("start_line", "end_line")) or not 1 <= section["start_line"] <= section["end_line"]: raise SupportInvalid("request_schema")
    return obj

def _git(root, *args, cap=MAX_SOURCE_BYTES + 1):
    # Read only bounded stdout and kill a child that exceeds size or time caps.
    env = {"PATH": "/usr/bin:/bin", "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1", "HOME": "/nonexistent"}
    child = subprocess.Popen(["git", "--no-replace-objects", "-C", str(root), *args], env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    data = bytearray()
    deadline = time.monotonic() + 5
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining): raise AdmissionFailure("stale", "src.not_at_revision")
                chunk = os.read(child.stdout.fileno(), min(65536, cap + 1 - len(data)))
                if not chunk: break
                data.extend(chunk)
                if len(data) > cap: raise AdmissionFailure("stale", "src.not_at_revision")
        if child.wait(timeout=max(.01, deadline-time.monotonic())): raise AdmissionFailure("stale", "src.not_at_revision")
    except subprocess.TimeoutExpired: raise AdmissionFailure("stale", "src.not_at_revision")
    finally:
        if child.poll() is None: child.kill()
        child.wait()
        child.stdout.close()
    return bytes(data)

def _admit(request, key_literal=None):
    if any(k not in request for k in ("project_root", "revision", "sections")):
        raise AdmissionFailure("refused", "src.provenance_unavailable")
    validate_request(request)
    raw_root = Path(request["project_root"])
    try:
        if not raw_root.is_absolute(): raise OSError()
        root = raw_root.resolve(strict=True)
        if not root.is_dir(): raise OSError()
        if _git(root, "rev-parse", "--show-toplevel").decode().strip() != str(root): raise OSError()
    except (OSError, ValueError, AdmissionFailure): raise AdmissionFailure("refused", "src.provenance_unavailable")
    try:
        if _git(root, "cat-file", "-t", request["revision"]).strip() != b"commit" or _git(root, "rev-parse", "HEAD").decode().strip() != request["revision"]:
            raise AdmissionFailure("stale", "revision_mismatch")
    except AdmissionFailure: raise AdmissionFailure("stale", "revision_mismatch")
    if egress.project_owner(root) not in egress._ALLOWED_OWNERS: raise AdmissionFailure("refused", "proj.unowned")
    if digest(request["claim"]["text"].encode()) != request["claim"]["sha256"]: raise AdmissionFailure("stale", "claim_hash")
    if len(request["claim"]["text"]) > contract.MAX_SUPPORT_CLAIM_CHARS or any(len(s["text"]) > contract.MAX_SUPPORT_SECTION_CHARS for s in request["sections"]): raise AdmissionFailure("refused", "size.over_limit")
    texts = [request["claim"]["text"], request["run_id"], request["case_id"], *request["label_descriptions"].values()]
    for section in request["sections"]:
        path = section["path"]
        if not path or "\0" in path or path.startswith(("/", "~")) or ".." in PurePosixPath(path).parts: raise AdmissionFailure("refused", "src.path_invalid")
        lexical = root / PurePosixPath(path)
        try:
            target = lexical.resolve(strict=True)
            try: target.relative_to(root)
            except ValueError: raise AdmissionFailure("refused", "src.outside_project")
            if target != lexical: raise AdmissionFailure("refused", "src.symlink")
            assert target.is_absolute()  # _source_rule always receives absolute resolved paths.
            before = os.stat(target)
            rule = egress._source_rule(target, root)
            if rule: raise AdmissionFailure("refused", rule)
            try: fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            except OSError: raise AdmissionFailure("stale", "src.target_changed")
            with os.fdopen(fd, "rb") as stream:
                after = os.fstat(stream.fileno())
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or not stat.S_ISREG(after.st_mode): raise AdmissionFailure("stale", "src.target_changed")
                data = stream.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES: raise AdmissionFailure("refused", "size.over_limit")
            entries = _git(root, "ls-tree", "-z", "--full-tree", request["revision"], "--", path).split(b"\0")
            if len(entries) != 2 or entries[1] != b"": raise AdmissionFailure("stale", "src.not_at_revision")
            meta, name = entries[0].split(b"\t", 1)
            mode, kind, oid = meta.split()
            if mode not in (b"100644", b"100755") or kind != b"blob" or name != path.encode(): raise AdmissionFailure("stale", "src.not_at_revision")
            if int(_git(root, "cat-file", "-s", oid.decode()).strip()) > MAX_SOURCE_BYTES: raise AdmissionFailure("refused", "size.over_limit")
            if _git(root, "cat-file", "blob", oid.decode()) != data: raise AdmissionFailure("stale", "src.not_at_revision")
            lines = data.splitlines(keepends=True)
            if section["end_line"] > len(lines): raise AdmissionFailure("stale", "span_text")
            span = b"".join(lines[section["start_line"]-1:section["end_line"]])
            try: text = span.decode("utf-8", errors="strict")
            except UnicodeError: raise AdmissionFailure("stale", "span_text")
            if text != section["text"]: raise AdmissionFailure("stale", "span_text")
            if digest(span) != section["sha256"]: raise AdmissionFailure("stale", "span_hash")
        except OSError: raise AdmissionFailure("refused", "src.provenance_unavailable")
        texts.append(section["text"])
    for text in texts:
        rules = egress.scan_text(text, contract.Point.LIBRARY)
        if rules: raise AdmissionFailure("refused", rules[0])
        if key_literal and key_literal in text: raise AdmissionFailure("refused", "cred.loaded_key")
    body = canonical({"model": j.PINNED_MODEL, "state": {"schema": WIRE_SCHEMA, "claim": request["claim"]["text"], "sections": [{"id": f"s{i}", "text": s["text"]} for i, s in enumerate(request["sections"], 1)]}, "questions": {"support": {"type": "choice", "criteria": request["label_descriptions"]}}})
    if len(body) > contract.MAX_REQUEST_BYTES: raise AdmissionFailure("refused", "size.over_limit")
    sha = digest(body)
    return egress.AdmittedRequest(body, sha, egress._compute_tag(sha))

def admit_support(request, *, key_literal=None):
    try: return _admit(request, key_literal)
    except AdmissionFailure as failure:
        result = egress.Refusal((failure.reason,))
        object.__setattr__(result, "outcome", failure.outcome)
        return result

@dataclass(frozen=True)
class SupportAnswer:
    choice: str
    confidence: float
    probabilities: dict
    usage: j.Usage
    model: str = j.PINNED_MODEL

def _validate_support_response(data):
    try:
        if len(data) > j.MAX_RESPONSE_BYTES: raise SupportInvalid("response_schema")
        obj = json.loads(data)
        if not isinstance(obj, dict): raise SupportInvalid("response_schema")
        if not valid_usage(obj.get("usage")): raise SupportInvalid("usage")
        if obj.get("model") != j.PINNED_MODEL: raise SupportInvalid("model_mismatch")
        if not isinstance(obj.get("answers"), dict) or set(obj["answers"]) != {"support"}: raise SupportInvalid("response_schema")
        answer = obj["answers"]["support"]
        if not isinstance(answer, dict) or answer.get("type") != "choice" or answer.get("choice") not in LABELS or not number(answer.get("confidence")): raise SupportInvalid("response_schema")
        probs = answer.get("probabilities")
        if not isinstance(probs, dict) or set(probs) != set(LABELS) or not all(number(v) for v in probs.values()) or abs(sum(probs.values()) - 1) > j._PROBABILITY_SUM_TOLERANCE: raise SupportInvalid("response_schema")
        if probs[answer["choice"]] < max(probs.values()) - j._TIE_EPSILON: raise SupportInvalid("response_schema")
        return SupportAnswer(answer["choice"], answer["confidence"], probs, j.Usage(**{k: obj["usage"][k] for k in ("input_tokens", "output_tokens")}))
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        if isinstance(exc, SupportInvalid): raise
        raise SupportInvalid("response_schema") from None

@dataclass(frozen=True)
class SupportCall:
    admitted: egress.AdmittedRequest
    descriptions: dict
    deadline: j.Deadline

    def __post_init__(self):
        if not egress.verify(self.admitted): raise j.NotAdmitted("unverified support admission")
        body = json.loads(self.admitted.body)
        expected = {"support": {"type": "choice", "criteria": self.descriptions}}
        if body.get("questions") != expected or body.get("state", {}).get("schema") != WIRE_SCHEMA or body.get("model") != j.PINNED_MODEL: raise j.BatteryMismatch("support questions changed")

    @classmethod
    def build(cls, admitted, *, deadline):
        if not egress.verify(admitted): raise j.NotAdmitted("unverified support admission")
        return cls(admitted, json.loads(admitted.body)["questions"]["support"]["criteria"], deadline)

    def wire_body(self): return self.admitted.body

    def interpret(self, box, elapsed, attempts):
        if "exception" in box:
            return j.JevFailure(contract.FallbackReason.HTTP_ERROR, j.FailureDetail.CONNECT_ERROR, attempts, None, elapsed), None
        status = box.get("status")
        retry = j._retry_after_ms(box.get("headers", {}).get("retry-after"))
        if status != 200:
            reason = contract.FallbackReason.CREDENTIAL_REJECTED if status in (401, 403) else contract.FallbackReason.RATE_LIMITED if status == 429 else contract.FallbackReason.HTTP_ERROR
            return j.JevFailure(reason, j.FailureDetail.STATUS, attempts, status, elapsed), retry
        # Validation is performed by the outer caller after accounting is secure.
        return j.JevOk(box.get("data", b""), attempts, status, elapsed), None


def _receipt():
    fields = dict.fromkeys(("subreason", "fallback_reason", "label", "confidence", "probabilities",
        "abstain_below", "run_ref", "case_ref", "claim_sha256", "label_descriptions_sha256", "revision",
        "project_root_sha256", "request_sha256", "model_returned_matches", "model_returned_sha256", "persist_error_class"))
    fields.update(schema="clavain.selector.support_check", schema_version=1, adapter_version=ADAPTER_VERSION,
        wire_schema=WIRE_SCHEMA, decision_id=str(uuid.uuid4()), started_at=stamp(), ended_at=None,
        outcome="internal_error", section_sha256s=[], model_requested=None, rule_ids=[],
        effective_mode="off", active_denied=False, application="native", advisory=True, use="evaluation_only", persisted=False,
        flag_value_unknown=False)
    return fields


def _input_fields(record, obj):
    if not isinstance(obj, dict): return
    # IDs are a pair: neither is retained if either fails its grammar.
    if all(isinstance(obj.get(k), str) and re.fullmatch(ID_GRAMMAR, obj[k]) for k in ("run_id", "case_id")):
        record.update(run_ref=digest(obj["run_id"].encode()), case_ref=digest(obj["case_id"].encode()))
    if number(obj.get("abstain_below")): record["abstain_below"] = obj["abstain_below"]
    claim = obj.get("claim")
    if isinstance(claim, dict) and isinstance(claim.get("text"), str): record["claim_sha256"] = digest(claim["text"].encode())
    if hash_string(obj.get("revision"), 40): record["revision"] = obj["revision"]
    descriptions = obj.get("label_descriptions")
    if isinstance(descriptions, dict) and set(descriptions) == set(LABELS) and all(isinstance(v, str) and len(v) <= 500 for v in descriptions.values()): record["label_descriptions_sha256"] = digest(canonical(descriptions))
    if isinstance(obj.get("sections"), list):
        record["section_sha256s"] = [digest(s["text"].encode()) for s in obj["sections"] if isinstance(s, dict) and isinstance(s.get("text"), str)]
    try:
        root = Path(obj.get("project_root", "")).resolve(strict=True)
        if Path(obj.get("project_root", "")).is_absolute() and root.is_dir(): record["project_root_sha256"] = digest(str(root).encode())
    except (OSError, ValueError, TypeError): pass


def _guard_record(record):
    """Reject all string leaves except fixed enums and validated hashes/identity."""
    fixed = set(LABELS) | {"clavain.selector.support_check", ADAPTER_VERSION, WIRE_SCHEMA, j.PINNED_MODEL,
        "label", "abstain", "disabled", "invalid", "refused", "stale", "unavailable", "provider_failure", "timeout", "internal_error",
        "below_threshold", "tie", "kill_switch", "flag_off", "flag_value_unknown", "registry_missing", "request_schema", "response_schema", "model_mismatch", "usage",
        "revision_mismatch", "claim_hash", "span_text", "span_hash", "credential_unavailable", "circuit_open", "budget_session", "budget_daily", "credential_rejected",
        "http_429", "http_redirect", "http_4xx", "http_5xx", "http_other", "connect_error", "read_error", "deadline", "in_flight_cap", "abandoned", "interrupted",
        "off", "shadow", "native", "evaluation_only", "unknown", "not_started", "connect", "request_sent", "response_read", "finished",
        "reported", "not_sent", "unknown_unparseable", "unknown_non200", "unknown_abandoned", "unknown_interrupted", "ok", "other"}
    from clavain_selector.accounting import ERROR_CLASSES
    fixed |= ERROR_CLASSES | {v.value for v in contract.FallbackReason} | {v.value for v in j.FailureDetail}
    fixed |= {rule for rule, _ in egress._TEXT_RULES} | {"cred.loaded_key", "cred.high_entropy", "src.provenance_unavailable", "src.path_invalid", "src.outside_project", "src.symlink", "src.denylisted_path", "src.not_at_revision", "src.target_changed", "proj.unowned", "size.over_limit"}
    def visit(value, key=""):
        if isinstance(value, dict):
            for k, v in value.items(): visit(v, k)
        elif isinstance(value, list):
            for v in value: visit(v, key)
        elif isinstance(value, str):
            if value in fixed: return
            if key == "revision" and hash_string(value, 40): return
            if ("sha256" in key or key in ("run_ref", "case_ref")) and hash_string(value): return
            if key == "decision_id" and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value): return
            if key.endswith("_at") and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z", value): return
            raise ValueError("unsafe receipt string")
        elif type(value) is float and not math.isfinite(value): raise ValueError("nonfinite receipt number")
    visit(record)


def run(stdin, stdout, *, env, registry, transport=None, credential_loader=None):
    """Emit one receipt for every outcome. Native results always remain applied."""
    log, record = AttemptLog(), _receipt()
    resolved = flags.resolve_mode("support_check", env, registry)
    record.update(effective_mode=resolved.mode, active_denied=resolved.active_denied,
                  flag_value_unknown=resolved.unknown_value is not None)

    def emit(outcome, subreason=None, fallback=None):
        record.update(outcome=outcome, subreason=subreason, fallback_reason=fallback, ended_at=stamp(), **log.to_fields())
        if outcome != "label": record["label"] = None
        _guard_record(record)
        if resolved.mode != "off":
            try:
                record["persisted"] = True
                records.append_record(record)
            except Exception as exc:
                record.update(persisted=False, persist_error_class=safe_class(exc))
        stdout.write(canonical(record).decode() + "\n")
        return 0

    try:
        if resolved.mode == "off":
            why = "kill_switch" if str(env.get(flags.GLOBAL_KILL_SWITCH, "")).strip().lower() == "off" else "registry_missing" if "support_check" not in registry.get("integrations", {}) else "flag_value_unknown" if resolved.unknown_value is not None else "flag_off"
            return emit("disabled", why, "flag_off")
        raw = stdin.read(contract.MAX_REQUEST_BYTES * 4 + 1)
        if len(raw) > contract.MAX_REQUEST_BYTES * 4:
            record["rule_ids"] = ["size.over_limit"]
            return emit("refused", "size.over_limit", "egress_refused")
        try: obj = json.loads(raw)
        except (ValueError, UnicodeError): return emit("invalid", "request_schema", "invalid_input")
        _input_fields(record, obj)
        try:
            if not isinstance(obj, dict): raise SupportInvalid("request_schema")
            if any(k not in obj for k in ("project_root", "revision", "sections")):
                return emit("refused", "src.provenance_unavailable", "egress_refused")
            validate_request(obj)
        except SupportInvalid: return emit("invalid", "request_schema", "invalid_input")
        admitted = egress.admit_support(obj)
        if isinstance(admitted, egress.Refusal):
            record["rule_ids"] = list(admitted.rule_ids)
            outcome = getattr(admitted, "outcome", "refused")
            return emit(outcome, admitted.rule_ids[0], "stale_before_select" if outcome == "stale" else "egress_refused")
        record.update(request_sha256=admitted.sha256, model_requested=j.PINNED_MODEL)
        breaker = j.Breaker()
        if breaker.check() is not None: return emit("unavailable", "circuit_open", "circuit_open")
        entry = registry["integrations"]["support_check"]
        # Check credentials and literal leakage before consuming either budget.
        try: credential = (credential_loader or credentials.load)()
        except credentials.CredentialUnavailable: return emit("unavailable", "credential_unavailable", "credential_unavailable")
        admitted = egress.admit_support(obj, key_literal=credential.reveal())
        if isinstance(admitted, egress.Refusal):
            record.update(request_sha256=None, model_requested=None, rule_ids=list(admitted.rule_ids))
            return emit(getattr(admitted, "outcome", "refused"), admitted.rule_ids[0], "egress_refused")
        budgets = [j.Budget(obj["run_id"], "support_check", limit=entry["session_budget"]),
                   j.Budget("utc-day:" + dt.datetime.now(dt.timezone.utc).date().isoformat(), "support_check.daily", limit=entry["daily_budget"])]
        refused_budget = j.Budget.consume_all(budgets)
        if refused_budget is not None:
            return emit("unavailable", ("budget_session", "budget_daily")[refused_budget], "budget_exhausted")
        call = SupportCall.build(admitted, deadline=j.Deadline.start(min(obj["deadline_ms"], entry["deadline_ms"])))
        result = j.JevClient(credential, transport=transport).call(call, log=log)
        if isinstance(result, j.JevFailure):
            breaker.record(result)
            if result.reason == contract.FallbackReason.TIMEOUT:
                final = log.to_fields()["attempt_records"]
                sub = "abandoned" if final and final[-1]["state"] == "abandoned" else "in_flight_cap" if result.detail == j.FailureDetail.INFLIGHT_CAP else "deadline"
                return emit("timeout", sub, result.reason.value)
            status = result.http_status
            if status is None:
                final = log.to_fields()["attempt_records"]
                sub = "connect_error" if final[-1]["phase"] in ("connect", "not_started") else "read_error"
            elif status in (401, 403): sub = "credential_rejected"
            elif status == 429: sub = "http_429"
            elif 300 <= status <= 399: sub = "http_redirect"
            elif 400 <= status <= 499: sub = "http_4xx"
            elif 500 <= status <= 599: sub = "http_5xx"
            else: sub = "http_other"
            return emit("provider_failure", sub, result.reason.value)
        data = result.response
        try:
            parsed = json.loads(data)
            model = parsed.get("model") if isinstance(parsed, dict) else None
            if isinstance(model, str): record.update(model_returned_matches=model == j.PINNED_MODEL, model_returned_sha256=digest(model.encode()))
        except (ValueError, UnicodeError): pass
        try: answer = _validate_support_response(data)
        except SupportInvalid as exc:
            model_mismatch = str(exc) == "model_mismatch"
            breaker.record(j.JevFailure(contract.FallbackReason.MODEL_MISMATCH if model_mismatch else contract.FallbackReason.INVALID_RESPONSE,
                j.FailureDetail.MODEL if model_mismatch else j.FailureDetail.SCHEMA, result.attempts, result.http_status, result.latency_ms))
            return emit("invalid", str(exc), "model_mismatch" if str(exc) == "model_mismatch" else "invalid_response")
        breaker.record(result)
        record.update(confidence=answer.confidence, probabilities=answer.probabilities)
        top = max(answer.probabilities.values())
        if sum(p >= top - j._TIE_EPSILON for p in answer.probabilities.values()) > 1: return emit("abstain", "tie")
        if answer.confidence < obj["abstain_below"]: return emit("abstain", "below_threshold")
        record["label"] = answer.choice
        return emit("label")
    except BaseException as exc:
        log.finalize_open()
        code = emit("internal_error", safe_class(exc) if isinstance(exc, Exception) else "interrupted", "internal_error")
        if isinstance(exc, (KeyboardInterrupt, SystemExit)): raise
        return code
