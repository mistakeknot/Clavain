import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))


@pytest.fixture
def orc():
    path = Path(__file__).resolve().parents[2] / 'scripts/orchestrate.py'
    spec = importlib.util.spec_from_file_location('pilot_orchestrator', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop(spec.name, None)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path/'repo'
    path.mkdir()
    subprocess.run(['git','init','-q',str(path)],check=True)
    (path/'source').write_text('source\n')
    subprocess.run(['git','-C',str(path),'add','source'],check=True)
    subprocess.run(['git','-C',str(path),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','init'],check=True)
    return path


def run_pipeline(orc, repo, tmp_path, monkeypatch, config, approve=True):
    task = orc.Task('task-1', 'test', 's', verification=config)
    manifest = orc.Manifest(1, 'all-sequential', 'fast', 1, 5, [], {'task-1': task})
    calls = {'executor':0,'repair':0,'review':0}
    def dispatch(*args, **kwargs):
        calls['repair' if 'phase' in kwargs else 'executor'] += 1
        return orc.TaskResult(task_id='task-1',status='pass')
    def review(*args, **kwargs):
        calls['review'] += 1
        return approve, 'reviewed'
    monkeypatch.setattr(orc, 'dispatch_task', dispatch)
    monkeypatch.setattr(orc, 'dispatch_review', review)
    monkeypatch.setenv('CLAVAIN_VERIFICATION_EVIDENCE_DIR',str(tmp_path/'evidence'))
    run_dir = tmp_path/'run'
    (run_dir/'task-1').mkdir(parents=True)
    result = orc.run_task_pipeline(task,manifest,str(repo),None,{},None,{},'unused','pilot',str(run_dir))
    return result,calls


def contract(command='true', **config):
    return {'required':True,'checks':[{'id':'check','run':command,'expect':'exit 0'}],**config}


@pytest.mark.parametrize('config,kind',[
    (contract('sleep 3',timeout=.1),'timeout'),
    (contract('true',prerequisites={'paths':['missing']}),'prerequisite'),
    (contract('python3 -c "print(\'x\'*10000)"',output_limit=1024),'output-limit'),
    (contract('echo changed >> source'),'source-changed'),
])
def test_operational_failure_spawns_no_repair(orc,repo,tmp_path,monkeypatch,config,kind):
    result,calls=run_pipeline(orc,repo,tmp_path,monkeypatch,config)
    assert result.status=='error'
    assert result.verification_failure==kind
    assert calls=={'executor':1,'repair':0,'review':0}


def test_assertion_failure_retains_bounded_repair(orc,repo,tmp_path,monkeypatch):
    result,calls=run_pipeline(orc,repo,tmp_path,monkeypatch,contract('false'))
    assert result.status=='escalated'
    assert calls=={'executor':1,'repair':orc.MAX_FIX_ROUNDS,'review':0}


def test_optional_empty_review_has_no_machine_acceptance(orc,repo,tmp_path,monkeypatch):
    result,calls=run_pipeline(orc,repo,tmp_path,monkeypatch,{'required':False,'checks':[]})
    assert result.status=='pass' and not result.machine_eligible
    assert result.verification_state=='UNVERIFIABLE'
    assert calls=={'executor':1,'repair':0,'review':1}


@pytest.mark.parametrize('config',[
    {'required':True,'checks':[]},None,
    {'checks':[{'run':'true','expect':'invalid'}]},
    {'checks':[],'required':False,'unknown':True},
])
def test_invalid_contract_stops_before_executor(orc,repo,tmp_path,monkeypatch,config):
    result,calls=run_pipeline(orc,repo,tmp_path,monkeypatch,config)
    assert result.status=='error' and not result.machine_eligible
    assert calls=={'executor':0,'repair':0,'review':0}


def test_valid_evidence_still_requires_review(orc,repo,tmp_path,monkeypatch):
    result,calls=run_pipeline(orc,repo,tmp_path,monkeypatch,contract())
    assert result.machine_eligible
    assert calls=={'executor':1,'repair':0,'review':1}


def test_both_legacy_false_passes_fixed(orc,repo):
    first,_=orc.run_verify_entries([{'run':'echo expected; exit 7','expect':'contains "expected"'}],str(repo))
    second,_=orc.run_verify_entries([{'run':'true','expect':'malformed'}],str(repo))
    assert not first and not second


@pytest.mark.parametrize('body',[
    '## Task 1: X\n<verify>\n- run: `true`\n</verify>',
    '## Task 1: X\n<verify>\n- run: `true`\n  expect: exit 0\n  extra: bad\n</verify>',
])
def test_plan_does_not_partially_parse(orc,tmp_path,body):
    plan=tmp_path/'plan.md'
    plan.write_text(body)
    info=orc.parse_plan_tasks(str(plan))[1]
    with pytest.raises(ValueError):
        orc._task_verification(orc.Task('task-1','x','s'), info)


def test_duplicate_plan_task_rejected(orc,tmp_path):
    plan=tmp_path/'plan.md'
    plan.write_text('## Task 1: X\n## Task 1: Y\n')
    with pytest.raises(ValueError):
        orc.parse_plan_tasks(str(plan))


def test_duplicate_manifest_field_rejected(orc,tmp_path):
    manifest=tmp_path/'m.yaml'
    manifest.write_text('version: 1\nversion: 2\nstages: []\n')
    with pytest.raises(ValueError):
        orc.load_manifest(manifest)


def test_manifest_preserves_verification(orc,tmp_path):
    manifest=tmp_path/'m.yaml'
    manifest.write_text('version: 1\nstages:\n  - name: s\n    tasks:\n      - id: task-1\n        title: test\n        verification:\n          required: false\n          checks: []\n')
    assert orc.load_manifest(manifest).tasks['task-1'].verification=={'required':False,'checks':[]}


def test_cli_validate_rejects_invalid_verification(tmp_path):
    manifest = tmp_path / 'invalid.yaml'
    manifest.write_text('version: 1\nstages:\n  - name: s\n    tasks:\n      - id: task-1\n        title: test\n        verification:\n          required: true\n          checks: []\n')
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[2] / 'scripts/orchestrate.py'),
                             '--validate', str(manifest)], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'required' in result.stdout


def test_cli_validate_preserves_graph_errors_and_names_task(tmp_path):
    manifest = tmp_path / 'invalid.yaml'
    manifest.write_text('version: 1\nstages:\n  - name: s\n    tasks:\n      - id: task-1\n        title: test\n        depends: [missing-task]\n        verification:\n          required: true\n          checks: []\n')
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[2] / 'scripts/orchestrate.py'),
                             '--validate', str(manifest)], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'missing-task' in result.stdout and 'task-1: UNVERIFIABLE' in result.stdout


