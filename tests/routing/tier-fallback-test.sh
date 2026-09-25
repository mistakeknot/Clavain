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
echo '{"type":"task_complete","last_agent_message":"ok"}'
FAKE_CODEX

# Fake claude: records the invoking args (including --model) and succeeds.
cat > "$TMP_ROOT/bin/claude" <<'FAKE_CLAUDE'
#!/usr/bin/env bash
printf '%s\n' "$@" >> "$FAKE_CLAUDE_LOG"
cat > /dev/null
echo 'VERDICT: CLEAN'
FAKE_CLAUDE
chmod +x "$TMP_ROOT/bin/codex" "$TMP_ROOT/bin/claude"

export PATH="$TMP_ROOT/bin:$PATH"
export FAKE_CODEX_LOG="$TMP_ROOT/codex.log"
export FAKE_CLAUDE_LOG="$TMP_ROOT/claude.log"
export CLAVAIN_CONTEXT_GATEWAY_MODE=off
export CLAVAIN_BB_DIRECT_POOL=0
export CLAVAIN_429_BACKOFF_SECONDS=0
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
grep -A1 -x -- "--model" "$FAKE_CLAUDE_LOG" | grep -q -x "claude-opus-5" || fail "deep: quota_exhausted did not reach claude-opus-5, got: $(cat "$FAKE_CLAUDE_LOG")"

# deep-clavain: same terminus.
run_tier deep-clavain
[[ "$(cat "$FAKE_CODEX_LOG")" == "gpt-5.6-sol" ]] || fail "deep-clavain: expected one gpt-5.6-sol Codex attempt, got: $(cat "$FAKE_CODEX_LOG")"
grep -A1 -x -- "--model" "$FAKE_CLAUDE_LOG" | grep -q -x "claude-opus-5" || fail "deep-clavain: quota_exhausted did not reach claude-opus-5, got: $(cat "$FAKE_CLAUDE_LOG")"

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

echo "PASS: bare --tier dispatch reaches its declared Claude fallback on quota_exhausted"
