"""Real subprocess failures against the shipped observer configuration."""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('track', ['route', 'review_exit', 'learned_router'])
def test_cli_exit_one_never_records_success(tmp_path, monkeypatch, track):
    from clavain_selector import route_shadow, learned_router_shadow
    import review_exit_shadow
    monkeypatch.delenv('CLAVAIN_SELECTOR', raising=False)
    marker = tmp_path / 'called'
    stub = tmp_path / 'clavain-cli'
    stub.write_text('#!/bin/sh\nprintf called > "$FAILURE_MARKER"\nexit 1\n')
    stub.chmod(0o700)
    monkeypatch.setenv('PATH', str(tmp_path))
    monkeypatch.setenv('FAILURE_MARKER', str(marker))
    if track == 'route':
        route_shadow.observe(site='route-4b', native_choice='work',
            subject_sha256=hashlib.sha256(b'synthetic').hexdigest(),
            input_bytes=1, output_bytes=1, plugin_root=tmp_path,
            config=ROOT / 'config/routing.yaml', project_root=tmp_path)
    elif track == 'review_exit':
        # observe loads root/config; the root need not contain a bundled CLI.
        (tmp_path / 'config').mkdir()
        (tmp_path / 'config/routing.yaml').write_bytes((ROOT / 'config/routing.yaml').read_bytes())
        with pytest.raises(subprocess.CalledProcessError):
            review_exit_shadow.observe(tmp_path, tmp_path, 'synthetic', 'continue', 1, 1)
    else:
        with pytest.raises(subprocess.CalledProcessError):
            learned_router_shadow.observe(ROOT, ROOT / 'config/routing.yaml', tmp_path,
                dict(route=dict(profile_ref='native', profile=dict(backend='claude', model='synthetic')),
                     native='native', role='scout', prompt_chars=1, exit_code=0))
    assert marker.read_text() == 'called'
    assert not list((tmp_path / '.clavain/decisions').glob('*.jsonl'))
