#!/usr/bin/env bash
# Manual zklw guest recipe. Source, dependency, recipe and image are broker-pinned.
set -euo pipefail
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]]
[[ ${CI_SOURCE_SHA:-} =~ ^[0-9a-f]{40}$ && ${CI_INTERCORE_SHA:-} =~ ^[0-9a-f]{40}$ ]]
[[ ${CI_GO_VERSION:-} == go1.26.4 ]]
[[ ${CI_GO_ARCHIVE_SHA256:-} == 1153d3d50e0ac764b447adfe05c2bcf08e889d42a02e0fe0259bd47f6733ad7f ]]
[[ $(git -C /workspace/source rev-parse HEAD) == "$CI_SOURCE_SHA" ]]
[[ $(git -C /workspace/intercore rev-parse HEAD) == "$CI_INTERCORE_SHA" ]]
[[ ! -e /workspace/build && ! -e /workspace/package-output ]]
mkdir -p /workspace/tools /workspace/build/os /workspace/build/core
curl --fail --location --retry 3 --max-time 180 --silent --show-error \
  https://go.dev/dl/go1.26.4.linux-amd64.tar.gz -o /workspace/tools/go.tar.gz
printf '%s  %s\n' 1153d3d50e0ac764b447adfe05c2bcf08e889d42a02e0fe0259bd47f6733ad7f \
  /workspace/tools/go.tar.gz | sha256sum --check -
tar -xzf /workspace/tools/go.tar.gz -C /workspace/tools
export PATH="/workspace/tools/go/bin:$PATH" GOTOOLCHAIN=local
[[ $(go version) == 'go version go1.26.4 linux/amd64' ]]
git clone --no-hardlinks /workspace/source /workspace/build/os/Clavain
git -C /workspace/build/os/Clavain checkout --detach "$CI_SOURCE_SHA"
git clone --no-hardlinks /workspace/intercore /workspace/build/core/intercore
git -C /workspace/build/core/intercore checkout --detach "$CI_INTERCORE_SHA"
bash /workspace/build/os/Clavain/scripts/build-release.sh
bash /workspace/build/os/Clavain/scripts/verify-release-binaries.sh
mkdir /workspace/package-output
for platform in darwin-arm64 linux-amd64 windows-amd64; do
  install -m 0755 "/workspace/build/os/Clavain/bin/clavain-cli-go-$platform" "/workspace/package-output/clavain-cli-go-$platform"
done
install -m 0644 /workspace/build/os/Clavain/bin/release-manifest.json /workspace/package-output/release-manifest.json
