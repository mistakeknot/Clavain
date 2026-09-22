import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_session_identity_fallback(tmp_path):
    cli=tmp_path/'bb'
    cli.write_text('#!/bin/sh\necho \'{"thread":{"id":"thr_fixture","environment":{"hostId":"host_pda34naxgq"}}}\'\n')
    cli.chmod(0o755)
    env=dict(os.environ, BB_CLI=str(cli), BB_THREAD_ID='thr_fixture', BB_SERVER_URL='https://bb.example', CLAUDE_SESSION_ID='')
    p=subprocess.run(['bash','-c', 'source "$1/scripts/lib-bb.sh"; _clavain_session_id', 'test', str(ROOT)],env=env,text=True,capture_output=True)
    assert p.stdout.strip() == 'thr_fixture'


def test_compaction_preserves_protected_sections():
    spec=importlib.util.spec_from_file_location('startup',ROOT/'scripts/startup.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sections=[('contract','CONTRACT'),('ownership-error','OWNER UNKNOWN'),('runtime-blocker','BLOCKER'),('diagnostics','long boilerplate')]
    result=module.bb_sections(sections)
    assert result[:3] == sections[:3]
    assert len(result) == 3


def test_notice_dedup_key_includes_thread_stage_evidence(tmp_path):
    env = dict(os.environ, CLAVAIN_BB_STATE_DIR=str(tmp_path), BB_THREAD_ID='thr_one')
    def check(stage='failed', evidence='receipt-one', thread='thr_one'):
        payload=json.dumps({'cycle':{'id':'cycle-one','stage':stage,'signed_receipt_id':evidence}})
        return subprocess.run(['python3',str(ROOT/'scripts/bb-notice.py')],input=payload,
                              text=True,env=env | {'BB_THREAD_ID':thread}).returncode
    assert check() == 0
    assert check() == 1
    assert check(stage='approved') == 0
    assert check(evidence='receipt-two') == 0
    assert check(thread='thr_two') == 0
