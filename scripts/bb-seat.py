#!/usr/bin/env python3
"""Supervise one BB execution seat. Events are evidence, never task acceptance."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time
import uuid


class SeatError(Exception):
    pass


def atomic(path, value):
    path=Path(path); temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('x') as stream:
        os.chmod(temporary,0o600)
        stream.write(json.dumps(value,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def command(argv, *, cwd=None, prompt=None, timeout=20):
    result=subprocess.run(argv,cwd=cwd,input=prompt,text=True,capture_output=True,timeout=timeout)
    if result.returncode:
        raise SeatError(f'{argv[0]} {argv[1]} failed ({result.returncode}): {result.stderr[:500]}')
    return result.stdout


def bb(*argv,prompt=None):
    value=json.loads(command([os.environ.get('BB_CLI') or 'bb',*argv,'--json'],prompt=prompt))
    if isinstance(value,dict) and value.get('ok') is False:
        raise SeatError('BB rejected command: '+str(value.get('error')))
    return value


def git(work,*argv):
    return command(['git','-C',str(work),*argv]).strip()


def persist(path,row):
    # Local intent is durable before any remote mutation, even if Intercore fails.
    atomic(path,row)
    argv=['ic']
    db=os.environ.get('CLAVAIN_INTERCORE_DB')
    cwd=row['workdir']
    if db:
        db=Path(db).resolve(strict=True);cwd=str(db.parent);argv+=['--db='+str(db)]
    command(argv+['state','set','clavain.bb-seat',row['attempt_id']],cwd=cwd,prompt=json.dumps(row))


def artifact(path):
    return {'path':str(path),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def stop_export_archive(row):
    thread=row['bb_thread_id']
    if thread=='unknown':
        candidates=bb('thread','list')
        matches=[t for t in candidates if t.get('title')=='Clavain seat '+row['attempt_id']
                 and t.get('parentThreadId')==row['parent_thread_id']]
        if len(matches)!=1 or not str(matches[0].get('id','')).startswith('thr_'):
            raise SeatError('Spawn acceptance unknown; reconcile saved intent before any new seat')
        thread=matches[0]['id'];row['bb_thread_id']=thread
        persist(Path(row['journal']),row)
    bb('thread','stop',thread)
    shown=bb('thread','show',thread)
    if shown['thread']['status'] not in ('idle','failed','error','interrupted'):
        raise SeatError('BB stop not confirmed')
    row['cleanup']='stopped'
    environment=shown.get('environment') or bb('environment','show',shown['thread']['environmentId'])
    work=Path(environment['path']).resolve(strict=True)
    # A forged/stale environment cannot export an unrelated checkout.
    if git(work,'rev-parse','--path-format=absolute','--git-common-dir') != row['git_common_dir']:
        raise SeatError('BB environment belongs to another repository')
    if subprocess.run(['git','-C',str(work),'merge-base','--is-ancestor',row['source_commit'],'HEAD'],capture_output=True).returncode:
        raise SeatError('BB environment does not descend from the pinned commit')
    output=Path(row['output'])
    patch=Path(str(output)+'.'+row['attempt_id']+'.patch')
    patch.write_text(command(['git','-C',str(work),'diff','--binary',row['source_commit']]))
    extras=Path(str(output)+'.'+row['attempt_id']+'.untracked.tar')
    names=command(['git','-C',str(work),'ls-files','--others','--exclude-standard','-z']).split('\0')
    with tarfile.open(extras,'w') as archive:
        for name in filter(None,names):
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise SeatError('Unsafe artifact path')
            archive.add(work/name,arcname=name,recursive=False)
    row['artifacts']={'patch':artifact(patch),'untracked':artifact(extras)}
    row['branch']=git(work,'rev-parse','--abbrev-ref','HEAD')
    row['checkout_after']=git(work,'rev-parse','HEAD')
    row['cleanup']='exported'
    # Durably record exported hashes before allowing archive to retire the tree.
    persist(Path(row['journal']),row)
    bb('thread','archive',thread)
    row['cleanup']='archived'


def reconcile(directory,parent):
    for path in directory.glob('*.json'):
        row=json.loads(path.read_text())
        if row.get('parent_thread_id')!=parent or row.get('cleanup')=='archived':
            continue
        with path.with_suffix('.lock').open('a') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: continue  # a live supervisor owns it
            stop_export_archive(row)
            row.update(state='terminal',outcome='interrupted')
            persist(path,row)


def resolve_project(work,host):
    common=git(work,'rev-parse','--path-format=absolute','--git-common-dir')
    matches=set()
    for project in bb('project','list'):
        for source in project.get('sources',[]):
            if source.get('hostId')!=host or not source.get('path'):
                continue
            try:
                if git(source['path'],'rev-parse','--path-format=absolute','--git-common-dir')==common:
                    matches.add(project['id'])
            except SeatError:
                continue
    if len(matches)!=1:
        raise SeatError('Source checkout must resolve to exactly one BB project on this host')
    return matches.pop(),common


def supervise(args):
    if args.role not in ('routine-execution','deep-execution') or args.sandbox=='read-only':
        raise SeatError('BB seats support writable execution roles only')
    spec=importlib.util.spec_from_file_location('bb_host',Path(__file__).with_name('bb-host.py'))
    host_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(host_module)
    host=host_module.bb_host()
    if not host: raise SeatError('BB seat requires an enrolled host')
    work=Path(args.workdir).resolve(strict=True)
    if git(work,'status','--porcelain'):
        raise SeatError('BB seat requires a clean source checkout; commit task changes first')
    project,common=resolve_project(work,host)
    provider={'codex':'codex','claude':'claude-code'}.get(args.backend)
    available=[p for p in bb('provider','list','--machine',host) if p['id']==provider and p.get('available')]
    if not available or 'auto' not in available[0].get('capabilities',{}).get('permissionModes',[]):
        raise SeatError('Requested provider/permission mode unavailable')
    models=bb('provider','models',provider,'--machine',host,'--selected-model',args.model)
    model=next((m for m in models if m.get('id')==args.model),{})
    if args.effort not in [r['reasoningEffort'] for r in model.get('supportedReasoningEfforts',[])]:
        raise SeatError('Requested model/effort unsupported')
    tier='default' if args.service_tier=='standard' else args.service_tier
    if tier not in [t['id'] for t in available[0].get('serviceTiers',[])]:
        raise SeatError('Requested service tier unsupported by BB provider')
    directory=Path(os.environ.get('CLAVAIN_BB_STATE_DIR','~/.local/state/clavain/bb/seats')).expanduser()
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    parent=os.environ['BB_THREAD_ID']
    reconcile(directory,parent)
    prompt=sys.stdin.read()
    if not prompt.strip(): raise SeatError('Empty prompt')
    key=hashlib.sha256(args.attempt_id.encode()).hexdigest()
    journal=directory/(key+'.json')
    if journal.exists(): raise SeatError('Attempt already exists; never spawn it twice')
    output=Path(args.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    row={'schema_version':1,'transport':'bb','role':args.role,'attempt_id':args.attempt_id,
         'dispatch_id':args.dispatch_id,'bead_id':os.environ.get('CLAVAIN_BEAD_ID',''),
         'run_id':os.environ.get('CLAVAIN_RUN_ID',''),'parent_thread_id':parent,
         'bb_thread_id':'unknown','turn_id':'unknown','request_id':'unknown','after_seq':0,
         'source_commit':git(work,'rev-parse','HEAD'),'git_common_dir':common,'workdir':str(work),
         'output':str(output),'journal':str(journal),'state':'intent','cleanup':'pending',
         'outcome':'unknown','actual_model':'unknown','actual_effort':'unknown',
         'effective_permission_mode':'unknown','usage':'unknown','account':'unknown',
         'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'artifacts':{}}
    cancelled=False
    def cancel(signum,frame):
        nonlocal cancelled
        cancelled=True
    previous={s:signal.signal(s,cancel) for s in (signal.SIGTERM,signal.SIGINT)}
    answer=''
    with journal.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        persist(journal,row)
        try:
            spawned=bb('thread','spawn','--project',project,'--parent-thread',parent,
                       '--lifecycle-owner-thread',parent,'--new-environment','worktree',
                       '--base-branch',row['source_commit'],'--provider',provider,'--model',args.model,
                       '--reasoning-level',args.effort,'--service-tier',tier,'--permission-mode','auto',
                       '--title','Clavain seat '+args.attempt_id,'--prompt-file','-',prompt=prompt)
            identity=spawned.get('id')
            if not isinstance(identity,str) or not identity.startswith('thr_'):
                raise SeatError('Unclear spawn response')
            row.update(bb_thread_id=identity,state='running')
            persist(journal,row)
            deadline=time.monotonic()+args.timeout
            while row['outcome']=='unknown':
                if cancelled:
                    row['outcome']='interrupted';break
                if time.monotonic()>=deadline:
                    row['outcome']='timeout';break
                events=bb('thread','log',identity,'--after-seq',str(row['after_seq']),'--limit','200')
                for event in events:
                    seq=event['seq']
                    if not isinstance(seq,int) or seq<=row['after_seq']: continue
                    row['after_seq']=seq
                    kind=event['type'];data=event.get('data',{});turn=event.get('scope',{}).get('turnId')
                    if kind=='client/turn/requested':
                        if row['request_id']!='unknown': raise SeatError('Unexpected additional submitted turn')
                        row['request_id']=data.get('requestId','unknown')
                    if kind=='turn/input/accepted':
                        if data.get('clientRequestId')!=row['request_id'] or not turn:
                            raise SeatError('Turn acceptance cannot be correlated')
                        row['turn_id']=turn
                    if turn!=row['turn_id']: continue
                    # Installed BB has no turn event attesting model, effort or
                    # effective permission. Requested settings are not evidence.
                    if kind=='thread/tokenUsage/updated':
                        row['usage']=data.get('tokenUsage','unknown')
                    if kind=='item/agentMessage/delta': answer+=data.get('delta','')
                    if kind in ('system/interaction/lifecycle','system/userQuestion/lifecycle'):
                        row['outcome']='waiting'
                    if kind=='provider/modelFallback':
                        row['outcome']='model-changed'
                    if kind=='provider/error' and data.get('willRetry'):
                        row['outcome']='provider-retry'  # dispatch alone owns retries
                    if kind=='turn/completed':
                        status=data.get('status')
                        row['outcome']=status if status in ('completed','failed','interrupted') else 'unknown-terminal'
                    if row['outcome']!='unknown':
                        break  # A later completion cannot erase a retry or interaction.
                persist(journal,row)
                if not events: time.sleep(min(.1,max(0,deadline-time.monotonic())))
            row['state']='terminal'
        except (SeatError,OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
            row.update(outcome='indeterminate',error=str(error))
        finally:
            for sig,handler in previous.items(): signal.signal(sig,handler)
            try: stop_export_archive(row)
            except (SeatError,OSError,ValueError,KeyError,TypeError,AttributeError,subprocess.SubprocessError) as error:
                row['cleanup_error']=str(error)
            complete=(row['outcome']=='completed' and row['cleanup']=='archived' and
                      row['actual_model']==args.model and row['actual_effort']==args.effort and
                      row['effective_permission_mode']=='auto')
            if os.environ.get('CLAVAIN_REQUIRE_USAGE')=='1' and (row['usage']=='unknown' or row['account']=='unknown'):
                complete=False
            row['accepted']=False  # independent validation is always separate
            row['failure_class']='' if complete else 'terminal_bb_evidence'
            output.write_text(answer)
            persist(journal,row)
            atomic(str(output)+'.receipt.json',row)
    if not complete:
        print('BB seat incomplete: '+row.get('error',row['outcome'])+'; cleanup='+row['cleanup'],file=sys.stderr)
    return 0 if complete else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('role','backend','model','effort','service-tier','workdir','output','attempt-id','dispatch-id'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--sandbox',default='workspace-write')
    parser.add_argument('--timeout',type=float,default=300)
    args=parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout<=0:
        parser.error('--timeout must be positive and finite')
    try: return supervise(args)
    except (SeatError,OSError,ValueError,KeyError,TypeError,AttributeError,subprocess.SubprocessError) as error:
        print('BB seat: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':
    raise SystemExit(main())
