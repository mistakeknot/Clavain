#!/usr/bin/env bash
# Bare --tier (not --role) dispatch must not dead-end on a Codex tier when
# Codex is exhausted. `ic route dispatch --tier=<name>` only ever resolves the
# single named tier (verified: it never returns .fallback_chain, even for a
# tier that already declares `fallbacks:`), so this is a separate resolution
# surface from --role and needs its own coverage.
#
# mk ruling 2026-09-25: Codex exhaustion must never block development on any
# project. Covers fast / fast-clavain / deep / deep-clavain (config/routing.yaml
# dispatch.tiers), plus the config-level chains reached through --role:
# validation-sol and main-astra -> main-sol.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/bin" "$TMP_ROOT/work"
git -C "$TMP_ROOT/work" init -q
# dispatch.sh's _seat_snapshot runs `git diff HEAD`, which fails (exit 128)
# against an unborn HEAD; give the fixture repo an initial commit so the
# Claude fallback leg's seat-mutation check behaves like a real project dir.
git -C "$TMP_ROOT/work" -c user.email=test@example.com -c user.name=test commit -q --allow-empty -m init

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# Fake codex: FAKE_CODEX_MODE=quota_all reports usage_limit_exceeded for
# whatever model it is invoked with, on every attempt (mirrors
# tests/routing/role-dispatch-test.sh's fixture).
cat > "$TMP_ROOT/bin/codex" <<'FAKE_CODEX'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  echo "codex-cli 0.153.2"
  exit 0
fi
model=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  [[ "${args[$i]}" == "-m" ]] && model="${args[$((i+1))]:-}"
done
printf '%s\n' "$model" >> "$FAKE_CODEX_LOG"
if [[ "${FAKE_CODEX_MODE:-success}" == quota_all ]]; then
  echo '{"type":"task_complete","error":{"codex_error_info":"usage_limit_exceeded"}}'
  exit 0
fi
if [[ "${FAKE_CODEX_MODE:-success}" == rate429_all ]]; then
  # A pooled Codex lane whose own client already retried and gave up
  # (mk-nh6v): classifies rate_limited, distinct from quota_all above.
  echo '{"type":"error","message":"exceeded retry limit, last status: 429 Too Many Requests"}'
  echo '{"type":"turn.failed","error":{"message":"exceeded retry limit, last status: 429 Too Many Requests"}}'
  exit 1
fi
echo '{"type":"task_complete","last_agent_message":"ok"}'
FAKE_CODEX

# Fake claude: records the invoking args (including --model) and succeeds.
# FAKE_CLAUDE_WRITE=1 also writes a file into the cwd (WORKDIR), simulating
# a real Write-tool call, so B1's test can prove genuine write authority
# rather than just inspecting --allowedTools flags.
cat > "$TMP_ROOT/bin/claude" <<'FAKE_CLAUDE'
#!/usr/bin/env bash
printf '%s\n' "$@" >> "$FAKE_CLAUDE_LOG"
cat > /dev/null
if [[ "${FAKE_CLAUDE_WRITE:-0}" == 1 ]]; then
  echo "written by fake claude" > bihl-write-marker.txt
fi
echo 'VERDICT: CLEAN'
FAKE_CLAUDE
chmod +x "$TMP_ROOT/bin/codex" "$TMP_ROOT/bin/claude"

export PATH="$TMP_ROOT/bin:$PATH"
export FAKE_CODEX_LOG="$TMP_ROOT/codex.log"
export FAKE_CLAUDE_LOG="$TMP_ROOT/claude.log"
export CLAVAIN_CONTEXT_GATEWAY_MODE=off
export CLAVAIN_BB_DIRECT_POOL=0
export CLAVAIN_ROUTING_POLICY="$ROOT/config/routing.yaml"
(cd "$TMP_ROOT/work" && ic init >/dev/null 2>&1) || true

run_tier() {
  local tier="$1"
  : > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"
  # -o writes outside WORKDIR: dispatch.sh's Claude leg diffs the workdir
  # before/after (_seat_snapshot) to catch a seat editing files it shouldn't;
  # an -o path inside WORKDIR would trip that as a false "seat mutated".
  FAKE_CODEX_MODE=quota_all bash "$ROOT/scripts/dispatch.sh" --tier "$tier" \
    -C "$TMP_ROOT/work" -o "$TMP_ROOT/answer.md" "hi" >/dev/null 2>&1
}

