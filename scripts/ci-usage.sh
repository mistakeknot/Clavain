#!/usr/bin/env bash
# Manual-only zklw usage recipe. The broker must pin source, recipe and image.
set -Eeuo pipefail
umask 077

readonly SOURCE_ROOT=/workspace/source
readonly BUILD_ROOT=/workspace/build
readonly INTERCORE_URL=https://github.com/mistakeknot/intercore.git
readonly INTERCORE_SHA=9bc85a3bbf81c135a2784677676dac2487ddd02a
readonly INTERCORE_TAG="refs/tags/ci/$INTERCORE_SHA"
readonly INTERSTAT_SHA=2dd2bac412288b7aead853a1e43abf9c40496ee5
readonly INTERSTAT_URL="https://github.com/mistakeknot/interstat/archive/$INTERSTAT_SHA.tar.gz"
readonly INTERSTAT_ARCHIVE_SHA256=41bc1a92e1279aab479418a8937489de56558d0402cc25b21dcc570b7e5ef1cf
readonly BATS_URL=https://github.com/bats-core/bats-core/archive/refs/tags/v1.12.0.tar.gz
readonly BATS_ARCHIVE_SHA256=e36b020436228262731e3319ed013d84fcd7c4bd97a1b34dee33d170e9ae6bab
readonly GAWK_URL=https://ftp.gnu.org/gnu/gawk/gawk-5.3.1.tar.xz
readonly GAWK_ARCHIVE_SHA256=694db764812a6236423d4ff40ceb7b6c4c441301b72ad502bb5c27e00cd56f78
readonly GO_URL=https://go.dev/dl/go1.26.4.linux-amd64.tar.gz
readonly GO_ARCHIVE_SHA256=1153d3d50e0ac764b447adfe05c2bcf08e889d42a02e0fe0259bd47f6733ad7f
readonly NATIVE_CODEX_URL=https://github.com/openai/codex/releases/download/rust-v0.154.0/codex-x86_64-unknown-linux-musl.tar.gz
readonly NATIVE_CODEX_ARCHIVE_SHA256=d7e18b2597ae8f242f5f31ee9e90deef48dbc9edd634d9868fb6435d08c07f02
readonly NATIVE_CODEX_ARCHIVE_SIZE=98981886
readonly IMAGE_SHA256=698d1b22ad393190d3d4d2339439fd6bb2ecdb3f6651320049351f4283c156b6
readonly USAGE_MANIFEST_SHA256=c6ff1aa63dbdf72325a5404fd3a8e31c60f58a71acedb9ca9b4902396a72f401

unverifiable() {
  echo "UNVERIFIABLE: $*" >&2
  exit 2
}

# shellcheck disable=SC2329 # Invoked indirectly by the ERR trap below.
bootstrap_error() {
  local status=$?
  echo "UNVERIFIABLE: usage CI bootstrap failed at line $1 (exit $status)" >&2
  exit 2
}
trap 'bootstrap_error "$LINENO"' ERR

