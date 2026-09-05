"""Exercise the public narrow action without touching a real Codex home."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
START = b'<!-- BEGIN CLAVAIN CODEX TOOL MAP -->'
END = b'<!-- END CLAVAIN CODEX TOOL MAP -->'


class SyncInstructionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'codex'
        self.home.mkdir()
        self.file = self.home / 'AGENTS.md'
        self.before = b'operator policy\r\n' + START + b'\nold map\n' + END + b'\nkeep tail without newline'
        self.file.write_bytes(self.before)
        (self.home / 'config.toml').write_text('# must remain untouched\n')
        (self.home / 'hooks.json').write_text('{"operator":true}\n')

    def run_sync(self, *args, shell='bash'):
        return subprocess.run([shell, str(ROOT / 'scripts/install-codex.sh'),
                               'sync-instructions', '--source', str(ROOT),
                               '--codex-home', str(self.home), *args],
                              capture_output=True, text=True, timeout=10)

    def test_system_bash_supports_apply_and_dry_run(self):
        # macOS still ships Bash 3.2, whose nounset handling differs for empty arrays.
        for args in [('--dry-run',), ()]:
            result = self.run_sync(*args, shell='/bin/bash')
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'Synthesize', self.file.read_bytes())

    def test_preserves_unmanaged_bytes_and_configuration_idempotently(self):
        before = {p.name: p.read_bytes() for p in self.home.iterdir()}
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.file.read_bytes()
        self.assertTrue(after.startswith(b'operator policy\r\n'))
        self.assertTrue(after.endswith(b'\nkeep tail without newline'))
        self.assertIn(b'Synthesize', after)
        self.assertEqual(set(before), {p.name for p in self.home.iterdir()})
        for name in ['config.toml', 'hooks.json']:
            self.assertEqual(before[name], (self.home / name).read_bytes())
        stamp = self.file.stat().st_mtime_ns
        self.assertEqual(self.run_sync().returncode, 0)
        self.assertEqual(self.file.stat().st_mtime_ns, stamp)
        self.assertEqual(self.run_sync('--dry-run').stdout, '')

    def test_dry_run_has_no_side_effects(self):
        stamp = self.file.stat().st_mtime_ns
        result = self.run_sync('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Synthesize', result.stdout)
        self.assertEqual(self.file.read_bytes(), self.before)
        self.assertEqual(self.file.stat().st_mtime_ns, stamp)
        self.assertEqual(len(list(self.home.iterdir())), 3)

    def test_non_utf8_unmanaged_bytes_survive_dry_run_and_apply(self):
        self.file.write_bytes(b'operator \xff\xfe\n' + self.before)
        self.assertEqual(self.run_sync('--dry-run').returncode, 0)
        self.assertEqual(self.run_sync().returncode, 0)
        self.assertTrue(self.file.read_bytes().startswith(b'operator \xff\xfe\n'))

    def test_missing_target_directory_is_not_created(self):
        self.home = self.root / 'mistyped' / 'codex'
        for args in [('--dry-run',), ()]:
            result = self.run_sync(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('directory must already exist', result.stderr)
            self.assertFalse(self.home.parent.exists())

    def test_relative_symlink_and_target_mode_survive(self):
        target = self.root / 'dotfiles.md'
        self.file.rename(target)
        target.chmod(0o640)
        self.file.symlink_to('../dotfiles.md')
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.file), '../dotfiles.md')
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertIn(b'Synthesize', target.read_bytes())

    def test_malformed_duplicate_and_reversed_markers_fail_without_writing(self):
        for value in [START, END, END + START, START + START + END, self.before + START + END]:
            with self.subTest(value=value):
                self.file.write_bytes(value)
                result = self.run_sync()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.file.read_bytes(), value)

    def test_appends_once_without_changing_existing_bytes(self):
        self.file.write_bytes(b'unmanaged no newline')
        self.assertEqual(self.run_sync().returncode, 0)
        self.assertTrue(self.file.read_bytes().startswith(b'unmanaged no newline\n\n'))
        self.assertEqual(self.file.read_bytes().count(START), 1)

    def test_dangling_symlink_fails_without_creating_target(self):
        self.file.unlink()
        self.file.symlink_to('../missing.md')
        self.assertNotEqual(self.run_sync().returncode, 0)
        self.assertTrue(self.file.is_symlink())
        self.assertFalse((self.root / 'missing.md').exists())

    def test_requires_explicit_source_and_rejects_broad_install_flags(self):
        result = subprocess.run(['bash', str(ROOT / 'scripts/install-codex.sh'),
                                 'sync-instructions', '--codex-home', str(self.home)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        for option in ['--no-prompts', '--remove-clone', '--json', '--repo-url=https://example.invalid']:
            self.assertNotEqual(self.run_sync(option).returncode, 0)
        self.assertEqual(self.file.read_bytes(), self.before)


if __name__ == '__main__':
    unittest.main()
