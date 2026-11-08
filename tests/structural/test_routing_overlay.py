"""Operator routing overlay: neutral defaults, merge rules, loud failures, profile line."""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "routing_overlay.py"
BASE = ROOT / "config" / "routing.yaml"
GENERATOR = ROOT / "scripts" / "sync-agent-instructions.py"

DEVBOX_OVERLAY = {
    "reasoning": {
        "profiles": {
            "devbox-campaign": {
                "scope": "alex-campaign",
                "roles": {"main-integrator": "main-sonnet"},
            }
        },
        "projects": ["alex-app", "alex-site"],
        "project_aliases": {"proj_devbox1": "alex-app"},
    },
    "dispatch": {
        "roles": {"coordination": "lane-status-quo"},
        "tiers": {"alex-tier": {"model": "claude-sonnet-5-5", "reasoning_effort": "medium", "role": "coordination"}},
    },
}


def run(*args, env=None, home=None):
    merged = {k: v for k, v in os.environ.items()
              if not k.startswith(("CLAVAIN_ROUTING", "CLAVAIN_ORCH", "ALEPH_ORCH"))}
    if home is not None:
        merged["HOME"] = str(home)
        merged.pop("XDG_CACHE_HOME", None)
    merged.update(env or {})
    return subprocess.run([sys.executable, "-I", str(HELPER), *args], capture_output=True, text=True,
                          env=merged, timeout=60)


def write(path, data):
    path.write_text(data if isinstance(data, str) else yaml.safe_dump(data))
    return path