# fast: routine-execution's tier alias. Codex-exhausted must reach the same
# Sonnet capacity seat routine-sol already falls back to (routine-sonnet).
run_tier fast
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "fast: expected one gpt-5.6-sol Codex attempt before fallback, got: $(cat "$FAKE_CODEX_LOG")"
grep -A1 -x -- "--model" "$FAKE_CLAUDE_LOG" | grep -q -x "claude-sonnet-5" || fail "fast: quota_exhausted did not reach claude-sonnet-5, got: $(cat "$FAKE_CLAUDE_LOG")"

# fast-clavain: scout's tier alias. Falls back to scout-sonnet.
run_tier fast-clavain
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "fast-clavain: expected one gpt-5.6-sol Codex attempt, got: $(cat "$FAKE_CODEX_LOG")"
grep -A1 -x -- "--model" "$FAKE_CLAUDE_LOG" | grep -q -x "claude-sonnet-5" || fail "fast-clavain: quota_exhausted did not reach claude-sonnet-5, got: $(cat "$FAKE_CLAUDE_LOG")"

# deep: deep-execution's tier alias. Falls back to deep-opus (Opus, matching
# deep-astra -> deep-sol -> deep-opus's own terminus).
run_tier deep
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "deep: expected one gpt-5.6-sol Codex attempt, got: $(cat "$FAKE_CODEX_LOG")"
grep -A1 -x -- "--model" "$FAKE_CLAUDE_LOG" | grep -q -x "claude-opus-5-5" || fail "deep: quota_exhausted did not reach claude-opus-5-5, got: $(cat "$FAKE_CLAUDE_LOG")"

# deep-clavain: same terminus.
run_tier deep-clavain
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "deep-clavain: expected one gpt-5.6-sol Codex attempt, got: $(cat "$FAKE_CODEX_LOG")"
grep -A1 -x -- "--model" "$FAKE_CLAUDE_LOG" | grep -q -x "claude-opus-5-5" || fail "deep-clavain: quota_exhausted did not reach claude-opus-5-5, got: $(cat "$FAKE_CLAUDE_LOG")"

# A healthy Codex lane keeps using the primary tier model unchanged (Claude
# fallbacks go last, so nothing changes while Codex is reachable).
: > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"
bash "$ROOT/scripts/dispatch.sh" --tier fast -C "$TMP_ROOT/work" -o "$TMP_ROOT/answer2.md" "hi" >/dev/null 2>&1
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "healthy fast tier did not use gpt-5.6-sol"
[[ ! -s "$FAKE_CLAUDE_LOG" ]] || fail "healthy Codex lane unexpectedly reached Claude"

# tier-fallback-chain.py: unknown tier fails loudly rather than resolving nothing.
if python3 "$ROOT/scripts/tier-fallback-chain.py" --policy "$ROOT/config/routing.yaml" --tier does-not-exist >/dev/null 2>&1; then
  fail "unknown tier silently resolved"
fi

# An exhausted-retries 429 (rate_limited) walks the tier chain exactly like
# quota_exhausted (mk ruling 2026-09-25, mk-nh6v): one attempt on the primary
# Codex model, one account-pool retry gets skipped (CLAVAIN_BB_DIRECT_POOL=0),
# then the walk reaches the same Sonnet capacity seat as the quota case.
run_tier_rate429() {
  local tier="$1"
  : > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"
  FAKE_CODEX_MODE=rate429_all bash "$ROOT/scripts/dispatch.sh" --tier "$tier" \
    -C "$TMP_ROOT/work" -o "$TMP_ROOT/answer-429.md" "hi" >/dev/null 2>&1
}
run_tier_rate429 fast
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "fast/429: expected one gpt-5.6-sol Codex attempt before fallback, got: $(cat "$FAKE_CODEX_LOG")"
grep -A1 -x -- "--model" "$FAKE_CLAUDE_LOG" | grep -q -x "claude-sonnet-5" || fail "fast/429: rate_limited did not reach claude-sonnet-5, got: $(cat "$FAKE_CLAUDE_LOG")"

