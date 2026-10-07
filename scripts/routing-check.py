#!/usr/bin/env python3
"""Read-only audit of dispatch pins and normalized BB seats/receipts.

See units/README.md for the input contract and scheduling templates.
Only --file-beads enables a write, through bd; policy and seats are never edited.
Exit codes: 0 clean/consider/unknown (non-strict), 1 drift, 2 invalid input,
3 UNKNOWN seat evidence under --strict.
"""
import argparse
import fnmatch
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import yaml

EFFORTS = {name: rank for rank, name in enumerate(
    ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"))}
DEFAULT_RETIRED = ["gpt-6", "gpt-6-sol", "gpt-5.6-sol", "claude-sonnet-5", "sonnet-5"]


def mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def strings(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return [string(item, label) for item in value]


def effort(value):
    if not isinstance(value, str) or value not in EFFORTS:
        raise ValueError(f"unknown reasoning_effort: {value!r}")
    return value


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Policy:
    def __init__(self, path):
        raw = mapping(yaml.safe_load(Path(path).read_text(encoding="utf-8")), "routing")
        self.raw = raw
        dispatch = mapping(raw.get("dispatch"), "dispatch")
        self.aliases = mapping(dispatch.get("model_aliases", {}), "model_aliases")
        self.roles = mapping(dispatch.get("roles"), "dispatch.roles")
        self.tiers = mapping(dispatch.get("tiers"), "dispatch.tiers")
        if not self.roles or not self.tiers:
            raise ValueError("roles and tiers must not be empty")
        for alias, model in self.aliases.items():
            string(alias, "alias")
            self.canonical(string(model, "alias model"))
        for name, tier in self.tiers.items():
            string(name, "tier name")
            mapping(tier, name)
            self.canonical(string(tier.get("model"), f"{name}.model"))
            effort(tier.get("reasoning_effort"))
            for fallback in strings(tier.get("fallbacks", []), f"{name}.fallbacks"):
                self.reference(fallback)
        self.validate_roles(self.roles)
        reasoning = mapping(raw.get("reasoning", {}), "reasoning")
        self.profiles = mapping(reasoning.get("profiles", {}), "reasoning.profiles")
        for name, profile in self.profiles.items():
            string(name, "policy profile")
            self.validate_roles(mapping(mapping(profile, name).get("roles"), f"{name}.roles"))
        # Real schema (see route-spawn.sh): project slug -> profile name, where the
        # named reasoning profile carries scope "project:<slug>" and the role overrides.
        project_profiles = mapping(reasoning.get("project_profiles") or {}, "project_profiles")
        listed = reasoning.get("projects")
        self.known_projects = set(strings(listed, "reasoning.projects")) if listed is not None else set()
        self.project_roles = {}
        for slug, profile_name in project_profiles.items():
            string(slug, "project")
            if listed is not None and slug not in self.known_projects:
                raise ValueError(f"project_profiles.{slug} must belong to reasoning.projects")
            if not isinstance(profile_name, str) or profile_name not in self.profiles:
                raise ValueError(f"project_profiles.{slug} must name an existing reasoning profile")
            if self.profiles[profile_name].get("scope") != f"project:{slug}":
                raise ValueError(f"project profile {profile_name} must have scope project:{slug}")
            self.project_roles[slug] = self.profiles[profile_name]["roles"]
        self.known_projects |= set(self.project_roles)

    def canonical(self, model):
        seen = set()
        while model in self.aliases:
            if model in seen:
                raise ValueError(f"model alias cycle at {model}")
            seen.add(model)
            model = string(self.aliases[model], "alias model")
        return model

    def reference(self, name):
        if name not in self.tiers:
            raise ValueError(f"unknown tier: {name}")

    def validate_roles(self, roles):
        for role, name in roles.items():
            string(role, "role")
            self.reference(string(name, f"{role} tier"))

    def chain(self, head):
        # Cyclic capacity chains are intentional in the real table. Visit once.
        seen = set()
        pending = [head]
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            pending.extend(self.tiers[name].get("fallbacks", []))
        return seen

    def candidates(self, role, profile="default", project=None):
        if role not in self.roles:
            raise ValueError(f"unknown role: {role}")
        head = self.roles[role]
        if profile != "default":
            if profile not in self.profiles:
                raise ValueError(f"unknown policy_profile: {profile}")
            head = self.profiles[profile]["roles"].get(role, head)
        if project is not None:
            if project not in self.known_projects:
                raise ValueError(f"unknown project: {project}")
            head = self.project_roles.get(project, {}).get(role, head)
        return self.chain(head)

    def model_strings(self):
        """Find model IDs and aliases in string leaves, independent of key names."""
        found = []
        model_id = re.compile(r"(?:gpt-|claude-)[A-Za-z0-9_.-]+|(?:sonnet|opus|haiku)(?:-[A-Za-z0-9_.-]+)?")

        def walk(node, path):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, path + [str(key)])
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, path + [str(index)])
            elif isinstance(node, str) and (node in self.aliases or model_id.fullmatch(node)):
                found.append((".".join(path), node))

        walk(self.raw, [])
        return found


def released_models(path):
    raw = mapping(read_json(path), "released models")
    items = raw.get("models")
    if not isinstance(items, list) or not items:
        raise ValueError("released models.models must be a nonempty array")
    models = {}
    for item in items:
        item = mapping(item, "released model")
        name = string(item.get("id"), "model.id")
        if name in models:
            raise ValueError(f"duplicate released model: {name}")
        models[name] = strings(item.get("better_than", []), "better_than")
    return models


def seat_records(path):
    raw = mapping(read_json(path), "seat records")
    if not isinstance(raw.get("seats"), list):
        raise ValueError("seat records.seats must be an array (empty is allowed)")
    records = []
    for source in ("seats", "receipts"):
        items = raw.get(source, [])
        if not isinstance(items, list):
            raise ValueError(f"{source} must be an array")
        for index, item in enumerate(items):
            item = mapping(item, f"{source}[{index}]")
            for field in ("role", "model"):
                string(item.get(field), f"{source}[{index}].{field}")
            effort(item.get("reasoning_effort"))
            for field in ("thread", "profile_ref", "policy_profile", "project"):
                if field in item:
                    string(item[field], field)
            records.append((f"{source}[{index}]", item))
    return records


def execution_candidates(policy, role, execution, retired):
    """Bind supplied execution arguments and profile metadata to one policy tier."""
    route = mapping(json.loads(string(execution.get("route_json"), "resolved route JSON")), "resolved route")
    candidates = policy.candidates(role, route.get("policy_profile", "default"), route.get("project"))
    supplied = (mapping(json.loads(execution["profile_json"]), "resolved candidate")
                if execution.get("profile_json") else route)
    refs = [execution.get("profile_ref"), supplied.get("profile_ref")]
    for ref in refs:
        if ref:
            string(ref, "execution profile_ref")
            candidates &= {ref}
    profile = mapping(supplied.get("profile", {}), "execution profile")
    if "role" in profile and profile["role"] != role:
        raise ValueError("execution profile role conflicts with decision role")
    model = policy.canonical(string(execution.get("model"), "execution model"))
    for field in ("model", "model_identity"):
        if field in profile:
            spelling = string(profile[field], field)
            if any(fnmatch.fnmatchcase(spelling, p) for p in retired):
                raise ValueError(f"execution profile {field} uses retired alias {spelling}")
            if policy.canonical(spelling) != model:
                raise ValueError(f"execution profile {field} conflicts with supplied model")
    constraints = {"model": model}
    for field in ("reasoning_effort", "backend"):
        actual = execution.get(field)
        declared = profile.get(field)
        if declared is not None:
            string(declared, f"execution profile {field}")
            if actual and actual != declared:
                raise ValueError(f"execution profile {field} conflicts with supplied execution")
        if actual or declared:
            constraints[field] = actual or declared
    if "reasoning_effort" in constraints:
        effort(constraints["reasoning_effort"])
    backend = "claude" if model.startswith("claude-") else "codex"
    return {name for name in candidates if all(
        (policy.canonical(policy.tiers[name][field]) if field == "model" else
         policy.tiers[name].get(field, backend if field == "backend" else None)) == value
        for field, value in constraints.items())}


def audit(policy, models, records, retired, role=None, execution=None):
    findings = []

    def add(kind, subject, detail):
        findings.append({"kind": kind, "severity": "consider" if kind == "consider" else "error",
                         "subject": subject, "detail": detail})

    selected = set(policy.tiers) if role is None else policy.candidates(role)
    if role is not None:
        # Include configured role overrides in the cheap role-specific scan.
        for profile in policy.profiles.values():
            if role in profile["roles"]:
                selected.update(policy.chain(profile["roles"][role]))
        for overrides in policy.project_roles.values():
            if role in overrides:
                selected.update(policy.chain(overrides[role]))

    def check_model(model, subject):
        if any(fnmatch.fnmatchcase(model, pattern) for pattern in retired):
            add("retired-pin", subject, f"retired model {model}")
        if model not in models:
            add("unreleased-model", subject, f"model {model} is absent from released list")

    def check_alias(spelling, model, subject):
        if spelling != model and any(fnmatch.fnmatchcase(spelling, p) for p in retired):
            add("retired-pin", subject, f"retired alias {spelling}")

    # These are the model override variables consumed by dispatch.sh's Claude
    # tier resolver. Audit them even on role-scoped checks; empty means default.
    for variable in ("CLAVAIN_CLAUDE_MODEL_FAST", "CLAVAIN_CLAUDE_MODEL_DEEP"):
        spelling = os.environ.get(variable)
        if spelling:
            model = policy.canonical(spelling)
            check_alias(spelling, model, f"env:{variable}")
            check_model(model, f"env:{variable}")

    if execution is not None:
        if role is None:
            raise ValueError("execution validation requires --precheck ROLE")
        spelling = string(execution.get("model"), "execution model")
        check_model(policy.canonical(spelling), "execution:model")
        check_alias(spelling, policy.canonical(spelling), "execution:model")
        if not execution_candidates(policy, role, execution, retired):
            add("execution-drift", "execution:profile", "supplied execution does not match a policy candidate for the role")

    if role is None:
        for alias in sorted(policy.aliases):
            model = policy.canonical(alias)
            check_model(model, f"alias:{alias}")
            check_alias(alias, model, f"alias:{alias}")

        for path, value in policy.model_strings():
            model = policy.canonical(value)
            subject = f"policy:{path}"
            check_alias(value, model, subject)
            if any(fnmatch.fnmatchcase(model, pattern) for pattern in retired):
                add("retired-pin", subject, f"retired model {model}")

    for name in sorted(selected):
        tier = policy.tiers[name]
        # Check both alias spelling and canonical destination for retired pins.
        model = policy.canonical(tier["model"])
        check_model(model, f"tier:{name}")
        check_alias(tier["model"], model, f"tier:{name}")

    for source, seat in records:
        if role is not None and seat["role"] != role:
            continue
        subject = f"{source}:{seat.get('thread', 'receipt')}:{seat['role']}"
        model = policy.canonical(seat["model"])
        check_model(model, subject)
        check_alias(seat["model"], model, subject)
        try:
            candidates = policy.candidates(seat["role"], seat.get("policy_profile", "default"),
                                           seat.get("project"))
        except ValueError as exc:
            add("seat-drift", subject, str(exc))
            continue
        if "profile_ref" in seat:
            if seat["profile_ref"] not in candidates:
                add("seat-drift", subject, f"profile {seat['profile_ref']} is not in role chain")
                continue
            candidates = {seat["profile_ref"]}
        matching = [policy.tiers[name] for name in candidates
                    if policy.canonical(policy.tiers[name]["model"]) == model]
        expected = sorted({tier["reasoning_effort"] for tier in matching}, key=EFFORTS.get)
        actual = seat["reasoning_effort"]
        if expected and EFFORTS[actual] > max(EFFORTS[e] for e in expected):
            add("over-cap", subject, f"{model} effort {actual} exceeds cap {expected[-1]}")
        elif actual not in expected:
            add("seat-drift", subject, f"{model}/{actual} does not match role table; efforts {expected}")
        for newer, better_than in sorted(models.items()):
            # Only explicit source evidence supports a quality comparison.
            if newer != model and model in better_than and not any(
                    fnmatch.fnmatchcase(newer, pattern) for pattern in retired):
                add("consider", subject, f"consider released {newer} over {model}; mk decides")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routing", default=str(Path(__file__).resolve().parents[1] / "config/routing.yaml"))
    parser.add_argument("--released-models", required=True)
    parser.add_argument("--seats", required=True)
    parser.add_argument("--retired-models", help="JSON array of retired model globs; replaces default list")
    parser.add_argument("--precheck", metavar="ROLE", help="scan only this role and its seats; no model/network calls")
    parser.add_argument("--strict", action="store_true",
                        help="exit 3 when seat evidence is UNKNOWN (empty or none for the prechecked role)")
    parser.add_argument("--execution-json", help="supplied resolved execution arguments to validate against the role")
    parser.add_argument("--file-beads", action="store_true", help="execute printed bd commands (default: dry-run)")
    args = parser.parse_args(argv)
    result = {"status": "error", "findings": [], "unknown": [], "bead_commands": [],
              "dry_run": not args.file_beads}
    code = 2
    try:
        policy = Policy(args.routing)
        models = released_models(args.released_models)
        records = seat_records(args.seats)
        retired = DEFAULT_RETIRED if args.retired_models is None else strings(
            read_json(args.retired_models), "retired models")
        execution = mapping(json.loads(args.execution_json), "execution") if args.execution_json else None
        result["findings"] = audit(policy, models, records, retired, args.precheck, execution)
        relevant = [r for _, r in records if args.precheck is None or r["role"] == args.precheck]
        result["evidence"] = {"seats": sum(s.startswith("seats[") for s, _ in records),
                              "receipts": sum(s.startswith("receipts[") for s, _ in records),
                              "matched": len(relevant)}
        if not relevant:
            scope = f"role {args.precheck}" if args.precheck else "the fleet"
            result["unknown"].append(
                f"no seat or receipt evidence for {scope}; absence of evidence is not a clean pass")
        drift = any(f["severity"] == "error" for f in result["findings"])
        code = 1 if drift else 3 if result["unknown"] and args.strict else 0
        result["status"] = ("drift" if drift else "unknown" if result["unknown"]
                            else "consider" if result["findings"] else "clean")
        for finding in result["findings"]:
            command = ["bd", "--actor", "clavain-coord", "create", "--type", "task",
                       "--title", f"routing-check {finding['kind']}: {finding['subject']}",
                       "--description", finding["detail"]]
            result["bead_commands"].append(command)
        result["printed_commands"] = [shlex.join(c) for c in result["bead_commands"]]
        if args.file_beads:
            for command in result["bead_commands"]:
                subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
    except (OSError, ValueError, yaml.YAMLError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
        code = 2
    result["exit_code"] = code
    print(json.dumps(result, indent=2))
    if result["unknown"]:
        print("routing-check: UNKNOWN: " + "; ".join(result["unknown"]), file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
