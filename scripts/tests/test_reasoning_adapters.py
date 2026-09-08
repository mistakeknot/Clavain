import importlib.util
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class ReasoningAdapters(unittest.TestCase):
    def test_all_hosts_sync_idempotently_and_report_drift(self):
        for host in ('codex', 'claude', 'hermes', 'gemini', 'kimi', 'opencode', 'cursor', 'vscode'):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as td:
                target = Path(td) / 'instructions.md'
                target.write_text('Local personality and user choices.\n')
                cmd = ['python3', str(ROOT/'scripts/sync-agent-instructions.py'), '--source', str(ROOT), '--host', host, '--file', str(target)]
                first = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(first.returncode, 0, first.stderr)
                before = target.read_bytes()
                self.assertTrue(before.startswith(b'Local personality and user choices.\n'))
                self.assertIn(b'frontier', before)
                self.assertIn(str(ROOT/'config/routing.yaml').encode(), before)
                self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
                self.assertEqual(before, target.read_bytes())
                doctor = subprocess.run(cmd+['--check'], capture_output=True, text=True)
                receipt = json.loads(doctor.stdout)
                self.assertEqual(doctor.returncode, 0, doctor.stderr)
                self.assertFalse(receipt['behaviorally_verified'])
                target.write_bytes(before.replace(b'frontier', b'cheap', 1))
                self.assertNotEqual(subprocess.run(cmd+['--check'], capture_output=True).returncode, 0)

    def test_hermes_blocks_parent_inheritance(self):
        spec = importlib.util.spec_from_file_location('clavain_hermes', ROOT/'adapters/hermes/__init__.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.before_tool('delegate_task', {})['action'], 'block')
        self.assertIsNone(module.before_tool('read_file', {}))
        context = module.inject_context(model='parent-personality')
        self.assertIn('does not change', context['context'])

    def test_kimi_migrates_legacy_block_without_duplicate_contract(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)/'AGENTS.md'
            target.write_text('Personality\n<!-- BEGIN CLAVAIN KIMI TOOL MAP -->\nold agent inheritance\n<!-- END CLAVAIN KIMI TOOL MAP -->\nLocal rules\n')
            result = subprocess.run(['python3',str(ROOT/'scripts/sync-agent-instructions.py'),'--source',str(ROOT),'--host','kimi','--file',str(target)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('old agent inheritance',target.read_text())
            self.assertTrue(target.read_text().endswith('Local rules\n'))

    def test_standalone_install_with_spaces_and_policy_drift(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/'standalone install'
            for relative in ('config/agent-instructions.md','config/codex-instructions.md','config/host-adapters.json','config/routing.yaml','.claude-plugin/plugin.json','scripts/sync-agent-instructions.py','scripts/sync-codex-instructions.py'):
                (source/relative).parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/relative,source/relative)
            target = Path(td)/'AGENTS.md'
            cmd=['python3',str(source/'scripts/sync-agent-instructions.py'),'--source',str(source),'--host','codex','--file',str(target)]
            result=subprocess.run(cmd,cwd=td,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn("--policy='"+str(source.resolve()),target.read_text())
            self.assertEqual(subprocess.run(cmd+['--check'],capture_output=True).returncode,0)
            policy=source/'config/routing.yaml'
            policy.write_text(policy.read_text()+'\n# new installation revision\n')
            self.assertNotEqual(subprocess.run(cmd+['--check'],capture_output=True).returncode,0)

if __name__ == '__main__': unittest.main()
