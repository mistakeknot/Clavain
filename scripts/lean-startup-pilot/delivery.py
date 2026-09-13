"""Prospective task-delivery bindings for the separate correctness cohort.

No subject or reviewer identity is inferred from configuration. Native evidence
and the canonical collector decide whether an acceptance record can be written.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def record(base, kind, value):
    config = json.loads((base/'delivery-config.json').read_text())
    script, db = Path(config['script']), Path(config['db'])
    if not db.is_file(): raise ValueError('existing authoritative Intercore DB required')
    if digest(script) != config['script_sha256']: raise ValueError('task-delivery source drift')
    folder = base/'delivery-records'; folder.mkdir(exist_ok=True)
    payload = folder/(kind+'-'+uuid.uuid4().hex+'.json')
    write(payload,value)
    result = subprocess.run([sys.executable,str(script),'--db',str(db),'record','--kind',kind,'--record',str(payload)],capture_output=True,text=True)
    write(payload.with_suffix('.result.json'),dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
    if result.returncode: raise RuntimeError('task-delivery rejected '+kind+': '+result.stderr[-1000:]+result.stdout[-1000:])
    return json.loads(result.stdout)


def capture(folder, profile, sources, command, persist=True):
    native = Path(command[0]).resolve(strict=True)
    files = [p for root in (profile,sources) for p in root.rglob('*')
             if p.is_file() and not p.is_symlink() and p.name not in ('auth.json','.credentials.json')]
    observation = {'executable':str(native),'executable_sha256':digest(native),
        'files':{str(p):digest(p) for p in sorted(files)},
        'scope':'isolated profile and pinned sources before launch; effective configuration remains partial'}
    if persist:write(folder/'prelaunch.json',observation)
    return observation


def before_launch(base, number, folder, profile=None, sources=None, command=None):
    manifest_path = base/'manifest.json'; manifest = json.loads(manifest_path.read_text())
    case = manifest['order'][number]
    if manifest.get('cohort_kind') != 'correctness' or manifest['subject_limit'] != 12:
        raise ValueError('separate 12-subject correctness manifest required')
    if any(row['condition'] != 'candidate' for row in manifest['order']):
        raise ValueError('correctness cohort cannot modify the stopped comparison')
    config = json.loads((base/'delivery-config.json').read_text())
    observation = capture(folder,profile,sources,command) if command else json.loads((folder/'prelaunch.json').read_text())
    value = dict(cohort_id=manifest['cohort_id'],enrollment_id=manifest['cohort_id']+'-'+str(number),
        bead_id='sylveste-z55b',objective=case['host']+' '+case['scenario']+' correctness acceptance',
        enrolled_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),role='deep-execution',
        model=manifest['model_effort'][case['host']][0],parent_session_id=config['parent_session_id'],
        manifest_sha256=digest(manifest_path),implementation_dispatched=False)
    receipt = record(base,'enrollment',value)
    enrollment = dict(value,decision_receipt=receipt,attempt_id=str(uuid.uuid4()),prelaunch=observation,
                      prelaunch_sha256=digest(folder/'prelaunch.json'))
    write(folder/'enrollment.json',enrollment)
    record(base,'execution',dict(cohort_id=value['cohort_id'],enrollment_id=value['enrollment_id'],
        attempt_id=enrollment['attempt_id'],execution_status='started',evidence_refs=[str(folder/'prelaunch.json')]))
    return enrollment


def after_run(base, folder, result):
    enrollment = json.loads((folder/'enrollment.json').read_text())
    host = result['case']['host']; sid = result.get('native_session_id')
    if host == 'codex':
        rollouts = result.get('native_rollouts',[])
        evidence = rollouts[0]['path'] if len(rollouts) == 1 else None
        models = {r['model'] for r in result.get('native_model_contexts',[]) if r.get('model')}
    else:
        # Stream output omits native request/prompt ancestry. Bind the complete
        # persisted session, including compaction/resume, without inventing IDs.
        rollouts = result.get('native_rollouts',[])
        evidence = rollouts[0]['path'] if len(rollouts)==1 else None
        models = set(result.get('observed_models',[]))
    if result.get('transport') and evidence:
        evidence=result['transport']['evidence_paths'].get(evidence,evidence)
    model = next(iter(models)) if len(models)==1 else 'unknown'
    value = dict(cohort_id=enrollment['cohort_id'],enrollment_id=enrollment['enrollment_id'],
        manifest_sha256=enrollment['manifest_sha256'],provider=host,role='deep-execution',model=model,
        session_id=sid,thread_id=sid,attempt_id=enrollment['attempt_id'],
        executable=enrollment['prelaunch']['executable'],executable_sha256=enrollment['prelaunch']['executable_sha256'],
        configuration_sha256=None,configuration_coverage='partial',
        configuration_observation_sha256=enrollment['prelaunch_sha256'],
        evidence_path=evidence,evidence_sha256=digest(evidence) if evidence else None,
        identity_coverage='incomplete',missing_identity_reason='Effective configuration is partial; any absent native identity remains unknown.')
    result['delivery_binding'] = record(base,'binding',value)
    okay = all(r.get('exit_code')==0 for r in result['stages']) and result['fixture_check']['passed']
    if result['case']['scenario']=='resume': okay = okay and result.get('compaction_completed') is True
    terminal=record(base,'execution',dict(cohort_id=enrollment['cohort_id'],enrollment_id=enrollment['enrollment_id'],
        attempt_id=enrollment['attempt_id'],execution_status='completed' if okay else 'failed',
        evidence_refs=[str(folder/'result.json')]))
    write(folder/'terminal-decision.json',terminal)


def failed(base, folder, error):
    if not (folder/'enrollment.json').is_file() or (folder/'terminal-decision.json').exists():return
    enrollment=json.loads((folder/'enrollment.json').read_text())
    evidence=folder/'execution-error.json'
    write(evidence,dict(error=str(error),native_completion='unknown unless separately captured in native evidence'))
    receipt=record(base,'execution',dict(cohort_id=enrollment['cohort_id'],enrollment_id=enrollment['enrollment_id'],
        attempt_id=enrollment['attempt_id'],execution_status='failed',
        evidence_refs=[str(evidence),*[str(p) for p in folder.iterdir() if p.is_file() and p.suffix in ('.stdout','.stderr')]]))
    write(folder/'terminal-decision.json',receipt)


def accept(base, number, reviewer_record, verdict_record):
    result_path = base/'results'/('%02d.json'%number)
    result = json.loads(result_path.read_text())
    if result.get('independent_acceptance'): raise ValueError('existing judgment is immutable')
    case = result['case']; folder=base/'cases'/'-'.join([case['host'],case['scenario'],case['condition']])
    enrollment = json.loads((folder/'enrollment.json').read_text())
    reviewer = json.loads(reviewer_record.read_text()); verdict=json.loads(verdict_record.read_text())
    expected = dict(cohort_id=enrollment['cohort_id'],enrollment_id=enrollment['enrollment_id'])
    if any(reviewer.get(k)!=v or verdict.get(k)!=v for k,v in expected.items()):
        raise ValueError('reviewer or verdict belongs to a different enrollment')
    binding = record(base,'binding',reviewer)
    verdict['reviewer_binding_decision_id'] = binding['id']
    acceptance = record(base,'acceptance',verdict)
    # Only canonical task-delivery acceptance can release the next subject.
    result['independent_acceptance'] = dict(verdict='ACCEPT' if verdict['status']=='accepted' else 'NEEDS_FIX',
        acceptance_decision=acceptance,reviewer_binding=binding,evidence_refs=verdict['evidence_refs'])
    write(result_path,result); write(folder/'result.json',result)
