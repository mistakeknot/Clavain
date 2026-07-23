#!/usr/bin/env python3
"""Compare two dispatch executors without leaking source identity to judges.

The normal path is deliberately split into three stages:

1. Run the same JSONL prompts through the cheap and stronger backends.
2. Compute mechanical yield/coverage/agreement metrics and write a blind,
   interleaved judge queue whose rows contain only an opaque id and response.
3. After a human or external judge fills defensibility scores, apply the
   explicit PARITY/PIN_STRONGER threshold.

Use ``--self-test`` for a backend-free check of the metric and blinding paths.
The real-run path is opt-in and is not used by Clavain's routing tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


DEFAULT_MARGIN = 0.05
PARSE_MODES = ("json-array", "json-object", "raw")


def _canonical(value: Any) -> str:
    """Return a stable representation suitable for set comparison."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_json_output(text: str) -> Any:
    """Decode JSON from a response, tolerating a fenced or prefixed reply."""

    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
                return value
            except json.JSONDecodeError:
                continue
    raise ValueError("response did not contain valid JSON")


def parse_comparable_set(text: str, parse_mode: str) -> Optional[frozenset[str]]:
    """Parse a response into a comparable set, or None for yield-only mode."""

    if parse_mode == "raw":
        return None
    value = _decode_json_output(text)
    if parse_mode == "json-array":
        if not isinstance(value, list):
            raise ValueError("json-array mode requires a JSON array")
        return frozenset(_canonical(item) for item in value)
    if parse_mode == "json-object":
        if not isinstance(value, dict):
            raise ValueError("json-object mode requires a JSON object")
        return frozenset(
            f"{_canonical(key)}={_canonical(item)}" for key, item in value.items()
        )
    raise ValueError(f"unknown parse mode: {parse_mode}")


@dataclass
class ResponseRecord:
    """One backend response; backend identity never enters the judge queue."""

    prompt_id: str
    backend: str
    output: str
    returncode: int
    elapsed_seconds: float
    stderr: str = ""
    comparable_set: Optional[frozenset[str]] = None
    parse_error: str = ""

    @property
    def yielded(self) -> bool:
        return self.returncode == 0 and bool(self.output.strip())

    @property
    def dropped(self) -> bool:
        return not self.yielded


def compute_metrics(records: Sequence[ResponseRecord], comparable: bool) -> dict[str, Any]:
    """Compute yield, coverage, drops, and wall-clock metrics for a backend."""

    total = len(records)
    yielded = sum(record.yielded for record in records)
    drops = sum(record.dropped for record in records)
    parseable = sum(record.comparable_set is not None for record in records)
    # Raw responses have no comparable set; for them coverage is explicitly
    # the yield rate and agreement is reported as yield-only.
    coverage_count = parseable if comparable else yielded
    wall_clock = sum(record.elapsed_seconds for record in records)
    return {
        "total": total,
        "yield": yielded / total if total else 0.0,
        "yield_count": yielded,
        "coverage": coverage_count / total if total else 0.0,
        "coverage_count": coverage_count,
        "drops": drops,
        "drop_rate": drops / total if total else 0.0,
        "parse_failures": sum(bool(record.parse_error) for record in records),
        "wall_clock_seconds": wall_clock,
        "wall_clock_mean_seconds": wall_clock / total if total else 0.0,
    }


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def agreement_tier(
    left: Optional[frozenset[str]], right: Optional[frozenset[str]]
) -> tuple[str, float]:
    """Classify agreement from exact through partial, or yield-only."""

    if left is None or right is None:
        return "yield-only", 0.0
    score = _jaccard(left, right)
    if score == 1.0:
        return "exact", score
    if score >= 0.8:
        return "strong", score
    if score > 0.0:
        return "partial", score
    return "none", score


