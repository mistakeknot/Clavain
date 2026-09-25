"""Cache-aware burn ledger for selector burn accounting (mk-42j9.7 Task 3).

Reuses Interstat's per-request transcript parsers (`claude_attribution.parse_claude`,
`task_attribution.parse_codex`) so unsupported providers stay explicit missing
coverage rather than a silent zero, and reuses `scripts/burn-report.py`'s
`WEIGHTS` as the single source of pricing weights. See the plan's "Burn
ledger" section.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, Mapping, Sequence

_DEFAULT_INTERSTAT_ROOT = "/home/mk/projects/Sylveste/interverse/interstat"
_BURN_REPORT_PATH = Path(__file__).resolve().parents[1] / "burn-report.py"
_SYS_PATH_LOCK = threading.Lock()
_INTERSTAT_MODULE_NAMES = ("cost", "task_attribution", "claude_attribution")

_UNSUPPORTED_HOSTS = frozenset({"hermes", "kimi", "pi"})
_SUPPORTED_HOSTS = frozenset({"claude", "codex"})

# Maps a WEIGHTS field name (burn-report.py, Claude-native naming) to the
# normalized usage field name that both `parse_claude` and `parse_codex`
# produce (Interstat's common `normalize()` shape). Codex's normalized
# `input_tokens` is already fresh input (cache reads/writes subtracted); see
# `task_attribution.normalize`.
WEIGHTS_KEY_MAP: dict[str, str] = {
    "input_tokens": "input_tokens",
    "cache_creation_input_tokens": "cache_creation_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
    "output_tokens": "output_tokens",
}


class ParserUnavailable(Exception):
    """Interstat's parsers could not be loaded; the ledger is `status: unavailable`."""


