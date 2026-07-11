#!/usr/bin/env bash
# Gate wrapper for `git push` targeting main on the current remote.
#
# Usage: git-push-main.sh [remote] [refspec]
# Defaults: remote=origin, refspec=main.
#
# Force and deletion refspecs are refused. This wrapper authorizes one resolved
# commit and pushes that immutable object to refs/heads/main.
set -euo pipefail

REMOTE="${1:-origin}"
REFSPEC="${2:-main}"

# shellcheck source=/dev/null
source "$(dirname "$0")/_common.sh"

gate_resolve_authz_root "$PWD" target
gate_require_signer

if [[ "$REFSPEC" == +* ]]; then
  echo "git-push-main: force refspecs require a separate authorization path" >&2
  exit 1
fi
if [[ "$REFSPEC" == *:* ]]; then
  SOURCE_REF="${REFSPEC%%:*}"
  DEST_REF="${REFSPEC#*:}"
else
  SOURCE_REF="$REFSPEC"
  DEST_REF="$REFSPEC"
fi
if [[ -z "$SOURCE_REF" ]]; then
  echo "git-push-main: deletion refspecs are not allowed" >&2
  exit 1
fi
case "$DEST_REF" in
  main|refs/heads/main) DEST_REF="refs/heads/main" ;;
  *) echo "git-push-main: destination must be main, got $DEST_REF" >&2; exit 1 ;;
esac

SOURCE_SHA="$(git rev-parse --verify "${SOURCE_REF}^{commit}" 2>/dev/null || echo)"
PUSH_URLS="$(git remote get-url --push --all "$REMOTE" 2>/dev/null || echo)"
if [[ -z "$SOURCE_SHA" || -z "$PUSH_URLS" ]]; then
  echo "git-push-main: cannot resolve source commit or push URL" >&2
  exit 1
fi
REPO_HASH="$(printf '%s\n' "$PUSH_URLS" | gate_sha256)"
GIT_TARGET="repo=sha256:${REPO_HASH};ref=${DEST_REF};head=${SOURCE_SHA}"

if ! gate_token_consume git-push-main "$GIT_TARGET"; then
  exit 1
fi

if [[ "${GATE_CONSUMED:-0}" != "1" ]]; then
  check_flags=( --target="$GIT_TARGET" --head-sha="$SOURCE_SHA" )
  rc=0
  gate_check git-push-main "${check_flags[@]}" >/dev/null || rc=$?
  gate_decide_mode "$rc" git-push-main
  gate_record_signed git-push-main "$GIT_TARGET" "" --vetted-sha="$SOURCE_SHA"
fi

CURRENT_PUSH_URLS="$(git remote get-url --push --all "$REMOTE" 2>/dev/null || echo)"
if [[ "$CURRENT_PUSH_URLS" != "$PUSH_URLS" ]]; then
  echo "git-push-main: push URL changed after authorization; refusing" >&2
  exit 1
fi
git push "$REMOTE" "${SOURCE_SHA}:${DEST_REF}"

echo "git-push-main: pushed ${SOURCE_SHA} → ${REMOTE}/${DEST_REF}"
