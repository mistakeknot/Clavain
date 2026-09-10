"""Prepare the new correctness cohort from reviewed committed candidate sources.

This does not launch models, install packages, or touch the original comparison.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

import delivery
import runner


def source(repo, sha, output):
    actual=subprocess.check_output(['git','-C',str(repo),'rev-parse',sha+'^{commit}'],text=True).strip()
    if actual != sha or len(sha) != 40: raise ValueError('full source commit required')
    raw=subprocess.check_output(['git','-C',str(repo),'archive',sha])
    output.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive: archive.extractall(output,filter='data')
    return dict(sha=sha,archive_sha256=hashlib.sha256(raw).hexdigest(),repo=str(repo.resolve()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('base','clavain-repo','intertest-repo','frozen-evidence','delivery-script','db'):
        parser.add_argument('--'+flag,type=Path,required=True)
    for flag in ('clavain-sha','intertest-sha','parent-session-id','cohort-id'):
        parser.add_argument('--'+flag,required=True)
    args=parser.parse_args()
    args.base=args.base.resolve()
    if not args.db.is_file(): raise ValueError('existing authoritative Intercore DB required')
    if args.base.exists(): raise ValueError('new cohort directory required')
    if args.base.resolve().is_relative_to(args.frozen_evidence.resolve()): raise ValueError('cannot write into frozen comparison')
    args.base.mkdir(mode=0o700,parents=True)
    (args.base/'results').mkdir()
    pins={}; snapshots={}
    for name,repo,sha in [('clavain',args.clavain_repo,args.clavain_sha),('intertest',args.intertest_repo,args.intertest_sha)]:
        snapshots[name]=source(repo,sha,args.base/'sources/candidate'/name);pins[name]=sha
    # Reuse the observed specialist catalog and baseline global content. The
    # candidate's sync-agent-instructions renderer updates its managed block.
    shutil.copytree(args.frozen_evidence/'catalog',args.base/'catalog')
    shutil.copyfile(args.frozen_evidence/'catalog.json',args.base/'catalog.json')
    shutil.copyfile(args.frozen_evidence/'sources/candidate/global-AGENTS.md',args.base/'sources/candidate/global-AGENTS.md')
    old=json.loads((args.frozen_evidence/'manifest.json').read_text())
    pins['dotfiles']=old['pins']['candidate']['dotfiles']
    manifest=dict(schema_version=1,cohort_id=args.cohort_id,cohort_kind='correctness',subject_limit=12,
        pins={'candidate':pins},snapshots=snapshots,
        order=[dict(host=host,scenario=scenario,condition='candidate') for host in ('codex','claude') for scenario in runner.SCENARIOS],
        model_effort={'codex':['gpt-6-astra','high'],'claude':['claude-fable-5-1','high']},
        original_comparison=str(args.frozen_evidence),original_manifest_sha256=delivery.digest(args.frozen_evidence/'manifest.json'),
        efficiency='inconclusive; correctness-only cohort',requires_completed_native_compaction=True)
    harness=args.base/'sources/candidate/clavain/scripts/lean-startup-pilot'
    names=('runner.py','delivery.py','compaction.py','transport.py')
    manifest['harness_sha256']={name:delivery.digest(harness/name) for name in names}
    delivery.write(args.base/'manifest.json',manifest)
    delivery.write(args.base/'delivery-config.json',dict(script=str(args.delivery_script.resolve()),
        script_sha256=delivery.digest(args.delivery_script),db=str(args.db.resolve()),parent_session_id=args.parent_session_id))
    for name in names:
        shutil.copyfile(harness/name,args.base/name)
    print(json.dumps({'prepared':str(args.base),'subjects_launched':0,'manifest_sha256':delivery.digest(args.base/'manifest.json')}))


if __name__=='__main__': main()