[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || unverifiable "requires Linux x86_64 guest image $IMAGE_SHA256"
[[ ${CI_SOURCE_SHA:-} =~ ^[0-9a-f]{40}$ ]] || unverifiable "CI_SOURCE_SHA must be an exact commit"
# Ordinary check jobs receive source/recipe identities only. Dependency and Go
# inputs are pinned by this reviewed recipe and verified against downloaded bytes;
# the broker supplies CI_INTERCORE_SHA/CI_GO_* only to separate packaging jobs.
[[ -d "$SOURCE_ROOT/.git" || -f "$SOURCE_ROOT/.git" ]] || unverifiable "source checkout is missing"
[[ $(git -C "$SOURCE_ROOT" rev-parse HEAD) == "$CI_SOURCE_SHA" ]] || unverifiable "CI_SOURCE_SHA does not equal source HEAD"
[[ -z $(git -C "$SOURCE_ROOT" status --porcelain=v1 --untracked-files=all) ]] || unverifiable "source checkout is not clean"
[[ ! -e "$BUILD_ROOT" ]] || unverifiable "$BUILD_ROOT already exists; fresh guest required"

for command in bash curl gcc git install jq make python3 sha256sum shasum tar xz; do
  command -v "$command" >/dev/null 2>&1 || unverifiable "required executable is unavailable: $command"
done
python3 -c 'import pytest, yaml' >/dev/null 2>&1 || unverifiable "pytest and PyYAML are required from the pinned guest image"

tools_root=$(mktemp -d /workspace/clavain-usage-tools.XXXXXX)
runtime_root=$(mktemp -d /workspace/clavain-usage-runtime.XXXXXX)
legacy_runtime_root=$(mktemp -d /workspace/clavain-legacy-runtime.XXXXXX)
evidence_root=$(mktemp -d /workspace/clavain-usage-evidence.XXXXXX)
chmod 700 "$tools_root" "$runtime_root" "$legacy_runtime_root" "$evidence_root"
mkdir -m 700 "$tools_root/bin" "$tools_root/downloads" "$tools_root/src" \
  "$runtime_root/home" "$runtime_root/tmp" "$legacy_runtime_root/home" "$legacy_runtime_root/tmp"
legacy_marker="$legacy_runtime_root/start.marker"
install -m 0600 /dev/null "$legacy_marker"
mkdir -p "$BUILD_ROOT/os" "$BUILD_ROOT/core" "$BUILD_ROOT/interverse"

download() {
  local url=$1 output=$2 expected=$3
  curl --fail --location --retry 3 --max-time 180 --silent --show-error "$url" -o "$output" \
    || unverifiable "download failed: $url"
  printf '%s  %s\n' "$expected" "$output" | sha256sum --check - \
    || unverifiable "download digest mismatch: $url"
}

download "$GO_URL" "$tools_root/downloads/go.tar.gz" "$GO_ARCHIVE_SHA256"
tar -xzf "$tools_root/downloads/go.tar.gz" -C "$tools_root"
export PATH="$tools_root/bin:$tools_root/go/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"
export GOTOOLCHAIN=local
[[ $(go version) == 'go version go1.26.4 linux/amd64' ]] || unverifiable "unexpected Go toolchain"

# Actual pinned parser/schema generator only; never put it on the generic
# codex PATH where a fixture might accidentally launch inference.
download "$NATIVE_CODEX_URL" "$tools_root/downloads/native-codex.tar.gz" "$NATIVE_CODEX_ARCHIVE_SHA256"
[[ $(wc -c < "$tools_root/downloads/native-codex.tar.gz") -eq "$NATIVE_CODEX_ARCHIVE_SIZE" ]] || unverifiable "native Codex archive size mismatch"
[[ $(tar -tzf "$tools_root/downloads/native-codex.tar.gz") == codex-x86_64-unknown-linux-musl ]] || unverifiable "native Codex archive inventory mismatch"
tar -xzf "$tools_root/downloads/native-codex.tar.gz" -C "$tools_root"
export NATIVE_TEST_CODEX="$tools_root/codex-x86_64-unknown-linux-musl"
export NATIVE_TEST_CODEX_SHA256="$(sha256sum "$NATIVE_TEST_CODEX" | cut -d ' ' -f 1)"

# Native fixture schema validation uses only these six declared wheel packages.
# Verify bytes from uv.lock, then unpack into the private job dependency root.
# No global installation or dependency resolver/network fallback is involved.
python3 - "$SOURCE_ROOT/tests/uv.lock" "$tools_root/python" <<'PY'
import hashlib, io, pathlib, sys, tomllib, urllib.request, zipfile
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
pins=tomllib.loads(pathlib.Path(sys.argv[1]).read_text())
destination=pathlib.Path(sys.argv[2]); destination.mkdir(mode=0o700)
tags=set(sys_tags())
names={'jsonschema','attrs','jsonschema-specifications','referencing','rpds-py','typing-extensions'}
selected=[p for p in pins['package'] if p['name'] in names]
assert len(selected)==len(names)
for package in selected:
    wheels=[w for w in package['wheels'] if parse_wheel_filename(w['url'].rsplit('/',1)[-1])[3] & tags]
    assert wheels, 'no declared compatible schema-validation wheel: '+package['name']
    wheel=wheels[0]; assert wheel['url'].startswith('https://files.pythonhosted.org/packages/')
    with urllib.request.urlopen(wheel['url'], timeout=60) as response: raw=response.read(4*1024*1024)
    assert 'sha256:'+hashlib.sha256(raw).hexdigest()==wheel['hash']
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for item in archive.infolist():
            relative=pathlib.PurePosixPath(item.filename)
            assert not relative.is_absolute() and '..' not in relative.parts
            assert item.file_size<16*1024*1024 and (item.external_attr>>16)&0o170000 != 0o120000
        archive.extractall(destination)
PY
export PYTHONPATH="$tools_root/python"
python3 -c 'import importlib.metadata,jsonschema; assert importlib.metadata.version("jsonschema") == "4.26.0"'

download "$GAWK_URL" "$tools_root/downloads/gawk.tar.xz" "$GAWK_ARCHIVE_SHA256"
tar -xJf "$tools_root/downloads/gawk.tar.xz" -C "$tools_root/src"
(
  cd "$tools_root/src/gawk-5.3.1"
  ./configure --disable-nls --prefix="$tools_root/gawk" > "$evidence_root/gawk-configure.log"
  make -j2 > "$evidence_root/gawk-make.log"
)
install -m 0755 "$tools_root/src/gawk-5.3.1/gawk" "$tools_root/bin/gawk"
ln -s gawk "$tools_root/bin/awk"
[[ $(gawk --version | head -1) == 'GNU Awk 5.3.1, API 4.0' ]] || unverifiable "unexpected GNU awk version"
[[ $(awk --version | head -1) == 'GNU Awk 5.3.1, API 4.0' ]] || unverifiable "private awk does not resolve to GNU awk 5.3.1"

download "$BATS_URL" "$tools_root/downloads/bats.tar.gz" "$BATS_ARCHIVE_SHA256"
tar -xzf "$tools_root/downloads/bats.tar.gz" -C "$tools_root/src"
ln -s "$tools_root/src/bats-core-1.12.0/bin/bats" "$tools_root/bin/bats"
[[ $(bats --version) == 'Bats 1.12.0' ]] || unverifiable "unexpected Bats version"

download "$INTERSTAT_URL" "$tools_root/downloads/interstat.tar.gz" "$INTERSTAT_ARCHIVE_SHA256"
tar -xzf "$tools_root/downloads/interstat.tar.gz" -C "$BUILD_ROOT/interverse"
mv "$BUILD_ROOT/interverse/interstat-$INTERSTAT_SHA" "$BUILD_ROOT/interverse/interstat"
printf '%s  %s\n' \
  7a3690becdd64321b0d46b3968dd9fceb9e1039cf6693d8a40e1984c92b9d0f3 "$BUILD_ROOT/interverse/interstat/scripts/profile.py" \
  8bf7365336e6c47782b739a6abad45f2a499dddba602738f4edabd9e910a00ec "$BUILD_ROOT/interverse/interstat/scripts/claude_usage.py" \
  1b59f0687dc66fc60d6a06fa9bca6bed9e0f55eb74805be5b6b759cf920ec51c "$BUILD_ROOT/interverse/interstat/scripts/cost.py" \
  | sha256sum --check - || unverifiable "Interstat task-delivery dependency files differ from reviewed pin"

git clone --no-hardlinks --no-checkout "$SOURCE_ROOT" "$BUILD_ROOT/os/Clavain"
git -C "$BUILD_ROOT/os/Clavain" checkout --detach "$CI_SOURCE_SHA"
[[ $(git -C "$BUILD_ROOT/os/Clavain" rev-parse HEAD) == "$CI_SOURCE_SHA" ]] || unverifiable "isolated Clavain checkout has wrong HEAD"
[[ -z $(git -C "$BUILD_ROOT/os/Clavain" status --porcelain=v1 --untracked-files=all) ]] || unverifiable "isolated Clavain checkout is not clean"

# The parent publishes only this exact reviewed commit under a lightweight
# ci/<SHA> source tag. Until that exists, the guest must fail instead of using
# a branch, an archive with an unavailable digest, or a different kernel.
git clone --filter=blob:none --depth 1 --no-checkout --single-branch --branch "ci/$INTERCORE_SHA" \
  "$INTERCORE_URL" "$BUILD_ROOT/core/intercore" \
  || unverifiable "exact reviewed Intercore source tag is unavailable"
[[ $(git -C "$BUILD_ROOT/core/intercore" remote get-url origin) == "$INTERCORE_URL" ]] \
  || unverifiable "Intercore repository URL differs from reviewed origin"
[[ $(git -C "$BUILD_ROOT/core/intercore" cat-file -t "$INTERCORE_TAG") == commit ]] \
  || unverifiable "Intercore CI tag is not lightweight"
[[ $(git -C "$BUILD_ROOT/core/intercore" rev-parse "$INTERCORE_TAG^{commit}") == "$INTERCORE_SHA" ]] \
  || unverifiable "Intercore CI tag does not resolve to reviewed commit"
git -C "$BUILD_ROOT/core/intercore" checkout --detach "$INTERCORE_SHA"
git -C "$BUILD_ROOT/core/intercore" cat-file -e "$INTERCORE_SHA^{commit}"
[[ $(git -C "$BUILD_ROOT/core/intercore" rev-parse HEAD) == "$INTERCORE_SHA" ]] || unverifiable "Intercore checkout has wrong HEAD"
[[ -z $(git -C "$BUILD_ROOT/core/intercore" status --porcelain=v1 --untracked-files=all) ]] || unverifiable "Intercore checkout is not clean"
(
  cd "$BUILD_ROOT/core/intercore"
  go build -trimpath -buildvcs=true -o "$tools_root/bin/ic" ./cmd/ic
)
# Even identity probes receive a DB below their physical cwd.
mkdir -m 700 "$runtime_root/identity"
(cd "$runtime_root/identity" && ic --db="$runtime_root/identity/intercore.db" init)
ic_version=$(cd "$runtime_root/identity" && ic --db="$runtime_root/identity/intercore.db" version)
[[ "$ic_version" == *'ic 0.3.5'* && "$ic_version" == *"commit: ${INTERCORE_SHA:0:12}"* && "$ic_version" != *dirty* ]] \
  || unverifiable "built Intercore identity does not match reviewed source"

cd "$BUILD_ROOT/os/Clavain"
mkdir -m 700 .native-ci-identity
ic --db="$PWD/.native-ci-identity/intercore.db" init
printf '%s  %s\n' "$USAGE_MANIFEST_SHA256" tests/usage-pilot.json | sha256sum --check - \
  || unverifiable "usage verification contract differs from pinned recipe"

# The manifest freezes native operation and GNU awk coverage together with the
# legacy pilot. Registration binds this recipe only after final source review.

python3 - "$evidence_root/bootstrap-provenance.json" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()

tools = {}
for name in ("bash", "bats", "curl", "gawk", "awk", "gcc", "git", "go", "ic", "jq", "make", "python3", "sha256sum", "shasum", "tar", "xz"):
    path = Path(shutil.which(name)).resolve()
    tools[name] = {"path": str(path), "sha256": digest(path)}
root = Path("/workspace/build/core/intercore")
data = {
    "schema": 1,
    "expected_image_sha256": "698d1b22ad393190d3d4d2339439fd6bb2ecdb3f6651320049351f4283c156b6",
    "source_sha": os.environ["CI_SOURCE_SHA"],
    "native_schema_generator": {"path": os.environ["NATIVE_TEST_CODEX"], "sha256": os.environ["NATIVE_TEST_CODEX_SHA256"],
        "archive_sha256": "d7e18b2597ae8f242f5f31ee9e90deef48dbc9edd634d9868fb6435d08c07f02", "archive_size": 98981886},
    "intercore": {
        "repository_url": subprocess.check_output(["git", "-C", str(root), "remote", "get-url", "origin"], text=True).strip(),
        "commit": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
        "tree": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True).strip(),
        "tag": "refs/tags/ci/9bc85a3bbf81c135a2784677676dac2487ddd02a",
    },
    "contracts": {
        "tests/usage-pilot.json": digest("tests/usage-pilot.json"),
        "scripts/ci-usage-evidence.py": digest("scripts/ci-usage-evidence.py"),
        "scripts/ci-verification.sh": digest("scripts/ci-verification.sh"),
        "tests/verification-pilot.json": digest("tests/verification-pilot.json"),
    },
    "archives": {
        "go1.26.4.linux-amd64.tar.gz": "1153d3d50e0ac764b447adfe05c2bcf08e889d42a02e0fe0259bd47f6733ad7f",
        "gawk-5.3.1.tar.xz": "694db764812a6236423d4ff40ceb7b6c4c441301b72ad502bb5c27e00cd56f78",
        "bats-core-v1.12.0.tar.gz": "e36b020436228262731e3319ed013d84fcd7c4bd97a1b34dee33d170e9ae6bab",
        "interstat-2dd2bac412288b7aead853a1e43abf9c40496ee5.tar.gz": "41bc1a92e1279aab479418a8937489de56558d0402cc25b21dcc570b7e5ef1cf",
    },
    "interstat_files": {
        "scripts/profile.py": digest("/workspace/build/interverse/interstat/scripts/profile.py"),
        "scripts/claude_usage.py": digest("/workspace/build/interverse/interstat/scripts/claude_usage.py"),
        "scripts/cost.py": digest("/workspace/build/interverse/interstat/scripts/cost.py"),
    },
    "executables": tools,
}
output = Path(sys.argv[1])
fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, "w") as stream:
    json.dump(data, stream, sort_keys=True, separators=(",", ":"))
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY

