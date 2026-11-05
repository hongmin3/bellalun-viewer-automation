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

    def test_bad_remembered_workspace_no_longer_blocks_installed_start(self):
        """설치판은 기억 파일 대신 설치 폴더의 `작업`을 쓴다. 쓸 수 없는 기억 경로가 시작을 막지 않는다."""
        from bellalunauto import runtime
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)/'app'
            install.mkdir()
            prefs = Path(tmp)/'prefs'
            prefs.mkdir()
            (prefs/'preferences.json').write_text(json.dumps({'workspace': str(install/'ws')}), encoding='utf-8')
            with patch.object(runtime, '_compiled', return_value=True), \
                    patch.object(runtime.sys, 'executable', str(install/'BellalunAuto.exe')):
                layout = runtime.resolve_layout(resource_dir=tmp, preferences_dir=prefs)
                self.assertEqual(layout.workspace, (install/'작업').resolve())
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


class InstallWorkspaceTests(unittest.TestCase):
    """사용자 결정(2026-11-05): 설치판 리포트·로그·설정은 설치 폴더 아래 `작업`에 둔다."""

    def compiled(self, install):
        from bellalunauto import runtime
        return (patch.object(runtime, '_compiled', return_value=True),
                patch.object(runtime.sys, 'executable', str(install/'BellalunAuto.exe')))

    def test_compiled_default_workspace_is_install_work_folder_and_ignores_preferences(self):
        from bellalunauto import runtime
        with tempfile.TemporaryDirectory() as tmp:
            install, prefs = Path(tmp)/'app', Path(tmp)/'prefs'
            install.mkdir()
            prefs.mkdir()
            (prefs/'preferences.json').write_text(json.dumps({'workspace': str(Path(tmp)/'old')}), encoding='utf-8')
            first, second = self.compiled(install)
            with first, second:
                layout = runtime.resolve_layout(preferences_dir=prefs)
            self.assertEqual(layout.workspace, (install/'작업').resolve())
            self.assertEqual(layout.config_path, (install/'작업'/'config.json').resolve())

    def test_writes_allowed_only_under_install_work_folder(self):
        from bellalunauto import runtime
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)/'app'
            install.mkdir()
            first, second = self.compiled(install)
            with first, second:
                runtime.resolve_layout(workspace=install/'작업')
                runtime.resolve_layout(workspace=Path(tmp)/'outside')
                for bad in (install, install/'resources', install/'작업2'):
                    with self.assertRaises(ValueError, msg=str(bad)):
                        runtime.resolve_layout(workspace=bad)

    def test_previous_config_reads_remembered_workspace_first(self):
        from bellalunauto import gui
        with tempfile.TemporaryDirectory() as tmp:
            prefs, old = Path(tmp)/'prefs', Path(tmp)/'old'
            (prefs/'workspace').mkdir(parents=True)
            old.mkdir()
            (old/'config.json').write_text('{"viewer": {"login": {"id": "remembered"}}}', encoding='utf-8')
            (prefs/'workspace'/'config.json').write_text('{"viewer": {"login": {"id": "default"}}}', encoding='utf-8')
            (prefs/'preferences.json').write_text(json.dumps({'workspace': str(old)}), encoding='utf-8')
            with patch('bellalunauto.runtime._preferences_dir', return_value=prefs):
                self.assertEqual(gui.previous_config()['viewer']['login']['id'], 'remembered')
                (prefs/'preferences.json').unlink()
                self.assertEqual(gui.previous_config()['viewer']['login']['id'], 'default')

    def test_installer_grants_users_modify_only_on_work_folder(self):
        import re
        script = (Path(__file__).resolve().parents[1]/'packaging'/'BellalunAuto.iss').read_text(encoding='utf-8')
        self.assertRegex(script, r'(?m)^\[Dirs\]\s*\n(?:;.*\n)*Name: "\{app\}\\작업"; Permissions: users-modify; Flags: uninsneveruninstall\s*$')
        self.assertEqual(len(re.findall(r'users-modify', script)), 1)
        self.assertNotRegex(script, r'(?m)^Type: filesandordirs; Name: "\{app\}\\작업')


class ElevatedWorkspaceGuardTests(unittest.TestCase):
    """리뷰 지적: Users가 쓸 수 있는 `작업`을 승격 시험이 그대로 믿으면 다른 계정이 관리자 권한을 얻는다."""

    def test_product_executables_inside_workspace_are_refused(self):
        from bellalunauto import app
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)/'작업'
            work.mkdir()
            config = {'viewer': {'exe': str(work/'VIEWER.exe')}, 'xipl': {'tesseract_exe': 'C:/Program Files/T/tesseract.exe'},
                      'baseline_dir': str(work/'Baseline')}
            problems = app.elevated_workspace_problems(work, config)
            self.assertEqual(len(problems), 2, problems)
            self.assertEqual(app.elevated_workspace_problems(work, {'viewer': {'exe': 'C:/Program Files/Bellalun/VIEWER.exe'}}), [])

    @unittest.skipUnless(hasattr(__import__('_winapi'), 'CreateJunction'), 'Windows junction')
    def test_result_folder_replaced_by_junction_is_refused(self):
        import _winapi
        from bellalunauto import app
        with tempfile.TemporaryDirectory() as tmp:
            work, target = Path(tmp)/'작업', Path(tmp)/'protected'
            work.mkdir()
            target.mkdir()
            _winapi.CreateJunction(str(target), str(work/'Log'))
            problems = app.elevated_workspace_problems(work, {})
            self.assertTrue(any('Log' in p for p in problems), problems)

    def test_safe_cwd_is_never_the_workspace(self):
        from bellalunauto import app, runtime
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)/'app'
            install.mkdir()
            with patch.object(runtime, '_compiled', return_value=True), \
                    patch.object(app.sys, 'executable', str(install/'BellalunAuto.exe')):
                self.assertEqual(app._safe_cwd(), install.resolve())