@pytest.fixture
def box(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    cache = tmp_path / "cache"
    return home, {"CLAVAIN_ROUTING_CACHE_DIR": str(cache)}, tmp_path


def resolved(box, overlay, extra=None):
    home, env, tmp = box
    overlay_file = write(tmp / "overlay.yaml", overlay)
    result = run("resolve", "--overlay", str(overlay_file), env={**env, **(extra or {})}, home=home)
    assert result.returncode == 0, result.stderr
    return yaml.safe_load(Path(result.stdout.strip()).read_text()), result


def fail_with(box, overlay):
    home, env, tmp = box
    overlay_file = write(tmp / "bad.yaml", overlay)
    result = run("resolve", "--overlay", str(overlay_file), env=env, home=home)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("routing overlay: ")
    return result.stderr


def fake_orch(directory, snapshot, exit_code=0):
    script = directory / "orch"
    payload = json.dumps(snapshot)
    script.write_text(f"#!/bin/sh\nprintf '%s' '{payload}'\nexit {exit_code}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def operator_snapshot(overlay_path):
    return {"operator.json": json.dumps({"seats": {"routing_overlay": overlay_path}})}


def test_no_overlay_gives_neutral_defaults(box):
    home, env, _ = box
    assert run("path", env=env, home=home).stdout == ""
    plain = run("resolve", env=env, home=home)
    assert plain.returncode == 0 and Path(plain.stdout.strip()) == BASE
    check = run("check", env=env, home=home)
    assert check.returncode == 0 and "neutral defaults apply" in check.stdout
    assert not (Path(env["CLAVAIN_ROUTING_CACHE_DIR"])).exists()


def test_empty_overlay_variable_means_none(box):
    home, env, _ = box
    result = run("path", env={**env, "CLAVAIN_ROUTING_OVERLAY": ""}, home=home)
    assert result.returncode == 0 and result.stdout == ""


def test_packaged_policy_carries_no_instance_data():
    policy = yaml.safe_load(BASE.read_text())
    reasoning = policy["reasoning"]
    assert reasoning["projects"] == []
    assert reasoning["profiles"] == {}
    assert reasoning["project_profiles"] == {}
    assert reasoning["project_aliases"] == {}
    text = BASE.read_text()
    assert not re.search(r"thr_[a-z0-9]{10}", text)
    assert not re.search(r"proj_[a-z0-9]{10}", text)
    assert "/home/" not in text and "~/.bb-machines" not in text


def test_synthetic_overlay_merges_every_overlaid_key(box):
    merged, result = resolved(box, DEVBOX_OVERLAY)
    base = yaml.safe_load(BASE.read_text())
    assert merged["reasoning"]["profiles"]["devbox-campaign"]["scope"] == "alex-campaign"
    assert merged["reasoning"]["projects"] == ["alex-app", "alex-site"]
    assert merged["reasoning"]["project_aliases"] == {"proj_devbox1": "alex-app"}
    assert merged["dispatch"]["roles"]["coordination"] == "lane-status-quo"
    assert merged["dispatch"]["roles"]["lane"] == base["dispatch"]["roles"]["lane"]
    assert merged["dispatch"]["tiers"]["alex-tier"]["role"] == "coordination"
    assert set(base["dispatch"]["tiers"]) <= set(merged["dispatch"]["tiers"])
    assert merged["reasoning"]["project_profiles"] == {}


def test_untouched_keys_survive_unchanged(box):
    merged, _ = resolved(box, {"reasoning": {"projects": ["alex-app"]}})
    base = yaml.safe_load(BASE.read_text())
    merged["reasoning"]["projects"] = base["reasoning"]["projects"]
    assert merged == base


@pytest.mark.parametrize("text", ["", "\n", "# only a comment\n", "null\n", "~\n"])
def test_empty_or_null_overlay_is_an_error(box, text):
    stderr = fail_with(box, text)
    assert "empty or null document" in stderr


def test_scalar_replaces(box):
    base = yaml.safe_load(BASE.read_text())
    tier = next(name for name, spec in base["dispatch"]["tiers"].items() if "reasoning_effort" in spec)
    other = "low" if base["dispatch"]["tiers"][tier]["reasoning_effort"] != "low" else "high"
    merged, _ = resolved(box, {"dispatch": {"tiers": {tier: {"reasoning_effort": other}}}})
    assert merged["dispatch"]["tiers"][tier]["reasoning_effort"] == other
    assert merged["dispatch"]["tiers"][tier]["model"] == base["dispatch"]["tiers"][tier]["model"]


def test_list_replaces_wholesale(box):
    base = yaml.safe_load(BASE.read_text())
    tier, spec = next((n, s) for n, s in base["dispatch"]["tiers"].items() if s.get("fallbacks"))
    chosen = [spec["fallbacks"][0]]
    merged, _ = resolved(box, {"dispatch": {"tiers": {tier: {"fallbacks": chosen}}}})
    assert merged["dispatch"]["tiers"][tier]["fallbacks"] == chosen


def test_open_map_entry_deep_merges_into_existing(box):
    overlay = {"reasoning": {"profiles": {"one": {"scope": "s1", "roles": {"validation": "validation-sol"}}}}}
    first, _ = resolved(box, overlay)
    assert first["reasoning"]["profiles"]["one"]["roles"] == {"validation": "validation-sol"}


def test_closed_maps_reject_new_keys(box):
    for overlay, where in (
        ({"surprise": 1}, "surprise"),
        ({"reasoning": {"surprise": 1}}, "reasoning.surprise"),
        ({"dispatch": {"surprise": 1}}, "dispatch.surprise"),
        ({"dispatch": {"tiers": {"main-sonnet": {"surprise": 1}}}}, "dispatch.tiers.main-sonnet.surprise"),
    ):
        err = fail_with(box, overlay)
        assert where + ": unknown key" in err


def test_null_is_rejected(box):
    assert "null is not allowed" in fail_with(box, {"reasoning": {"projects": None}})
    assert "null is not allowed" in fail_with(box, {"reasoning": {"profiles": {"x": {"scope": None}}}})
    assert "null is not allowed" in fail_with(box, {"reasoning": {"projects": ["a", None]}})


def test_type_mismatch_is_rejected(box):
    assert "reasoning.projects: expected list, found string" in fail_with(box, {"reasoning": {"projects": "alex-app"}})
    assert "reasoning: expected mapping, found list" in fail_with(box, {"reasoning": []})
    base = yaml.safe_load(BASE.read_text())
    tier = next(name for name, spec in base["dispatch"]["tiers"].items() if "reasoning_effort" in spec)
    assert "expected string, found number" in fail_with(box, {"dispatch": {"tiers": {tier: {"reasoning_effort": 3}}}})


def test_malformed_yaml_is_rejected(box):
    assert "malformed YAML" in fail_with(box, "reasoning: [unclosed\n")


def test_non_mapping_top_level_is_rejected(box):
    assert "top level is not a mapping" in fail_with(box, "- a\n- b\n")


def test_missing_overlay_variable_target_is_rejected(box):
    home, env, tmp = box
    result = run("path", env={**env, "CLAVAIN_ROUTING_OVERLAY": str(tmp / "absent.yaml")}, home=home)
    assert result.returncode == 1 and "is not a file" in result.stderr


def test_env_overlay_selected_and_cached_by_content(box):
    home, env, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    first = run("path", env={**env, "CLAVAIN_ROUTING_OVERLAY": str(overlay)}, home=home)
    assert first.returncode == 0
    target = Path(first.stdout.strip())
    assert target.parent == Path(env["CLAVAIN_ROUTING_CACHE_DIR"])
    expected = hashlib.sha256(BASE.read_bytes() + b"\0" + overlay.read_bytes()).hexdigest()
    assert target.name == f"routing.{expected}.yaml"
    again = run("path", env={**env, "CLAVAIN_ROUTING_OVERLAY": str(overlay)}, home=home)
    assert again.stdout == first.stdout
    write(overlay, {"reasoning": {"projects": ["alex-other"]}})
    changed = run("path", env={**env, "CLAVAIN_ROUTING_OVERLAY": str(overlay)}, home=home)
    assert changed.stdout != first.stdout
    assert target.exists()


def test_operator_config_names_the_overlay(box):
    home, env, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    orch = fake_orch(tmp, operator_snapshot(str(overlay)))
    config = write(tmp / "operator.toml", "")
    result = run("path", env={**env, "ALEPH_ORCH_CONFIG": str(config), "CLAVAIN_ORCH_BIN": str(orch)}, home=home)
    assert result.returncode == 0
    merged = yaml.safe_load(Path(result.stdout.strip()).read_text())
    assert merged["reasoning"]["projects"] == ["alex-app", "alex-site"]


def test_default_operator_config_location_is_used(box):
    home, env, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    orch = fake_orch(tmp, operator_snapshot(str(overlay)))
    config_dir = home / ".config" / "aleph-orchestration"
    config_dir.mkdir(parents=True)
    write(config_dir / "operator.toml", "")
    result = run("path", env={**env, "CLAVAIN_ORCH_BIN": str(orch)}, home=home)
    assert result.returncode == 0 and result.stdout.strip()


def test_env_overlay_beats_operator_config(box):
    home, env, tmp = box
    named = write(tmp / "named.yaml", {"reasoning": {"projects": ["from-config"]}})
    chosen = write(tmp / "chosen.yaml", {"reasoning": {"projects": ["from-env"]}})
    orch = fake_orch(tmp, operator_snapshot(str(named)))
    config = write(tmp / "operator.toml", "")
    result = run("path", env={**env, "ALEPH_ORCH_CONFIG": str(config), "CLAVAIN_ORCH_BIN": str(orch),
                              "CLAVAIN_ROUTING_OVERLAY": str(chosen)}, home=home)
    merged = yaml.safe_load(Path(result.stdout.strip()).read_text())
    assert merged["reasoning"]["projects"] == ["from-env"]


def test_operator_config_without_overlay_means_neutral(box):
    home, env, tmp = box
    orch = fake_orch(tmp, operator_snapshot(""))
    config = write(tmp / "operator.toml", "")
    result = run("path", env={**env, "ALEPH_ORCH_CONFIG": str(config), "CLAVAIN_ORCH_BIN": str(orch)}, home=home)
    assert result.returncode == 0 and result.stdout == ""


@pytest.mark.parametrize("value,fragment", [
    ("relative/overlay.yaml", "is not an absolute path"),
    ("/nonexistent/devbox/overlay.yaml", "does not exist"),
])
def test_operator_config_bad_overlay_path_fails_loudly(box, value, fragment):
    home, env, tmp = box
    orch = fake_orch(tmp, operator_snapshot(value))
    config = write(tmp / "operator.toml", "")
    result = run("path", env={**env, "ALEPH_ORCH_CONFIG": str(config), "CLAVAIN_ORCH_BIN": str(orch)}, home=home)
    assert result.returncode == 1 and fragment in result.stderr


def test_failing_orch_fails_loudly(box):
    home, env, tmp = box
    orch = fake_orch(tmp, {}, exit_code=3)
    config = write(tmp / "operator.toml", "")
    result = run("path", env={**env, "ALEPH_ORCH_CONFIG": str(config), "CLAVAIN_ORCH_BIN": str(orch)}, home=home)
    assert result.returncode == 1 and "orch snapshot failed" in result.stderr


def test_missing_configured_config_file_fails_loudly(box):
    home, env, tmp = box
    result = run("path", env={**env, "ALEPH_ORCH_CONFIG": str(tmp / "absent.toml")}, home=home)
    assert result.returncode == 1 and "is not a file" in result.stderr


def test_check_reports_digests(box):
    home, env, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    result = run("check", "--overlay", str(overlay), env=env, home=home)
    assert result.returncode == 0
    assert f"sha256={hashlib.sha256(overlay.read_bytes()).hexdigest()}" in result.stdout


def generator_module():
    spec = importlib.util.spec_from_file_location("sync_agent_instructions", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_profile_sentence_comes_from_policy(tmp_path):
    module = generator_module()
    policy = write(tmp_path / "policy.yaml", {"reasoning": {"profiles": {
        "devbox-campaign": {"scope": "alex-campaign"},
        "unscoped": {"roles": {}},
    }}})
    sentence = module.profile_sentences(policy)
    assert sentence == " `CLAVAIN_POLICY_PROFILE=devbox-campaign` requires `scope: alex-campaign` and applies only there."
    none = write(tmp_path / "none.yaml", {"reasoning": {"profiles": {}}})
    assert module.profile_sentences(none) == ""
    assert module.profile_sentences(write(tmp_path / "bad.yaml", "reasoning: [")) == ""


def render_with_policy(policy):
    result = subprocess.run([sys.executable, "-I", str(GENERATOR), "--source", str(ROOT), "--host", "claude",
                             "--render", "--policy", str(policy)],
                            capture_output=True, text=True, timeout=60,
                            env={k: v for k, v in os.environ.items() if not k.startswith("CLAVAIN_ROUTING")})
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_rendered_contract_carries_policy_profile_line(tmp_path):
    with_profile = write(tmp_path / "with.yaml", {"reasoning": {"profiles": {"devbox-campaign": {"scope": "alex-campaign"}}}})
    body = render_with_policy(with_profile)
    assert "`CLAVAIN_POLICY_PROFILE=devbox-campaign` requires `scope: alex-campaign` and applies only there." in body
    assert "{{POLICY_PROFILES}}" not in body
    plain = render_with_policy(BASE)
    assert "CLAVAIN_POLICY_PROFILE=" not in plain
    assert "{{POLICY_PROFILES}}" not in plain


def test_contract_template_names_no_operator_values():
    text = (ROOT / "config" / "agent-instructions.md").read_text()
    assert "{{POLICY_PROFILES}}" in text
    assert "ci-campaign-pilot" not in text and "mk-ag2s" not in text


@pytest.mark.requires_ic
def test_resolved_policy_changes_routing_under_ic(box):
    if shutil.which("ic") is None:
        pytest.skip("ic not installed")
    home, env, tmp = box
    context = tmp / "context.json"
    context.write_text(json.dumps({"reasons": [], "rationale": "overlay test"}))
    def route(policy):
        out = subprocess.run(["ic", "--json", "route", "dispatch", f"--policy={policy}",
                              f"--context-file={context}", "--role=coordination"],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)["profile_ref"]
    merged_path = run("resolve", "--overlay", str(write(tmp / "alex.yaml", DEVBOX_OVERLAY)), env=env, home=home).stdout.strip()
    assert route(BASE) == "coordination-sonnet"
    assert route(merged_path) == "lane-status-quo"


@pytest.mark.requires_ic
def test_route_spawn_reads_the_overlay_for_project_slugs(box):
    if shutil.which("ic") is None:
        pytest.skip("ic not installed")
    home, env, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    base_env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAVAIN_ROUTING", "CLAVAIN_ORCH", "ALEPH_ORCH"))}
    base_env.update(env, HOME=str(home), CLAVAIN_RECEIPT_DIR=str(tmp / "receipts"))
    command = [str(ROOT / "scripts" / "route-spawn.sh"), "--role", "coordinator-seat", "--project", "alex-app"]
    neutral = subprocess.run(command, capture_output=True, text=True, env=base_env, timeout=120)
    assert neutral.returncode == 2 and "unknown coordinator-seat project: alex-app" in neutral.stderr
    base_env["CLAVAIN_ROUTING_OVERLAY"] = str(overlay)
    overlaid = subprocess.run(command, capture_output=True, text=True, env=base_env, timeout=120)
    assert overlaid.returncode == 0, overlaid.stderr
    assert len(overlaid.stdout.split()) == 3
    base_env["CLAVAIN_ROUTING_OVERLAY"] = str(tmp / "absent.yaml")
    broken = subprocess.run(command, capture_output=True, text=True, env=base_env, timeout=120)
    assert broken.returncode == 3 and "routing overlay:" in broken.stderr


def overlay_module():
    spec = importlib.util.spec_from_file_location("routing_overlay_under_test", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("text", ["", "\n", "# comment only\n", "null\n", "~\n"])
def test_build_rejects_empty_and_null_overlay(tmp_path, text):
    module = overlay_module()
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(text)
    with pytest.raises(module.OverlayError, match="empty or null document"):
        module.build(BASE, overlay)


def test_build_accepts_explicit_empty_mapping(tmp_path):
    module = overlay_module()
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text("{}\n")
    text, _ = module.build(BASE, overlay)
    assert yaml.safe_load(text) == yaml.safe_load(BASE.read_text())


def test_null_overlay_never_restores_neutral_routing(box):
    home, env, tmp = box
    overlay = write(tmp / "null.yaml", "null\n")
    result = run("policy", env={**env, "CLAVAIN_ROUTING_OVERLAY": str(overlay)}, home=home)
    assert result.returncode == 1 and result.stdout == ""
    assert "empty or null document" in result.stderr


def test_policy_verb_prints_effective_path(box):
    home, env, tmp = box
    neutral = run("policy", env={**env, "CLAVAIN_ROUTING_OVERLAY": ""}, home=home)
    assert neutral.returncode == 0 and Path(neutral.stdout.strip()) == BASE
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    active = run("policy", env={**env, "CLAVAIN_ROUTING_OVERLAY": str(overlay)}, home=home)
    assert active.returncode == 0
    path = Path(active.stdout.strip())
    assert path != BASE and yaml.safe_load(path.read_text())["reasoning"]["projects"] == ["alex-app", "alex-site"]


@pytest.mark.parametrize("bad", ["absent", "unknown-key", "malformed"])
def test_policy_verb_fails_on_bad_overlay(box, bad):
    home, env, tmp = box
    if bad == "absent":
        target = tmp / "absent.yaml"
    elif bad == "unknown-key":
        target = write(tmp / "bad.yaml", {"no_such_section": {"a": 1}})
    else:
        target = write(tmp / "bad.yaml", "reasoning: [")
    result = run("policy", env={**env, "CLAVAIN_ROUTING_OVERLAY": str(target)}, home=home)
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.startswith("routing overlay: ")


LIB = ROOT / "scripts" / "lib-routing.sh"


def lib_env(box, overlay, extra=None):
    home, env, tmp = box
    merged = {k: v for k, v in os.environ.items()
              if not k.startswith(("CLAVAIN_ROUTING", "CLAVAIN_ORCH", "ALEPH_ORCH", "CLAVAIN_RUN_ID"))}
    merged.update(env, HOME=str(home))
    merged["CLAVAIN_ROUTING_OVERLAY"] = overlay
    merged["PATH"] = f"{tmp / 'bin'}:{os.environ['PATH']}" if (tmp / "bin").is_dir() else os.environ["PATH"]
    merged.update(extra or {})
    return merged


def lib_call(box, overlay, snippet, extra=None):
    return subprocess.run(["bash", "-c", f'source "{LIB}"; {snippet}'], capture_output=True, text=True,
                          env=lib_env(box, overlay, extra), timeout=120)


def stub_ic(box, body):
    _, _, tmp = box
    (tmp / "bin").mkdir(exist_ok=True)
    stub = tmp / "bin" / "ic"
    stub.write_text("#!/bin/sh\n" + body)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


def test_lib_find_config_returns_neutral_without_overlay(box):
    result = lib_call(box, "", '_routing_find_config')
    assert result.returncode == 0
    assert Path(result.stdout.strip()).resolve() == BASE


def test_lib_find_config_returns_the_overlaid_file(box):
    _, _, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    result = lib_call(box, str(overlay), '_routing_find_config')
    assert result.returncode == 0
    found = Path(result.stdout.strip())
    assert found.resolve() != BASE
    assert yaml.safe_load(found.read_text())["dispatch"]["roles"]["coordination"] == "lane-status-quo"


@pytest.mark.parametrize("kind", ["absent", "invalid", "null"])
def test_lib_find_config_fails_closed_on_bad_overlay(box, kind):
    _, _, tmp = box
    target = {"absent": tmp / "absent.yaml", "invalid": write(tmp / "bad.yaml", {"nope": 1}),
              "null": write(tmp / "null.yaml", "null\n")}[kind]
    result = lib_call(box, str(target), '_routing_find_config; echo "rc=$?"')
    assert "rc=2" in result.stdout
    assert str(BASE) not in result.stdout
    assert "routing overlay:" in result.stderr


@pytest.mark.parametrize("snippet", [
    "routing_executor_mode",
    "routing_executor_order_raw default",
    "routing_resolve_dispatch_tier coordination",
    "routing_list_mappings",
    "routing_resolve_model --phase plan",
    "routing_classify_complexity --prompt-tokens 100",
])
def test_lib_public_resolvers_fail_on_bad_overlay(box, snippet):
    _, _, tmp = box
    result = lib_call(box, str(tmp / "absent.yaml"), f'{snippet}; echo "rc=$?"',
                      extra={"CLAVAIN_EXECUTOR_ROUTING_MODE": ""})
    assert "rc=0" not in result.stdout
    assert "routing overlay:" in result.stderr


def test_lib_ic_fast_path_receives_the_effective_policy(box):
    _, _, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    seen = tmp / "seen.txt"
    stub_ic(box, f'printf "%s\\n" "${{CLAVAIN_ROUTING_POLICY:-unset}}" >> "{seen}"\necho stub-tier\n')
    result = lib_call(box, str(overlay), "routing_resolve_dispatch_tier coordination")
    assert result.returncode == 0 and result.stdout.strip() == "stub-tier"
    policy = Path(seen.read_text().strip().splitlines()[0])
    assert policy.is_file() and policy.resolve() != BASE
    assert yaml.safe_load(policy.read_text())["dispatch"]["roles"]["coordination"] == "lane-status-quo"


def test_lib_ic_fast_path_gets_no_policy_without_overlay(box):
    _, _, tmp = box
    seen = tmp / "seen.txt"
    stub_ic(box, f'printf "%s\\n" "${{CLAVAIN_ROUTING_POLICY:-unset}}" >> "{seen}"\necho stub-tier\n')
    result = lib_call(box, "", "routing_resolve_dispatch_tier coordination")
    assert result.returncode == 0
    assert seen.read_text().strip() == "unset"


@pytest.mark.parametrize("snippet", [
    "routing_resolve_dispatch_tier coordination",
    "routing_resolve_model --phase plan",
])
def test_lib_ic_is_not_called_when_overlay_is_bad(box, snippet):
    _, _, tmp = box
    marker = tmp / "called.txt"
    stub_ic(box, f'echo called >> "{marker}"\necho stub-tier\n')
    result = lib_call(box, str(tmp / "absent.yaml"), f'{snippet}; echo "rc=$?"')
    assert not marker.exists()
    assert "rc=0" not in result.stdout and "stub-tier" not in result.stdout
    assert "routing overlay:" in result.stderr


def test_lib_explicit_policy_is_left_alone(box):
    _, _, tmp = box
    seen = tmp / "seen.txt"
    stub_ic(box, f'printf "%s\\n" "${{CLAVAIN_ROUTING_POLICY:-unset}}" >> "{seen}"\necho stub-tier\n')
    result = lib_call(box, str(tmp / "absent.yaml"), "routing_resolve_dispatch_tier coordination",
                      extra={"CLAVAIN_ROUTING_POLICY": str(BASE)})
    assert result.returncode == 0 and seen.read_text().strip() == str(BASE)


PUBLIC_FILES = [
    "scripts/dispatch.sh",
    "scripts/routing_overlay.py",
    "scripts/lib-routing.sh",
    "scripts/sync-agent-instructions.py",
    "config/routing.yaml",
    "config/agent-instructions.md",
    "docs/canon/reasoning-routing.md",
    "docs/canon/reasoning-routing-operations.md",
    "docs/canon/reasoning-routing-verification.md",
    "skills/project-onboard/SKILL.md",
    "skills/project-onboard/SKILL-compact.md",
    "skills/project-onboard/templates/AGENTS.md.tmpl",
]


def test_public_files_carry_no_private_paths_or_hostnames():
    host = "".join(["zk", "lw"]) + "(?:-ci)?"
    pattern = re.compile(
        r"/Users/[a-z]|/home/[A-Za-z]|\.bb-machines|\b" + host + r"\b|\bsma@|thr_[a-z0-9]{8,}"
    )
    offenders = []
    for name in PUBLIC_FILES:
        path = ROOT / name
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{name}:{number}")
    assert offenders == []


# --- PyYAML is only needed when an overlay is configured -------------------

BUILDER = ROOT / "scripts" / "build-review-packet.py"


@pytest.fixture
def no_yaml(tmp_path):
    """A PYTHONPATH shim directory under which `import yaml` raises ImportError."""
    shim = tmp_path / "noyaml"
    shim.mkdir()
    (shim / "yaml.py").write_text('raise ImportError("PyYAML hidden for this test")\n')
    return {"PYTHONPATH": str(shim)}


def test_hidden_yaml_shim_really_hides_yaml(no_yaml):
    result = subprocess.run([sys.executable, "-c", "import yaml"], capture_output=True, text=True,
                            env={**os.environ, **no_yaml})
    assert result.returncode != 0 and "PyYAML hidden" in result.stderr


@pytest.mark.parametrize("verb", ["path", "check"])
def test_neutral_verbs_need_no_pyyaml_isolated_mode(box, verb):
    """Same check under -I, where PYTHONPATH is ignored: block yaml in-process instead."""
    home, env, _ = box
    code = ("import runpy, sys; sys.modules['yaml'] = None; "
            "sys.argv = ['routing_overlay.py', %r]; runpy.run_path(%r, run_name='__main__')" % (verb, str(HELPER)))
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("CLAVAIN_ROUTING", "CLAVAIN_ORCH", "ALEPH_ORCH"))}
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60,
                            env={**clean, **env, "HOME": str(home)})
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    if verb == "path":
        assert result.stdout == ""


def test_path_verb_without_pyyaml_via_shim(box, no_yaml):
    home, env, _ = box
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("CLAVAIN_ROUTING", "CLAVAIN_ORCH", "ALEPH_ORCH"))}
    result = subprocess.run([sys.executable, str(HELPER), "path"], capture_output=True, text=True, timeout=60,
                            env={**clean, **env, **no_yaml, "HOME": str(home)})
    assert result.returncode == 0, result.stderr
    assert result.stdout == "" and result.stderr == ""


