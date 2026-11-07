"""How the code reads roster-slugs.yaml, roster-families.yaml and fleet-registry.yaml.

Three readers are pinned:
  * scripts/roster/generate.py  (slug registry, family identity, shape checks)
  * scripts/lib-fleet.sh        (yq queries over fleet-registry.yaml)
  * scripts/route-spawn.sh      (argument validation that precedes any lookup)

The real config files are pinned by golden/roster_config.json (regenerate with
`gen_golden.py --roster`). Behavior is pinned with small synthetic configs so
that an unknown slug, a family mismatch or a malformed shape fails the same way
after the defaults and overlay split.
"""
import copy
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import orchlib as o

gen = o.load_generate()
GOLDEN = json.loads((o.GOLDEN / "roster_config.json").read_text())

FAMILIES = {"models": {
    "m-opus": {"lab": "anthropic", "family": "opus", "snapshot_name": "Opus One"},
    "m-sol": {"lab": "openai", "family": "sol", "snapshot_name": "Sol One"},
}}


def snap(*rows):
    return gen.index_snapshot({"models": [dict(providerSlug="p", **r) for r in rows]})


def slugs(rows=(), waivers=()):
    return {"rows": list(rows), "waivers": list(waivers)}


ROW = {"model": "m-opus", "effort": "high", "reasoning_mode": "reasoning", "slug": "opus-one-high"}
SNAP_OK = snap({"slug": "opus-one-high", "name": "Opus One (high)"})


# ---------------------------------------------------------------- real files --

def test_real_config_facts_match_golden():
    assert o.roster_facts() == GOLDEN


def test_every_real_slug_row_resolves_against_a_well_formed_snapshot():
    assert GOLDEN["registry_gaps"] == []
    assert set(GOLDEN["registry_entries"]) >= set(GOLDEN["slug_rows"])


@pytest.mark.parametrize("model,expect", [
    ("claude-opus-5-5", ["anthropic", "opus", "Claude Opus 5.5"]),
    ("claude-fable-5-1", ["anthropic", "fable", "Claude Fable 5.1"]),
    ("gpt-6-astra", ["openai", "astra", "GPT-6 Astra"]),
])
def test_slug_to_family_lookup(model, expect):
    assert GOLDEN["families"][model] == expect


def test_unmapped_model_is_not_in_families():
    assert "sao10k-l3-lunaris-8b" not in GOLDEN["families"]


# ------------------------------------------------------------ registry rules --

def resolve(slugs_cfg, snapshot=SNAP_OK, families=FAMILIES):
    return gen.resolve_registry(slugs_cfg, families, snapshot)


def test_exact_row_resolves():
    entries, gaps = resolve(slugs([ROW]))
    assert gaps == []
    assert entries["m-opus@high"]["slug"] == "opus-one-high"
    assert entries["m-opus@high"]["status"] == "exact"
    assert entries["m-opus@high"]["row_name"] == "Opus One (high)"


def test_unknown_slug_is_a_gap_not_a_guess():
    entries, gaps = resolve(slugs([dict(ROW, slug="missing")]))
    assert entries == {}
    assert gaps == [("m-opus@high", "slug 'missing' not present in snapshot")]


def test_model_absent_from_families_is_rejected():
    entries, gaps = resolve(slugs([dict(ROW, model="m-unknown")]),
                            snapshot=snap({"slug": "opus-one-high", "name": "Opus One (high)"}))
    assert entries == {}
    assert "unknown_family:m-unknown" in gaps[0][1]


def test_identity_mismatch_is_rejected():
    _, gaps = resolve(slugs([ROW]), snapshot=snap({"slug": "opus-one-high", "name": "Sol One (high)"}))
    assert "identity:row is 'Sol One', m-opus is 'Opus One'" in gaps[0][1]


