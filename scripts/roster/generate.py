#!/usr/bin/env python3
"""mk-rpnv.9 P1 -- evidence-generated roster: generator plus lint.

Builds `eligibility.json`, `roster.generated.json`, `routing.proposed.patch`
and `report.md` from a pinned, hash-verified interrank/AgMoDB snapshot and
the current `routing.yaml`. See `PLAN-M1-r5.md` §P1 for the full spec this
implements; the section references in comments below point back to it.

No network fetch, no live model calls, no default snapshot URL. The patch is
generated in memory, re-applied in memory and validated there, and is never
applied to `routing.yaml`. Every output carries `promotion_ready: false`.

One pipeline (`run_pipeline`) serves both the real run and `--self-test`:
the truth table feeds routing.yaml fragments, snapshot rows and registries
through the same enumeration, mapping, chain, rule, gate, patch and
validation code the real run uses.

Exit codes:
  0  success (patch emitted, or --self-test passed)
  1  usage / unexpected error, or routing.yaml changed during the run
  2  diagnostic refusal (stale snapshot, hash mismatch, unmapped model,
     corrupt input, patch validation failure, or --self-test failure) --
     never a passing proposal
  3  pyyaml is not installed
"""
import argparse
import copy
import difflib
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("generate: pyyaml is required", file=sys.stderr)
    sys.exit(3)

FRESHNESS_MAX_DAYS = 8
# A generatedAt this far ahead of the clock is treated as corrupt, not fresh.
FRESHNESS_FUTURE_SKEW = timedelta(minutes=10)

FIXER = "Claude Opus 5.5 (mk-chosen P1 fixer, 2026-09-25; the P1 build was Claude Sonnet 5)"

# intercore identity.go: the review roles that require a producer identity.
REVIEW_ROLES = ("validation", "cross-lab-review", "plan-review")
# Rule 2 scope (n4, mk-ratified 2026-09-25): review roles only, not validation.
# n4 also exempts cross_lab_first routing (mk, 2026-09-25: it covers both
# validation and cross-lab-review), so in a cross_lab_first role rule 2 is a
# chain-level lint (no Astra seat) and only the Fable m2 downgrade is flagged
# per seat. plan-review is not cross_lab_first and keeps per-seat flags.
RULE2_ROLES = ("plan-review", "cross-lab-review")
# N2: a waiver status is a closed enum. RATIFIED needs approved_by and an
# approval pointer; PROPOSED has no approver yet.
WAIVER_STATUSES = ("PROPOSED", "RATIFIED")

ROLE_CLASS = {
    "scout": "evidence",
    "main-integrator": "authority",
    "release-authority": "authority",
    "frontier-planning": "authority",
    "escalation": "authority",
    "planning": "judgment",
    "validation": "review",
    "cross-lab-review": "review",
    "plan-review": "review",
    "coordination": "relay",
    "routine-execution": "execution",
    "deep-execution": "execution",
    "release-preparation": "execution",
}
# Rule 5: Luna is excluded from evidence, authority and review triage.
RULE5_CLASSES = ("evidence", "authority", "review")
# Rule 6, role-class half: relay seats admit relay models only, and a
# Sol-medium relay seat never holds an authority or judgment role.
RELAY_ALLOWED_FAMILIES = ("sonnet", "sol")
RULE6_BARRED_CLASSES = ("authority", "judgment")

# Opus is a capacity substitute (mk ruling 2026-09-10); claude-opus-5 is the
# only Opus version admitted to frontier_models.
OPUS_FRONTIER_ADMITTED = ("claude-opus-5",)

# Availability scenarios for effective heads. `sol-unavailable` is the
# CHECK-M1-r3 case (Sol operationally failed, cross_lab_first falls through);
# `openai-unavailable` is the Codex-quota-out case.
SCENARIOS = ("nominal", "sol-unavailable", "openai-unavailable")

RULE_REFERENCES = {
    "3": {"enforced_by": "bb checkpoint rotation; the mk-rpnv.3 boundary envelope", "status": "not_verified_by_generator"},
    "4": {"enforced_by": "pool-headroom and the mk-rpnv.3 Jev/headroom envelope", "status": "not_verified_by_generator"},
    "7": {"enforced_by": "event triggers and the coordinator messaging rules", "status": "not_verified_by_generator"},
}

# Snapshot name qualifiers, matched as whole comma-separated tokens by dict
# lookup (never substring, never set iteration) so "Xhigh Effort" can only
# ever parse as xhigh (B3).
EFFORT_TOKENS = {
    "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max",
    "low effort": "low", "medium effort": "medium", "high effort": "high",
    "xhigh effort": "xhigh", "max effort": "max",
}
MODE_TOKENS = {
    "reasoning": "reasoning",
    "adaptive reasoning": "reasoning",
    "non-reasoning": "non-reasoning",
}
NEUTRAL_TOKENS = ("default fallback",)
NAME_RE = re.compile(r"^(?P<base>.*?) \((?P<quals>[^()]*)\)$")
PROVIDER_PREFIX_RE = re.compile(r"^[^:()]+: ")


class Refusal(Exception):
    """A diagnostic refusal: no proposal is emitted."""

    def __init__(self, codes, messages):
        super().__init__("; ".join(messages))
        self.codes = codes
        self.messages = messages


class PatchError(Exception):
    pass


# --------------------------------------------------------------------------
# Freshness (A1)
# --------------------------------------------------------------------------

def _parse_timestamp(value):
    if not value or not isinstance(value, str):
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def freshness(generated_at, now):
    """Return (status, deadline). Absent or unparseable is stale; a timestamp
    more than FRESHNESS_FUTURE_SKEW ahead of `now` is `future` (N2)."""
    ts = _parse_timestamp(generated_at)
    if ts is None:
        return "stale", None
    deadline = ts + timedelta(days=FRESHNESS_MAX_DAYS)
    if ts - now > FRESHNESS_FUTURE_SKEW:
        return "future", deadline
    if now > deadline:
        return "stale", deadline
    return "fresh", deadline


def _iso(ts):
    # N4: keep sub-second precision so the printed deadline is the exact one.
    if not ts:
        return None
    ts = ts.astimezone(timezone.utc)
    spec = "milliseconds" if ts.microsecond else "seconds"
    return ts.isoformat(timespec=spec).replace("+00:00", "Z")


# --------------------------------------------------------------------------
# Snapshot rows and the closed-world registry (A1, B3, B4)
# --------------------------------------------------------------------------

def parse_snapshot_row(entry, all_slugs):
    slug = entry.get("slug") or ""
    name = (entry.get("name") or "").strip()
    m = NAME_RE.match(name)
    if m:
        base = m.group("base")
        tokens = [t.strip().lower() for t in m.group("quals").split(",") if t.strip()]
    else:
        base, tokens = name, []
    efforts, modes, unrecognised = [], [], []
    composite = slug.endswith("-fallback")
    for tok in tokens:
        if tok in EFFORT_TOKENS:
            efforts.append(EFFORT_TOKENS[tok])
        elif tok in MODE_TOKENS:
            modes.append(MODE_TOKENS[tok])
        elif tok in NEUTRAL_TOKENS:
            continue
        elif tok.endswith(" fallback"):
            composite = True
        else:
            unrecognised.append(tok)
    distinct_efforts = sorted(set(efforts))
    effort = distinct_efforts[0] if len(distinct_efforts) == 1 else ("ambiguous" if efforts else None)
    distinct_modes = sorted(set(modes))
    if len(distinct_modes) > 1:
        mode = "ambiguous"
    elif distinct_modes:
        mode = distinct_modes[0]
    else:
        mode = "reasoning" if effort else "unlabelled"
    provider = entry.get("providerSlug") or ""
    prefixed = bool(provider) and slug.startswith(provider + "-")
    provider_duplicate = prefixed and (slug[len(provider) + 1:] in all_slugs or bool(PROVIDER_PREFIX_RE.match(name)))
    return {
        "slug": slug,
        "name": name,
        "base_name": base,
        "effort": effort,
        "reasoning_mode": mode,
        "is_latest_alias": slug.endswith("-latest"),
        "is_composite": composite,
        "is_provider_duplicate": provider_duplicate,
        "unrecognised_qualifiers": unrecognised,
    }


def index_snapshot(snapshot):
    models = snapshot.get("models")
    if not isinstance(models, list):
        raise Refusal(["snapshot_corrupt"], ["snapshot has no models[] list"])
    all_slugs = {m.get("slug") for m in models if isinstance(m, dict)}
    index = {}
    for m in models:
        if isinstance(m, dict) and m.get("slug"):
            index[m["slug"]] = parse_snapshot_row(m, all_slugs)
    return index


def row_problems(row, model, families, want_effort, want_mode):
    """Every reason `row` cannot stand for `model` at (want_effort, want_mode).
    Identity comes from roster-families.yaml, never from the registry (B4)."""
    problems = []
    if row["is_latest_alias"]:
        problems.append("latest_alias")
    if row["is_composite"]:
        problems.append("composite")
    if row["is_provider_duplicate"]:
        problems.append("provider_duplicate")
    for tok in row["unrecognised_qualifiers"]:
        problems.append(f"unrecognised_qualifier:{tok}")
    fam = (families.get("models") or {}).get(model)
    if fam is None:
        problems.append(f"unknown_family:{model}")
    elif fam.get("snapshot_name") != row["base_name"]:
        problems.append(f"identity:row is '{row['base_name']}', {model} is '{fam.get('snapshot_name')}'")
    if row["effort"] != want_effort:
        problems.append(f"effort:row {row['effort']!r} != declared {want_effort!r}")
    if row["reasoning_mode"] != want_mode:
        problems.append(f"reasoning_mode:row {row['reasoning_mode']!r} != declared {want_mode!r}")
    return problems