def test_configured_overlay_without_pyyaml_fails_closed(box, no_yaml):
    home, env, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("CLAVAIN_ROUTING", "CLAVAIN_ORCH", "ALEPH_ORCH"))}
    for verb in ("path", "policy", "check"):
        result = subprocess.run([sys.executable, str(HELPER), verb], capture_output=True, text=True, timeout=60,
                                env={**clean, **env, **no_yaml, "HOME": str(home),
                                     "CLAVAIN_ROUTING_OVERLAY": str(overlay)})
        assert result.returncode == 1, verb
        assert result.stdout == ""
        assert result.stderr.startswith("routing overlay: PyYAML is required"), result.stderr
        assert "Traceback" not in result.stderr


def packet_policy_path(box, extra):
    home, env, _ = box
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("CLAVAIN_ROUTING", "CLAVAIN_ORCH", "ALEPH_ORCH"))}
    code = ("import importlib.util, sys; "
            "s = importlib.util.spec_from_file_location('brp', %r); m = importlib.util.module_from_spec(s); "
            "s.loader.exec_module(m); print(m._routing_policy_path())" % str(BUILDER))
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                          env={**clean, **env, "HOME": str(home), **extra})


def test_packet_builder_policy_path_needs_no_pyyaml_when_neutral(box, no_yaml):
    result = packet_policy_path(box, no_yaml)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == BASE


