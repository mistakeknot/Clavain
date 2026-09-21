"""Remote authority must not turn missing local state into permission to act."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SharedStateAuthorityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.log = self.home / 'calls'
        fake = self.bin / 'ic'
        fake.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$HOME/calls"\n'
                        'if [[ "$1" == state && "$2" == get ]]; then\n'
                        '  printf "%s" "${FAKE_STATE_VALUE:-}"; exit "${FAKE_STATE_EXIT:-2}"\n'
                        'elif [[ "$1" == state && "$2" == set ]]; then exit "${FAKE_WRITE_EXIT:-2}"\n'
                        'fi\nexit 2\n')
        fake.chmod(0o700)
        self.env = {'HOME': str(self.home), 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                    'CLAUDE_PLUGIN_ROOT': str(ROOT), 'CLAVAIN_SELF_DISPATCH': 'true', 'CLAVAIN_DISPATCH_CAP':'5'}
        bd=self.bin/'bd';bd.write_text('#!/bin/bash\necho bd >> "$HOME/calls"\nexit 2\n');bd.chmod(0o700)

    def remote(self):
        marker = self.home / '.config/clavain/remote-shared-state'
        marker.parent.mkdir(parents=True)
        marker.touch()

    def shell(self, code):
        return subprocess.run(['bash', '-c', code], env=self.env, cwd=self.home,
                              capture_output=True, text=True, timeout=4)

    def source(self, name):
        return 'source "' + str(ROOT / 'hooks' / name) + '"; '

    def test_remote_authority_overrides_cached_binary(self):
        self.remote()
        r = self.shell(self.source('lib-intercore.sh') +
                       'INTERCORE_BIN="$HOME/bin/ic"; intercore_available')
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_remote_sentinel_never_allows_action(self):
        self.remote()
        r = self.shell(self.source('lib-intercore.sh') +
                       'INTERCORE_BIN="$HOME/bin/ic"; intercore_sentinel_check_or_legacy stop test 0')
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_real_stop_hook_skips_state_and_actions(self):
        self.remote()
        transcript = self.home / 'transcript.jsonl'
        transcript.write_text(json.dumps({'type':'assistant','message':{'content':'Goal completed. bead closed.'}})+'\n')
        r = subprocess.run(['bash', str(ROOT / 'hooks/auto-stop-actions.sh')],
                           input=json.dumps({'session_id':'fixture','transcript_path':str(transcript)}),
                           env=self.env, cwd=self.home, capture_output=True, text=True, timeout=4)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '')
        self.assertFalse(self.log.exists())
        self.assertFalse((self.home / '.clavain/intercore.db').exists())

    def test_session_end_does_not_create_handoff(self):
        self.remote()
        r = subprocess.run(['bash', str(ROOT / 'hooks/session-end-handoff.sh')],
                           input='{"session_id":"fixture"}', env=self.env, cwd=self.home,
                           capture_output=True, text=True, timeout=4)
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.home / 'docs').exists())
        self.assertFalse(self.log.exists())

    def counter(self, function, exit_code, value=''):
        self.env.update(FAKE_STATE_EXIT=str(exit_code), FAKE_STATE_VALUE=value)
        return self.shell(self.source('lib-dispatch.sh') +
                          'INTERCORE_BIN="$HOME/bin/ic"; ' + function + ' fixture')

    def test_unknown_counter_blocks_dispatch(self):
        for name in ['dispatch_cap_check', 'dispatch_circuit_check']:
            with self.subTest(name=name):
                self.assertNotEqual(self.counter(name, 2).returncode, 0)

    def test_absent_counter_allows_first_dispatch(self):
        for name in ['dispatch_cap_check', 'dispatch_circuit_check']:
            with self.subTest(name=name):
                self.assertEqual(self.counter(name, 1).returncode, 0)

    def test_corrupt_counter_is_unknown(self):
        for value in ['', '{}', 'null', 'garbage', '{"count":-1}']:
            with self.subTest(value=value):
                self.assertNotEqual(self.counter('dispatch_cap_check', 0, value).returncode, 0)

    def test_valid_counter_enforces_limit(self):
        self.assertEqual(self.counter('dispatch_cap_check', 0, '{"count":2}').returncode, 0)
        self.assertNotEqual(self.counter('dispatch_cap_check', 0, '{"count":5}').returncode, 0)

    def test_broken_marker_symlink_blocks(self):
        p=self.home/'.config/clavain/remote-shared-state';p.parent.mkdir(parents=True)
        p.symlink_to(self.home/'missing')
        self.assertNotEqual(self.counter('dispatch_cap_check',1).returncode,0)
        self.assertFalse(self.log.exists())

    def test_increment_propagates_write_failure(self):
        for name in ['_dispatch_cap_increment','_dispatch_circuit_increment']:
            with self.subTest(name=name):self.assertNotEqual(self.counter(name,1).returncode,0)
        self.env['FAKE_WRITE_EXIT']='0'
        for name in ['_dispatch_cap_increment','_dispatch_circuit_increment']:
            with self.subTest(name=name):self.assertEqual(self.counter(name,1).returncode,0)

    def test_no_claim_without_counter_write(self):
        self.env.update(FAKE_STATE_EXIT='1',FAKE_WRITE_EXIT='2')
        code=self.source('lib-dispatch.sh')+'''INTERCORE_BIN="$HOME/bin/ic";
            _dispatch_review_pressure() { echo 0; }
            discovery_scan_beads() { echo '[{"id":"fixture","score":1}]'; }
            dispatch_rescore() { echo "$1"; }
            dispatch_log() { :; }
            bead_claim() { echo claim >> "$HOME/claim"; }
            set -e; if dispatch_attempt_claim fixture; then exit 90; fi; echo survived'''
        r=self.shell(code);self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.strip(),'survived');self.assertFalse((self.home/'claim').exists())
        self.env['FAKE_WRITE_EXIT']='0'
        positive=code.replace('set -e; if dispatch_attempt_claim fixture; then exit 90; fi; echo survived',
                              'set -e; dispatch_attempt_claim fixture')
        r=self.shell(positive);self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.strip(),'fixture|1');self.assertTrue((self.home/'claim').exists())

    def test_state_status_preserved_under_errexit(self):
        for expected in [0,1,2]:
            with self.subTest(expected=expected):
                self.env.update(FAKE_STATE_EXIT=str(expected),FAKE_STATE_VALUE='')
                r=self.shell(self.source('lib-intercore.sh')+'INTERCORE_BIN="$HOME/bin/ic"; set -e; rc=0; value=$(intercore_state_get key scope) || rc=$?; echo "$rc"')
                self.assertEqual(r.returncode,0);self.assertEqual(r.stdout.strip(),str(expected))

    def test_remote_gates_and_reads_are_unknown(self):
        self.remote()
        for call in ['intercore_gate_check run','intercore_gate_override run reason',
                     'intercore_dispatch_list_active','intercore_events_tail run',
                     'intercore_events_tail_all','intercore_events_cursor_get consumer']:
            with self.subTest(call=call):
                r=self.shell(self.source('lib-intercore.sh')+call)
                self.assertEqual(r.returncode,2)
        self.assertFalse(self.log.exists())

    def test_remote_calibration_hook_skips_direct_calls(self):
        self.remote()
        r=subprocess.run(['bash',str(ROOT/'hooks/gate-calibration-session-end.sh')],input='{}',
                         env=self.env,cwd=self.home,capture_output=True,text=True,timeout=4)
        self.assertEqual(r.returncode,0);self.assertFalse(self.log.exists())

    def test_remote_sprint_and_rescore_skip_bare_calls(self):
        self.remote()
        for lib,call in [('lib-sprint.sh','sprint_create fixture project'),
                         ('lib-sprint.sh','sprint_escalate_strategic_contradiction fixture lane reason'),
                         ('lib-dispatch.sh',"dispatch_rescore '[{\"id\":\"fixture\",\"score\":1}]'")]:
            with self.subTest(call=call):
                r=self.shell(self.source(lib)+call);self.assertNotEqual(r.returncode,0)
        self.assertFalse(self.log.exists())

    def test_remote_stop_handoff_with_dirty_git(self):
        self.remote()
        subprocess.run(['git','init','--quiet'],cwd=self.home,env=self.env,check=True)
        (self.home/'unfinished.txt').write_text('unfinished work')
        r=subprocess.run(['bash',str(ROOT/'hooks/session-handoff.sh')],input='{"session_id":"fixture"}',
                         env=self.env,cwd=self.home,capture_output=True,text=True,timeout=4)
        self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,'');self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()
