#!/usr/bin/env python3
"""Paired skill eval: the same case with a skill body injected and not injected.

Adapted from executor-parity-eval.py (governed dispatch, blind judge queue).
For every case and repeat the runner makes one pair of runs, an injected arm
(the skill body is placed in the prompt) and a not-injected arm (it is not).
A judge from the other lab grades each response blind (opaque ids, no arm
label) and may grade the same response several times, which measures judge
noise separately from arm-to-arm variation.

Output is interlab METRIC lines on stdout:

    METRIC lift=<mean injected score - mean not-injected score>
    METRIC lift_sigma=<standard error of that lift over repeats>
    METRIC bytes=<injected skill body bytes>
    METRIC judge_sigma=<std dev of one judge re-grading the same response>

This is a measurement tool only. It builds no gate; per the design notes the
numbers are evidence until noise is characterized.

Real runs go through packaged ``dispatch.sh --role`` only. ``--fake-executor``
and ``--fake-judge`` replace the model calls with deterministic stand-ins so
tests (and ``--self-test``) make no model calls.

Case file: JSON list of {"id", "prompt", "rubric"}.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import secrets
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

ARMS = ("injected", "baseline")
DEFAULT_EXECUTOR_ROLE = "routine-execution"
DEFAULT_JUDGE_ROLE = "cross-lab-review"
FAKE_EXECUTOR_IDENTITY = "fake-executor"

# executor(arm, case, skill_body_or_None) -> (response text, identity of the
# model that actually produced it)
Executor = Callable[[str, dict, Optional[str]], tuple]
# judge(case, response, producer_identity) -> score in [0, 1]
Judge = Callable[[dict, str, str], float]


@dataclass
class Run:
    case_id: str
    repeat: int
    arm: str
    response: str = ""
    identity: str = ""  # model that actually produced the response
    blind_id: str = ""
    scores: list = field(default_factory=list)  # one entry per judge pass


def build_pairs(cases: Sequence[dict], repeats: int) -> list[Run]:
    """One injected and one baseline run per (case, repeat), adjacent."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    runs: list[Run] = []
    for case in cases:
        for repeat in range(repeats):
            for arm in ARMS:
                runs.append(Run(case["id"], repeat, arm))
    return runs


def assign_blind_ids(runs: Sequence[Run], seed: Optional[int] = None) -> list[Run]:
    """Give each run an opaque id and return runs in shuffled judge order."""
    rng = random.Random(seed)
    order = list(runs)
    rng.shuffle(order)
    used: set[str] = set()
    for run in order:
        while True:
            token = f"r{secrets.token_hex(4) if seed is None else '%08x' % rng.getrandbits(32)}"
            if token not in used:
                used.add(token)
                run.blind_id = token
                break
    return order


def judge_prompt(case: dict, response: str) -> str:
    """Judge brief: no arm label, no skill identity."""
    return (
        "You grade one response to a task against a rubric. Be strict and "
        "consistent.\n\n"
        f"TASK:\n{case['prompt']}\n\nRUBRIC:\n{case['rubric']}\n\n"
        f"RESPONSE:\n{response}\n\n"
        "Reply with brief reasoning, then a final line exactly of the form "
        "`SCORE: <number from 0 to 1>` (1 = fully meets the rubric)."
    )


_VERDICT_LINE_RE = re.compile(r"VERDICT: (?:PASS|PASS WITH NOTES|FAIL)")
_SCORE_LINE_RE = re.compile(r"SCORE: ([0-9]+(?:\.[0-9]+)?|\.[0-9]+)")