def test_journal_preserves_machine_evidence(orc, repo, tmp_path):
    result = orc.TaskResult('task-1', 'pass', verification_state='VERIFIED',
        verification_receipt='/private/evidence/receipt.json', machine_eligible=True)
    entry = orc._journal_task_entry(str(tmp_path), str(repo), result)
    assert entry['verification_state'] == 'VERIFIED'
    assert entry['verification_receipt'] == result.verification_receipt
    assert entry['machine_eligible'] is True


@pytest.mark.parametrize('environment,message', [
    ({'CI': '1'}, 'source SHA is required'),
    ({'CI': 'true'}, 'source SHA is required'),
    ({'CI_SOURCE_SHA': '0'*40}, 'wrong CI source SHA'),
    ({}, 'contract differs'),
])
def test_ci_guards_classify_unavailable(repo, environment, message):
    (repo / 'tests').mkdir()
    (repo / 'tests/verification-pilot.json').write_text('{}')
    env = {k: v for k, v in os.environ.items() if k not in {'CI', 'CI_SOURCE_SHA'}}
    env.update(environment)
    recipe = Path(__file__).resolve().parents[2] / 'scripts/ci-verification.sh'
    result = subprocess.run(['bash', str(recipe)], cwd=repo, env=env, capture_output=True, text=True)
    assert result.returncode == 2
    assert message in result.stderr


def test_persistence_failure_never_repairs(orc,repo,tmp_path,monkeypatch):
    import verification_runner
    def fail(*args,**kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(verification_runner.Evidence,'receipt',fail)
    result,calls=run_pipeline(orc,repo,tmp_path,monkeypatch,contract())
    assert result.status=='error' and not result.machine_eligible
    assert calls=={'executor':1,'repair':0,'review':0}


def test_cancellation_never_repairs(orc,repo,tmp_path,monkeypatch):
    import threading
    import verification_runner
    cancel=threading.Event()
    cancel.set()
    original=orc.verify_contract
    def cancelled(*args,**kwargs):
        return original(*args,**kwargs,cancel=cancel)
    monkeypatch.setattr(orc,'verify_contract',cancelled)
    result,calls=run_pipeline(orc,repo,tmp_path,monkeypatch,contract('sleep 3'))
    assert result.status=='error' and result.verification_failure=='cancelled'
    assert calls=={'executor':1,'repair':0,'review':0}
