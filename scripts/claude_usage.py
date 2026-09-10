#!/usr/bin/env python3
"""Meter one Claude print invocation; stdout remains the final Markdown response.

The append-only ledger contains cumulative *reported* tokens, including cache
reads/creation. It is a lower bound until the final provider totals reconcile.
Raw events are retained separately so new provider fields remain inspectable.
No model retry, resumption, pricing estimate, or authority decision lives here.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import uuid

FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
CAMEL = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
MAX_LINE = 8 << 20


def counts(value, *, model=False, output_required=True):
    if not isinstance(value, dict):
        raise ValueError("missing usage object")
    keys = CAMEL if model else FIELDS
    for key, number in value.items():
        if (key.endswith("_tokens") or key.endswith("Tokens")) and key not in keys:
            if key not in (("maxOutputTokens", "thinkingTokens") if model else ()) and isinstance(number, (int, float)):
                raise ValueError("unknown token field: " + key)
    result = {}
    for key, canonical in zip(keys, FIELDS):
        if key not in value and (canonical == "input_tokens" or
                                 (canonical == "output_tokens" and output_required)):
            raise ValueError("missing token field: " + key)
        number = value.get(key, 0)
        if type(number) is not int or number < 0 or number > (1 << 53):
            raise ValueError("invalid token field: " + key)
        result[canonical] = number
    # SDK 0.3.257 added thinkingTokens as a subset of outputTokens, not an
    # additional billable category. Validate the breakdown without counting it
    # twice. Older streams may omit it entirely.
    details = {"thinking_tokens": value["thinkingTokens"]} if model and "thinkingTokens" in value else {}
    if not model and "output_tokens_details" in value:
        details = value["output_tokens_details"]
        if not isinstance(details, dict):
            raise ValueError("invalid output token details")
    for key, number in details.items():
        if key != "thinking_tokens":
            raise ValueError("unknown output token detail: " + key)
        if type(number) is not int or number < 0 or number > result["output_tokens"]:
            raise ValueError("invalid thinking token subset")
    return result


class Meter:
    def __init__(self, model, dispatch, invocation, session, policy):
        self.model = model
        self.dispatch = dispatch
        self.invocation = invocation
        self.session = session
        self.policy = policy
        self.requested_identity = self.identity(model)
        self.observed_identity = ""
        self.models = {}
        self.steps = {}
        self.current = None
        self.total = dict.fromkeys(FIELDS, 0)
        self.result = None
        self.error = ""
        self.sequence = 0
        self.initialized = False

    @functools.lru_cache(maxsize=64)
    def identity(self, model):
        if not isinstance(model, str) or not model:
            raise ValueError("missing observed model identity")
        proc = subprocess.run(["ic", "--json", "route", "identity",
                               "--policy=" + self.policy, "--model=" + model],
                              capture_output=True, text=True, timeout=10)
        if proc.returncode:
            raise ValueError("model identity could not be resolved: " + model)
        return json.loads(proc.stdout)["model_identity"]

    def bind_model(self, model):
        identity = self.identity(model)
        self.observed_identity = identity
        if identity != self.requested_identity:
            raise ValueError("observed main-loop model differs from routed model")

    def event(self, event):
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError("invalid provider event")
        if event.get("session_id", self.session) != self.session:
            raise ValueError("provider session changed within invocation")
        if event.get("parent_tool_use_id"):
            raise ValueError("unexpected subagent activity in budgeted seat")
        kind = event["type"]
        if self.result is not None:
            raise ValueError("provider event after final result")
        if kind == "system" and event.get("subtype") == "init":
            self.bind_model(event.get("model"))
            self.initialized = True
        elif kind == "assistant":
            self.step(event.get("message"), partial=False)
        elif kind == "stream_event":
            partial = event.get("event", {})
            if partial.get("type") == "message_start":
                self.step(partial.get("message"), partial=True)
            elif partial.get("type") == "message_delta":
                if self.current is None:
                    raise ValueError("message delta without message start")
                usage = partial.get("usage")
                if not isinstance(usage, dict) or "output_tokens" not in usage:
                    raise ValueError("message delta lacks output usage")
                # Delta input/cache fields may be null. They are not new input
                # evidence; only the cumulative output field is consumed here.
                delta = {k: v for k, v in usage.items()
                         if k not in FIELDS or k == "output_tokens"}
                value = counts({"input_tokens": 0, **delta})["output_tokens"]
                old = self.steps[self.current]["output_tokens"]
                if value < old:
                    raise ValueError("message output regressed")
                self.steps[self.current]["output_tokens"] = value
                self.retotal()
        elif kind == "result":
            if not self.initialized or not self.steps:
                raise ValueError("result lacks observed main-loop identity/steps")
            main = counts(event.get("usage"))
            if any(main[k] < self.total[k] for k in FIELDS):
                raise ValueError("result below observed main-loop usage")
            models = event.get("modelUsage")
            if not isinstance(models, dict) or not models:
                raise ValueError("result lacks whole-invocation modelUsage")
            totals = dict.fromkeys(FIELDS, 0)
            routed = dict.fromkeys(FIELDS, 0)
            for model, usage in models.items():
                identity = self.identity(model)
                c = counts(usage, model=True)
                self.models[model] = {"model_identity": identity, **c}
                for k in FIELDS:
                    totals[k] += c[k]
                    if identity == self.requested_identity:
                        routed[k] += c[k]
            if any(routed[k] < main[k] for k in FIELDS):
                raise ValueError("per-model totals below bound main-loop usage")
            if type(event.get("is_error")) is not bool:
                raise ValueError("result lacks explicit outcome")
            if not event["is_error"] and (event.get("subtype") != "success" or
                                           not isinstance(event.get("result"), str)):
                raise ValueError("invalid successful result")
            self.total = totals
            self.result = event

    def step(self, message, *, partial):
        if not isinstance(message, dict) or not message.get("id"):
            raise ValueError("missing message identity")
        self.bind_model(message.get("model"))
        key = message["id"]
        values = counts(message.get("usage"))
        values["output_tokens"] = 0  # assistant output is a placeholder
        if key in self.steps:
            old = self.steps[key]
            if any(values[k] != old[k] for k in FIELDS if k != "output_tokens"):
                raise ValueError("conflicting usage for duplicate message")
        else:
            self.steps[key] = values
        if partial:
            self.current = key
        self.retotal()

    def retotal(self):
        self.total = {k: sum(step[k] for step in self.steps.values()) for k in FIELDS}

    def record(self, *, terminal=False, complete=False, status="running", backend_exit=None):
        self.sequence += 1
        return {"type": "usage.cumulative", "schema_version": 1,
                "dispatch_id": self.dispatch, "invocation_id": self.invocation,
                "session_id": self.session, "requested_model": self.model,
                "requested_identity": self.requested_identity,
                "model_identity": self.observed_identity,
                "sequence": self.sequence, **self.total,
                "budget_tokens": sum(self.total.values()), "models": self.models,
                "terminal": terminal, "complete": complete, "status": status,
                "error": self.error, "backend_exit": backend_exit}


def run(args):
    invocation, session = str(uuid.uuid4()), str(uuid.uuid4())
    meter = Meter(args.model, args.dispatch, invocation, session, args.policy)
    destination = Path(args.events)
    # Never overwrite prior attempts, including raw provider evidence.
    raw_path = Path(str(destination) + "." + invocation + ".raw.jsonl")
    ledger_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    cancelled = [False]
    signal.signal(signal.SIGTERM, lambda *_: cancelled.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda *_: cancelled.__setitem__(0, True))
    status = "running"
    budget_hit = False
    child = None
    with os.fdopen(ledger_fd, "a") as ledger, raw_path.open("x", encoding="utf-8") as raw:
        raw_path.chmod(0o600)

        def emit(**kwargs):
            ledger.write(json.dumps(meter.record(**kwargs), separators=(",", ":")) + "\n")
            ledger.flush()
            if kwargs.get("terminal"):
                os.fsync(ledger.fileno())

        def consume(line):
            nonlocal budget_hit
            raw.write(line.decode("utf-8", errors="replace") + "\n")
            raw.flush()
            try:
                meter.event(json.loads(line))
            except (ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                meter.error = meter.error or str(exc)
            emit()
            if args.budget and sum(meter.total.values()) >= args.budget:
                budget_hit = True

        emit()  # identity before launch, even if the first provider call fails
        command = args.command
        if command and command[0] == "--":
            command = command[1:]
        command += ["--output-format", "stream-json", "--verbose",
                    "--include-partial-messages", "--session-id", session]
        try:
            # Inherit the worker group so the supervisor's final group KILL
            # cannot orphan this adapter or the model's tool children.
            child = subprocess.Popen(command, stdin=sys.stdin, stdout=subprocess.PIPE)
            sel = selectors.DefaultSelector()
            sel.register(child.stdout, selectors.EVENT_READ)
            pending = b""
            stopping_at = None
            term_sent = False
            while sel.get_map():
                stopping = cancelled[0] or budget_hit or bool(meter.error)
                if stopping and stopping_at is None:
                    stopping_at = time.monotonic()
                    if child.poll() is None:
                        child.send_signal(signal.SIGINT)
                if stopping_at is not None and child.poll() is None:
                    elapsed = time.monotonic() - stopping_at
                    if elapsed >= 5 and not term_sent:
                        child.terminate()
                        term_sent = True
                    if elapsed >= 7:
                        child.kill()
                for key, _ in sel.select(0.1):
                    data = os.read(key.fd, 65536)
                    if not data:
                        sel.unregister(key.fileobj)
                        break
                    pending += data
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        consume(line)
                    if len(pending) > MAX_LINE:
                        raise ValueError("provider line exceeds accounting limit")
            sel.close()
            child.stdout.close()
            if pending:
                raw.write(pending.decode("utf-8", errors="replace"))
                meter.error = meter.error or "truncated provider stream"
            backend_exit = child.wait(timeout=8)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            meter.error = meter.error or str(exc)
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            backend_exit = child.returncode if child is not None else 127
        if backend_exit < 0:
            backend_exit = 128 - backend_exit
        if meter.result is None:
            meter.error = meter.error or "provider ended without complete accounting"
        complete = meter.result is not None and not meter.error and not cancelled[0] and not budget_hit
        status = ("budget_exhausted" if budget_hit else "cancelled" if cancelled[0] else
                  "accounting_error" if meter.error else "failed" if backend_exit or
                  meter.result.get("is_error") else "success")
        raw.flush()
        os.fsync(raw.fileno())
        emit(terminal=True, complete=complete, status=status, backend_exit=backend_exit)
        if meter.result and isinstance(meter.result.get("result"), str):
            print(meter.result["result"])
        if status != "success":
            failure = os.environ.get("CLAVAIN_DISPATCH_FAILURE_FILE")
            if failure:
                Path(failure).write_text("terminal_accounting\n")
            print("Claude accounting: " + status + (": " + meter.error if meter.error else ""),
                  file=sys.stderr)
        return backend_exit or (0 if status == "success" else 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True)
    parser.add_argument("--dispatch", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.budget < 0 or not args.command or not args.dispatch or not args.model:
        parser.error("explicit dispatch/model, command and nonnegative budget required")
    try:
        return run(args)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("Claude accounting unavailable: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
