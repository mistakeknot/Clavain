import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import compaction
import delivery


def test_compaction_requires_native_completion_on_exact_session():
    assert not compaction.codex_completed({'id':3,'result':{}},'session')
    event={'method':'item/completed','params':{'threadId':'session','item':{'type':'contextCompaction'}}}
    assert compaction.codex_completed(event,'session')
    assert not compaction.codex_completed(event,'other')
    assert not compaction.codex_completed(dict(event,method='item/started'),'session')
    boundary={'type':'system','subtype':'compact_boundary','session_id':'session'}
    success={'type':'result','subtype':'success','session_id':'session'}
    assert not compaction.claude_completed([success],'session')
    assert not compaction.claude_completed([boundary],'session')
    assert compaction.claude_completed([boundary,success],'session')
    assert not compaction.claude_completed([boundary,success],'other')


def test_prospective_enrollment_uses_real_intercore_without_acceptance(tmp_path):
    ic=shutil.which('ic')
    assert ic, 'Intercore CLI prerequisite required'
    db=tmp_path/'test-only.db'
    subprocess.run([ic,'--db='+str(db),'init'],cwd=tmp_path,capture_output=True,check=True)
    script=Path(__file__).resolve().parents[1]/'task-delivery.py'
    delivery.write(tmp_path/'delivery-config.json',dict(script=str(script),script_sha256=delivery.digest(script),db=str(db),parent_session_id='test-fixture-parent'))
    delivery.write(tmp_path/'manifest.json',dict(cohort_id='test-only',cohort_kind='correctness',subject_limit=12,
        order=[dict(host='codex',scenario='small-edit',condition='candidate')]*12,model_effort={'codex':['gpt-6-astra','high']}))
    folder=tmp_path/'case';folder.mkdir();profile=tmp_path/'profile';profile.mkdir();sources=tmp_path/'sources';sources.mkdir()
    (profile/'config.toml').write_text('fixture')
    enrollment=delivery.before_launch(tmp_path,0,folder,profile,sources,[sys.executable])
    assert enrollment['prelaunch']['executable_sha256']==delivery.digest(Path(sys.executable).resolve())
    records=json.loads(subprocess.check_output([ic,'--db='+str(db),'--json','route','list'],cwd=tmp_path))
    assert {r['rule_matched'] for r in records} == {'measured-delivery-enrollment','measured-delivery-execution'}
    # Enrollment precedes a native model launch. No model launches in this fixture.
    assert enrollment['implementation_dispatched'] is False
    assert not any(r['rule_matched']=='measured-delivery-acceptance' for r in records)


def test_runner_rejects_skipping_unaccepted_subject(tmp_path):
    spec=importlib.util.spec_from_file_location('correctness_runner',Path(__file__).with_name('runner.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    delivery.write(tmp_path/'manifest.json',dict(cohort_kind='correctness',subject_limit=12,order=[{}]*12,
        harness_sha256={'runner.py':delivery.digest(Path(module.__file__))}))
    with pytest.raises(ValueError,match='previous subject'): module.case_run(tmp_path,1)


def test_transport_preserves_bytes_and_rejects_paths(tmp_path):
    import base64,hashlib,transport
    row=dict(relative='native/session.jsonl',original='/remote/native/session.jsonl',
             sha256=hashlib.sha256(b'evidence').hexdigest(),bytes=base64.b64encode(b'evidence').decode())
    mapping=transport.unpack(json.dumps([row]).encode(),tmp_path)
    assert Path(mapping[row['original']]).read_bytes()==b'evidence'
    for changes in ({'relative':'../escape'},{'relative':'/escape'},{'sha256':'0'*64}):
        with pytest.raises(ValueError):transport.unpack(json.dumps([dict(row,**changes)]).encode(),tmp_path)


def test_remote_execution_cannot_start_if_enrollment_fails(tmp_path, monkeypatch):
    import transport
    (tmp_path/'results').mkdir()
    order=[dict(host='claude',scenario='small-edit',condition='candidate')]*12
    delivery.write(tmp_path/'manifest.json',dict(cohort_kind='correctness',order=order,
        harness_sha256={name:delivery.digest(Path(transport.__file__).with_name(name)) for name in ('transport.py','delivery.py')}))
    calls=[]
    def remote(code,*args,**kwargs):
        calls.append(args)
        return b'[]' if code==transport.COLLECT else b'{}'
    def refuse(*args,**kwargs):raise ValueError('authoritative enrollment refused')
    monkeypatch.setattr(transport,'remote',remote)
    monkeypatch.setattr(delivery,'before_launch',refuse)
    with pytest.raises(ValueError,match='authoritative enrollment refused'):
        transport.case(tmp_path,Path('/remote/cohort'),0)
    assert any(args[-1:] == ('prepare',) for args in calls)
    assert not any(args[-1:] == ('execute',) for args in calls)