def tiered_agreement(
    cheap: Sequence[ResponseRecord], strong: Sequence[ResponseRecord]
) -> dict[str, Any]:
    """Compare aligned response sets while preserving yield-only cases."""

    if len(cheap) != len(strong):
        raise ValueError("agreement requires aligned prompt records")
    tiers = {"exact": 0, "strong": 0, "partial": 0, "none": 0, "yield-only": 0}
    scores: list[float] = []
    for cheap_record, strong_record in zip(cheap, strong):
        tier, score = agreement_tier(
            cheap_record.comparable_set, strong_record.comparable_set
        )
        tiers[tier] += 1
        if tier != "yield-only":
            scores.append(score)
    comparable_pairs = len(scores)
    return {
        "tiers": tiers,
        "comparable_pairs": comparable_pairs,
        "yield_only_pairs": tiers["yield-only"],
        "mean_jaccard": sum(scores) / comparable_pairs if comparable_pairs else None,
    }


def _opaque_id(seed: int, ordinal: int) -> str:
    """Create an opaque id that carries no prompt or backend identity."""

    nonce = secrets.token_hex(8)
    digest = hashlib.sha256(f"{seed}:{ordinal}:{nonce}".encode()).hexdigest()[:20]
    return f"j-{digest}"


def build_blind_judge_queue(
    cheap: Sequence[ResponseRecord],
    strong: Sequence[ResponseRecord],
    seed: int = 0,
) -> tuple[list[dict[str, str]], dict[str, tuple[str, str]]]:
    """Return interleaved source-free rows and an in-memory assignment map.

    The assignment map is intentionally returned separately and is never
    serialized. This is what lets the evaluator aggregate scores without
    handing the judge a ``source`` or ``backend`` key.
    """

    if len(cheap) != len(strong):
        raise ValueError("judge queue requires aligned prompt records")
    rows: list[dict[str, str]] = []
    assignments: dict[str, tuple[str, str]] = {}
    ordinal = 0
    for cheap_record, strong_record in zip(cheap, strong):
        for record in (cheap_record, strong_record):
            judge_id = _opaque_id(seed, ordinal)
            ordinal += 1
            rows.append({"id": judge_id, "response": record.output})
            assignments[judge_id] = (record.backend, record.prompt_id)
    random.Random(seed).shuffle(rows)
    return rows, assignments


def write_judge_queue(path: Path, rows: Iterable[Mapping[str, str]]) -> None:
    """Write only opaque id/response rows; no source/backend metadata."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def load_judge_scores(path: Path) -> dict[str, float]:
    """Load ``id`` + ``defensibility`` values from JSONL or a JSON list/map."""

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    values: Any
    try:
        values = json.loads(text)
    except json.JSONDecodeError:
        values = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(values, dict):
        values = values.get("scores", values.get("items", values))
    if isinstance(values, dict):
        return {str(key): float(value) for key, value in values.items()}
    scores: dict[str, float] = {}
    for item in values:
        if not isinstance(item, Mapping):
            raise ValueError("judge score rows must be objects")
        identifier = item.get("id", item.get("judge_id"))
        score = item.get("defensibility")
        if identifier is None or score is None:
            raise ValueError("judge score rows require id and defensibility")
        scores[str(identifier)] = float(score)
    return scores


def aggregate_defensibility(
    assignments: Mapping[str, tuple[str, str]], scores: Mapping[str, float]
) -> dict[str, float]:
    """Aggregate blind scores by backend only after the judge is finished."""

    grouped: dict[str, list[float]] = {}
    for identifier, score in scores.items():
        if identifier not in assignments:
            raise ValueError(f"judge score id not present in queue: {identifier}")
        backend, _ = assignments[identifier]
        grouped.setdefault(backend, []).append(float(score))
    return {
        backend: sum(values) / len(values)
        for backend, values in grouped.items()
        if values
    }


def explicit_verdict(
    cheap_defensibility: float,
    strong_defensibility: float,
    cheap_coverage: float,
    strong_coverage: float,
    cheap_drops: int,
    strong_drops: int,
    margin: float = DEFAULT_MARGIN,
) -> dict[str, Any]:
    """Apply the doctrine's explicit threshold without hidden weighting."""

    parity = (
        cheap_defensibility >= strong_defensibility - margin
        and cheap_coverage >= strong_coverage
        and cheap_drops <= strong_drops
    )
    return {
        "verdict": "PARITY" if parity else "PIN_STRONGER",
        "margin": margin,
        "cheap_defensibility": cheap_defensibility,
        "strong_defensibility": strong_defensibility,
        "cheap_coverage": cheap_coverage,
        "strong_coverage": strong_coverage,
        "cheap_drops": cheap_drops,
        "strong_drops": strong_drops,
    }