def resolve_registry(slugs_cfg, families, snap_index):
    """Verify every row and waiver against the parsed snapshot. Returns
    ({key: entry}, [(key, reason)]). A key with any problem is not mapped."""
    entries, gaps = {}, []
    specs = []
    for row in slugs_cfg.get("rows") or []:
        key = row["ref"] if row.get("ref") else f"{row.get('model')}@{row.get('effort')}"
        specs.append((key, row, row.get("effort"), row.get("reasoning_mode"), "exact"))
    for w in slugs_cfg.get("waivers") or []:
        specs.append((w.get("ref"), w, w.get("row_effort"), w.get("row_reasoning_mode"), waiver_kind(w)))
    seen = set()
    for key, spec, want_effort, want_mode, kind in specs:
        if not key or not spec.get("model") or not spec.get("slug") or want_mode is None:
            gaps.append((key, "registry entry lacks ref/model/slug/reasoning_mode"))
            continue
        if key in seen:
            gaps.append((key, "duplicate registry entry (closed world: exactly one row)"))
            entries.pop(key, None)
            continue
        seen.add(key)
        if isinstance(kind, tuple):
            gaps.append((key, kind[1]))
            continue
        row = snap_index.get(spec["slug"])
        if row is None:
            gaps.append((key, f"slug '{spec['slug']}' not present in snapshot"))
            continue
        problems = row_problems(row, spec["model"], families, want_effort, want_mode)
        if problems:
            gaps.append((key, f"slug '{spec['slug']}' rejected ({'; '.join(problems)})"))
            continue
        entries[key] = {
            "status": kind,
            "model": spec["model"],
            "slug": spec["slug"],
            "row_name": row["name"],
            "label": spec.get("label"),
            "caveats": spec.get("caveats"),
            "waiver_status": spec.get("status"),
            "approved_by": spec.get("approved_by"),
            "approval": spec.get("approval"),
            "fallback_ref": spec.get("fallback_ref"),
            "evidence": spec.get("evidence"),
        }
    # A waiver's fallback_ref (e.g. Fable closed -> Claude Code `opus`) names
    # the producer that runs instead; it must itself be a verified entry.
    # F1 (CHECK-P1-r3): iterate to a fixpoint. A single pass misses a chain
    # (A -> B -> missing) when A sorts before B: A passes because B is still
    # present at check time, and only B gets popped, leaving A's fallback_ref
    # dangling for map_references to KeyError on.
    while True:
        round_gaps = []
        for key in sorted(entries):
            fb = entries[key].get("fallback_ref")
            if fb and fb not in entries:
                round_gaps.append((key, f"fallback_ref '{fb}' is not a verified registry entry"))
        if not round_gaps:
            break
        gaps.extend(round_gaps)
        for key, _ in round_gaps:
            entries.pop(key, None)
    return entries, gaps


def waiver_kind(w):
    """Closed-enum waiver status (N2). Returns the mapping kind, or
    ("invalid", reason)."""
    status = w.get("status")
    if status not in WAIVER_STATUSES:
        return ("invalid", f"waiver status must be exactly one of {', '.join(WAIVER_STATUSES)} (got {status!r})")
    if status == "RATIFIED":
        if not w.get("approved_by") or not w.get("approval"):
            return ("invalid", "a RATIFIED waiver needs approved_by and an approval pointer")
        # F2 (CHECK-P1-r3): "Only mk ratifies" (roster-slugs.yaml comment) was
        # not enforced -- approved_by was free text. RATIFIED now requires
        # approved_by to be exactly "mk".
        if w.get("approved_by") != "mk":
            return ("invalid", f"a RATIFIED waiver needs approved_by == \"mk\" (got {w.get('approved_by')!r})")
        return "waiver-ratified"
    if w.get("approved_by"):
        return ("invalid", "a PROPOSED waiver cannot carry approved_by")
    return "waiver-proposed"


# --------------------------------------------------------------------------
# routing.yaml model: seats, references, chains (intercore semantics)
# --------------------------------------------------------------------------

def runtime_lab(identity):
    """intercore identity.go modelLab: prefix-based lab of a canonical ID."""
    if identity.startswith("gpt-"):
        return "openai"
    if identity.startswith("claude-"):
        return "anthropic"
    if identity.startswith("kimi"):
        return "moonshot"
    return ""


class World:
    """A read-only view of one routing.yaml document for chain resolution."""

    def __init__(self, routing, families):
        self.routing = routing
        self.families = families
        dispatch = routing.get("dispatch") or {}
        self.aliases = dispatch.get("model_aliases") or {}
        self.tiers = dispatch.get("tiers") or {}
        self.roles = dispatch.get("roles") or {}
        self.legacy = dispatch.get("fallback") or {}
        self.cross_lab_first = list(dispatch.get("cross_lab_first") or [])
        reasoning = routing.get("reasoning") or {}
        self.frontier_models = list(reasoning.get("frontier_models") or [])
        self.profiles = reasoning.get("profiles") or {}
        self.frontier_ids = [self.expand(m) for m in self.frontier_models]
        self.frontier_labs = {runtime_lab(m) for m in self.frontier_ids if runtime_lab(m)}
        self.seats = {}
        for name, tier in self.tiers.items():
            tier = tier or {}
            model = self.expand(tier.get("model") or "")
            fam = self.family(model) or {}
            self.seats[name] = {
                "name": name,
                "role": tier.get("role"),
                "backend": tier.get("backend"),
                "model": model,
                "effort": tier.get("reasoning_effort"),
                "family": fam.get("family"),
                "lab": fam.get("lab"),
                "fallbacks": list(tier.get("fallbacks") or []),
            }

    def expand(self, model):
        return self.aliases.get(model, model)

    def family(self, model):
        return (self.families.get("models") or {}).get(model)

    def lookup(self, ref):
        """intercore lookupDispatchProfile: follow the legacy map only while a
        concrete tier is absent."""
        seen = set()
        while ref and ref not in seen:
            seen.add(ref)
            if ref in self.tiers:
                return ref
            ref = self.legacy.get(ref)
        return None

    def chain(self, profile_ref):
        """intercore resolveDispatch: preorder DFS over `fallbacks`, deduped."""
        head = self.lookup(profile_ref)
        if head is None:
            return []
        out, seen = [head], {head}

        def walk(refs):
            for ref in refs:
                actual = self.lookup(ref)
                if actual is None or actual in seen:
                    continue
                seen.add(actual)
                out.append(actual)
                walk(self.seats[actual]["fallbacks"])

        walk(self.seats[head]["fallbacks"])
        return out

    def contexts(self):
        """(context label, role, head tier, frontier_required options).
        Default role map, each policy profile's overrides, and review-role
        tiers reachable only by explicit --tier (e.g. validation-fable)."""
        out = []
        for role in sorted(self.roles):
            out.append(("default", role, self.roles[role], self._fr_options(role)))
        for pname in sorted(self.profiles):
            for role, head in sorted(((self.profiles[pname] or {}).get("roles") or {}).items()):
                out.append((f"profile:{pname}", role, head, self._fr_options(role)))
        reachable = set()
        for _, _, head, _ in out:
            reachable.update(self.chain(head))
        for name in sorted(self.seats):
            role = self.seats[name]["role"]
            if role in REVIEW_ROLES and name not in reachable:
                out.append((f"tier:{name}", role, name, (False,)))
        return out

    @staticmethod
    def _fr_options(role):
        # intercore reasoning.go: which roles can carry frontier_required.
        if role in ("frontier-planning", "escalation"):
            return (True,)
        if role in ("plan-review", "deep-execution"):
            return (False, True)
        return (False,)

    def effective_chain(self, context, role, head, producer, frontier_required, scenario):
        chain = self.chain(head)
        seats = [self.seats[s] for s in chain]
        runtime_contract = not context.startswith("tier:")
        if producer and runtime_contract:
            seats = [s for s in seats if s["model"] != producer]
            if role in self.cross_lab_first:
                plab = runtime_lab(producer)
                if plab:
                    first = [s for s in seats if runtime_lab(s["model"]) != plab and runtime_lab(s["model"]) in self.frontier_labs]
                    rest = [s for s in seats if s not in first]
                    seats = first + rest
        if frontier_required:
            seats = [s for s in seats if s["model"] in self.frontier_ids]
        if scenario == "sol-unavailable":
            seats = [s for s in seats if s["family"] != "sol"]
        elif scenario == "openai-unavailable":
            seats = [s for s in seats if runtime_lab(s["model"]) != "openai"]
        return [s["name"] for s in seats]


def tier_refs(routing):
    """Every place routing.yaml names a tier, with where it appears."""
    dispatch = routing.get("dispatch") or {}
    refs = []
    for role, ref in sorted((dispatch.get("roles") or {}).items()):
        refs.append((ref, f"dispatch.roles.{role}"))
    for pname, prof in sorted(((routing.get("reasoning") or {}).get("profiles") or {}).items()):
        for role, ref in sorted(((prof or {}).get("roles") or {}).items()):
            refs.append((ref, f"reasoning.profiles.{pname}.roles.{role}"))
    for name, tier in sorted((dispatch.get("tiers") or {}).items()):
        for ref in (tier or {}).get("fallbacks") or []:
            refs.append((ref, f"dispatch.tiers.{name}.fallbacks"))
    for key, ref in sorted((dispatch.get("fallback") or {}).items()):
        refs.append((ref, f"dispatch.fallback.{key}"))
    for level, ov in sorted(((routing.get("complexity") or {}).get("overrides") or {}).items()):
        ref = (ov or {}).get("dispatch_tier")
        if ref and ref != "inherit":
            refs.append((ref, f"complexity.overrides.{level}.dispatch_tier"))
    return refs


