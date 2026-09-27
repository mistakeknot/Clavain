"""Tests for scripts/clavain_selector/flags.py (mk-42j9.7 Task 1, Task R6b)."""

from __future__ import annotations

import json

from selector_helpers import selector_socket_guard  # noqa: F401

from clavain_selector.contract import Point
from clavain_selector.flags import (
    authorization_policy,
    hook_integration,
    load_registry,
    registry_errors,
    resolve_mode,
)

REGISTRY = {
    "schema_version": 1,
    "integrations": {
        "selftest": {
            "flag": "CLAVAIN_SELECTOR_SELFTEST",
            "active_allowed": False,
            "shadow_only": True,
        },
        "launch_profile": {
            "flag": "CLAVAIN_SELECTOR_LAUNCH_PROFILE",
            "active_allowed": True,
            "shadow_only": False,
        },
    },
}


def test_unset_resolves_off():
    resolved = resolve_mode("selftest", {}, REGISTRY)
    assert resolved.mode == "off"


def test_shadow_case_insensitive():
    resolved = resolve_mode("selftest", {"CLAVAIN_SELECTOR_SELFTEST": "SHADOW"}, REGISTRY)
    assert resolved.mode == "shadow"


def test_bogus_value_resolves_off():
    resolved = resolve_mode("selftest", {"CLAVAIN_SELECTOR_SELFTEST": "bogus"}, REGISTRY)
    assert resolved.mode == "off"


def test_global_kill_switch_overrides_shadow():
    env = {"CLAVAIN_SELECTOR_SELFTEST": "shadow", "CLAVAIN_SELECTOR": "off"}
    resolved = resolve_mode("selftest", env, REGISTRY)
    assert resolved.mode == "off"


def test_active_denied_when_not_allowed():
    resolved = resolve_mode("selftest", {"CLAVAIN_SELECTOR_SELFTEST": "active"}, REGISTRY)
    assert resolved.mode == "shadow"
    assert resolved.active_denied is True


def test_active_allowed_resolves_active():
    resolved = resolve_mode("launch_profile", {"CLAVAIN_SELECTOR_LAUNCH_PROFILE": "active"}, REGISTRY)
    assert resolved.mode == "active"
    assert resolved.active_denied is False


def test_unknown_integration_resolves_off():
    resolved = resolve_mode("nonexistent", {"CLAVAIN_SELECTOR_NONEXISTENT": "active"}, REGISTRY)
    assert resolved.mode == "off"


def test_malformed_registry_json_turns_every_integration_off(tmp_path):
    bad = tmp_path / "selector-integrations.json"
    bad.write_text("{not valid json")
    registry = load_registry(bad)
    assert registry["integrations"] == {}
    resolved = resolve_mode("selftest", {"CLAVAIN_SELECTOR_SELFTEST": "shadow"}, registry)
    assert resolved.mode == "off"


def test_missing_registry_file_fails_closed(tmp_path):
    registry = load_registry(tmp_path / "does-not-exist.json")
    assert registry["integrations"] == {}


def test_load_registry_reads_real_config():
    from pathlib import Path

    config_path = Path(__file__).resolve().parents[2] / "config" / "selector-integrations.json"
    registry = load_registry(config_path)
    assert "selftest" in registry["integrations"]
    entry = registry["integrations"]["selftest"]
    assert entry["flag"] == "CLAVAIN_SELECTOR_SELFTEST"
    resolved = resolve_mode("selftest", {"CLAVAIN_SELECTOR_SELFTEST": "shadow"}, registry)
    assert resolved.mode == "shadow"


def test_malformed_registry_not_dict(tmp_path):
    bad = tmp_path / "selector-integrations.json"
    bad.write_text(json.dumps([1, 2, 3]))
    registry = load_registry(bad)
    assert registry["integrations"] == {}


# ---------------------------------------------------------------------------
# Task R6b: registry_errors, authorization_policy, hook_integration
# ---------------------------------------------------------------------------