def _load_prompts(path: Path) -> list[dict[str, str]]:
    prompts: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid prompt JSON on line {line_number}: {exc}") from exc
        if not isinstance(item, Mapping) or "id" not in item or "prompt" not in item:
            raise ValueError(f"prompt line {line_number} requires id and prompt")
        prompts.append({"id": str(item["id"]), "prompt": str(item["prompt"])})
    if not prompts:
        raise ValueError("prompts file contains no JSONL prompts")
    return prompts


def run_prompt(
    dispatch: Path,
    backend: str,
    prompt_id: str,
    prompt: str,
    parse_mode: str,
    workdir: Optional[Path],
    timeout: float,
) -> ResponseRecord:
    """Run one prompt through dispatch; callers opt into this real-run path."""

    command = [
        str(dispatch),
        "--to",
        backend,
        "--dry-run=false",
        "-o",
        "-",
    ]
    if workdir is not None:
        command.extend(("-C", str(workdir)))
    command.append(prompt)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = completed.stdout
        returncode = completed.returncode
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        returncode = 124
        stderr = f"timeout after {timeout}s\n{exc.stderr or ''}"
    elapsed = time.monotonic() - started
    record = ResponseRecord(
        prompt_id=prompt_id,
        backend=backend,
        output=output,
        returncode=returncode,
        elapsed_seconds=elapsed,
        stderr=stderr,
    )
    if parse_mode != "raw" and record.yielded:
        try:
            record.comparable_set = parse_comparable_set(output, parse_mode)
        except ValueError as exc:
            record.parse_error = str(exc)
    return record


def _metrics_by_backend(
    records: Sequence[ResponseRecord],
    backend: str,
    comparable: bool,
) -> dict[str, Any]:
    return compute_metrics(
        [record for record in records if record.backend == backend], comparable
    )


def run_self_test() -> None:
    """Exercise metric, agreement, blinding, and threshold functions locally."""

    cheap = [
        ResponseRecord("one", "cheap", '["a", "b"]', 0, 0.2, comparable_set=frozenset({"a", "b"})),
        ResponseRecord("two", "cheap", '["c"]', 0, 0.3, comparable_set=frozenset({"c"})),
    ]
    strong = [
        ResponseRecord("one", "strong", '["a", "b"]', 0, 0.4, comparable_set=frozenset({"a", "b"})),
        ResponseRecord("two", "strong", '["c", "d"]', 0, 0.5, comparable_set=frozenset({"c", "d"})),
    ]
    cheap_metrics = compute_metrics(cheap, comparable=True)
    strong_metrics = compute_metrics(strong, comparable=True)
    assert cheap_metrics["coverage"] == 1.0
    assert strong_metrics["drops"] == 0
    agreement = tiered_agreement(cheap, strong)
    assert agreement["tiers"]["exact"] == 1
    assert agreement["tiers"]["partial"] == 1
    rows, assignments = build_blind_judge_queue(cheap, strong, seed=7)
    assert len(rows) == 4 and len(assignments) == 4
    assert all(set(row) == {"id", "response"} for row in rows)
    assert all("backend" not in row and "source" not in row for row in rows)
    scores = {identifier: 0.9 for identifier in assignments}
    defensibility = aggregate_defensibility(assignments, scores)
    result = explicit_verdict(
        defensibility["cheap"],
        defensibility["strong"],
        cheap_metrics["coverage"],
        strong_metrics["coverage"],
        cheap_metrics["drops"],
        strong_metrics["drops"],
    )
    assert result["verdict"] == "PARITY"
    assert parse_comparable_set('{"x": 1}', "json-object") == frozenset({"\"x\"=1"})
    assert parse_comparable_set("free text", "raw") is None
    print("SELFTEST_OK")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", type=Path, help="JSONL file of {id,prompt} rows")
    parser.add_argument("--cheap", default="kimi", help="cheap/free backend")
    parser.add_argument("--strong", default="codex", help="stronger reference backend")
    parser.add_argument("--parse-mode", choices=PARSE_MODES, default="raw")
    parser.add_argument("--dispatch", type=Path, help="dispatch.sh path")
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--judge-queue", type=Path)
    parser.add_argument("--judge-results", type=Path)
    parser.add_argument("--self-test", action="store_true")
    return parser


