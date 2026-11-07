"""Deterministic suppression ratchet (source: bead mk-3czro)."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'skills/gardener/scripts/suppressions.py'


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def repo(tmp_path, text=''):
    git(tmp_path, 'init', '-q')
    (tmp_path / 'sample.py').write_text(text)
    git(tmp_path, 'add', '.')
    git(tmp_path, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'initial source')
    git(tmp_path, 'branch', 'trusted')
    git(tmp_path, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'topic work')
    return tmp_path


def run(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), '--root', str(root), '--base-ref', 'trusted', *args], capture_output=True, text=True)


def commit(root):
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
    git(root, 'update-ref', 'refs/heads/trusted', 'HEAD')
    git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'topic work')


@pytest.mark.parametrize('text,suffix,kind,valid', [
    ('x = 1 # noqa: F841 # public API', '.py', 'noqa', True),
    ('x = 1 # noqa: F841', '.py', 'noqa', False),
    ('x = 1 # noqa # public API', '.py', 'noqa', False),
    ('x = 1 # type: ignore[arg-type] # generated API', '.py', 'type: ignore', True),
    ('x = 1 # type: ignore # generated API', '.py', 'type: ignore', False),
    ('//nolint:errcheck // best effort close', '.go', 'nolint', True),
    ('//nolint:errcheck', '.go', 'nolint', False),
    ('//nolint:errcheck,all // legacy', '.go', 'nolint', False),
    ('// eslint-disable-next-line no-alert -- browser API', '.tsx', 'eslint-disable', True),
    ('/* eslint-disable no-alert */', '.js', 'eslint-disable', False),
    ('// eslint-disable -- browser API', '.js', 'eslint-disable', False),
    ('// @ts-expect-error TS2322: legacy boundary', '.ts', 'ts-ignore/ts-expect-error', True),
    ('// @ts-ignore', '.mts', 'ts-ignore/ts-expect-error', False),
    ('// @ts-ignore', '.cts', 'ts-ignore/ts-expect-error', False),
    ('# pylint: disable=unused-import # public re-export', '.py', 'pylint: disable', True),
    ('# pylint: disable=all; reason', '.py', 'pylint: disable', False),
    ('# pylint: disable=all#reason', '.py', 'pylint: disable', False),
    ('# pylint: disable=W # legacy', '.py', 'pylint: disable', False),
    ('# pylint: disable=', '.py', 'pylint: disable', False),
    ('# pylint: disable', '.py', 'pylint: disable', False),
    ('// @ts-nocheck TS2322: legacy', '.ts', 'ts-nocheck', False),
])
def test_marker_counts_and_reasons(tmp_path, text, suffix, kind, valid):
    root = repo(tmp_path)
    (root / ('source' + suffix)).write_text(text + '\n')
    git(root, 'add', '.')
    result = run(root, '--json')
    assert result.returncode == (0 if valid else 1), result.stdout
    data = json.loads(result.stdout)
    assert data['scan']['counts'][kind] == 1
    assert sum(data['scan']['counts'].values()) == 1


def test_count_rise_and_update_refused(tmp_path):
    root = repo(tmp_path, 'x = 1 # noqa: F841 # public API\n')
    assert run(root, '--adopt').returncode == 0
    commit(root)
    assert run(root).returncode == 0
    (root / 'sample.py').write_text('x = 1 # noqa: F841 # public API\ny = 2 # noqa: F841 # public API\n')
    assert run(root).returncode == 1
    before = (root / '.suppression-baseline.json').read_bytes()
    assert run(root, '--update').returncode == 1
    assert (root / '.suppression-baseline.json').read_bytes() == before


def test_baseline_shrinks(tmp_path):
    root = repo(tmp_path, 'x = 1 # noqa\n')
    assert run(root, '--adopt').returncode == 0
    commit(root)
    (root / 'sample.py').write_text('x = 1\n')
    assert run(root).returncode == 1
    assert run(root, '--update').returncode == 0
    assert json.loads((root / '.suppression-baseline.json').read_text())['counts']['noqa'] == 0
    assert run(root).returncode == 0


def test_new_malformed_comment_refused_at_same_total(tmp_path):
    root = repo(tmp_path, 'x = 1 # noqa: F841 # public API\n')
    assert run(root, '--adopt').returncode == 0
    commit(root)
    (root / 'sample.py').write_text('x = 1 # noqa: F841\n')
    assert run(root).returncode == 1


def test_committed_baseline_increase_rejected(tmp_path):
    root = repo(tmp_path, 'x = 1\n')
    assert run(root, '--adopt').returncode == 0
    commit(root)
    git(root, 'branch', 'target', 'trusted')
    (root / 'sample.py').write_text('x = 1 # noqa: F841 # public API\n')
    data = json.loads((root / '.suppression-baseline.json').read_text())
    data['counts']['noqa'] = 1
    (root / '.suppression-baseline.json').write_text(json.dumps(data))
    commit(root)
    result = run(root, '--base-ref', 'target')
    assert result.returncode == 1
    assert 'baseline increased' in result.stdout
    assert run(root, '--update', '--base-ref', 'target').returncode == 1


def test_check_and_update_require_ref(tmp_path):
    root = repo(tmp_path)
    for flags in ([], ['--update']):
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(root), *flags], capture_output=True, text=True)
        assert result.returncode == 2
        assert '--base-ref' in result.stderr


def test_missing_ref_fails_closed(tmp_path):
    root = repo(tmp_path)
    assert run(root, '--base-ref', 'absent').returncode == 2


def test_adoption_cannot_overwrite_baseline(tmp_path):
    root = repo(tmp_path)
    assert run(root, '--adopt').returncode == 0
    assert run(root, '--adopt').returncode == 1


def test_deleted_baseline_rejected(tmp_path):
    root = repo(tmp_path)
    assert run(root, '--adopt').returncode == 0
    commit(root)
    (root / '.suppression-baseline.json').unlink()
    assert run(root).returncode == 1


def test_nested_baseline_reads_nested_committed_file(tmp_path):
    root = repo(tmp_path, 'x = 1 # noqa\n')
    assert run(root, '--adopt').returncode == 0
    nested = root / 'sub'
    nested.mkdir()
    (nested / 'source.py').write_text('x = 1\n')
    git(root, 'add', '.')
    assert run(nested, '--adopt').returncode == 0
    commit(root)
    git(root, 'branch', 'target', 'trusted')
    assert run(nested, '--base-ref', 'target').returncode == 0
    (nested / 'source.py').write_text('x = 1 # noqa: F841 # public API\n')
    data = json.loads((nested / '.suppression-baseline.json').read_text())
    data['counts']['noqa'] = 1
    (nested / '.suppression-baseline.json').write_text(json.dumps(data))
    result = run(nested, '--base-ref', 'target')
    assert result.returncode == 1
    assert 'baseline increased' in result.stdout


def test_nested_baseline_without_root_baseline(tmp_path):
    root = repo(tmp_path)
    nested = root / 'sub'
    nested.mkdir()
    (nested / 'source.py').write_text('x = 1\n')
    git(root, 'add', '.')
    assert run(nested, '--adopt').returncode == 0
    commit(root)
    assert run(nested).returncode == 0


@pytest.mark.parametrize('directory', ['research', '.conductor', 'vendor', 'node_modules', 'src/research'])
def test_no_hidden_directory_exclusions(tmp_path, directory):
    root = repo(tmp_path)
    path = root / directory / 'source.py'
    path.parent.mkdir(parents=True)
    path.write_text('x = 1 # noqa\n')
    git(root, 'add', '.')
    assert run(root).returncode == 1


def test_scanner_is_deterministic_and_can_count_strings(tmp_path):
    root = repo(tmp_path, 's = "# noqa"\n')
    first = run(root, '--json')
    second = run(root, '--json')
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)['scan']['counts']['noqa'] == 1


def test_legacy_comment_move_does_not_change_count(tmp_path):
    root = repo(tmp_path, 'import os # noqa\n')
    assert run(root, '--adopt').returncode == 0
    commit(root)
    (root / 'sample.py').write_text('import os\neval("x") # noqa\n')
    assert run(root).returncode == 0


def test_another_directive_is_not_a_reason(tmp_path):
    root = repo(tmp_path, 'x = 1 # type: ignore[arg-type] # noqa\n')
    result = run(root, '--json')
    assert len(json.loads(result.stdout)['findings']) == 2


def test_python_encoding_cookie(tmp_path):
    root = repo(tmp_path)
    (root / 'sample.py').write_bytes(b'# coding: latin-1\nx = "caf\xe9" # noqa\n')
    assert run(root).returncode == 1


def test_unreadable_source_names_path(tmp_path):
    root = repo(tmp_path)
    (root / 'sample.py').write_bytes(b'# coding: ascii\nx = "\xff"\n')
    result = run(root)
    assert result.returncode == 2
    assert 'sample.py' in result.stdout


def test_invalid_baseline_counts_fail_closed(tmp_path):
    root = repo(tmp_path)
    assert run(root, '--adopt').returncode == 0
    data = json.loads((root / '.suppression-baseline.json').read_text())
    data['counts']['noqa'] = -1
    (root / '.suppression-baseline.json').write_text(json.dumps(data))
    assert run(root).returncode == 2


@pytest.mark.parametrize('mode', [[], ['--update']])
@pytest.mark.parametrize('ref_kind', ['HEAD', 'sha', 'branch'])
def test_comparison_ref_must_differ_from_topic_head(tmp_path, mode, ref_kind):
    root = repo(tmp_path)
    assert run(root, '--adopt').returncode == 0
    commit(root)
    if ref_kind == 'sha':
        ref = git(root, 'rev-parse', 'HEAD')
    elif ref_kind == 'branch':
        git(root, 'branch', 'topic-alias', 'HEAD')
        ref = 'topic-alias'
    else:
        ref = 'HEAD'
    result = run(root, '--base-ref', ref, *mode)
    assert result.returncode == 2, result.stdout
    assert 'same commit as HEAD' in result.stdout


def test_gitlink_with_source_extension_is_skipped(tmp_path):
    root = repo(tmp_path)
    module = root / 'dependency.ts'
    module.mkdir()
    sha = git(root, 'rev-parse', 'HEAD')
    git(root, 'update-index', '--add', '--cacheinfo', f'160000,{sha},dependency.ts')
    result = run(root, '--json')
    assert result.returncode == 0, result.stdout
    assert sum(json.loads(result.stdout)['scan']['counts'].values()) == 0
