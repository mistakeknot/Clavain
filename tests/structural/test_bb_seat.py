"""Seat transport tests use a fake BB CLI and real Git/Intercore state."""
import json
import os
from pathlib import Path
import subprocess
import shutil

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
import json,os,sys
from pathlib import Path
a=sys.argv[1:]; mode=os.environ.get('MODE','completed'); root=Path(os.environ['FIXTURE'])
with (root/'calls').open('a') as f: f.write(json.dumps(a)+'\\n')
value={}
if a[:1]==['status']: value={'thread':{'id':'thr_parent','environment':{'hostId':'host_pda34naxgq'}}}
elif a[:2]==['pool','status']: value={'accounts':[{'id':'fixture-'+p,'provider':p,'enabled':True,'sevenDayUtilization':v,'fiveHourUtilization':.1} for p,v in [('codex',.8),('claude',.2)]]}
elif a[:2]==['project','list']: value=[{'id':'proj_fixture','sources':[{'hostId':'host_pda34naxgq','path':str(root/'work')}]}]
elif a[:2]==['provider','list']: value=[{'id':p,'available':True,'capabilities':{'permissionModes':['auto']},'serviceTiers':[{'id':'default'}]} for p in ('codex','claude-code')]
elif a[:2]==['provider','models']: value=[{'id':m,'supportedReasoningEfforts':[{'reasoningEffort':e}]} for m,e in [('gpt-6-astra','xhigh'),('claude-sonnet-5','high')]]
elif a[:2]==['thread','spawn']:
 sys.stdin.read()
 if mode!='unclear': (root/'accepted').touch()
 if mode.startswith('unclear'): print('not-json'); sys.exit(0)
 value={'id':'thr_child','environmentId':'env_child'}
elif a[:2]==['thread','list']:
 value=[{'id':'thr_child','title':'Clavain seat attempt_one','parentThreadId':'thr_parent'}] if (root/'accepted').exists() else []
 if mode=='unclear-wrapped': value={'threads':value}
elif a[:2]==['thread','show']:
 value={'thread':{'id':'thr_child','status':'idle' if (root/'stopped').exists() or mode not in ('timeout','waiting') else 'active','environmentId':'env_child'},'environment':{'path':str(root/'child')}}
elif a[:2]==['thread','log']:
 def ev(seq,kind,data): return {'seq':seq,'type':kind,'scope':{'kind':'turn','turnId':'turn_one'},'data':data}
 value=[ev(1,'client/turn/requested',{'requestId':'request_one'}),ev(2,'turn/started',{}),ev(3,'turn/input/accepted',{'clientRequestId':'request_one'})]
 if mode!='unknown': value.append(ev(4,'thread/tokenUsage/updated',{'tokenUsage':{'inputTokens':10,'outputTokens':2}}))
 if mode=='provider-retry': value.append(ev(5,'provider/error',{'willRetry':True}))
 if mode=='model-changed': value.append(ev(5,'provider/modelFallback',{}))
 if mode not in ('timeout','waiting'):
  value += [ev(5,'item/agentMessage/delta',{'delta':'VERDICT: CLEAN'}),ev(6,'turn/completed',{'status':mode if mode in ('failed','interrupted') else 'completed'})]
 elif mode=='waiting': value.append(ev(5,'system/interaction/lifecycle',{}))
 after=int(a[a.index('--after-seq')+1]); value=[v for v in value if v['seq']>after]
elif a[:2]==['thread','stop']: (root/'stopped').touch()
elif a[:2]==['thread','archive']:
 assert list(root.glob('*.patch')), 'archive before export'
