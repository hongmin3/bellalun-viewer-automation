"""Validates: REQ-DIST-007. 제품 UI와 SQL을 실행하지 않는다."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from bellalunauto import prerequisites as prep
from bellalunauto.runtime import Layout


class PreparationTests(unittest.TestCase):
    def setUp(self):
        # 설치 동작은 run_child로 대체하므로 PC의 실제 권한도 시험 안에서 격리한다.
        if os.name == 'nt':
            admin = patch('ctypes.windll.shell32.IsUserAnAdmin', return_value=True)
            admin.start()
            self.addCleanup(admin.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.resources = self.root / 'resources'
        self.resources.mkdir()
        self.exe = self.root / 'ocr/tesseract.exe'
        self.installer = self.resources / 'installers/ocr.exe'
        self.installer.parent.mkdir()
        self.installer.write_bytes(b'installer-fixture')
        self.spec = {'filename': 'ocr.exe', 'sha256': hashlib.sha256(self.installer.read_bytes()).hexdigest(),
                     'default_install_dir': str(self.exe.parent), 'timeout_sec': 900}
        (self.resources / 'components.json').write_text(json.dumps({'tesseract': self.spec}))
        self.layout = Layout(self.resources, self.root / 'work', self.root / 'work/config.json')

    def installed(self):
        self.exe.parent.mkdir(exist_ok=True)
        self.exe.write_bytes(b'ocr-fixture')
        data = self.exe.parent / 'tessdata/eng.traineddata'
        data.parent.mkdir(exist_ok=True)
        data.write_bytes(b'language')

    def run_child(self, args, **kwargs):
        if isinstance(args, str):
            self.installed()
            return subprocess.CompletedProcess(args, 0, '', '')
        return subprocess.CompletedProcess(args, 0, 'tesseract 5.5.3\n', '')

    def test_missing_ocr_installs_and_rechecks_without_network(self):
        with patch.object(prep.subprocess, 'run', side_effect=self.run_child) as child:
            self.assertEqual(prep.ensure_ocr(self.resources, ''), self.exe)
        self.assertEqual(child.call_args_list[0].args[0],
                         '"' + str(self.installer) + '" /S /D=' + str(self.exe.parent))
        self.assertEqual(child.call_args_list[-1].args[0][-1], '--version')

    @unittest.skipUnless(os.name == 'nt', 'Windows 관리자 권한 검사')
    def test_missing_ocr_without_admin_never_launches_installer(self):
        with patch('ctypes.windll.shell32.IsUserAnAdmin', return_value=False), \
             patch.object(prep.subprocess, 'run') as child:
            with self.assertRaisesRegex(ValueError, '관리자 권한'):
                prep.ensure_ocr(self.resources, '')
        child.assert_not_called()

    def test_working_existing_ocr_is_reused_without_installer(self):
        self.installed()
        self.installer.unlink()
        with patch.object(prep.subprocess, 'run', side_effect=self.run_child) as child:
            self.assertEqual(prep.ensure_ocr(self.resources, str(self.exe)), self.exe)
        self.assertEqual(child.call_count, 1)

    def test_corrupt_installer_never_executes(self):
        self.installer.write_bytes(b'tampered')
        with patch.object(prep.subprocess, 'run') as child:
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                prep.ensure_ocr(self.resources, '')
        child.assert_not_called()

    def test_failed_install_and_timeout_are_reported(self):
        for outcome in [subprocess.CompletedProcess([], 1, '', ''),
                        subprocess.TimeoutExpired('ocr', 900)]:
            with self.subTest(outcome=type(outcome).__name__):
                with patch.object(prep.subprocess, 'run', side_effect=outcome if isinstance(outcome, Exception) else None,
                                  return_value=outcome):
                    with self.assertRaises((ValueError, subprocess.TimeoutExpired)):
                        prep.ensure_ocr(self.resources, '')

    def test_missing_language_after_installer_is_failure(self):
        with patch.object(prep.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            with self.assertRaises(ValueError):
                prep.ensure_ocr(self.resources, '')

    def assets(self):
        items = []
        for name in ('DATA', 'ACCOUNT', 'CONFIGURATION', 'PROCEDURE'):
            target = self.resources / ('assets/Baseline/' + name + '.bak')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'backup-fixture')
            items.append({'kind': 'baseline', 'destination': 'Baseline/' + name + '.bak',
                          'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        (self.resources / 'assets-manifest.json').write_text(json.dumps({'files': items}))

    def test_assets_validate_all_four_baselines_and_reject_tampering_and_escape(self):
        self.assets()
        prep.verify_assets(self.resources)
        path = self.resources / 'assets/Baseline/DATA.bak'
        path.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            prep.verify_assets(self.resources)
        self.assets()
        manifest = self.resources / 'assets-manifest.json'
        data = json.loads(manifest.read_text())
        data['files'][0]['destination'] = '../outside.bak'
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            prep.verify_assets(self.resources)

    def test_existing_config_is_byte_preserved_and_summary_saved(self):
        self.assets()
        self.installed()
        self.layout.workspace.mkdir()
        original = ('{ "xipl": {"tesseract_exe": ' + json.dumps(str(self.exe)) +
                    '}, "baseline_dir": ' + json.dumps(str(self.resources / 'assets/Baseline')) + ', "custom":42 }').encode()
        self.layout.config_path.write_bytes(original)
        with patch.object(prep.subprocess, 'run', side_effect=self.run_child):
            self.assertEqual(prep.prepare_install(self.layout), 0)
        self.assertEqual(self.layout.config_path.read_bytes(), original)
        self.assertIn('[OK]', (self.layout.workspace / 'install-preparation.txt').read_text(encoding='utf-8-sig'))

    def test_new_config_connects_ocr_and_baseline(self):
        self.assets()
        with patch('bellalunauto.gui.first_run_config', return_value={'xipl': {}}), \
             patch('bellalunauto.gui.load_gui_config', return_value={}), \
             patch.object(prep.subprocess, 'run', side_effect=self.run_child):
            self.assertEqual(prep.prepare_install(self.layout), 0)
        config = json.loads(self.layout.config_path.read_text(encoding='utf-8'))
        self.assertEqual(config['xipl']['tesseract_exe'], str(self.exe))
        self.assertEqual(config['baseline_dir'], str(self.resources / 'assets/Baseline'))

    def test_bad_assets_fail_with_actionable_summary(self):
        self.assertNotEqual(prep.prepare_install(self.layout), 0)
        summary = (self.layout.workspace / 'install-preparation.txt').read_text(encoding='utf-8-sig')
        self.assertIn('[FAIL]', summary)
        self.assertIn('다음 행동', summary)

    def test_invalid_custom_path_is_preserved_and_not_replaced(self):
        with patch.object(prep.subprocess, 'run') as child:
            with self.assertRaisesRegex(ValueError, '저장된 OCR'):
                prep.ensure_ocr(self.resources, str(self.root / 'custom/missing.exe'))
        child.assert_not_called()

    def test_existing_empty_ocr_does_not_report_ready_with_unsaved_path(self):
        self.assets()
        self.layout.workspace.mkdir()
        original = json.dumps({'baseline_dir': str(self.resources / 'assets/Baseline'), 'xipl': {}}).encode()
        self.layout.config_path.write_bytes(original)
        with patch.object(prep.subprocess, 'run', side_effect=self.run_child):
            self.assertNotEqual(prep.prepare_install(self.layout), 0)
        self.assertEqual(self.layout.config_path.read_bytes(), original)

    def test_cli_runs_preparation_and_does_not_enter_product_engine(self):
        from bellalunauto import app
        self.assets()
        with patch.object(app, 'resolve_layout', return_value=self.layout), \
             patch.object(app, '_engine') as engine, \
             patch('bellalunauto.gui.first_run_config', return_value={'xipl': {}}), \
             patch('bellalunauto.gui.load_gui_config', return_value={}), \
             patch.object(prep.subprocess, 'run', side_effect=self.run_child):
            self.assertEqual(app.main(['prepare-install']), 0)
        engine.assert_not_called()

    def test_ocr_in_writable_workspace_is_not_executed(self):
        self.assets()
        self.layout.workspace.mkdir()
        self.layout.config_path.write_text(json.dumps({'xipl': {'tesseract_exe': str(self.layout.workspace / 'bad.exe')}}))
        with patch.object(prep.subprocess, 'run') as child:
            self.assertNotEqual(prep.prepare_install(self.layout), 0)
        child.assert_not_called()

    def test_path_ocr_inside_workspace_is_never_executed(self):
        self.assets()
        self.layout.workspace.mkdir()
        bad = self.layout.workspace / 'tesseract.exe'
        bad.write_bytes(b'untrusted')
        language = self.layout.workspace / 'tessdata/eng.traineddata'
        language.parent.mkdir()
        language.write_bytes(b'language')
        self.layout.config_path.write_text(json.dumps({'xipl': {'tesseract_exe': str(self.exe)}}))
        with patch.object(prep.shutil, 'which', return_value=str(bad)), \
             patch.object(prep.subprocess, 'run', side_effect=self.run_child) as child:
            prep.prepare_install(self.layout)
        self.assertFalse(any(isinstance(call.args[0], list) and call.args[0][0] == str(bad)
                             for call in child.call_args_list))


if __name__ == '__main__':
    unittest.main()
