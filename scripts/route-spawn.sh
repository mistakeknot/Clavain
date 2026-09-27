#!/usr/bin/env bash
# route-spawn.sh — resolve a bb spawn tuple and retain its routing receipt.
# Usage: route-spawn.sh --role <role> [--project <slug|bb-project-id>]
#          [--lineage <coordinatorId>] [--producer-identity <id>]
#          [--context-file <json>]
# Stdout: exactly <bb-provider> <model> <reasoning-level> on success.
# Exit codes: 0 success, 2 usage error, 3 resolution or receipt failure.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
POLICY="${CLAVAIN_ROUTING_POLICY:-$ROOT/config/routing.yaml}"
ROLE=""
PROJECT=""
LINEAGE=""
PRODUCER=""
CONTEXT="${CLAVAIN_DECISION_CONTEXT:-}"

usage_error() { echo "route-spawn: $*" >&2; exit 2; }
resolution_error() { echo "route-spawn: $*" >&2; exit 3; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role|--project|--lineage|--producer-identity|--context-file)
      [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || usage_error "$1 requires a value"
      case "$1" in
        --role) ROLE="$2" ;;
        --project) PROJECT="$2" ;;
        --lineage) LINEAGE="$2" ;;
        --producer-identity) PRODUCER="$2" ;;
        --context-file) CONTEXT="$2" ;;
      esac
      shift 2
      ;;
    *) usage_error "unknown argument: $1" ;;
  esac
done

[[ -n "$ROLE" ]] || usage_error "--role is required"
case "$ROLE" in
  coordination) [[ -n "$PROJECT" ]] || usage_error "coordination requires --project" ;;
  lane) [[ -n "$LINEAGE" ]] || usage_error "lane requires --lineage" ;;
  plan-review|validation|cross-lab-review)
    [[ -n "$PRODUCER" ]] || usage_error "$ROLE requires --producer-identity" ;;
esac

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
python3 - "$POLICY" "$ROLE" "$PROJECT" "$LINEAGE" "$PRODUCER" "$CONTEXT" "$ARM" "$TMP_ROOT" "$$" "$ROOT" <<'PY' || { rc=$?; [[ "$rc" == 2 ]] && exit 2; exit 3; }
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml


def fail(message, code=3):
    print(f"route-spawn: {message}", file=sys.stderr)
    sys.exit(code)


def main():
    policy, role, project_input, lineage, producer, context_file, arm, tmp, pid, root = sys.argv[1:]
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
    slug = aliases.get(project_input, project_input)
    project = slug if slug in known else None
    if role == "coordination" and project is None:
        fail(f"unknown coordination project: {project_input}; pass a known slug", 2)
    if project_input and project is None:
        print(f"route-spawn: unknown project: {project_input}; using fleet routing", file=sys.stderr)

    # Decide the profile before changing the decision context's scope.
    project_profile = project_profiles.get(project)
    profiles = reasoning.get("profiles") or {}
    applicable = role in (profiles.get(project_profile, {}).get("roles") or {})
    profile = None
    profile_source = "none"
    campaign_profile = os.environ.get("CLAVAIN_POLICY_PROFILE")
    if campaign_profile and campaign_profile != "default":
        if role == "coordination" and applicable:
            fail("campaign profile conflicts with the project coordination profile")
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
    if role in ("lane", "coordination", "main-session"):
        try:
            probe = subprocess.run(["bb", "pool", "status", "--json"],
                                   stdout=subprocess.PIPE, text=True, check=True,
                                   timeout=float(os.environ.get("ROUTE_SPAWN_POOL_TIMEOUT", "20")))
            pool = json.loads(probe.stdout)
            if pool.get("accepting") is not True:
                raise ValueError("pool is not accepting")
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
            for tier in (dispatch.get("tiers") or {}).values():
                backend = tier.get("backend")
                model = tier.get("model")
                if backend not in ("claude", "codex") or backend not in up or not model:
                    continue
                model = model_aliases.get(model, model)
                family = (families.get(model) or {}).get("family")
                if backend == "claude" and family and all(
                    ((a.get("familyWeekly") or {}).get(family) or {}).get("status") == "rejected"
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
    resolved = subprocess.run(command, stdout=subprocess.PIPE, text=True, check=True,
                              timeout=float(os.environ.get("ROUTE_SPAWN_IC_TIMEOUT", "30")))
    route = json.loads(resolved.stdout)
    seat = route["profile"]
    model = seat["model_identity"]
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
    if route.get("fallback_reason") or chosen != head:
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
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=receipt_dir,
                                         prefix=".route-spawn-", delete=False) as stream:
            pending = Path(stream.name)
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
        # Same-directory rename is atomic, just like temp file + mv.
        os.replace(pending, destination)
    finally:
        if pending is not None and pending.exists():
            pending.unlink()
    print(f"{provider} {model} {effort}")


try:
    main()
except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError,
        subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
    fail(str(error))
PY