@pytest.mark.parametrize("name,slug,expected", [
    ("Opus One (high)", "opus-one-latest", "latest_alias"),
    ("Opus One (high, Default Fallback)", "opus-one-high", None),
    ("Opus One (high, Anthropic Fallback)", "opus-one-high", "composite"),
    ("Opus One (high)", "opus-one-fallback", "composite"),
    ("Opus One (high, batch)", "opus-one-high", "unrecognised_qualifier:batch"),
    ("Opus One (low)", "opus-one-high", "effort:row 'low' != declared 'high'"),
    ("Opus One (high, non-reasoning)", "opus-one-high", "reasoning_mode:row 'non-reasoning' != declared 'reasoning'"),
])
def test_row_problems(name, slug, expected):
    _, gaps = resolve(slugs([dict(ROW, slug=slug)]), snapshot=snap({"slug": slug, "name": name}))
    if expected is None:
        assert gaps == []
    else:
        assert expected in gaps[0][1]


def test_provider_prefixed_duplicate_is_rejected():
    snapshot = gen.index_snapshot({"models": [
        {"slug": "opus-one-high", "name": "Opus One (high)", "providerSlug": "p"},
        {"slug": "p-opus-one-high", "name": "Opus One (high)", "providerSlug": "p"}]})
    _, gaps = resolve(slugs([dict(ROW, slug="p-opus-one-high")]), snapshot=snapshot)
    assert "provider_duplicate" in gaps[0][1]


def test_duplicate_registry_entry_removes_both():
    entries, gaps = resolve(slugs([ROW, dict(ROW)]))
    assert entries == {}
    assert gaps == [("m-opus@high", "duplicate registry entry (closed world: exactly one row)")]


def test_entry_missing_required_fields():
    entries, gaps = resolve(slugs([{"model": "m-opus", "effort": "high"}]))
    assert entries == {}
    assert gaps[0][1] == "registry entry lacks ref/model/slug/reasoning_mode"


WAIVER = {"ref": "alias:opus", "model": "m-opus", "slug": "opus-one-high", "row_effort": "high",
          "row_reasoning_mode": "reasoning"}


@pytest.mark.parametrize("extra,kind,reason", [
    ({"status": "PROPOSED"}, "waiver-proposed", None),
    ({"status": "RATIFIED", "approved_by": "mk", "approval": "p"}, "waiver-ratified", None),
    ({"status": "RATIFIED", "approved_by": "other", "approval": "p"}, None, 'needs approved_by == "mk"'),
    ({"status": "RATIFIED"}, None, "a RATIFIED waiver needs approved_by and an approval pointer"),
    ({"status": "PROPOSED", "approved_by": "mk"}, None, "a PROPOSED waiver cannot carry approved_by"),
    ({"status": "MAYBE"}, None, "waiver status must be exactly one of"),
    ({}, None, "waiver status must be exactly one of"),
])
def test_waiver_status_rules(extra, kind, reason):
    entries, gaps = resolve(slugs(waivers=[dict(WAIVER, **extra)]))
    if kind:
        assert entries["alias:opus"]["status"] == kind and gaps == []
    else:
        assert entries == {} and reason in gaps[0][1]


def test_fallback_ref_chain_to_missing_entry_is_dropped_to_a_fixpoint():
    a = dict(WAIVER, ref="a", status="PROPOSED", fallback_ref="b")
    b = dict(WAIVER, ref="b", status="PROPOSED", fallback_ref="missing")
    entries, gaps = resolve(slugs(waivers=[a, b]))
    assert entries == {}
    assert sorted(gaps) == [("a", "fallback_ref 'b' is not a verified registry entry"),
                            ("b", "fallback_ref 'missing' is not a verified registry entry")]


def test_fallback_ref_to_verified_entry_is_kept():
    a = dict(WAIVER, ref="a", status="PROPOSED", fallback_ref="m-opus@high")
    entries, gaps = resolve(slugs([ROW], [a]))
    assert gaps == [] and entries["a"]["fallback_ref"] == "m-opus@high"


def test_row_with_ref_is_keyed_by_ref():
    entries, _ = resolve(slugs([dict(ROW, ref="local:x")]))
    assert list(entries) == ["local:x"]