def parse_score(text: str) -> float:
    """Parse the judge's verdict: the last non-blank line must be exactly
    ``SCORE: <decimal in [0, 1]>`` and no other line may start a score.

    Anything else (trailing text, exponents, nan/inf, out of range, a score
    quoted in the reasoning) raises ValueError; callers treat that as a judge
    failure, never as a measurement.
    """
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if lines and _VERDICT_LINE_RE.fullmatch(lines[-1]):
        lines = lines[:-1]  # the packaged role contract appends a final VERDICT line
    if not lines:
        raise ValueError("judge reply is empty")
    match = _SCORE_LINE_RE.fullmatch(lines[-1])
    if not match:
        raise ValueError("judge reply does not end with a complete `SCORE: <number>` line")
    if any(re.search(r"SCORE\s*:", line) for line in lines[:-1]):
        raise ValueError("judge reply mentions SCORE before the final line")
    value = float(match.group(1))
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"judge score out of range: {match.group(1)}")
    return value


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sample_var(values: Sequence[float]) -> float:
    return statistics.variance(values) if len(values) >= 2 else 0.0


def compute_metrics(runs: Sequence[Run], skill_bytes: int) -> dict:
    """Lift, its standard error, judge noise and bytes.

    Each run's score is the mean of its judge passes. Lift is the mean over
    paired (case, repeat) differences; lift_sigma is the standard error of
    those paired differences (0.0 with fewer than two pairs, meaning unknown).
    judge_sigma pools within-run variance over runs judged more than once.
    """
    by_key: dict = {}
    for run in runs:
        if not run.scores:
            continue
        by_key.setdefault((run.case_id, run.repeat), {})[run.arm] = _mean(run.scores)
    diffs = [
        arms["injected"] - arms["baseline"]
        for arms in by_key.values()
        if "injected" in arms and "baseline" in arms
    ]
    lift = _mean(diffs)
    lift_sigma = math.sqrt(_sample_var(diffs) / len(diffs)) if len(diffs) >= 2 else 0.0
    inj = [_mean(r.scores) for r in runs if r.arm == "injected" and r.scores]
    base = [_mean(r.scores) for r in runs if r.arm == "baseline" and r.scores]
    num = sum(_sample_var(r.scores) * (len(r.scores) - 1) for r in runs if len(r.scores) >= 2)
    den = sum(len(r.scores) - 1 for r in runs if len(r.scores) >= 2)
    judge_sigma = math.sqrt(num / den) if den else 0.0
    return {
        "lift": lift,
        "lift_sigma": lift_sigma,
        "bytes": skill_bytes,
        "judge_sigma": judge_sigma,
        "pairs": len(diffs),
        "mean_injected": _mean(inj),
        "mean_baseline": _mean(base),
    }


def format_metric_lines(metrics: dict) -> list[str]:
    """interlab METRIC lines: ``METRIC name=value``, one per line."""
    lines = []
    for name in ("lift", "lift_sigma", "bytes", "judge_sigma"):
        value = metrics[name]
        text = str(int(value)) if name == "bytes" else f"{value:.6f}"
        lines.append(f"METRIC {name}={text}")
    return lines


def run_eval(
    cases: Sequence[dict],
    skill_body: str,
    repeats: int,
    judge_passes: int,
    executor: Executor,
    judge: Judge,
    seed: Optional[int] = None,
) -> tuple[dict, list[Run]]:
    if judge_passes < 1:
        raise ValueError("judge passes must be at least 1")
    runs = build_pairs(cases, repeats)  # validates repeats before any run
    by_id = {c["id"]: c for c in cases}
    for run in runs:
        body = skill_body if run.arm == "injected" else None
        run.response, run.identity = executor(run.arm, by_id[run.case_id], body)
        if not isinstance(run.identity, str) or not run.identity.strip():
            raise ValueError("executor did not report the identity it ran on")
    for run in assign_blind_ids(runs, seed):
        for _ in range(judge_passes):
            run.scores.append(judge(by_id[run.case_id], run.response, run.identity))
    return compute_metrics(runs, len(skill_body.encode("utf-8"))), runs


# ---- fakes (no model calls) ------------------------------------------------

