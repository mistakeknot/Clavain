"""Exercise the routing audit through its public CLI, including failing exits."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/routing-check.py"


@pytest.fixture
def inputs(tmp_path):
    policy = {"dispatch": {"model_aliases": {"sonnet": "claude-sonnet-5-5"},
              "roles": {"coordination": "coord", "routine-execution": "exec"},
              "tiers": {
                  "coord": {"model": "sonnet", "reasoning_effort": "medium"},
                  "exec": {"model": "claude-sonnet-5-5", "reasoning_effort": "high",
                           "fallbacks": ["sol"]},
                  "sol": {"model": "gpt-6.1-sol", "reasoning_effort": "medium"}}}}
    released = {"models": [{"id": "claude-sonnet-5-5"}, {"id": "gpt-6.1-sol"}]}
    seats = {"seats": [{"thread": "thr_test", "role": "coordination",
                        "model": "claude-sonnet-5-5", "reasoning_effort": "medium"}]}
    return tmp_path, policy, released, seats


def run(inputs, *args):
    folder, policy, released, seats = inputs
    paths = [folder / name for name in ("routing.yaml", "models.json", "seats.json")]
    for path, content in zip(paths, (yaml.safe_dump(policy), json.dumps(released), json.dumps(seats))):
        path.write_text(content)
    before = [p.read_bytes() for p in paths]
    result = subprocess.run([sys.executable, str(SCRIPT), "--routing", str(paths[0]),
                             "--released-models", str(paths[1]), "--seats", str(paths[2]), *args],
                            capture_output=True, text=True, timeout=10)
    assert before == [p.read_bytes() for p in paths], "audit edited an input"
    return result


def report(result, code):
    assert result.returncode == code, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_clean_pass(inputs):
    assert report(run(inputs), 0)["findings"] == []


@pytest.mark.parametrize("model", ["gpt-6", "gpt-6-sol", "gpt-5.6-sol", "claude-sonnet-5"])
def test_retired_pin_fails_even_when_released(inputs, model):
    inputs[1]["dispatch"]["tiers"]["sol"]["model"] = model
    inputs[2]["models"].append({"id": model})
    assert "retired-pin" in {f["kind"] for f in report(run(inputs), 1)["findings"]}


def test_unreleased_fallback_fails(inputs):
    inputs[2]["models"].pop()
    assert "unreleased-model" in {f["kind"] for f in report(run(inputs), 1)["findings"]}


def test_unused_retired_alias_pin_fails(inputs):
    inputs[1]["dispatch"]["model_aliases"]["old"] = "gpt-5.6-sol"
    inputs[2]["models"].append({"id": "gpt-5.6-sol"})
    assert "retired-pin" in {f["kind"] for f in report(run(inputs), 1)["findings"]}


def test_retired_seat_alias_fails(inputs):
    inputs[1]["dispatch"]["model_aliases"]["gpt-6-sol"] = "gpt-6.1-sol"
    inputs[3]["seats"][0].update(role="routine-execution", model="gpt-6-sol")
    assert "retired-pin" in {f["kind"] for f in report(run(inputs), 1)["findings"]}


def test_seat_drift_fails(inputs):
    inputs[3]["seats"][0]["model"] = "gpt-6.1-sol"
    result = report(run(inputs), 1)
    assert any(f["kind"] == "seat-drift" for f in result["findings"])
    assert all(c[:3] == ["bd", "--actor", "clavain-coord"] for c in result["bead_commands"])


@pytest.mark.parametrize("effort,kind", [("high", "over-cap"), ("low", "seat-drift")])
def test_effort_must_match_table(inputs, effort, kind):
    inputs[3]["seats"][0]["reasoning_effort"] = effort
    assert kind in {f["kind"] for f in report(run(inputs), 1)["findings"]}


def test_fallback_seat_and_receipt_match(inputs):
    inputs[3]["receipts"] = [{"role": "routine-execution", "model": "gpt-6.1-sol",
                              "reasoning_effort": "medium", "thread": "thr_exec"}]
    report(run(inputs), 0)
    inputs[3]["receipts"][0]["reasoning_effort"] = "high"
    assert "over-cap" in {f["kind"] for f in report(run(inputs), 1)["findings"]}


def test_consider_is_advisory(inputs):
    inputs[2]["models"].append({"id": "claude-sonnet-6", "better_than": ["claude-sonnet-5-5"]})
    data = report(run(inputs), 0)
    assert {f["kind"] for f in data["findings"]} == {"consider"}
    assert data["bead_commands"]


def test_precheck_scopes_to_role(inputs):
    inputs[1]["dispatch"]["tiers"]["sol"]["model"] = "gpt-5.6-sol"
    report(run(inputs, "--precheck", "coordination"), 0)
    report(run(inputs, "--precheck", "routine-execution"), 1)
    report(run(inputs, "--precheck", "unknown"), 2)


def test_custom_retired_list(inputs):
    path = inputs[0] / "retired.json"
    path.write_text('["claude-sonnet-*"]')
    assert "retired-pin" in {f["kind"] for f in report(run(inputs, "--retired-models", str(path)), 1)["findings"]}


@pytest.mark.parametrize("target,value", [(1, {}), (2, {}), (3, {}),
    (2, {"models": [{"id": "x", "better_than": "y"}]}),
    (3, {"seats": [{"role": "coordination", "model": "x", "reasoning_effort": "bogus"}]}),
    (3, {"seats": [None]}), (3, {"seats": [], "receipts": {}})])
def test_malformed_shapes_fail(inputs, target, value):
    changed = list(inputs)
    changed[target] = value
    report(run(changed), 2)


@pytest.mark.parametrize("field,value", [("model", None), ("reasoning_effort", "bogus"),
                                         ("fallbacks", ["missing"])])
def test_malformed_tier_fails(inputs, field, value):
    inputs[1]["dispatch"]["tiers"]["coord"][field] = value
    report(run(inputs), 2)


def test_cycles_in_real_fallback_graph_are_valid(inputs):
    inputs[1]["dispatch"]["tiers"]["sol"]["fallbacks"] = ["exec"]
    report(run(inputs), 0)


def test_real_policy_copy(inputs):
    policy = yaml.safe_load((ROOT / "config/routing.yaml").read_text())
    aliases = policy["dispatch"]["model_aliases"]
    released = {"models": [{"id": model} for model in sorted({
        aliases.get(t["model"], t["model"]) for t in policy["dispatch"]["tiers"].values()})]}
    actual = (inputs[0], policy, released, inputs[3])
    report(run(actual), 0)
    policy["dispatch"]["tiers"]["routine-sol"]["model"] = "gpt-5.6-sol"
    report(run(actual), 1)


def test_profile_override_and_alias_cycle(inputs):
    inputs[1]["reasoning"] = {"profiles": {"pilot": {"roles": {"coordination": "sol"}}}}
    inputs[3]["seats"][0].update(policy_profile="pilot", model="gpt-6.1-sol")
    report(run(inputs), 0)
    inputs[1]["dispatch"]["model_aliases"] = {"sonnet": "other", "other": "sonnet"}
    report(run(inputs), 2)


@pytest.mark.parametrize("content", ["{", "null", "[]"])
def test_invalid_json_and_missing_file(inputs, content):
    path = inputs[0] / "invalid.json"
    path.write_text(content)
    report(run(inputs, "--seats", str(path)), 2)
    report(run(inputs, "--seats", str(path.with_name("missing.json"))), 2)


def test_invalid_yaml_fails(inputs):
    path = inputs[0] / "invalid.yaml"
    path.write_text('dispatch: [unterminated')
    report(run(inputs, "--routing", str(path)), 2)


def test_units_are_read_only_templates():
    service = (ROOT / "units/routing-check.service").read_text()
    timer = (ROOT / "units/routing-check.timer").read_text()
    assert "--released-models" in service and "--seats" in service
    assert "--file-beads" not in service
    assert "Type=oneshot" in service
    assert "OnCalendar=*-*-* 04:25:00" in timer
    assert "Unit=routing-check.service" in timer


def test_filing_is_opt_in(inputs, monkeypatch):
    inputs[3]["seats"][0]["model"] = "gpt-6.1-sol"
    fake = inputs[0] / "bd"
    log = inputs[0] / "calls"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$BD_TEST_LOG"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(inputs[0]) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("BD_TEST_LOG", str(log))
    report(run(inputs), 1)
    assert not log.exists()
    report(run(inputs, "--file-beads"), 1)
    assert "--actor clavain-coord create" in log.read_text()
    fake.write_text('#!/bin/sh\nexit 1\n')
    report(run(inputs, "--file-beads"), 2)


# --- round 1: project profiles, whole-policy model scan, UNKNOWN evidence ---

def with_project(inputs, **extra):
    """Real schema: project_profiles maps slug -> profile name; the scoped profile lives in profiles."""
    policy = inputs[1]
    policy["dispatch"]["tiers"]["proj"] = {"model": "gpt-6.1-sol", "reasoning_effort": "high"}
    policy["reasoning"] = {
        "projects": ["clavain", "autarch"],
        "profiles": {"project-clavain": {"scope": "project:clavain", "roles": {"coordination": "proj"}}},
        "project_profiles": {"clavain": "project-clavain"}, **extra}
    return inputs


def test_scoped_project_profile_is_valid_and_selects_candidates(inputs):
    with_project(inputs)
    inputs[3]["seats"][0].update(project="clavain", model="gpt-6.1-sol", reasoning_effort="high")
    report(run(inputs), 0)
    # Another project and the fleet row still follow the base table.
    inputs[3]["seats"][0].update(project="autarch", model="claude-sonnet-5-5", reasoning_effort="medium")
    report(run(inputs), 0)
    inputs[3]["seats"][0].update(project="clavain", model="claude-sonnet-5-5", reasoning_effort="medium")
    assert "seat-drift" in {f["kind"] for f in report(run(inputs), 1)["findings"]}


def test_project_without_override_uses_fleet_row(inputs):
    with_project(inputs)
    inputs[3]["seats"][0].update(project="autarch")
    report(run(inputs), 0)


def test_unknown_project_in_record_is_drift(inputs):
    with_project(inputs)
    inputs[3]["seats"][0].update(project="ghost")
    assert "seat-drift" in {f["kind"] for f in report(run(inputs), 1)["findings"]}


def test_precheck_traverses_project_profile_chain(inputs):
    with_project(inputs)
    inputs[1]["dispatch"]["tiers"]["proj"]["model"] = "gpt-5.6-sol"
    inputs[2]["models"].append({"id": "gpt-5.6-sol"})
    assert "retired-pin" in {f["kind"] for f in report(run(inputs, "--precheck", "coordination"), 1)["findings"]}
    assert "retired-pin" not in {f["kind"] for f in report(run(inputs, "--precheck", "routine-execution"), 0)["findings"]}


@pytest.mark.parametrize("mutate", [
    lambda r: r["project_profiles"].update(clavain={"coordination": "proj"}),     # old role-mapping shape
    lambda r: r["project_profiles"].update(clavain="missing-profile"),
    lambda r: r["profiles"]["project-clavain"].update(scope="project:autarch"),
    lambda r: r["project_profiles"].update(ghost="project-clavain"),              # not in reasoning.projects
])
def test_malformed_project_profiles_fail(inputs, mutate):
    with_project(inputs)
    mutate(inputs[1]["reasoning"])
    report(run(inputs), 2)


def test_real_policy_with_scoped_project_clavain_profile(inputs):
    policy = yaml.safe_load((ROOT / "config/routing.yaml").read_text())
    aliases = policy["dispatch"]["model_aliases"]
    tiers = policy["dispatch"]["tiers"]
    policy["reasoning"]["profiles"]["project-clavain"] = {
        "scope": "project:clavain", "roles": {"coordinator-seat": "coordinator-seat-opus"}}
    policy["reasoning"]["project_profiles"] = {"clavain": "project-clavain"}
    released = {"models": [{"id": model} for model in sorted({
        aliases.get(t["model"], t["model"]) for t in tiers.values()})]}
    opus = tiers["coordinator-seat-opus"]
    seats = {"seats": [{"thread": "thr_c", "role": "coordinator-seat", "project": "clavain",
                        "model": aliases.get(opus["model"], opus["model"]),
                        "reasoning_effort": opus["reasoning_effort"]}]}
    actual = (inputs[0], policy, released, seats)
    report(run(actual), 0)
    report(run(actual, "--precheck", "coordinator-seat"), 0)


@pytest.mark.parametrize("path", [
    ["subagents", "defaults", "model"],
    ["subagents", "defaults", "categories", "review"],
    ["subagents", "overrides", "fd-safety", "model"],
    ["complexity", "overrides", "C5", "subagent_model"],
])
def test_retired_model_anywhere_in_policy_fails(inputs, path):
    node = inputs[1]
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = "gpt-5.6-sol"
    result = report(run(inputs), 1)
    assert any(f["kind"] == "retired-pin" and ".".join(path) in f["subject"] for f in result["findings"])


def test_retired_model_hidden_behind_alias_in_subagents_fails(inputs):
    inputs[1]["dispatch"]["model_aliases"]["legacy"] = "gpt-5.6-sol"
    inputs[1]["subagents"] = {"defaults": {"model": "legacy"}}
    inputs[2]["models"].append({"id": "gpt-5.6-sol"})
    assert "retired-pin" in {f["kind"] for f in report(run(inputs), 1)["findings"]}


def test_subagent_shorthand_models_are_not_flagged_unreleased(inputs):
    inputs[1]["subagents"] = {"defaults": {"model": "sonnet", "categories": {"research": "haiku"}}}
    assert report(run(inputs), 0)["findings"] == []


def test_real_policy_subagent_default_retired(inputs):
    policy = yaml.safe_load((ROOT / "config/routing.yaml").read_text())
    aliases = policy["dispatch"]["model_aliases"]
    released = {"models": [{"id": model} for model in sorted({
        aliases.get(t["model"], t["model"]) for t in policy["dispatch"]["tiers"].values()})]}
    policy["subagents"]["defaults"]["model"] = "gpt-5.6-sol"
    assert "retired-pin" in {f["kind"] for f in
                             report(run((inputs[0], policy, released, inputs[3])), 1)["findings"]}


def test_clean_run_reports_status_and_evidence_counts(inputs):
    data = report(run(inputs), 0)
    assert data["status"] == "clean"
    assert data["evidence"] == {"seats": 1, "receipts": 0, "matched": 1}
    assert data["unknown"] == []
    assert report(run(inputs, "--strict"), 0)["status"] == "clean"


@pytest.mark.parametrize("seats", [{"seats": []}, {"seats": [], "receipts": []}])
def test_empty_seat_evidence_is_unknown_not_clean(inputs, seats):
    changed = (inputs[0], inputs[1], inputs[2], seats)
    data = report(run(changed), 0)
    assert data["status"] == "unknown" and data["findings"] == []
    assert data["unknown"] and "no seat or receipt evidence" in data["unknown"][0]
    data = report(run(changed, "--strict"), 3)
    assert data["status"] == "unknown"


def test_receipt_only_evidence_is_known(inputs):
    seats = {"seats": [], "receipts": [{"role": "routine-execution", "model": "gpt-6.1-sol",
                                        "reasoning_effort": "medium"}]}
    changed = (inputs[0], inputs[1], inputs[2], seats)
    assert report(run(changed, "--strict"), 0)["status"] == "clean"


def test_precheck_role_without_evidence_is_unknown(inputs):
    # Evidence exists, but none for the prechecked role.
    data = report(run(inputs, "--precheck", "routine-execution"), 0)
    assert data["status"] == "unknown" and "routine-execution" in data["unknown"][0]
    report(run(inputs, "--precheck", "routine-execution", "--strict"), 3)
    assert report(run(inputs, "--precheck", "coordination", "--strict"), 0)["status"] == "clean"


def test_findings_outrank_unknown_in_exit_code(inputs):
    inputs[1]["subagents"] = {"defaults": {"model": "gpt-5.6-sol"}}
    changed = (inputs[0], inputs[1], inputs[2], {"seats": []})
    data = report(run(changed, "--strict"), 1)
    assert data["status"] == "drift" and data["unknown"]


def test_readme_documents_unknown_and_collector_followup():
    text = (ROOT / "units/README.md").read_text()
    assert "UNKNOWN" in text and "--strict" in text
    assert "follow-up bead" in text and "out of scope" in text


@pytest.mark.parametrize("model", ["gpt-5.6-sol", "claude-sonnet-5", "sonnet-5", "opus-4", "haiku-3", "legacy"])
@pytest.mark.parametrize("location", ["override", "arbitrary", "list"])
def test_generic_model_string_leaves(inputs, model, location):
    inputs[1]["dispatch"]["model_aliases"]["legacy"] = "gpt-5.6-sol"
    # Custom retirements exercise shorthand families beyond the default list.
    retired = inputs[0] / "retired.json"
    retired.write_text(json.dumps(["gpt-5.6-sol", "claude-sonnet-5", "sonnet-5", "opus-4", "haiku-3"]))
    if location == "override":
        inputs[1]["subagents"] = {"overrides": {"interflux:fd-safety": model}}
        path = "subagents.overrides.interflux:fd-safety"
    elif location == "arbitrary":
        inputs[1]["extension"] = {"seat": model}
        path = "extension.seat"
    else:
        inputs[1]["extension"] = {"seats": [False, {"choice": model}]}
        path = "extension.seats.1.choice"
    data = report(run(inputs, "--retired-models", str(retired)), 1)
    assert any(f["kind"] == "retired-pin" and f["subject"] == f"policy:{path}" for f in data["findings"])


@pytest.mark.parametrize("model", ["gpt-5.6-sol", "claude-sonnet-5", "legacy"])
def test_real_policy_direct_override_retired(inputs, model):
    policy = yaml.safe_load((ROOT / "config/routing.yaml").read_text())
    aliases = policy["dispatch"]["model_aliases"]
    released = {"models": [{"id": aliases.get(t["model"], t["model"])}
                            for t in policy["dispatch"]["tiers"].values()]}
    released["models"] = list({m["id"]: m for m in released["models"]}.values())
    aliases["legacy"] = "gpt-5.6-sol"
    policy["subagents"]["overrides"]["interflux:fd-safety"] = model
    data = report(run((inputs[0], policy, released, inputs[3])), 1)
    assert any(f["kind"] == "retired-pin" and
               f["subject"] == "policy:subagents.overrides.interflux:fd-safety" for f in data["findings"])


@pytest.mark.parametrize("variable", ["CLAVAIN_CLAUDE_MODEL_FAST", "CLAVAIN_CLAUDE_MODEL_DEEP"])
@pytest.mark.parametrize("model", ["claude-sonnet-5", "gpt-5.6-sol", "legacy"])
def test_audit_reports_retired_environment_override(inputs, monkeypatch, variable, model):
    inputs[1]["dispatch"]["model_aliases"]["legacy"] = "claude-sonnet-5"
    monkeypatch.setenv(variable, model)
    for scope in ((), ("--precheck", "coordination")):
        data = report(run(inputs, *scope), 1)
        assert any(f["kind"] == "retired-pin" and f["subject"] == f"env:{variable}"
                   for f in data["findings"])


@pytest.mark.parametrize("model", ["", "sonnet", "opus", "claude-sonnet-5-5"])
def test_current_environment_override_is_allowed(inputs, monkeypatch, model):
    inputs[1]["dispatch"]["model_aliases"]["opus"] = "claude-opus-5-5"
    inputs[2]["models"].append({"id": "claude-opus-5-5"})
    monkeypatch.setenv("CLAVAIN_CLAUDE_MODEL_FAST", model)
    assert report(run(inputs), 0)["findings"] == []


@pytest.mark.parametrize("variable", ["CLAVAIN_CLAUDE_MODEL_FAST", "CLAVAIN_CLAUDE_MODEL_DEEP"])
@pytest.mark.parametrize("model", ["claude-nonexistent-99", "unknown-model"])
@pytest.mark.parametrize("scope", [(), ("--precheck", "coordination")])
def test_audit_reports_unreleased_environment_override(inputs, monkeypatch, variable, model, scope):
    monkeypatch.setenv(variable, model)
    data = report(run(inputs, *scope), 1)
    assert any(f["kind"] == "unreleased-model" and f["subject"] == f"env:{variable}"
               and model in f["detail"] for f in data["findings"])


@pytest.mark.parametrize("variable", ["CLAVAIN_CLAUDE_MODEL_FAST", "CLAVAIN_CLAUDE_MODEL_DEEP"])
@pytest.mark.parametrize("alias", ["sonnet", "opus", "haiku"])
@pytest.mark.parametrize("scope", [(), ("--precheck", "coordination")])
def test_environment_shorthand_requires_released_policy_alias(inputs, monkeypatch, variable, alias, scope):
    model = "claude-policy-target-99"
    inputs[1]["dispatch"]["model_aliases"][alias] = model
    inputs[2]["models"].append({"id": model})
    inputs[3]["seats"][0]["model"] = model if alias == "sonnet" else "claude-sonnet-5-5"
    monkeypatch.setenv(variable, alias)
    assert report(run(inputs, *scope), 0)["findings"] == []
    inputs[2]["models"] = [m for m in inputs[2]["models"] if m["id"] != model]
    data = report(run(inputs, *scope), 1)
    assert any(f["kind"] == "unreleased-model" and f["subject"] == f"env:{variable}"
               and model in f["detail"] for f in data["findings"])