def test_snapshot_without_models_list_is_refused():
    with pytest.raises(gen.Refusal) as exc:
        gen.index_snapshot({"models": "nope"})
    assert exc.value.codes == ["snapshot_corrupt"]


# ------------------------------------------------------------- snapshot rows --

@pytest.mark.parametrize("name,effort,mode", [
    ("Opus One (high)", "high", "reasoning"),
    ("Opus One (xhigh effort)", "xhigh", "reasoning"),
    ("Opus One (Non-reasoning)", None, "non-reasoning"),
    ("Opus One (Reasoning)", None, "reasoning"),
    ("Opus One (low, high)", "ambiguous", "reasoning"),
    ("Opus One", None, "unlabelled"),
])
def test_parse_snapshot_row(name, effort, mode):
    row = gen.parse_snapshot_row({"slug": "s", "name": name}, {"s"})
    assert (row["base_name"], row["effort"], row["reasoning_mode"]) == ("Opus One", effort, mode)


# -------------------------------------------------------------- shape + time --

def test_shape_problems_clean_config_is_empty():
    assert gen.config_shape_problems(FAMILIES, slugs([ROW]), []) == []


@pytest.mark.parametrize("fam,sl,waivers,expected", [
    ([], {}, [], "roster-families.yaml top level is list, not a mapping"),
    ({}, [], [], "roster-slugs.yaml top level is list, not a mapping"),
    ({"models": [1]}, {}, [], "roster-families.yaml `models` is not a mapping"),
    ({"models": {"m": 3}}, {}, [], "roster-families.yaml models.m is not a mapping"),
    ({"candidates": "x"}, {}, [], "roster-families.yaml `candidates` is not a list"),
    ({"luna_class_evaluations": [1]}, {}, [], "roster-families.yaml `luna_class_evaluations` is not a mapping"),
    ({}, {"rows": ["x"]}, [], "roster-slugs.yaml `rows` is not a list of mappings"),
    ({}, {"waivers": {}}, [], None),  # falsy empties are accepted, not diagnosed
    ({"models": []}, {}, [], None),
    ({}, {}, "x", "reorder waivers `waivers` is not a list"),
    ({}, {}, [3], "reorder waiver #0 is not a mapping with a `seat` string"),
    ({}, {}, [{"seat": "s"}], "reorder waiver for s needs approved_by and an approval pointer"),
])
def test_shape_problems(fam, sl, waivers, expected):
    got = gen.config_shape_problems(fam, sl, waivers)
    if expected is None:
        assert got == []  # an empty mapping is falsy, so `or []` accepts it
    else:
        assert expected in got


NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)


@pytest.mark.parametrize("stamp,status", [
    ((NOW - timedelta(days=1)).isoformat(), "fresh"),
    (None, "stale"),
    ("not-a-date", "stale"),
    ((NOW + timedelta(days=30)).isoformat(), "future"),
    ((NOW - timedelta(days=3650)).isoformat(), "stale"),
])
def test_freshness(stamp, status):
    assert gen.freshness(stamp, NOW)[0] == status


# ----------------------------------------------------------------- generate CLI --

def _gen(*args, env=None, home):
    return o.run([o.py(), o.ROOT / "scripts/roster/generate.py", *args],
                 env or o.hermetic_env(home))


TABLE = o.ROOT / "tests/fixtures/roster/truth-table.json"
# Known drift, present at the baseline and at main: this one truth-table case
# no longer matches the repo's current routing.yaml, so the shipped table makes
# `--self-test` exit 2. Pinned so a fix (or a new break) shows up as a change.
STALE_CASE = "repo-routing-end-to-end"


def _failed_ids(stderr):
    return sorted(line.split()[1].rstrip(":") for line in stderr.splitlines() if line.startswith("  FAIL "))


