"""Seat transport tests use a fake BB CLI and real Git/Intercore state."""
import itertools
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def seat(tmp_path):
    work=tmp_path/'work';work.mkdir()
    subprocess.run(['git','init','-q',str(work)],check=True)
    subprocess.run(['git','-C',str(work),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','fixture'],check=True)
    head=subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD'],text=True).strip()
    database=tmp_path/'intercore.db'
    subprocess.run(['ic','--db='+str(database),'init'],cwd=tmp_path,check=True,capture_output=True)
    child=tmp_path/'child'
    subprocess.run(['git','-C',str(work),'worktree','add','--detach',str(child),head],check=True,capture_output=True)
    cli=tmp_path/'bb'
    cli.write_text('''#!/usr/bin/env python3
import json,os,signal,subprocess,sys
from pathlib import Path
a=sys.argv[1:]; mode=os.environ.get('MODE','completed'); root=Path(os.environ['FIXTURE'])
with (root/'calls').open('a') as f: f.write(json.dumps(a)+'\\n')
value={}
if a[:1]==['status']: value={'thread':{'id':'thr_parent','environment':{'hostId':'host_pda34naxgq'}}}
elif a[:2]==['pool','status']: value={'accounts':[{'id':'fixture-'+p,'provider':p,'enabled':True,'sevenDayUtilization':v,'fiveHourUtilization':.1} for p,v in [('codex',.8),('claude',.2)]]}
elif a[:2]==['project','list']: value=[{'id':'proj_fixture','sources':[{'hostId':'host_pda34naxgq','path':str(root/'work')}]}]
elif a[:2]==['provider','list']: value=[{'id':p,'available':True,'capabilities':{'permissionModes':['auto']},'serviceTiers':[{'id':'default'}]} for p in ('codex','claude-code')]
elif a[:2]==['provider','models']: value=[{'id':m,'supportedReasoningEfforts':[{'reasoningEffort':e}]} for m,e in [('gpt-6-astra','xhigh'),('claude-sonnet-5','high'),('claude-opus-5-5','high')]]
elif a[:2]==['thread','spawn']:
 sys.stdin.read()
 if '--plan' in a: (root/'plan-mode').touch()
 if mode!='unclear': (root/'accepted').touch()
 if mode.startswith('unclear'): print('not-json'); sys.exit(0)
 value={'id':'thr_child','environmentId':'env_child'}
elif a[:2]==['thread','list']:
 value=[{'id':'thr_child','title':'Clavain seat attempt_one','parentThreadId':'thr_parent'}] if (root/'accepted').exists() else []
 if mode=='unclear-wrapped': value={'threads':value}
 if os.environ.get('BB_TEST_CANDIDATES_FILE'): value=json.loads(Path(os.environ['BB_TEST_CANDIDATES_FILE']).read_text())
elif a[:2]==['thread','show']:
 value={'thread':{'id':'thr_child','status':'idle' if (root/'stopped').exists() or mode not in ('timeout','waiting') else 'active','environmentId':'env_child'},'environment':{'path':str(root/'child')}}
elif a[:2]==['thread','log']:
 if mode=='mutated': (root/'child'/'unexpected.txt').write_text('review mutation')
 if mode=='committed-mutation': subprocess.run(['git','-C',str(root/'child'),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','review mutation'],check=True)
 def ev(seq,kind,data): return {'seq':seq,'type':kind,'scope':{'kind':'turn','turnId':'turn_one'},'data':data}
 value=[ev(1,'client/turn/requested',{'requestId':'request_one'}),ev(2,'turn/started',{}),ev(3,'turn/input/accepted',{'clientRequestId':'request_one'})]
 if mode!='unknown': value.append(ev(4,'thread/tokenUsage/updated',{'tokenUsage':{'inputTokens':10,'outputTokens':2,'sensitiveField':'must-not-persist'}}))
 if mode=='provider-retry': value.append(ev(5,'provider/error',{'willRetry':True}))
 if mode=='model-changed': value.append(ev(5,'provider/modelFallback',{}))
 if mode=='plan-completed':
  value += [ev(5,'item/plan/delta',{'itemId':'plan_one','delta':'partial'}),ev(6,'item/completed',{'item':{'type':'plan','id':'plan_one','text':'VERDICT: FINAL'}}),ev(7,'turn/completed',{'status':'completed'})]
 elif mode=='plan-approval':
  value.append(ev(5,'system/interaction/lifecycle',{'interaction':{'payload':{'kind':'approval','subject':{'kind':'plan','itemId':'plan_one','plan':'VERDICT: APPROVAL','planFilePath':None}}}}))
 elif mode not in ('timeout','waiting'):
  message_kind='item/plan/delta' if (root/'plan-mode').exists() else 'item/agentMessage/delta'
  value += [ev(5,message_kind,{'itemId':'plan_one','delta':'VERDICT: CLEAN'}),ev(6,'turn/completed',{'status':mode if mode in ('failed','interrupted') else 'completed'})]
 elif mode=='waiting': value.append(ev(5,'system/interaction/lifecycle',{}))
 after=int(a[a.index('--after-seq')+1]); value=[v for v in value if v['seq']>after]
 if os.environ.get('BB_TEST_EVENTS_FILE'):
  pages=json.loads(Path(os.environ['BB_TEST_EVENTS_FILE']).read_text())
  counter=root/'log-count'; index=int(counter.read_text()) if counter.exists() else 0
  counter.write_text(str(index+1))
  value=pages[index] if index<len(pages) else []
elif a[:2]==['thread','stop']: (root/'stopped').touch()
elif a[:2]==['thread','archive']:
 assert list(root.glob('*.patch')), 'archive before export'
elif a[:2]==['environment','show']: value={'path':str(root/'child'),'hostId':'host_pda34naxgq'}
# Cut the real supervisor at an external side-effect boundary. The transport
# does not implement recovery, deduplication, or any expected invariant.
fault=os.environ.get('BB_TEST_CRASH')
hit=(fault=='spawn-accepted' and a[:2]==['thread','spawn'] or
     fault=='log-observed' and a[:2]==['thread','log'] and (root/'log-count').read_text()=='2' or
     fault in ('stop','archive') and a[:2]==['thread',fault])
if hit and not (root/'crashed').exists():
 (root/'crashed').touch()
 os.kill(os.getppid(),signal.SIGKILL)
print(json.dumps(value))
''')
    cli.chmod(0o755)
    env=dict(os.environ,BB_CLI=str(cli),BB_THREAD_ID='thr_parent',BB_SERVER_URL='https://bb.example',
             FIXTURE=str(tmp_path),CLAVAIN_INTERCORE_DB=str(database),CLAVAIN_BB_STATE_DIR=str(tmp_path/'state'),CLAVAIN_REQUIRE_USAGE='0')
    def run(mode='completed',role='deep-execution',attempt='attempt_one',extra_env=None,
            backend='codex',model='gpt-6-astra',effort='xhigh',extra_args=(),via_dispatch=False,
            sandbox=None,producer_identity='gpt-6-astra'):
        if via_dispatch:
            context=tmp_path/'decision.json'
            context.write_text(json.dumps({'reasons':[], 'rationale':'fixture'}))
            command=['bash',str(ROOT/'scripts/dispatch.sh'),'--role',role,
                '--via','bb','--context-file',str(context),'-C',str(work),'-o',str(tmp_path/'result')]
            if role in ('plan-review','validation'):
                command += ['--producer-identity',producer_identity]
            if sandbox is not None:
                command += ['--sandbox',sandbox]
            command += list(extra_args)
            command += ['fixture']
            return subprocess.run(command,
                text=True,capture_output=True,env=env | {'CLAVAIN_CONTEXT_GATEWAY_MODE':'off',
                    'CLAVAIN_BB_DIRECT_POOL':'1','CLAVAIN_POOL_HEADROOM':'1'} | (extra_env or {}),timeout=15)
        command=['python3',str(ROOT/'scripts/bb-seat.py'),'--role',role,'--backend',backend,
                 '--model',model,'--effort',effort,'--service-tier','standard','--workdir',str(work),
                 '--output',str(tmp_path/'result'), '--attempt-id',attempt,'--dispatch-id','dispatch_one',
                 '--timeout','0.6']
        if sandbox is not None:
            command += ['--sandbox',sandbox]
        command += list(extra_args)
        return subprocess.run(command,input='Scratch fixture',text=True,capture_output=True,env=env | {'MODE':mode} | (extra_env or {}),timeout=15)
    return tmp_path,run


@pytest.mark.requires_ic
def test_spawn_contract(seat):
    root,run=seat; run()
    calls=[json.loads(s) for s in (root/'calls').read_text().splitlines()]
    spawn=next(x for x in calls if x[:2]==['thread','spawn'])
    assert spawn[spawn.index('--project')+1]=='proj_fixture'
    assert spawn[spawn.index('--service-tier')+1]=='default'
    assert spawn[spawn.index('--permission-mode')+1]=='auto'
    assert '--plan' not in spawn
    assert len(spawn[spawn.index('--base-branch')+1])==40


@pytest.mark.requires_ic
def test_headroom_resolved_claude_seat(seat):
    root,run=seat
    reorder={'from':['routine-sol','routine-sonnet'], 'to':['routine-sonnet','routine-sol'],
             'snapshot_at':'2026-09-22T23:00:00Z'}
    route={'profile_ref':'routine-sol','headroom_reorder':reorder,'headroom_exclusion':[]}
    p=run(role='routine-execution',backend='claude',model='claude-sonnet-5',effort='high',
          extra_args=['--resolved-route-json',json.dumps(route),'--profile-ref','routine-sonnet'])
    assert p.returncode==1,p.stderr  # BB still supplies no observed model attestation.
    calls=[json.loads(s) for s in (root/'calls').read_text().splitlines()]
    spawn=next(x for x in calls if x[:2]==['thread','spawn'])
    assert spawn[spawn.index('--provider')+1]=='claude-code'
    assert spawn[spawn.index('--model')+1]=='claude-sonnet-5'
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['profile_ref']=='routine-sol'
    assert receipt['resolved_profile_ref']=='routine-sonnet'
    assert receipt['headroom_reorder']==reorder
    assert receipt['requested_provider']=='claude-code'
    assert receipt['requested_model']=='claude-sonnet-5'
    assert receipt['actual_model']=='unknown'


@pytest.mark.requires_ic
def test_dispatch_carries_headroom_route_to_bb_journal(seat):
    root,run=seat
    p=run(role='routine-execution',via_dispatch=True)
    assert p.returncode==1,p.stderr  # Unknown observed identity still blocks acceptance.
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['requested_provider']=='claude-code'
    assert receipt['requested_model']=='claude-sonnet-5'
    assert receipt['profile_ref']=='routine-sol'
    assert receipt['resolved_profile_ref']=='routine-sonnet'
    assert receipt['headroom_reorder']['to'][0]=='routine-sonnet'
    assert receipt['actual_model']=='unknown'


@pytest.mark.requires_ic
def test_completion(seat):
    root,run=seat; p=run(); assert p.returncode==1,p.stderr
    r=json.loads((root/'result.receipt.json').read_text())
    assert r['bb_thread_id']=='thr_child' and r['turn_id']=='turn_one'
    assert r['actual_model']=='unknown' and r['actual_effort']=='unknown'
    assert r['outcome']=='completed' and r['accepted'] is False
    assert r['usage']=={'inputTokens':10,'outputTokens':2}
    assert r['cleanup']=='archived' and r['artifacts']['patch']['sha256']


def test_read_only_completion_rejects_writable_permission_attestation():
    spec=importlib.util.spec_from_file_location('bb_seat_completion',ROOT/'scripts/bb-seat.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    args=SimpleNamespace(model='claude-opus-5-5',effort='high')
    receipt={'outcome':'completed','cleanup':'archived','actual_model':args.model,
             'actual_effort':args.effort,'effective_permission_mode':'auto'}
    assert module.completion_evidence_matches(receipt,args,read_only=True) is False
    receipt['effective_permission_mode']='plan'
    assert module.completion_evidence_matches(receipt,args,read_only=True) is True
    receipt['effective_permission_mode']='auto'
    assert module.completion_evidence_matches(receipt,args,read_only=False) is True


@pytest.mark.requires_ic
@pytest.mark.parametrize('mode',['timeout','waiting','failed','interrupted','provider-retry','model-changed'])
def test_timeout(seat,mode):
    root,run=seat; p=run(mode); assert p.returncode!=0
    calls=(root/'calls').read_text()
    assert '"stop"' in calls and '"archive"' in calls
    assert json.loads((root/'result.receipt.json').read_text())['outcome']==mode


@pytest.mark.requires_ic
def test_unknown_evidence(seat):
    root,run=seat; p=run('unknown'); assert p.returncode!=0
    r=json.loads((root/'result.receipt.json').read_text()); assert r['actual_model']=='unknown'


@pytest.mark.requires_ic
@pytest.mark.parametrize('role', ['plan-review','validation'])
def test_review_roles_accept_only_read_only_and_record_receipt(seat,role):
    root,run=seat
    result=run(role=role,sandbox='read-only',backend='claude',model='claude-opus-5-5',effort='high')
    assert result.returncode==1,result.stderr  # Missing observed identity still blocks acceptance.
    calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
    spawn=next(call for call in calls if call[:2]==['thread','spawn'])
    assert '--plan' in spawn
    assert spawn[spawn.index('--provider')+1]=='claude-code'
    assert spawn[spawn.index('--permission-mode')+1]=='auto'
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['schema_version']==2
    assert receipt['role']==role
    assert receipt['sandbox']=='read-only'
    assert (root/'result').read_text()=='VERDICT: CLEAN'


@pytest.mark.parametrize(('mode','expected'), [
    ('plan-completed','VERDICT: FINAL'),
    ('plan-approval','VERDICT: APPROVAL'),
])
@pytest.mark.requires_ic
def test_review_roles_capture_terminal_plan_shapes(seat,mode,expected):
    root,run=seat
    result=run(mode=mode,role='plan-review',sandbox='read-only',backend='claude',
               model='claude-opus-5-5',effort='high')
    assert result.returncode==1,result.stderr
    assert (root/'result').read_text()==expected


@pytest.mark.requires_ic
def test_read_only_review_mutation_is_a_terminal_seat_failure(seat):
    root,run=seat
    result=run(mode='mutated',role='plan-review',sandbox='read-only',backend='claude',
               model='claude-opus-5-5',effort='high')
    assert result.returncode!=0
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['outcome']=='sandbox-violation'
    assert receipt['accepted'] is False
    assert receipt['artifacts']['patch']['sha256']


@pytest.mark.requires_ic
def test_read_only_review_commit_is_a_terminal_seat_failure(seat):
    root,run=seat
    result=run(mode='committed-mutation',role='plan-review',sandbox='read-only',backend='claude',
               model='claude-opus-5-5',effort='high')
    assert result.returncode!=0
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['checkout_after']!=receipt['source_commit']
    assert receipt['outcome']=='sandbox-violation'


@pytest.mark.requires_ic
def test_recovery_preserves_review_sandbox_violation(seat):
    root,run=seat
    result=run(mode='mutated',role='plan-review',sandbox='read-only',backend='claude',
               model='claude-opus-5-5',effort='high',extra_env={'BB_TEST_CRASH':'archive'})
    assert result.returncode==-9,result.stderr
    journal=next((root/'state').glob('*.json'))
    assert json.loads(journal.read_text())['outcome']=='sandbox-violation'
    run(mode='mutated',role='plan-review',attempt='attempt_two',sandbox='read-only',backend='claude',
        model='claude-opus-5-5',effort='high',extra_env={'BB_TEST_CRASH':'archive'})
    assert json.loads(journal.read_text())['outcome']=='sandbox-violation'


@pytest.mark.requires_ic
def test_codex_review_rejected_without_enforced_read_only_bb_permission(seat):
    root,run=seat
    failure=root/'failure-class'
    result=run(role='plan-review',sandbox='read-only',
               extra_env={'CLAVAIN_DISPATCH_FAILURE_FILE':str(failure)})
    assert result.returncode!=0
    assert 'cannot enforce read-only' in result.stderr
    assert failure.read_text().strip()=='unsupported_adapter'
    assert not (root/'calls').exists()


def astra_first_review_policy(root):
    policy=(ROOT/'config/routing.yaml').read_text()
    assert '    plan-review: review-opus\n' in policy
    policy=policy.replace('    plan-review: review-opus\n','    plan-review: review-astra\n',1)
    policy=policy.replace('      description: Cross-lab reviewer for Claude-authored plans\n',
                          '      fallbacks: [review-opus]\n'
                          '      description: Cross-lab reviewer for Claude-authored plans\n',1)
    path=root/'astra-first-routing.yaml';path.write_text(policy)
    return path


@pytest.mark.requires_ic
def test_dispatch_astra_first_review_falls_back_to_read_only_claude_seat(seat):
    root,run=seat
    policy=astra_first_review_policy(root)
    result=run(role='plan-review',via_dispatch=True,producer_identity='gpt-5',
               extra_env={'CLAVAIN_ROUTING_POLICY':str(policy)})
    assert result.returncode==1,result.stderr  # Fallback ran; observed identity remains unknown.
    assert "review-astra' unavailable (unsupported_adapter)" in result.stderr
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['resolved_profile_ref']=='review-opus'
    assert receipt['requested_provider']=='claude-code'
    calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
    assert sum(call[:2]==['thread','spawn'] for call in calls)==1


@pytest.mark.requires_ic
def test_dispatch_dry_run_applies_backend_check_and_reports_read_only_fallback(seat):
    root,run=seat
    policy=astra_first_review_policy(root)
    result=run(role='plan-review',via_dispatch=True,producer_identity='gpt-5',
               extra_env={'CLAVAIN_ROUTING_POLICY':str(policy)},extra_args=['--dry-run'])
    assert result.returncode==0,result.stderr
    assert "review-astra' unavailable (unsupported_adapter)" in result.stderr
    assert 'backend=claude' in result.stdout
    assert 'backend=codex' not in result.stdout
    calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
    assert not any(call[:2]==['thread','spawn'] for call in calls)


@pytest.mark.requires_ic
@pytest.mark.parametrize('role', ['plan-review','validation'])
@pytest.mark.parametrize('sandbox', ['workspace-write','danger-full-access'])
def test_review_roles_reject_writable_sandboxes_before_bb(seat,role,sandbox):
    root,run=seat
    result=run(role=role,sandbox=sandbox)
    assert result.returncode!=0
    assert 'not permitted' in result.stderr
    assert not (root/'calls').exists()


@pytest.mark.requires_ic
def test_unknown_role_rejected_before_bb(seat):
    root,run=seat
    result=run(role='cross-lab-review',sandbox='read-only')
    assert result.returncode!=0
    assert 'unsupported role' in result.stderr
    assert not (root/'calls').exists()


@pytest.mark.requires_ic
@pytest.mark.parametrize('role', ['routine-execution','deep-execution'])
@pytest.mark.parametrize('sandbox', ['workspace-write','danger-full-access'])
def test_execution_roles_keep_writable_auto_mode(seat,role,sandbox):
    root,run=seat
    result=run(role=role,sandbox=sandbox)
    assert result.returncode==1,result.stderr  # Missing observed identity still blocks acceptance.
    calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
    spawn=next(call for call in calls if call[:2]==['thread','spawn'])
    assert '--plan' not in spawn
    assert spawn[spawn.index('--permission-mode')+1]=='auto'
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['role']==role
    assert receipt['sandbox']==sandbox


@pytest.mark.requires_ic
@pytest.mark.parametrize('role', ['plan-review','validation'])
def test_dispatch_review_roles_default_read_only_through_helper(seat,role):
    root,run=seat
    result=run(role=role,via_dispatch=True)
    assert result.returncode==1,result.stderr  # Missing observed identity still blocks acceptance.
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['role']==role
    assert receipt['sandbox']=='read-only'
    calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
    spawn=next(call for call in calls if call[:2]==['thread','spawn'])
    assert '--plan' in spawn
    assert spawn[spawn.index('--provider')+1]=='claude-code'


@pytest.mark.requires_ic
def test_dispatch_plan_review_rejects_explicit_writable_sandbox(seat):
    root,run=seat
    result=run(role='plan-review',via_dispatch=True,sandbox='workspace-write')
    assert result.returncode!=0
    assert 'not permitted' in result.stderr
    assert not (root/'calls').exists()


@pytest.mark.requires_ic
def test_unclear_spawn(seat):
    root,run=seat; assert run('unclear').returncode!=0
    assert (root/'calls').read_text().count('"spawn"')==1
    assert run('completed',attempt='attempt_two').returncode!=0
    assert (root/'calls').read_text().count('"spawn"')==1


@pytest.mark.requires_ic
def test_orphan(seat):
    root,run=seat; assert run().returncode==1
    path=next((root/'state').glob('*.json')); row=json.loads(path.read_text())
    row['cleanup']='pending';row['state']='running';path.write_text(json.dumps(row))
    assert run(attempt='attempt_two').returncode==1
    assert json.loads(path.read_text())['cleanup']=='archived'


@pytest.mark.requires_ic
@pytest.mark.parametrize('mode',['unclear-found','unclear-wrapped'])
def test_unclear_spawn_reconciles_real_list_shapes(seat,mode):
    root,run=seat
    assert run(mode).returncode!=0
    row=json.loads((root/'result.receipt.json').read_text())
    assert row['bb_thread_id']=='thr_child' and row['cleanup']=='archived'
    assert (root/'calls').read_text().count('"spawn"')==1


@pytest.mark.requires_ic
@pytest.mark.parametrize('fail_at',[1,2])
def test_intercore_failure_before_spawn_does_not_block_next_attempt(seat,fail_at):
    root,run=seat
    real_ic=shutil.which('ic')
    shim=root/'ic'
    shim.write_text(f'''#!/usr/bin/env python3
import os,sys
from pathlib import Path
p=Path({str(root/'ic-count')!r})
count=int(p.read_text())+1 if p.exists() else 1
p.write_text(str(count))
if count=={fail_at}: sys.exit(1)
os.execv({real_ic!r}, [{real_ic!r}, *sys.argv[1:]])
''')
    shim.chmod(0o755)
    env={'PATH':str(root)+':'+os.environ['PATH']}
    assert run(extra_env=env).returncode!=0
    assert '"spawn"' not in (root/'calls').read_text()
    path=next((root/'state').glob('*.json'))
    assert run(attempt='attempt_two',extra_env=env).returncode==1
    assert (root/'calls').read_text().count('"spawn"')==1
    assert json.loads(path.read_text())['cleanup']=='not-started'


def recovery_event(seq, kind, data=None, turn='turn_one'):
    return {'seq':seq, 'type':kind, 'scope':{'kind':'turn', 'turnId':turn},
            'data':data or {}}


def recovery_pages(order, terminals=('interrupted','completed')):
    """Reorder semantic observations, preserving BB's monotonic log sequence."""
    events=[recovery_event(1, 'client/turn/requested', {'requestId':'request_one'}),
            recovery_event(2, 'turn/input/accepted', {'clientRequestId':'request_one'})]
    for kind in order:
        if kind=='usage':
            event=recovery_event(len(events)+1, 'thread/tokenUsage/updated',
                                 {'tokenUsage':{'inputTokens':17, 'outputTokens':5}})
        else:
            event=recovery_event(len(events)+1, 'item/agentMessage/delta',
                                 {'delta':'result before cancellation'})
        events.append(event)
    # A repeated page and unrelated turn may neither double usage nor replace
    # this attempt's result. The fake delivers bytes; the real supervisor folds.
    return [events, [events[-1],
            recovery_event(5, 'thread/tokenUsage/updated',
                           {'tokenUsage':{'inputTokens':999, 'outputTokens':999}}, 'other_turn'),
            recovery_event(6, 'turn/completed', {'status':terminals[0]}),
            recovery_event(7, 'turn/completed', {'status':terminals[1]})]]


@pytest.mark.parametrize('order', list(itertools.permutations(('usage','result'))),
                         ids=lambda order:'-'.join(order))
@pytest.mark.parametrize('terminals', list(itertools.permutations(('interrupted','completed'))),
                         ids=lambda order:'-'.join(order))
@pytest.mark.requires_ic
def test_generated_observation_order_and_duplicate_cancellation(seat, order, terminals):
    root, run=seat
    events=root/'observations.json'
    events.write_text(json.dumps(recovery_pages(order, terminals)))
    result=run(extra_env={'BB_TEST_EVENTS_FILE':str(events)})
    assert result.returncode==1, result.stderr
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['outcome']==terminals[0]
    assert receipt['usage']=={'inputTokens':17, 'outputTokens':5}
    assert receipt['accepted'] is False
    assert (root/'result').read_text()=='result before cancellation'
    assert receipt['cleanup']=='archived'
    assert sum(json.loads(line)[:2]==['thread','spawn']
               for line in (root/'calls').read_text().splitlines())==1


@pytest.mark.parametrize('order', list(itertools.permutations(('usage','result'))),
                         ids=lambda order:'-'.join(order))
@pytest.mark.requires_ic
@pytest.mark.parametrize('boundary', ['spawn-accepted','log-observed','stop','archive'])
def test_generated_supervisor_crash_recovery(seat, order, boundary):
    root, run=seat
    events=root/'observations.json'
    events.write_text(json.dumps(recovery_pages(order)))
    env={'BB_TEST_EVENTS_FILE':str(events), 'BB_TEST_CRASH':boundary}
    result=run(extra_env=env)
    assert result.returncode==-9, result.stderr
    journal=next((root/'state').glob('*.json'))
    before=json.loads(journal.read_text())
    assert before['cleanup']!='archived'
    if boundary=='spawn-accepted':
        assert before['state']=='spawning' and before['bb_thread_id']=='unknown'
    else:
        assert before['usage']=={'inputTokens':17, 'outputTokens':5}

    # An orphan belonging to a different parent is not ours to retire. This
    # journal represents another owner's reservation and must remain untouched.
    foreign=root/'state'/'foreign.json'
    foreign.write_text(json.dumps(dict(before, attempt_id='foreign_attempt',
                                      parent_thread_id='thr_other', bb_thread_id='thr_foreign')))
    foreign_bytes=foreign.read_bytes()
    for _ in range(2):
        # A new process recovers actual durable state and refuses replay of the
        # same attempt, including loss of the accepted spawn response.
        replay=run(extra_env=env)
        assert replay.returncode==1, replay.stderr
        assert 'Attempt already exists' in replay.stderr
        after=json.loads(journal.read_text())
        assert after['state']=='terminal' and after['outcome']=='interrupted'
        assert after['cleanup']=='archived' and after['bb_thread_id']=='thr_child'
        assert after['usage']==before['usage']
        assert foreign.read_bytes()==foreign_bytes
        calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
        assert sum(call[:2]==['thread','spawn'] for call in calls)==1
        assert not any('thr_foreign' in call for call in calls)
        assert after['artifacts']['patch']['sha256']
        with sqlite3.connect(root/'intercore.db') as db:
            payload,=db.execute("SELECT payload FROM state WHERE key='clavain.bb-seat' AND scope_id=?",
                                ('attempt_one',)).fetchone()
        assert json.loads(payload)==after


@pytest.mark.requires_ic
@pytest.mark.parametrize('discovery', ['missing','ambiguous','foreign-parent'])
def test_unknown_acceptance_blocks_new_attempt_until_unambiguous(seat, discovery):
    root, run=seat
    assert run(extra_env={'BB_TEST_CRASH':'spawn-accepted'}).returncode==-9
    child={'id':'thr_child', 'title':'Clavain seat attempt_one', 'parentThreadId':'thr_parent'}
    foreign=dict(child, id='thr_foreign', parentThreadId='thr_other')
    candidates={'missing':[], 'ambiguous':[child, dict(child,id='thr_duplicate')],
                'foreign-parent':[foreign]}
    listing=root/'candidates.json'
    listing.write_text(json.dumps(candidates[discovery]))
    env={'BB_TEST_CANDIDATES_FILE':str(listing)}
    journal=next((root/'state').glob('*.json'))
    before=journal.read_bytes()
    for attempt in ('attempt_one','attempt_two'):
        result=run(attempt=attempt,extra_env=env)
        assert result.returncode==1
        assert 'Spawn acceptance unknown' in result.stderr
        assert journal.read_bytes()==before
        calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
        assert sum(call[:2]==['thread','spawn'] for call in calls)==1
        assert not any(call[:2] in (['thread','stop'],['thread','archive']) for call in calls)
    # Discovery later resolves the original call. A foreign same-title child
    # is still excluded, irrespective of list order.
    for listing_order in itertools.permutations((foreign,child)):
        listing.write_text(json.dumps(listing_order))
        assert run(extra_env=env).returncode==1
        recovered=json.loads(journal.read_text())
        assert recovered['bb_thread_id']=='thr_child' and recovered['cleanup']=='archived'
        assert recovered['usage']=='unknown'
        calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
        assert sum(call[:2]==['thread','spawn'] for call in calls)==1
        assert not any('thr_foreign' in call or 'thr_duplicate' in call for call in calls)


@pytest.mark.parametrize('fixture', ['codex-usage-limit-rollout.jsonl',
                                   'codex-usage-limit-stdout.jsonl'])
@pytest.mark.parametrize('order', list(itertools.permutations(('failure','result','cancel'))),
                         ids=lambda order:'-'.join(order))
def test_recorded_failure_envelopes_with_reordered_results(tmp_path, fixture, order):
    # Replay the recorded provider bytes through their production parser, not
    # an invented translation to BB events. BB observation recovery is above.
    recorded=(ROOT/'tests'/'fixtures'/fixture).read_bytes()
    groups={'failure':recorded,
            'result':b'{"type":"turn.completed","usage":{"input_tokens":17,"output_tokens":5}}\n',
            'cancel':b'{"type":"turn.failed","error":{"message":"interrupted by user"}}\n'}
    stream=b''.join(groups[kind] for kind in order)+recorded
    (tmp_path/'replay.jsonl').write_bytes(stream)
    work=tmp_path/'work'
    subprocess.run(['git','init','-q',str(work)], check=True)
    cli=tmp_path/'codex'
    cli.write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
root=Path(os.environ['REPLAY_ROOT'])
with (root/'invocations').open('a') as log: log.write('spawn\\n')
Path(sys.argv[sys.argv.index('-o')+1]).write_text('VERDICT: CLEAN')
sys.stdout.buffer.write((root/'replay.jsonl').read_bytes())
''')
    cli.chmod(0o755)
    env=dict(os.environ, PATH=str(tmp_path)+':'+os.environ['PATH'],
             REPLAY_ROOT=str(tmp_path), CLAVAIN_CONTEXT_GATEWAY_MODE='off',
             CLAVAIN_BB_DIRECT_POOL='0', CLAVAIN_REQUIRE_USAGE='0',
             CLAVAIN_DISPATCH_FAILURE_FILE=str(tmp_path/'failure'),
             CLAVAIN_REVIEW_EVENTS=str(tmp_path/'events'))
    result=subprocess.run(['bash',str(ROOT/'scripts/dispatch.sh'),'-C',str(work),
                           '-o',str(tmp_path/'out'),'fixture'],
                          env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode!=0, result.stderr
    # Explicit failed/cancelled work dominates quota fallback, regardless of
    # ordering, and cannot be laundered into success by a later result.
    assert (tmp_path/'failure').read_text().strip()=='terminal_error'
    assert (tmp_path/'events').read_bytes()==stream
    assert (tmp_path/'invocations').read_text()=='spawn\n'
    assert 'Tokens: 17 in / 5 out\n' in (tmp_path/'out.summary').read_text()
