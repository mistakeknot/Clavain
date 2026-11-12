#!/usr/bin/env bats
setup() {
    unset CLAVAIN_ROUTING_POLICY CLAVAIN_SELECTED_ROOT CLAVAIN_POLICY_PROFILE
    unset ANTHROPIC_AUTH_TOKEN CODEX_POOL_AUTH_TOKEN BB_ACCOUNT_POOL_PARENT_TOKEN CLAUDE_CODE_MESSAGING_TOKEN
    ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    T="$(mktemp -d)"
    export T REAL_IC="$(command -v ic)"
    mkdir -p "$T/bin" "$T/repo"
    git -C "$T/repo" init -q
    git -C "$T/repo" -c user.name=test -c user.email=test@example.com commit -qm base --allow-empty
    printf '{"reasons":["difficult-verification"],"scope":"mk-d0h1j.1","rationale":"experiment fixture"}\n' > "$T/ctx"
    chmod 600 "$T/ctx"
    printf 'fixture prompt\n' > "$T/prompt"
    cat > "$T/bin/ic" <<'FAKE'
#!/usr/bin/env bash
if [[ "$*" != *'route dispatch'* ]]; then exit 0; fi
if [[ "${FAKE_ROUTE:-}" == fixture ]]; then cat "$T/fixture-route"; exit; fi
args=("$@")
raw_sol=false
for ((i=0; i<${#args[@]}; i++)); do
  if [[ "${args[$i]}" == --producer-identity=sol ]]; then args[$i]=--producer-identity=gpt-6.1-sol; raw_sol=true; fi
done
"$REAL_IC" "${args[@]}" > "$T/route.tmp" || exit $?
if [[ "$raw_sol" == true ]]; then
  jq '.producer_identity="sol"' "$T/route.tmp" > "$T/normalized"
  cp "$T/normalized" "$T/route.tmp"
fi
cp "$T/route.tmp" "$T/last-route"
case "${FAKE_ROUTE:-}" in
 high) jq '.profile.reasoning_effort="high"' "$T/route.tmp" ;;
 model) jq '.profile.model="other"' "$T/route.tmp" ;;
 exemption) jq 'del(.effort_floors_exempted)' "$T/route.tmp" ;;
 two) jq '.fallback_chain=[{profile_ref:"other",profile:.profile}]' "$T/route.tmp" ;;
 producer) jq '.producer_identity="other"' "$T/route.tmp" ;;
 unknown) jq '.producer_model="mystery-model-1"' "$T/route.tmp" ;;
 empty) jq '.producer_model=""' "$T/route.tmp" ;;
 missing) jq 'del(.producer_model)' "$T/route.tmp" ;;
 *) cat "$T/route.tmp" ;;
esac
FAKE
    cat > "$T/bin/claude" <<'FAKE'
#!/usr/bin/env bash
if [[ "$*" == *--help* || "$*" == *--version* ]]; then echo '--tools --effort'; exit; fi
printf '%s\n' "$@" >> "$T/backend"
cat >/dev/null
printf '{"type":"result","subtype":"success","is_error":false,"result":"done"}\n'
exit "${FAKE_EXIT:-0}"
FAKE
    cat > "$T/bin/codex" <<'FAKE'
#!/usr/bin/env bash
if [[ "$*" == *--version* ]]; then echo 'codex-cli 0.153.2'; exit; fi
if [[ "${1:-}" != exec || "$*" == *--help* ]]; then echo '--ephemeral --json'; exit; fi
printf '%s\n' "$@" >> "$T/backend"
if [[ "${FAKE_CAPACITY:-0}" == 1 ]]; then
  printf '{"type":"task_complete","error":{"codex_error_info":"usage_limit_exceeded"}}\n'
  exit 3
fi
cat >/dev/null
printf '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
exit "${FAKE_EXIT:-0}"
FAKE
    cat > "$T/bin/date" <<'FAKE'
