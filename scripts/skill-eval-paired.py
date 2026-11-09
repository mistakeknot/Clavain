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
DEFAULT_EXECUTOR_IDENTITY = "claude-sonnet-5-5"

# executor(arm, case, skill_body_or_None) -> response text
Executor = Callable[[str, dict, Optional[str]], str]
# judge(case, response) -> score in [0, 1]
Judge = Callable[[dict, str], float]


@dataclass
class Run:
    case_id: str
    repeat: int
    arm: str
    response: str = ""
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


_SCORE_RE = re.compile(r"SCORE:\s*([0-9]*\.?[0-9]+)")


def parse_score(text: str) -> float:
    matches = _SCORE_RE.findall(text)
    if not matches:
        raise ValueError("judge reply has no SCORE line")
    value = float(matches[-1])
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"judge score out of range: {value}")
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
    runs = build_pairs(cases, repeats)
    by_id = {c["id"]: c for c in cases}
    for run in runs:
        body = skill_body if run.arm == "injected" else None
        run.response = executor(run.arm, by_id[run.case_id], body)
    for run in assign_blind_ids(runs, seed):
        for _ in range(judge_passes):
            run.scores.append(judge(by_id[run.case_id], run.response))
    return compute_metrics(runs, len(skill_body.encode("utf-8"))), runs


# ---- fakes (no model calls) ------------------------------------------------

def fake_executor(arm: str, case: dict, skill_body: Optional[str]) -> str:
    return f"answer to {case['id']}" + (" [follows-skill]" if skill_body else "")


def fake_judge(case: dict, response: str) -> float:
    return 1.0 if "[follows-skill]" in response else 0.25


# ---- real dispatch -----------------------------------------------------------

def _dispatch(dispatch: Path, role: str, identity: str, prompt: str,
              timeout: float) -> str:
    """Run one prompt through packaged dispatch.sh --role; return the reply."""
    with tempfile.TemporaryDirectory(prefix="skill-eval-") as tmp:
        root = Path(tmp)
        ctx = root / "context.json"
        ctx.write_text(json.dumps({"reasons": [], "rationale": "skill eval run; routine settled work"}))
        pf = root / "prompt.md"
        pf.write_text(prompt)
        out = root / "out.md"
        work = root / "work"
        work.mkdir()
        cmd = [
            str(dispatch), "--role", role, "--context-file", str(ctx),
            "--producer-identity", identity, "-s", "read-only", "-C", str(work),
            "--prompt-file", str(pf), "-o", str(out),
        ]
        done = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
        if done.returncode != 0:
            raise RuntimeError(f"dispatch failed (exit {done.returncode}): {done.stderr.strip()[-300:]}")
        text = out.read_text() if out.is_file() else done.stdout
        if not text.strip():
            raise RuntimeError("dispatch returned an empty reply")
        return text


def executor_prompt(case: dict, skill_body: Optional[str]) -> str:
    if skill_body is None:
        return case["prompt"] + "\n\nAnswer in text only; do not use tools."
    return (
        "The following skill is in effect for this task.\n\n"
        f"<skill>\n{skill_body}\n</skill>\n\n{case['prompt']}\n\n"
        "Answer in text only; do not use tools."
    )


def make_dispatch_callables(dispatch: Path, executor_role: str, judge_role: str,
                            identity: str, timeout: float) -> tuple[Executor, Judge]:
    def executor(arm: str, case: dict, body: Optional[str]) -> str:
        return _dispatch(dispatch, executor_role, identity, executor_prompt(case, body), timeout)

    def judge(case: dict, response: str) -> float:
        return parse_score(_dispatch(dispatch, judge_role, identity, judge_prompt(case, response), timeout))

    return executor, judge


def load_cases(path: Path) -> list[dict]:
    cases = json.loads(path.read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError("case file must be a non-empty JSON list")
    for case in cases:
        for key in ("id", "prompt", "rubric"):
            if not isinstance(case.get(key), str) or not case[key]:
                raise ValueError(f"case missing {key}: {case!r:.80}")
    return cases


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--skill", type=Path, required=True, help="SKILL.md whose body is injected")
    p.add_argument("--cases", type=Path, required=True, help="JSON case file")
    p.add_argument("--repeats", type=int, default=3, help="repeats per arm (max 3 for the spike)")
    p.add_argument("--judge-passes", type=int, default=2, help="times each response is judged")
    p.add_argument("--dispatch", type=Path, help="dispatch.sh path (default: alongside this script)")
    p.add_argument("--executor-role", default=DEFAULT_EXECUTOR_ROLE)
    p.add_argument("--judge-role", default=DEFAULT_JUDGE_ROLE)
    p.add_argument("--executor-identity", default=DEFAULT_EXECUTOR_IDENTITY,
                   help="producer identity passed to the judge's role resolution")
    p.add_argument("--timeout", type=float, default=600.0)
    p.add_argument("--seed", type=int, help="seed for blind order (tests)")
    p.add_argument("--fake-executor", action="store_true", help="no model call for the executor")
    p.add_argument("--fake-judge", action="store_true", help="no model call for the judge")
    p.add_argument("--details", type=Path, help="write per-run JSON here")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = load_cases(args.cases)
        body = args.skill.read_text()
        executor: Executor = fake_executor
        judge: Judge = fake_judge
        if not (args.fake_executor and args.fake_judge):
            dispatch = args.dispatch or Path(__file__).with_name("dispatch.sh")
            if not dispatch.is_file():
                raise ValueError(f"dispatch script not found: {dispatch}")
            real_exec, real_judge = make_dispatch_callables(
                dispatch, args.executor_role, args.judge_role, args.executor_identity, args.timeout)
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