def test_packet_builder_policy_path_fails_closed_for_configured_overlay_without_pyyaml(box, no_yaml):
    _, _, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    result = packet_policy_path(box, {**no_yaml, "CLAVAIN_ROUTING_OVERLAY": str(overlay)})
    assert result.returncode != 0
    assert "PyYAML is required" in result.stderr


def test_lib_find_config_is_neutral_without_pyyaml(box, no_yaml):
    result = lib_call(box, "", '_routing_find_config', extra=no_yaml)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == BASE


def test_lib_find_config_fails_closed_for_configured_overlay_without_pyyaml(box, no_yaml):
    _, _, tmp = box
    overlay = write(tmp / "alex.yaml", DEVBOX_OVERLAY)
    result = lib_call(box, str(overlay), '_routing_find_config; echo "rc=$?"', extra=no_yaml)
    assert "rc=2" in result.stdout
    assert "PyYAML is required" in result.stderr


@pytest.mark.parametrize("script", ["capacity-fallback.sh", "dispatch.sh"])
def test_shell_callers_resolve_neutral_policy_without_pyyaml(box, no_yaml, script):
    """The overlay call these scripts make at startup must not die on a missing PyYAML."""
    home, env, tmp = box
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("CLAVAIN_ROUTING", "CLAVAIN_ORCH", "ALEPH_ORCH"))}
    result = subprocess.run(["bash", str(ROOT / "scripts" / script), "--help"], capture_output=True, text=True,
                            timeout=60, env={**clean, **env, **no_yaml, "HOME": str(home)})
    assert "ModuleNotFoundError" not in result.stderr and "PyYAML" not in result.stderr, result.stderr
