#!/usr/bin/env bash
# Compare a deployed bundle's /.well-known/<project>/version to the expected commit.
# Usage: check-version-endpoint.sh <base-url> <project> <expected-commit> [expected-version]
# The endpoint must serve JSON with "version" and "commit". A commit matches when
# either value is a prefix of the other (min 7 chars). Exit 0 match, 1 mismatch or
# bad payload, 2 fetch failure/usage. CHECK_VERSION_FETCH_CMD overrides curl (tests).
set -euo pipefail
if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "usage: $0 <base-url> <project> <expected-commit> [expected-version]" >&2; exit 2
fi
base="${1%/}"; project="$2"; want="$3"; want_version="${4:-}"
url="$base/.well-known/$project/version"
if [ -n "${CHECK_VERSION_FETCH_CMD:-}" ]; then
  body="$($CHECK_VERSION_FETCH_CMD "$url")" || { echo "fetch failed: $url" >&2; exit 2; }
else
  body="$(curl -fsSL --max-time 20 "$url")" || { echo "fetch failed: $url" >&2; exit 2; }
fi
export BODY="$body" WANT="$want" WANT_VERSION="$want_version" URL="$url"
exec python3 -I - <<'PY'
import json, os, re, sys
try:
    d = json.loads(os.environ["BODY"])
    got, ver = d["commit"], d["version"]
    if not (isinstance(got, str) and isinstance(ver, str) and ver
            and re.fullmatch(r"[0-9a-fA-F]{7,64}", got)):
        raise ValueError("bad field types or commit format")
except (ValueError, KeyError, TypeError):
    print(f"{os.environ['URL']}: payload lacks string version and hex commit", file=sys.stderr); sys.exit(1)
want, wv = os.environ["WANT"], os.environ["WANT_VERSION"]
ok = len(want) >= 7 and len(got) >= 7 and (got.startswith(want) or want.startswith(got))
if not ok:
    print(f"commit mismatch: deployed {got}, expected {want}", file=sys.stderr); sys.exit(1)
if wv and ver != wv:
    print(f"version mismatch: deployed {ver}, expected {wv}", file=sys.stderr); sys.exit(1)
print(f"version-endpoint: ok version={ver} commit={got}")
PY