legacy_status=0
env -i \
  HOME="$legacy_runtime_root/home" TMPDIR="$legacy_runtime_root/tmp" LANG=C LC_ALL=C TZ=UTC \
  PATH="$PATH" GOTOOLCHAIN=local PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PYTHONPATH" NATIVE_TEST_CODEX="$NATIVE_TEST_CODEX" NATIVE_TEST_CODEX_SHA256="$NATIVE_TEST_CODEX_SHA256" \
  CI_SOURCE_SHA="$CI_SOURCE_SHA" \
  bash scripts/ci-verification.sh \
    > "$evidence_root/legacy-verification.stdout" \
    2> "$evidence_root/legacy-verification.stderr" || legacy_status=$?
python3 - "$evidence_root/legacy-verification-status.json" "$legacy_status" <<'PY'
import json
import os
from pathlib import Path
import sys

output = Path(sys.argv[1])
payload = {"schema": 1, "exit_status": int(sys.argv[2])}
fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, "w") as stream:
    json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY

status=0
env -i \
  HOME="$runtime_root/home" TMPDIR="$runtime_root/tmp" LANG=C LC_ALL=C TZ=UTC \
  PATH="$PATH" GOTOOLCHAIN=local PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PYTHONPATH" NATIVE_TEST_CODEX="$NATIVE_TEST_CODEX" NATIVE_TEST_CODEX_SHA256="$NATIVE_TEST_CODEX_SHA256" \
  CI_SOURCE_SHA="$CI_SOURCE_SHA" \
  LEGACY_VERIFY_TMPDIR="$legacy_runtime_root/tmp" \
  LEGACY_VERIFY_MARKER="$legacy_marker" \
  LEGACY_VERIFY_LOG="$evidence_root/legacy-verification.stdout" \
  python3 scripts/verification_runner.py \
    --spec tests/usage-pilot.json --project-dir "$PWD" \
    --evidence-dir "$evidence_root" --run-id "$CI_SOURCE_SHA" \
    --task-id usage-pilot > "$evidence_root/step.json" || status=$?
