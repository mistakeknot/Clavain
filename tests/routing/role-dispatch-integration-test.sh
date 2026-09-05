#!/usr/bin/env bash
# Real Intercore resolver + SQLite audit store, fake model backend. No paid calls.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
command -v ic >/dev/null
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/bin" "$TMP_ROOT/work"
cat > "$TMP_ROOT/bin/codex" <<'CODEX'
#!/usr/bin/env bash
if [[ "${1:-}" == --version ]]; then echo 'codex-cli 0.153.3'; exit 0; fi
echo 'VERDICT: CLEAN'
CODEX
chmod +x "$TMP_ROOT/bin/codex"
export PATH="$TMP_ROOT/bin:$PATH" CLAVAIN_CONTEXT_GATEWAY_MODE=off
(cd "$TMP_ROOT/work" && ic init >/dev/null)
CLAVAIN_RUN_ID=integration-run CLAVAIN_BEAD_ID=integration-bead DISPATCH_SESSION_ID=integration-parent bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" 'fixture only' >/dev/null
records="$(cd "$TMP_ROOT/work" && ic --json route list --limit=10)"
jq -e 'length == 2 and all(.[]; .dispatch_id != null and .session_id == "integration-parent")' <<< "$records" >/dev/null
jq -e 'all(.[]; .run_id == "integration-run" and .bead_id == "integration-bead" and (.context_json | fromjson | .run_id == "integration-run" and .bead_id == "integration-bead"))' <<< "$records" >/dev/null
jq -e '[.[] | .context_json | fromjson] | all(.[]; .resolved_profile.profile.model == "gpt-6-astra" and .resolved_profile.profile.model_identity == "gpt-6-astra" and .resolved_route.fallback_chain[0].profile.model == "gpt-5.6-sol") and ([.[].state] | sort == ["completed","started"]) and ([.[].attempt_id] | unique | length == 1)' <<< "$records" >/dev/null
fable="$(bash "$ROOT/scripts/dispatch.sh" --dry-run --role validation --producer-identity 'anthropic/claude-fable-5-1[1m]' -C "$TMP_ROOT/work" fixture 2>&1)"
[[ "$fable" == *'kimi-code/k3'* && "$fable" != *'--model fable'* ]]
astra="$(bash "$ROOT/scripts/dispatch.sh" --dry-run --via zaka --role validation --producer-identity codex/gpt-6-astra -C "$TMP_ROOT/work" fixture 2>&1)"
[[ "$astra" == *'--agent claude-code'* && "$astra" == *'--model claude-fable-5-1'* ]]
echo 'PASS: real Intercore identity, dispatch and immutable SQLite audit integration'