def dangling_tier_refs(world):
    return sorted({f"{where} -> {ref}" for ref, where in tier_refs(world.routing) if world.lookup(ref) is None})


def model_references(routing):
    """STRICT (mk, 2026-09-25): every model string routing.yaml references.
    Returns {ref: {"kind", "where": [...], ...}}."""
    refs = {}

    def add(ref, kind, where, **extra):
        entry = refs.setdefault(ref, {"kind": kind, "where": [], **extra})
        entry["where"].append(where)

    dispatch = routing.get("dispatch") or {}
    aliases = dispatch.get("model_aliases") or {}
    for name, tier in sorted((dispatch.get("tiers") or {}).items()):
        tier = tier or {}
        model = aliases.get(tier.get("model"), tier.get("model"))
        effort = tier.get("reasoning_effort") or "unset"
        add(f"{model}@{effort}", "tier", f"dispatch.tiers.{name}", model=model)
    for alias, target in sorted(aliases.items()):
        add(f"alias:{alias}", "alias", "dispatch.model_aliases", model=target)
    for m in (routing.get("reasoning") or {}).get("frontier_models") or []:
        add(f"frontier:{m}", "frontier", "reasoning.frontier_models", model=aliases.get(m, m))

    sub = routing.get("subagents") or {}

    def add_sub(value, where):
        if value and value != "inherit":
            add(f"subagent:{value}", "subagent", where)

    defaults = sub.get("defaults") or {}
    add_sub(defaults.get("model"), "subagents.defaults.model")
    for cat, v in sorted((defaults.get("categories") or {}).items()):
        add_sub(v, f"subagents.defaults.categories.{cat}")
    for agent, v in sorted((sub.get("overrides") or {}).items()):
        add_sub(v, f"subagents.overrides.{agent}")
    for phase, p in sorted((sub.get("phases") or {}).items()):
        p = p or {}
        add_sub(p.get("model"), f"subagents.phases.{phase}.model")
        for cat, v in sorted((p.get("categories") or {}).items()):
            add_sub(v, f"subagents.phases.{phase}.categories.{cat}")
    for level, ov in sorted(((routing.get("complexity") or {}).get("overrides") or {}).items()):
        add_sub((ov or {}).get("subagent_model"), f"complexity.overrides.{level}.subagent_model")

    local = routing.get("local_models") or {}
    for key in sorted(local.get("tier_mappings") or {}):
        add(key, "local", "local_models.tier_mappings")
    for level, v in sorted((local.get("complexity_routing") or {}).items()):
        # N11: `cloud` names a model too (routing.yaml's C3 comment says
        # GPT-5.5 xhigh via codex), so it needs an explicit row or waiver.
        add(v, "cloud" if v == "cloud" else "local", f"local_models.complexity_routing.{level}")

    ex = routing.get("executor_routing") or {}
    for cls, backends in sorted((ex.get("classes") or {}).items()):
        for b in backends or []:
            add(f"executor:{b}", "executor", f"executor_routing.classes.{cls}", backend=b)
    for b in ex.get("default") or []:
        add(f"executor:{b}", "executor", "executor_routing.default", backend=b)
    return refs


def map_references(routing, families, registry):
    """Bind every reference to a verified registry entry. Returns
    ({ref: mapping}, [unmapped refs])."""
    refs = model_references(routing)
    fam_models = families.get("models") or {}
    by_model = {}
    for key, entry in registry.items():
        by_model.setdefault(entry["model"], []).append(key)
    mapping, unmapped = {}, []
    for ref in sorted(refs):
        info = refs[ref]
        kind = info["kind"]
        m = None
        if kind in ("alias", "frontier"):
            target = info["model"]
            if target in fam_models and by_model.get(target):
                m = {"status": "derived", "model": target, "via": sorted(by_model[target])}
        else:
            # Tiers, subagents, local models, executors and `cloud` map only
            # through an explicit row or waiver. Executors are never derived
            # from tiers: executor_routing dispatches untiered, so the model
            # is the host default, not any tier's (Blocker 1, r2).
            entry = registry.get(ref)
            if entry and (kind != "tier" or entry["model"] == info["model"]):
                fb = entry.get("fallback_ref")
                if fb and fb not in registry:
                    # F1 defense-in-depth: resolve_registry's fixpoint pass
                    # should never leave a dangling fallback_ref here, but if
                    # it does, refuse instead of KeyError-ing on registry[fb].
                    m = None
                else:
                    m = dict(entry)
                    if fb:
                        m["fallback_model"] = registry[fb]["model"]
        if m is None:
            unmapped.append(ref)
            mapping[ref] = {"status": "unmapped", "kind": kind, "where": info["where"]}
        else:
            m.update({"kind": kind, "where": info["where"]})
            mapping[ref] = m
    return mapping, unmapped


# --------------------------------------------------------------------------
# Rules as predicates (§P1 Rules), applied per (role, producer, seat)
# --------------------------------------------------------------------------

def seat_failures(world, role, producer, seat, luna_evals):
    fails = []
    cls = ROLE_CLASS.get(role, "execution")
    pfam = (world.family(producer) or {}).get("family") if producer else None
    if role in REVIEW_ROLES and pfam == "sol" and not (seat["lab"] == "anthropic" or seat["family"] == "astra"):
        fails.append(("rule1", "m1: Kimi validating Sol-produced work" if seat["family"] == "kimi" else ""))
    if role in RULE2_ROLES and pfam == "opus" and seat["family"] != "astra":
        if seat["family"] == "fable":
            fails.append(("rule2", "m2: declared same-lab downgrade"))
        elif role not in world.cross_lab_first:
            fails.append(("rule2", ""))
    if role in REVIEW_ROLES and producer and pfam and pfam == seat["family"] and producer != seat["model"]:
        fails.append(("A2", "runtime_family_unenforced"))
    if seat["family"] == "luna" and cls in RULE5_CLASSES and cls not in luna_evals:
        fails.append(("rule5", f"Luna in {cls} without an accepted per-class evaluation"))
    if cls == "relay" and seat["family"] not in RELAY_ALLOWED_FAMILIES:
        fails.append(("rule6", "relay seat admits relay models only"))
    if cls in RULE6_BARRED_CLASSES and seat["family"] == "sol" and seat["effort"] == "medium":
        fails.append(("rule6", "Sol-medium relay seat in an authority/judgment role"))
    return fails


def producers_of(world, mapping, families):
    """Every exact model that can produce work: dispatch seats, subagent and
    local models, plus the unevaluated candidates (A2 is checked for them)."""
    out = {s["model"] for s in world.seats.values() if s["model"]}
    for m in mapping.values():
        if m.get("kind") in ("subagent", "local", "executor", "cloud") and m.get("model"):
            out.add(m["model"])
            if m.get("fallback_model"):
                out.add(m["fallback_model"])
    out.update(families.get("candidates") or [])
    return sorted(out)


def head_table(world, producers):
    """Effective head and chain for every (context, role, producer,
    scenario, frontier_required) the runtime can produce."""
    heads, chains = {}, {}
    for context, role, head, fr_opts in world.contexts():
        prods = producers if role in REVIEW_ROLES else [None]
        for producer in prods:
            for fr in fr_opts:
                for scenario in SCENARIOS:
                    key = f"{context}|{role}|{producer or '-'}|{scenario}|{'frontier' if fr else 'default'}"
                    chain = world.effective_chain(context, role, head, producer, fr, scenario)
                    chains[key] = chain
                    heads[key] = chain[0] if chain else None
    return heads, chains


def evaluate(world, producers, luna_evals):
    """Per (context, role, producer) seat eligibility plus the per-seat
    aggregation that A3 needs: which pairs reach the seat, which fail."""
    entries = []
    reach = {}      # seat -> set of (context, role, producer)
    failing = {}    # seat -> {(context, role, producer): [(rule, note)]}
    for context, role, head, _ in world.contexts():
        base_chain = world.chain(head)
        prods = producers if role in REVIEW_ROLES else [None]
        for producer in prods:
            seats_out = []
            for name in base_chain:
                seat = world.seats[name]
                fails = seat_failures(world, role, producer, seat, luna_evals)
                reach.setdefault(name, set()).add((context, role, producer))
                if fails:
                    failing.setdefault(name, {})[(context, role, producer)] = fails
                seats_out.append({
                    "seat": name,
                    "model": seat["model"],
                    "family": seat["family"],
                    "eligible": not fails,
                    "failures": [{"rule": r, "note": n} for r, n in fails],
                })
            entries.append({
                "context": context,
                "role": role,
                "producer": producer,
                "producer_family": (world.family(producer) or {}).get("family") if producer else None,
                "base_chain": base_chain,
                "seats": seats_out,
            })
    return entries, reach, failing


def flag_strings(world, pairs):
    out = set()
    for (context, role, producer), fails in pairs.items():
        pfam = (world.family(producer) or {}).get("family") if producer else "*"
        for rule, _ in fails:
            # Rules 5 and 6 depend on the seat and role class, not the producer.
            out.add(f"{rule}/{role}/{'*' if rule in ('rule5', 'rule6') else pfam}")
    return sorted(out)


# --------------------------------------------------------------------------
# Patch scope (A3): remove only when ineligible for every producer reaching
# the chain; any effective-head change is a reorder and needs a gate.
# --------------------------------------------------------------------------

def apply_removals(routing, removals):
    patched = copy.deepcopy(routing)
    tiers = patched["dispatch"]["tiers"]
    for name in removals:
        tiers.pop(name, None)
    for tier in tiers.values():
        if tier and "fallbacks" in tier:
            kept = [f for f in tier["fallbacks"] if f not in removals]
            if kept:
                tier["fallbacks"] = kept
            else:
                del tier["fallbacks"]
    return patched