def _load_burn_report_module():
    spec = importlib.util.spec_from_file_location("clavain_selector._burn_report", _BURN_REPORT_PATH)
    if spec is None or spec.loader is None:
        raise ParserUnavailable(f"could not load burn-report.py from {_BURN_REPORT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_weights() -> dict[str, float]:
    """Single-sourced pricing weights, imported from scripts/burn-report.py."""
    return dict(_load_burn_report_module().WEIGHTS)


def _weighted(usage: Mapping[str, Any] | None, weights: Mapping[str, float]) -> float:
    if not usage:
        return 0.0
    total = 0.0
    for weight_field, weight in weights.items():
        usage_field = WEIGHTS_KEY_MAP.get(weight_field, weight_field)
        value = usage.get(usage_field) or 0
        total += weight * value
    return total


def _interstat_root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CLAVAIN_INTERSTAT_ROOT") or _DEFAULT_INTERSTAT_ROOT)


def _module_matches_dir(name: str, scripts_dir: Path) -> bool:
    """True when sys.modules[name] is absent, or was already loaded from scripts_dir."""
    module = sys.modules.get(name)
    if module is None:
        return True
    file = getattr(module, "__file__", None)
    if not file:
        return False
    try:
        return Path(file).resolve().parent == scripts_dir.resolve()
    except OSError:
        return False


def _git_head(root_path: Path) -> str | None:
    # Outside any hook path: burn.ledger is a batch/eval-time call, never a
    # per-turn hook, so a subprocess here does not risk a hook deadline.
    try:
        result = subprocess.run(
            ["git", "-C", str(root_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def load_parsers(root: str | Path | None = None):
    """Import Interstat's `parse_claude` and `parse_codex`.

    Inserts Interstat's `scripts/` directory at `sys.path[0]` under a lock
    before importing, because its modules import siblings by bare name
    (`claude_attribution.py` does `from cost import ...`). First checks that
    no module named `cost`, `task_attribution` or `claude_attribution` is
    already loaded from a different path; such a collision is reported as
    `ParserUnavailable` rather than silently importing the wrong module.

    Returns `(parse_claude, parse_codex, commit_sha)`.
    """
    root_path = _interstat_root(root)
    scripts_dir = root_path / "scripts"
    if not scripts_dir.is_dir():
        raise ParserUnavailable(f"no Interstat scripts directory at {scripts_dir}")

    with _SYS_PATH_LOCK:
        collisions = [name for name in _INTERSTAT_MODULE_NAMES if not _module_matches_dir(name, scripts_dir)]
        if collisions:
            raise ParserUnavailable(
                f"module name collision with already-loaded module(s) {collisions}; "
                "refusing to import Interstat parsers under a foreign module of the same name"
            )
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        try:
            import claude_attribution  # noqa: PLC0415
            import task_attribution  # noqa: PLC0415
        except ImportError as exc:
            raise ParserUnavailable(f"failed to import Interstat parsers from {scripts_dir}: {exc}") from exc

    return claude_attribution.parse_claude, task_attribution.parse_codex, _git_head(root_path)


def _rescan_like_burn_report(paths: Sequence[Path], weights: Mapping[str, float]) -> dict[tuple, dict]:
    """Reproduce burn-report.py's `responses()` dedup rule directly on `paths`.

    Keyed by (message.id, requestId), later lines overwrite each field with
    the largest value seen (streaming writes the same key several times).
    Unlike burn-report.py's own `responses()`, this does not walk a directory
    tree or apply a time window: it scans exactly the given files, which is
    what a burn ledger over specific transcripts needs.
    """
    seen: dict[tuple, dict] = {}
    for path in paths:
        try:
            content = Path(path).read_text(errors="ignore")
        except OSError:
            continue
        for line in content.splitlines():
            if '"usage"' not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            usage, model = message.get("usage"), message.get("model")
            if not isinstance(usage, dict) or model == "<synthetic>":
                continue
            key = (message.get("id"), event.get("requestId"))
            if key not in seen:
                seen[key] = {"raw": dict.fromkeys(weights, 0), "event": event}
            merged = seen[key]["raw"]
            for field in weights:
                merged[field] = max(merged[field], usage.get(field) or 0)
    return seen


def _claude_row(record: dict, weights: Mapping[str, float]) -> dict:
    return {
        "provider": "claude",
        "session_id": record.get("session_id"),
        "thread_id": record.get("thread_id"),
        "turn_id": record.get("turn_id"),
        "response_id": record.get("response_id"),
        "request_id": record.get("request_id"),
        "model": record.get("model"),
        "timestamp": record.get("timestamp"),
        "usage": record.get("usage"),
        "weighted": _weighted(record.get("usage"), weights),
        "valid": bool(record.get("valid")),
    }


def _codex_row(record: dict, weights: Mapping[str, float]) -> dict:
    return {
        "provider": "codex",
        "session_id": record.get("session_id"),
        "thread_id": record.get("thread_id"),
        "turn_id": record.get("turn_id"),
        "response_id": record.get("response_id"),
        "request_id": None,
        "model": record.get("model"),
        "timestamp": record.get("timestamp"),
        "usage": record.get("usage"),
        "weighted": _weighted(record.get("usage"), weights),
        "valid": bool(record.get("valid")),
        "request_kind": record.get("request_kind", "inference"),
    }


def _claude_consistency(paths: Sequence[Path], requests: list[dict], weights: Mapping[str, float]) -> dict:
    """Reconcile the ledger's Claude total with an independent burn-report-style rescan."""
    rescanned = _rescan_like_burn_report(paths, weights)
    burn_report_weighted = sum(_weighted_raw_claude(entry["raw"], weights) for entry in rescanned.values())

    covered = {(r.get("response_id"), r.get("request_id")) for r in requests if r.get("valid")}
    ledger_weighted = sum(_weighted(r.get("usage"), weights) for r in requests if r.get("valid"))

    explained_by_cause: dict[str, list[float]] = collections.defaultdict(list)
    for (msg_id, request_id), entry in rescanned.items():
        if (msg_id, request_id) in covered:
            continue
        event = entry["event"]
        weighted_value = _weighted_raw_claude(entry["raw"], weights)
        if event.get("isApiErrorMessage"):
            cause = "isApiErrorMessage"
        elif not isinstance(msg_id, str) or not msg_id or not isinstance(request_id, str) or not request_id:
            cause = "missing_identity"
        else:
            cause = "unmatched"
        explained_by_cause[cause].append(weighted_value)

    explained = [
        {"cause": cause, "entries": len(values), "weighted": sum(values)}
        for cause, values in explained_by_cause.items()
        if cause != "unmatched"
    ]
    explained_total = sum(item["weighted"] for item in explained)
    delta = burn_report_weighted - ledger_weighted
    unexplained = delta - explained_total
    tolerance = 1e-6 * burn_report_weighted
    return {
        "burn_report_weighted": burn_report_weighted,
        "ledger_weighted": ledger_weighted,
        "delta": delta,
        "explained": explained,
        "unexplained": unexplained,
        "tolerance": tolerance,
        "reconciled": abs(unexplained) <= tolerance,
    }


def _weighted_raw_claude(raw: Mapping[str, Any], weights: Mapping[str, float]) -> float:
    # burn-report.py's raw fields already use the same names as WEIGHTS for
    # Claude, so no field-name mapping is needed here.
    return sum(weights[field] * (raw.get(field) or 0) for field in weights)


def _last_total_token_usage(paths: Sequence[Path]) -> dict[str, int] | None:
    last = None
    for path in paths:
        try:
            content = Path(path).read_text(errors="ignore")
        except OSError:
            continue
        for line in content.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") != "event_msg":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "token_count":
                continue
            info = payload.get("info")
            if isinstance(info, dict) and isinstance(info.get("total_token_usage"), dict):
                last = info["total_token_usage"]
    return last


def _codex_consistency(paths: Sequence[Path], requests: list[dict], issues: list[dict], task_attribution) -> dict:
    raw_fields = task_attribution.RAW_FIELDS
    non_compaction_sum = dict.fromkeys(raw_fields, 0)
    compaction_requests = 0
    for record in requests:
        if not record.get("valid"):
            continue
        if record.get("request_kind") == "compaction":
            compaction_requests += 1
            continue
        raw_usage = record.get("raw_usage") or {}
        for field in raw_fields:
            non_compaction_sum[field] += raw_usage.get(field, 0)

    final_cumulative = _last_total_token_usage(paths)
    matches = final_cumulative is not None and all(
        non_compaction_sum[field] == final_cumulative.get(field) for field in raw_fields
    )
    session_cumulative_mismatch = any(issue.get("code") == "session_cumulative_mismatch" for issue in issues)
    return {
        "final_cumulative": final_cumulative,
        "non_compaction_sum": non_compaction_sum,
        "compaction_requests": compaction_requests,
        "matches_final_cumulative_excluding_compaction": matches,
        "session_cumulative_mismatch": session_cumulative_mismatch,
    }


def _selector_overhead(selector_usage: Sequence[Mapping[str, Any]], weights: Mapping[str, float]) -> dict:
    totals = {"input_tokens": 0, "output_tokens": 0}
    for item in selector_usage:
        totals["input_tokens"] += int(item.get("input_tokens") or 0)
        totals["output_tokens"] += int(item.get("output_tokens") or 0)
    weighted_total = (
        weights.get("input_tokens", 1.0) * totals["input_tokens"]
        + weights.get("output_tokens", 5.0) * totals["output_tokens"]
    )
    return {"calls": len(selector_usage), "raw": totals, "weighted_total": weighted_total}


def ledger(
    paths: Sequence[str | Path],
    host: str,
    *,
    selector_usage: Sequence[Mapping[str, Any]] | None = None,
    interstat_root: str | Path | None = None,
) -> dict:
    """Per-request rows and weighted totals for one or more transcripts.

    `host` is `claude`, `codex`, or one of the currently unsupported hosts
    (`hermes`, `kimi`, `pi`), which return `status: unsupported` rather than
    a fabricated zero total. If Interstat is absent or a parser raises, the
    result is `status: unavailable`, never a numeric total.
    """
    if host in _UNSUPPORTED_HOSTS or host not in _SUPPORTED_HOSTS:
        return {"status": "unsupported", "host": host}

    resolved_paths = [Path(p) for p in paths]
    try:
        parse_claude, parse_codex, commit_sha = load_parsers(interstat_root)
    except ParserUnavailable as exc:
        return {"status": "unavailable", "host": host, "reason": str(exc)}

    weights = load_weights()

    if host == "claude":
        requests: list[dict] = []
        for path in resolved_paths:
            reqs, _turns, _issues = parse_claude(path)
            requests.extend(reqs)
        rows = [_claude_row(r, weights) for r in requests]
        consistency = _claude_consistency(resolved_paths, requests, weights)
    else:
        import task_attribution  # available: load_parsers already imported it

        requests = []
        all_issues: list[dict] = []
        for path in resolved_paths:
            reqs, _turns, issues = parse_codex(path)
            requests.extend(reqs)
            all_issues.extend(issues)
        rows = [_codex_row(r, weights) for r in requests]
        consistency = _codex_consistency(resolved_paths, requests, all_issues, task_attribution)

    weighted_total = sum(row["weighted"] for row in rows if row["valid"])
    result = {
        "status": "ok",
        "host": host,
        "interstat_commit": commit_sha,
        "rows": rows,
        "weighted_total": weighted_total,
        "consistency": consistency,
    }
    if selector_usage:
        result["selector_overhead"] = _selector_overhead(selector_usage, weights)
    return result


@dataclasses.dataclass(frozen=True)
class Row:
    """A convenience row shape for `invalidation_events`; ledger() rows are plain dicts."""

    ts: dt.datetime
    input: int
    cache_read: int
    cache_creation: int
    cache_creation_1h: bool = False


def invalidation_events(rows, *, ttl_s: int = 300, ttl_1h_s: int = 3600):
    """Per-thread cache invalidation/expiry/compaction events, in timestamp order.

    `rows` are duck-typed objects (or `Row` instances) with `.cache_read`,
    `.cache_creation`, `.input`, `.ts` and `.cache_creation_1h` attributes, as
    used by the plan's "Burn ledger" section.
    """
    events = []
    for prev, cur in zip(rows, rows[1:]):
        prev_prefix = prev.cache_read + prev.cache_creation + prev.input
        cur_context = cur.cache_read + cur.cache_creation + cur.input
        gap = (cur.ts - prev.ts).total_seconds()
        ttl = ttl_1h_s if prev.cache_creation_1h else ttl_s
        if cur_context < 0.8 * prev_prefix:
            events.append(("compaction_or_reset", cur, 0))
            continue
        invalidated = max(0, min(prev_prefix, cur_context) - cur.cache_read)
        if invalidated < max(1024, 0.05 * prev_prefix):
            continue
        kind = "expiry" if gap >= ttl else "invalidation"
        events.append((kind, cur, invalidated))
    return events
