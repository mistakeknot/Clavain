"""Exercise managed MCP updates and the actual installer in isolated homes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/sync-codex-mcp.py"
START = "# BEGIN CLAVAIN MCP SERVERS\n"
END = "# END CLAVAIN MCP SERVERS\n"
BLOCK = START + '[mcp_servers.managed]\ncommand = "true"\n' + END


def invoke(config, block, *flags):
    source = config.parent / "block.toml"
    source.write_text(block)
    return subprocess.run(["python3", str(SCRIPT), "--file", str(config),
                           "--block", str(source), *flags], capture_output=True, text=True)


def test_preserves_unmanaged_bytes_mode_and_symlink(tmp_path):
    target = tmp_path / "operator.toml"
    link = tmp_path / "config.toml"
    before = '# personal comment\n[mcp_servers."owner.server"]\ncommand = "owner"\nenv = { KEY = "fixture-only" }\n'
    suffix = '\n[profiles.personal]\nmodel = "example" # retained\n'
    target.write_text(before + START + '[mcp.servers.managed]\ncommand = "old"\n' + END + suffix)
    target.chmod(0o640)
    link.symlink_to(target)
    result = invoke(link, BLOCK)
    assert result.returncode == 0, result.stderr
    assert link.is_symlink()
    assert target.stat().st_mode & 0o777 == 0o640
    assert target.read_text() == before + BLOCK + suffix
    prior = target.stat().st_mtime_ns
    assert invoke(link, BLOCK).returncode == 0
    assert target.stat().st_mtime_ns == prior
    assert invoke(link, BLOCK, "--check").returncode == 0


@pytest.mark.parametrize("content", [
    START + '[mcp_servers.x]\ncommand = "x"\n',
    END + START,
    BLOCK + BLOCK,
    'bad = [\n' + BLOCK,
    '[mcp_servers.managed]\ncommand = "user"\n',
    START + '[profiles.personal]\nmodel = "owned"\n' + END,
    'note = """\n' + BLOCK + '"""\n',
])
def test_rejects_malformed_or_conflicting_content_without_write(tmp_path, content):
    config = tmp_path / "config.toml"
    config.write_text(content)
    result = invoke(config, BLOCK)
    assert result.returncode != 0
    assert config.read_text() == content


def test_quoted_keys_and_unrelated_legacy_tables(tmp_path):
    config = tmp_path / "config.toml"
    old = '[mcp.servers.personal]\ncommand = "personal"\n'
    config.write_text(old)
    block = START + '[mcp_servers."with.dot".env]\n"odd:key" = "value"\n[mcp_servers."with.dot"]\ncommand = "true"\n' + END
    assert invoke(config, block).returncode == 0
    assert config.read_text().startswith(old)
    assert invoke(config, block, "--check").returncode == 0


def test_dry_run_and_dangling_symlink(tmp_path):
    config = tmp_path / "config.toml"
    assert invoke(config, BLOCK, "--dry-run").returncode == 0
    assert not config.exists()
    config.symlink_to(tmp_path / "missing")
    assert invoke(config, BLOCK).returncode != 0
    assert config.is_symlink() and not config.exists()


def test_doctor_rejects_wrong_managed_schema(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(BLOCK.replace("mcp_servers", "mcp.servers"))
    assert invoke(config, BLOCK, "--check").returncode != 0


def test_removal_preserves_explicit_unmanaged_parent_table(tmp_path):
    config = tmp_path / 'config.toml'
    prefix = '[mcp_servers]\n# explicit operator parent\n'
    config.write_text(prefix + BLOCK)
    result = invoke(config, BLOCK, '--remove', '--dry-run')
    assert result.returncode == 0, result.stderr
    assert config.read_text() == prefix + BLOCK
    result = invoke(config, BLOCK, '--remove')
    assert result.returncode == 0, result.stderr
    assert config.read_text() == prefix + '\n'


def test_crlf_block_preserves_surrounding_bytes(tmp_path):
    config = tmp_path / "config.toml"
    prefix = b'# operator comment\r\n'
    suffix = b'\r\n[profiles.personal]\r\nmodel = "example"\r\n'
    config.write_bytes(prefix + BLOCK.replace('\n', '\r\n').encode() + suffix)
    assert invoke(config, BLOCK, "--check").returncode == 0
    assert invoke(config, BLOCK).returncode == 0
    assert config.read_bytes() == prefix + BLOCK.rstrip('\n').encode() + b'\r\n' + suffix


def test_crlf_removal_preserves_surrounding_bytes(tmp_path):
    config = tmp_path / 'config.toml'
    prefix = b'# operator comment\r\n'
    suffix = b'\r\n[mcp_servers.personal]\r\ncommand = "owner"\r\n'
    config.write_bytes(prefix + BLOCK.replace('\n', '\r\n').encode() + suffix)
    assert invoke(config, BLOCK, '--remove').returncode == 0
    assert config.read_bytes() == prefix + b'\r\n' + suffix


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS ACL semantics')
def test_macos_acl_survives_atomic_replacement(tmp_path):
    config = tmp_path / 'config.toml'
    config.write_text(BLOCK)
    config.chmod(0o640)
    subprocess.run(['/bin/chmod', '+a', 'daemon deny read', str(config)], check=True)
    def acl():
        lines = subprocess.check_output(['/bin/ls', '-le', str(config)], text=True).splitlines()
        return lines[1:]
    original = acl()
    assert original
    result = invoke(config, BLOCK.replace('"true"', '"false"'))
    assert result.returncode == 0, result.stderr
    assert acl() == original
    assert config.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize("fields", [
    'command = "true"\nurl = "https://example.invalid/mcp"\n',
    'command = "true"\nargs = [1]\n',
    'command = 1\n',
    'command = "true"\nenv = { TOKEN = 2 }\n',
    'url = "https://example.invalid/mcp"\nargs = ["bad"]\n',
    'url = "https://example.invalid/mcp"\nhttp_headers = { TOKEN = 2 }\n',
    '',
])
def test_rejects_invalid_managed_server_semantics(tmp_path, fields):
    config = tmp_path / "config.toml"
    invalid = START + '[mcp_servers.managed]\n' + fields + END
    config.write_text(invalid)
    for flags in [(), ("--dry-run",), ("--check",)]:
        assert invoke(config, invalid, *flags).returncode != 0
        assert config.read_text() == invalid


def fixture_source(tmp_path):
    source = tmp_path / "source"
    for directory in ["scripts", "skills", "commands", "config", "bin", "hooks", ".claude-plugin"]:
        (source / directory).mkdir(parents=True)
    (source / "README.md").write_text("fixture\n")
    for relative in ("config/codex-instructions.md", "config/agent-instructions.md", "config/routing.yaml", "config/host-adapters.json", "scripts/sync-codex-instructions.py"):
        shutil.copyfile(ROOT / relative, source / relative)
    (source / "bin/clavain-cli").write_text("#!/bin/sh\nexit 0\n")
    (source / "bin/clavain-cli").chmod(0o755)
    for script in ["scripts/remontoire-attention.sh", "scripts/codex-session-refresh.sh", "hooks/context-gateway.sh"]:
        (source / script).write_text("#!/bin/sh\nexit 0\n")
        (source / script).chmod(0o755)
    (source / ".claude-plugin/plugin.json").write_text(json.dumps({"mcpServers": {"managed.dot": {"command": "true", "env": {"FIXTURE": "yes"}}}}))
    return source


def installer(tmp_path, source):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    codex = home / ".codex"
    codex.mkdir(exist_ok=True)
    env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(codex),
           "AGENTS_SKILLS_DIR": str(home / ".agents/skills"), "LOCAL_BIN_DIR": str(home / ".local/bin"),
           "CLAVAIN_CLI_LINK": str(home / ".local/bin/clavain-cli")}
    result = subprocess.run(["bash", str(ROOT / "scripts/install-codex.sh"), "install",
                             "--source", str(source), "--no-prompts"], env=env, text=True, capture_output=True)
    return result, codex, env


def test_real_installer_preserves_user_server_and_cli_reads_generated_config(tmp_path):
    source = fixture_source(tmp_path)
    codex = tmp_path / "home/.codex"
    codex.mkdir(parents=True)
    original = '# keep\n[mcp_servers."operator.dot"]\ncommand = "true"\n'
    (codex / "config.toml").write_text(original)
    result, codex, env = installer(tmp_path, source)
    assert result.returncode == 0, result.stderr
    content = (codex / "config.toml").read_text()
    assert content.startswith(original)
    assert '[mcp_servers."managed.dot"]' in content
    binary = shutil.which("codex")
    if binary:
        parsed = subprocess.run([binary, "mcp", "list", "--json"], env=env, text=True, capture_output=True)
        assert parsed.returncode == 0, parsed.stderr
        assert {row["name"] for row in json.loads(parsed.stdout)} == {"operator.dot", "managed.dot"}


def test_real_cli_accepts_both_transport_definitions(tmp_path):
    source = fixture_source(tmp_path)
    servers = {
        'stdio.quoted': {'command': 'true', 'args': ['space value', 'quoted"value'], 'env': {'ODD:KEY': 'fixture-only'}},
        'http.quoted': {'type': 'http', 'url': 'https://example.invalid/mcp', 'headers': {'X-Fixture': 'fixture-only'}},
    }
    (source / '.claude-plugin/plugin.json').write_text(json.dumps({'mcpServers': servers}))
    result, _, env = installer(tmp_path, source)
    assert result.returncode == 0, result.stderr
    binary = shutil.which('codex')
    if binary:
        parsed = subprocess.run([binary, 'mcp', 'list', '--json'], env=env, text=True, capture_output=True)
        assert parsed.returncode == 0, parsed.stderr
        assert {row['name'] for row in json.loads(parsed.stdout)} == set(servers)


def test_uninstall_preflights_removal_without_importing_source_servers(tmp_path):
    source = fixture_source(tmp_path)
    result, codex, env = installer(tmp_path, source)
    assert result.returncode == 0, result.stderr
    # The owner removed the managed block and now owns this server name.
    original = '# user-owned\n[mcp_servers."managed.dot"]\ncommand = "true"\n'
    (codex / 'config.toml').write_text(original)
    result = subprocess.run(['bash', str(ROOT / 'scripts/install-codex.sh'), 'uninstall', '--source', str(source)],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (codex / 'config.toml').read_text() == original
    assert not (tmp_path / 'home/.agents/skills/clavain').exists()


def test_uninstall_removes_session_refresh_and_preserves_other_hooks(tmp_path):
    source = fixture_source(tmp_path)
    result, codex, env = installer(tmp_path, source)
    assert result.returncode == 0, result.stderr
    hooks_file = codex / 'hooks.json'
    hooks = json.loads(hooks_file.read_text())
    hooks['hooks']['SessionStart'].append({'hooks': [{'type': 'command', 'command': 'echo user-owned'}]})
    hooks_file.write_text(json.dumps(hooks))
    result = subprocess.run(['bash', str(ROOT / 'scripts/install-codex.sh'), 'uninstall', '--source', str(source)],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    hooks = json.loads(hooks_file.read_text())
    commands = [h['command'] for group in hooks['hooks']['SessionStart'] for h in group['hooks']]
    assert commands == ['echo user-owned']


def test_doctor_reports_missing_refresh_hook(tmp_path):
    source = fixture_source(tmp_path)
    result, codex, env = installer(tmp_path, source)
    assert result.returncode == 0, result.stderr
    hooks_file = codex / 'hooks.json'
    hooks = json.loads(hooks_file.read_text())
    for group in hooks['hooks']['SessionStart']:
        group['hooks'] = [h for h in group['hooks'] if 'codex-session-refresh.sh' not in h['command']]
    hooks_file.write_text(json.dumps(hooks))
    result = subprocess.run(['bash', str(ROOT / 'scripts/install-codex.sh'), 'doctor', '--source', str(source), '--json'],
                            env=env, text=True, capture_output=True)
    report = json.loads(result.stdout)
    assert report['checks']['session_refresh_hook_match'] is False
    assert any('session refresh' in issue.lower() for issue in report['issues'])


def test_installer_preflights_config_before_changing_links(tmp_path):
    source = fixture_source(tmp_path)
    codex = tmp_path / "home/.codex"
    codex.mkdir(parents=True)
    (codex / "config.toml").write_text(START + "broken = [\n")
    result, _, _ = installer(tmp_path, source)
    assert result.returncode != 0
    assert not (tmp_path / "home/.agents/skills/clavain").exists()
    assert not (tmp_path / "home/.local/bin/clavain-cli").exists()


def test_installer_preflights_hooks_before_any_consumer_update(tmp_path):
    source = fixture_source(tmp_path)
    codex = tmp_path / 'home/.codex'
    codex.mkdir(parents=True)
    (codex / 'hooks.json').write_text('{"hooks": {"SessionStart": "malformed"}}')
    result, _, _ = installer(tmp_path, source)
    assert result.returncode != 0
    assert not (codex / 'config.toml').exists()
    assert not (codex / 'AGENTS.md').exists()
    assert not (tmp_path / 'home/.agents/skills/clavain').exists()


def test_manifest_plugin_root_resolves_to_selected_producer(tmp_path):
    source = fixture_source(tmp_path)
    (source / '.claude-plugin/plugin.json').write_text(json.dumps({'mcpServers': {
        'local': {'command': 'node', 'args': ['${CLAUDE_PLUGIN_ROOT}/server.js'],
                  'env': {'ROOT': '${CLAUDE_PLUGIN_ROOT}'}}}}))
    result, codex, _ = installer(tmp_path, source)
    assert result.returncode == 0, result.stderr
    import tomllib
    server = tomllib.loads((codex / 'config.toml').read_text())['mcp_servers']['local']
    assert server['args'] == [str(source.resolve() / 'server.js')]
    assert server['env']['ROOT'] == str(source.resolve())


@pytest.mark.parametrize("server", [
    {"command": "true", "url": "https://example.invalid/mcp"},
    {"command": "true", "args": [1]},
    {"command": 5},
    {"command": "true", "env": {"TOKEN": 2}},
    {"command": "true", "args": "ignored-before"},
    {"url": "https://example.invalid/mcp", "headers": {"TOKEN": 2}},
])
def test_installer_rejects_manifest_without_coercion(tmp_path, server):
    source = fixture_source(tmp_path)
    (source / '.claude-plugin/plugin.json').write_text(json.dumps({"mcpServers": {"managed": server}}))
    result, codex, _ = installer(tmp_path, source)
    assert result.returncode != 0
    assert not (codex / 'config.toml').exists()
    assert not (tmp_path / 'home/.agents/skills/clavain').exists()