def fake_executor(arm: str, case: dict, skill_body: Optional[str]) -> tuple:
    text = f"answer to {case['id']}" + (" [follows-skill]" if skill_body else "")
    return text, FAKE_EXECUTOR_IDENTITY


def fake_judge(case: dict, response: str, identity: str) -> float:
    return 1.0 if "[follows-skill]" in response else 0.25


# ---- real dispatch -----------------------------------------------------------

def read_receipt_identity(receipt_file: Path, role: str) -> str:
    """Model that actually served a dispatch, from its run receipts.

    Uses ``observed_model`` only; ``model`` is the requested model and is never
    trusted. Dispatch writes "unknown" when the model could not be observed,
    which fails closed, as do a missing or blank value, no completed exit-0
    receipt for ``role``, or receipts that disagree. A mismatch between the
    observed and requested model is fine: the observed value is the truth.
    """
    models: set[str] = set()
    if receipt_file.is_file():
        for line in receipt_file.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (isinstance(rec, dict) and rec.get("role") == role
                    and rec.get("outcome") == "completed" and rec.get("exit_code") == 0):
                value = rec.get("observed_model")
                if not isinstance(value, str) or value.strip().lower() in ("", "unknown"):
                    # a completed receipt with no usable identity is never skipped
                    raise RuntimeError("a completed dispatch receipt has no observed model")
                models.add(value.strip())
    if len(models) != 1:
        raise RuntimeError(
            f"cannot determine the executor identity from the dispatch receipt "
            f"({len(models)} distinct completed models)")
    return models.pop()


def _dispatch(dispatch: Path, role: str, identity: Optional[str], prompt: str,
              timeout: float) -> tuple:
    """Run one prompt through packaged dispatch.sh --role.

    Returns (reply text, actual model identity from the run receipt). The
    receipt goes to a private per-call file so only this call's records count.
    """
    with tempfile.TemporaryDirectory(prefix="skill-eval-") as tmp:
        root = Path(tmp)
        ctx = root / "context.json"
        ctx.write_text(json.dumps({"reasons": [], "rationale": "skill eval run; routine settled work"}))
        pf = root / "prompt.md"
        pf.write_text(prompt)
        out = root / "out.md"
        work = root / "work"
        work.mkdir()
        receipts = root / "receipts.jsonl"
        cmd = [str(dispatch), "--role", role, "--context-file", str(ctx)]
        if identity is not None:
            cmd += ["--producer-identity", identity]
        cmd += ["-s", "read-only", "-C", str(work), "--prompt-file", str(pf), "-o", str(out)]
        env = {**os.environ, "CLAVAIN_DISPATCH_RECEIPT_FILE": str(receipts)}
        done = subprocess.run(cmd, check=False, capture_output=True, text=True,
                              timeout=timeout, env=env)
        if done.returncode != 0:
            raise RuntimeError(f"dispatch failed (exit {done.returncode}): {done.stderr.strip()[-300:]}")
        text = out.read_text() if out.is_file() else done.stdout
        if not text.strip():
            raise RuntimeError("dispatch returned an empty reply")
        return text, read_receipt_identity(receipts, role)


def executor_prompt(case: dict, skill_body: Optional[str]) -> str:
    if skill_body is None:
        return case["prompt"] + "\n\nAnswer in text only; do not use tools."
    return (
        "The following skill is in effect for this task.\n\n"
        f"<skill>\n{skill_body}\n</skill>\n\n{case['prompt']}\n\n"
        "Answer in text only; do not use tools."
    )


def require_audit_db(env=None) -> str:
    """Absolute path of the Intercore DB that dispatch must record routing in.

    Each dispatch runs from a temporary workdir with no .clavain tree, so ic
    cannot discover a DB there and the routing decision would go unrecorded
    (terminal_recording). dispatch.sh records through CLAVAIN_INTERCORE_DB when
    it is set, so a real run requires it up front rather than failing mid-run.
    """
    db = (os.environ if env is None else env).get("CLAVAIN_INTERCORE_DB", "")
    if not db:
        raise ValueError(
            "CLAVAIN_INTERCORE_DB is not set: dispatch runs from a temporary workdir with no "
            ".clavain tree, so its routing decisions could not be recorded; set it to the "
            "absolute path of the Intercore database to record in")
    if not os.path.isabs(db) or not os.path.isfile(db):
        raise ValueError("CLAVAIN_INTERCORE_DB must be an absolute path to an existing database file")
    return db