def test_cli_self_test_shipped_table_fails_only_the_stale_case(home):
    n = len(json.loads(TABLE.read_text())["cases"])
    r = _gen("--self-test", TABLE, home=home)
    assert r.returncode == 2
    assert r.stdout.strip() == f"self-test: {n - 1}/{n} cases passed"
    assert _failed_ids(r.stderr) == [STALE_CASE]


def test_cli_self_test_passes_without_the_stale_case(home, tmp_path):
    table = json.loads(TABLE.read_text())
    table["cases"] = [c for c in table["cases"] if c["id"] != STALE_CASE]
    path = tmp_path / "table.json"
    path.write_text(json.dumps(table))
    r = _gen("--self-test", path, home=home)
    n = len(table["cases"])
    assert (r.returncode, r.stdout.strip(), r.stderr) == (0, f"self-test: {n}/{n} cases passed", "")


def test_cli_without_arguments_reports_missing_required_flags(home):
    r = _gen(home=home)
    assert r.returncode == 1
    assert ("generate: missing required arguments for a generate run: --routing, --families, "
            "--slugs, --snapshot, --snapshot-sha256, --expect-base, --out") in r.stderr


def test_cli_missing_routing_file_exits_2(home, tmp_path):
    args = ["--routing", tmp_path / "none.yaml", "--families", "f", "--slugs", "s", "--snapshot", "n",
            "--snapshot-sha256", "0", "--expect-base", "0", "--out", tmp_path / "out"]
    r = _gen(*args, home=home)
    assert r.returncode == 2
    assert "routing file not found" in r.stderr


def test_cli_self_test_reports_an_edited_failing_case(home, tmp_path):
    table = json.loads(TABLE.read_text())
    table["cases"] = [c for c in table["cases"] if c["id"] != STALE_CASE]
    victim = table["cases"][0]
    victim["expect"] = {"status": "refused"} if victim["expect"].get("status") != "refused" else {"status": "ok"}
    path = tmp_path / "table.json"
    path.write_text(json.dumps(table))
    r = _gen("--self-test", path, home=home)
    assert r.returncode == 2
    assert _failed_ids(r.stderr) == [victim["id"]]
    assert r.stdout.strip() == f"self-test: {len(table['cases']) - 1}/{len(table['cases'])} cases passed"


# ------------------------------------------------------------------ lib-fleet --

YQ = shutil.which("yq")
needs_yq = pytest.mark.skipif(YQ is None, reason="yq v4 not installed: lib-fleet.sh tests skipped "
                                                  "(--orchcompat-require-ic makes this an error)")


def fleet(home, call, registry=None, **extra):
    """Source lib-fleet.sh in a clean shell and run one function call."""
    extra_env = dict(extra)
    if registry is not None:
        extra_env["CLAVAIN_FLEET_REGISTRY"] = registry
    env = o.hermetic_env(home, Path(YQ).parent, **extra_env)
    return o.run(["bash", "-c", f'source "{o.ROOT}/scripts/lib-fleet.sh"; {call}'], env)


@needs_yq
def test_fleet_list_is_the_non_orphaned_agents(home):
    r = fleet(home, "fleet_list")
    assert r.returncode == 0
    active = [a for a, v in GOLDEN["fleet_agents"].items() if not v[3]]
    assert sorted(r.stdout.split()) == sorted(active)


@needs_yq
@pytest.mark.parametrize("agent", ["fd-architecture", "fd-safety"])
def test_fleet_get_json_matches_registry(home, agent):
    r = fleet(home, f"FLEET_FORMAT=json fleet_get {agent}")
    assert r.returncode == 0
    reg = yaml.safe_load((o.ROOT / "config/fleet-registry.yaml").read_text())["agents"][agent]
    assert json.loads(r.stdout) == reg


@needs_yq
def test_fleet_get_unknown_agent(home):
    r = fleet(home, "fleet_get no-such-agent")
    assert (r.returncode, r.stdout, r.stderr.strip()) == (1, "", "lib-fleet: agent 'no-such-agent' not found")


