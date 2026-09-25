"""Tests for scripts/clavain_selector/burn.py (mk-42j9.7 Task 3).

The two fixture-consistency tests (`test_claude_fixture_reconciles`,
`test_codex_fixture_reconciles`) exercise Interstat's real parsers against
synthetic, fully-fake-id transcripts; they do not read any real transcript.
"""

from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

import pytest
from selector_helpers import selector_socket_guard  # noqa: F401

from clavain_selector.burn import ParserUnavailable, Row, invalidation_events, ledger, load_parsers, load_weights

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "selector" / "burn"
CLAUDE_FIXTURE = FIXTURES / "claude_session.jsonl"
CODEX_FIXTURE = FIXTURES / "codex_rollout.jsonl"


def test_weights_single_sourced():
    weights = load_weights()
    assert weights == {
        "input_tokens": 1.0,
        "cache_creation_input_tokens": 1.25,
        "cache_read_input_tokens": 0.1,
        "output_tokens": 5.0,
    }


def test_interstat_missing_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAVAIN_INTERSTAT_ROOT", str(tmp_path / "does-not-exist"))
    result = ledger([CLAUDE_FIXTURE], "claude")
    assert result["status"] == "unavailable"
    assert "reason" in result
    assert "weighted_total" not in result  # no numeric totals on an unavailable ledger


def test_unsupported_hosts():
    for host in ("hermes", "kimi", "pi", "made-up-host"):
        result = ledger([CLAUDE_FIXTURE], host)
        assert result["status"] == "unsupported"
        assert result["host"] == host


def test_invalidation_metric():
    ts = dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc)

    def at(seconds, **kwargs):
        row = dict(ts=ts + dt.timedelta(seconds=seconds), input=0, cache_read=0, cache_creation=0, cache_creation_1h=False)
        row.update(kwargs)
        return Row(**row)

    # A stable, growing prefix (cache reads keep pace with growth) produces no events.
    rows = [at(0, cache_read=1_000, input=500), at(30, cache_read=1_400, input=600), at(60, cache_read=1_900, input=700)]
    assert invalidation_events(rows) == []

    # A cache miss: the same ~11,000-token prefix is resent, but as fresh input
    # instead of a cache read (cache_read drops to 0, input absorbs the rest).
    # Within 60s of a 300s default TTL, that is an invalidation with the exact
    # recovered (previously-cached, now-fresh) token count.
    rows = [at(0, cache_read=10_000, input=1_000), at(60, cache_read=0, input=11_000)]
    events = invalidation_events(rows)
    assert len(events) == 1
    kind, row, invalidated = events[0]
    assert kind == "invalidation"
    prev_prefix, cur_context = 11_000, 11_000
    assert invalidated == max(0, min(prev_prefix, cur_context) - row.cache_read)
    assert invalidated == 11_000

    # The same cache miss, but after the default 300s TTL has elapsed, is an expiry.
    rows = [at(0, cache_read=10_000, input=1_000), at(400, cache_read=0, input=11_000)]
    events = invalidation_events(rows)
    assert events[0][0] == "expiry"

    # Context shrinking below 0.8x the previous prefix (a much larger collapse
    # than a mere cache eviction) is a compaction/reset, not an invalidation.
    rows = [at(0, cache_read=10_000, input=1_000), at(10, cache_read=100, input=200)]
    events = invalidation_events(rows)
    assert events[0][0] == "compaction_or_reset"

    # A small cache-read drop under the noise floor produces no event.
    rows = [at(0, cache_read=10_000, input=1_000), at(10, cache_read=9_950, input=1_000)]
    assert invalidation_events(rows) == []

    # A 1h-eligible row uses the longer TTL: a 30-minute gap that would be an
    # expiry under the default 5m TTL is an invalidation once cache_creation_1h is set.
    rows = [at(0, cache_read=10_000, input=1_000, cache_creation_1h=True), at(1_800, cache_read=0, input=11_000)]
    events = invalidation_events(rows, ttl_1h_s=3600)
    assert events[0][0] == "invalidation"


def test_parsers_load_with_sys_path():
    try:
        parse_claude, parse_codex, commit_sha = load_parsers()
    except ParserUnavailable as exc:
        pytest.skip(f"Interstat unavailable: {exc}")
    assert callable(parse_claude)
    assert callable(parse_codex)
    assert commit_sha is None or isinstance(commit_sha, str)


def test_parsers_load_rejects_foreign_module_collision(monkeypatch):
    # A `cost` module already loaded from somewhere else must not be silently
    # shadowed by Interstat's same-named module: load_parsers must refuse.
    foreign = types.ModuleType("cost")
    foreign.__file__ = "/tmp/not-interstat/cost.py"
    monkeypatch.setitem(sys.modules, "cost", foreign)
    with pytest.raises(ParserUnavailable):
        load_parsers()


def test_claude_fixture_reconciles():
    result = ledger([CLAUDE_FIXTURE], "claude")
    if result["status"] == "unavailable":
        import pytest

        pytest.skip(f"Interstat unavailable: {result.get('reason')}")
    assert result["status"] == "ok"
    assert len(result["rows"]) == 2  # the isApiErrorMessage entry is dropped by parse_claude
    assert all(row["valid"] for row in result["rows"])

    consistency = result["consistency"]
    assert consistency["burn_report_weighted"] > consistency["ledger_weighted"]
    assert consistency["reconciled"] is True
    causes = {item["cause"] for item in consistency["explained"]}
    assert "isApiErrorMessage" in causes


def test_codex_fixture_reconciles():
    result = ledger([CODEX_FIXTURE], "codex")
    if result["status"] == "unavailable":
        import pytest

        pytest.skip(f"Interstat unavailable: {result.get('reason')}")
    assert result["status"] == "ok"
    assert len(result["rows"]) == 3
    assert all(row["valid"] for row in result["rows"])

    consistency = result["consistency"]
    assert consistency["compaction_requests"] == 0
    assert consistency["matches_final_cumulative_excluding_compaction"] is True
    assert consistency["session_cumulative_mismatch"] is False
    assert consistency["final_cumulative"]["total_tokens"] == 15650


def test_selector_overhead_separate():
    selector_usage = [{"input_tokens": 500, "output_tokens": 50}, {"input_tokens": 300, "output_tokens": 20}]
    result = ledger([CLAUDE_FIXTURE], "claude", selector_usage=selector_usage)
    if result["status"] == "unavailable":
        import pytest

        pytest.skip(f"Interstat unavailable: {result.get('reason')}")
    overhead = result["selector_overhead"]
    assert overhead["calls"] == 2
    assert overhead["raw"] == {"input_tokens": 800, "output_tokens": 70}
    # Selector overhead must not be folded into the host's own weighted_total.
    without_overhead = ledger([CLAUDE_FIXTURE], "claude")
    assert result["weighted_total"] == without_overhead["weighted_total"]
    assert overhead["weighted_total"] == 800 * 1.0 + 70 * 5.0
