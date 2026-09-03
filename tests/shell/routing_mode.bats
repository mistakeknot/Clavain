#!/usr/bin/env bats
# Sylveste-0pk: mode toggles must never rewrite the doctrine phases.

setup() {
    REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    TMP="$(mktemp -d)"
    cp "$REPO/config/routing.yaml" "$TMP/routing.yaml"
    export ROUTING_FILE="$TMP/routing.yaml"
    SCRIPT="$REPO/scripts/routing-mode.sh"
}

teardown() { rm -rf "$TMP"; }

phase_model() {  # $1 = phase name → value of its model: line
    awk -v p="    $1:" '$0==p{f=1;next} f&&/^      model:/{print $2;exit} f&&/^    [a-z]/{exit}' "$ROUTING_FILE"
}

phase_cat() {    # $1 = phase, $2 = category → value
    awk -v p="    $1:" -v c="        $2:" '$0==p{f=1;next} f&&index($0,c)==1{print $2;exit} f&&/^    [a-z]/{exit}' "$ROUTING_FILE"
}

@test "baseline fixture carries the doctrine entries" {
    [ "$(phase_model strategized)" = "fable" ]
    [ "$(phase_model planned)" = "fable" ]
    [ "$(phase_cat planned research)" = "haiku" ]
}

@test "economy leaves brainstorm/strategized/planned on fable and moves executing to sonnet" {
    run bash "$SCRIPT" economy
    [ "$status" -eq 0 ]
    [ "$(phase_model strategized)" = "fable" ]
    [ "$(phase_model planned)" = "fable" ]
    [ "$(phase_model brainstorm)" = "fable" ]
    [ "$(phase_model executing)" = "sonnet" ]
    [ "$(phase_model shipping)" = "sonnet" ]
    grep -q '^    model: sonnet' "$ROUTING_FILE"
}

@test "quality sets non-doctrine phases to inherit but keeps the dose guard on planned" {
    run bash "$SCRIPT" quality
    [ "$status" -eq 0 ]
    [ "$(phase_model executing)" = "inherit" ]
    [ "$(phase_cat executing review)" = "inherit" ]
    [ "$(phase_model planned)" = "fable" ]
    [ "$(phase_cat planned research)" = "haiku" ]
    [ "$(phase_cat planned review)" = "sonnet" ]
    grep -q '^    model: opus' "$ROUTING_FILE"
}

@test "economy after quality restores executing to sonnet and never touched the doctrine rows" {
    bash "$SCRIPT" quality >/dev/null
    bash "$SCRIPT" economy >/dev/null
    [ "$(phase_model executing)" = "sonnet" ]
    [ "$(phase_model strategized)" = "fable" ]
    diff <(awk '/^    (brainstorm|strategized|planned):/,/^    [a-z-]*:$/' "$REPO/config/routing.yaml" | grep -E 'model:|research:|review:|synthesis:') \
         <(awk '/^    (brainstorm|strategized|planned):/,/^    [a-z-]*:$/' "$ROUTING_FILE"      | grep -E 'model:|research:|review:|synthesis:')
}

@test "dispatch section is untouched by either mode" {
    before="$(awk '/^dispatch:/,0' "$ROUTING_FILE" | md5)"
    bash "$SCRIPT" quality >/dev/null; bash "$SCRIPT" economy >/dev/null
    after="$(awk '/^dispatch:/,0' "$ROUTING_FILE" | md5)"
    [ "$before" = "$after" ]
}