def test_compaction_rpc_uses_native_sandbox_enum_and_waits_for_completion(tmp_path):
    import os,sys
    binary=tmp_path/'app-server-fixture'
    binary.write_text('#!'+sys.executable+'\n'+'''import json,sys
for line in sys.stdin:
 r=json.loads(line);method=r.get('method')
 if method=='initialize':reply={'id':r['id'],'result':{}}
 elif method=='thread/resume':
  if r['params'].get('sandbox')!='workspace-write':
   reply={'id':r['id'],'error':{'message':'invalid SandboxMode'}}
  else:reply={'id':r['id'],'result':{'thread':{'id':r['params']['threadId']}}}
 elif method=='thread/compact/start':
  reply={'method':'item/completed','params':{'threadId':r['params']['threadId'],'item':{'id':'compact-1','type':'contextCompaction'}}}
 else:continue
 print(json.dumps(reply),flush=True)
''')
    binary.chmod(0o700)
    result=compaction.codex(str(binary),'native-fixture',tmp_path,tmp_path,os.environ.copy())
    assert result['compaction_completed'],result


def test_remote_claude_binding_uses_copied_native_session_not_print_stream(tmp_path, monkeypatch):
    native=tmp_path/'native.jsonl';native.write_text('native fixture\n')
    delivery.write(tmp_path/'enrollment.json',dict(cohort_id='fixture',enrollment_id='fixture-0',manifest_sha256='a'*64,
        attempt_id='attempt',prelaunch=dict(executable='/remote/claude',executable_sha256='b'*64),prelaunch_sha256='c'*64))
    result=dict(case=dict(host='claude',scenario='resume'),native_session_id='native-session',observed_models=['claude-fable-5-1'],
        native_rollouts=[dict(path='/remote/session.jsonl')],transport=dict(evidence_paths={'/remote/session.jsonl':str(native)}),
        stages=[dict(exit_code=0)],fixture_check=dict(passed=True),compaction_completed=True)
    records=[]
    def record(base,kind,value):records.append((kind,value));return dict(id=len(records))
    monkeypatch.setattr(delivery,'record',record)
    delivery.after_run(tmp_path,tmp_path,result)
    binding=records[0][1]
    assert binding['evidence_path']==str(native)
    assert binding['evidence_sha256']==delivery.digest(native)
    assert binding['session_id']=='native-session'


def test_transport_accepts_base_alias_but_rejects_links_inside_it(tmp_path):
    import base64,hashlib,transport
    real=tmp_path/'real';real.mkdir();alias=tmp_path/'alias';alias.symlink_to(real,target_is_directory=True)
    row=dict(relative='native/session',original='/remote/session',sha256=hashlib.sha256(b'ok').hexdigest(),bytes=base64.b64encode(b'ok').decode())
    transport.unpack(json.dumps([row]).encode(),alias)
    assert (real/'native/session').read_bytes()==b'ok'
    (real/'link').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError,match='linked evidence'):
        transport.unpack(json.dumps([dict(row,relative='link/session')]).encode(),alias)


def test_failed_execution_is_terminal_and_retains_error_evidence(tmp_path, monkeypatch):
    delivery.write(tmp_path/'enrollment.json',dict(cohort_id='test',enrollment_id='test-1',attempt_id='attempt'))
    (tmp_path/'transport-error.stderr').write_text('transport fixture failed')
    calls=[]
    def record(base,kind,value):calls.append((kind,value));return {'id':12}
    monkeypatch.setattr(delivery,'record',record)
    delivery.failed(tmp_path,tmp_path,RuntimeError('remote fixture error'))
    delivery.failed(tmp_path,tmp_path,RuntimeError('retry cannot rewrite terminal'))
    assert len(calls)==1
    assert calls[0][1]['execution_status']=='failed'
    assert str(tmp_path/'transport-error.stderr') in calls[0][1]['evidence_refs']
    assert json.loads((tmp_path/'terminal-decision.json').read_text())=={'id':12}


def test_prelaunch_comparison_does_not_overwrite_original(tmp_path):
    import sys
    profile=tmp_path/'profile';profile.mkdir();sources=tmp_path/'sources';sources.mkdir()
    config=profile/'config.toml';config.write_text('before')
    before=delivery.capture(tmp_path,profile,sources,[sys.executable])
    config.write_text('after')
    assert delivery.capture(tmp_path,profile,sources,[sys.executable],persist=False)!=before
    assert json.loads((tmp_path/'prelaunch.json').read_text())==before


def test_collector_preserves_planted_skill_link_as_observation(tmp_path):
    import transport,subprocess,sys
    root=tmp_path/'case';root.mkdir()
    for name in ('result.json','initial.stdout','initial.stderr'):(root/name).write_text('{}')
    skills=root/'fixture/.claude/skills';skills.mkdir(parents=True)
    target=tmp_path/'catalog/skill';target.mkdir(parents=True);(target/'SKILL.md').write_text('fixture')
    (skills/'standalone').symlink_to(target,target_is_directory=True)
    raw=subprocess.check_output([sys.executable,'-c',transport.COLLECT,str(root),'completed'])
    rows=json.loads(raw)
    assert 'skill-links/standalone.json' in {r['relative'] for r in rows}
    assert not any(r['relative'].endswith('SKILL.md') for r in rows)


def test_transport_rejects_unpinned_coordinator_before_remote_calls(tmp_path,monkeypatch):
    import transport
    delivery.write(tmp_path/'manifest.json',{'harness_sha256':{}})
    monkeypatch.setattr(transport,'remote',lambda *a,**k:pytest.fail('must not launch'))
    with pytest.raises(ValueError,match='coordinator differs'):
        transport.case(tmp_path,Path('/remote'),0)
