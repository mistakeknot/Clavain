"""Startup is bounded evidence, never maintenance or acceptance authority."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import fcntl
import hashlib
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/startup.py'


def test_archive_ledger_preserves_bytes_and_hash(tmp_path):
    project = tmp_path/'project'; project.mkdir()
    state = tmp_path/'state'
    assert invoke(project, state, extra=('--telemetry',)).returncode == 0
    before = (state/'hook-health.jsonl').read_bytes()
    result = invoke(project, state, 'refresh', extra=('--archive-ledger',))
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)['ledger_archive']
    archived = state/receipt['path']
    assert archived.read_bytes() == before
    assert receipt['sha256'] == hashlib.sha256(before).hexdigest()
    assert receipt['size_bytes'] == len(before)
    assert not (state/'hook-health.jsonl').exists()
    assert invoke(project, state, extra=('--telemetry',)).returncode == 0
    assert archived.read_bytes() == before
    assert len((state/'hook-health.jsonl').read_text().splitlines()) == 1
    assert invoke(project, state, 'refresh', extra=('--archive-ledger',)).returncode == 0
    assert archived.read_bytes() == before


def test_archive_is_explicit_and_empty_state_is_safe(tmp_path):
    project = tmp_path/'project'; project.mkdir(); state = tmp_path/'state'
    assert invoke(project, state, extra=('--archive-ledger',)).returncode != 0
    result = invoke(project, state, 'refresh', extra=('--archive-ledger',))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['ledger_archive']['status'] == 'absent'


def test_archive_detects_unlocked_legacy_append(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from contextlib import contextmanager
    spec=importlib.util.spec_from_file_location('archive_startup',SCRIPT)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=tmp_path/'hook-health.jsonl';path.write_bytes(b'original\n');path.chmod(0o600)
    @contextmanager
    def lock(*args,**kwargs):yield tmp_path
    monkeypatch.setattr(module,'ledger_lock',lock)
    fsync=module.os.fsync
    def append(fd):
        with path.open('ab') as stream:stream.write(b'legacy writer\n')
        fsync(fd)
    monkeypatch.setattr(module.os,'fsync',append)
    with pytest.raises(ValueError,match='changed during archival'):
        module.archive_ledger(SimpleNamespace())
    assert path.read_bytes()==b'original\nlegacy writer\n'
    assert not list(tmp_path.glob('hook-health-archive-*'))


def test_lock_contention_does_not_block_startup(tmp_path):
    project = tmp_path/'project'; project.mkdir(); state = tmp_path/'state'; state.mkdir(mode=0o700)
    lock = state/'hook-health.lock'
    lock.touch(mode=0o600)
    with lock.open('rb') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        start = time.monotonic()
        result = invoke(project, state, extra=('--telemetry',))
        assert time.monotonic()-start < 2
    assert result.returncode == 0
    assert 'telemetry unavailable' in result.stdout
    assert len(result.stdout.encode()) <= 10000
    assert not (state/'hook-health.jsonl').exists()


@pytest.mark.parametrize('name', ['hook-health.lock', 'hook-health.jsonl'])
def test_archive_refuses_links(tmp_path, name):
    project = tmp_path/'project'; project.mkdir(); state = tmp_path/'state'; state.mkdir(mode=0o700)
    victim = tmp_path/'victim'; victim.write_text('untouched'); victim.chmod(0o600)
    (state/name).symlink_to(victim)
    result = invoke(project, state, 'refresh', extra=('--archive-ledger',))
    assert result.returncode != 0
    assert victim.read_text() == 'untouched'


def test_archival_preserves_concurrent_successful_appends(tmp_path):
    project = tmp_path/'project'; project.mkdir(); state = tmp_path/'state'
    processes = []
    for index in range(16):
        processes.append(subprocess.Popen([sys.executable, str(SCRIPT), 'render', '--project', str(project),
            '--state-dir', str(state), '--telemetry'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        processes[-1].stdin.write(json.dumps({'session_id':str(index)})); processes[-1].stdin.close(); processes[-1].stdin = None
        if index % 4 == 0:
            result = invoke(project, state, 'refresh', extra=('--archive-ledger',))
            assert result.returncode == 0, result.stdout + result.stderr
    successful = set()
    for index, process in enumerate(processes):
        out, err = process.communicate(timeout=10)
        assert process.returncode == 0, err
        if 'telemetry unavailable' not in out:
            successful.add(str(index))
    rows = []
    for path in [*state.glob('hook-health-archive-*.jsonl'), state/'hook-health.jsonl']:
        if path.exists(): rows.extend(json.loads(line) for line in path.read_text().splitlines())
    assert successful
    assert {row['session_id'] for row in rows} == successful
    assert len(rows) == len(successful)


def invoke(project, state, operation='render', payload=None, extra=()):
    return subprocess.run([sys.executable, str(SCRIPT), operation, '--project', str(project),
                           '--state-dir', str(state), '--source', str(ROOT), *extra],
                          input=json.dumps(payload or {}), text=True, capture_output=True)


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_cold_render_is_unknown_and_does_not_write(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    state = tmp_path / 'private'
    before = tree(project)
    r = invoke(project, state)
    assert r.returncode == 0, r.stderr
    context = json.loads(r.stdout)['hookSpecificOutput']['additionalContext']
    assert 'unknown' in context
    assert tree(project) == before
    assert not state.exists(), 'render cannot initialize snapshot state'


def test_preserves_inflight_and_dirty_work(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    scratch = project / '.clavain/scratch'; scratch.mkdir(parents=True)
    (scratch / 'inflight-agents.json').write_text(json.dumps({'agents':[{'id':'agent-1','task':'review architecture'}]}))
    (project / 'dirty.txt').write_text('unrelated work')
    before = tree(project)
    r = invoke(project, tmp_path / 'state', payload={'source':'compact'})
    assert r.returncode == 0, r.stderr
    assert 'review architecture' in r.stdout
    assert tree(project) == before
    assert 'MANDATORY' not in r.stdout


def test_serialized_budget_preserves_task_blocker_and_ownership(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    (project / '.beads').mkdir()
    (project / '.beads/issues.jsonl').write_text(json.dumps({'id':'task-1','status':'in_progress','assignee':'owner-1','title':'Fix startup','notes':'blocked by review ' + '🚀"\\\n'*20000})+'\n')
    r = invoke(project, tmp_path / 'state')
    assert r.returncode == 0, r.stderr
    assert len(r.stdout.encode()) <= 10000
    assert all(s in r.stdout for s in ['task-1','owner-1','blocked by review'])


def test_refresh_then_stale_is_not_healthy(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    state = tmp_path / 'state'
    r = invoke(project, state, 'refresh')
    assert r.returncode == 0, r.stderr
    r = invoke(project, state)
    assert 'fresh' in r.stdout
    snapshot = next(state.glob('snapshot-*.json'))
    data = json.loads(snapshot.read_text()); data['created_at'] = 0
    snapshot.write_text(json.dumps(data))
    r = invoke(project, state)
    assert 'stale' in r.stdout
    assert 'healthy' not in r.stdout


@pytest.mark.parametrize('content',['{bad','[]','null','{"schema_version":999}'])
def test_malformed_snapshot_is_unknown(tmp_path, content):
    project = tmp_path / 'project'; project.mkdir(); state = tmp_path / 'state'
    assert invoke(project, state, 'refresh').returncode == 0
    next(state.glob('snapshot-*.json')).write_text(content)
    r = invoke(project, state)
    assert r.returncode == 0
    assert 'unknown' in r.stdout


def test_project_identity_prevents_cross_scope_reuse(tmp_path):
    a = tmp_path / 'a'; a.mkdir(); b = tmp_path / 'b'; b.mkdir(); state = tmp_path / 'state'
    assert invoke(a, state, 'refresh').returncode == 0
    assert 'unknown' in invoke(b, state).stdout


def test_telemetry_failure_is_visible_and_output_valid(tmp_path):
    project = tmp_path / 'project'; project.mkdir(); state = tmp_path / 'state'
    state.write_text('not a directory')
    r = invoke(project, state, extra=('--telemetry',))
    assert r.returncode == 0
    assert 'telemetry unavailable' in r.stdout
    assert len(r.stdout.encode()) <= 10000


def test_telemetry_in_worktree_is_refused(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    r = invoke(project, project / '.private', extra=('--telemetry',))
    assert r.returncode == 0
    assert 'telemetry unavailable' in r.stdout
    assert not (project / '.private').exists()


@pytest.mark.parametrize('kind',['missing','cycle','version'])
def test_doctor_rejects_broken_selected_installation(tmp_path, kind):
    root = tmp_path / 'selected'
    if kind == 'cycle':
        root.symlink_to(tmp_path/'other'); (tmp_path/'other').symlink_to(root)
    elif kind == 'version':
        (root/'.claude-plugin').mkdir(parents=True)
        (root/'.claude-plugin/plugin.json').write_text('{"version":"wrong"}')
    manifest = tmp_path / 'installed.json'
    manifest.write_text(json.dumps({'plugins':{'clavain@interagency-marketplace':[{'installPath':str(root),'version':'0.6.314'}]}}))
    r = invoke(tmp_path, tmp_path/'state', 'doctor', extra=('--installed-manifest',str(manifest)))
    assert r.returncode != 0
    data = json.loads(r.stdout)
    assert data['installation']['status'] != 'ok'


def test_hook_does_not_execute_mutating_dependencies(tmp_path):
    project = tmp_path/'project'; project.mkdir(); fake = tmp_path/'bin'; fake.mkdir()
    for tool in ['bd','ic','curl','ockham','find']:
        p = fake/tool; p.write_text('#!/bin/sh\necho invoked >> "$PROBE_LOG"\nexit 1\n'); p.chmod(0o755)
    env = dict(os.environ, PATH=str(fake)+os.pathsep+os.environ['PATH'],
               PROBE_LOG=str(tmp_path/'calls'), HOME=str(tmp_path/'home'),
               CLAVAIN_STARTUP_STATE_DIR=str(tmp_path/'private'))
    r = subprocess.run(['bash',str(ROOT/'hooks/session-start.sh')], cwd=project, env=env,
                       input='{}',text=True,capture_output=True)
    assert r.returncode == 0
    assert not (tmp_path/'calls').exists()
    assert tree(project) == {}
    assert len(r.stdout.encode()) <= 10000


def test_instruction_contract_is_never_dropped(tmp_path):
    project=tmp_path/'project'; project.mkdir(); (project/'.beads').mkdir()
    rows=[{'id':f'task-{n}','status':'blocked','title':'🚀'*180,'notes':'x'*500} for n in range(20)]
    (project/'.beads/issues.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    r=invoke(project,tmp_path/'state',extra=('--instruction-file',str(tmp_path/'absent')))
    assert len(r.stdout.encode())<=10000
    context=json.loads(r.stdout)['hookSpecificOutput']['additionalContext']
    assert 'Sylveste operating contract' in context
    assert 'task-0' in context


def test_existing_contract_not_duplicated(tmp_path):
    instruction=tmp_path/'CLAUDE.md'
    r=subprocess.run([sys.executable,str(ROOT/'scripts/sync-agent-instructions.py'),'--source',str(ROOT),'--host','claude','--portable-policy','--render'],capture_output=True,text=True,check=True)
    instruction.write_text(r.stdout)
    out=invoke(tmp_path,tmp_path/'state',extra=('--instruction-file',str(instruction)))
    assert 'Sylveste operating contract' not in out.stdout
    assert 'current' in out.stdout


def test_configuration_change_invalidates_snapshot(tmp_path):
    project=tmp_path/'project'; project.mkdir(); state=tmp_path/'state'; instruction=tmp_path/'CLAUDE.md'
    instruction.write_text('baseline')
    extra=('--instruction-file',str(instruction))
    assert invoke(project,state,'refresh',extra=extra).returncode==0
    instruction.write_text('changed')
    assert 'stale' in invoke(project,state,extra=extra).stdout


def test_explicit_audit_refresh_retains_stale_findings(tmp_path):
    project=tmp_path/'project'; project.mkdir(); state=tmp_path/'state'
    audit=tmp_path/'audit.sh'
    audit.write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"findings":[{"bead_id":"blocked-1","message":"receipt missing","action":"collect fresh evidence"}]}\'\nexit 1\n')
    assert invoke(project,state,'refresh',extra=('--runtime-audit',str(audit))).returncode==0
    snap=next(state.glob('snapshot-*')); data=json.loads(snap.read_text());data['created_at']=0;snap.write_text(json.dumps(data))
    result=invoke(project,state)
    assert 'receipt missing' in result.stdout and 'stale' in result.stdout
    assert 'collect fresh evidence' in result.stdout


def test_owners_survive_many_large_tasks(tmp_path):
    project=tmp_path/'project';project.mkdir();(project/'.beads').mkdir()
    (project/'.beads/issues.jsonl').write_text('\n'.join(json.dumps({'id':f'task-{n}','status':'blocked','assignee':f'owner-{n}','notes':'🚀'*500}) for n in range(6)))
    scratch=project/'.clavain/scratch';scratch.mkdir(parents=True)
    (scratch/'inflight-agents.json').write_text(json.dumps({'agents':[{'id':f'agent-{n}','task':'x'*500} for n in range(6)]}))
    r=invoke(project,tmp_path/'state',extra=('--instruction-file',str(tmp_path/'absent')))
    assert len(r.stdout.encode())<=10000
    assert 'Sylveste operating contract' in r.stdout
    assert all(f'agent-{n}' in r.stdout and f'task-{n}' in r.stdout for n in range(6))


def test_missing_renderer_has_visible_fallback(tmp_path):
    hooks=tmp_path/'hooks';hooks.mkdir()
    hook=hooks/'session-start.sh';hook.write_bytes((ROOT/'hooks/session-start.sh').read_bytes())
    r=subprocess.run(['bash',str(hook)],input='{}',capture_output=True,text=True)
    assert r.returncode==0
    assert 'renderer unavailable' in json.loads(r.stdout)['hookSpecificOutput']['additionalContext']


def test_session_join_is_visible_without_environment_writes(tmp_path):
    r=invoke(tmp_path,tmp_path/'state',payload={'session_id':'native-123'})
    assert 'DISPATCH_SESSION_ID=native-123' in r.stdout


def test_renderer_finishes_before_first_turn():
    hooks=json.loads((ROOT/'hooks/hooks.json').read_text())['hooks']['SessionStart']
    start=next(h for group in hooks for h in group['hooks'] if h['command'].endswith('/session-start.sh'))
    assert not start.get('async',False), 'authority and task context must arrive before first turn'


def test_telemetry_failure_large_findings_never_lie_about_contract(tmp_path):
    project=tmp_path/'project';project.mkdir();state=tmp_path/'state'
    assert invoke(project,state,'refresh').returncode==0
    snap=next(state.glob('snapshot-*'));data=json.loads(snap.read_text())
    data['runtime_audit']={'result':{'findings':[{'bead_id':'blocked','message':'🚀'*240,'action':'🚀'*240} for _ in range(3)]}}
    snap.write_text(json.dumps(data));(state/'hook-health.jsonl').write_text('');(state/'hook-health.jsonl').chmod(0o644)
    r=invoke(project,state,extra=('--telemetry','--instruction-file',str(tmp_path/'absent')))
    assert 'telemetry unavailable' in r.stdout
    assert 'Sylveste operating contract' in r.stdout
    assert len(r.stdout.encode())<=10000


def test_symlinked_state_directory_is_refused(tmp_path):
    project=tmp_path/'project';project.mkdir();target=tmp_path/'target';target.mkdir(mode=0o700)
    link=tmp_path/'link';link.symlink_to(target,target_is_directory=True)
    r=invoke(project,link,extra=('--telemetry',))
    assert 'telemetry unavailable' in r.stdout
    assert list(target.iterdir())==[]


def test_missing_task_id_does_not_match_missing_current_bead(tmp_path):
    project=tmp_path/'project';project.mkdir();(project/'.beads').mkdir()
    (project/'.beads/issues.jsonl').write_text('{"status":"closed","title":"should not appear"}\n')
    assert 'should not appear' not in invoke(project,tmp_path/'state').stdout


def test_impossible_contract_budget_reports_actual_final_selection():
    spec=importlib.util.spec_from_file_location('startup_test',SCRIPT)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sections=[('boundaries','Preserve authority'),('status','placeholder'),('contract','🚀'*10000)]
    for extra in [[],[('telemetry','telemetry unavailable')]]:
        out,dropped,status=module.finish_context(extra+sections,'fresh','injected')
        assert 'Instruction contract: injected' not in out
        assert 'NOT injected' in out
        assert 'contract' in dropped
        assert len(out.encode())<=10000


def test_native_ledger_preserves_unknown_identity(tmp_path):
    project=tmp_path/'project';project.mkdir();state=tmp_path/'state'
    r=invoke(project,state,payload={'session_id':'session-1'},extra=('--telemetry',))
    assert r.returncode==0
    row=json.loads((state/'hook-health.jsonl').read_text())
    assert row['session_id']=='session-1'
    assert row['model'] is None and row['effort'] is None
    assert row['serialized_bytes']==len(r.stdout.encode())
    assert row['injected_bytes']==len(json.loads(r.stdout)['hookSpecificOutput']['additionalContext'].encode())


def test_doctor_requires_observation_after_refresh(tmp_path):
    project=tmp_path/'project';project.mkdir();state=tmp_path/'state'
    assert invoke(project,state,'refresh').returncode==0
    row={'timestamp':0,'status':'ok','serialized_bytes':1,'duration_ms':1,'context_identity':{'project_scope':str(project.resolve())}}
    (state/'hook-health.jsonl').write_text(json.dumps(row)+'\n')
    r=invoke(project,state,'doctor')
    assert json.loads(r.stdout)['ledger_status']=='unknown'


def test_doctor_reads_recent_events_from_large_private_ledger(tmp_path):
    project=tmp_path/'project';project.mkdir();state=tmp_path/'state'
    assert invoke(project,state,'refresh').returncode==0
    assert invoke(project,state,payload={'session_id':'recent'},extra=('--telemetry',)).returncode==0
    ledger=state/'hook-health.jsonl';recent=ledger.read_bytes()
    ledger.write_bytes((json.dumps({'padding':'x'*512})+'\n').encode()*35000 + recent)
    assert ledger.stat().st_size>16*1024*1024
    result=json.loads(invoke(project,state,'doctor').stdout)
    assert result['ledger_status']=='observed'


@pytest.mark.parametrize('kind',['public-directory','public-snapshot','symlink-snapshot'])
def test_untrusted_snapshot_reads_remain_unknown_without_writes(tmp_path,kind):
    project=tmp_path/'project';project.mkdir();state=tmp_path/'state'
    assert invoke(project,state,'refresh').returncode==0
    snapshot=next(state.glob('snapshot-*'))
    if kind=='public-directory': state.chmod(0o755)
    elif kind=='public-snapshot': snapshot.chmod(0o644)
    else:
        target=tmp_path/'other-snapshot';snapshot.rename(target);snapshot.symlink_to(target)
    before=tree(tmp_path)
    result=invoke(project,state)
    assert 'Startup snapshot: unknown' in result.stdout
    assert tree(tmp_path)==before


def test_blank_export_lines_preserve_active_task_and_owner(tmp_path):
    project=tmp_path/'project';project.mkdir();(project/'.beads').mkdir()
    (project/'.beads/issues.jsonl').write_text('\n  \n'+json.dumps({'id':'active-7','status':'blocked','assignee':'owner-7','notes':'needs review'})+'\n\n')
    result=invoke(project,tmp_path/'state')
    assert 'active-7' in result.stdout and 'owner-7' in result.stdout
    assert 'Task export unknown' not in result.stdout


def test_mode_and_state_errors_precede_verbose_diagnostics():
    spec=importlib.util.spec_from_file_location('startup_priority_test',SCRIPT)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sections=[('task','x'*9580),('mode','INTERSERVE MODE: ON'),
              ('ownership-error','ownership unknown; inspect live'),('task-error','tracker unavailable'),
              ('runtime-blocker','independent acceptance missing')]
    output,dropped,_=module.finish_context(sections,'unknown','current')
    assert all(name not in dropped for name in ('mode','ownership-error','task-error','runtime-blocker'))


def test_ledger_tail_uses_observed_size_during_concurrent_append(tmp_path,monkeypatch):
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('startup_tail_test',SCRIPT)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    project=tmp_path/'project';project.mkdir();state=tmp_path/'state';state.mkdir(mode=0o700)
    ledger=state/'hook-health.jsonl';ledger.write_bytes(b'prefix-line-1234567890\nold\n');ledger.chmod(0o600)
    original=os.fstat
    def append_after_stat(fd):
        info=original(fd)
        with ledger.open('ab') as stream: stream.write(b'new\n')
        return info
    monkeypatch.setattr(module,'MAX_READ',16)
    monkeypatch.setattr(module.os,'fstat',append_after_stat)
    assert module.read_private(SimpleNamespace(project=project,state_dir=state),ledger,tail=True)==[b'old']


def test_doctor_requires_current_host_and_source_identity(tmp_path):
    project=tmp_path/'project';project.mkdir();state=tmp_path/'state'
    assert invoke(project,state,'refresh').returncode==0
    assert invoke(project,state,extra=('--telemetry',)).returncode==0
    ledger=state/'hook-health.jsonl';row=json.loads(ledger.read_text())
    row['context_identity']['host']='different-host'
    ledger.write_text(json.dumps(row)+'\n')
    result=json.loads(invoke(project,state,'doctor').stdout)
    assert result['ledger_status']=='unknown'
