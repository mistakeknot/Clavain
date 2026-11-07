"""Shared helpers for the orchestration characterization tests.

Everything here is hermetic: a temp HOME, a scrubbed environment, and fake
external CLIs (ic, claude, codex) that record their arguments and exit.
Nothing launches a model, and nothing touches a real bb, gh or network.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
FIXTURES = HERE / "fixtures"
SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"

REASONS = (
    "unresolved-success-criteria",
    "foundational-invariants",
    "broad-consequences",
    "difficult-verification",
    "capability-failure",
)

# Env prefixes that would leak the operator's session into a test.
_SCRUB_PREFIXES = ("CLAVAIN_", "BB_", "CLAUDE", "CODEX", "DISPATCH_", "INTERCORE", "IC_")


def real_ic():
    """The real `ic` binary, or None. Honors ORCHCOMPAT_IC for a pinned build."""
    override = os.environ.get("ORCHCOMPAT_IC")
    if override:
        return override if os.access(override, os.X_OK) else None
    return shutil.which("ic")


def policy_under_test():
    """The routing policy the role table is computed from.

    Defaults to this checkout's config/routing.yaml. S8 points
    ORCHCOMPAT_POLICY at the policy that results from the neutral defaults
    plus the operator overlay, and the same golden then proves identity.
    """
    return Path(os.environ.get("ORCHCOMPAT_POLICY") or ROOT / "config/routing.yaml")


def hermetic_env(home, *path_dirs, **extra):
    """A scrubbed environment: temp HOME, fakes first on PATH, no session vars."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(_SCRUB_PREFIXES)}
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                "TMPDIR", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(key, None)
    tmp = Path(home) / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env.update(HOME=str(home), TMPDIR=str(tmp), LANG="C.UTF-8", LC_ALL="C.UTF-8",
               PATH=":".join([*map(str, path_dirs), SYSTEM_PATH]))
    env.update({k: str(v) for k, v in extra.items()})
    return env


