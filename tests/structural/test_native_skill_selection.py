"""Portable Claude instructions must select policy from the loaded plugin."""
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('selected_contract', ROOT/'scripts/sync-agent-instructions.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


INVALID_POLICY = '/dev/null/clavain-invalid-routing-overlay'


@pytest.fixture(autouse=True)
def no_ambient_overlay(monkeypatch):
    monkeypatch.setenv('CLAVAIN_ROUTING_OVERLAY', '')


def policy_argument(body, env):
    argument = re.search(r'--policy=(.*?) --role=', body).group(1)
    return subprocess.run(['bash', '-c', 'printf "%s" '+argument],
                          env=env, capture_output=True, text=True)


def install(target):
    (target/'config').mkdir(parents=True, exist_ok=True)
    (target/'scripts').mkdir(exist_ok=True)
    shutil.copy(ROOT/'config/routing.yaml', target/'config/routing.yaml')
    shutil.copy(ROOT/'scripts/routing_overlay.py', target/'scripts/routing_overlay.py')
    return target.resolve()


def test_portable_claude_uses_native_selected_root_and_fails_without_it(tmp_path):
    body, meta = contract.render(ROOT, 'claude', portable_policy=True)
    env = {k: v for k, v in os.environ.items()
           if k not in ('CLAVAIN_ROUTING_POLICY', 'CLAVAIN_SELECTED_ROOT')}
    env['CLAVAIN_ROUTING_OVERLAY'] = ''
    missing = policy_argument(body, env)
    assert missing.stdout == INVALID_POLICY
    assert 'CLAVAIN_SELECTED_ROOT' in missing.stderr
    for name in ('selected one', 'selected-two'):
        selected = install(tmp_path/name)
        result = policy_argument(body, dict(env, CLAVAIN_SELECTED_ROOT=str(selected)))
        assert result.returncode == 0
        assert result.stdout == str(selected/'config/routing.yaml')
    override = policy_argument(body, dict(env, CLAVAIN_ROUTING_POLICY='/override/policy.yaml'))
    assert override.returncode == 0 and override.stdout == '/override/policy.yaml'
    assert '$HOME/.agents' not in body
    assert body.index('first invoke native Skill') < body.index('For substantive work, read')
    assert meta['policy_selection'] == 'portable-managed-installation'


def test_relocated_sources_keep_portable_hash_and_explicit_policy(tmp_path):
    original, meta = contract.render(ROOT, 'claude', portable_policy=True)
    for name in ('one', 'two with spaces'):
        source = tmp_path/name
        shutil.copytree(ROOT/'config', source/'config')
        shutil.copytree(ROOT/'.claude-plugin', source/'.claude-plugin')
        portable, relocated = contract.render(source, 'claude', portable_policy=True)
        assert portable == original
        assert relocated['contract_hash'] == meta['contract_hash']
        explicit, _ = contract.render(source, 'claude')
        result = policy_argument(explicit, os.environ.copy())
        assert result.returncode == 0 and result.stdout == str(source/'config/routing.yaml')
        with pytest.raises(ValueError, match='policy changed'):
            contract.render(source, 'claude', expected_policy_hash='0'*64)
    codex, codex_meta = contract.render(ROOT, 'codex', portable_policy=True)
    assert '$HOME/.agents/skills/clavain/../scripts/routing_overlay.py" policy' in codex
    assert codex_meta['policy_hash'] == meta['policy_hash']


def portable_env(tmp_path, **extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ('CLAVAIN_ROUTING_POLICY', 'CLAVAIN_SELECTED_ROOT', 'CLAVAIN_ROUTING_OVERLAY')}
    env['CLAVAIN_ROUTING_CACHE_DIR'] = str(tmp_path/'cache')
    env['CLAVAIN_SELECTED_ROOT'] = str(install(tmp_path/'installed'))
    env.update(extra)
    return env


def test_portable_policy_resolves_the_overlaid_policy(tmp_path):
    body, _ = contract.render(ROOT, 'claude', portable_policy=True)
    overlay = tmp_path/'overlay.yaml'
    overlay.write_text('reasoning:\n  profiles:\n    alex-devbox:\n      scope: alex-devbox\n')
    result = policy_argument(body, portable_env(tmp_path, CLAVAIN_ROUTING_OVERLAY=str(overlay)))
    assert result.returncode == 0
    resolved = Path(result.stdout)
    assert resolved.parent == tmp_path/'cache'
    assert 'alex-devbox' in resolved.read_text()


def test_portable_policy_with_invalid_overlay_never_falls_back_to_neutral(tmp_path):
    body, _ = contract.render(ROOT, 'claude', portable_policy=True)
    neutral = str(tmp_path/'installed'/'config'/'routing.yaml')
    for content in ('reasoning: [', 'reasoning:\n  bogus_key: 1\n', '', 'null\n'):
        overlay = tmp_path/'bad.yaml'
        overlay.write_text(content)
        result = policy_argument(body, portable_env(tmp_path, CLAVAIN_ROUTING_OVERLAY=str(overlay)))
        assert result.stdout != neutral, content
        assert result.stdout == INVALID_POLICY, content
        assert 'routing overlay:' in result.stderr
    missing = policy_argument(body, portable_env(tmp_path, CLAVAIN_ROUTING_OVERLAY=str(tmp_path/'absent.yaml')))
    assert missing.stdout == INVALID_POLICY
