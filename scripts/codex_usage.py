#!/usr/bin/env python3
"""Meter pooled Codex JSONL and reconcile it with scoped hub request evidence.

CLI events remain unchanged on stdout. Account and observed model identity come
only from retained pool evidence; CLI input includes cached input, so subtract
that subset before comparing the pool's disjoint categories.
"""
import argparse
import json
from pathlib import Path
import sys

from claude_usage import FIELDS, Meter as ClaudeMeter, run


class Meter(ClaudeMeter):
    provider = "codex"

    def __init__(self, model, dispatch, invocation, session, policy):
        # The CLI does not attest the model: resolve identity only when the
        # authenticated pool's observed response models are available.
        self.model, self.dispatch, self.invocation = model, dispatch, invocation
        self.session, self.policy = session, policy
        self.requested_identity = self.observed_identity = ""
        self.models = {}
        self.total = dict.fromkeys(FIELDS, 0)
        self.result = None
        self.error = ""
        self.sequence = 0
        self.thread = None
        self.started = False

    def event(self, event):
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError("invalid Codex event")
        if self.result is not None:
            raise ValueError("Codex event after terminal turn")
        kind = event["type"]
        if kind == "thread.started":
            if self.thread is not None or not isinstance(event.get("thread_id"), str) or not event["thread_id"]:
                raise ValueError("invalid Codex thread identity")
            self.thread = self.session = event["thread_id"]
        elif kind == "turn.started":
            if self.thread is None or self.started:
                raise ValueError("unexpected Codex turn")
            self.started = True
        elif kind in ("error", "turn.failed"):
            raise ValueError("Codex provider failure")
        elif kind == "turn.completed":
            if not self.started:
                raise ValueError("Codex completion without turn")
            usage = event.get("usage")
            required = {"input_tokens", "cached_input_tokens", "output_tokens"}
            optional = {"cache_write_input_tokens", "reasoning_output_tokens"}
            if not isinstance(usage, dict) or not required <= usage.keys() or usage.keys() - required - optional:
                raise ValueError("unknown or missing Codex usage fields")
            if any(type(v) is not int or not 0 <= v <= 2**53 for v in usage.values()):
                raise ValueError("invalid Codex usage counts")
            if usage["cached_input_tokens"] > usage["input_tokens"] or usage.get("reasoning_output_tokens", 0) > usage["output_tokens"]:
                raise ValueError("invalid Codex usage subset")
            self.total = dict(input_tokens=usage["input_tokens"] - usage["cached_input_tokens"],
                cache_read_input_tokens=usage["cached_input_tokens"],
                cache_creation_input_tokens=usage.get("cache_write_input_tokens", 0),
                output_tokens=usage["output_tokens"])
            self.result = {"is_error": False}

    def bind_pool(self, ref):
        self.requested_identity = self.identity(self.model)
        data = json.loads(Path(ref["path"]).read_text())
        for request in data["requests"]:
            if request["kind"] == "inference":
                for hop in request["hops"]:
                    self.bind_model(hop["model"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("events", "dispatch", "model", "policy", "pool-receipt", "pool-attempt"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.budget < 0 or not args.command:
        parser.error("a command and nonnegative budget are required")
    try:
        return run(args, Meter)
    except (ValueError, OSError, KeyError, TypeError):
        # Do not include service errors or bearers in diagnostic output.
        print("Codex pool accounting unavailable", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
