#!/usr/bin/env bash
# route-spawn.sh — resolve a bb spawn tuple and retain its routing receipt.
# Usage: route-spawn.sh --role <role> [--project <slug|bb-project-id>]
#          [--lineage <coordinatorId>] [--producer-identity <id>]
#          [--context-file <json>] [--seat-out <file>]
# Stdout: exactly <bb-provider> <model> <reasoning-level> on success.
# --seat-out writes the seat tuple, role, profile, policy hash and receipt path
# as JSON, on success only.
# Exit codes: 0 success, 2 usage error, 3 resolution or receipt failure.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
POLICY="${CLAVAIN_ROUTING_POLICY:-$ROOT/config/routing.yaml}"
ROLE=""
PROJECT=""
LINEAGE=""
PRODUCER=""
CONTEXT="${CLAVAIN_DECISION_CONTEXT:-}"
SEAT_OUT=""

usage_error() { echo "route-spawn: $*" >&2; exit 2; }
resolution_error() { echo "route-spawn: $*" >&2; exit 3; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role|--project|--lineage|--producer-identity|--context-file|--seat-out)
      [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || usage_error "$1 requires a value"
      case "$1" in
        --role) ROLE="$2" ;;
        --project) PROJECT="$2" ;;
        --lineage) LINEAGE="$2" ;;
        --producer-identity) PRODUCER="$2" ;;
        --context-file) CONTEXT="$2" ;;
        --seat-out) SEAT_OUT="$2" ;;
      esac
      shift 2
      ;;
    *) usage_error "unknown argument: $1" ;;
  esac
done

[[ -n "$ROLE" ]] || usage_error "--role is required"
case "$ROLE" in
  coordination) usage_error "coordinator threads resolve --role coordinator-seat; relay work uses dispatch.sh" ;;
  coordinator-seat) [[ -n "$PROJECT" ]] || usage_error "coordinator-seat requires --project" ;;
  lane) [[ -n "$LINEAGE" ]] || usage_error "lane requires --lineage" ;;
  plan-review|validation|cross-lab-review)
    [[ -n "$PRODUCER" ]] || usage_error "$ROLE requires --producer-identity" ;;
esac
if [[ -n "$SEAT_OUT" ]]; then
  seat_dir="$(dirname -- "$SEAT_OUT")"
  [[ -d "$seat_dir" && -w "$seat_dir" && ! -d "$SEAT_OUT" ]] ||
    usage_error "--seat-out needs a file in an existing writable directory: $SEAT_OUT"
fi

lane_arm() {
  # TODO(mk-42j9.25 Phase 2b): consult rollout state for the supplied lineage.
  # Until then, every lineage stays on the explicit status-quo control arm.
  echo control
}

ARM=""
if [[ "$ROLE" == lane ]]; then
  ARM="$(lane_arm "$LINEAGE")" || resolution_error "cannot resolve lane arm"
fi

TMP_ROOT="$(mktemp -d)" || resolution_error "cannot create temporary directory"
trap 'rm -rf "$TMP_ROOT"' EXIT

# Keep structured policy/context handling together; only the final tuple may
# reach stdout. The caller's context is read once and never written back.
python3 - "$POLICY" "$ROLE" "$PROJECT" "$LINEAGE" "$PRODUCER" "$CONTEXT" "$ARM" "$TMP_ROOT" "$$" "$ROOT" "$SEAT_OUT" <<'PY' || { rc=$?; [[ "$rc" == 2 ]] && exit 2; exit 3; }
import datetime
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

import yaml


def fail(message, code=3):
    print(f"route-spawn: {message}", file=sys.stderr)
    sys.exit(code)


def timeout_setting(name, default):
    try:
        value = float(os.environ.get(name, default))
    except ValueError:
        fail(f"{name} must be a finite number > 0", 2)
    if not math.isfinite(value) or value <= 0:
        fail(f"{name} must be a finite number > 0", 2)
    return value


def relay(stderr):
    if stderr:
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        sys.stderr.write(stderr)
        sys.stderr.flush()