#!/usr/bin/env bash
if [[ "$*" == '-u +%s' && -f "$T/clock" ]]; then cat "$T/clock"; else /bin/date "$@"; fi
FAKE
    chmod +x "$T/bin/"*
    export PATH="$T/bin:$PATH" CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
    export CLAVAIN_DISPATCH_RECEIPT_FILE="$T/receipts"
    DISPATCH="$ROOT/scripts/dispatch.sh"
    arm sol-medium opus
}
teardown() { rm -rf "$T"; }
arm() {
    ARM="$1"; PRODUCER="$2"
    PROFILE="experiment-mk-d0h1j.1-$ARM"
    if [[ "$ARM" == sol-medium ]]; then ENGINE=codex; MODEL=gpt-6.1-sol; EFFORT=medium
    else ENGINE=claude; MODEL=claude-fable-5-2; EFFORT=high; fi
}
outer() {
    local -a producer=()
    [[ -z "$PRODUCER" ]] || producer=(--producer-identity "$PRODUCER")
    bash "$DISPATCH" --policy-profile "$PROFILE" --role cross-lab-review "${producer[@]}" \
      --bead mk-d0h1j.1 --context-file "$T/ctx" -C "$T/repo" --prompt-file "$T/prompt" -o "$T/out" "$@"
}
route() {
    ROUTE="$("$REAL_IC" --json route dispatch --policy="$ROOT/config/routing.yaml" --role=cross-lab-review \
      --context-file="$T/ctx" --policy-profile="$PROFILE" --producer-identity="$PRODUCER")"
    CANDIDATE="$(jq -c '{profile_ref,profile}' <<< "$ROUTE")"
}
child() {
    bash "$DISPATCH" --role-resolved --policy-profile "$PROFILE" --role cross-lab-review --producer-identity "$PRODUCER" \
      --bead mk-d0h1j.1 --context-file "$T/ctx" --resolved-profile-ref "exp-mk-d0h1j.1-$ARM" \
      --resolved-route-json "$ROUTE" --resolved-profile-json "$CANDIDATE" --to "$ENGINE" --model "$MODEL" \
      --reasoning-effort "$EFFORT" --service-tier standard -C "$T/repo" --prompt-file "$T/prompt" -o "$T/out" "$@"
}
refused() { [ "$status" -eq 2 ]; [ ! -e "$T/backend" ]; }
@test "unregistered experiment refuses before resolution" {
    PROFILE=experiment-unknown run outer
    refused
    [[ "$output" == *"unregistered experiment"* ]]
}
@test "outer reaches each backend with exact effort and strict complete evidence" {
    for spec in 'sol-medium opus' 'fable-high sol' 'sol-medium anthropic/claude-opus-5-5' 'fable-high openai/gpt-6.1-sol'; do
        read -r a p <<< "$spec"; arm "$a" "$p"
        rm -f "$T/backend" "$T/receipts"
        run outer
        [ "$status" -eq 0 ]
        grep -qx "$MODEL" "$T/backend"
        if [[ "$ENGINE" == codex ]]; then [ "$(grep -cx model_reasoning_effort=medium "$T/backend")" -eq 1 ];
        else grep -qx high "$T/backend"; fi
        [ "$(wc -l < "$T/receipts")" -eq 2 ]
        jq -se '.[0].outcome=="started" and .[1].launched==true and .[0].run_id==.[1].run_id and
          all(.[]; .schema_version==1 and .evidence_mode=="strict" and .scope=="mk-d0h1j.1" and
          (.decision_context_sha256|length==64) and (.fresh_route_sha256|length==64) and
          .producer_model!=null and .producer_lab!=null and .policy_hash!=null)' "$T/receipts"
    done
}
@test "outer refuses all execution and backend override flags" {
    for flag in --to --model --tier --reasoning-effort --service-tier -c --config -p --profile --add-dir -a --output-schema --claude-unsafe --yolo --dangerously-skip-permissions --via --capacity-substitute; do
        run outer "$flag" dummy
        refused
    done
}
@test "child rejects duplicate execution flags and backend config" {
    route
    for flag in --to --model --reasoning-effort --service-tier --resolved-profile-ref --resolved-profile-json --resolved-route-json; do
        run child "$flag" medium
        refused
    done
    run child --reasoning-effort high
    refused
    run child --engine codex
    refused
    run child -m gpt-6.1-sol
    refused
    run child -c model_reasoning_effort=high
    refused
}
@test "child requires exact candidate ref model effort and service" {
    route
    EFFORT=high run child; refused
    MODEL=other run child; refused
    CANDIDATE="$(jq -c '.profile_ref="other"' <<< "$CANDIDATE")" run child; refused
}
@test "stale context and scope are refused" {
    route
    jq '.reasons += ["foundational-invariants"]' "$T/ctx" > "$T/new"; cat "$T/new" > "$T/ctx"
    run child; refused
    jq '.reasons=["difficult-verification"] | .scope="mk-other"' "$T/ctx" > "$T/new"; cat "$T/new" > "$T/ctx"
    run child; refused
}
@test "fresh resolution detects semantic mismatch and missing exemption" {
    route
    for mode in high model exemption two producer; do
        FAKE_ROUTE="$mode" run child
        refused
    done
}
@test "canonical producer aliases refuse same lab for both arms" {
    for p in opus claude-opus-5-5 anthropic/claude-opus-5-5; do
        arm fable-high "$p"; run outer; refused
    done
    for p in sol gpt-6.1-sol openai/gpt-6.1-sol; do
        arm sol-medium "$p"; run outer; refused
    done
}
@test "unknown empty and missing canonical producer refuse both arms" {
    for spec in 'sol-medium opus' 'fable-high sol'; do
        read -r a p <<< "$spec"; arm "$a" "$p"
        for mode in unknown empty missing; do
            FAKE_ROUTE="$mode" run outer; refused
        done
    done
}
@test "missing producer wrong role and wrong bead refuse" {
    PRODUCER='' run outer; refused
    run outer --role scout; refused
    run outer --bead mk-other; refused
}
@test "bare experiment tiers never reach a backend" {
    for a in sol-medium fable-high; do
        run bash "$DISPATCH" --tier "exp-mk-d0h1j.1-$a" --dry-run hello
        refused
    done
}
@test "expiry is exclusive and the previous second launches" {
    /bin/date -u -d 2026-12-31T00:00:00Z +%s > "$T/clock"
    run outer; refused
    echo 1798675199 > "$T/clock"
    run outer
    [ "$status" -eq 0 ]
}
@test "strict started append failure prevents launch" {
    echo blocked > "$T/blocker"
    CLAVAIN_DISPATCH_RECEIPT_FILE="$T/blocker/receipts" run outer
    [ "$status" -eq 4 ]
    [ ! -e "$T/backend" ]
}
@test "capacity failure cannot add a candidate" {
    FAKE_CAPACITY=1 run outer
    [ "$status" -ne 0 ]
    [ "$(grep -cx exec "$T/backend")" -eq 1 ]
    [[ "$output" == *"quota_exhausted"* ]]
}

