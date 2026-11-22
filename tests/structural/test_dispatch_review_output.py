"""Cross-lab reviews retain output before routing or launching a paid seat."""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def dispatch(tmp_path):
    bins = tmp_path / 'bin'
    bins.mkdir()
    calls = tmp_path / 'calls'
    failure = tmp_path / 'failure'
    for name in ('ic', 'codex', 'bb'):
        shim = bins / name
        shim.write_text(f'#!/bin/sh\necho "{name} $*" >> "{calls}"\nexit 97\n')
        shim.chmod(0o755)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('CLAVAIN_', 'BB_'))}
    env.update(PATH=f"{bins}:{env['PATH']}",
               CLAVAIN_DISPATCH_FAILURE_FILE=str(failure))

    def run(args):
        result = subprocess.run(
            ['bash', str(ROOT / 'scripts/dispatch.sh'), *args],
            env=env, capture_output=True, text=True, timeout=30, cwd=tmp_path)
        return result, calls, failure

    return run


@pytest.mark.parametrize('role_args', [
    ['--role', 'cross-lab-review'], ['--role=cross-lab-review'],
])
@pytest.mark.parametrize('mode', [[], ['--role-resolved'], ['--dry-run'],
                                 ['--hold-prompt', 'held.md', '--context-gateway', 'off']])
def test_missing_output_refused_before_any_backend(dispatch, role_args, mode):
    result, calls, failure = dispatch([
        *role_args, *mode, '--producer-identity', 'claude/claude-sonnet-5-5',
        'Review this change'])
    assert result.returncode != 0
    assert 'cross-lab-review requires -o/--output-last-message <file>' in result.stderr
    assert failure.read_text().strip() == 'terminal_configuration'
    assert not calls.exists(), calls.read_text() if calls.exists() else ''


@pytest.mark.parametrize('output_args', [[], ['-o', 'review.md']])
def test_partial_receipt_flags_still_name_missing_flags(dispatch, output_args):
    result, calls, _ = dispatch([
        '--role', 'cross-lab-review', '--producer-identity', 'x',
        '--repo', 'o/r', *output_args, '--prompt', 'hi'])
    assert result.returncode != 0
    assert '--repo-id' in result.stderr
    assert 'requires -o/' not in result.stderr
    assert not calls.exists()


@pytest.mark.parametrize('output_flag', ['-o', '--output-last-message'])
def test_supported_output_flags_reach_route_resolution(dispatch, output_flag):
    result, calls, _ = dispatch([
        '--role', 'cross-lab-review', '--producer-identity', 'claude/claude-sonnet-5-5',
        output_flag, 'review.md', 'Review this change'])
    assert result.returncode != 0  # deliberate route shim failure
    assert 'route dispatch --role=cross-lab-review' in calls.read_text()
    assert 'requires -o/' not in result.stderr