def run_bounded(command, timeout):
    # Pipe stderr too, so no descendant inherits the caller's stderr; relay it.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # Kill the entire session group. A setsid descendant escapes it and can
        # still hold our pipes, so close them instead of draining.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.stdout.close()
        process.stderr.close()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        relay(exc.stderr)
        raise exc
    relay(stderr)
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command, stdout)
    return stdout


def write_pending(destination, text):
    # A temp file beside destination, so the later rename is atomic.
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".route-spawn-", delete=False) as stream:
            pending = Path(stream.name)
            stream.write(text + "\n")
    except BaseException:
        if pending is not None:
            pending.unlink(missing_ok=True)
        raise
    return pending


def replace_pending(pending, destination):
    # Same-directory rename is atomic, just like temp file + mv.
    try:
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)


def write_atomic(destination, text):
    replace_pending(write_pending(destination, text), destination)


SOL = "gpt-5.6-sol"


def is_sol(name, aliases):
    """Canonicalize a model name and report whether it is gpt-5.6-sol."""
    canonical = str(name).lower()
    seen = {canonical}
    while aliases.get(canonical, canonical) != canonical:
        canonical = aliases[canonical]
        if canonical in seen:
            fail(f"model_aliases cycle through {canonical} while checking {name} for {SOL}")
        seen.add(canonical)
    canonical = canonical.rsplit("/", 1)[-1]
    return canonical in (SOL, "gpt-5.6") or (
        canonical.startswith(SOL) and canonical[len(SOL):len(SOL) + 1] in ("-", "@", ":", "."))


def active_window(window, threshold, now_ms):
    if not window:
        return False
    reset_at = window.get("resetAt")
    utilization = window.get("utilization")
    return (reset_at is None or reset_at > now_ms) and (
        str(window.get("status", "")).lower() == "rejected"
        or (utilization is not None and utilization >= threshold)
    )


