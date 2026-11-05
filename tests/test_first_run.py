"""REQ-DIST-006: 첫 실행 자동 탐지와 손상된 작업 폴더 기억 복구."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class PreferencesRecoveryTests(unittest.TestCase):
    def test_corrupt_preferences_raise_named_error_and_stay_untouched(self):
        from bellalunauto import runtime
        with tempfile.TemporaryDirectory() as tmp:
            prefs = Path(tmp)/'prefs'
            prefs.mkdir()
            broken = prefs/'preferences.json'
            broken.write_bytes(b'{"workspace": ')
            with self.assertRaises(runtime.PreferencesError) as caught:
                runtime.resolve_layout(resource_dir=tmp, preferences_dir=prefs)
            self.assertEqual(caught.exception.path, broken)
            self.assertIn(str(broken), str(caught.exception))
            self.assertEqual(broken.read_bytes(), b'{"workspace": ')

    def test_relative_saved_workspace_is_a_preferences_error(self):
        from bellalunauto import runtime
        with tempfile.TemporaryDirectory() as tmp:
            prefs = Path(tmp)
            (prefs/'preferences.json').write_text('{"workspace": "relative"}', encoding='utf-8')
            with self.assertRaises(runtime.PreferencesError):
                runtime.resolve_layout(resource_dir=tmp, preferences_dir=prefs)

    def test_replacing_corrupt_preferences_keeps_a_copy_of_the_original(self):
        from bellalunauto import runtime
        with tempfile.TemporaryDirectory() as tmp:
            prefs = Path(tmp)/'prefs'
            prefs.mkdir()
            (prefs/'preferences.json').write_bytes(b'not json')
            chosen = Path(tmp)/'작업 폴더'
            backup = runtime.replace_corrupt_preferences(chosen, preferences_dir=prefs)
            self.assertTrue(backup.name.startswith('preferences.json.손상-'), backup)
            self.assertEqual(backup.read_bytes(), b'not json')
            saved = json.loads((prefs/'preferences.json').read_text(encoding='utf-8'))
            self.assertEqual(Path(saved['workspace']), chosen.resolve())

    def test_remembered_workspace_inside_install_dir_routes_to_recovery(self):
        """기억된 폴더를 쓸 수 없으면 재설치로도 풀리지 않으므로 다시 고르게 해야 한다."""
        from bellalunauto import runtime
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)/'app'
            install.mkdir()
            prefs = Path(tmp)/'prefs'
            prefs.mkdir()
            (prefs/'preferences.json').write_text(json.dumps({'workspace': str(install/'ws')}), encoding='utf-8')
            with patch.object(runtime, '_compiled', return_value=True), \
                    patch.object(runtime.sys, 'executable', str(install/'BellalunAuto.exe')):
                with self.assertRaises(runtime.PreferencesError):
                    runtime.resolve_layout(resource_dir=tmp, preferences_dir=prefs)
                with self.assertRaises(ValueError) as explicit:
                    runtime.resolve_layout(workspace=install/'ws', resource_dir=tmp, preferences_dir=prefs)
                self.assertNotIsInstance(explicit.exception, runtime.PreferencesError)

    def test_gui_start_failure_shows_dialog_instead_of_silent_exit(self):
        """숨김 콘솔 EXE에서 print만 하면 바로가기 실행이 아무 표시 없이 꺼진다."""
        from bellalunauto import app, runtime
        error = runtime.PreferencesError(Path('C:/x/preferences.json'), ValueError('bad'))
        with patch.object(app, 'resolve_layout', side_effect=error), \
                patch('bellalunauto.gui.recover_start', return_value=7) as recover:
            self.assertEqual(app.main([]), 7)
        recover.assert_called_once()
        self.assertIs(recover.call_args.args[0], error)

    def test_cli_start_failure_still_prints_and_returns_two(self):
        from bellalunauto import app, runtime
        error = runtime.PreferencesError(Path('C:/x/preferences.json'), ValueError('bad'))
        with patch.object(app, 'resolve_layout', side_effect=error), \
                patch('bellalunauto.gui.recover_start') as recover:
            self.assertEqual(app.main(['selfcheck']), 2)
        recover.assert_not_called()


class FirstRunDetectionTests(unittest.TestCase):
    def fields(self):
        from bellalunauto import gui
        return gui

    def test_single_registered_viewer_location_fills_install_dir_and_exe(self):
        gui = self.fields()
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)/'Bellalun'
            install.mkdir()
            (install/'VIEWER.exe').write_bytes(b'')
            with patch.object(gui, 'registered_viewer_locations', return_value=[install, Path(str(install) + '\\')]):
                values = gui.detect_settings({})
            self.assertEqual(Path(values['install_dir']), install.resolve())
            self.assertEqual(Path(values['viewer.exe']), (install/'VIEWER.exe').resolve())

    def test_ambiguous_or_missing_registry_location_is_left_empty(self):
        gui = self.fields()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp)/'a', Path(tmp)/'b'
            first.mkdir()
            second.mkdir()
            with patch.object(gui, 'registered_viewer_locations', return_value=[first, second]):
                self.assertEqual(gui.detect_settings({})['install_dir'], '')
            with patch.object(gui, 'registered_viewer_locations', return_value=[Path(tmp)/'gone']):
                self.assertEqual(gui.detect_settings({})['install_dir'], '')

    def test_explicit_install_dir_is_never_replaced(self):
        gui = self.fields()
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp)/'other'
            other.mkdir()
            config = {'install_dir': 'D:/kept'}
            with patch.object(gui, 'registered_viewer_locations', return_value=[other]):
                self.assertEqual(gui.detect_settings(config)['install_dir'], 'D:/kept')

    def test_first_run_config_applies_detected_paths_but_no_server_or_secret(self):
        gui = self.fields()
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)/'Bellalun'
            install.mkdir()
            (install/'VIEWER.exe').write_bytes(b'')
            with patch.object(gui, 'registered_viewer_locations', return_value=[install]):
                config = gui.first_run_config({'dicom': {'mwl_server_url': ''}})
            self.assertEqual(Path(config['viewer']['exe']), (install/'VIEWER.exe').resolve())
            self.assertEqual(config['dicom']['mwl_server_url'], '')

    def test_shipped_defaults_with_missing_example_paths_use_detected_location(self):
        """리뷰 지적: 배포 기본값에 예시 경로가 있어 빈 값 기준 탐지가 실제로는 동작하지 않았다."""
        gui = self.fields()
        from bellalunauto.runtime import default_config
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            config = default_config(root)
            gui._set(config, 'install_dir', str(Path(tmp)/'이 PC에 없는 예시'))
            gui._set(config, 'viewer.exe', str(Path(tmp)/'이 PC에 없는 예시'/'VIEWER.exe'))
            install = Path(tmp)/'D드라이브 Bellalun'
            install.mkdir()
            (install/'VIEWER.exe').write_bytes(b'')
            servers = {key: gui._get(config, key) for key in ('dicom.mwl_server_url', 'viewer.login.id')}
            with patch.object(gui, 'registered_viewer_locations', return_value=[install]):
                updated = gui.first_run_config(config)
            self.assertEqual(Path(gui._get(updated, 'install_dir')), install.resolve())
            self.assertEqual(Path(gui._get(updated, 'viewer.exe')), (install/'VIEWER.exe').resolve())
            for key, value in servers.items():
                self.assertEqual(gui._get(updated, key), value)

    def test_registry_reader_only_accepts_exact_bellalun_name(self):
        gui = self.fields()
        entries = [{'DisplayName': 'Bellalun', 'InstallLocation': 'C:/Program Files/Bellalun/'},
                   {'DisplayName': 'BellalunAuto 버전 1.0.0', 'InstallLocation': 'C:/Program Files/BellalunAuto/'},
                   {'DisplayName': 'Bellalun', 'InstallLocation': ''}]
        with patch.object(gui, '_uninstall_entries', return_value=entries):
            self.assertEqual(gui.registered_viewer_locations(), [Path('C:/Program Files/Bellalun/')])


if __name__ == '__main__':
    unittest.main()
