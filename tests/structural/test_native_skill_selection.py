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


def policy_argument(body, env):
    argument = re.search(r'--policy=(.*?) --role=', body).group(1)
    return subprocess.run(['bash', '-c', 'printf "%s" '+argument],
                          env=env, capture_output=True, text=True)


def test_portable_claude_uses_native_selected_root_and_fails_without_it(tmp_path):
    body, meta = contract.render(ROOT, 'claude', portable_policy=True)
    env = {k: v for k, v in os.environ.items()
           if k not in ('CLAVAIN_ROUTING_POLICY', 'CLAVAIN_SELECTED_ROOT')}
    missing = policy_argument(body, env)
    assert missing.returncode != 0
    assert not missing.stdout
    for name in ('selected one', 'selected-two'):
        selected = tmp_path/name
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
    assert '$HOME/.agents/skills/clavain/../config/routing.yaml' in codex
    assert codex_meta['policy_hash'] == meta['policy_hash']
