"""Validates: REQ-OCR-001 / TEST-OCR-001. 제품과 설치 프로그램은 실행하지 않는다."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from bellalunauto import prerequisites as prep
from bellalunauto.runtime import Layout


class OcrRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / 'ocr/tesseract.exe'
        self.exe.parent.mkdir()
        self.exe.write_bytes(b'engine')
        self.eng = self.exe.parent / 'tessdata/eng.traineddata'
        self.eng.parent.mkdir()
        self.eng.write_bytes(b'language')

    def runtime(self):
        self.assertIsNotNone(importlib.util.find_spec('core.ocr_runtime'),
                             'OCR runtime identity inspection is missing')
        return importlib.import_module('core.ocr_runtime')

    def inspect(self, output='tesseract v5.5.3.20241111\n private details', **kwargs):
        runtime = self.runtime()
        with patch.object(runtime.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 0, output, 'private stderr'), **kwargs):
            return runtime.inspect_runtime(self.exe)

    def test_identity_contains_version_and_both_file_digests_without_paths(self):
        result = self.inspect()
        self.assertEqual(result['executable_sha256'], hashlib.sha256(b'engine').hexdigest())
        self.assertEqual(result['eng_traineddata_sha256'], hashlib.sha256(b'language').hexdigest())
        self.assertEqual(result['version_line'], 'tesseract v5.5.3.20241111')
        self.assertEqual(result['version'], '5.5.3')
        self.assertEqual(result['reference_version'], '5.5.3')
        self.assertTrue(result['reference_match'])
        self.assertEqual(result['errors'], [])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn('private', json.dumps(result))

    def test_old_working_engine_is_identified_as_reference_mismatch(self):
        result = self.inspect('tesseract 5.4.0\n')
        self.assertEqual(result['version'], '5.4.0')
        self.assertFalse(result['reference_match'])
        self.assertEqual(result['errors'], [])

    def test_changed_language_is_read_again(self):
        first = self.inspect()
        self.eng.write_bytes(b'replaced language')
        second = self.inspect()
        self.assertNotEqual(first['eng_traineddata_sha256'], second['eng_traineddata_sha256'])

    def test_missing_files_return_safe_codes(self):
        runtime = self.runtime()
        self.exe.unlink()
        self.eng.unlink()
        with patch.object(runtime.subprocess, 'run') as child:
            result = runtime.inspect_runtime(self.exe)
        child.assert_not_called()
        self.assertIsNone(result['executable_sha256'])
        self.assertIsNone(result['eng_traineddata_sha256'])
        self.assertFalse(result['reference_match'])
        self.assertIn('executable_unreadable', result['errors'])
        self.assertIn('eng_traineddata_unreadable', result['errors'])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_timeout_nonzero_and_invalid_version_are_safe(self):
        runtime = self.runtime()
        cases = [(subprocess.TimeoutExpired(str(self.exe), 30, stderr='secret'), 'version_timeout'),
                 (subprocess.CompletedProcess([], 1, '', 'secret'), 'version_failed'),
                 (subprocess.CompletedProcess([], 0, str(self.root), 'secret'), 'version_unrecognized')]
        for outcome, code in cases:
            with self.subTest(code=code), patch.object(runtime.subprocess, 'run',
                    side_effect=outcome if isinstance(outcome, Exception) else None,
                    return_value=outcome) as child:
                result = runtime.inspect_runtime(self.exe)
                self.assertIn(code, result['errors'])
                self.assertFalse(result['reference_match'])
                self.assertNotIn('secret', json.dumps(result))
                self.assertNotIn(str(self.root), json.dumps(result))
                self.assertEqual(child.call_args.kwargs['timeout'], 30)
                self.assertEqual(child.call_args.kwargs['creationflags'],
                                 getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def test_prepare_install_records_old_identity_and_preserves_config_and_engine(self):
        resources = self.root / 'resources'
        resources.mkdir()
        items = []
        baseline = resources / 'assets/Baseline'
        baseline.mkdir(parents=True)
        for name in prep.BASELINES:
            (baseline / name).write_bytes(b'backup')
            items.append({'kind': 'baseline', 'destination': 'Baseline/' + name,
                          'sha256': hashlib.sha256(b'backup').hexdigest()})
        (resources / 'assets-manifest.json').write_text(json.dumps({'files': items}))
        (resources / 'components.json').write_text(json.dumps({'tesseract': {
            'default_install_dir': str(self.exe.parent)}}))
        work = self.root / 'work'
        work.mkdir()
        layout = Layout(resources, work, work / 'config.json')
        original = json.dumps({'xipl': {'tesseract_exe': str(self.exe)},
                               'baseline_dir': str(baseline)}).encode()
        layout.config_path.write_bytes(original)
        with patch.object(prep.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 0, 'tesseract 5.4.0\n', '')):
            self.assertEqual(prep.prepare_install(layout), 0)
        self.assertEqual(layout.config_path.read_bytes(), original)
        self.assertEqual(self.exe.read_bytes(), b'engine')
        self.assertEqual(self.eng.read_bytes(), b'language')
        self.assertTrue((work / 'ocr-runtime.json').is_file(), 'Setup must record OCR identity')
        result = json.loads((work / 'ocr-runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(result['version'], '5.4.0')
        self.assertFalse(result['reference_match'])
        summary = (work / 'install-preparation.txt').read_text(encoding='utf-8-sig')
        self.assertIn('[WARN]', summary)
        self.assertIn('5.5.3', summary)
        self.assertIn('5.4.0', summary)


if __name__ == '__main__':
    unittest.main()
