#!/usr/bin/env bash
# Proposed manual zklw recipe; registry admission belongs to mk-ag2s.25.
# Preserve the existing pilot and packaging contract. No publication or install.
set -euo pipefail
initial_umask=$(umask)
umask 077
unverifiable() { echo "UNVERIFIABLE: $*" >&2; exit 2; }
readonly dependency=39f7599083c76ce32f46527c84fd58b43d1143de
readonly go_digest=1153d3d50e0ac764b447adfe05c2bcf08e889d42a02e0fe0259bd47f6733ad7f
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || unverifiable 'requires Linux x86_64 guest'
[[ ${CI_SOURCE_SHA:-} =~ ^[0-9a-f]{40}$ ]] || unverifiable 'exact CI_SOURCE_SHA required'
[[ $(git -C /workspace/source rev-parse HEAD) == "$CI_SOURCE_SHA" ]] || unverifiable 'source HEAD mismatch'
[[ -z $(git -C /workspace/source status --porcelain --untracked-files=all) ]] || unverifiable 'source is not clean'
[[ ! -e /workspace/work-ownership ]] || unverifiable 'fresh guest workspace required'
for required in bash curl gcc git python3 sha256sum tar; do
  command -v "$required" >/dev/null || unverifiable "missing executable: $required"
done
python3 -c 'import pytest, yaml' || unverifiable 'pilot requires pytest and PyYAML'
printf '%s  %s\n' \
  e6db19c2dd4d2a02503fc0cb989ed3640beab4ed18ec97aa104783d41a8640dd /workspace/source/scripts/ci-verification.sh \
  862a9fbfec60a30aaeadc9cce1c3a2914c4caa2b3b21b1458ff6bd3e37de5bc1 /workspace/source/scripts/ci-package.sh \
  | sha256sum --check - || unverifiable 'legacy recipe bytes changed'
mkdir -p /workspace/work-ownership/{tools,os,core}
curl --fail --location --retry 3 --max-time 180 --silent --show-error \
  https://go.dev/dl/go1.26.4.linux-amd64.tar.gz \
  -o /workspace/work-ownership/tools/go.tar.gz
printf '%s  %s\n' "$go_digest" /workspace/work-ownership/tools/go.tar.gz | sha256sum --check -
tar -xzf /workspace/work-ownership/tools/go.tar.gz -C /workspace/work-ownership/tools
export PATH="/workspace/work-ownership/tools/go/bin:$PATH" GOTOOLCHAIN=local CGO_ENABLED=1 CC=gcc
[[ $(go version) == 'go version go1.26.4 linux/amd64' ]] || unverifiable 'unexpected Go toolchain'
git clone --no-hardlinks /workspace/source /workspace/work-ownership/os/Clavain
git -C /workspace/work-ownership/os/Clavain checkout --detach "$CI_SOURCE_SHA"
# Public landed dependency; no credentials, branch fallback or unlanded launcher.
git init /workspace/work-ownership/core/intercore
git -C /workspace/work-ownership/core/intercore remote add origin https://github.com/mistakeknot/intercore.git
GIT_TERMINAL_PROMPT=0 git -C /workspace/work-ownership/core/intercore fetch --depth=1 origin "$dependency"
git -C /workspace/work-ownership/core/intercore checkout --detach "$dependency"
[[ $(git -C /workspace/work-ownership/core/intercore rev-parse HEAD) == "$dependency" ]] || unverifiable 'dependency commit mismatch'
[[ $(git -C /workspace/work-ownership/core/intercore rev-parse 'HEAD^{tree}') == 4c3a4bb74cbeffd50fd6fbd35cfff2bf9f072455 ]] || unverifiable 'dependency tree mismatch'
cd /workspace/work-ownership/os/Clavain
printf 'ownership-check source=%s dependency=%s toolchain=%s\n' "$CI_SOURCE_SHA" "$dependency" "$(go version)"
# Execute unchanged legacy verification first; its protected archive remains in
# the job log. Failure stops the composite check without laundering its result.
(umask "$initial_umask"; bash scripts/ci-verification.sh)
bash scripts/check-work-ownership.sh
