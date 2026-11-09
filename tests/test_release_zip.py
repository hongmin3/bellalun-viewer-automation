"""설치 릴리즈 ZIP의 무결성·최소 포함 파일·실패 안전성 계약."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/release_zip.py'


def load_tool():
    spec = importlib.util.spec_from_file_location('release_zip', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / 'release/1.0.3'
        self.release.mkdir(parents=True)
        self.output = self.root / 'installer.zip'
        self.exe = 'BellalunAuto-1.0.3-candidate-setup.exe'
        self.info = {
            'schema_version': 1, 'version': '1.0.3',
            'application': {'path': 'BellalunAuto.exe', 'sha256': 'a' * 64},
            'release_gate': {'status': 'candidate', 'passed': False},
        }
        (self.release / self.exe).write_bytes(b'MZ installer fixture')
        (self.release / '게이트-미통과-후보.txt').write_text('UI 미검증 후보\n', encoding='utf-8')
        self.write_info()

    def write_info(self):
        (self.release / 'build-info.json').write_text(json.dumps(self.info), encoding='utf-8')
        self.manifest()

    def manifest(self, names=None):
        names = names or [self.exe, 'build-info.json']
        text = ''.join(hashlib.sha256((self.release / n).read_bytes()).hexdigest() + '  ' + n + '\n'
                       for n in names)
        (self.release / 'SHA256SUMS.txt').write_text(text, encoding='utf-8')

    def create(self):
        return load_tool().create_release_zip(self.release, self.output)

    def assert_rejected(self):
        with self.assertRaises((ValueError, OSError)):
            self.create()
        self.assertFalse(self.output.exists())
        self.assertEqual([], list(self.root.glob('.*.tmp')))

    def test_candidate_zip_is_installable_bundle_with_exact_hash_inventory(self):
        result = self.create()
        self.assertEqual('1.0.3', result['version'])
        self.assertTrue(result['candidate'])
        self.assertEqual('a' * 64, result['application_sha256'])
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), result['sha256'])
        with zipfile.ZipFile(self.output) as archive:
            self.assertIsNone(archive.testzip())
            expected = {self.exe, 'build-info.json', '게이트-미통과-후보.txt', '사용안내.txt', 'SHA256SUMS.txt'}
            self.assertEqual(expected, set(archive.namelist()))
            self.assertEqual(sorted(expected), result['entries'])
            self.assertTrue(all(i.compress_type == zipfile.ZIP_DEFLATED for i in archive.infolist()))
            rows = archive.read('SHA256SUMS.txt').decode('utf-8').splitlines()
            hashes = dict((name, digest) for digest, name in (line.split('  ', 1) for line in rows))
            self.assertEqual(expected - {'SHA256SUMS.txt'}, set(hashes))
            for name, digest in hashes.items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
            guide = archive.read('사용안내.txt').decode('utf-8')
            for phrase in ('Setup', '기존 설정', 'UI', '후보', '공개 업로드 금지'):
                self.assertIn(phrase, guide)

    def test_formal_zip_has_no_candidate_marker(self):
        (self.release / '게이트-미통과-후보.txt').unlink()
        old = self.release / self.exe
        self.exe = 'BellalunAuto-1.0.3-setup.exe'
        old.rename(self.release / self.exe)
        self.info['release_gate'] = {'status': 'passed', 'passed': True}
        self.write_info()
        self.assertFalse(self.create()['candidate'])
        with zipfile.ZipFile(self.output) as archive:
            self.assertNotIn('게이트-미통과-후보.txt', archive.namelist())

    def test_tampered_input_hash_is_rejected(self):
        (self.release / self.exe).write_bytes(b'tampered')
        self.assert_rejected()

    def test_manifest_must_cover_installer_and_build_info(self):
        self.manifest([self.exe])
        self.assert_rejected()

    def test_manifest_traversal_absolute_duplicates_and_unknown_entries_are_rejected(self):
        original = (self.release / 'SHA256SUMS.txt').read_text()
        for name in ('../secret', '/etc/config', 'C:/secret', 'folder\\secret', 'build-info.json', 'config.json'):
            with self.subTest(name=name):
                (self.release / 'SHA256SUMS.txt').write_text(original + 'a' * 64 + '  ' + name + '\n')
                self.assert_rejected()

    def test_unexpected_sensitive_files_and_directories_are_rejected(self):
        for name in ('config.json', 'patient.dcm', 'run.log', 'RELEASE-NOTES.txt', 'verification.json'):
            with self.subTest(name=name):
                path = self.release / name
                path.write_text('private')
                self.assert_rejected()
                path.unlink()
        (self.release / 'logs').mkdir()
        self.assert_rejected()

    def test_missing_files_and_candidate_marker_are_rejected(self):
        for name in (self.exe, 'build-info.json', 'SHA256SUMS.txt', '게이트-미통과-후보.txt'):
            with self.subTest(name=name):
                path = self.release / name
                content = path.read_bytes()
                path.unlink()
                self.assert_rejected()
                path.write_bytes(content)

    def test_gate_version_application_hash_and_filename_mismatch_are_rejected(self):
        cases = [({'version': '../1.0.3'},), ({'version': '1.0.4'},),
                 ({'application': {'path': '../app.exe', 'sha256': 'a' * 64}},),
                 ({'application': {'path': 'BellalunAuto.exe', 'sha256': 'invalid'}},),
                 ({'release_gate': {'status': 'passed', 'passed': False}},),
                 ({'release_gate': {'status': 'candidate', 'passed': 0}},)]
        original = self.info.copy()
        for (changes,) in cases:
            with self.subTest(changes=changes):
                self.info = {**original, **changes}
                self.write_info()
                self.assert_rejected()

    def test_candidate_marker_is_hashed_when_present_in_input_manifest(self):
        self.manifest([self.exe, 'build-info.json', '게이트-미통과-후보.txt'])
        (self.release / '게이트-미통과-후보.txt').write_text('changed')
        self.assert_rejected()

    def test_output_normalized_inside_release_is_rejected(self):
        (self.root / 'other').mkdir()
        self.output = self.root / 'other/../release/1.0.3/bundle.zip'
        self.assert_rejected()

    def test_zip_is_reproducible_for_same_release(self):
        first = self.create()
        original = self.output.read_bytes()
        self.output = self.root / 'second.zip'
        second = self.create()
        self.assertEqual(original, self.output.read_bytes())
        self.assertEqual(first['sha256'], second['sha256'])

    def test_setup_filename_must_agree_with_candidate_state(self):
        original = self.release / self.exe
        self.exe = 'BellalunAuto-1.0.3-setup.exe'
        original.rename(self.release / self.exe)
        self.manifest()
        self.assert_rejected()

    def test_existing_output_is_never_overwritten(self):
        self.output.write_bytes(b'existing')
        with self.assertRaises((ValueError, OSError)):
            self.create()
        self.assertEqual(b'existing', self.output.read_bytes())

    def test_hardlinks_are_rejected(self):
        import os
        target = self.release / self.exe
        alias = self.root / 'alias.exe'
        os.link(target, alias)
        self.assert_rejected()

    def test_symlink_and_linked_parent_are_rejected_when_supported(self):
        link = self.root / 'linked'
        try:
            link.symlink_to(self.release, target_is_directory=True)
        except OSError as error:
            self.skipTest(f'심볼릭 링크 권한 없음: {error}')
        with self.assertRaises(ValueError):
            load_tool().create_release_zip(link, self.output)
        self.assertFalse(self.output.exists())

    def test_zip_validation_failure_cleans_temporary_output(self):
        module = load_tool()
        with patch.object(zipfile.ZipFile, 'testzip', return_value=self.exe):
            with self.assertRaises(ValueError):
                module.create_release_zip(self.release, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual([], list(self.root.glob('.*.tmp')))

    def test_cli_creates_zip_and_reports_json(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), '--release', str(self.release),
                               '--output', str(self.output)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)['candidate'])
        proc = subprocess.run([sys.executable, str(SCRIPT), '--release', str(self.release),
                               '--output', str(self.output)], capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(0, proc.returncode)


if __name__ == '__main__':
    unittest.main()