def make_dispatch_callables(dispatch: Path, executor_role: str, judge_role: str,
                            timeout: float) -> tuple[Executor, Judge]:
    def executor(arm: str, case: dict, body: Optional[str]) -> tuple:
        return _dispatch(dispatch, executor_role, None, executor_prompt(case, body), timeout)

    def judge(case: dict, response: str, identity: str) -> float:
        text, judge_model = _dispatch(dispatch, judge_role, identity, judge_prompt(case, response), timeout)
        if judge_model == identity:
            raise RuntimeError(f"judge ran on the producer's model ({identity}); not cross-model")
        return parse_score(text)

    return executor, judge


def load_cases(path: Path) -> list[dict]:
    cases = json.loads(path.read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError("case file must be a non-empty JSON list")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each case must be a JSON object")
        for key in ("id", "prompt", "rubric"):
            if not isinstance(case.get(key), str) or not case[key]:
                raise ValueError(f"case missing {key}: {case!r:.80}")
        if case["id"] in seen:
            raise ValueError(f"duplicate case id: {case['id']}")
        seen.add(case["id"])
    return cases


def build_parser() -> argparse.ArgumentParser:
    doc = (__doc__ or "Paired skill eval runner.").strip()
    p = argparse.ArgumentParser(description=doc.split("\n\n")[0])
    p.add_argument("--skill", type=Path, required=True, help="SKILL.md whose body is injected")
    p.add_argument("--cases", type=Path, required=True, help="JSON case file")
    p.add_argument("--repeats", type=int, default=3, help="repeats per arm (max 3 for the spike)")
    p.add_argument("--judge-passes", type=int, default=2, help="times each response is judged")
    p.add_argument("--dispatch", type=Path, help="dispatch.sh path (default: alongside this script)")
    p.add_argument("--executor-role", default=DEFAULT_EXECUTOR_ROLE)
    p.add_argument("--judge-role", default=DEFAULT_JUDGE_ROLE)
    p.add_argument("--timeout", type=float, default=600.0)
    p.add_argument("--seed", type=int, help="seed for blind order (tests)")
    p.add_argument("--fake-executor", action="store_true", help="no model call for the executor")
    p.add_argument("--fake-judge", action="store_true", help="no model call for the judge")
    p.add_argument("--details", type=Path, help="write per-run JSON here")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.repeats < 1 or args.judge_passes < 1:
            raise ValueError("--repeats and --judge-passes must each be at least 1")
        cases = load_cases(args.cases)
        body = args.skill.read_text()
        executor: Executor = fake_executor
        judge: Judge = fake_judge
        if not (args.fake_executor and args.fake_judge):
            dispatch = args.dispatch or Path(__file__).with_name("dispatch.sh")
            if not dispatch.is_file():
                raise ValueError(f"dispatch script not found: {dispatch}")
            require_audit_db()
            real_exec, real_judge = make_dispatch_callables(
                dispatch, args.executor_role, args.judge_role, args.timeout)
            executor = fake_executor if args.fake_executor else real_exec
            judge = fake_judge if args.fake_judge else real_judge
        metrics, runs = run_eval(cases, body, args.repeats, args.judge_passes, executor, judge, args.seed)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.details:
        args.details.write_text(json.dumps([
            {"case": r.case_id, "repeat": r.repeat, "arm": r.arm, "scores": r.scores}
            for r in runs], indent=2))
    print("\n".join(format_metric_lines(metrics)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