class FirstRunDetectionTests(unittest.TestCase):
    def setUp(self):
        # 이 PC의 실제 디스크·SQL·기존 설정에 결과가 좌우되지 않게 기본은 비워 둔다.
        from bellalunauto import gui
        for name, value in (('_fixed_drive_roots', []), ('_sql_instances', []), ('previous_config', None),
                            ('team_settings', None)):
            patcher = patch.object(gui, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

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

    def test_data_dir_needs_product_markers_on_fixed_drive_not_usb_log_folder(self):
        """2026-11-05 실측: 배포 기본값 D:\\BellalunData가 USB의 제품 로그 폴더와 이름이 같아 그대로 채워졌다."""
        gui = self.fields()
        with tempfile.TemporaryDirectory() as tmp:
            usb, fixed = Path(tmp)/'usb', Path(tmp)/'fixed'
            (usb/'BellalunData'/'Log').mkdir(parents=True)
            for name in ('Config', 'Database'):
                (fixed/'BellalunData'/name).mkdir(parents=True)
            config = {'data_dir': str(usb/'BellalunData')}
            with patch.object(gui, 'registered_viewer_locations', return_value=[]), \
                    patch.object(gui, '_fixed_drive_roots', return_value=[fixed]), \
                    patch.object(gui, '_sql_instances', return_value=[]):
                updated = gui.first_run_config(config)
            self.assertEqual(Path(updated['data_dir']), (fixed/'BellalunData').resolve())

    def test_sql_instance_is_taken_only_when_bellalun_instance_is_registered(self):
        gui = self.fields()
        with patch.object(gui, 'registered_viewer_locations', return_value=[]), \
                patch.object(gui, '_fixed_drive_roots', return_value=[]):
            with patch.object(gui, '_sql_instances', return_value=['MAMMO', 'BELLALUN', 'CHAMELEON']):
                found = gui.first_run_config({'sql_server': 'X\\OTHER', 'sql_service_name': 'MSSQL$OTHER'})
            self.assertEqual((found['sql_server'], found['sql_service_name']), ('.\\BELLALUN', 'MSSQL$BELLALUN'))
            with patch.object(gui, '_sql_instances', return_value=['MAMMO']):
                kept = gui.first_run_config({'sql_server': 'X\\OTHER'})
            self.assertEqual(kept['sql_server'], 'X\\OTHER')

    def test_previous_settings_on_this_pc_supply_servers_and_login_but_not_paths(self):
        gui = self.fields()
        previous = {'viewer': {'exe': 'Z:/old/VIEWER.exe', 'login': {'id': 'qa', 'password': ' p w '}},
                    'dicom': {'mwl_server_url': 'http://mwl.example:8080', 'print_scp': {'port': 104}}}
        with patch.object(gui, 'registered_viewer_locations', return_value=[]), \
                patch.object(gui, '_fixed_drive_roots', return_value=[]), \
                patch.object(gui, '_sql_instances', return_value=[]), \
                patch.object(gui, 'previous_config', return_value=previous):
            updated = gui.first_run_config({'viewer': {'exe': '', 'login': {'id': '', 'password': ''}},
                                            'dicom': {'mwl_server_url': '', 'print_scp': {'port': ''}}})
        self.assertEqual(updated['viewer']['login'], {'id': 'qa', 'password': ' p w '})
        self.assertEqual(updated['dicom']['mwl_server_url'], 'http://mwl.example:8080')
        self.assertEqual(updated['dicom']['print_scp']['port'], 104)
        self.assertNotEqual(updated['viewer']['exe'], 'Z:/old/VIEWER.exe')

    def test_first_run_saves_detected_settings_without_opening_the_form(self):
        """사용자 결정(2026-11-05): 첫 실행에 PC별 설정 창을 띄우지 않는다."""
        gui = self.fields()
        import inspect
        source = inspect.getsource(gui.launch)
        self.assertNotIn('first_run=True', source)
        from bellalunauto.runtime import Layout
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parents[1]
            work = Path(tmp)/'작업'
            layout = Layout(root, work, work/'config.json')
            with patch.object(gui, 'registered_viewer_locations', return_value=[]), \
                    patch.object(gui, '_fixed_drive_roots', return_value=[]), \
                    patch.object(gui, '_sql_instances', return_value=[]), \
                    patch.object(gui, 'previous_config', return_value=None), \
                    patch('bellalunauto.runtime.remember_workspace') as remember:
                config = gui.prepare_first_run(layout)
            saved = json.loads((work/'config.json').read_text(encoding='utf-8'))
            self.assertEqual(saved, config)
            remember.assert_called_once_with(work)

    def test_registry_reader_only_accepts_exact_bellalun_name(self):
        gui = self.fields()
        entries = [{'DisplayName': 'Bellalun', 'InstallLocation': 'C:/Program Files/Bellalun/'},
                   {'DisplayName': 'BellalunAuto 버전 1.0.0', 'InstallLocation': 'C:/Program Files/BellalunAuto/'},
                   {'DisplayName': 'Bellalun', 'InstallLocation': ''}]
        with patch.object(gui, '_uninstall_entries', return_value=entries):
            self.assertEqual(gui.registered_viewer_locations(), [Path('C:/Program Files/Bellalun/')])


if __name__ == '__main__':
    unittest.main()
