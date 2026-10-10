"""scripts/check-instruction-contract.sh: JSON drift report with exit codes."""
import json
import os
import subprocess

import pytest



@pytest.fixture
def run(project_root):
    script = project_root / 'scripts/check-instruction-contract.sh'

    def go(*args, root=None):
        env = dict(os.environ)
        env.pop('CLAVAIN_SELECTED_ROOT', None)
        if root is not False:
            env['CLAVAIN_SELECTED_ROOT'] = str(root or project_root)
        return subprocess.run([str(script), *args], capture_output=True, text=True,
                              env=env, timeout=30)
    return go


@pytest.fixture
def rendered(project_root, tmp_path):
    """A host file holding the freshly rendered managed block."""
    path = tmp_path / 'CLAUDE.md'
    sync = project_root / 'scripts/sync-agent-instructions.py'
    subprocess.run(['python3', '-I', str(sync), '--source', str(project_root), '--host', 'claude',
                    '--file', str(path), '--portable-policy'], check=True, capture_output=True,
                   timeout=30)
    return path


def test_current_file_exits_zero(run, rendered):
    result = run('--host', 'claude', '--file', str(rendered))
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report['current'] is True and report['drift'] == []
    assert report['file_policy_hash'] == report['policy_hash']


def test_policy_hash_drift_under_same_version(run, rendered):
    text = rendered.read_text()
    report = json.loads(run('--host', 'claude', '--file', str(rendered)).stdout)
    rendered.write_text(text.replace(report['policy_hash'], '0' * 64))
    result = run('--host', 'claude', '--file', str(rendered))
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report['current'] is False
    assert report['drift'] == ['policy-hash']
    assert report['file_version'] == report['installed_version']


def test_version_drift(run, rendered):
    report = json.loads(run('--host', 'claude', '--file', str(rendered)).stdout)
    rendered.write_text(rendered.read_text().replace(
        f"package: {report['version']};", 'package: 0.0.1;'))
    result = run('--host', 'claude', '--file', str(rendered))
    assert result.returncode == 1
    assert 'version' in json.loads(result.stdout)['drift']


def test_file_without_block_is_drifted(run, tmp_path):
    path = tmp_path / 'CLAUDE.md'
    path.write_text('# local only\n')
    result = run('--host', 'claude', '--file', str(path))
    assert result.returncode == 1
    assert 'no-receipt' in json.loads(result.stdout)['drift']


def test_missing_file_is_drifted(run, tmp_path):
    result = run('--host', 'claude', '--file', str(tmp_path / 'absent.md'))
    assert result.returncode == 1
    assert 'file-missing' in json.loads(result.stdout)['drift']


@pytest.mark.parametrize('args', [(), ('--host', 'claude'), ('--file', 'x'), ('--bogus',)])
def test_usage_errors_exit_two(run, args):
    assert run(*args).returncode == 2


def test_requires_selected_root(run, tmp_path):
    assert run('--host', 'claude', '--file', str(tmp_path / 'x'), root=False).returncode == 2
    assert run('--host', 'claude', '--file', str(tmp_path / 'x'), root=tmp_path).returncode == 2


def test_unknown_host_reports_error_json(run, rendered):
    result = run('--host', 'nonesuch', '--file', str(rendered))
    assert result.returncode == 2
    assert json.loads(result.stdout)['drift'] == ['renderer-error']
