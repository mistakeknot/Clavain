"""VerificationStep primitive — explicit checkpoint contract for state transitions.

Vendored from interflux/scripts/_verification.py (BP-C2.A) — companion plugins
install independently in user environments, so cross-plugin imports are unsafe.
The schema (field set, enum values, JSONL format) MUST stay identical to the
upstream copy; if upstream changes, re-sync this file and the matching tests.

A VerificationStep records that a state transition was checked, with three
possible verdicts:

    VERIFIED              — the precondition was checked and held
    FAILED_VERIFICATION   — the precondition was checked and did not hold
    UNVERIFIABLE          — the check could not be performed (missing data,
                            broken tool, etc.). UNVERIFIABLE is NOT success.

Use this anywhere a "no-op short-circuit" pattern would otherwise erase the
audit trail — i.e., when a code path skips a normally-recorded operation
because some condition was already met. The skip itself must emit a
VerificationStep so the audit log distinguishes "we checked and were correct
to skip" from "we never checked".

The canonical case is the microrouter no-op short-circuit (Sylveste-a5u): when
microrouter recommendation matches B3 calibration, the resolver short-circuits
without writing a shadow log entry. Operators can't distinguish "router said
sonnet" from "router was skipped". The fix is a VerificationStep with
decision_type='passthrough' on the no-op branch.

Public API:

    step = VerificationStep.verified(name, evidence, **kwargs)
    step = VerificationStep.failed(name, evidence, **kwargs)
    step = VerificationStep.unverifiable(name, evidence, **kwargs)
    step.is_success()         -> True iff state == VERIFIED
    step.to_dict()            -> JSON-friendly dict
    step.to_jsonl_line()      -> single-line JSON string

CLI:
    python3 _verification.py --demo
    python3 _verification.py emit --name N --state S --evidence E \
        [--decision-type T] [--log-path P]

The `emit` subcommand is the Bash-callable bridge used by lib-routing.sh:
constructs a step from CLI args and either appends to --log-path or writes
the JSONL line to stdout. run_uuid auto-flows from FLUX_RUN_UUID env.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class VerificationState(str, Enum):
    """Outcome of a verification check.

    Inheriting from str makes JSON serialization use the bare string value
    ('VERIFIED' / 'FAILED_VERIFICATION' / 'UNVERIFIABLE') without custom
    encoders.
    """

    VERIFIED = "VERIFIED"
    FAILED_VERIFICATION = "FAILED_VERIFICATION"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class VerificationStep:
    """A single audit checkpoint.

    Fields:
        name        — short kebab-case identifier (e.g. 'microrouter-passthrough')
        state       — one of VerificationState.{VERIFIED, FAILED_VERIFICATION, UNVERIFIABLE}
        evidence    — human-readable string describing what was checked + outcome
        decision_type (optional) — 'override' | 'passthrough' | 'skipped' | 'timed-out' |
                       'agent-ineligible' | 'endpoint-unreachable' | <custom>
        run_uuid (optional) — opaque run identifier; correlates with run_uuid quire-mark
                              (BP-C2.B). Auto-populated from FLUX_RUN_UUID env if unset.
        timestamp_ms — monotonic-ish epoch milliseconds (auto-populated)
        step_id     — uuid4 for this step (auto-populated)
        extra       — caller-supplied JSON-serializable extras
    """

    name: str
    state: VerificationState
    evidence: str
    decision_type: str | None = None
    run_uuid: str | None = None
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Auto-fill run_uuid from env if not provided. Use object.__setattr__
        # because dataclass is frozen.
        if self.run_uuid is None:
            env_uuid = os.environ.get("FLUX_RUN_UUID")
            if env_uuid:
                object.__setattr__(self, "run_uuid", env_uuid)
        # Validate state — defensive; dataclass type hints aren't runtime-checked.
        if not isinstance(self.state, VerificationState):
            raise TypeError(
                f"state must be VerificationState, got {type(self.state).__name__}"
            )
        if not self.name or not isinstance(self.name, str):
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.evidence, str):
            raise ValueError("evidence must be a string")

    # --- Factory constructors -------------------------------------------

    @classmethod
    def verified(
        cls,
        name: str,
        evidence: str,
        *,
        decision_type: str | None = None,
        run_uuid: str | None = None,
        **extra: Any,
    ) -> VerificationStep:
        return cls(
            name=name,
            state=VerificationState.VERIFIED,
            evidence=evidence,
            decision_type=decision_type,
            run_uuid=run_uuid,
            extra=dict(extra),
        )

    @classmethod
    def failed(
        cls,
        name: str,
        evidence: str,
        *,
        decision_type: str | None = None,
        run_uuid: str | None = None,
        **extra: Any,
    ) -> VerificationStep:
        return cls(
            name=name,
            state=VerificationState.FAILED_VERIFICATION,
            evidence=evidence,
            decision_type=decision_type,
            run_uuid=run_uuid,
            extra=dict(extra),
        )

    @classmethod
    def unverifiable(
        cls,
        name: str,
        evidence: str,
        *,
        decision_type: str | None = None,
        run_uuid: str | None = None,
        **extra: Any,
    ) -> VerificationStep:
        return cls(
            name=name,
            state=VerificationState.UNVERIFIABLE,
            evidence=evidence,
            decision_type=decision_type,
            run_uuid=run_uuid,
            extra=dict(extra),
        )

    # --- Accessors ------------------------------------------------------

    def is_success(self) -> bool:
        """Return True iff state is VERIFIED. UNVERIFIABLE is NOT success."""
        return self.state == VerificationState.VERIFIED

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Enum → string for clean JSON without a custom encoder.
        d["state"] = self.state.value
        # Drop None fields for compactness.
        return {k: v for k, v in d.items() if v is not None and v != {}}

    def to_jsonl_line(self) -> str:
        """Render as a single JSON line suitable for appending to a log."""
        return json.dumps(self.to_dict(), separators=(",", ":"))


def append_to_log(step: VerificationStep, log_path: str) -> None:
    """Append a step to a JSONL log file.

    Single-line writes <PIPE_BUF (~4KB) under O_APPEND are atomic on Linux,
    so concurrent appenders don't need flock.
    """
    with open(log_path, "a") as f:
        f.write(step.to_jsonl_line() + "\n")


# --- CLI -------------------------------------------------------------------


def _demo() -> int:
    samples = [
        VerificationStep.verified(
            "microrouter-passthrough",
            "matched B3 calibration: sonnet",
            decision_type="passthrough",
            slug="fd-architecture",
        ),
        VerificationStep.failed(
            "safety-floor-check",
            "fd-safety routed to haiku — should be sonnet floor",
            decision_type="agent-ineligible",
        ),
        VerificationStep.unverifiable(
            "shadow-log-fetch",
            "interspect endpoint unreachable: connection refused",
            decision_type="endpoint-unreachable",
        ),
    ]
    for s in samples:
        print(s.to_jsonl_line())
    return 0


def _emit(argv: list[str]) -> int:
    """`emit` subcommand — Bash-callable bridge.

    Constructs a VerificationStep from CLI args. If --log-path is given,
    appends the JSONL line atomically; otherwise prints to stdout. Errors
    write a one-line diagnostic to stderr and return non-zero so callers
    can detect emit failure (the audit trail is the point).
    """
    parser = argparse.ArgumentParser(prog="_verification.py emit")
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--state",
        required=True,
        choices=[s.value for s in VerificationState],
    )
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--decision-type", default=None)
    parser.add_argument("--log-path", default=None)
    parser.add_argument("--run-uuid", default=None)
    args = parser.parse_args(argv)

    try:
        step = VerificationStep(
            name=args.name,
            state=VerificationState(args.state),
            evidence=args.evidence,
            decision_type=args.decision_type,
            run_uuid=args.run_uuid,
        )
    except (TypeError, ValueError) as exc:
        print(f"[verification-emit-fail] construct: {exc}", file=sys.stderr)
        return 2

    if args.log_path:
        try:
            os.makedirs(os.path.dirname(args.log_path) or ".", exist_ok=True)
            append_to_log(step, args.log_path)
        except OSError as exc:
            print(f"[verification-emit-fail] write {args.log_path}: {exc}", file=sys.stderr)
            return 3
    else:
        print(step.to_jsonl_line())
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in ("--demo", "demo"):
        return _demo()
    if argv and argv[0] == "emit":
        return _emit(argv[1:])
    print(__doc__, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
