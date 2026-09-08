import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ReasoningFollowups(unittest.TestCase):
    def test_quality_gate_actual_jq_calls_require_both_receipt_fields(self):
        document = (ROOT/'commands/quality-gates.md').read_text()
        verdict = re.search(r'(jq -n --arg s .*?> \.clavain/verdicts/plan-conformance\.json)', document, re.S).group(1)
        outcome = re.search(r'(_ctx=\$\(jq -nc --arg a .*?\)\n)', document, re.S).group(1)
        for model, policy in ((None, None), ('claude-fable-5-1', None),
                              (None, 'a'*64), ('  ', 'a'*64), ('claude-fable-5-1', 'a'*64)):
            with self.subTest(model=model, policy=policy), tempfile.TemporaryDirectory() as td:
                path = Path(td)
                (path/'.clavain/verdicts').mkdir(parents=True)
                env = dict(os.environ, conf_status='CLEAN', conf_findings='0', results_path='results.md',
                           _author='gpt-6-astra', _executor='gpt-5.6-sol', _crit_total='1',
                           _crit_failed='0', _esc='0', _src='normal', CLAVAIN_BEAD_ID='fixture', criteria_path='criteria.md')
                env.pop('VALIDATOR_MODEL', None)
                env.pop('VALIDATOR_POLICY_HASH', None)
                if model is not None:
                    env['VALIDATOR_MODEL'] = model
                if policy is not None:
                    env['VALIDATOR_POLICY_HASH'] = policy
                result = subprocess.run(['bash', '-uc', verdict+'\n'+outcome+'\nprintf "%s" "$_ctx"'],
                                        cwd=path, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                known = bool(model and model.strip() and policy)
                self.assertEqual(json.loads((path/'.clavain/verdicts/plan-conformance.json').read_text())['status'],
                                 'CLEAN' if known else 'UNKNOWN')
                self.assertEqual(json.loads(result.stdout)['pass'], known)

    def test_kimi_narrow_sync_defaults_to_script_install_and_accepts_override(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)/'AGENTS.md'
            target.write_text('Local instructions.\n')
            env = dict(os.environ, KIMI_AGENTS_FILE=str(target))
            cmd = ['bash', str(ROOT/'scripts/install-kimi.sh'), 'sync-instructions', '--dry-run']
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(ROOT/'config/routing.yaml'), result.stdout)
            self.assertEqual(target.read_text(), 'Local instructions.\n')
            alternate = Path(td)/'alternate install'
            alternate.mkdir()
            for name in ('config', 'scripts', '.claude-plugin'):
                (alternate/name).symlink_to(ROOT/name, target_is_directory=True)
            result = subprocess.run(cmd+['--source', str(alternate)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(alternate/'config/routing.yaml'), result.stdout)
            self.assertEqual(target.read_text(), 'Local instructions.\n')


if __name__ == '__main__':
    unittest.main()