@needs_yq
def test_fleet_by_category_and_source_and_role(home):
    facts = GOLDEN["fleet_agents"]
    by_cat = sorted(a for a, v in facts.items() if v[0] == "review" and not v[3])
    assert sorted(fleet(home, "fleet_by_category review").stdout.split()) == by_cat
    by_src = sorted(a for a, v in facts.items() if v[1] == "interflux" and not v[3])
    assert sorted(fleet(home, "fleet_by_source interflux").stdout.split()) == by_src
    assert fleet(home, "fleet_by_role fd-safety").stdout.split() == ["fd-safety"]
    assert fleet(home, "fleet_by_category no-such-category").stdout == ""


@needs_yq
def test_fleet_cost_estimate(home):
    assert fleet(home, "fleet_cost_estimate fd-architecture").stdout.strip() == "800"
    r = fleet(home, "fleet_cost_estimate nope")
    assert r.returncode == 1 and "not found or has no cold_start_tokens" in r.stderr


@needs_yq
def test_fleet_check_coverage_reports_missing_capabilities(home):
    ok = fleet(home, "fleet_check_coverage domain_review")
    assert ok.returncode == 0
    bad = fleet(home, "fleet_check_coverage domain_review not_a_capability")
    assert bad.returncode == 1 and bad.stderr.strip() == "not_a_capability"


@needs_yq
def test_orphaned_agents_are_excluded_but_still_gettable(home, tmp_path):
    reg = tmp_path / "reg.yaml"
    reg.write_text("version: '1.0'\nagents:\n  live: {category: review, source: s, cold_start_tokens: 5}\n"
                   "  gone: {category: review, source: s, cold_start_tokens: 5, orphaned_at: '2026-01-01'}\n")
    assert fleet(home, "fleet_list", registry=reg).stdout.split() == ["live"]
    assert fleet(home, "fleet_by_category review", registry=reg).stdout.split() == ["live"]
    assert fleet(home, "fleet_get gone", registry=reg).returncode == 0


@needs_yq
def test_empty_registry_warns_and_missing_registry_fails(home, tmp_path):
    reg = tmp_path / "empty.yaml"
    reg.write_text("version: '1.0'\nagents: {}\n")
    r = fleet(home, "fleet_list", registry=reg)
    assert "Warning: fleet-registry.yaml exists but has no agents" in r.stderr
    # an explicit registry path that does not exist falls back to the repo copy
    r = fleet(home, "fleet_list", registry=tmp_path / "absent.yaml")
    assert r.returncode == 0 and r.stdout.split()


# ---------------------------------------------------------------- route-spawn --

def spawn(home, *args, **extra):
    return o.run(["bash", o.ROOT / "scripts/route-spawn.sh", *args], o.hermetic_env(home, **extra))


@pytest.mark.parametrize("args,message", [
    ((), "--role is required"),
    (("--bogus",), "unknown argument: --bogus"),
    (("--role",), "--role requires a value"),
    (("--role", "--project"), "--role requires a value"),
    (("--role", "coordination"), "coordinator threads resolve --role coordinator-seat; relay work uses dispatch.sh"),
    (("--role", "coordinator-seat"), "coordinator-seat requires --project"),
    (("--role", "lane"), "lane requires --lineage"),
    (("--role", "plan-review"), "plan-review requires --producer-identity"),
    (("--role", "validation"), "validation requires --producer-identity"),
    (("--role", "cross-lab-review"), "cross-lab-review requires --producer-identity"),
])
def test_route_spawn_usage_errors_exit_2(home, args, message):
    r = spawn(home, *args)
    assert (r.returncode, r.stdout) == (2, "")
    assert r.stderr.strip() == f"route-spawn: {message}"


def test_route_spawn_seat_out_must_be_in_writable_directory(home, tmp_path):
    r = spawn(home, "--role", "planning", "--seat-out", tmp_path / "no-dir" / "seat.json")
    assert r.returncode == 2 and "--seat-out needs a file in an existing writable directory" in r.stderr
