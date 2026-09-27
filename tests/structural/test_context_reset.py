"""Structural checks for the observe-mode context-reset telemetry (mk-42j9.40).

This is observe-mode hygiene telemetry, NOT a security boundary. These tests pin
that it stays that way: it ships in observe mode, always allows, never emits a
blocking decision, and implements no enforcement mode.
"""

import json
import re
import subprocess

import pytest

NEW_SHELL = [
    "hooks/lib-context-reset.sh",
    "hooks/context-reset-pre.sh",
    "hooks/context-reset-post.sh",
    "scripts/context-reset-verdict.sh",
    "scripts/context-reset-audit.sh",
    "scripts/context-reset-report.sh",
]
NEW_FILES = NEW_SHELL + ["config/context-reset.yaml", "tests/shell/context_reset.bats"]
DOCS = ["agents/hooks-reference.md", "agents/codex-integration.md"]
BLOCK_DECISION = re.compile(r"""decision["']?\s*:\s*["']?block""")


def _config(project_root):
    values = {}
    for line in (project_root / "config" / "context-reset.yaml").read_text().splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*?)\s*(#.*)?$", line)
        if m:
            values[m.group(1)] = m.group(2)
    return values


def _hooks_for(hooks_json, event, script):
    found = []
    for group in hooks_json["hooks"].get(event, []):
        for hook in group.get("hooks", []):
            if hook.get("command", "").endswith("/hooks/" + script):
                found.append((group.get("matcher"), hook))
    return found


def test_config_ships_observe_mode(project_root):
    cfg = _config(project_root)
    assert cfg["mode"] == "observe"
    assert cfg["batch_max_reads"] == "20"
    assert cfg["batch_max_seconds"] == "600"
    assert float(cfg["cache_write_weight"]) == 1.25
    assert float(cfg["cache_read_weight"]) == 0.1
    assert cfg["exempt_mcp_servers"] == "[]"


def test_config_defers_enforcement_modes(project_root):
    text = (project_root / "config" / "context-reset.yaml").read_text()
    assert "mk-42j9.42" in text
    assert "`mode: off`" in text


def test_hooks_json_wires_context_reset(hooks_json):
    starts = _hooks_for(hooks_json, "SessionStart", "context-reset-post.sh")
    pres = _hooks_for(hooks_json, "PreToolUse", "context-reset-pre.sh")
    posts = _hooks_for(hooks_json, "PostToolUse", "context-reset-post.sh")
    assert len(starts) == 1 and len(pres) == 1 and len(posts) == 1
    assert starts[0][0] == "startup|resume|clear|compact"
    assert pres[0][0] == "Bash|Skill|mcp__.*"
    for _, hook in starts + pres + posts:
        assert hook["type"] == "command"
        assert 0 < hook["timeout"] <= 5
        assert not hook.get("async", False)

    pre = re.compile(pres[0][0])
    post = re.compile(posts[0][0])
    for tool in ("Bash", "Skill", "mcp__github__create_pull_request"):
        assert pre.fullmatch(tool), tool
    for tool in ("Read", "Edit", "WebFetch"):
        assert not pre.fullmatch(tool), tool
    for tool in ("WebFetch", "WebSearch", "Bash", "mcp__context7__get-library-docs", "web.run", "web__search"):
        assert post.fullmatch(tool), tool
    for tool in ("Read", "Edit", "Write", "Grep"):
        assert not post.fullmatch(tool), tool


@pytest.mark.parametrize("rel", NEW_SHELL)
def test_new_shell_files_have_shebang(project_root, rel):
    path = project_root / rel
    assert path.is_file(), rel
    assert path.read_text().startswith("#!/"), rel


@pytest.mark.parametrize("rel", NEW_FILES)
def test_new_files_never_emit_block(project_root, rel):
    assert not BLOCK_DECISION.search((project_root / rel).read_text()), rel


@pytest.mark.parametrize("rel", NEW_FILES + DOCS)
def test_not_a_security_boundary_disclaimer(project_root, rel):
    assert "not a security boundary" in (project_root / rel).read_text().lower(), rel


@pytest.mark.parametrize("rel", NEW_FILES)
def test_no_routing_or_deferred_integration(project_root, rel):
    text = (project_root / rel).read_text()
    assert "routing.yaml" not in text, rel
    assert "quilan" not in text.lower(), rel


@pytest.mark.parametrize("name", ["context-reset-pre.sh", "context-reset-post.sh"])
def test_hooks_fail_open(project_root, name):
    text = (project_root / "hooks" / name).read_text()
    assert "set -uo pipefail" in text
    assert "trap 'exit 0' ERR" in text
    registry = (project_root / "tests" / "structural" / "test_scripts.py").read_text()
    assert f'"{name}"' in registry, f"{name} must be listed in FAIL_OPEN_HOOKS"


def test_verdict_script_only_allows(project_root):
    text = (project_root / "scripts" / "context-reset-verdict.sh").read_text()
    assert '"decision":"allow"' in text
    assert "exit 1" not in text


@pytest.mark.parametrize("stdin", ['{"event":"x"}', "not json", ""])
def test_verdict_script_always_allows_at_runtime(project_root, tmp_path, stdin):
    result = subprocess.run(
        ["bash", str(project_root / "scripts" / "context-reset-verdict.sh"), "--store", str(tmp_path / "store")],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "allow"
