#!/usr/bin/env python3
"""Resolve a `dispatch.tiers.<name>` entry plus its transitive, deduped
`fallbacks:` chain directly from routing.yaml.

Used by dispatch.sh's bare `--tier <name>` path, which is a separate
resolution surface from `--role` (`ic route dispatch --role=... ` walks role
fallback chains; `ic route dispatch --tier=...` only ever returns the single
named tier's model, ignoring any `fallbacks:` it declares). This helper lets
`--tier` dispatch retry through the same declared Claude/Codex fallback chain
on a quota_exhausted (or similar) failure class, without requiring an `ic`
change.

Output: a JSON array, primary tier first, each entry:
  {"tier": <name>, "role": ..., "backend": ..., "model": ..., "reasoning_effort": ...,
   "service_tier": ..., "minimum_codex_version": ...}

`role` lets the caller (dispatch.sh's _dispatch_tier_profile) grant a Claude
candidate the same write authority an execution role gets — routine-execution,
deep-execution and escalation may write when the sandbox is not read-only;
every other role (validation, scout, main-integrator, ...) stays read-only.

Cycles and repeats are silently deduped (first occurrence wins), matching
`ic route dispatch --role=...`'s observed behavior. A `fallbacks:` entry that
names a tier absent from dispatch.tiers, or that isn't a plain tier-name
string, fails loudly (exit 1) rather than being dropped silently — a typo'd
fallback should never look like "no fallback was configured".

Exit codes: 0 success, 1 unknown/malformed tier or fallback entry, 3 pyyaml
is not installed (a distinct code so the caller can degrade to its own
non-python resolution instead of failing dispatch outright).
"""
import argparse
import json
import sys

try:
    import yaml
except ImportError:  # pyyaml missing: let the caller degrade gracefully
    print("tier-fallback-chain: pyyaml is required", file=sys.stderr)
    sys.exit(3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--tier", required=True)
    args = parser.parse_args()

    with open(args.policy, encoding="utf-8") as fh:
        policy = yaml.safe_load(fh) or {}

    tiers = ((policy.get("dispatch") or {}).get("tiers")) or {}

    chain = []
    seen = set()
    queue = [args.tier]
    while queue:
        name = queue.pop(0)
        if not isinstance(name, str):
            print(f"tier-fallback-chain: malformed fallback entry (not a tier name): {name!r}", file=sys.stderr)
            return 1
        if name in seen:
            continue
        seen.add(name)
        tier = tiers.get(name)
        if tier is None:
            print(f"tier-fallback-chain: unknown tier '{name}'" + ("" if name == args.tier else f" (referenced from a fallbacks: list)"), file=sys.stderr)
            return 1
        chain.append({
            "tier": name,
            "role": tier.get("role"),
            "backend": tier.get("backend"),
            "model": tier.get("model"),
            "reasoning_effort": tier.get("reasoning_effort"),
            "service_tier": tier.get("service_tier"),
            "minimum_codex_version": tier.get("minimum_codex_version"),
        })
        queue.extend(tier.get("fallbacks") or [])

    print(json.dumps(chain))
    return 0


if __name__ == "__main__":
    sys.exit(main())
