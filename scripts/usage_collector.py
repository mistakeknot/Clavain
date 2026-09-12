#!/usr/bin/env python3
"""Opt-in, read-only usage observations. No inference, routing or acceptance writes."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time
import uuid

MAX_RESPONSE = 8 * 1024 * 1024
METHODS = frozenset({"initialize", "account/rateLimits/read", "account/usage/read"})


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def payload_hash(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def read_regular(path, limit=MAX_RESPONSE):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("bounded regular file required")
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("input limit exceeded")
        return raw


def native_identity(path):
    missing = dict(thread_id=None, identity_coverage="incomplete", missing_identity_reason="native-events-unavailable")
    if path is None:
        return missing
    try:
        raw = read_regular(path, 64 * 1024 * 1024)
        identities = set()
        for line in raw.splitlines():
            if not line.strip():
                continue
            row = strict_json(line)
            if not isinstance(row, dict):
                raise ValueError("event must be an object")
            if row.get("type") == "thread.started":
                ident = row.get("thread_id")
                if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ident):
                    raise ValueError("invalid native identity")
                identities.add(ident)
        if len(identities) != 1:
            return missing | dict(missing_identity_reason="native-identity-missing-or-conflicting")
        ident = identities.pop()
        return dict(thread_id=ident, identity_coverage="complete", missing_identity_reason=None,
                    identity_provenance_sha256=payload_hash({"type": "thread.started", "thread_id": ident}))
    except (OSError, ValueError, UnicodeError):
        return missing | dict(missing_identity_reason="native-events-invalid-or-unavailable")


def number(value, *, integer=False, maximum=None):
    if value is None:
        return None
    if type(value) not in (int, float) or (integer and type(value) is not int):
        raise ValueError("invalid numeric counter")
    if (type(value) is float and not math.isfinite(value)) or value < 0 or (maximum is not None and value > maximum):
        raise ValueError("counter outside range")
    if integer and value > 2**63 - 1:
        raise ValueError("counter outside int64 range")
    return value


def sanitize_rate_limits(value):
    if not isinstance(value, dict) or not isinstance(value.get("rateLimits"), dict):
        raise ValueError("missing rateLimits")
    # Only known quota windows; provider account identifiers/credits are dropped.
    rows = []
    for bucket in ("primary", "secondary"):
        window = value["rateLimits"].get(bucket)
        if window is None:
            continue
        if not isinstance(window, dict):
            raise ValueError("invalid quota window")
        rows.append(dict(bucket=bucket, used_percent=number(window.get("usedPercent"), maximum=100),
                         resets_at=number(window.get("resetsAt"), integer=True),
                         window_minutes=number(window.get("windowDurationMins"), integer=True)))
    return rows


def sanitize_account_usage(value):
    if not isinstance(value, dict) or not isinstance(value.get("summary"), dict):
        raise ValueError("missing account summary")
    summary = value["summary"]
    return dict(lifetime_tokens=number(summary.get("lifetimeTokens"), integer=True),
                peak_daily_tokens=number(summary.get("peakDailyTokens"), integer=True))


def sanitize_thread_usage(value, thread_id):
    if not isinstance(value, dict) or "threadUsage" not in value:
        raise ValueError("missing threadUsage field")
    usage = value["threadUsage"]
    if usage is None:
        return None
    if not isinstance(usage, dict) or usage.get("threadId") != thread_id:
        raise ValueError("thread identity mismatch")
    groups = usage.get("groups")
    if not isinstance(groups, list) or len(groups) > 10000:
        raise ValueError("invalid usage groups")
    names = {"inputTokens": "input_tokens", "cachedInputTokens": "cached_input_tokens",
             "netNewInputTokens": "net_new_input_tokens", "outputTokens": "output_tokens",
             "totalTokens": "total_tokens", "estimatedUsageCreditsMicros": "estimated_credits_micros"}
    clean = []
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("invalid usage group")
        counters = {dest: number(group.get(src), integer=True) for src, dest in names.items()}
        # Keep group separation. Only constrained configuration labels are retained.
        for src, dest in (("model", "model"), ("reasoningEffort", "reasoning_effort"), ("speed", "speed")):
            item = group.get(src)
            counters[dest] = item if isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", item) else None
        clean.append(counters)
    return dict(thread_id=thread_id,
                estimated_credits_micros=number(usage.get("estimatedUsageCreditsMicros"), integer=True),
                estimated_usd_micros=number(usage.get("estimatedUsageUsdMicros"), integer=True), groups=clean)


class RPCError(Exception):
    def __init__(self, status, code=None):
        self.status, self.code = status, code
        super().__init__(status)


class CollectionInterrupted(SystemExit):
    def __init__(self, code, evidence):
        super().__init__(code)
        self.evidence = evidence


class AppServer:
    """One bounded process, no thread creation or model turns, no raw log persistence."""
    def __init__(self, executable, timeout=15):
        self.started = time.monotonic()
        self.deadline = self.started + timeout
        self.calls, self.buffer, self.received = [], b"", 0
        self.process = subprocess.Popen([executable, "app-server"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.previous_signals = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            self.previous_signals[sig] = signal.signal(sig, self.interrupt)

    def interrupt(self, signum, _frame):
        self.close()
        raise SystemExit(128 + signum)

    def send(self, value):
        self.process.stdin.write((canonical(value) + "\n").encode())
        self.process.stdin.flush()

    def line(self):
        while b"\n" not in self.buffer:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise RPCError("timeout")
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                raise RPCError("unavailable")
            self.received += len(data)
            if self.received > MAX_RESPONSE:
                raise RPCError("oversized-response")
            self.buffer += data
        line, self.buffer = self.buffer.split(b"\n", 1)
        try:
            value = strict_json(line)
        except (ValueError, UnicodeError):
            raise RPCError("malformed-response") from None
        if not isinstance(value, dict):
            raise RPCError("malformed-response")
        return value

    def request(self, method, params=None):
        if method not in METHODS:
            raise ValueError("collector method is not read-only")
        ident = len(self.calls) + 1
        entry = dict(method=method, status="started", error_code=None)
        self.calls.append(entry)
        try:
            self.send(dict(id=ident, method=method, params=params or {}))
            while True:
                row = self.line()
                if "method" in row:
                    if "id" in row:
                        self.send(dict(id=row["id"], error=dict(code=-32601, message="read-only collector")))
                    continue
                if row.get("id") != ident:
                    raise RPCError("mismatched-response")
                if "error" in row:
                    code = row["error"].get("code") if isinstance(row["error"], dict) else None
                    raise RPCError("unsupported-endpoint" if code == -32601 else "endpoint-error",
                                   code if type(code) is int else None)
                if "result" not in row:
                    raise RPCError("malformed-response")
                entry["status"] = "available"
                return row["result"]
        except (RPCError, OSError) as exc:
            error = exc if isinstance(exc, RPCError) else RPCError("unavailable")
            entry.update(status=error.status, error_code=error.code)
            raise error from None

    def initialize(self):
        self.request("initialize", dict(clientInfo=dict(name="clavain_usage_collector", version="1"),
                                        capabilities=dict(experimentalApi=True)))
        self.send(dict(method="initialized"))

    def close(self):
        process = self.process
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=1)
        self.selector.close()
        for stream in (process.stdin, process.stdout):
            stream.close()
        for sig, previous in self.previous_signals.items():
            signal.signal(sig, previous)
        return dict(duration_seconds=round(time.monotonic() - self.started, 6),
                    process_exit_code=process.returncode, calls=self.calls,
                    collector_transport="app-server", allowance_effect="unknown",
                    overhead_usage="unknown", stderr="discarded-before-persistence")


def timestamp(value=None):
    value = time.time() if value is None else value
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def counter(name, value, unit, semantics, subset=None):
    return dict(name=name, value=value, unit=unit, semantics=semantics, subset_of=subset)


def observation(source, kind, clean, native, *, status="available", reason=None, counters=None,
                bucket=None, reset=None):
    reasons = ["account-binding-not-observed"]
    if native.get("identity_coverage") != "complete":
        reasons.append(native.get("missing_identity_reason", "native-identity-incomplete"))
    kind = {"account_quota": "rate_limits", "thread_usage": "account_usage"}.get(kind, kind)
    return dict(id="usage_" + uuid.uuid4().hex, provider="openai", source=source, kind=kind,
        status=status, reason=reason, captured_at=timestamp(), source_at=None,
        interval_start=None, interval_end=None, quota_bucket=bucket,
        quota_reset_at=timestamp(reset) if reset is not None else None, counters=counters or [],
        identity=dict(native_thread_id=native.get("thread_id"), native_session_id=None,
                      account=dict(coverage="incomplete", safe_ref=None, reasons=reasons)),
        execution_refs={name: None for name in ("dispatch_id", "session_row_id", "run_id", "task_id",
            "dispatch_request_id", "enrollment_id", "execution_id", "attempt_id")},
        payload_sha256=payload_hash(clean), supersedes=None)


def unavailable(source, kind, native, reason):
    return observation(source, kind, dict(status=reason), native, status="unavailable", reason=reason)


def source_timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid source timestamp")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("source timestamp needs a timezone")
    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def codexbar_observations(value, native):
    """Import CLI JSON without copying account identities, details or credentials."""
    snapshots = value if isinstance(value, list) else [value]
    if len(snapshots) > 100:
        raise ValueError("too many CodexBar snapshots")
    rows = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or snapshot.get("provider") != "codex":
            continue
        label = snapshot.get("source")
        label = label if label in {"oauth", "api", "cli", "local", "web", "openai-web"} else "unknown"
        usage = snapshot.get("usage")
        if isinstance(usage, dict):
            for bucket in ("primary", "secondary", "tertiary"):
                window = usage.get(bucket)
                if window is None:
                    continue
                if not isinstance(window, dict):
                    raise ValueError("invalid CodexBar window")
                clean = dict(bucket=bucket, used_percent=number(window.get("usedPercent"), maximum=100),
                    source_at=source_timestamp(usage.get("updatedAt")), reset_at=source_timestamp(window.get("resetsAt")),
                    window_minutes=number(window.get("windowMinutes"), integer=True))
                record = observation("codexbar." + label, "account_quota", clean, native, bucket=bucket,
                    counters=[counter("window_used_percent", clean["used_percent"], "percent", "provider-reported-quota-window-gauge")])
                record.update(source_at=clean["source_at"], quota_reset_at=clean["reset_at"])
                rows.append(record)
        dashboard = snapshot.get("openaiDashboard")
        if isinstance(dashboard, dict):
            clean = dict(source_at=source_timestamp(dashboard.get("updatedAt")),
                         code_review_remaining_percent=number(dashboard.get("codeReviewRemainingPercent"), maximum=100))
            record = observation("codexbar.dashboard", "account_quota", clean, native, bucket="code-review",
                counters=[counter("code_review_remaining_percent", clean["code_review_remaining_percent"], "percent", "provider-reported-remaining-gauge")])
            record["source_at"] = clean["source_at"]
            rows.append(record)
    return rows or [unavailable("codexbar.unknown", "account_quota", native, "codexbar-snapshot-unavailable")]


def disagreements(rows):
    result = []
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            if left["source"] == right["source"] or left["kind"] != right["kind"] or left["quota_bucket"] != right["quota_bucket"]:
                continue
            lc = {c["name"]: c for c in left["counters"]}
            rc = {c["name"]: c for c in right["counters"]}
            different = sorted(k for k in lc.keys() & rc.keys() if lc[k] != rc[k])
            if different or left["quota_reset_at"] != right["quota_reset_at"] or left["source_at"] != right["source_at"]:
                result.append(dict(observation_ids=[left["id"], right["id"]], different_counters=different,
                    reset_differs=left["quota_reset_at"] != right["quota_reset_at"],
                    source_time_differs=left["source_at"] != right["source_at"], account_comparability="unknown"))
    return dict(status="differences-observed" if result else "none-observed", comparisons=result,
                account_comparability="unknown", interpretation="sources-retained-separately")


def collect(executable, events=None, timeout=15):
    native = native_identity(events)
    rows, server, interrupted = [], None, None
    sources = (("codex-app-server.rate-limits-read", "account_quota"),
               ("codex-app-server.account-usage-read", "account_usage"),
               ("codex-app-server.thread-usage-read", "thread_usage"))
    transport = dict(collector_transport="app-server", allowance_effect="unknown", overhead_usage="unknown",
                     duration_seconds=None, process_exit_code=None, calls=[], status="unavailable")
    try:
        server = AppServer(executable, timeout)
        server.initialize()
        for source, kind in sources:
            if kind == "thread_usage" and native["thread_id"] is None:
                rows.append(unavailable(source, kind, native, "native-identity-unavailable"))
                continue
            try:
                if kind == "account_quota":
                    clean = sanitize_rate_limits(server.request("account/rateLimits/read"))
                    if not clean:
                        rows.append(unavailable(source, kind, native, "quota-windows-null"))
                    for window in clean:
                        rows.append(observation(source, kind, window, native, bucket=window["bucket"],
                            reset=window["resets_at"], counters=[counter("window_used_percent", window["used_percent"],
                                "percent", "provider-reported-quota-window-gauge")]))
                elif kind == "account_usage":
                    clean = sanitize_account_usage(server.request("account/usage/read"))
                    rows.append(observation(source, kind, clean, native, counters=[
                        counter(key, value, "tokens", "provider-reported-account-activity") for key, value in clean.items()]))
                else:
                    clean = sanitize_thread_usage(server.request("account/usage/read", dict(threadId=native["thread_id"])), native["thread_id"])
                    if clean is None:
                        rows.append(unavailable(source, kind, native, "thread-usage-null"))
                        continue
                    counters = [counter("estimated_credits_micros", clean["estimated_credits_micros"], "credits_micros", "provider-estimate"),
                                counter("estimated_usd_micros", clean["estimated_usd_micros"], "usd_micros", "provider-estimate")]
                    for index, group in enumerate(clean["groups"]):
                        prefix = f"group_{index}_"
                        for key in ("input_tokens", "cached_input_tokens", "net_new_input_tokens", "output_tokens", "total_tokens"):
                            subset = prefix + "input_tokens" if key in ("cached_input_tokens", "net_new_input_tokens") else None
                            counters.append(counter(prefix + key, group[key], "tokens", "provider-reported-thread-activity", subset))
                        counters.append(counter(prefix + "estimated_credits_micros", group["estimated_credits_micros"], "credits_micros", "provider-estimate"))
                    rows.append(observation(source, kind, clean, native, counters=counters))
            except RPCError as exc:
                rows.append(unavailable(source, kind, native, exc.status))
            except (ValueError, OverflowError, OSError):
                rows.append(unavailable(source, kind, native, "malformed-response"))
        transport["status"] = "completed"
    except (OSError, RPCError) as exc:
        reason = exc.status if isinstance(exc, RPCError) else "executable-unavailable"
        rows = [unavailable(source, kind, native, reason) for source, kind in sources]
        transport["status"] = reason
    except SystemExit as exc:
        interrupted = exc.code
        known_sources = {row["source"] for row in rows}
        rows.extend(unavailable(source, kind, native, "collection-cancelled")
                    for source, kind in sources if source not in known_sources)
        transport["status"] = "cancelled"
    finally:
        if server is not None:
            transport.update(server.close())
    result = dict(schema_version=1, native_identity=native, transport=transport, observations=rows,
                account_attribution="unknown", source_disagreement="not-evaluated-sources-retained-separately")
    if interrupted is not None:
        raise CollectionInterrupted(interrupted, result)
    return result


def write_private(path, value):
    raw = (canonical(value) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--codex", default="codex", help="existing Codex executable")
    parser.add_argument("--events", type=Path, help="actual execution JSONL; never the parent identity")
    parser.add_argument("--codexbar-record", type=Path, help="optional existing CodexBar CLI JSON snapshot; sources stay separate")
    parser.add_argument("--output-dir", type=Path, required=True, help="new private task evidence directory")
    parser.add_argument("--phase", choices=("boundary", "completion", "reconcile"), required=True)
    parser.add_argument("--completed-at", type=float, help="Unix completion timestamp; required for reconciliation")
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 60:
        parser.error("timeout must be greater than zero and at most 60 seconds")
    if args.phase == "reconcile" and (args.completed_at is None or not math.isfinite(args.completed_at) or args.completed_at <= 0 or args.completed_at > time.time()):
        parser.error("reconcile requires a valid --completed-at timestamp")
    if args.phase != "reconcile" and args.completed_at is not None:
        parser.error("--completed-at is only supported for reconcile")
    try:
        args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        delays = (5, 30) if args.phase == "reconcile" else (0,)
        previous = {}
        for delay in delays:
            if delay:
                # This explicit process owns the wait; dispatch never starts it.
                time.sleep(max(0, args.completed_at + delay - time.time()))
            result = collect(args.codex, args.events, args.timeout)
            if args.codexbar_record:
                try:
                    result["observations"].extend(codexbar_observations(strict_json(read_regular(args.codexbar_record)), result["native_identity"]))
                except (OSError, ValueError, OverflowError):
                    result["observations"].append(unavailable("codexbar.unknown", "account_quota", result["native_identity"], "codexbar-record-invalid-or-unavailable"))
            result["source_disagreement"] = disagreements(result["observations"])
            result.update(phase=args.phase, requested_delay_seconds=delay)
            refs = []
            counts = {}
            for record in result["observations"]:
                key = (record["source"], record["kind"], record["quota_bucket"])
                counts[key] = counts.get(key, 0) + 1
            for index, record in enumerate(result["observations"]):
                key = (record["source"], record["kind"], record["quota_bucket"])
                # Multi-account snapshots have no safe account key. Never invent
                # predecessor association by ordering two same-source records.
                record["supersedes"] = previous.get(key) if counts[key] == 1 else None
                previous[key] = record["id"] if counts[key] == 1 else None
                name = f"{delay}-{index}-observation.json"
                write_private(args.output_dir / name, record)
                refs.append(dict(path=name, sha256=hashlib.sha256((args.output_dir / name).read_bytes()).hexdigest()))
            result["observation_artifacts"] = refs
            write_private(args.output_dir / f"{delay}-collection.json", result)
        manifest = args.output_dir / f"{delays[-1]}-collection.json"
        print(canonical(dict(evidence_dir=str(args.output_dir.resolve()), phase=args.phase, acceptance=False,
            path=str(manifest.resolve()), sha256=hashlib.sha256(read_regular(manifest)).hexdigest())))
    except CollectionInterrupted as exc:
        write_private(args.output_dir / "cancelled-collection.json", exc.evidence)
        return exc.code
    except (OSError, ValueError) as exc:
        parser.exit(2, f"usage-collector: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