package_fixture() {
    mkdir "$T/package"
    cp -a "$ROOT/scripts" "$ROOT/config" "$ROOT/.claude-plugin" "$T/package/"
    DISPATCH="$T/package/scripts/dispatch.sh"
}
append_wrapper() {
    package_fixture
    # A wrapper stub models a blocked append returning after the clock crossed
    # expiry. It uses the real locked append, including its in-lock check.
    cat >> "$T/package/scripts/lib-dispatch-audit.sh" <<'WRAP'
eval "$(declare -f _append_dispatch_run_receipt | sed '1s/_append_dispatch_run_receipt/_real_experiment_append/')"
_append_dispatch_run_receipt() {
  if [[ "$(jq -r .outcome <<< "$1")" == started ]]; then
    _real_experiment_append "$1" || return $?
    echo 1798675200 > "$T/clock"
  else
    [[ "${FAIL_TERMINAL:-0}" != 1 ]] || return 1
    _real_experiment_append "$1"
  fi
}
WRAP
    echo 1798675199 > "$T/clock"
}
@test "expiry during append records a refused terminal and no launch" {
    append_wrapper
    run outer
    refused
    jq -se 'length==2 and .[0].outcome=="started" and .[1].outcome=="refused_expired" and
      .[0].run_id==.[1].run_id and .[1].launched==false and .[1].launch_checked_at=="1798675200"' "$T/receipts"
    # Accepted evidence requires both lifecycle records and a launched terminal.
    ! jq -se '.[0].outcome=="started" and .[1].run_id==.[0].run_id and .[1].launched==true' "$T/receipts"
    head -1 "$T/receipts" > "$T/started-only"
    ! jq -se 'length==2 and .[1].launched==true' "$T/started-only"
}
@test "terminal failure after append expiry returns evidence failure" {
    append_wrapper
    FAIL_TERMINAL=1 run outer
    [ "$status" -eq 75 ]
    [ ! -e "$T/backend" ]
}
@test "terminal write failure after launch returns evidence failure" {
    package_fixture
    cat >> "$T/package/scripts/lib-dispatch-audit.sh" <<'WRAP'
eval "$(declare -f _append_dispatch_run_receipt | sed '1s/_append_dispatch_run_receipt/_real_experiment_append/')"
_append_dispatch_run_receipt() {
  [[ "$(jq -r .outcome <<< "$1")" == started ]] || return 1
  _real_experiment_append "$1"
}
WRAP
    run outer
    [ "$status" -eq 75 ]
    [ -e "$T/backend" ]
}
@test "expiry inside the lock appends nothing" {
    package_fixture
    cat >> "$T/package/scripts/lib-dispatch-audit.sh" <<'WRAP'
eval "$(declare -f _append_dispatch_run_receipt | sed '1s/_append_dispatch_run_receipt/_real_experiment_append/')"
_append_dispatch_run_receipt() {
  echo 1798675200 > "$T/clock"
  _real_experiment_append "$1"
}
WRAP
    echo 1798675199 > "$T/clock"
    run outer
    refused
    [ ! -s "$T/receipts" ]
}
@test "expiry while waiting for the receipt lock appends nothing" {
    echo 1798675199 > "$T/clock"
    ( exec 8>>"$T/receipts.lock"; flock 8; touch "$T/locked"; sleep 2; echo 1798675200 > "$T/clock" ) &
    holder=$!
    for _ in $(seq 1 50); do [ -f "$T/locked" ] && break; sleep 0.02; done
    run outer
    wait "$holder"
    refused
    [ ! -s "$T/receipts" ]
}
@test "fresh decision refuses stale route even with cheap precheck disabled" {
    route
    package_fixture
    sed -i 's/select(. != "difficult-verification")/select(false)/' "$DISPATCH"
    jq '.reasons += ["foundational-invariants"]' "$T/ctx" > "$T/new"; cat "$T/new" > "$T/ctx"
    run child
    refused
    [[ "$output" == *"stale for this context"* ]]
}
@test "missing service flag refuses the resolved child" {
    route
    run bash "$DISPATCH" --role-resolved --policy-profile "$PROFILE" --role cross-lab-review --producer-identity "$PRODUCER" \
      --bead mk-d0h1j.1 --context-file "$T/ctx" --resolved-profile-ref "exp-mk-d0h1j.1-$ARM" \
      --resolved-route-json "$ROUTE" --resolved-profile-json "$CANDIDATE" --to "$ENGINE" --model "$MODEL" \
      --reasoning-effort "$EFFORT" --dry-run fixture
    refused
}
@test "malformed registry expiry fails closed" {
    package_fixture
    jq 'with_entries(.value.expires="invalid")' "$T/package/config/experiment-profiles.json" > "$T/new"
    cat "$T/new" > "$T/package/config/experiment-profiles.json"
    run outer
    refused
}
@test "missing flock refuses strict launch" {
    mkdir "$T/nolock"
    for tool in bash jq date sha256sum awk sed head dirname mkdir sleep cat wc tr rm seq mktemp chmod stat git python3 cp env touch sort grep comm tee tail cut basename readlink timeout; do
        path="$(command -v "$tool")" || continue
        ln -s "$path" "$T/nolock/$tool"
    done
    ln -s "$T/bin/ic" "$T/nolock/ic"
    ln -s "$T/bin/codex" "$T/nolock/codex"
    ln -s "$T/bin/claude" "$T/nolock/claude"
    PATH="$T/nolock" run outer
    [ "$status" -eq 4 ]
    [ ! -e "$T/backend" ]
}
@test "receipt lock timeout refuses strict launch" {
    ( exec 8>>"$T/receipts.lock"; flock 8; touch "$T/locked"; sleep 12 ) &
    holder=$!
    for _ in $(seq 1 50); do [ -f "$T/locked" ] && break; sleep 0.02; done
    run outer
    wait "$holder"
    [ "$status" -eq 4 ]
    [ ! -e "$T/backend" ]
    [ ! -s "$T/receipts" ]
}
@test "mutating original context after launch cannot change snapshot evidence" {
    before="$(sha256sum "$T/ctx" | awk '{print $1}')"
    sed -i '/cat >\/dev\/null/a echo changed > "$T/ctx"' "$T/bin/codex"
    run outer
    [ "$status" -eq 0 ]
    [ "$(cat "$T/ctx")" = changed ]
    jq -se --arg hash "$before" 'all(.[]; .decision_context_sha256==$hash)' "$T/receipts"
}

