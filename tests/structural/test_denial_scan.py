"""Read-only structured denial event scanning."""
import json
import subprocess

import pytest


@pytest.fixture
def scan(project_root, tmp_path):
    def run(events=None, raw=None):
        path = tmp_path / 'events.jsonl'
        if events is not None:
            path.write_text(''.join(json.dumps(e) + '\n' for e in events))
        elif raw is not None:
            path.write_text(raw)
        return subprocess.run(['python3', str(project_root / 'scripts/denial-scan.py'), str(path)],
                              capture_output=True, text=True, timeout=10)
    return run


def event(kind, seq, text='', thread='a'):
    return dict(type=kind, seq=seq, text=text, thread=thread)


@pytest.mark.parametrize('phrase', ['ALLOW RULE', 'Permission rule', 'settings', 'Auto mode'])
def test_denied_turns_flagged_even_out_of_order(scan, phrase):
    result = scan([event('turn', 7, phrase), event('denial', 2)])
    assert result.returncode == 1
    assert 'a' in result.stdout and '7' in result.stdout


def test_thread_and_sequence_boundaries(scan):
    result = scan([event('turn', 1, 'settings'), event('denial', 2),
                   event('turn', 2, 'allow rule'), event('turn', 3, 'stopped'),
                   event('turn', 4, 'settings', 'b')])
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('raw', ['no json\n', '{}\n', '[]\n', '\n',
    '{"type":"other","thread":"a","seq":1,"text":""}\n',
    '{"type":"turn","thread":"a","seq":true,"text":""}\n',
    '{"type":"turn","thread":"a","seq":1,"text":null}\n'])
def test_malformed(scan, raw):
    assert scan(raw=raw).returncode == 2


def test_missing(scan):
    assert scan().returncode == 2


def test_empty_clean(scan):
    assert scan(events=[]).returncode == 0


def test_help_documents_schema_and_missing_producer(project_root):
    result = subprocess.run(['python3', str(project_root / 'scripts/denial-scan.py'), '--help'],
                            capture_output=True, text=True)
    assert result.returncode == 0
    for word in ('structured events', 'none exist yet', 'thread', 'seq', 'text', 'token-free'):
        assert word in result.stdout
