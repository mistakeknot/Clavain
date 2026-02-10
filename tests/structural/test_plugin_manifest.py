"""Tests for .claude-plugin/plugin.json manifest."""

import json
import re


def test_plugin_json_valid(project_root):
    """plugin.json parses as valid JSON."""
    path = project_root / ".claude-plugin" / "plugin.json"
    with open(path) as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_plugin_json_required_fields(plugin_json):
    """plugin.json has all required fields."""
    for field in ("name", "version", "description", "author"):
        assert field in plugin_json, f"Missing required field: {field}"


def test_plugin_json_version_format(plugin_json):
    """Version matches semver-like format: X.Y.Z."""
    version = plugin_json["version"]
    assert re.match(r"^\d+\.\d+\.\d+$", version), f"Bad version format: {version}"


def test_mcp_servers_valid(plugin_json):
    """Each mcpServer has a valid type field."""
    servers = plugin_json.get("mcpServers", {})
    assert len(servers) > 0, "No MCP servers defined"
    for name, config in servers.items():
        assert "type" in config, f"MCP server {name!r} missing 'type'"
        assert config["type"] in ("stdio", "http"), (
            f"MCP server {name!r} has invalid type: {config['type']}"
        )
