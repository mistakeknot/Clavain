import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "flere-worker.py"

FAKE = '''#!/usr/bin/env python3
import hashlib,json,os,pathlib,subprocess,sys,time
args=dict(zip(sys.argv[2::2],sys.argv[3::2]))
session=args['--session-id']; directory=pathlib.Path(args['--session-dir']).resolve(); directory.mkdir()
file=directory/'native.jsonl'; entries=[]; scenario=''; prompt=''; settled=False
for line in sys.stdin:
 c=json.loads(line); kind=c['type']; data=None; ok=True
 if kind=='get_state':
  data={'sessionId':session,'sessionFile':str(file),'model':{'provider':args['--provider'],'id':args['--model']},'isStreaming':False,'isCompacting':False,'pendingMessageCount':0,'worker':{'profile':'read-only-v1','activeTools':['read','grep','find','ls'],'singlePrompt':True,'autoRetryEnabled':False,'providerMaxRetries':0,'sandboxEffective':'tool-policy-read-only','enforcement':'application-level-canonical-root','canonicalRoots':[os.getcwd()],'executable':os.path.realpath(__file__),'executableSha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'profileDir':args['--profile-dir'],'profileSha256':hashlib.sha256((pathlib.Path(args['--profile-dir'])/'models.json').read_bytes()).hexdigest(),'runtimeVersion':'fixture','sessionDir':str(directory)}}
 if kind=='get_entries': data={'entries':entries,'leafId':'assistant'}
 if kind=='get_entries' and scenario=='null_entries': data=None
 if kind=='get_entries' and scenario=='malformed_content': data['entries'][-1]['message']['content']='not a content array'
 if kind=='get_session_stats': data={'sessionId':session,'tokens':{'input':10,'output':3,'cacheRead':2,'cacheWrite':0},'cost':0.0}
 if kind=='get_session_stats' and scenario=='null_stats': data=None
 if kind=='prompt':
  prompt=c['message']; scenario=prompt.split()[0]
  if scenario=='before_ack_death': sys.exit(1)
  if scenario=='reject': ok=False
  if scenario=='malformed': print('invalid',flush=True); continue
 print(json.dumps({'type':'response','command':kind,'id':c['id'],'success':ok,'data':data,'error':'rejected' if not ok else None}),flush=True)
 if kind=='prompt' and ok:
  if scenario=='descendant':
   descendant=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
   (directory.parent/'descendant.pid').write_text(str(descendant.pid)); sys.exit(1)
  if scenario=='after_ack_death': sys.exit(1)
  if scenario=='hang': continue
  if scenario=='ui': print(json.dumps({'type':'extension_ui_request','method':'confirm','id':'ui'}),flush=True); continue
  if scenario=='settled_only': print(json.dumps({'type':'agent_settled'}),flush=True); continue
  entries=[{'type':'message','id':'user','message':{'role':'user','content':[{'type':'text','text':prompt}]}},{'type':'message','id':'assistant','parentId':'user','message':{'role':'assistant','provider':args['--provider'],'model':args['--model'],'stopReason':'error' if scenario=='error' else 'stop','content':[{'type':'text','text':'Inspected.'}],'usage':{'input':10,'output':3,'cacheRead':2,'cacheWrite':0}}}]
  file.write_text(json.dumps({'type':'session','id':session})+'\\n'+'\\n'.join(map(json.dumps,entries))+'\\n')
  print(json.dumps({'type':'agent_settled'}),flush=True)
'''

class FlereWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"; self.project.mkdir()
        self.profile = self.root / "profile"; self.profile.mkdir()
        (self.profile / "models.json").write_text('{}')
        self.child = self.root / "child.py"; self.child.write_text(FAKE); self.child.chmod(0o700)
        self.output = self.root / "out.md"

    def run_worker(self, scenario):
        prompt = self.root / "prompt"; prompt.write_text(scenario + "\nmultiline input")
        env = {**os.environ, 'IC_DISPATCH_ID':'dispatch1','IC_RUN_ID':'run1','IC_DISPATCH_ATTEMPT':'0','IC_PROMPT_HASH':hashlib.sha256(prompt.read_bytes()).hexdigest()[:16]}
        return subprocess.run([sys.executable,str(SCRIPT),'--executable',str(self.child),'--profile',str(self.profile),'--model','fixture/model/slash','--project',str(self.project),'--prompt-file',str(prompt),'--output',str(self.output),'--timeout','1'],env=env,text=True,capture_output=True,timeout=8)

    def receipt(self): return json.loads(Path(str(self.output)+'.receipt.json').read_text())

    def test_native_terminal_proof_and_identity(self):
        result = self.run_worker('success')
        self.assertEqual(result.returncode,0,result.stderr)
        receipt = self.receipt()
        self.assertEqual(receipt['dispatch_id'],'dispatch1')
        self.assertEqual(receipt['model'],'model/slash')
        self.assertEqual(receipt['outcome'],'success')
        self.assertEqual(receipt['final_assistant_entry_id'],'assistant')
        self.assertEqual(receipt['usage']['input'],10)
        self.assertFalse(receipt['independent_acceptance'])
        self.assertEqual(receipt['usage_semantics'],'fresh_session_cumulative')
        self.assertTrue(Path(receipt['artifacts']['started']['path']).exists())
        self.assertNotEqual(self.run_worker('success').returncode,0)

    def test_no_output_or_quiescence_can_prove_success(self):
        for scenario in ['before_ack_death','after_ack_death','settled_only','malformed','hang','ui','error','reject','null_entries','null_stats','malformed_content']:
            with self.subTest(scenario=scenario):
                self.output=self.root/(scenario+'.md')
                result=self.run_worker(scenario)
                self.assertNotEqual(result.returncode,0,result.stderr)
                receipt=self.receipt()
                self.assertNotEqual(receipt['outcome'],'success')
                self.assertFalse(receipt['retry_allowed'])
                if scenario == 'error':
                    self.assertEqual(receipt['usage']['input'], 10)
                    self.assertEqual(receipt['measurement_coverage'], 'complete')
                if scenario in ['before_ack_death','after_ack_death','settled_only','malformed','hang','null_entries','null_stats','malformed_content']:
                    self.assertEqual(receipt['failure_class'],'worker_outcome_indeterminate')

    def test_identity_and_reply_shapes_are_checked_before_prompt(self):
        for index, replacement in enumerate([
            ("'singlePrompt':True", "'singlePrompt':1"),
            ("'sessionId':session", "'sessionId':'different'"),
            ("'success':ok", "'success':'true'"),
            ("'id':c['id']", "'id':'uncorrelated'"),
        ]):
            with self.subTest(replacement=replacement):
                self.output=self.root/('mismatch'+str(index)+'.md')
                self.child.write_text(FAKE.replace(*replacement))
                result=self.run_worker('success')
                self.assertNotEqual(result.returncode,0,result.stderr)
                self.assertFalse(self.receipt()['prompt_accepted'])

    def test_cancellation_retains_receipt_and_terminates_worker(self):
        def cancel_worker(argv, **kwargs):
            kwargs.pop('timeout')
            kwargs.pop('capture_output')
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
            events=Path(str(self.output)+'.attempt/rpc.jsonl')
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if events.exists() and '"command": "prompt"' in events.read_text(): break
                time.sleep(.01)
            else:
                process.kill();process.communicate();self.fail('worker never acknowledged prompt')
            process.send_signal(signal.SIGTERM)
            stdout,stderr=process.communicate(timeout=3)
            return subprocess.CompletedProcess(argv,process.returncode,stdout,stderr)
        from unittest.mock import patch
        with patch('subprocess.run', cancel_worker):
            result=self.run_worker('hang')
        self.assertNotEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.receipt()['failure_class'],'worker_outcome_indeterminate')
        self.assertTrue(self.receipt()['prompt_accepted'])

    def test_process_group_cleanup_survives_leader_death(self):
        result=self.run_worker('descendant')
        self.assertNotEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.receipt()['failure_class'],'worker_outcome_indeterminate')
        pid=int(Path(str(self.output)+'.attempt/descendant.pid').read_text())
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            try: os.kill(pid,0)
            except ProcessLookupError: break
            time.sleep(.01)
        else: self.fail('worker descendant survived owned process-group cleanup')

if __name__ == '__main__': unittest.main()
