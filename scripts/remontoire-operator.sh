#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: remontoire-operator.sh <operation> [arguments]

operations:
  doctor
  status [cycle-id]
  attention
  shadow
  proposal
  inspect <cycle-id>
  approve <cycle-id> --actor=<principal>
  decline <cycle-id> --actor=<principal> --reason=<text>
  resume <cycle-id>
  receipt <show|replay> <cycle-id>

Set REMONTOIRE_HOST=local to use the local runtime. Otherwise the adapter uses
zklw, except when already running on zklw.
EOF
  exit 2
}

[[ $# -gt 0 ]] || usage
operation="$1"
shift

runtime_args=()
case "$operation" in
  doctor)
    [[ $# -eq 0 ]] || usage
    runtime_args=(doctor)
    ;;
  status)
    [[ $# -le 1 ]] || usage
    runtime_args=(status "$@")
    ;;
  attention)
    [[ $# -eq 0 ]] || usage
    runtime_args=(attention)
    ;;
  shadow)
    [[ $# -eq 0 ]] || usage
    runtime_args=(cycle --mode=shadow)
    ;;
  proposal)
    [[ $# -eq 0 ]] || usage
    runtime_args=(cycle --mode=proposal)
    ;;
  inspect)
    [[ $# -eq 1 && "$1" != -* ]] || usage
    runtime_args=(status "$1")
    ;;
  approve)
    [[ $# -ge 2 && "$1" != -* ]] || usage
    runtime_args=(approve "$@")
    ;;
  decline)
    [[ $# -ge 3 && "$1" != -* ]] || usage
    runtime_args=(decline "$@")
    ;;
  resume)
    [[ $# -eq 1 && "$1" != -* ]] || usage
    runtime_args=(resume "$1")
    ;;
  receipt)
    [[ $# -eq 2 && ("$1" == "show" || "$1" == "replay") && "$2" != -* ]] || usage
    runtime_args=(receipt "$1" "$2")
    ;;
  *)
    usage
    ;;
esac

has_json=0
for arg in "${runtime_args[@]}"; do
  [[ "$arg" == "--json" ]] && has_json=1
done
[[ "$has_json" -eq 1 ]] || runtime_args+=(--json)

host="${REMONTOIRE_HOST:-}"
if [[ -z "$host" ]]; then
  local_hostname="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
  if [[ "$local_hostname" == "zklw" ]]; then
    host="local"
  else
    host="zklw"
  fi
fi

if [[ "$host" == "local" ]]; then
  binary="${REMONTOIRE_BINARY:-}"
  if [[ -z "$binary" ]]; then
    binary="$(command -v remontoire 2>/dev/null || true)"
  fi
  [[ -n "$binary" ]] || binary="$HOME/.local/bin/remontoire"
  if [[ ! -x "$binary" ]]; then
    echo "remontoire-operator: runtime not installed: $binary" >&2
    exit 127
  fi
  exec "$binary" "${runtime_args[@]}"
fi

if [[ ! "$host" =~ ^[A-Za-z0-9._-]+(@[A-Za-z0-9._-]+)?$ ]]; then
  echo "remontoire-operator: invalid SSH host: $host" >&2
  exit 2
fi

ssh_binary="${REMONTOIRE_SSH_BINARY:-ssh}"
connect_timeout="${REMONTOIRE_CONNECT_TIMEOUT:-10}"
[[ "$connect_timeout" =~ ^[0-9]+$ ]] || {
  echo "remontoire-operator: REMONTOIRE_CONNECT_TIMEOUT must be an integer" >&2
  exit 2
}

remote_binary="${REMONTOIRE_REMOTE_BINARY:-remontoire}"
printf -v quoted_binary '%q' "$remote_binary"
remote_command="PATH=\"\$HOME/.local/bin:\$PATH\" exec ${quoted_binary}"
for arg in "${runtime_args[@]}"; do
  printf -v quoted_arg '%q' "$arg"
  remote_command+=" ${quoted_arg}"
done

exec "$ssh_binary" \
  -o BatchMode=yes \
  -o "ConnectTimeout=$connect_timeout" \
  "$host" \
  "$remote_command"
