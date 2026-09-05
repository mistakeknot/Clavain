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
while (( $# )); do
  if [[ "$1" == -o ]]; then
    [[ "${FAKE_CODEX_NO_OUTPUT:-0}" == 1 ]] || printf '%s\n' 'VERDICT: CLEAN' > "$2"
    break
  fi
  shift
done
echo 'VERDICT: CLEAN'
CODEX
chmod +x "$TMP_ROOT/bin/codex"
export PATH="$TMP_ROOT/bin:$PATH" CLAVAIN_CONTEXT_GATEWAY_MODE=off
(cd "$TMP_ROOT/work" && ic init >/dev/null)
# Reusing a report path must not attach a previous attempt's verdict at start.
printf '%s\n' 'STALE PRIOR ATTEMPT' > "$TMP_ROOT/result.md.verdict"
CLAVAIN_RUN_ID=integration-run CLAVAIN_BEAD_ID=integration-bead DISPATCH_SESSION_ID=integration-parent bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" -o "$TMP_ROOT/result.md" 'fixture only' >/dev/null
records="$(cd "$TMP_ROOT/work" && ic --json route list --limit=10)"
jq -e 'length == 2 and all(.[]; .dispatch_id != null and .session_id == "integration-parent")' <<< "$records" >/dev/null
jq -e 'all(.[]; .run_id == "integration-run" and .bead_id == "integration-bead" and (.context_json | fromjson | .run_id == "integration-run" and .bead_id == "integration-bead"))' <<< "$records" >/dev/null
jq -e '[.[] | .context_json | fromjson] | all(.[]; .resolved_profile.profile.model == "gpt-6-astra" and .resolved_profile.profile.model_identity == "gpt-6-astra" and .resolved_route.fallback_chain[0].profile.model == "gpt-5.6-sol") and ([.[].state] | sort == ["completed","started"]) and ([.[].attempt_id] | unique | length == 1)' <<< "$records" >/dev/null
jq -e '[.[] | .context_json | fromjson | select(.state == "started")] | length == 1 and all(.[]; .result.verdict == "")' <<< "$records" >/dev/null || { echo 'FAIL: started record inherited a prior verdict' >&2; exit 1; }
jq -e '[.[] | .context_json | fromjson | select(.state == "completed")] | length == 1 and all(.[]; .result.verdict | contains("STATUS: pass"))' <<< "$records" >/dev/null
# A later successful process that fails to write its report must not inherit
# either the old output text or its synthesized pass verdict.
FAKE_CODEX_NO_OUTPUT=1 bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" -o "$TMP_ROOT/result.md" 'no output fixture' >/dev/null
latest="$(cd "$TMP_ROOT/work" && ic --json route list --limit=20 | jq 'sort_by(.id) | reverse | .[:2]')"
jq -e '[.[] | .context_json | fromjson | select(.state == "completed")] | length == 1 and all(.[]; .result.verdict | contains("STATUS: warn"))' <<< "$latest" >/dev/null || { echo 'FAIL: terminal record inherited a prior pass verdict' >&2; exit 1; }
# An unwriteable report target fails before execution and cannot attach an old
# sidecar even though the failure itself is a terminal lifecycle state.
mkdir "$TMP_ROOT/report-directory"
printf '%s\n' 'STALE PRIOR ATTEMPT' > "$TMP_ROOT/report-directory.verdict"
if bash "$ROOT/scripts/dispatch.sh" --role deep-execution -C "$TMP_ROOT/work" -o "$TMP_ROOT/report-directory" 'bad output fixture' >/dev/null 2>&1; then
  echo 'FAIL: unwriteable report target accepted' >&2; exit 1
fi
latest="$(cd "$TMP_ROOT/work" && ic --json route list --limit=20 | jq 'sort_by(.id) | reverse | .[:2]')"
jq -e '[.[] | .context_json | fromjson | select(.state == "failed")] | length == 1 and all(.[]; .result.verdict == "" and .result.failure_class == "terminal_configuration")' <<< "$latest" >/dev/null
fable="$(bash "$ROOT/scripts/dispatch.sh" --dry-run --role validation --producer-identity 'anthropic/claude-fable-5-1[1m]' -C "$TMP_ROOT/work" fixture 2>&1)"
[[ "$fable" == *'kimi-code/k3'* && "$fable" != *'--model fable'* ]]
astra="$(bash "$ROOT/scripts/dispatch.sh" --dry-run --via zaka --role validation --producer-identity codex/gpt-6-astra -C "$TMP_ROOT/work" fixture 2>&1)"
[[ "$astra" == *'--agent claude-code'* && "$astra" == *'--model claude-fable-5-1'* ]]
echo 'PASS: real Intercore identity, dispatch and immutable SQLite audit integration'
