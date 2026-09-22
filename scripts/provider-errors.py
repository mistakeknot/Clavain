#!/usr/bin/env python3
"""Classify only provider event envelopes, never task text or tool output."""
import json
import sys

QUOTA = {"usage_limit_exceeded", "quota_exhausted", "insufficient_quota"}
DENIAL = {"permission_denied", "policy_denied", "policy_violation", "forbidden", "403"}
CONFIG = {"invalid_request_error", "authentication_error", "unauthorized", "401", "400"}


def classify(events):
    failures = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") == "event_msg":
            event = event.get("payload", {})
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        error = None
        if kind in ("task_complete", "turn.failed", "error"):
            error = event.get("error")
        elif kind == "result" and event.get("is_error"):
            error = event.get("error", {})
        elif kind == "assistant" and event.get("error"):
            error = event["error"]
        if error is None:
            continue
        codes = {error} if isinstance(error, str) else set()
        if isinstance(error, dict):
            codes = {str(error.get(k, "")) for k in ("codex_error_info", "code", "type", "status")}
        if codes & DENIAL:
            failures.add("terminal_policy")
        elif codes & CONFIG:
            failures.add("terminal_configuration")
        elif codes & QUOTA:
            failures.add("quota_exhausted")
        else:
            failures.add("terminal_error")
    for failure in ("terminal_policy", "terminal_configuration", "terminal_error", "quota_exhausted"):
        if failure in failures:
            return failure
    return ""


def read_events(path):
    try:
        with open(path) as stream:
            for line in stream:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        pass


if __name__ == "__main__":
    print(classify(read_events(sys.argv[1])))
