#!/usr/bin/env python3
"""Regenerate the role-resolution golden for one or more routing policies.

    python3 tests/orchcompat/gen_golden.py [POLICY ...]   # role_resolution.json
    python3 tests/orchcompat/gen_golden.py --roster       # roster_config.json
    python3 tests/orchcompat/gen_golden.py --contract     # contract_render.json
    python3 tests/orchcompat/gen_golden.py --dispatch [POLICY ...]  # dispatch_dry_run.json

With no argument it uses this checkout's config/routing.yaml. Tables are keyed
by the policy's sha256, and existing keys for other policies are kept, so the
golden can carry the baseline policy and the current one together. Review the
diff before committing it: a changed row is a changed routing decision.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchlib as o  # noqa: E402

GOLDEN_FILE = o.GOLDEN / "role_resolution.json"


def dump(golden):
    """One line per case, so a changed routing decision is a one-line diff."""
    lines = ['{"schema": 1, "policies": {']
    pols = sorted(golden["policies"].items())
    for pi, (sha, table) in enumerate(pols):
        lines.append(f'"{sha}": {{')
        keys = sorted(table)
        for ki, key in enumerate(keys):
            comma = "," if ki < len(keys) - 1 else ""
            lines.append(f"{json.dumps(key)}: {json.dumps(table[key], sort_keys=True)}{comma}")
        lines.append("}" + ("," if pi < len(pols) - 1 else ""))
    lines.append("}}")
    return "\n".join(lines) + "\n"


ROSTER_FILE = o.GOLDEN / "roster_config.json"
CONTRACT_FILE = o.GOLDEN / "contract_render.json"
DISPATCH_FILE = o.GOLDEN / "dispatch_dry_run.json"


def main(argv):
    if argv[:1] == ["--roster"]:
        ROSTER_FILE.write_text(json.dumps(o.roster_facts(), indent=1, sort_keys=True) + "\n")
        print("wrote", ROSTER_FILE)
        return
    if argv[:1] == ["--contract"]:
        with tempfile.TemporaryDirectory() as tmp:
            CONTRACT_FILE.write_text(json.dumps(o.contract_cases(tmp), indent=1, sort_keys=True) + "\n")
        print("wrote", CONTRACT_FILE)
        return
    ic = o.real_ic()
    if not ic:
        sys.exit("gen_golden: no `ic` on PATH (set ORCHCOMPAT_IC)")
    if argv[:1] == ["--dispatch"]:
        policies = [Path(a).resolve() for a in argv[1:]] or [o.ROOT / "config/routing.yaml"]
        golden = (json.loads(DISPATCH_FILE.read_text()) if DISPATCH_FILE.exists()
                  else {"schema": 1, "policies": {}})
        for policy in policies:
            with tempfile.TemporaryDirectory() as tmp:
                golden["policies"][o.policy_sha256(policy)] = o.dispatch_dry_table(ic, policy, tmp)
        DISPATCH_FILE.write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
        print("wrote", DISPATCH_FILE, "policies:", ", ".join(sorted(golden["policies"])))
        return
    policies = [Path(a).resolve() for a in argv] or [o.ROOT / "config/routing.yaml"]
    golden = json.loads(GOLDEN_FILE.read_text()) if GOLDEN_FILE.exists() else {"schema": 1, "policies": {}}
    for policy in policies:
        with tempfile.TemporaryDirectory() as home:
            golden["policies"][o.policy_sha256(policy)] = o.role_table(ic, policy, home)
    GOLDEN_FILE.write_text(dump(golden))
    print("wrote", GOLDEN_FILE, "policies:", ", ".join(sorted(golden["policies"])))


if __name__ == "__main__":
    main(sys.argv[1:])
