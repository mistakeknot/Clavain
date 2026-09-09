"""Startup is bounded evidence, never maintenance or acceptance authority."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/startup.py'


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
