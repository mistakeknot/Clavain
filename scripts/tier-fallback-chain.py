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
  {"tier": <name>, "backend": ..., "model": ..., "reasoning_effort": ...,
   "service_tier": ..., "minimum_codex_version": ...}

Cycles and repeats are silently deduped (first occurrence wins), matching
`ic route dispatch --role=...`'s observed behavior.
"""
import argparse
import json
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - pyyaml is a repo-wide dependency
    print("tier-fallback-chain: pyyaml is required", file=sys.stderr)
    sys.exit(1)


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
        if name in seen:
            continue
        seen.add(name)
        tier = tiers.get(name)
        if tier is None:
            if name == args.tier:
                print(f"tier-fallback-chain: unknown tier '{name}'", file=sys.stderr)
                return 1
            continue
        chain.append({
            "tier": name,
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