def test_registry_errors_empty_for_valid_registry():
    valid = {
        "schema_version": 1,
        "integrations": {
            "selftest": {
                "flag": "CLAVAIN_SELECTOR_SELFTEST",
                "authorize": {"allow_all": True},
                "shadow_only": True,
                "hooks": [{"host": "claude-code", "point": "library"}],
            },
        },
    }
    assert registry_errors(valid) == ()


def test_registry_errors_unknown_key():
    bad = {"schema_version": 1, "integrations": {"selftest": {"bogus_key": 1}}}
    errors = registry_errors(bad)
    assert any(e.key == "" and "bogus_key" in e.message for e in errors)


def test_registry_errors_allow_all_requires_shadow_only():
    bad = {
        "schema_version": 1,
        "integrations": {
            "selftest": {"authorize": {"allow_all": True}, "shadow_only": False},
        },
    }
    errors = registry_errors(bad)
    assert any(e.key == "authorize" for e in errors)


def test_registry_errors_malformed_authorize_block():
    bad = {
        "schema_version": 1,
        "integrations": {"selftest": {"authorize": {"allow_ids": "not-a-list"}}},
    }
    errors = registry_errors(bad)
    assert any(e.key == "authorize.allow_ids" for e in errors)


def test_registry_errors_duplicate_hook_pair():
    bad = {
        "schema_version": 1,
        "integrations": {
            "a": {"hooks": [{"host": "claude-code", "point": "library"}]},
            "b": {"hooks": [{"host": "claude-code", "point": "library"}]},
        },
    }
    errors = registry_errors(bad)
    assert any(e.key == "hooks" and "duplicate" in e.message for e in errors)


def test_registry_errors_malformed_hooks_block():
    bad = {
        "schema_version": 1,
        "integrations": {"selftest": {"hooks": [{"host": "claude-code", "point": "not-a-point"}]}},
    }
    errors = registry_errors(bad)
    assert any(e.key == "hooks" for e in errors)


def test_load_registry_fails_closed_on_registry_errors(tmp_path):
    bad = tmp_path / "selector-integrations.json"
    bad.write_text(json.dumps({
        "schema_version": 1,
        "integrations": {"selftest": {"authorize": {"allow_all": True}, "shadow_only": False}},
    }))
    registry = load_registry(bad)
    assert registry["integrations"] == {}


def test_authorization_policy_parse():
    registry = {
        "schema_version": 1,
        "integrations": {
            "selftest": {
                "authorize": {
                    "allow_all": False,
                    "allow_ids": ["cand-a"],
                    "allow_id_prefixes": ["safe-"],
                    "deny_ids": ["cand-b"],
                },
            },
        },
    }
    policy = authorization_policy(registry, "selftest", Point.LIBRARY)
    assert policy.integration == "selftest"
    assert policy.point == Point.LIBRARY
    assert policy.allow_all is False
    assert policy.allow_ids == frozenset({"cand-a"})
    assert policy.allow_id_prefixes == ("safe-",)
    assert policy.deny_ids == frozenset({"cand-b"})


def test_authorization_policy_missing_denies_everything():
    registry = {"schema_version": 1, "integrations": {}}
    policy = authorization_policy(registry, "unknown", Point.LIBRARY)
    assert policy.allow_all is False
    assert policy.allow_ids == frozenset()
    assert policy.allow_id_prefixes == ()
    assert policy.deny_ids == frozenset()


def test_hook_integration_single_match():
    registry = {
        "schema_version": 1,
        "integrations": {
            "selftest": {"hooks": [{"host": "claude-code", "point": "library"}]},
        },
    }
    assert hook_integration(registry, "claude-code", Point.LIBRARY) == "selftest"
    assert hook_integration(registry, "claude-code", Point.PRE_TOOL) is None
    assert hook_integration(registry, "codex", Point.LIBRARY) is None


def test_hook_integration_ambiguous_is_none():
    registry = {
        "schema_version": 1,
        "integrations": {
            "a": {"hooks": [{"host": "claude-code", "point": "library"}]},
            "b": {"hooks": [{"host": "claude-code", "point": "library"}]},
        },
    }
    assert hook_integration(registry, "claude-code", Point.LIBRARY) is None
