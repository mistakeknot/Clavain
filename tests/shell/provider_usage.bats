#!/usr/bin/env bats
# provider_usage.py turns provider evidence into receipt usage fields and says
# how complete they are. Transports without evidence are reported unavailable.

setup() {
    ROOT="$BATS_TEST_DIRNAME/../.."
    F="$ROOT/tests/fixtures/provider-usage"
    U() { python3 -I "$ROOT/scripts/provider_usage.py" "$@"; }
}

@test "codex multi-turn sums every category and is complete" {
    r="$(U --backend codex --events "$F/codex-complete.jsonl")"
    [ "$(jq -r .usage_status <<< "$r")" = complete ]
    [ "$(jq -r .usage_basis <<< "$r")" = codex-input-includes-cached ]
    [ "$(jq -r .tokens_in <<< "$r")" = 1500 ]
    [ "$(jq -r .tokens_cached_in <<< "$r")" = 1200 ]
    [ "$(jq -r .tokens_out <<< "$r")" = 70 ]
    [ "$(jq -r .tokens_reasoning_out <<< "$r")" = 10 ]
    [ "$(jq -r .tokens_cache_write_in <<< "$r")" = 0 ]
}

@test "codex absent cache keys stay null" {
    printf '%s\n' '{"type":"turn.started"}' '{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":1}}' > "$BATS_TMPDIR/e.jsonl"
    r="$(U --backend codex --events "$BATS_TMPDIR/e.jsonl")"
    [ "$(jq -r .tokens_cached_in <<< "$r")" = null ]
}

@test "codex killed mid-turn with a truncated line is partial" {
    r="$(U --backend codex --events "$F/codex-killed.jsonl" --exit-code 143)"
    [ "$(jq -r .usage_status <<< "$r")" = partial ]
    [ "$(jq -r .tokens_in <<< "$r")" = 1000 ]
}

@test "codex killed between turns (nonzero exit) is partial" {
    r="$(U --backend codex --events "$F/codex-complete.jsonl" --exit-code 143)"
    [ "$(jq -r .usage_status <<< "$r")" = partial ]
}

@test "codex with no completed turn is unavailable" {
    : > "$BATS_TMPDIR/empty.jsonl"
    r="$(U --backend codex --events "$BATS_TMPDIR/empty.jsonl" --exit-code 143)"
    [ "$(jq -r .usage_status <<< "$r")" = unavailable ]
}

@test "claude ledger keeps cache categories separate from input" {
    r="$(U --backend claude --ledger "$F/claude-ledger.jsonl")"
    [ "$(jq -r .usage_status <<< "$r")" = complete ]
    [ "$(jq -r .usage_basis <<< "$r")" = claude-input-excludes-cache ]
    [ "$(jq -r .tokens_in <<< "$r")" = 10 ]
    [ "$(jq -r .tokens_cached_in <<< "$r")" = 30 ]
    [ "$(jq -r .tokens_cache_write_in <<< "$r")" = 20 ]
}

@test "claude non-terminal ledger is partial" {
    r="$(U --backend claude --ledger "$F/claude-ledger-partial.jsonl")"
    [ "$(jq -r .usage_status <<< "$r")" = partial ]
}

@test "claude stream-json result is the fallback source" {
    r="$(U --backend claude --events "$F/claude-stream.jsonl")"
    [ "$(jq -r .usage_status <<< "$r")" = complete ]
    [ "$(jq -r .tokens_cached_in <<< "$r")" = 30 ]
}

@test "BB, Zaka and unknown transports are unavailable, not guessed" {
    for b in bb zaka kimi ""; do
        r="$(U --backend "$b" --events "$F/codex-complete.jsonl")"
        [ "$(jq -r .usage_status <<< "$r")" = unavailable ]
        [ "$(jq -r .tokens_in <<< "$r")" = null ]
    done
}

@test "report counts only complete rows and never goes negative" {
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    {
      jq -cn --arg t "$now" '{kind:"dispatch-run-receipt",role:"a",started_at:$t,ended_at:$t,usage_status:"complete",usage_basis:"codex-input-includes-cached",tokens_in:100,tokens_cached_in:80,tokens_out:5}'
      jq -cn --arg t "$now" '{kind:"dispatch-run-receipt",role:"a",started_at:$t,ended_at:$t,usage_status:"partial",tokens_in:999}'
      jq -cn --arg t "$now" '{kind:"dispatch-run-receipt",role:"a",started_at:$t,ended_at:$t,tokens_in:50}'
      jq -cn --arg t "$now" '{kind:"dispatch-run-receipt",role:"b",started_at:$t,ended_at:$t,usage_status:"complete",usage_basis:"claude-input-excludes-cache",tokens_in:10,tokens_cached_in:30}'
    } > "$BATS_TMPDIR/r.jsonl"
    r="$(python3 -I "$ROOT/scripts/receipt-token-report.py" --file "$BATS_TMPDIR/r.jsonl" --json)"
    [ "$(jq '.groups|length' <<< "$r")" = 2 ]
    [ "$(jq '.groups[]|select(.role=="a")|.uncached_in' <<< "$r")" = 20 ]
    [ "$(jq '.groups[]|select(.role=="b")|.uncached_in' <<< "$r")" = 10 ]
    [ "$(jq '.excluded.partial' <<< "$r")" = 1 ]
    [ "$(jq '.excluded["pre-change"]' <<< "$r")" = 1 ]
}