elif a[:2]==['environment','show']: value={'path':str(root/'child'),'hostId':'host_pda34naxgq'}
print(json.dumps(value))
''')
    cli.chmod(0o755)
    env=dict(os.environ,BB_CLI=str(cli),BB_THREAD_ID='thr_parent',BB_SERVER_URL='https://bb.example',
             FIXTURE=str(tmp_path),CLAVAIN_INTERCORE_DB=str(database),CLAVAIN_BB_STATE_DIR=str(tmp_path/'state'),CLAVAIN_REQUIRE_USAGE='0')
    def run(mode='completed',role='deep-execution',attempt='attempt_one',extra_env=None,
            backend='codex',model='gpt-6-astra',effort='xhigh',extra_args=(),via_dispatch=False):
        if via_dispatch:
            context=tmp_path/'decision.json'
            context.write_text(json.dumps({'reasons':[], 'rationale':'fixture'}))
            return subprocess.run(['bash',str(ROOT/'scripts/dispatch.sh'),'--role','routine-execution',
                '--via','bb','--context-file',str(context),'-C',str(work),'-o',str(tmp_path/'result'),'fixture'],
                text=True,capture_output=True,env=env | {'CLAVAIN_CONTEXT_GATEWAY_MODE':'off',
                    'CLAVAIN_BB_DIRECT_POOL':'1','CLAVAIN_POOL_HEADROOM':'1'},timeout=15)
        return subprocess.run(['python3',str(ROOT/'scripts/bb-seat.py'),'--role',role,'--backend',backend,
                 '--model',model,'--effort',effort,'--service-tier','standard','--workdir',str(work),
                 '--output',str(tmp_path/'result'), '--attempt-id',attempt,'--dispatch-id','dispatch_one',
                 '--timeout','0.6',*extra_args],input='Scratch fixture',text=True,capture_output=True,env=env | {'MODE':mode} | (extra_env or {}),timeout=15)
    return tmp_path,run


def test_spawn_contract(seat):
    root,run=seat; run()
    calls=[json.loads(s) for s in (root/'calls').read_text().splitlines()]
    spawn=next(x for x in calls if x[:2]==['thread','spawn'])
    assert spawn[spawn.index('--project')+1]=='proj_fixture'
    assert spawn[spawn.index('--service-tier')+1]=='default'
    assert spawn[spawn.index('--permission-mode')+1]=='auto'
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
    p=run(via_dispatch=True)
    assert p.returncode==1,p.stderr  # Unknown observed identity still blocks acceptance.
    receipt=json.loads((root/'result.receipt.json').read_text())
    assert receipt['requested_provider']=='claude-code'
    assert receipt['requested_model']=='claude-sonnet-5'
    assert receipt['profile_ref']=='routine-sol'
    assert receipt['resolved_profile_ref']=='routine-sonnet'
    assert receipt['headroom_reorder']['to'][0]=='routine-sonnet'
    assert receipt['actual_model']=='unknown'


def test_completion(seat):
    root,run=seat; p=run(); assert p.returncode==1,p.stderr
    r=json.loads((root/'result.receipt.json').read_text())
    assert r['bb_thread_id']=='thr_child' and r['turn_id']=='turn_one'
    assert r['actual_model']=='unknown' and r['actual_effort']=='unknown'
    assert r['outcome']=='completed' and r['accepted'] is False
    assert r['cleanup']=='archived' and r['artifacts']['patch']['sha256']


@pytest.mark.parametrize('mode',['timeout','waiting','failed','interrupted','provider-retry','model-changed'])
def test_timeout(seat,mode):
    root,run=seat; p=run(mode); assert p.returncode!=0
    calls=(root/'calls').read_text()
    assert '"stop"' in calls and '"archive"' in calls
    assert json.loads((root/'result.receipt.json').read_text())['outcome']==mode


def test_unknown_evidence(seat):
    root,run=seat; p=run('unknown'); assert p.returncode!=0
    r=json.loads((root/'result.receipt.json').read_text()); assert r['actual_model']=='unknown'


def test_read_only_refused(seat):
    root,run=seat; assert run(role='plan-review').returncode!=0
    assert not (root/'calls').exists()


def test_unclear_spawn(seat):
    root,run=seat; assert run('unclear').returncode!=0
    assert (root/'calls').read_text().count('"spawn"')==1
    assert run('completed',attempt='attempt_two').returncode!=0
    assert (root/'calls').read_text().count('"spawn"')==1


def test_orphan(seat):
    root,run=seat; assert run().returncode==1
    path=next((root/'state').glob('*.json')); row=json.loads(path.read_text())
    row['cleanup']='pending';row['state']='running';path.write_text(json.dumps(row))
    assert run(attempt='attempt_two').returncode==1
    assert json.loads(path.read_text())['cleanup']=='archived'


@pytest.mark.parametrize('mode',['unclear-found','unclear-wrapped'])
def test_unclear_spawn_reconciles_real_list_shapes(seat,mode):
    root,run=seat
    assert run(mode).returncode!=0
    row=json.loads((root/'result.receipt.json').read_text())
    assert row['bb_thread_id']=='thr_child' and row['cleanup']=='archived'
    assert (root/'calls').read_text().count('"spawn"')==1


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