def write_exec(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return path


# A fake model CLI. It logs one JSON line per call (argv, stdin, selected
# environment) to $FAKE_CALLS and answers with one stream-json result event so
# dispatch.sh sees a clean run. `--version` answers without logging a run.
FAKE_MODEL_CLI = r"""#!/usr/bin/env python3
import json, os, sys
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
if args[:1] in (["--version"], ["-V"]):
    print(name + " " + os.environ.get("FAKE_VERSION", "9.9.9"))
    sys.exit(0)
stdin = "" if sys.stdin.isatty() else sys.stdin.read()
calls = os.environ.get("FAKE_CALLS")
if calls:
    with open(calls, "a") as fh:
        fh.write(json.dumps({"cli": name, "argv": args, "stdin_bytes": len(stdin),
                             "stdin_head": stdin[:40]}) + "\n")
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "done"}))
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""

# A fake `ic`. `route dispatch` answers from $FAKE_IC_ROUTE (a JSON file) with
# $FAKE_IC_RC; stderr text comes from $FAKE_IC_STDERR. Every other subcommand
# succeeds silently. Every call is logged to $FAKE_IC_CALLS.
FAKE_IC = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ.get("FAKE_IC_CALLS")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps(args) + "\n")
words = [a for a in args if not a.startswith("-")]
if words[:2] == ["route", "dispatch"]:
    if os.environ.get("FAKE_IC_STDERR"):
        sys.stderr.write(os.environ["FAKE_IC_STDERR"] + "\n")
    route = os.environ.get("FAKE_IC_ROUTE")
    if route:
        sys.stdout.write(open(route).read())
    sys.exit(int(os.environ.get("FAKE_IC_RC", "0")))
sys.exit(0)
"""


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run(cmd, env, cwd=None, timeout=90, stdin=None):
    return subprocess.run([str(c) for c in cmd], env=env, cwd=cwd, input=stdin,
                          capture_output=True, text=True, timeout=timeout)


def py():
    return sys.executable


# ---------------------------------------------------------------------------
# Role resolution through the real `ic route dispatch`
# ---------------------------------------------------------------------------

ROLES = (
    "planning", "frontier-planning", "plan-review", "escalation", "main-integrator",
    "scout", "routine-execution", "deep-execution", "validation", "release-preparation",
    "release-authority", "cross-lab-review", "coordination", "coordinator-seat",
    "main-session", "lane",
)
# Roles that refuse to resolve without a producer identity (checked by the
# golden: the no-producer case for these records the refusal).
PRODUCERS = (None, "claude-opus-5-5", "gpt-6.1-sol")
REASON_SETS = ((),) + tuple((r,) for r in REASONS) + (tuple(REASONS),)


def case_key(role, reasons, producer):
    return "{}|{}|{}".format(role, ",".join(reasons) or "none", producer or "-")


def policy_sha256(policy):
    import hashlib
    return hashlib.sha256(Path(policy).read_bytes()).hexdigest()


def _seat(profile):
    return {"backend": profile.get("backend"), "model": profile.get("model"),
            "effort": profile.get("reasoning_effort"), "service_tier": profile.get("service_tier")}


def resolve_role(ic, policy, role, reasons, producer, home):
    """Run `ic route dispatch` with the policy passed explicitly and normalize.

    Drops fields that vary by checkout (policy_source, policy_hash). A refusal
    is recorded as its exit code and message, which is part of the behavior.
    """
    home = Path(home)
    ctx = home / "ctx.json"
    ctx.write_text(json.dumps({"reasons": list(reasons), "rationale": "characterization"}))
    cmd = [ic, "--json", "route", "dispatch", f"--policy={policy}", f"--role={role}",
           f"--context-file={ctx}"]
    if producer:
        cmd.append(f"--producer-identity={producer}")
    env = hermetic_env(home)
    r = run(cmd, env)
    if r.returncode != 0:
        return {"rc": r.returncode, "error": (r.stderr or r.stdout).strip()}
    d = json.loads(r.stdout)
    out = {"rc": 0, "profile_ref": d.get("profile_ref"), **_seat(d.get("profile", {}))}
    out["fallbacks"] = [{"profile_ref": f.get("profile_ref"), **_seat(f.get("profile", {}))}
                        for f in d.get("fallback_chain", [])]
    out["excluded"] = [{"profile_ref": e.get("profile_ref"), "reason": e.get("reason")}
                       for e in d.get("excluded", [])]
    for key in ("effort_floors_applied", "classification_reasons", "review_requirement",
                "frontier_required", "policy_profile", "fallback_reason",
                "validator_relationship"):
        if key in d:
            out[key] = d[key]
    return out


def role_table(ic, policy, home):
    table = {}
    for role in ROLES:
        for reasons in REASON_SETS:
            for producer in PRODUCERS:
                table[case_key(role, reasons, producer)] = resolve_role(
                    ic, policy, role, reasons, producer, home)
    return table


# ---------------------------------------------------------------------------
# Roster / fleet configuration readers
# ---------------------------------------------------------------------------

def load_generate():
    """Import scripts/roster/generate.py without executing main()."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("roster_generate", ROOT / "scripts/roster/generate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("roster_generate", mod)
    spec.loader.exec_module(mod)
    return mod


def snapshot_for(slugs_cfg, families):
    """A snapshot with one well-formed row per slug the config references."""
    models = []
    specs = [(r.get("slug"), r["model"], r.get("effort"), r.get("reasoning_mode"))
             for r in slugs_cfg.get("rows") or []]
    specs += [(w.get("slug"), w["model"], w.get("row_effort"), w.get("row_reasoning_mode"))
              for w in slugs_cfg.get("waivers") or []]
    for slug, model, effort, mode in specs:
        base = ((families.get("models") or {}).get(model) or {}).get("snapshot_name", model)
        quals = [effort] if effort else (["reasoning"] if mode == "reasoning" else [])
        if mode == "non-reasoning":
            quals.append("non-reasoning")
        models.append({"slug": slug, "name": base + (f" ({', '.join(quals)})" if quals else ""),
                       "providerSlug": "test"})
    return {"models": models}


def roster_facts():
    """Facts read from the real roster-slugs, roster-families and fleet-registry."""
    import yaml
    gen = load_generate()
    cfg = ROOT / "config"
    families = yaml.safe_load((cfg / "roster-families.yaml").read_text())
    slugs = yaml.safe_load((cfg / "roster-slugs.yaml").read_text())
    fleet = yaml.safe_load((cfg / "fleet-registry.yaml").read_text())
    entries, gaps = gen.resolve_registry(slugs, families, gen.index_snapshot(snapshot_for(slugs, families)))
    return {
        "families": {m: [v.get("lab"), v.get("family"), v.get("snapshot_name")]
                     for m, v in sorted(families["models"].items())},
        "families_top_level_keys": sorted(families),
        "slug_rows": sorted(r["ref"] if r.get("ref") else f"{r['model']}@{r.get('effort')}"
                            for r in slugs["rows"]),
        "slug_waivers": {w["ref"]: w.get("status") for w in slugs["waivers"]},
        "registry_entries": {k: [v["status"], v["model"], v["slug"]] for k, v in sorted(entries.items())},
        "registry_gaps": sorted([k, why] for k, why in gaps),
        "fleet_version": fleet.get("version"),
        "fleet_agents": {a: [v.get("category"), v.get("source"), v.get("roles"),
                             v.get("orphaned_at") is not None]
                         for a, v in sorted(fleet["agents"].items())},
    }


# ---------------------------------------------------------------------------
# Instruction contract generator (scripts/sync-agent-instructions.py)
# ---------------------------------------------------------------------------

CONTRACT_FIXTURES = FIXTURES / "contract"
CONTRACT_HOSTS = ("codex", "claude", "hermes", "gemini", "kimi", "opencode", "cursor", "vscode")


def make_source(dest, policy_text=None):
    """A minimal Clavain source tree around the frozen contract fixtures.

    The generator and its block helper come from this checkout, so the tests
    exercise the real code; the template, adapters, version and policy are the
    frozen fixtures, so the output is a fixed function of the generator alone.
    """
    dest = Path(dest)
    for rel in ("config/agent-instructions.md", "config/host-adapters.json",
                "config/codex-instructions.md", "config/routing.yaml",
                ".claude-plugin/plugin.json"):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CONTRACT_FIXTURES / Path(rel).name, target)
    if policy_text is not None:
        (dest / "config/routing.yaml").write_text(policy_text)
    for rel in ("scripts/sync-agent-instructions.py", "scripts/sync-codex-instructions.py",
                "scripts/check-instruction-contract.sh"):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
        target.chmod(0o755)
    return dest


def run_generator(source, home, *args, env_extra=None):
    env = hermetic_env(home, **(env_extra or {}))
    return run([py(), "-I", ROOT / "scripts/sync-agent-instructions.py", "--source", source, *args], env)


def normalize_contract(text, source, policy):
    """Replace the temp paths that vary per run with stable tokens."""
    for value, token in ((str(Path(policy).resolve()), "<POLICY>"), (str(Path(source).resolve()), "<SOURCE>")):
        text = text.replace(value, token)
    return text


def contract_cases(tmp):
    """Rendered body and metadata per (host, mode) for the fixture tree."""
    source = make_source(Path(tmp) / "src")
    home = Path(tmp) / "home"
    home.mkdir(exist_ok=True)
    policy = source / "config/routing.yaml"
    cases = {}
    for host in CONTRACT_HOSTS:
        for mode, flags in (("explicit", ["--policy", policy]), ("portable", ["--portable-policy"]),
                            ("default", [])):
            r = run_generator(source, home, "--host", host, "--render", *flags)
            body = normalize_contract(r.stdout, source, policy)
            # The metadata is only reachable through --check; use a missing file.
            c = run_generator(source, home, "--host", host, "--file", home / "absent.md",
                              "--check", *flags)
            meta = json.loads(normalize_contract(c.stdout, source, policy)) if c.returncode in (0, 1) else None
            cases[f"{host}|{mode}"] = {"rc": r.returncode, "body": body, "metadata": meta}
    return cases


# ---------------------------------------------------------------------------
# scripts/dispatch.sh without launching a model
# ---------------------------------------------------------------------------

import re  # noqa: E402

DISPATCH = ROOT / "scripts" / "dispatch.sh"
ROUTE_FIXTURES = FIXTURES / "dispatch"


class Rig:
    """A hermetic place to run dispatch.sh: fake ic/claude/codex first on PATH.

    The fake CLIs log every call; the receipt goes to a temp JSONL file. With
    real_ic=True the real `ic` is on PATH instead of the fake (dry runs only:
    a real `ic` cannot persist a started routing decision in a temp HOME).
    """

    def __init__(self, root, real_ic_path=None, codex_version="9.9.9"):
        self.t = Path(root)
        self.home = self.t / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.bin = self.t / "bin"
        if real_ic_path:
            (self.bin).mkdir(parents=True, exist_ok=True)
            link = self.bin / "ic"
            if not link.exists():
                link.symlink_to(real_ic_path)
        else:
            write_exec(self.bin / "ic", FAKE_IC)
        write_exec(self.bin / "claude", FAKE_MODEL_CLI)
        write_exec(self.bin / "codex", FAKE_MODEL_CLI)
        self.codex_version = codex_version
        self.repo = self.t / "repo"
        self.repo.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.prompt = self.t / "prompt.md"
        self.prompt.write_text("PROMPT\n")
        self.out = self.t / "out.md"
        self.ctx = self.t / "ctx.json"
        self.ctx.write_text(json.dumps({"reasons": [], "rationale": "characterization"}))
        self.calls_file = self.t / "calls.jsonl"
        self.ic_file = self.t / "ic-calls.jsonl"
        self.receipt_file = self.t / "receipt.jsonl"

    def use_route(self, name):
        """Install a canned `ic` answer. policy_source/policy_hash are filled in
        from this checkout's policy: dispatch.sh reads the policy file named by
        the route to deliver the instruction contract, so it must exist."""
        route = json.loads((ROUTE_FIXTURES / f"route-{name}.json").read_text())
        policy = ROOT / "config" / "routing.yaml"
        route["policy_source"] = str(policy)
        route["policy_hash"] = policy_sha256(policy)
        (self.t / "route.json").write_text(json.dumps(route))

    def base_args(self):
        return ["-C", self.repo, "--prompt-file", self.prompt, "-o", self.out]

    def env(self, **extra):
        env = hermetic_env(
            self.home, self.bin, FAKE_IC_ROUTE=self.t / "route.json",
            FAKE_CALLS=self.calls_file, FAKE_IC_CALLS=self.ic_file,
            FAKE_VERSION=self.codex_version,
            CLAVAIN_DISPATCH_RECEIPT_FILE=self.receipt_file,
            CLAVAIN_CONTEXT_GATEWAY_MODE="off", CLAVAIN_BB_DIRECT_POOL="0",
            CLAVAIN_POOL_HEADROOM="0")
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def dispatch(self, *args, env_path=None, **extra):
        env = self.env(**extra)
        if env_path is not None:
            env["PATH"] = env_path
        return run(["bash", DISPATCH, *args], env, cwd=ROOT)

    def calls(self):
        return read_jsonl(self.calls_file)

    def ic_calls(self):
        return read_jsonl(self.ic_file)

    def receipts(self):
        return read_jsonl(self.receipt_file)

    def norm(self, text):
        return text.replace(str(self.t), "<T>")


_RECEIPT_VOLATILE = ("dispatch_id", "attempt_id", "started_at", "ended_at")


def normalize_receipt(rec):
    return {k: ("<volatile>" if k in _RECEIPT_VOLATILE else v) for k, v in rec.items()}


DRY_REASON_SETS = ((), tuple(REASONS))


def dispatch_dry_row(rig, policy, role, reasons=(), producer="claude-opus-5-5"):
    """One `dispatch.sh --role R --dry-run` through the real ic, normalized."""
    ctx = rig.ctx
    ctx.write_text(json.dumps({"reasons": list(reasons), "rationale": "characterization"}))
    r = rig.dispatch("--role", role, *rig.base_args(), "--dry-run",
                     "--producer-identity", producer,
                     CLAVAIN_ROUTING_POLICY=policy, CLAVAIN_DECISION_CONTEXT=ctx)
    row = {"rc": r.returncode}
    if r.returncode == 0:
        lines = r.stdout.splitlines()
        cmd = rig.norm(lines[0])
        row["command"] = re.sub(r"\$'.*?bytes total\)'", "<PROMPT>", cmd, flags=re.S)
        row["env"] = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("# Env:")]
    else:
        row["error"] = rig.norm(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
    return row


def dispatch_dry_table(ic, policy, tmp):
    table = {}
    for i, role in enumerate(ROLES):
        rig = Rig(Path(tmp) / f"r{i}", real_ic_path=ic)
        for reasons in DRY_REASON_SETS:
            key = "{}|{}".format(role, ",".join(reasons) or "none")
            table[key] = dispatch_dry_row(rig, policy, role, reasons)
    return table