def changed_heads(base_heads, other_heads):
    return sorted(k for k in base_heads if base_heads[k] != other_heads.get(k))


def gate_removals(routing, families, producers, candidates, reorder_waivers):
    """Admit removal candidates one at a time (sorted, deterministic). Returns
    (removed, withheld, head_changes_by_seat)."""
    base_world = World(routing, families)
    base_heads, _ = head_table(base_world, producers)
    role_heads = set((routing.get("dispatch") or {}).get("roles", {}).values())
    for prof in ((routing.get("reasoning") or {}).get("profiles") or {}).values():
        role_heads.update(((prof or {}).get("roles") or {}).values())
    legacy = (routing.get("dispatch") or {}).get("fallback") or {}
    legacy_refs = set(legacy) | set(legacy.values())
    complexity_refs = {
        (ov or {}).get("dispatch_tier")
        for ov in ((routing.get("complexity") or {}).get("overrides") or {}).values()
    }
    waived = {w.get("seat"): w for w in reorder_waivers or []}
    accepted, withheld, head_changes = [], [], {}
    current_heads = base_heads
    for seat in sorted(candidates):
        gates = []
        if base_world.seats[seat]["family"] == "fable":
            gates.append("fable_canon_seat")
        if seat in role_heads:
            gates.append("role_head_needs_repoint")
        if seat in legacy_refs:
            gates.append("legacy_fallback_ref")
        if seat in complexity_refs:
            gates.append("complexity_dispatch_tier_ref")
        trial = accepted + [seat]
        trial_heads, _ = head_table(World(apply_removals(routing, trial), families), producers)
        newly = sorted(k for k in changed_heads(current_heads, trial_heads))
        if newly:
            head_changes[seat] = newly
            if seat not in waived:
                gates.append("reorder_gate")
        if gates:
            withheld.append({"seat": seat, "gates": gates, "head_changes": newly})
            continue
        accepted.append(seat)
        current_heads = trial_heads
    return accepted, withheld, head_changes


# --------------------------------------------------------------------------
# Opus-last invariant and rule-2 gaps (lint, A3)
# --------------------------------------------------------------------------

def opus_last_violations(world, chains):
    """No Opus version ahead of a non-Opus frontier_models seat, in any
    effective chain. `validation-opus` as validation primary is allowed: the
    invariant governs ordering relative to frontier seats only."""
    out = set()
    for key, chain in chains.items():
        context, role = key.split("|")[:2]
        for i, name in enumerate(chain):
            if world.seats[name]["family"] != "opus":
                continue
            for later in chain[i + 1:]:
                s = world.seats[later]
                if s["model"] in world.frontier_ids and s["family"] != "opus":
                    out.add(f"{context}|{role}: {name} ({world.seats[name]['model']}) ahead of frontier seat {later} ({s['model']})")
    for m in world.frontier_ids:
        if (world.family(m) or {}).get("family") == "opus" and m not in OPUS_FRONTIER_ADMITTED:
            out.add(f"frontier_models: Opus version {m} added (only {', '.join(OPUS_FRONTIER_ADMITTED)} is admitted)")
    return sorted(out)


# --------------------------------------------------------------------------
# Textual patch: remove tier blocks, strip fallbacks, add flag comments
# --------------------------------------------------------------------------

TIER_HEADER_RE = re.compile(r"^    ([A-Za-z0-9_.\-]+):\s*(#.*)?$")
FALLBACKS_RE = re.compile(r"^(?P<lead>\s+fallbacks:\s*)\[(?P<items>[^\]]*)\](?P<trail>\s*(#.*)?)$")


def _tiers_region(lines):
    start = None
    in_dispatch = False
    for i, line in enumerate(lines):
        if re.match(r"^dispatch:\s*(#.*)?$", line):
            in_dispatch = True
            continue
        if in_dispatch and re.match(r"^\S", line) and not line.startswith("#"):
            break
        if in_dispatch and re.match(r"^  tiers:\s*(#.*)?$", line):
            start = i + 1
            break
    if start is None:
        raise PatchError("dispatch.tiers not found in routing.yaml text")
    end = start
    while end < len(lines):
        line = lines[end]
        stripped = line.strip()
        if stripped and (len(line) - len(line.lstrip(" "))) < 4:
            break
        end += 1
    return start, end


def render_patched_text(base_text, removals, flags_by_seat):
    if not base_text.endswith("\n"):
        raise PatchError("routing.yaml does not end with a newline")
    lines = base_text.splitlines(keepends=True)
    start, end = _tiers_region(lines)
    headers = {}
    for i in range(start, end):
        m = TIER_HEADER_RE.match(lines[i].rstrip("\n"))
        if m:
            headers[m.group(1)] = i
    order = sorted(headers.values())
    block_end = {}
    for idx, h in enumerate(order):
        nxt = order[idx + 1] if idx + 1 < len(order) else end
        while nxt - 1 > h and not lines[nxt - 1].strip():
            nxt -= 1
        block_end[h] = nxt
    drop = set()
    for name in removals:
        if name not in headers:
            raise PatchError(f"tier {name} not found as a block in routing.yaml text")
        drop.update(range(headers[name], block_end[headers[name]]))
    replace = {}
    for i in range(start, end):
        if i in drop:
            continue
        stripped = lines[i].lstrip()
        if not stripped.startswith("fallbacks:"):
            continue
        m = FALLBACKS_RE.match(lines[i].rstrip("\n"))
        if not m:
            raise PatchError(f"line {i + 1}: fallbacks is not an inline list; P1 cannot edit it textually")
        items = [x.strip() for x in m.group("items").split(",") if x.strip()]
        kept = [x for x in items if x not in removals]
        if kept == items:
            continue
        replace[i] = f"{m.group('lead')}[{', '.join(kept)}]{m.group('trail')}\n" if kept else None
    insert = {}
    for name, comments in flags_by_seat.items():
        if name in headers and headers[name] not in drop:
            insert[headers[name]] = [f"    # {c}\n" for c in comments]
    out = []
    for i, line in enumerate(lines):
        if i in insert:
            out.extend(insert[i])
        if i in drop:
            continue
        if i in replace:
            if replace[i] is not None:
                out.append(replace[i])
            continue
        out.append(line)
    return "".join(out)


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def apply_unified_diff(base_text, diff_text):
    """Apply a unified diff with full context verification (B8)."""
    base = base_text.splitlines(keepends=True)
    lines = diff_text.splitlines(keepends=True)
    i = 0
    while i < len(lines) and not lines[i].startswith("--- "):
        i += 1
    if i == len(lines):
        return base_text
    if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
        raise PatchError("malformed diff header")
    i += 2
    out, pos = [], 0
    while i < len(lines):
        m = HUNK_RE.match(lines[i])
        if not m:
            raise PatchError(f"expected hunk header, got {lines[i]!r}")
        start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        src = start - 1 if count > 0 else start
        if src < pos:
            raise PatchError("overlapping hunks")
        out.extend(base[pos:src])
        pos = src
        i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            tag, body = lines[i][:1], lines[i][1:]
            if tag in (" ", "-"):
                if pos >= len(base) or base[pos] != body:
                    raise PatchError(f"context mismatch at base line {pos + 1}")
                if tag == " ":
                    out.append(body)
                pos += 1
            elif tag == "+":
                out.append(body)
            elif tag != "\\":
                raise PatchError(f"unexpected diff line {lines[i]!r}")
            i += 1
    out.extend(base[pos:])
    return "".join(out)


def _without_tiers(routing):
    r = copy.deepcopy(routing)
    (r.get("dispatch") or {}).pop("tiers", None)
    return r


def _is_subsequence(small, big):
    it = iter(big)
    return all(x in it for x in small)


def validate_patched(base, patched, families, producers, removals, allowed_head_changes):
    """Structural validation of the in-memory applied patch (B8, A3)."""
    v = []
    if not isinstance(patched, dict):
        return ["patched routing.yaml is not a mapping"]
    if ((patched.get("reasoning") or {}).get("frontier_models")) != ((base.get("reasoning") or {}).get("frontier_models")):
        v.append("frontier_models_edited")
    if _without_tiers(patched) != _without_tiers(base):
        v.append("non_tier_edit")
    btiers = (base.get("dispatch") or {}).get("tiers") or {}
    ptiers = (patched.get("dispatch") or {}).get("tiers") or {}
    for name in sorted(set(ptiers) - set(btiers)):
        v.append(f"seat_added:{name}")
    for name in sorted(set(btiers) - set(ptiers)):
        if name not in removals:
            v.append(f"seat_removed_without_decision:{name}")
    for name in sorted(set(ptiers) & set(btiers)):
        bt, pt = dict(btiers[name] or {}), dict(ptiers[name] or {})
        bfb, pfb = bt.pop("fallbacks", []) or [], pt.pop("fallbacks", []) or []
        if bt != pt:
            v.append(f"seat_edited:{name}")
        if not _is_subsequence(pfb, bfb):
            v.append(f"fallbacks_reordered_or_added:{name}")
        elif any(f not in pfb and f not in removals for f in bfb):
            v.append(f"fallback_dropped_without_removal:{name}")
    bworld, pworld = World(base, families), World(patched, families)
    for d in dangling_tier_refs(pworld):
        v.append(f"dangling:{d}")
    for name, seat in bworld.seats.items():
        if seat["family"] == "fable" and name not in ptiers:
            v.append(f"fable_canon_seat_removed:{name}")
    bheads, bchains = head_table(bworld, producers)
    pheads, pchains = head_table(pworld, producers)
    for k in changed_heads(bheads, pheads):
        if k not in allowed_head_changes:
            v.append(f"head_changed_without_gate:{k}")
    before = set(opus_last_violations(bworld, bchains))
    for x in opus_last_violations(pworld, pchains):
        if x not in before:
            v.append(f"opus_last:{x}")
    return v