def main():
    policy, role, project_input, lineage, producer, context_file, arm, tmp, pid, root, seat_out = sys.argv[1:]
    pool_timeout = timeout_setting("ROUTE_SPAWN_POOL_TIMEOUT", "20")
    ic_timeout = timeout_setting("ROUTE_SPAWN_IC_TIMEOUT", "30")
    spawn_roles = ("lane", "coordinator-seat", "main-session")
    resolved_role = role
    if role == "lane":
        if arm == "control":
            resolved_role = "lane"
        else:
            fail(f"arm {arm} is Phase 2b")

    if context_file:
        try:
            with open(context_file, encoding="utf-8") as stream:
                context = json.load(stream)
        except (OSError, ValueError) as exc:
            fail(f"cannot read decision context: {exc}", 2)
    else:
        context = {"reasons": [], "rationale": f"route-spawn {role} for a bb thread spawn"}
    if not isinstance(context, dict):
        fail("decision context must be a JSON object", 2)

    with open(policy, encoding="utf-8") as stream:
        cfg = yaml.safe_load(stream)
    if not isinstance(cfg, dict):
        fail("routing policy must be a YAML mapping")

    reasoning = cfg.get("reasoning") or {}
    project_profiles = reasoning.get("project_profiles") or {}
    aliases = reasoning.get("project_aliases") or {}
    projects = reasoning.get("projects")
    if not isinstance(projects, list) or not all(isinstance(p, str) for p in projects):
        fail("reasoning.projects must be a list of slugs")
    known = set(projects)
    if not isinstance(project_profiles, dict) or not isinstance(aliases, dict):
        fail("project_profiles and project_aliases must be mappings")
    if any(p not in known for p in project_profiles) or any(p not in known for p in aliases.values()):
        fail("project_profiles keys and project_aliases values must belong to reasoning.projects")
    if any(alias in known for alias in aliases):
        fail("project_aliases keys must not be project slugs")
    profiles = reasoning.get("profiles") or {}
    if not isinstance(profiles, dict):
        fail("reasoning.profiles must be a mapping")
    for slug, profile_name in project_profiles.items():
        if not isinstance(profile_name, str) or profile_name not in profiles:
            fail(f"project_profiles.{slug} must name an existing reasoning profile")
        project_config = profiles[profile_name]
        if not isinstance(project_config, dict) or project_config.get("scope") != f"project:{slug}":
            fail(f"project profile {profile_name} must have scope project:{slug}")
        roles = project_config.get("roles")
        if not isinstance(roles, dict) or set(roles) != {"coordinator-seat"}:
            fail(f"project profile {profile_name} must override only coordinator-seat")
    slug = aliases.get(project_input, project_input)
    project = slug if slug in known else None
    if role == "coordinator-seat" and project is None:
        fail(f"unknown coordinator-seat project: {project_input}; pass a known slug", 2)
    if project_input and project is None:
        print(f"route-spawn: unknown project: {project_input}; using fleet routing", file=sys.stderr)

    # Decide the profile before changing the decision context's scope.
    project_profile = project_profiles.get(project)
    applicable = role in (profiles.get(project_profile, {}).get("roles") or {})
    profile = None
    profile_source = "none"
    campaign_profile = os.environ.get("CLAVAIN_POLICY_PROFILE")
    if campaign_profile and campaign_profile != "default":
        if role == "coordinator-seat" and applicable:
            fail("campaign profile conflicts with the project coordinator-seat profile")
        profile = campaign_profile
        profile_source = "campaign"
    elif applicable:
        profile = project_profile
        profile_source = "project"

    if profile_source == "project":
        scope = f"project:{project}"
        if context.get("scope") and context["scope"] != scope:
            fail(f"context scope conflicts with {scope}")
        context["scope"] = scope

    dispatch = cfg.get("dispatch") or {}
    model_aliases = dispatch.get("model_aliases") or {}
    caller_available = context.get("available_models")
    if caller_available is not None:
        if not isinstance(caller_available, list) or not all(isinstance(m, str) for m in caller_available):
            fail("available_models must be a list of model names or null", 2)
        caller_available = [model_aliases.get(m, m) for m in caller_available]
    context["available_models"] = caller_available

    fallbacks_evaluated = False
    # Governed roles leave capacity handling to dispatch.sh.
    if role in spawn_roles:
        try:
            deadline = time.monotonic() + pool_timeout
            pool = json.loads(run_bounded(["bb", "pool", "status", "--json"], pool_timeout))
            if pool.get("parent") is not None:
                raise ValueError("child host delegates pool routing to its parent")
            if pool.get("accepting") is not True:
                raise ValueError("pool is not accepting")
            threshold = 0.98
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired("bb pool config", pool_timeout)
                pool_config = json.loads(run_bounded(["bb", "pool", "config", "--json"], remaining))
                configured = pool_config["config"]["switchThreshold"]
                if type(configured) in (int, float) and 0 < configured <= 1:
                    threshold = configured
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
                    ValueError, KeyError, TypeError):
                pass  # bb's default applies when its config cannot be read.
            routing = pool.get("routing") or {}
            accounts = pool["accounts"]
            if not isinstance(accounts, list) or not all(isinstance(a, dict) for a in accounts):
                raise ValueError("pool accounts must be an array of objects")
            up_accounts = [a for a in accounts
                           if a.get("enabled") is True and a.get("status") in ("ready", "held")]
            up = {a.get("provider") for a in up_accounts}
            claude_accounts = [a for a in up_accounts if a.get("provider") == "claude"]
            with open(Path(root) / "config/roster-families.yaml", encoding="utf-8") as stream:
                families = (yaml.safe_load(stream) or {}).get("models") or {}
            available = []
            now_ms = time.time() * 1000
            for tier in (dispatch.get("tiers") or {}).values():
                backend = tier.get("backend")
                model = tier.get("model")
                if backend not in ("claude", "codex") or not model:
                    continue
                pooled = routing.get(backend) is not False
                if pooled and backend not in up:
                    continue
                model = model_aliases.get(model, model)
                family = (families.get(model) or {}).get("family")
                if pooled and backend == "claude" and family and all(
                    active_window((a.get("familyWeekly") or {}).get(family), threshold, now_ms)
                    for a in claude_accounts
                ):
                    continue
                if model not in available:
                    available.append(model)
            if caller_available is not None:
                available = [m for m in available if m in caller_available]
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
                ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
            print(f"route-spawn: pool unavailable; fallbacks not evaluated: {exc}", file=sys.stderr)
        else:
            context["available_models"] = available
            fallbacks_evaluated = True

    context_path = Path(tmp) / "context.json"
    context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
    command = ["ic", "--json", "route", "dispatch", f"--policy={policy}",
               f"--role={resolved_role}", f"--context-file={context_path}"]
    if profile is not None:
        command.append(f"--policy-profile={profile}")
    if producer:
        command.append(f"--producer-identity={producer}")
    route = json.loads(run_bounded(command, ic_timeout))
    seat = route["profile"]
    model = seat["model_identity"]
    sol_aliases = {str(k).lower(): str(v).lower() for k, v in model_aliases.items()}
    for name in (seat.get("model"), model):
        if name is not None and is_sol(name, sol_aliases):
            fail(f"{SOL} ({name}) is forbidden for every route-spawn role (mk ruling 2026-09-27)")
    effort = seat["reasoning_effort"]
    for label, value in (("model identity", model), ("reasoning effort", effort)):
        if not isinstance(value, str) or not value or any(c.isspace() for c in value):
            fail(f"resolver returned an invalid {label}")
    provider = {"claude": "claude-code", "codex": "codex"}.get(seat["backend"])
    if provider is None:
        fail(f"bb cannot spawn backend: {seat['backend']}")

    # ic receipts here omit the primary seat from fallback_chain; use the
    # policy's role head so a primary spawn is never called a fallback.
    head = (profiles.get(profile, {}).get("roles") or {}).get(resolved_role)
    head = head or (dispatch.get("roles") or {}).get(resolved_role)
    chosen = route["profile_ref"]
    fallback_reason = route.get("fallback_reason") or ""
    if "producer" in fallback_reason:
        print(f"route-spawn: {fallback_reason}; selected {chosen}", file=sys.stderr)
    elif fallback_reason or chosen != head:
        print(f"route-spawn: fallback from {head} to {chosen}", file=sys.stderr)

    receipt = {
        "schema": "clavain.route-spawn.v1",
        "role": role,
        "project_input": project_input or None,
        "project": project,
        "policy_profile": profile if profile is not None else "default",
        "profile_source": profile_source,
        "arm": arm or None,
        "lineage": lineage or None,
        "producer_identity": producer or None,
        "available_models": context.get("available_models"),
        "fallbacks_evaluated": fallbacks_evaluated,
        "policy_hash": route["policy_hash"],
        "spawn": {"provider": provider, "model": model, "reasoning_level": effort},
        "route": route,
    }
    state_home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    if not state_home.is_absolute():
        state_home = Path.home() / ".local/state"
    receipt_dir = Path(os.environ.get("ROUTE_SPAWN_RECEIPT_DIR") or state_home / "clavain/route-spawn")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    # Keep an untrusted role from introducing path separators in the filename.
    safe_role = "".join(c if c.isalnum() or c in "-_" else "_" for c in role)
    destination = receipt_dir / f"{stamp}-{safe_role}-{pid}.json"
    write_atomic(destination, json.dumps(receipt, indent=2))
    seat_path = Path(seat_out) if seat_out else None
    seat_pending = None
    if seat_path is not None:
        seat_pending = write_pending(seat_path, json.dumps({
            "provider": provider, "model": model, "reasoning_level": effort,
            "role": role, "profile_ref": chosen, "policy_profile": profile,
            "policy_hash": route["policy_hash"], "receipt": str(destination.absolute()),
        }))
    try:
        print(f"{provider} {model} {effort}", flush=True)
    except OSError:
        # The seat file changes only when the tuple reached stdout.
        if seat_pending is not None:
            seat_pending.unlink(missing_ok=True)
        raise
    if seat_pending is not None:
        # The tuple is already on stdout: a failed rename here exits 3 with a
        # printed tuple and no seat file. Accepted; the caller sees the exit.
        replace_pending(seat_pending, seat_path)


try:
    main()
except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError,
        subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
    fail(str(error))
PY
