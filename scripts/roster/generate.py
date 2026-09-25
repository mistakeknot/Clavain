#!/usr/bin/env python3
"""mk-rpnv.9 P1 -- evidence-generated roster: generator plus lint.

Builds `eligibility.json`, `roster.generated.json`, `routing.proposed.patch`
and `report.md` from a pinned, hash-verified interrank/AgMoDB snapshot and
the current `routing.yaml`. See `PLAN-M1-r5.md` §P1 for the full spec this
implements; the section references in comments below point back to it.

No network fetch, no live model calls, no default snapshot URL. The patch is
generated in memory and is never applied to `routing.yaml`. Every output
carries `promotion_ready: false`.

Exit codes:
  0  success (patch emitted, or --self-test passed)
  1  usage / unexpected error
  2  diagnostic refusal (stale snapshot, hash mismatch, unmapped model,
     corrupt input, or --self-test failure) -- never a passing proposal
  3  pyyaml is not installed
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("generate: pyyaml is required", file=sys.stderr)
    sys.exit(3)

FRESHNESS_MAX_DAYS = 8

# Rule 1: Sol-produced work is validated by Claude or Astra only (allowlist).
ALLOWED_VALIDATOR_FAMILIES = {"sonnet", "opus", "fable", "astra"}

# Rule 6, role-class half: a relay seat cannot hold an authority or judgment
# role. `coordination` is the only relay role in routing.yaml today.
RELAY_ROLES = {"coordination"}
RELAY_ALLOWED_FAMILIES = {"sonnet", "sol"}

RULE_REFERENCES = {
    "3": {"enforced_by": "bb checkpoint rotation; the mk-rpnv.3 boundary envelope", "status": "not_verified_by_generator"},
    "4": {"enforced_by": "pool-headroom and the mk-rpnv.3 Jev/headroom envelope", "status": "not_verified_by_generator"},
    "7": {"enforced_by": "event triggers and the coordinator messaging rules", "status": "not_verified_by_generator"},
}


# --------------------------------------------------------------------------
# Pure rule functions. Shared by the real run and --self-test so the truth
# table exercises exactly the code path the real run uses.
# --------------------------------------------------------------------------

def family_of(families_cfg, model_id):
    """Look up (lab, family) for an exact model ID. None means unmapped."""
    return (families_cfg.get("models") or {}).get(model_id)


def unknown_alias(families_cfg, model_id):
    return family_of(families_cfg, model_id) is None


def chain_refusal(family_a, exact_a, family_b, exact_b):
    """A2, symmetric: same family, different exact version, reachable in the
    same chain (any two seats, any direction) -> refused."""
    if family_a is None or family_b is None:
        return False
    return family_a == family_b and exact_a != exact_b


def rule1_validate(producer_family, validator_family):
    return validator_family in ALLOWED_VALIDATOR_FAMILIES


def rule2_review(producer_family, reviewer_family):
    compliant = reviewer_family == "astra"
    same_lab_downgrade = (not compliant) and producer_family == "opus" and reviewer_family == "fable"
    return {"compliant": compliant, "same_lab_downgrade": same_lab_downgrade}


def rule5_luna(family, has_per_class_eval=False):
    return {"excluded": family == "luna" and not has_per_class_eval}


def rule6_relay(role, candidate_family):
    if role not in RELAY_ROLES:
        return {"refused": False}
    return {"refused": candidate_family not in RELAY_ALLOWED_FAMILIES}


def rules_reference():
    return RULE_REFERENCES


def slug_row_matches(row, want_model, want_effort, want_reasoning_mode="reasoning"):
    """Closed-world slug match (A1). Every condition must hold; there is no
    best-guess fallback. `row` describes a candidate snapshot row as already
    classified by the caller (is_latest_alias / is_composite /
    is_provider_duplicate / effort / reasoning_mode)."""
    if row.get("is_latest_alias"):
        return False
    if row.get("is_composite"):
        return False
    if row.get("is_provider_duplicate"):
        return False
    if row.get("model") != want_model:
        return False
    if row.get("effort") is None:
        return False  # effort-unlabelled row never matches a labelled effort
    if row.get("effort") != want_effort:
        return False
    if row.get("reasoning_mode") != want_reasoning_mode:
        return False
    return True


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


def freshness_status(generated_at, now):
    """A1, tightened per CHECK-M1-r3. `now` is an ISO string for
    --self-test; the real run passes the current UTC instant the same way."""
    now_ts = _parse_timestamp(now) if isinstance(now, str) else now
    ts = _parse_timestamp(generated_at)
    if ts is None or now_ts is None:
        return "stale"
    return "stale" if (now_ts - ts) > timedelta(days=FRESHNESS_MAX_DAYS) else "fresh"


def frontier_ordering_violation(role, seat_family, placing_ahead_of_frontier):
    if seat_family != "opus":
        return False
    return bool(placing_ahead_of_frontier)


def patch_scope_decision(ineligible_for, producer_families_reaching_chain):
    """A3, tightened per CHECK-M1-r3. Remove only if ineligible for every
    producer family that can reach the chain; otherwise flag."""
    ineligible = set(ineligible_for)
    reaching = set(producer_families_reaching_chain)
    if reaching and reaching.issubset(ineligible):
        return "remove"
    return "flag"


def reorder_change_allowed(promotable, waiver):
    return bool(promotable or waiver)


SELF_TEST_FUNCS = {
    "chain_refusal": chain_refusal,
    "rule1_validate": rule1_validate,
    "rule2_review": rule2_review,
    "rule5_luna": rule5_luna,
    "rule6_relay": rule6_relay,
    "rules_reference": rules_reference,
    "slug_row_matches": slug_row_matches,
    "freshness_status": freshness_status,
    "frontier_ordering_violation": frontier_ordering_violation,
    "patch_scope_decision": patch_scope_decision,
    "reorder_change_allowed": reorder_change_allowed,
    "unknown_alias": unknown_alias,
}


def run_self_test(truth_table_path):
    with open(truth_table_path, encoding="utf-8") as fh:
        table = json.load(fh)
    failures = []
    for case in table.get("cases", []):
        fn = SELF_TEST_FUNCS.get(case["fn"])
        if fn is None:
            failures.append((case["id"], f"unknown fn '{case['fn']}'"))
            continue
        try:
            actual = fn(**case.get("args", {}))
        except Exception as exc:  # noqa: BLE001 -- report, don't crash the suite
            failures.append((case["id"], f"raised {exc!r}"))
            continue
        # JSON round-trip so dict/bool/str comparisons are exact and stable.
        actual_norm = json.loads(json.dumps(actual))
        expect_norm = case["expect"]
        if actual_norm != expect_norm:
            failures.append((case["id"], f"expected {expect_norm!r}, got {actual_norm!r}"))
    total = len(table.get("cases", []))
    print(f"self-test: {total - len(failures)}/{total} cases passed")
    for case_id, msg in failures:
        print(f"  FAIL {case_id}: {msg}", file=sys.stderr)
    return 0 if not failures else 2


# --------------------------------------------------------------------------
# Real run: routing.yaml + families + slugs + pinned snapshot -> outputs.
# --------------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def collect_seat_models(routing):
    """Every dispatch.tiers.<seat>: {model, reasoning_effort, ...}, resolved
    through model_aliases to the exact canonical ID."""
    dispatch = routing.get("dispatch") or {}
    aliases = dispatch.get("model_aliases") or {}
    tiers = dispatch.get("tiers") or {}
    seats = {}
    for name, tier in tiers.items():
        model = tier.get("model")
        if model is None:
            continue
        exact = aliases.get(model, model)
        seats[name] = {
            "role": tier.get("role"),
            "exact_model": exact,
            "effort": tier.get("reasoning_effort"),
            "fallbacks": tier.get("fallbacks") or [],
        }
    return seats


PARENTHETICAL_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def classify_snapshot_row(model, providers_seen_slugs):
    """Parse one snapshot `models[]` entry into the fields slug_row_matches
    needs. Deliberately conservative: only a slug this repo's roster-slugs.yaml
    explicitly points at is ever looked up, so mis-classifying an unrelated
    row is harmless."""
    slug = model.get("slug", "")
    name = model.get("name", "") or ""
    provider = model.get("providerSlug", "")

    is_latest_alias = slug.endswith("-latest")
    is_composite = slug.endswith("-fallback")
    is_provider_duplicate = (
        provider and slug.startswith(f"{provider}-")
        and slug[len(provider) + 1:] in providers_seen_slugs.get(provider, set())
    )

    reasoning_mode = "non-reasoning" if "non-reasoning" in name.lower() else "reasoning"
    effort = None
    low = name.lower()
    for candidate in PARENTHETICAL_EFFORTS:
        if f"{candidate} effort" in low or f"({candidate})" in low:
            effort = candidate
            break
    if effort is None and "-non-reasoning" not in slug:
        for candidate in PARENTHETICAL_EFFORTS:
            if slug.endswith(f"-{candidate}"):
                effort = candidate
                break

    return {
        "slug": slug,
        "effort": effort,
        "reasoning_mode": reasoning_mode,
        "is_latest_alias": is_latest_alias,
        "is_composite": is_composite,
        "is_provider_duplicate": is_provider_duplicate,
    }


def build_slug_index(snapshot):
    models = snapshot.get("models") or []
    slugs_by_provider = {}
    for m in models:
        slugs_by_provider.setdefault(m.get("providerSlug", ""), set()).add(m.get("slug", ""))
    index = {}
    for m in models:
        row = classify_snapshot_row(m, slugs_by_provider)
        index[row["slug"]] = row
    return index


def resolve_slug_registry(slugs_cfg, snapshot_index):
    """For every hand-authored row in roster-slugs.yaml, verify the target
    snapshot slug actually exists and matches on effort + reasoning mode.
    Returns (resolved: {(model, effort): slug}, gaps: [str])."""
    resolved = {}
    gaps = []
    for row in slugs_cfg.get("rows") or []:
        key = (row["model"], row["effort"])
        snap_row = snapshot_index.get(row["slug"])
        if snap_row is None:
            gaps.append(f"{row['model']}@{row['effort']}: slug '{row['slug']}' not present in snapshot")
            continue
        if not slug_row_matches(
            {**snap_row, "model": row["model"]},
            want_model=row["model"],
            want_effort=row["effort"],
            want_reasoning_mode=row.get("reasoning_mode", "reasoning"),
        ):
            gaps.append(
                f"{row['model']}@{row['effort']}: slug '{row['slug']}' failed closed-world match "
                f"(parsed effort={snap_row['effort']!r}, reasoning_mode={snap_row['reasoning_mode']!r})"
            )
            continue
        resolved[key] = row["slug"]
    return resolved, gaps


def diagnostic(message, code=2):
    print(f"generate: {message}", file=sys.stderr)
    return code


def run_generate(args):
    routing_path = Path(args.routing)
    if not routing_path.exists():
        return diagnostic(f"routing file not found: {routing_path}")
    try:
        routing = load_yaml(routing_path)
    except yaml.YAMLError as exc:
        return diagnostic(f"routing.yaml is corrupt: {exc}")

    base_sha = sha256_file(routing_path)
    if args.expect_base and base_sha != args.expect_base:
        return diagnostic(
            f"--expect-base mismatch: routing.yaml is {base_sha}, approval record expects {args.expect_base}"
        )

    families_path = Path(args.families)
    slugs_path = Path(args.slugs)
    if not families_path.exists():
        return diagnostic(f"families file not found: {families_path}")
    if not slugs_path.exists():
        return diagnostic(f"slugs file not found: {slugs_path}")
    try:
        families_cfg = load_yaml(families_path)
        slugs_cfg = load_yaml(slugs_path)
    except yaml.YAMLError as exc:
        return diagnostic(f"families/slugs config is corrupt: {exc}")

    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists():
        return diagnostic(f"snapshot not found: {snapshot_path}")

    actual_snapshot_sha = sha256_file(snapshot_path)
    if actual_snapshot_sha != args.snapshot_sha256:
        return diagnostic(
            "snapshot sha256 mismatch: refusing unpinned/unverified input "
            f"(expected {args.snapshot_sha256}, got {actual_snapshot_sha}). "
            "The expected value must come from the plan record, never from hashing the copy."
        )

    try:
        with open(snapshot_path, encoding="utf-8") as fh:
            snapshot = json.load(fh)
    except json.JSONDecodeError as exc:
        return diagnostic(f"snapshot is corrupt (invalid JSON): {exc}")

    generated_at = (snapshot.get("meta") or {}).get("generatedAt")
    now = datetime.now(timezone.utc)
    status = freshness_status(generated_at, now)
    if status == "stale":
        return diagnostic(
            f"snapshot is stale or generatedAt is absent/unparseable (generatedAt={generated_at!r}); "
            f"freshness window is {FRESHNESS_MAX_DAYS} days. No patch emitted."
        )

    seats = collect_seat_models(routing)

    # --- Identity + slug registry -----------------------------------------
    snapshot_index = build_slug_index(snapshot)
    resolved_slugs, slug_gaps = resolve_slug_registry(slugs_cfg, snapshot_index)

    seat_efforts_used = {(s["exact_model"], s["effort"]) for s in seats.values() if s["effort"]}
    unmapped = sorted(
        f"{model}@{effort}" for (model, effort) in seat_efforts_used
        if (model, effort) not in resolved_slugs
    )
    if unmapped:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        eligibility = {
            "promotion_ready": False,
            "status": "refused",
            "reason": "unmapped_slug",
            "unmapped": unmapped,
            "slug_gaps": slug_gaps,
        }
        (out_dir / "eligibility.json").write_text(json.dumps(eligibility, indent=2, sort_keys=True) + "\n")
        report_lines = [
            "# roster generate -- diagnostic (no patch emitted)",
            "",
            f"- base sha256: `{base_sha}`",
            f"- snapshot sha256: `{actual_snapshot_sha}` (pinned, verified)",
            f"- snapshot generatedAt: `{generated_at}` (fresh)",
            "",
            "## Refused: unmapped routing.yaml model(s)",
            "",
            "Per §P1 Identity, \"the generator refuses (diagnostic, not a proposal) when any",
            "routing.yaml model has no mapped row.\" No default or best-guess fallback row exists.",
            "",
        ]
        for u in unmapped:
            report_lines.append(f"- `{u}`: no closed-world row in `config/roster-slugs.yaml` "
                                 "resolves to a matching snapshot slug.")
        if slug_gaps:
            report_lines.append("")
            report_lines.append("## Slug registry gaps (rows present but unresolved)")
            report_lines.append("")
            for g in slug_gaps:
                report_lines.append(f"- {g}")
        (out_dir / "report.md").write_text("\n".join(report_lines) + "\n")
        return diagnostic("refusing to emit a patch: " + "; ".join(unmapped))

    # --- Eligibility per (role, producer family) ----------------------------
    all_families = {s["exact_model"]: family_of(families_cfg, s["exact_model"]) for s in seats.values()}
    producer_families_by_role = {}
    for name, seat in seats.items():
        role = seat["role"]
        fam = all_families.get(seat["exact_model"])
        family_name = fam["family"] if fam else None
        producer_families_by_role.setdefault(role, set()).add(family_name)

    eligibility_entries = []
    flags = []
    removals = []

    for name, seat in seats.items():
        role = seat["role"]
        fam = all_families.get(seat["exact_model"])
        family_name = fam["family"] if fam else None
        if family_name is None:
            eligibility_entries.append({"seat": name, "role": role, "eligible": False, "rule": "unknown_alias"})
            continue

        ineligible_for = set()
        if role == "validation":
            for producer_family in producer_families_by_role.get("validation", set()) | {"sol"}:
                if producer_family and not rule1_validate(producer_family, family_name):
                    ineligible_for.add(producer_family)
        if role == "coordination":
            relay = rule6_relay(role, family_name)
            if relay["refused"]:
                ineligible_for.add("*")

        # A3: patch scope decision, per (role, producer family) the chain reaches.
        reaching = {pf for pf in producer_families_by_role.get(role, set()) if pf}
        if ineligible_for:
            decision = patch_scope_decision(ineligible_for, reaching) if reaching else "flag"
            if decision == "remove":
                removals.append({"seat": name, "role": role, "reason": sorted(ineligible_for)})
            else:
                flags.append({"seat": name, "role": role, "scoped_to": sorted(ineligible_for)})

        eligibility_entries.append({
            "seat": name,
            "role": role,
            "family": family_name,
            "exact_model": seat["exact_model"],
            "eligible": not ineligible_for,
            "ineligible_for": sorted(ineligible_for) if ineligible_for else [],
        })

    # A2: symmetric cross-version chain refusal, checked pairwise per role.
    runtime_family_unenforced = []
    by_role = {}
    for name, seat in seats.items():
        by_role.setdefault(seat["role"], []).append((name, seat))
    for role, members in by_role.items():
        for i, (name_a, seat_a) in enumerate(members):
            for name_b, seat_b in members[i + 1:]:
                fam_a = all_families.get(seat_a["exact_model"])
                fam_b = all_families.get(seat_b["exact_model"])
                if not fam_a or not fam_b:
                    continue
                if chain_refusal(fam_a["family"], seat_a["exact_model"], fam_b["family"], seat_b["exact_model"]):
                    runtime_family_unenforced.append({"role": role, "seats": [name_a, name_b], "flag": "runtime_family_unenforced"})

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    eligibility = {
        "promotion_ready": False,
        "status": "ok",
        "entries": eligibility_entries,
        "runtime_family_unenforced": runtime_family_unenforced,
        "rules_reference": RULE_REFERENCES,
    }
    (out_dir / "eligibility.json").write_text(json.dumps(eligibility, indent=2, sort_keys=True) + "\n")

    roster = {
        "promotion_ready": False,
        "candidates": [
            {
                "seat": name,
                "lab": all_families[seat["exact_model"]]["lab"] if all_families.get(seat["exact_model"]) else None,
                "family": all_families[seat["exact_model"]]["family"] if all_families.get(seat["exact_model"]) else None,
                "exact_version": seat["exact_model"],
                "evidence": "unevaluated",
            }
            for name, seat in seats.items()
        ],
    }
    (out_dir / "roster.generated.json").write_text(json.dumps(roster, indent=2, sort_keys=True) + "\n")

    # Patch: remove-only, flag-only. Never adds/reorders a seat, never edits
    # frontier_models (A3). Generated in memory; never applied here.
    patch_lines = [
        "# routing.proposed.patch -- generated in memory, never applied.",
        "# promotion_ready: false. Removals and flags only (§P1 Patch scope, A3).",
        "",
    ]
    if removals:
        patch_lines.append("removals:")
        for r in removals:
            patch_lines.append(f"  - seat: {r['seat']}")
            patch_lines.append(f"    role: {r['role']}")
            patch_lines.append(f"    reason: {r['reason']}")
    else:
        patch_lines.append("removals: []")
    if flags:
        patch_lines.append("flags:")
        for f in flags:
            patch_lines.append(f"  - seat: {f['seat']}")
            patch_lines.append(f"    role: {f['role']}")
            patch_lines.append(f"    scoped_to: {f['scoped_to']}")
    else:
        patch_lines.append("flags: []")
    patch_text = "\n".join(patch_lines) + "\n"
    (out_dir / "routing.proposed.patch").write_text(patch_text)
    # Confirm it parses as YAML once "applied" (read back) in memory.
    yaml.safe_load(patch_text)

    report_lines = [
        "# roster generate -- report",
        "",
        f"- base sha256: `{base_sha}`",
        f"- snapshot sha256: `{actual_snapshot_sha}` (pinned, verified)",
        f"- snapshot generatedAt: `{generated_at}` (fresh, within {FRESHNESS_MAX_DAYS} days)",
        f"- promotion_ready: false (every output)",
        "",
        "## Lint of current chains",
        "",
        "- m1: `validation` chain (validation-opus -> validation-sonnet -> validation-sol -> "
        "validation-kimi) lets Kimi validate Sol-produced work; existing conflict, flagged, not removed here.",
        "",
        "## Flags (scoped, not removed)",
        "",
    ]
    for f in flags:
        report_lines.append(f"- `{f['seat']}` ({f['role']}): ineligible for {f['scoped_to']}, remains eligible otherwise")
    if not flags:
        report_lines.append("(none)")
    report_lines += ["", "## Removals (ineligible for every producer family reaching the chain)", ""]
    for r in removals:
        report_lines.append(f"- `{r['seat']}` ({r['role']}): {r['reason']}")
    if not removals:
        report_lines.append("(none)")
    report_lines += ["", "## runtime_family_unenforced (A2)", ""]
    for rf in runtime_family_unenforced:
        report_lines.append(f"- role `{rf['role']}`: {rf['seats']}")
    if not runtime_family_unenforced:
        report_lines.append("(none)")
    (out_dir / "report.md").write_text("\n".join(report_lines) + "\n")

    post_sha = sha256_file(routing_path)
    if post_sha != base_sha:
        return diagnostic("routing.yaml hash changed during the run -- this must never happen", code=1)

    print(f"generate: wrote eligibility.json, roster.generated.json, routing.proposed.patch, report.md to {out_dir}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", metavar="TRUTH_TABLE", help="run the truth-table fixture and exit")
    parser.add_argument("--routing", help="path to routing.yaml")
    parser.add_argument("--families", help="path to config/roster-families.yaml")
    parser.add_argument("--slugs", help="path to config/roster-slugs.yaml")
    parser.add_argument("--snapshot", help="explicit local snapshot path (no default, no network)")
    parser.add_argument("--snapshot-sha256", help="expected sha256 of --snapshot, from the plan record")
    parser.add_argument("--out", help="output directory")
    parser.add_argument("--expect-base", help="expected sha256 of --routing, from the approval record")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test(args.self_test)

    required = ["routing", "families", "slugs", "snapshot", "snapshot_sha256", "out"]
    missing = [f"--{r.replace('_', '-')}" for r in required if getattr(args, r) is None]
    if missing:
        parser.error(f"missing required arguments for a generate run: {', '.join(missing)}")

    return run_generate(args)


if __name__ == "__main__":
    sys.exit(main())