cat "$evidence_root/step.json"

export_status=0
python3 - "$evidence_root" <<'PY' || export_status=$?
import base64
import hashlib
from pathlib import Path
import sys
import tarfile
import tempfile

root = Path(sys.argv[1])
with tempfile.TemporaryFile() as archive:
    with tarfile.open(fileobj=archive, mode="w:gz") as bundle:
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise SystemExit("unsafe evidence export entry")
            bundle.add(path, arcname=str(path.relative_to(root)), recursive=False)
    if archive.tell() > 32 * 1024 * 1024:
        raise SystemExit("evidence export exceeds 32 MiB compressed limit")
    archive.seek(0)
    digest = hashlib.sha256()
    while chunk := archive.read(1024 * 1024):
        digest.update(chunk)
    archive.seek(0)
    print("BEGIN_USAGE_EVIDENCE_TGZ_BASE64 sha256=" + digest.hexdigest(), flush=True)
    base64.encode(archive, sys.stdout.buffer)
    print("END_USAGE_EVIDENCE_TGZ_BASE64", flush=True)
PY
if (( export_status != 0 )); then
  echo "UNVERIFIABLE: usage evidence export failed (exit $export_status)" >&2
fi
if (( legacy_status != 0 )); then
  exit "$legacy_status"
fi
if (( status != 0 )); then
  exit "$status"
fi
if (( export_status != 0 )); then
  exit 2
fi
exit 0
