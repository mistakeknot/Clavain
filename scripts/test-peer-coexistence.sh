#!/usr/bin/env bash
# test-peer-coexistence.sh — acceptance tests for sylveste-4ct0 (A scope)
# Covers F1-F6. Written once in task-1; not modified by other tasks.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RIG="$SCRIPT_DIR/../agent-rig.json"
fail() { echo "FAIL: $1" >&2; exit 1; }
pass() { echo "PASS: $1"; }

# ---- F1: agent-rig.json reclassification ----
jq -e '.plugins.hard_conflicts | type == "array"' "$RIG" >/dev/null || fail "F1.1 hard_conflicts missing"
pass "F1.1 hard_conflicts array exists"

jq -e '.plugins.peers | type == "array"' "$RIG" >/dev/null || fail "F1.2 peers missing"
pass "F1.2 peers array exists"

jq -e '.plugins.conflicts == null' "$RIG" >/dev/null || fail "F1.3 legacy conflicts still present"
pass "F1.3 legacy conflicts removed"

jq -e '.plugins.peers[]? | select(.source == "superpowers@superpowers-marketplace")' "$RIG" >/dev/null || fail "F1.4 superpowers should be in peers"
pass "F1.4 superpowers in peers"

jq -e '.plugins.peers | all(.bridge_skill != null)' "$RIG" >/dev/null || fail "F1.5 peer missing bridge_skill"
pass "F1.5 each peer has bridge_skill"

# F1.6: verify-config.sh updated to read new arrays (no false PASS via empty conflicts)
grep -q "hard_conflicts" "$SCRIPT_DIR/verify-config.sh" || fail "F1.6 verify-config.sh still references legacy conflicts only"
pass "F1.6 verify-config.sh updated"

# ---- F2: modpack-install.sh process_peers() ----
DRYRUN=$(bash "$SCRIPT_DIR/modpack-install.sh" --dry-run --quiet 2>/dev/null) || fail "F2.0 modpack-install --dry-run failed"
echo "$DRYRUN" | jq -e '.peers_detected | type == "array"' >/dev/null || fail "F2.1 peers_detected missing"
pass "F2.1 peers_detected key present"

echo "$DRYRUN" | jq -e '.peers_active | type == "array"' >/dev/null || fail "F2.2 peers_active missing"
pass "F2.2 peers_active key present"

peer_in_disable=$(echo "$DRYRUN" | jq '[.would_disable[]? | select(. == "superpowers@superpowers-marketplace" or . == "compound-engineering@every-marketplace")] | length')
[[ "$peer_in_disable" == "0" ]] || fail "F2.3 peer found in would_disable: $peer_in_disable"
pass "F2.3 no peers in would_disable"

bash "$SCRIPT_DIR/modpack-install.sh" --dry-run --quiet --category=hard_conflicts >/dev/null || fail "F2.4 hard_conflicts category not accepted"
pass "F2.4 hard_conflicts category accepted"

bash "$SCRIPT_DIR/modpack-install.sh" --dry-run --quiet --category=peers >/dev/null || fail "F2.5 peers category not accepted"
pass "F2.5 peers category accepted"

if bash "$SCRIPT_DIR/modpack-install.sh" --dry-run --quiet --category=conflicts 2>/dev/null; then
    fail "F2.6 legacy conflicts category should be rejected"
fi
pass "F2.6 legacy conflicts category rejected"

# ---- F3: bridge skills exist ----
[[ -f "$SCRIPT_DIR/../skills/interop-with-superpowers/SKILL.md" ]] || fail "F3.1 interop-with-superpowers/SKILL.md missing"
pass "F3.1 interop-with-superpowers exists"

[[ -f "$SCRIPT_DIR/../skills/interop-with-gsd/SKILL.md" ]] || fail "F3.2 interop-with-gsd/SKILL.md missing"
pass "F3.2 interop-with-gsd exists"

# ---- F4: /clavain:peers viewer ----
[[ -f "$SCRIPT_DIR/../commands/peers.md" ]] || fail "F4.1 peers.md missing"
head -10 "$SCRIPT_DIR/../commands/peers.md" | grep -q "^name:" || fail "F4.2 peers.md missing name frontmatter"
pass "F4.1 peers.md exists with frontmatter"
grep -q "[Rr]ead-only" "$SCRIPT_DIR/../commands/peers.md" || fail "F4.3 peers.md missing read-only assertion"
pass "F4.3 peers.md asserts read-only"

# ---- F5: AGENTS.md beads-softening (bonus, soft-skip if not landed) ----
AGENTS_MD="$SCRIPT_DIR/../../../AGENTS.md"
if grep -q "is the canonical tracker for Sylveste-internal work" "$AGENTS_MD" 2>/dev/null; then
    pass "F5.1 AGENTS.md softened (bonus)"
else
    echo "SKIP: F5.1 AGENTS.md softening not applied (bonus, optional)"
fi

# ---- F6: peer-telemetry hook ----
[[ -x "$SCRIPT_DIR/../hooks/peer-telemetry.sh" ]] || fail "F6.1 peer-telemetry.sh missing/not executable"
pass "F6.1 peer-telemetry.sh exists"

TMPLOG=$(mktemp); rm -f "$TMPLOG"
CLAVAIN_PEER_TELEMETRY_FILE="$TMPLOG" bash "$SCRIPT_DIR/../hooks/peer-telemetry.sh" >/dev/null 2>&1
[[ -s "$TMPLOG" ]] || fail "F6.2 telemetry hook produced no output"
jq -e '. | type == "object"' "$TMPLOG" >/dev/null || fail "F6.2 telemetry not valid JSON"
pass "F6.2 hook emits valid JSONL"

TMPLOG2=$(mktemp); rm -f "$TMPLOG2"
CLAVAIN_PEER_TELEMETRY=0 CLAVAIN_PEER_TELEMETRY_FILE="$TMPLOG2" bash "$SCRIPT_DIR/../hooks/peer-telemetry.sh" >/dev/null 2>&1
[[ ! -s "$TMPLOG2" ]] || fail "F6.3 opt-out did not suppress telemetry"
pass "F6.3 opt-out env var works"
rm -f "$TMPLOG"

# F6.4: hook is registered in hooks.json (not plugin.json)
HOOKS_JSON="$SCRIPT_DIR/../hooks/hooks.json"
[[ -f "$HOOKS_JSON" ]] || fail "F6.4 hooks.json missing"
jq -e '.hooks.SessionStart | map(.hooks[]?.command) | flatten | any(. | contains("peer-telemetry.sh"))' "$HOOKS_JSON" >/dev/null || fail "F6.4 peer-telemetry not registered in hooks.json SessionStart"
pass "F6.4 peer-telemetry registered in hooks.json"

echo
echo "=== ALL ACCEPTANCE TESTS PASSED ==="