def run_evaluation(args: argparse.Namespace) -> int:
    if args.prompts is None:
        raise ValueError("--prompts is required unless --self-test is used")
    if not 0 <= args.margin:
        raise ValueError("--margin must be non-negative")
    prompts = _load_prompts(args.prompts)
    dispatch = args.dispatch or Path(__file__).with_name("dispatch.sh")
    if not dispatch.is_file():
        raise ValueError(f"dispatch script not found: {dispatch}")

    records: list[ResponseRecord] = []
    for prompt in prompts:
        for backend in (args.cheap, args.strong):
            print(
                f"progress id={prompt['id']} backend={backend} starting",
                file=sys.stderr,
                flush=True,
            )
            record = run_prompt(
                dispatch,
                backend,
                prompt["id"],
                prompt["prompt"],
                args.parse_mode,
                args.workdir,
                args.timeout,
            )
            records.append(record)
            print(
                f"progress id={prompt['id']} backend={backend} "
                f"rc={record.returncode} elapsed={record.elapsed_seconds:.2f}s",
                file=sys.stderr,
                flush=True,
            )

    cheap_records = [record for record in records if record.backend == args.cheap]
    strong_records = [record for record in records if record.backend == args.strong]
    comparable = args.parse_mode != "raw"
    cheap_metrics = compute_metrics(cheap_records, comparable)
    strong_metrics = compute_metrics(strong_records, comparable)
    agreement = tiered_agreement(cheap_records, strong_records)
    rows, assignments = build_blind_judge_queue(
        cheap_records, strong_records, seed=args.seed
    )
    queue_path = args.judge_queue or Path.cwd() / "executor-parity-judge-queue.jsonl"
    write_judge_queue(queue_path, rows)

    result: dict[str, Any] = {
        "cheap": cheap_metrics,
        "strong": strong_metrics,
        "agreement": agreement,
        "judge_queue": str(queue_path),
        "margin": args.margin,
    }
    if args.judge_results is None:
        result["verdict"] = "JUDGE_PENDING"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    scores = load_judge_scores(args.judge_results)
    missing = set(assignments) - set(scores)
    if missing:
        raise ValueError(f"judge scores missing {len(missing)} queue ids")
    defensibility = aggregate_defensibility(assignments, scores)
    if args.cheap not in defensibility or args.strong not in defensibility:
        raise ValueError("judge scores must cover both backends")
    result["verdict"] = explicit_verdict(
        defensibility[args.cheap],
        defensibility[args.strong],
        cheap_metrics["coverage"],
        strong_metrics["coverage"],
        cheap_metrics["drops"],
        strong_metrics["drops"],
        args.margin,
    )
    result["defensibility"] = defensibility
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        run_self_test()
        return 0
    try:
        return run_evaluation(args)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"executor-parity-eval: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