echo "PASS: bare --tier dispatch reaches its declared Claude fallback on quota_exhausted"

# N1: the tier walk must apply the same usage-budget guards
# _dispatch_role_profile does — CLAVAIN_REQUIRE_USAGE skips a candidate whose
# backend cannot report usage, and stops retrying entirely after the first
# started (budgeted) candidate fails, rather than silently overspending by
# trying further fallbacks. validation-kimi's own chain is
# kimi(primary) -> validation-sol(codex) -> validation-opus(claude) ->
# validation-sonnet(claude): under CLAVAIN_REQUIRE_USAGE=1, kimi is skipped
# (cannot report usage) and codex is tried once, quota-exhausts, and the walk
# must stop there — never reaching claude at all.
: > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"
CLAVAIN_REQUIRE_USAGE=1 FAKE_CODEX_MODE=quota_all CLAVAIN_REVIEW_EVENTS="$TMP_ROOT/events.jsonl" \
  bash "$ROOT/scripts/dispatch.sh" --tier validation-kimi -C "$TMP_ROOT/work" -o "$TMP_ROOT/answer3.md" "hi" >/dev/null 2>&1 || true
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "N1: expected exactly one codex attempt (validation-sol), got: $(cat "$FAKE_CODEX_LOG")"
[[ ! -s "$FAKE_CLAUDE_LOG" ]] || fail "N1: CLAVAIN_REQUIRE_USAGE must stop after the first started candidate's failure, but Claude was reached: $(cat "$FAKE_CLAUDE_LOG")"

# B1: a tier-resolved Claude candidate must get the same write authority an
# execution role gets when the sandbox is not read-only. Real caller:
# interserve split-mode "Implement agent" (--tier deep -s workspace-write).
# Before the fix, _dispatch_tier_profile built `--to claude --model ...` with
# no --role, so ROLE_RESOLVED stayed false, the CLAUDE_UNSAFE auto-enable at
# dispatch.sh:1771-1772 never fired, and the fake claude's write below would
# trip the read-only seat's mutation check and fail the dispatch.
run_tier_write() {
  local tier="$1" sandbox="$2" out="$3"
  : > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"
  rm -f "$TMP_ROOT/work/bihl-write-marker.txt"
  set +e
  FAKE_CODEX_MODE=quota_all FAKE_CLAUDE_WRITE=1 bash "$ROOT/scripts/dispatch.sh" --tier "$tier" \
    -s "$sandbox" -C "$TMP_ROOT/work" -o "$out" "hi" >/dev/null 2>&1
  local rc=$?
  set -e
  return "$rc"
}

# deep + workspace-write (the default sandbox): the Claude fallback must be
# allowed to actually write, and must not be flagged as a mutated seat.
rc=0; run_tier_write deep workspace-write "$TMP_ROOT/answer-write.md" || rc=$?
[[ "$rc" == 0 ]] || fail "B1: deep + workspace-write expected success, got exit $rc"
[[ -f "$TMP_ROOT/work/bihl-write-marker.txt" ]] || fail "B1: deep + workspace-write — fake claude's write did not survive"
grep -q "seat mutated" "$TMP_ROOT/answer-write.md.verdict" 2>/dev/null && fail "B1: deep + workspace-write — write was wrongly treated as seat mutation"

# An explicit read-only sandbox still wins even for an execution tier
# (dispatch.sh:1771's own rule: "an explicit read-only sandbox wins").
rc=0; run_tier_write deep read-only "$TMP_ROOT/answer-ro.md" || rc=$?
[[ "$rc" != 0 ]] || fail "B1: deep + read-only expected the write to be refused, got exit 0"
grep -q "seat mutated" "$TMP_ROOT/answer-ro.md.verdict" || fail "B1: deep + read-only expected a seat-mutated error verdict, got: $(cat "$TMP_ROOT/answer-ro.md.verdict" 2>/dev/null)"

