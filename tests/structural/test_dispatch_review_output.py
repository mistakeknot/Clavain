"""PR reviews must retain output before routing or launching a paid seat."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_crosslab_missing_output_refused_before_any_backend(tmp_path):
    bins = tmp_path / 'bin'
    bins.mkdir()
    calls = tmp_path / 'calls'
    for name in ('ic', 'codex', 'bb'):
        shim = bins / name
        shim.write_text(f'#!/bin/sh\necho {name} >> "{calls}"\nexit 97\n')
        shim.chmod(0o755)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('CLAVAIN_', 'BB_'))}
    env['PATH'] = f"{bins}:{env['PATH']}"
    result = subprocess.run(
        ['bash', str(ROOT / 'scripts/dispatch.sh'), '--role', 'cross-lab-review',
         '--producer-identity', 'claude/claude-sonnet-5-5', 'Review this change'],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'cross-lab-review requires -o/--output' in result.stderr
    assert not calls.exists(), calls.read_text() if calls.exists() else ''


def test_crosslab_with_output_reaches_route_resolution(tmp_path):
    bins = tmp_path / 'bin'
    bins.mkdir()
    calls = tmp_path / 'calls'
    shim = bins / 'ic'
    shim.write_text(f'#!/bin/sh\necho "$*" >> "{calls}"\nexit 97\n')
    shim.chmod(0o755)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('CLAVAIN_', 'BB_'))}
    env['PATH'] = f"{bins}:{env['PATH']}"
    result = subprocess.run(
        ['bash', str(ROOT / 'scripts/dispatch.sh'), '--role', 'cross-lab-review',
         '--producer-identity', 'claude/claude-sonnet-5-5',
         '-o', str(tmp_path / 'review.md'), 'Review this change'],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0  # deliberate route shim failure
    assert 'route dispatch --role=cross-lab-review' in calls.read_text()
    assert 'requires -o/--output' not in result.stderr
