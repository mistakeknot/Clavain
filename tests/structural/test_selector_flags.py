"""Tests for scripts/clavain_selector/flags.py (mk-42j9.7 Task 1)."""

from __future__ import annotations

import json

from selector_helpers import selector_socket_guard  # noqa: F401

from clavain_selector.flags import load_registry, resolve_mode

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
