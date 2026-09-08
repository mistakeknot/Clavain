import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'scripts/sync-hermes-adapter.py'


class HermesAdapterSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base/'profile'
        self.home.mkdir()
        self.source = self.make_source('selected install')

    def make_source(self, name):
        source = self.base/name
        adapter = source/'adapters/hermes'
        adapter.mkdir(parents=True)
        (adapter/'plugin.yaml').write_text('name: clavain\nversion: 1.0.0\n')
        (adapter/'__init__.py').write_text('# fixture\n')
        return source

    def run_sync(self, *args, source=None):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), '--source', str(source or self.source),
                               '--home', str(self.home), *args], capture_output=True, text=True)

    def test_absent_section_idempotence_and_read_only_modes(self):
        config = self.home/'config.yaml'
        original = b'# local settings\npersonality: unchanged\n'
        config.write_bytes(original)
        before = config.stat()
        for flag in ('--check', '--dry-run'):
            result = self.run_sync(flag)
            self.assertEqual(result.returncode, 1 if flag == '--check' else 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['current'])
            self.assertEqual(config.read_bytes(), original)
            self.assertFalse((self.home/'plugins').exists())
            self.assertEqual(config.stat().st_mtime_ns, before.st_mtime_ns)
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(config.read_bytes().startswith(original))
        self.assertTrue((self.home/'plugins/clavain').is_symlink())
        installed = config.read_bytes()
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_bytes(), installed)
        self.assertEqual(self.run_sync('--check').returncode, 0)

    def test_existing_block_preserves_others_symlink_mode_and_outer_bytes(self):
        import yaml
        target = self.base/'shared-config.yaml'
        prefix = b'# keep first\npersonality: "same spelling"\n'
        suffix = b'\n# outside plugins\nprovider:\n  token: "fixture-placeholder" # retain format\n'
        target.write_bytes(prefix+b'plugins:\n  enabled: [other, clavain]\n  disabled: [clavain, blocked]\n  custom: {keep: true}\n'+suffix)
        target.chmod(0o640)
        config = self.home/'config.yaml'
        config.symlink_to(target)
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(config.is_symlink())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        content = target.read_bytes()
        self.assertTrue(content.startswith(prefix))
        self.assertTrue(content.endswith(suffix))
        self.assertEqual(yaml.safe_load(content)['plugins'],
                         {'enabled': ['other', 'clavain'], 'disabled': ['blocked'], 'custom': {'keep': True}})

    def test_source_drift_updates_only_managed_link(self):
        self.assertEqual(self.run_sync().returncode, 0)
        old = (self.home/'config.yaml').read_bytes()
        other = self.make_source('new install')
        self.assertEqual(self.run_sync('--check', source=other).returncode, 1)
        result = self.run_sync(source=other)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home/'plugins/clavain').resolve(), (other/'adapters/hermes').resolve())
        self.assertEqual((self.home/'config.yaml').read_bytes(), old)

    def test_malformed_or_unsupported_config_has_no_writes(self):
        for raw in ('plugins: [', 'a: 1\na: 2\n', '- not-a-mapping\n',
                    'plugins: {enabled: []}\n', 'a: &value 1\nb: *value\n',
                    'plugins:\n  enabled: wrong-type\n', 'plugins:\n  enabled: []\n  enabled: []\n'):
            with self.subTest(raw=raw):
                config = self.home/'config.yaml'
                config.write_text(raw)
                result = self.run_sync()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(config.read_text(), raw)
                self.assertFalse((self.home/'plugins').exists())

    def test_unmanaged_directory_is_not_replaced(self):
        target = self.home/'plugins/clavain'
        target.mkdir(parents=True)
        (target/'local.txt').write_text('keep')
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((target/'local.txt').read_text(), 'keep')
        self.assertFalse((self.home/'config.yaml').exists())

    def test_yaml_boundaries_without_final_newline_and_document_markers(self):
        import yaml
        for original in ('plugins:\n  enabled: []', '\ufeffplugins:\n  enabled: []',
                         '---\r\npersonality: same\r\n...\r\n',
                         'plugins:\r\n  enabled: []\r\n# trailing comment\r\n'):
            with self.subTest(original=original):
                config = self.home/'config.yaml'
                config.write_bytes(original.encode())
                result = self.run_sync()
                self.assertEqual(result.returncode, 0, result.stderr)
                content = config.read_bytes()
                self.assertEqual(yaml.safe_load(content)['plugins']['enabled'], ['clavain'])
                if original.startswith('\ufeff'):
                    self.assertTrue(content.startswith(b'\xef\xbb\xbf'))
                if '\r\n' in original:
                    self.assertNotIn(b'\n', content.replace(b'\r\n', b''))
                if 'trailing comment' in original:
                    self.assertTrue(content.endswith(b'# trailing comment\r\n'))
                self.assertEqual(self.run_sync('--check').returncode, 0)

    def test_concurrent_edit_is_refused_before_mutation(self):
        spec = importlib.util.spec_from_file_location('hermes_sync', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = self.home/'config.yaml'
        config.write_text('personality: before\n')
        plan = module.prepare(self.source, self.home)
        config.write_text('personality: concurrent\n')
        with self.assertRaisesRegex(ValueError, 'changed during'):
            module.apply(plan)
        self.assertEqual(config.read_text(), 'personality: concurrent\n')
        self.assertFalse((self.home/'plugins').exists())


if __name__ == '__main__':
    unittest.main()
