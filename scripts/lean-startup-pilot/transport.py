"""One coordinator DB; Claude executes on zklw with sealed evidence returned.

Only disposable cohort fixtures cross SSH. Candidate repositories arrive through
Git at the manifest commits. Enrollment and acceptance always run on the Mac.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

import delivery

HOST='zklw'


def remote(code, *args, data=None):
    command=shlex.join(['python3','-c',code,*map(str,args)])
    return subprocess.run(['ssh','-o','BatchMode=yes',HOST,command],input=data,capture_output=True,check=True).stdout


def unpack(data, destination):
    """Evidence paths are relative, regular files only, bounded to 64 MiB total."""
    if len(data)>90*1024**2:raise ValueError('oversized evidence response')
    destination=destination.resolve()
    rows=json.loads(data);total=0;mapping={}
    for row in rows:
        relative=Path(row['relative'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('unsafe evidence path')
        raw=base64.b64decode(row['bytes'],validate=True);total+=len(raw)
        if total>64*1024**2 or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('invalid evidence bytes')
        output=destination/relative
        if any(p.is_symlink() for p in (output,*output.parents) if p!=destination and destination in p.parents):raise ValueError('linked evidence destination')
        output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists() and output.read_bytes()!=raw:raise ValueError('existing evidence changed')
        output.write_bytes(raw);mapping[row['original']]=str(output)
    return mapping


COLLECT='''import base64,hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();mode=sys.argv[2];rows=[];total=0
names=['prelaunch.json','request.json','binary.json'] if mode=='prepared' else ['result.json','initial.stdout','initial.stderr','precompact.stdout','precompact.stderr','compaction.stdout','compaction.stderr','resume.stdout','resume.stderr']
paths=[root/n for n in names]
required=names if mode=='prepared' else (['result.json','initial.stdout','initial.stderr'] if mode=='completed' else [])
for name in required:
 if not (root/name).is_file():raise ValueError('required evidence missing: '+name)
if mode!='prepared':
 for name in ['fixture','private-state','profile/.claude/projects','profile/.codex/sessions','readiness']:
  paths.extend((root/name).rglob('*'))
for p in paths:
 if p.is_symlink():
  if p.parent==root/'fixture/.claude/skills':
   # Discovery links are fixture wiring, not native evidence. Preserve the
   # target as an observation without following or silently dropping it.
   raw=json.dumps({'path':str(p),'target':str(p.readlink())}).encode()
   rows.append(dict(relative='skill-links/'+p.name+'.json',original=str(p),sha256=hashlib.sha256(raw).hexdigest(),bytes=base64.b64encode(raw).decode()))
   continue
  raise ValueError('linked evidence: '+str(p))
 if not p.is_file():continue
 if any(q.is_symlink() for q in p.parents if q!=root and root in q.parents):raise ValueError('linked evidence ancestor')
 raw=p.read_bytes();total+=len(raw)
 if total>67108864:raise ValueError('oversized evidence')
 rows.append(dict(relative=str(p.relative_to(root)),original=str(p),sha256=hashlib.sha256(raw).hexdigest(),bytes=base64.b64encode(raw).decode()))
print(json.dumps(rows))
'''


def bootstrap(base, target):
    manifest=json.loads((base/'manifest.json').read_text())
    if manifest.get('cohort_kind')!='correctness':raise ValueError('correctness cohort required')
    # Catalog is a frozen observed fixture, never a live checkout synchronization.
    paths=[base/'manifest.json',base/'catalog.json',base/'sources/candidate/global-AGENTS.md']
    paths.extend(p for p in (base/'catalog').rglob('*') if p.is_file())
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as archive:
        for p in paths:
            if p.is_symlink():raise ValueError('linked fixture')
            archive.add(p,arcname=str(p.relative_to(base)),recursive=False)
    code='''import io,json,subprocess,sys,tarfile
from pathlib import Path
base=Path(sys.argv[1]);base.mkdir(mode=0o700);(base/'results').mkdir()
with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read())) as archive:archive.extractall(base,filter='data')
manifest=json.loads((base/'manifest.json').read_text())
for name,slug in [('clavain','Clavain'),('intertest','intertest')]:
 repo=base/('git-'+name);sha=manifest['pins']['candidate'][name]
 subprocess.run(['git','clone','--quiet','https://github.com/mistakeknot/'+slug,str(repo)],check=True)
 actual=subprocess.check_output(['git','-C',str(repo),'rev-parse',sha+'^{commit}'],text=True).strip()
 if actual!=sha:raise ValueError('source pin mismatch')
 raw=subprocess.check_output(['git','-C',str(repo),'archive',sha]);out=base/'sources/candidate'/name;out.mkdir()
 with tarfile.open(fileobj=io.BytesIO(raw)) as archive:archive.extractall(out,filter='data')
print(json.dumps({'prepared':str(base),'subjects_launched':0}))
'''
    return remote(code,target,data=buffer.getvalue()).decode()


def _case(base, target, number):
    manifest=json.loads((base/'manifest.json').read_text())
    if not 0<=number<12 or manifest['order'][number]['host']!='claude':raise ValueError('Claude subject required')
    for index in range(number):
        prior=json.loads((base/'results'/f'{index:02}.json').read_text())
        if (prior.get('independent_acceptance') or {}).get('verdict')!='ACCEPT':raise ValueError('prior subject not accepted')
    key='-'.join(manifest['order'][number][k] for k in ('host','scenario','condition'))
    local=base/'cases'/key;local.mkdir(parents=True)
    distant=target/'cases'/key
    results={p.name:json.loads(p.read_text()) for p in (base/'results').glob('*.json')}
    remote('''import json,sys
from pathlib import Path
base=Path(sys.argv[1]);rows=json.load(sys.stdin)
for name,row in rows.items():
 if not name.endswith('.json') or '/' in name:raise ValueError('invalid result name')
 (base/'results'/name).write_text(json.dumps(row))
''',target,data=json.dumps(results).encode())
    runner=target/'sources/candidate/clavain/scripts/lean-startup-pilot/runner.py'
    invoke='''import subprocess,sys
subprocess.run([sys.executable,sys.argv[1],'case','--base',sys.argv[2],'--number',sys.argv[3],'--phase',sys.argv[4]],check=True)
'''
    remote(invoke,runner,target,number,'prepare')
    unpack(remote(COLLECT,distant,'prepared'),local)
    # Hashes were observed on zklw and returned over the authenticated connection.
    # Enrollment is durable in the single authoritative Mac DB before launch.
    delivery.before_launch(base,number,local)
    remote('''import sys
from pathlib import Path
p=Path(sys.argv[1]);p.open('xb').write(sys.stdin.buffer.read())
''',distant/'enrollment.json',data=(local/'enrollment.json').read_bytes())
    execution=None
    try:remote(invoke,runner,target,number,'execute')
    except subprocess.CalledProcessError as error:
        execution=error
        (local/'transport-error.stdout').write_bytes(error.stdout or b'')
        (local/'transport-error.stderr').write_bytes(error.stderr or b'')
    try:mapping=unpack(remote(COLLECT,distant,'failed' if execution else 'completed'),local)
    except subprocess.CalledProcessError as error:
        (local/'collection-error.stderr').write_bytes(error.stderr or b'')
        raise
    if execution:raise execution
    result=json.loads((local/'result.json').read_text())
    result['transport']=dict(host=HOST,remote_base=str(target),evidence_paths=mapping)
    delivery.after_run(base,local,result)
    delivery.write(local/'transport-result.json',result)
    delivery.write(base/'results'/f'{number:02}.json',result)
    return result


def case(base,target,number):
    base=base.resolve()
    manifest=json.loads((base/'manifest.json').read_text())
    for name in ('transport.py','delivery.py'):
        if delivery.digest(Path(__file__).with_name(name))!=manifest.get('harness_sha256',{}).get(name):
            raise ValueError('coordinator differs from pinned candidate harness: '+name)
    try:return _case(base,target,number)
    except BaseException as error:
        manifest=json.loads((base/'manifest.json').read_text())
        if isinstance(number,int) and 0<=number<len(manifest.get('order',[])):
            case=manifest['order'][number]
            folder=base/'cases'/'-'.join(case[k] for k in ('host','scenario','condition'))
            delivery.failed(base,folder,error)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['bootstrap','case']);parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--remote-base',type=Path,required=True);parser.add_argument('--number',type=int)
    args=parser.parse_args()
    print(bootstrap(args.base,args.remote_base) if args.operation=='bootstrap' else json.dumps(case(args.base,args.remote_base,args.number)))
