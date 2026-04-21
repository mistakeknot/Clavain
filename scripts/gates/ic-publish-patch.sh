#!/usr/bin/env bash
# Gate wrapper for `ic publish --patch <plugin>`.
#
# Usage: ic-publish-patch.sh <plugin-dir> [ic-args...]
#
# v1 note: the `.publish-approved` marker remains an additive parallel gate.
# This wrapper records an authorization row but does NOT modify the
# RequiresApproval() hook. Unification is scheduled for v1.5.
set -euo pipefail

PLUGIN_DIR="${1:?usage: ic-publish-patch.sh <plugin-dir> [ic-args...]}"
shift

# shellcheck source=/dev/null
source "$(dirname "$0")/_common.sh"

HEAD_SHA="$(git -C "$PLUGIN_DIR" rev-parse HEAD 2>/dev/null || echo)"

if ! gate_token_consume ic-publish-patch "$PLUGIN_DIR"; then
  exit 1
fi

if [[ "${GATE_CONSUMED:-0}" != "1" ]]; then
  if [[ -n "${CLAVAIN_BEAD_ID:-}" ]]; then
    gate_populate_vetting "$CLAVAIN_BEAD_ID"
  fi

  check_flags=( --target="$PLUGIN_DIR" --head-sha="$HEAD_SHA" )
  if [[ -n "${CLAVAIN_VETTED_AT:-}"          ]]; then check_flags+=( --vetted-at="$CLAVAIN_VETTED_AT" ); fi
  if [[ -n "${CLAVAIN_VETTED_SHA:-}"         ]]; then check_flags+=( --vetted-sha="$CLAVAIN_VETTED_SHA" ); fi
  if [[ "${CLAVAIN_TESTS_PASSED:-0}"   == "1" ]]; then check_flags+=( --tests-passed ); fi

  rc=0
  gate_check ic-publish-patch "${check_flags[@]}" >/dev/null || rc=$?
  gate_decide_mode "$rc" ic-publish-patch
fi

ic publish --patch "$PLUGIN_DIR" "$@"

gate_record ic-publish-patch "$PLUGIN_DIR" "" --vetted-sha="$HEAD_SHA"
gate_sign   ic-publish-patch "$PLUGIN_DIR" ""