@test "fresh canonical same-lab guard refuses aliases independently of resolver exclusion" {
    for spec in 'sol-medium opus gpt-6.1-sol sol' 'sol-medium opus gpt-6.1-sol openai/gpt-6.1-sol' 'sol-medium opus gpt-6.1-sol gpt-6.1-sol' 'fable-high gpt-6.1-sol claude-opus-5-5 opus' 'fable-high gpt-6.1-sol claude-opus-5-5 anthropic/claude-opus-5-5' 'fable-high gpt-6.1-sol claude-opus-5-5 claude-opus-5-5'; do
        read -r a p canonical raw <<< "$spec"
        arm "$a" "$p"; route
        ROUTE="$(jq -c --arg p "$raw" --arg m "$canonical" '.producer_identity=$p | .producer_model=$m' <<< "$ROUTE")"
        printf '%s\n' "$ROUTE" > "$T/fixture-route"
        PRODUCER="$raw" FAKE_ROUTE=fixture run child
        refused
        [[ "$output" == *"same-lab producer refused"* ]]
    done
}
@test "resolved child experiment tier requires a validated experiment profile" {
    route
    for profile in default ""; do
        run child --policy-profile="$profile"
        refused
    done
}

@test "registry read failure aborts tier guard even under set +e" {
    # One-line helpers are emitted separately from the multiline guard.
    sed -n '/^_experiment_refuse() /p; /^_experiment_registry() /p; /^_experiment_tier_guard() {/,/^}/p' "$DISPATCH" > "$T/tier-guard.sh"
    run bash -c '
        set -uo pipefail
        set +e
        source "$1"
        _experiment_registry() { return 1; }
        ROLE_RESOLVED=false EXPERIMENT_VALIDATED=false CLAVAIN_POLICY_PROFILE=""
        _experiment_tier_guard ordinary
        touch "$2"
    ' _ "$T/tier-guard.sh" "$T/continued"
    [ "$status" -eq 2 ]
    [ ! -e "$T/continued" ]
    [[ "$output" == *"experiment registry"* ]]
}

@test "tier helper clearly refuses a registry entry with no tier" {
    package_fixture
    jq 'with_entries(.value |= del(.tier))' "$T/package/config/experiment-profiles.json" > "$T/no-tier.json"
    cp "$T/no-tier.json" "$T/package/config/experiment-profiles.json"
    run python3 "$T/package/scripts/tier-fallback-chain.py" --policy "$ROOT/config/routing.yaml" --tier fast
    [ "$status" -eq 4 ]
    [[ "$output" == *"experiment registry"* ]]
    [[ "$output" != *"Traceback"* ]]
}