# --------------------------------------------------------------------------
# The pipeline shared by the real run and --self-test
# --------------------------------------------------------------------------

def config_shape_problems(families, slugs_cfg, reorder_waivers):
    """N6: a list or scalar where a mapping is expected is a refusal with a
    diagnostic, never a traceback."""
    out = []
    if not isinstance(families, dict):
        return [f"roster-families.yaml top level is {type(families).__name__}, not a mapping"]
    if not isinstance(slugs_cfg, dict):
        return [f"roster-slugs.yaml top level is {type(slugs_cfg).__name__}, not a mapping"]
    if not isinstance(families.get("models") or {}, dict):
        out.append("roster-families.yaml `models` is not a mapping")
    else:
        for k, v in (families.get("models") or {}).items():
            if not isinstance(v, dict):
                out.append(f"roster-families.yaml models.{k} is not a mapping")
    if not isinstance(families.get("candidates") or [], list):
        out.append("roster-families.yaml `candidates` is not a list")
    if not isinstance(families.get("luna_class_evaluations") or {}, dict):
        out.append("roster-families.yaml `luna_class_evaluations` is not a mapping")
    for key in ("rows", "waivers"):
        items = slugs_cfg.get(key) or []
        if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
            out.append(f"roster-slugs.yaml `{key}` is not a list of mappings")
    if not isinstance(reorder_waivers or [], list):
        out.append("reorder waivers `waivers` is not a list")
    else:
        for i, w in enumerate(reorder_waivers or []):
            # N3: a reorder waiver is an mk decision, so it carries the same
            # approval fields as a RATIFIED registry waiver.
            if not isinstance(w, dict) or not isinstance(w.get("seat"), str):
                out.append(f"reorder waiver #{i} is not a mapping with a `seat` string")
            elif not w.get("approved_by") or not w.get("approval"):
                out.append(f"reorder waiver for {w['seat']} needs approved_by and an approval pointer")
    return out


def run_pipeline(routing_text, families, slugs_cfg, snapshot, now, reorder_waivers=None):
    res = {"promotion_ready": False, "status": "refused", "refusal": [], "messages": []}
    shape = config_shape_problems(families, slugs_cfg, reorder_waivers)
    if shape:
        raise Refusal(["config_corrupt"], shape)
    try:
        routing = yaml.safe_load(routing_text) or {}
    except yaml.YAMLError as exc:
        raise Refusal(["routing_corrupt"], [f"routing.yaml is corrupt: {exc}"])
    if not isinstance(routing, dict) or not isinstance((routing.get("dispatch") or {}).get("tiers"), dict):
        raise Refusal(["routing_corrupt"], ["routing.yaml has no dispatch.tiers mapping"])

    generated_at = (snapshot.get("meta") or {}).get("generatedAt") if isinstance(snapshot, dict) else None
    fstatus, deadline = freshness(generated_at, now)
    res["freshness"] = {"generatedAt": generated_at, "status": fstatus, "deadline": _iso(deadline),
                        "window_days": FRESHNESS_MAX_DAYS}
    if fstatus != "fresh":
        raise Refusal([fstatus], [
            f"snapshot is {fstatus} (generatedAt={generated_at!r}, window {FRESHNESS_MAX_DAYS} days, "
            f"deadline {_iso(deadline)}); no patch emitted"])

    snap_index = index_snapshot(snapshot)
    registry, gaps = resolve_registry(slugs_cfg, families, snap_index)
    mapping, unmapped = map_references(routing, families, registry)
    res.update({"mapping": mapping, "registry_gaps": [f"{k}: {r}" for k, r in gaps], "unmapped": unmapped})
    world = World(routing, families)
    codes, messages = [], []
    for key, reason in gaps:
        codes.append(f"registry:{key}")
        messages.append(f"registry gap: {key}: {reason}")
    for u in unmapped:
        codes.append(f"unmapped:{u}")
        messages.append(f"unmapped routing.yaml reference: {u} ({', '.join(mapping[u]['where'][:3])})")
    for d in dangling_tier_refs(world):
        codes.append(f"dangling:{d}")
        messages.append(f"dangling tier reference: {d}")
    for c in families.get("candidates") or []:
        if world.family(c) is None:
            codes.append(f"unknown_candidate:{c}")
            messages.append(f"candidate {c} has no roster-families.yaml entry")
    if codes:
        raise Refusal(codes, messages)

    luna_evals = families.get("luna_class_evaluations") or {}
    producers = producers_of(world, mapping, families)
    heads, chains = head_table(world, producers)
    entries, reach, failing = evaluate(world, producers, luna_evals)

    flags, remove_candidates, annotations = {}, [], set()
    for seat in sorted(reach):
        pairs = failing.get(seat, {})
        if not pairs:
            continue
        if set(pairs) == reach[seat]:
            remove_candidates.append(seat)
        flags[seat] = flag_strings(world, pairs)
        for (context, role, producer), fails in pairs.items():
            for rule, note in fails:
                if note.startswith(("m1", "m2")):
                    annotations.add(f"{seat} ({role}, {(world.family(producer) or {}).get('family')}-produced): {note}")

    removals, withheld, head_changes = gate_removals(
        routing, families, producers, remove_candidates, reorder_waivers)
    waived_changes = set()
    for seat in removals:
        waived_changes.update(head_changes.get(seat, []))

    rfu = set()
    for key, chain in chains.items():
        context, role, producer, scenario, fr = key.split("|")
        if role not in REVIEW_ROLES or producer == "-":
            continue
        pfam = (world.family(producer) or {}).get("family")
        for i, name in enumerate(chain):
            s = world.seats[name]
            if s["family"] == pfam and s["model"] != producer:
                where = "head" if i == 0 else "reachable"
                rfu.add(f"{producer} -> {name} ({s['model']}) in {role} [{where}, {scenario}]")
    candidate_a2, candidate_rfu = set(), set()
    for cand in families.get("candidates") or []:
        cfam = (world.family(cand) or {}).get("family")
        for context, role, head, _ in world.contexts():
            if role not in REVIEW_ROLES:
                continue
            for name in world.chain(head):
                s = world.seats[name]
                if s["family"] == cfam and s["model"] != cand:
                    candidate_rfu.add(cand)
                    candidate_a2.add(f"{cand}: refused as reviewer/validator in {role} while {name} ({s['model']}) is reachable; "
                                     f"refused as producer while {name} can review it")

    lint = {
        "m1": sorted(a for a in annotations if ": m1" in a),
        "m2": sorted(a for a in annotations if ": m2" in a),
        "rule2_no_astra_seat": [],
        "opus_last": opus_last_violations(world, chains),
        "fable_seats": sorted(n for n, s in world.seats.items() if s["family"] == "fable"),
        "cross_lab_first": world.cross_lab_first,
    }
    for key, chain in chains.items():
        context, role, producer, scenario, fr = key.split("|")
        if role in RULE2_ROLES and scenario == "nominal" and (world.family(producer) or {}).get("family") == "opus":
            if not any(world.seats[n]["family"] == "astra" for n in chain):
                lint["rule2_no_astra_seat"].append(f"{context}|{role}: no Astra seat for {producer}-produced work ({fr})")
    lint["rule2_no_astra_seat"] = sorted(set(lint["rule2_no_astra_seat"]))

    flag_comments = {}
    for seat, fl in flags.items():
        by_rule = {}
        for f in fl:
            rule, role, pfam = f.split("/")
            by_rule.setdefault(rule, []).append(f"{role}:{pfam}")
        status = "withheld removal" if seat in {w["seat"] for w in withheld} else "flag only"
        if seat in removals:
            continue
        flag_comments[seat] = [f"roster-lint FLAG ({status}, mk-rpnv.9 P1): {rule} [{', '.join(v)}]"
                               for rule, v in sorted(by_rule.items())]

    patched_text = render_patched_text(routing_text, removals, flag_comments)
    patched = yaml.safe_load(patched_text)
    if patched != apply_removals(routing, removals):
        raise Refusal(["patch_semantics"], ["textual patch does not match the semantic removal set"])
    diff = "".join(difflib.unified_diff(
        routing_text.splitlines(keepends=True), patched_text.splitlines(keepends=True),
        fromfile="a/config/routing.yaml", tofile="b/config/routing.yaml"))
    applied = apply_unified_diff(routing_text, diff)
    if applied != patched_text:
        raise Refusal(["patch_apply"], ["unified diff does not reproduce the patched text"])
    try:
        applied_doc = yaml.safe_load(applied)
    except yaml.YAMLError as exc:
        raise Refusal(["patch_yaml"], [f"patched routing.yaml does not parse: {exc}"])
    violations = validate_patched(routing, applied_doc, families, producers, removals, waived_changes)
    if violations:
        raise Refusal(["patch_validation"], [f"patch failed validation: {x}" for x in violations])
    pworld = World(applied_doc, families)
    pheads, _ = head_table(pworld, producers)

    res.update({
        "status": "ok",
        "producers": producers,
        "entries": entries,
        "flags": flags,
        "annotations": sorted(annotations),
        "removals": removals,
        "withheld": withheld,
        "heads": heads,
        "heads_changed": changed_heads(heads, pheads),
        "runtime_family_unenforced": sorted(rfu),
        "candidate_a2": sorted(candidate_a2),
        "candidate_rfu": sorted(candidate_rfu),
        "lint": lint,
        "diff": diff,
        "patched_yaml_parses": True,
        "patch_validation": violations,
        "schema_gaps": schema_gaps(routing, world, lint, mapping, producers, heads),
        "rules_reference": RULE_REFERENCES,
        "reorder_waivers": reorder_waivers or [],
    })
    return res


