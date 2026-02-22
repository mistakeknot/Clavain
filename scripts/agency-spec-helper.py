#!/usr/bin/env python3
"""Agency spec helper — YAML load/merge and JSON Schema validation.

Two subcommands:
  load <spec_path> [override_path]  — Read YAML, merge override, normalize budget, output JSON
  validate <spec_path> <schema_path> — Validate against JSON Schema, exit 0/1, errors to stderr

Called once per spec_load() in lib-spec.sh. All subsequent queries use jq on cached JSON.
"""
import json
import sys
import yaml


def deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base. Arrays replace, dicts merge recursively."""
    result = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def normalize_budget(spec: dict) -> dict:
    """Scale budget shares to sum to 100 if they don't. Warn on overallocation of min_tokens."""
    stages = spec.get("stages", {})
    if not stages:
        return spec

    total_share = sum(s.get("budget", {}).get("share", 0) for s in stages.values())
    if total_share > 0 and total_share != 100:
        print(f"spec: budget shares sum to {total_share}%, normalizing to 100%", file=sys.stderr)
        for stage in stages.values():
            budget = stage.get("budget", {})
            if "share" in budget:
                budget["share"] = round(budget["share"] * 100 / total_share)
        # Fix rounding: adjust largest stage to make sum exactly 100
        new_total = sum(s.get("budget", {}).get("share", 0) for s in stages.values())
        if new_total != 100:
            largest = max(stages.values(), key=lambda s: s.get("budget", {}).get("share", 0))
            largest["budget"]["share"] += 100 - new_total

    total_min = sum(s.get("budget", {}).get("min_tokens", 0) for s in stages.values())
    if total_min > 50000:
        print(f"spec: min_tokens sum ({total_min}) exceeds 50000 floor — stages may compete for budget", file=sys.stderr)

    return spec


def cmd_load(args: list[str]) -> int:
    if not args:
        print("Usage: load <spec_path> [override_path]", file=sys.stderr)
        return 1

    spec_path = args[0]
    override_path = args[1] if len(args) > 1 else None

    try:
        with open(spec_path) as f:
            spec = yaml.safe_load(f) or {}
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"spec: failed to load {spec_path}: {e}", file=sys.stderr)
        return 1

    if override_path:
        try:
            with open(override_path) as f:
                override = yaml.safe_load(f) or {}
            spec = deep_merge(spec, override)
        except FileNotFoundError:
            pass  # No override is fine
        except yaml.YAMLError as e:
            print(f"spec: failed to load override {override_path}: {e}", file=sys.stderr)
            # Continue with base spec

    spec = normalize_budget(spec)
    json.dump(spec, sys.stdout, separators=(",", ":"))
    return 0


def cmd_validate(args: list[str]) -> int:
    if len(args) < 2:
        print("Usage: validate <spec_path> <schema_path>", file=sys.stderr)
        return 1

    spec_path, schema_path = args[0], args[1]

    try:
        from jsonschema import validate, ValidationError
    except ImportError:
        print("spec: jsonschema not available, skipping validation", file=sys.stderr)
        return 0  # Degrade gracefully

    try:
        with open(spec_path) as f:
            spec = yaml.safe_load(f) or {}
        with open(schema_path) as f:
            schema = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, yaml.YAMLError) as e:
        print(f"spec: failed to read files: {e}", file=sys.stderr)
        return 1

    try:
        validate(instance=spec, schema=schema)
        return 0
    except ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path) or "(root)"
        print(f"spec: validation error at {path}: {e.message}", file=sys.stderr)
        return 1


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: agency-spec-helper.py <load|validate> [args...]", file=sys.stderr)
        return 1

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "load":
        return cmd_load(args)
    elif cmd == "validate":
        return cmd_validate(args)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