# validation-sol's role is 'validation', not an execution role, so the
# mutation prohibition applies regardless of sandbox — write authority must
# stay scoped to execution roles only.
rc=0; run_tier_write validation-sol workspace-write "$TMP_ROOT/answer-val.md" || rc=$?
[[ "$rc" != 0 ]] || fail "B1: validation-sol + workspace-write expected the write to be refused, got exit 0"
grep -q "seat mutated" "$TMP_ROOT/answer-val.md.verdict" || fail "B1: validation-sol + workspace-write expected a seat-mutated error verdict, got: $(cat "$TMP_ROOT/answer-val.md.verdict" 2>/dev/null)"

echo "PASS: tier-resolved Claude candidates get execution write authority only for execution-role tiers, never for validation"

# N3a: policy discovery must still find routing.yaml via CLAVAIN_ROUTING_CONFIG
# even when CLAVAIN_ROUTING_POLICY (the tier walk's own narrower default) is
# unset — the same discovery _routing_find_config() (lib-routing.sh) gives
# every other routing consumer. Point CLAVAIN_ROUTING_CONFIG at a *distinct*
# copy of routing.yaml with tier fast's model swapped, so a pass here can only
# mean CLAVAIN_ROUTING_CONFIG was actually read (the script-relative default
# would resolve the real repo file, with the real model, and mask this).
DECOY_POLICY="$TMP_ROOT/decoy-routing.yaml"
sed 's/^\(    fast:\n\)/\1/' "$ROOT/config/routing.yaml" > "$DECOY_POLICY" 2>/dev/null || cp "$ROOT/config/routing.yaml" "$DECOY_POLICY"
python3 - "$ROOT/config/routing.yaml" "$DECOY_POLICY" <<'PY'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
text = text.replace("    fast:\n      role: routine-execution\n      backend: codex\n      model: gpt-5.6-sol\n",
                     "    fast:\n      role: routine-execution\n      backend: codex\n      model: bihl-decoy-model\n", 1)
open(dst, "w", encoding="utf-8").write(text)
PY
grep -q "bihl-decoy-model" "$DECOY_POLICY" || fail "N3: test setup — decoy routing.yaml substitution did not take"
: > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"
(
  unset CLAVAIN_ROUTING_POLICY
  export CLAVAIN_ROUTING_CONFIG="$DECOY_POLICY"
  FAKE_CODEX_MODE=quota_all bash "$ROOT/scripts/dispatch.sh" --tier fast -C "$TMP_ROOT/work" -o "$TMP_ROOT/answer4.md" "hi" >/dev/null 2>&1
)
[[ "$(cat "$FAKE_CODEX_LOG")" == "bihl-decoy-model" ]] || fail "N3: CLAVAIN_ROUTING_CONFIG discovery was not honored — expected the decoy model, got: $(cat "$FAKE_CODEX_LOG")"

# N3b: pyyaml unavailable must degrade (warn, single-candidate legacy
# resolution) instead of failing dispatch outright. Shim python3 to fail
# tier-fallback-chain.py's `import yaml` (exit 3) while still running real
# python3 for everything else dispatch.sh needs.
REAL_PYTHON3="$(command -v python3)"
mkdir -p "$TMP_ROOT/bin-noyaml"
cat > "$TMP_ROOT/bin-noyaml/python3" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do
  if [[ "\$a" == *tier-fallback-chain.py ]]; then
    echo "tier-fallback-chain: pyyaml is required" >&2
    exit 3
  fi
done
exec "$REAL_PYTHON3" "\$@"
EOF
chmod +x "$TMP_ROOT/bin-noyaml/python3"
: > "$FAKE_CODEX_LOG"; : > "$FAKE_CLAUDE_LOG"
PATH="$TMP_ROOT/bin-noyaml:$PATH" bash "$ROOT/scripts/dispatch.sh" --tier fast -C "$TMP_ROOT/work" -o "$TMP_ROOT/answer5.md" "hi" >/dev/null 2>&1
rc=$?
[[ "$rc" == 0 ]] || fail "N3: pyyaml-missing degradation expected dispatch to still succeed via the legacy resolver, got exit $rc"
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "N3: pyyaml-missing degradation expected the legacy resolver to still reach gpt-5.6-sol, got: $(cat "$FAKE_CODEX_LOG")"

echo "PASS: tier resolution restores CLAVAIN_ROUTING_CONFIG discovery and degrades gracefully without pyyaml"