def inoperable_seats(world):
    """Kimi seats that set reasoning_effort: dispatch.sh:1053 rejects them as
    governed runs (bead mk-d3rf)."""
    return sorted(n for n, s in world.seats.items() if s["backend"] == "kimi" and s["effort"])


def schema_gaps(routing, world, lint, mapping, producers, heads):
    gaps = []
    if lint["rule2_no_astra_seat"]:
        gaps.append("Rule 2 cannot be met by removal or flag alone: a review chain lacks an Astra seat for "
                    "Opus-produced work, and P1 never adds seats.")
    gaps.append("Additions have no apply path through M1 (the generator never emits additions); a "
                "Promotable- or waiver-backed addition fails closed.")
    executors = sorted(r for r, m in mapping.items() if m.get("kind") in ("executor", "cloud"))
    if executors:
        gaps.append("executor_routing and the `cloud` keyword name no model: "
                    + ", ".join(f"`{r}` -> {mapping[r].get('model')} ({mapping[r]['status']})" for r in executors)
                    + " are host-default mappings from explicit waivers, true only for the host whose config they cite.")
    if "codex" in ((((routing.get("executor_routing") or {}).get("classes") or {}).get("reasoning")) or []):
        gaps.append("The `reasoning: [codex]` comment cites a Luna-only parity eval (FLUXrig-92u), which is not "
                    "evidence for the model the executor actually runs.")
    inop = inoperable_seats(world)
    for name in inop:
        gaps.append(f"{name} is INOPERABLE as a governed seat: scripts/dispatch.sh:1053 rejects governed "
                    f"Kimi runs that set reasoning_effort (bead mk-d3rf). routing.yaml is not changed.")
    # N10: an inoperable effective head leaves that pair without a working head.
    dead = sorted(k for k, h in heads.items() if h in inop and k.split("|")[0] == "default"
                  and k.split("|")[4] == "default")
    for k in dead:
        context, role, producer, scenario, _ = k.split("|")
        gaps.append(f"{role} for {producer}-produced work under {scenario}: the effective head is "
                    f"{heads[k]}, which is INOPERABLE, so that pair has no working head.")
    # N7: explicit --tier contexts bypass intercore producer exclusion.
    for context, role, head, _ in world.contexts():
        if not context.startswith("tier:"):
            continue
        selfrev = sorted(p for p in producers if p in {world.seats[n]["model"] for n in world.chain(head)})
        if selfrev:
            gaps.append(f"{context} ({role}) bypasses producer exclusion: {', '.join(selfrev)}-produced work can "
                        f"be reviewed by the same model along its fallback chain (known gap; the generator mirrors dispatch --tier).")
    return gaps


# --------------------------------------------------------------------------
# Outputs
# --------------------------------------------------------------------------

def _heads_summary(res):
    rows = []
    for key in sorted(res["heads"]):
        context, role, producer, scenario, fr = key.split("|")
        if context != "default" or fr != "default":
            continue
        rows.append((role, producer, scenario, res["heads"][key]))
    return rows


def write_outputs(out_dir, res, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    eligibility = {
        "promotion_ready": False,
        "status": res["status"],
        "fixer": FIXER,
        **meta,
        "freshness": res.get("freshness"),
        "mapping": res.get("mapping"),
        "entries": res["entries"],
        "flags": res["flags"],
        "removals": res["removals"],
        "withheld": res["withheld"],
        "runtime_family_unenforced": res["runtime_family_unenforced"],
        "candidate_a2": res["candidate_a2"],
        "lint": res["lint"],
        "schema_gaps": res["schema_gaps"],
        "heads_changed": res["heads_changed"],
        "rules_reference": RULE_REFERENCES,
    }
    (out_dir / "eligibility.json").write_text(json.dumps(eligibility, indent=2, sort_keys=True) + "\n")

    world_seats = res["_world"].seats
    mapping = res["mapping"]
    seats = []
    for name, s in sorted(world_seats.items()):
        ref = f"{s['model']}@{s['effort'] or 'unset'}"
        m = mapping.get(ref, {})
        seats.append({"seat": name, "role": s["role"], "lab": s["lab"], "family": s["family"],
                      "exact_version": s["model"], "effort": s["effort"], "snapshot_slug": m.get("slug"),
                      "mapping": m.get("status"), "evidence": "unevaluated"})
    cands = []
    fam_models = res["_families"].get("models") or {}
    for c in res["_families"].get("candidates") or []:
        f = fam_models.get(c, {})
        rows = sorted(r["slug"] for r in res["_snap_index"].values()
                      if r["base_name"] == f.get("snapshot_name") and not r["is_provider_duplicate"]
                      and not r["is_latest_alias"] and not r["is_composite"] and not r["unrecognised_qualifiers"])
        cands.append({"candidate": c, "lab": f.get("lab"), "family": f.get("family"), "exact_version": c,
                      "snapshot_rows": rows, "evidence": "unevaluated",
                      "runtime_family_unenforced": c in res["candidate_rfu"]})
    roster = {"promotion_ready": False, **meta, "seats": seats, "candidates": cands,
              "note": "Ties are kept; no weighted score is computed."}
    (out_dir / "roster.generated.json").write_text(json.dumps(roster, indent=2, sort_keys=True) + "\n")

    header = [
        "# routing.proposed.patch -- generated in memory, never applied. promotion_ready: false",
        f"# base config/routing.yaml sha256 {meta['base_sha256']}; snapshot sha256 {meta['snapshot_sha256']}",
        f"# families sha256 {meta['families_sha256']}; slugs sha256 {meta['slugs_sha256']}; "
        f"reorder waivers sha256 {meta['reorder_waivers_sha256'] or 'none'}",
        f"# removals: {', '.join(res['removals']) or 'none'}; flagged seats: {', '.join(sorted(res['flags'])) or 'none'}",
        "",
    ]
    (out_dir / "routing.proposed.patch").write_text("\n".join(header) + res["diff"])
    (out_dir / "report.md").write_text(render_report(res, meta))


def render_report(res, meta):
    L = []
    a = L.append
    a("# mk-rpnv.9 P1 roster generate -- report")
    a("")
    a(f"- **Fixer:** {FIXER}. This P1 fix pass was written by Claude Opus 5.5 at mk's choice.")
    a(f"- base `config/routing.yaml` sha256: `{meta['base_sha256']}` (matches `--expect-base`)")
    a(f"- snapshot sha256: `{meta['snapshot_sha256']}` (pinned, verified); generatedAt "
      f"`{res['freshness']['generatedAt']}`; freshness deadline **{res['freshness']['deadline']}**")
    a("- promotion_ready: **false** (every output). M1 never applies the patch.")
    a("")
    a(f"- inputs sha256: families `{meta['families_sha256']}`, slugs `{meta['slugs_sha256']}`, "
      f"reorder waivers `{meta['reorder_waivers_sha256'] or 'none'}`")
    a("")
    mapping = res["mapping"]
    pending = [(r, m) for r, m in sorted(mapping.items()) if m.get("status") == "waiver-proposed"]
    ratified = [(r, m) for r, m in sorted(mapping.items()) if m.get("status") == "waiver-ratified"]
    a("## mk decisions applied")
    a("")
    a("- **STRICT:** every model string routing.yaml references (tiers, aliases, frontier_models, subagents, "
      "complexity overrides, executors, the `cloud` keyword, local models) must be mapped or waived before a "
      "patch is emitted; anything unmapped is a refusal. Executors map only through an explicit row or waiver.")
    for ref, m in ratified:
        a(f"- **Waiver RATIFIED by {m.get('approved_by')}** ({m.get('approval')}): `{ref}` maps to snapshot row "
          f"`{m['slug']}` ({m['row_name']}), labelled \"{m.get('label')}\". Evidence: {' / '.join(m.get('evidence') or [])}")
    if not ratified:
        a("- Ratified mk waivers: none.")
    for name in inoperable_seats(res["_world"]):
        a(f"- **{name} is INOPERABLE:** `scripts/dispatch.sh:1053` rejects governed Kimi runs that set an "
          "effort (bead mk-d3rf). routing.yaml is unchanged.")
    a(f"- **{len(pending)} waiver(s) PROPOSED** in `config/roster-slugs.yaml`, listed below. "
      + ("P1 is not accepted until mk ratifies them." if pending else "None are pending."))
    a("")
    a("## Waivers pending mk")
    a("")
    a("| Reference | Snapshot row | Label and caveats | Evidence |")
    a("|---|---|---|---|")
    for ref, m in pending:
        cav = [m.get("label") or "(no label)"] + list(m.get("caveats") or [])
        if m.get("fallback_ref"):
            cav.append(f"fallback producer `{m['fallback_ref']}` ({m.get('fallback_model')})")
        a(f"| `{ref}` | `{m['slug']}` ({m['row_name']}) | {' / '.join(cav)} | {' / '.join(m.get('evidence') or [])} |")
    if not pending:
        a("| (none) | | | |")
    a("")
    a("## Reference coverage (STRICT)")
    a("")
    a("| Reference | Status | Row / via |")
    a("|---|---|---|")
    for ref, m in sorted(mapping.items()):
        a(f"| `{ref}` | {m['status']} | {m.get('slug') or ', '.join(m.get('via') or [])} |")
    a("")
    caveated = [(r, m) for r, m in sorted(mapping.items())
                if m.get("status") in ("exact", "waiver-ratified") and m.get("caveats")]
    for ref, m in caveated:
        a(f"Mapping caveat, `{ref}`: {' / '.join(m['caveats'])}")
    if caveated:
        a("")
    a("## Proposed patch (remove or flag only)")
    a("")
    a(f"- Removals: {', '.join(res['removals']) or 'none'}")
    for w in res["withheld"]:
        a(f"- Withheld removal `{w['seat']}`: gates {', '.join(w['gates'])}")
    a(f"- Effective-head changes after the patch: {len(res['heads_changed'])}")
    a(f"- `validation-sol` removed: {'yes' if 'validation-sol' in res['removals'] else 'no'}")
    a("- Flags (seat: rule/role/producer-family):")
    for seat, fl in sorted(res["flags"].items()):
        a(f"  - `{seat}`: {', '.join(fl)}")
    if not res["flags"]:
        a("  - (none)")
    for rw in res["reorder_waivers"]:
        a(f"- Reorder waiver recorded: {rw}")
    a("")
    a("## Lint of the current chains")
    a("")
    a("- **m1 (existing conflict):** " + ("; ".join(res["lint"]["m1"]) or "none"))
    a("- **m2 (declared same-lab downgrade):** " + ("; ".join(res["lint"]["m2"]) or "none"))
    a("- **Rule 2 (plan-review, cross-lab-review; n4):** " + ("; ".join(res["lint"]["rule2_no_astra_seat"]) or "every chain has an Astra seat")
      + ". In cross_lab_first roles (" + ", ".join(res["lint"]["cross_lab_first"]) + ") rule 2 is this chain-level "
      "lint only; per-seat rule-2 flags there are the Fable m2 downgrade alone (n4, mk 2026-09-25).")
    a("- **Rule 1 scope:** applied to every review role (" + ", ".join(REVIEW_ROLES) + "), plan-review included, "
      "which is broader than the plan's \"validated by\" wording.")
    a("- **Opus-last (no Opus ahead of a frontier_models seat; no Opus added to frontier_models):** "
      + ("; ".join(res["lint"]["opus_last"]) or "holds") + ". `validation-opus` as validation primary is allowed.")
    a(f"- **Fable canon seat (r7):** fable seats kept: {', '.join(res['lint']['fable_seats']) or 'none'}")
    a(f"- **cross_lab_first (2026-09-24):** {', '.join(res['lint']['cross_lab_first'])}; treated as a routing-order rule.")
    a("- **Rule 5 (Luna):** " + (", ".join(f for fl in res["flags"].values() for f in fl if f.startswith("rule5")) or
                                  "no Luna seat in routing.yaml; keyed on mapped family, never a name fragment"))
    a("- **Rule 6 (relay):** " + (", ".join(f"{s}: {f}" for s, fl in res["flags"].items() for f in fl if f.startswith("rule6")) or "holds"))
    a("")
    a("## Effective heads (default context, per role and producer)")
    a("")
    a("| Role | Producer | nominal | sol-unavailable | openai-unavailable |")
    a("|---|---|---|---|---|")
    grouped = {}
    for role, producer, scenario, head in _heads_summary(res):
        grouped.setdefault((role, producer), {})[scenario] = head
    inop = set(inoperable_seats(res["_world"]))

    def cell(h):
        return f"{h} (INOPERABLE)" if h in inop else f"{h}"
    for (role, producer), sc in sorted(grouped.items()):
        a(f"| {role} | {producer} | {cell(sc.get('nominal'))} | {cell(sc.get('sol-unavailable'))} | "
          f"{cell(sc.get('openai-unavailable'))} |")
    a("")
    a("## runtime_family_unenforced (A2, along effective chains)")
    a("")
    for x in res["runtime_family_unenforced"]:
        a(f"- {x}")
    if not res["runtime_family_unenforced"]:
        a("- (none)")
    a("")
    a("## New candidates (unevaluated; report only, never added)")
    a("")
    for x in res["candidate_a2"]:
        a(f"- {x}")
    if not res["candidate_a2"]:
        a("- (none)")
    a("")
    a("## Conflicts and schema gaps")
    a("")
    a("- **m3:** Astra is both the promotion reviewer and a coordinator candidate. mk's ruling covers this conflict.")
    for g in res["schema_gaps"]:
        a(f"- {g}")
    a("")
    a("## Rules 3, 4, 7 (references only)")
    a("")
    for rule, ref in sorted(RULE_REFERENCES.items()):
        a(f"- Rule {rule}: enforced_by {ref['enforced_by']}; status {ref['status']}")
    return "\n".join(L) + "\n"


def write_refusal(out_dir, refusal, meta, partial):
    out_dir.mkdir(parents=True, exist_ok=True)
    # N5: a refusal replaces every output of an earlier run; no stale patch
    # or roster survives next to the refusal record.
    for name in ("routing.proposed.patch", "roster.generated.json"):
        stale = out_dir / name
        if stale.exists():
            stale.unlink()
    doc = {"promotion_ready": False, "status": "refused", "fixer": FIXER, **meta,
           "refusal": refusal.codes, "messages": refusal.messages,
           "freshness": partial.get("freshness"), "mapping": partial.get("mapping"),
           "registry_gaps": partial.get("registry_gaps"), "unmapped": partial.get("unmapped")}
    (out_dir / "eligibility.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    lines = ["# mk-rpnv.9 P1 roster generate -- diagnostic (no patch emitted)", "",
             f"- Fixer: {FIXER}", "- promotion_ready: false", ""]
    lines += [f"- {k}: `{v}`" for k, v in sorted(meta.items())]
    lines += ["", "## Refused", ""] + [f"- {m}" for m in refusal.messages]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------
# Real run
# --------------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def diagnostic(message, code=2):
    print(f"generate: {message}", file=sys.stderr)
    return code


def load_yaml_file(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class EarlyRefusal(Exception):
    """A refusal before the pipeline runs (hash mismatch, missing or corrupt
    input). N5: it still writes a refusal record, so an earlier run's
    report.md and eligibility.json never stay in --out looking current."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def run_generate(args):
    routing_path = Path(args.routing)
    if not routing_path.exists():
        return diagnostic(f"routing file not found: {routing_path}")
    base_sha = sha256_file(routing_path)
    out_dir = Path(args.out)
    rc = 1
    try:
        rc = _run_generate(args, routing_path, base_sha)
    except EarlyRefusal as exc:
        write_refusal(out_dir, Refusal([exc.code], [exc.message]), {"base_sha256": base_sha}, {})
        rc = diagnostic(exc.message)
    finally:
        # N4: the post-run base check runs on every path, refusals included.
        if sha256_file(routing_path) != base_sha:
            msg = "routing.yaml hash changed during the run -- this must never happen"
            write_refusal(out_dir, Refusal(["base_changed"], [msg]), {"base_sha256": base_sha}, {})
            rc = diagnostic(msg, code=1)
        if rc != 0:
            # A refusal never leaves an earlier run's proposal behind.
            for name in ("routing.proposed.patch", "roster.generated.json"):
                stale = out_dir / name
                if stale.exists():
                    stale.unlink()
    return rc


def _run_generate(args, routing_path, base_sha):
    if base_sha != args.expect_base:
        raise EarlyRefusal("expect_base", f"--expect-base mismatch: routing.yaml is {base_sha}, "
                                          f"approval record expects {args.expect_base}")
    for label, p in (("families", args.families), ("slugs", args.slugs), ("snapshot", args.snapshot),
                     ("reorder waivers", args.reorder_waivers)):
        if p is not None and not Path(p).exists():
            raise EarlyRefusal("input_missing", f"{label} file not found: {p}")
    try:
        families = load_yaml_file(args.families)
        slugs_cfg = load_yaml_file(args.slugs)
        reorder_doc = load_yaml_file(args.reorder_waivers) if args.reorder_waivers else {}
    except yaml.YAMLError as exc:
        raise EarlyRefusal("config_corrupt", f"families/slugs/waiver config is corrupt: {exc}")
    if not isinstance(reorder_doc, dict):
        raise EarlyRefusal("config_corrupt", "reorder waivers top level is not a mapping")
    reorder_waivers = reorder_doc.get("waivers") or []
    actual = sha256_file(args.snapshot)
    if actual != args.snapshot_sha256:
        raise EarlyRefusal("snapshot_sha256",
            "snapshot sha256 mismatch: refusing unpinned/unverified input "
            f"(expected {args.snapshot_sha256}, got {actual}). "
            "The expected value must come from the plan record, never from hashing the copy.")
    try:
        with open(args.snapshot, encoding="utf-8") as fh:
            snapshot = json.load(fh)
    except json.JSONDecodeError as exc:
        raise EarlyRefusal("snapshot_corrupt", f"snapshot is corrupt (invalid JSON): {exc}")
    if not isinstance(snapshot, dict):
        raise EarlyRefusal("snapshot_corrupt", "snapshot is corrupt (not a JSON object)")
    routing_text = routing_path.read_text(encoding="utf-8")
    meta = {"base_sha256": base_sha, "snapshot_sha256": actual, "snapshot_path": str(args.snapshot),
            "families_sha256": sha256_file(args.families), "slugs_sha256": sha256_file(args.slugs),
            "reorder_waivers_sha256": sha256_file(args.reorder_waivers) if args.reorder_waivers else None}
    out_dir = Path(args.out)
    now = datetime.now(timezone.utc)  # no override outside --self-test (A1)
    partial = {}
    try:
        res = run_pipeline(routing_text, families, slugs_cfg, snapshot, now, reorder_waivers)
    except Refusal as ref:
        # Recompute the cheap diagnostic context for the refusal record.
        fstatus, deadline = freshness((snapshot.get("meta") or {}).get("generatedAt"), now)
        partial["freshness"] = {"status": fstatus, "deadline": _iso(deadline)}
        try:
            idx = index_snapshot(snapshot)
            registry, gaps = resolve_registry(slugs_cfg, families, idx)
            mapping, unmapped = map_references(yaml.safe_load(routing_text) or {}, families, registry)
            partial.update({"mapping": mapping, "registry_gaps": [f"{k}: {r}" for k, r in gaps],
                            "unmapped": unmapped})
        except (Refusal, yaml.YAMLError, AttributeError, KeyError, TypeError):
            pass
        write_refusal(out_dir, ref, meta, partial)
        return diagnostic("refused, no patch emitted: " + "; ".join(ref.messages))
    except PatchError as exc:
        write_refusal(out_dir, Refusal(["patch_error"], [str(exc)]), meta, partial)
        return diagnostic(f"refused, patch could not be built: {exc}")
    res["_world"] = World(yaml.safe_load(routing_text), families)
    res["_families"] = families
    res["_snap_index"] = index_snapshot(snapshot)
    write_outputs(out_dir, res, meta)
    print(f"generate: wrote eligibility.json, roster.generated.json, routing.proposed.patch, report.md to {out_dir} "
          f"(removals: {len(res['removals'])}, flagged seats: {len(res['flags'])}, head changes: {len(res['heads_changed'])})")
    return 0


# --------------------------------------------------------------------------
# --self-test: end-to-end truth table (B9)
# --------------------------------------------------------------------------

def _merge_registry(base, patch):
    out = copy.deepcopy(base)
    for key in ("rows", "waivers"):
        drop = set((patch or {}).get(f"{key}_drop") or [])
        items = [x for x in out.get(key) or [] if (x.get("ref") or f"{x.get('model')}@{x.get('effort')}") not in drop]
        out[key] = items + list((patch or {}).get(f"{key}_add") or [])
    return out


def _case_inputs(case, defaults, root):
    if "routing_file" in case:
        routing_text = (root / case["routing_file"]).read_text(encoding="utf-8")
    else:
        routing_text = case["routing"]
    families = (load_yaml_file(root / case["families_file"]) if "families_file" in case
                else copy.deepcopy(defaults["families"]))
    for k, v in (case.get("families_patch") or {}).items():
        if k == "models":
            families.setdefault("models", {}).update(v)
        else:
            families[k] = v
    slugs = (load_yaml_file(root / case["slugs_file"]) if "slugs_file" in case
             else copy.deepcopy(defaults["slugs"]))
    slugs = _merge_registry(slugs, case.get("slugs_patch"))
    models = [m for m in defaults["snapshot_models"] if m["slug"] not in set(case.get("snapshot_drop") or [])]
    models += case.get("snapshot_add") or []
    meta = {"generatedAt": case.get("generatedAt", defaults["generatedAt"])}
    if case.get("generatedAt_absent"):
        meta.pop("generatedAt")
    snapshot = {"meta": meta, "models": models}
    now = _parse_timestamp(case.get("now", defaults["now"]))
    return routing_text, families, slugs, snapshot, now


def _check(expect, got):
    """Compare the pipeline result against plan-derived expectations."""
    errs = []

    def eq(name, want, have):
        if want != have:
            errs.append(f"{name}: expected {want!r}, got {have!r}")

    def includes(name, want, have):
        missing = [w for w in want if not any(w == h or (isinstance(h, str) and w in h) for h in have)]
        if missing:
            errs.append(f"{name}: missing {missing!r} in {have!r}")

    def excludes(name, want, have):
        present = [w for w in want if any(w == h or (isinstance(h, str) and w in h) for h in have)]
        if present:
            errs.append(f"{name}: unexpected {present!r}")

    def fields(name, want, have, sep, keep):
        # N9: structured match on sep-delimited fields, so "rule2" matches the
        # rule2 flags and never "rule2_no_astra_seat".
        def hit(w, h):
            return isinstance(h, str) and h.split(sep)[:len(w.split(sep))] == w.split(sep)
        bad = [w for w in want if any(hit(w, h) for h in have) != keep]
        if bad:
            errs.append(f"{name}: {'missing' if keep else 'unexpected'} {bad!r} in {have!r}")

    for key, want in expect.items():
        if key == "status":
            eq(key, want, got["status"])
        elif key == "refusal_include":
            fields(key, want, got.get("refusal", []), ":", True)
        elif key == "refusal_exclude":
            fields(key, want, got.get("refusal", []), ":", False)
        elif key == "messages_include":
            includes(key, want, got.get("messages", []))
        elif key == "removals":
            eq(key, want, got.get("removals"))
        elif key == "withheld":
            eq(key, want, {w["seat"]: w["gates"] for w in got.get("withheld", [])})
        elif key == "flags":
            eq(key, want, got.get("flags"))
        elif key == "flags_include":
            for seat, items in want.items():
                fields(f"flags[{seat}]", items, got.get("flags", {}).get(seat, []), "/", True)
        elif key == "flags_exclude":
            for seat, items in want.items():
                fields(f"flags[{seat}]", items, got.get("flags", {}).get(seat, []), "/", False)
        elif key == "not_flagged":
            fields(key, want, list(got.get("flags", {})), "\0", False)
        elif key == "not_removed":
            fields(key, want, got.get("removals", []), "\0", False)
        elif key == "annotations_include":
            includes(key, want, got.get("annotations", []))
        elif key == "rfu_include":
            includes(key, want, got.get("runtime_family_unenforced", []))
        elif key == "rfu_empty":
            eq(key, want, not got.get("runtime_family_unenforced"))
        elif key == "candidate_a2_include":
            includes(key, want, got.get("candidate_a2", []))
        elif key == "heads":
            for k, v in want.items():
                eq(f"heads[{k}]", v, got.get("heads", {}).get(k, "<absent>"))
        elif key == "heads_changed":
            eq(key, want, got.get("heads_changed"))
        elif key == "lint_include":
            for lk, items in want.items():
                includes(f"lint.{lk}", items, got.get("lint", {}).get(lk, []))
        elif key == "lint_empty":
            for lk in want:
                eq(f"lint.{lk} empty", True, not got.get("lint", {}).get(lk))
        elif key == "mapping":
            for ref, status in want.items():
                eq(f"mapping[{ref}]", status, (got.get("mapping", {}).get(ref) or {}).get("status"))
        elif key == "diff_include":
            includes(key, want, got.get("diff", "").splitlines())
        elif key == "diff_empty":
            eq(key, want, got.get("diff", "") == "")
        elif key == "violations_include":
            includes(key, want, got.get("violations", []))
        elif key == "violations":
            eq(key, want, got.get("violations"))
        elif key == "rules_reference":
            eq(key, want, got.get("rules_reference"))
        elif key == "schema_gaps_include":
            includes(key, want, got.get("schema_gaps", []))
        elif key == "schema_gaps_exclude":
            excludes(key, want, got.get("schema_gaps", []))
        elif key == "mapping_field":
            for ref, kv in want.items():
                for field, v in kv.items():
                    eq(f"mapping[{ref}].{field}", v, (got.get("mapping", {}).get(ref) or {}).get(field))
        elif key == "producers_include":
            fields(key, want, got.get("producers", []), "\0", True)
        else:
            errs.append(f"unknown expectation key {key!r}")
    return errs


def run_self_test(truth_table_path):
    path = Path(truth_table_path)
    table = json.loads(path.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[2]
    defaults = table["defaults"]
    failures = []
    for case in table.get("cases", []):
        try:
            routing_text, families, slugs, snapshot, now = _case_inputs(case, defaults, root)
            if case.get("kind") == "validate":
                # An attempted edit (reorder, addition, frontier_models edit)
                # fed straight to the validator every real patch must pass.
                base = yaml.safe_load(routing_text)
                patched = yaml.safe_load(case["patched"])
                producers = producers_of(World(base, families), {}, families)
                got = {"status": "ok", "violations": validate_patched(
                    base, patched, families, producers, case.get("removals", []), set())}
            else:
                try:
                    got = run_pipeline(routing_text, families, slugs, snapshot, now, case.get("reorder_waivers"))
                except Refusal as ref:
                    got = {"status": "refused", "refusal": ref.codes, "messages": ref.messages}
        except Exception as exc:  # noqa: BLE001 -- report, don't crash the suite
            failures.append((case["id"], f"raised {exc!r}"))
            continue
        errs = _check(case["expect"], got)
        if errs:
            failures.append((case["id"], "; ".join(errs)))
    total = len(table.get("cases", []))
    print(f"self-test: {total - len(failures)}/{total} cases passed")
    for case_id, msg in failures:
        print(f"  FAIL {case_id}: {msg}", file=sys.stderr)
    return 0 if not failures else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", metavar="TRUTH_TABLE", help="run the truth-table fixture and exit")
    parser.add_argument("--routing", help="path to routing.yaml")
    parser.add_argument("--families", help="path to config/roster-families.yaml")
    parser.add_argument("--slugs", help="path to config/roster-slugs.yaml")
    parser.add_argument("--snapshot", help="explicit local snapshot path (no default, no network)")
    parser.add_argument("--snapshot-sha256", help="expected sha256 of --snapshot, from the plan record")
    parser.add_argument("--expect-base", help="expected sha256 of --routing, from the approval record (required)")
    parser.add_argument("--out", help="output directory")
    parser.add_argument("--reorder-waivers", help="optional YAML of mk waivers / Promotable results for head-changing removals")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test(args.self_test)

    required = ["routing", "families", "slugs", "snapshot", "snapshot_sha256", "expect_base", "out"]
    missing = [f"--{r.replace('_', '-')}" for r in required if getattr(args, r) is None]
    if missing:
        parser.print_usage(sys.stderr)
        print(f"generate: missing required arguments for a generate run: {', '.join(missing)}", file=sys.stderr)
        return 1
    return run_generate(args)


if __name__ == "__main__":
    sys.exit(main())
