"""REQ-DIST-002/004: 감시·worker·소스 없는 진단의 안전 검사."""

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class DistributionAppTests(unittest.TestCase):
    def write_wu_report(self, folder, name='WindowsUpdate_20260101_010101', meta=None, count=13):
        from core.result import TCResult, write_reports
        results = []
        for number in range(1, count + 1):
            result = TCResult(f'TC_WindowsUpdate_{number:02}', 'Synthetic report protocol')
            result.add(1, 'Synthetic assertion', 'PASS')
            results.append(result)
        return write_reports(results, str(folder), name, meta=meta or {})

    def app(self):
        self.assertIsNotNone(importlib.util.find_spec('bellalunauto.app'),
                             '배포 진입 계층이 필요하다')
        from bellalunauto import app
        return app

    def test_version_does_not_load_config_or_engine(self):
        app = self.app()
        with patch.object(app, 'resolve_layout', side_effect=AssertionError('config read')):
            self.assertEqual(app.main(['--version']), 0)

    def test_worker_command_has_one_worker_and_absolute_paths(self):
        app = self.app()
        from bellalunauto.runtime import Layout
        layout = Layout(Path.cwd(), Path.cwd()/'한글 폴더', Path.cwd()/'설정.json')
        command = app.worker_command(layout, ['run-regression'])
        self.assertEqual(command.count('--worker'), 1)
        self.assertIn(str(layout.config_path), command)
        self.assertIn(str(layout.workspace), command)
        self.assertEqual(command[-1], 'run-regression')

    def test_worker_rejects_recursive_worker_argument(self):
        app = self.app()
        from bellalunauto.runtime import Layout
        layout = Layout(Path.cwd(), Path.cwd(), Path.cwd()/'config.json')
        with self.assertRaises(ValueError):
            app.worker_command(layout, ['--worker', 'run-regression'])

    def test_wu_report_requires_all_thirteen_tcs_and_current_run(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            meta = {'execution_mode':'live','chain_completed':True}
            paths = self.write_wu_report(folder, meta=meta)
            report = Path(paths['json'])
            self.assertEqual(report.name, 'Result_WindowsUpdate_20260101_010101.json')
            self.assertIsNotNone(app.completed_report(folder, 'run-winupdate', time.time()-2))
            self.assertIsNone(app.completed_report(folder, 'run-winupdate', time.time()+2))
            self.write_wu_report(folder, meta=meta, count=12)
            self.assertIsNone(app.completed_report(folder, 'run-winupdate', time.time()-2))

    def test_wu_completed_report_matches_actual_report_producer(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.write_wu_report(Path(tmp), meta={'execution_mode':'live','chain_completed':True})
            summary = app.completed_report(Path(tmp), 'run-winupdate', time.time()-2)
            self.assertIsNotNone(summary)
            self.assertEqual(summary['path'], paths['json'])
            self.assertEqual(summary['tc_count'], 13)
            self.assertEqual(summary['verdicts'], {'PASS':13})

    def test_basic_report_prefix_cannot_be_accepted_as_windows_update(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            # Even equivalent IDs/meta cannot turn a basic report filename into
            # a completed Windows Update chain.
            paths = self.write_wu_report(Path(tmp), name='20260101_010101',
                                         meta={'execution_mode':'live','chain_completed':True})
            self.assertEqual(Path(paths['json']).name, 'Result_20260101_010101.json')
            self.assertIsNone(app.completed_report(Path(tmp), 'run-winupdate', time.time()-2))

    def test_historical_or_aborted_wu_is_not_a_completed_live_chain(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for meta in ({}, {'execution_mode':'historical','chain_completed':False},
                         {'execution_mode':'live','chain_completed':False}):
                self.write_wu_report(folder, name='WindowsUpdate_1', meta=meta)
                with self.subTest(meta=meta):
                    self.assertIsNone(app.completed_report(folder, 'run-winupdate', time.time()-2))

    def test_single_tc_is_not_full_regression(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'Result_1.json').write_text(json.dumps({'results':[
                {'tc_id':'TC_Basic_WorkFlow_01','verdict':'PASS'}]}), encoding='utf-8')
            self.assertIsNone(app.completed_report(Path(tmp), 'run-regression', time.time()-2))

    def test_diagnostic_missing_config_does_not_create_workspace(self):
        app = self.app()
        from bellalunauto.runtime import Layout
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layout = Layout(root, root/'new workspace', root/'new workspace/config.json')
            rows = app.diagnostics(layout, check_connections=False)
            self.assertTrue(rows)
            self.assertTrue(any(not row['ok'] for row in rows))
            self.assertFalse(layout.workspace.exists())
            self.assertTrue(all('fix' in row for row in rows))

    def test_reported_configuration_redacts_credentials(self):
        app = self.app()
        value = app.redact({'login':{'password':'private-password', 'id':'test'},
                            'api_token':'secret', 'path':'visible'})
        text = json.dumps(value)
        self.assertNotIn('private-password', text)
        self.assertNotIn('secret', text)
        self.assertIn('visible', text)

    def test_ui_command_classification_keeps_readonly_diagnostics(self):
        app = self.app()
        self.assertTrue(app.requires_product_control('run-wf09'))
        self.assertTrue(app.requires_product_control('run-winupdate'))
        self.assertTrue(app.requires_product_control('reset-environment'))
        self.assertFalse(app.requires_product_control('selfcheck'))
        self.assertFalse(app.requires_product_control('portability-check'))

    def test_elevation_log_relay_keeps_partial_lines_until_complete(self):
        import io
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'elevated.log'
            output = io.StringIO()
            path.write_bytes('한글 로그\npartial'.encode('utf-8'))
            offset = app.relay_log(path, 0, output=output)
            self.assertEqual(output.getvalue(), '한글 로그\n')
            with path.open('ab') as stream:
                stream.write(b' complete\n')
            offset = app.relay_log(path, offset, output=output)
            self.assertEqual(output.getvalue(), '한글 로그\npartial complete\n')
            self.assertEqual(offset, path.stat().st_size)

    def test_elevation_log_must_be_in_selected_workspace(self):
        app = self.app()
        from bellalunauto.runtime import Layout
        with tempfile.TemporaryDirectory() as tmp:
            layout = Layout(Path(tmp), Path(tmp)/'workspace', Path(tmp)/'config.json')
            with self.assertRaises(ValueError):
                app.validate_log_path(layout, Path(tmp)/'elsewhere.log')

    def test_worker_waits_for_guard_to_assign_job(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp)/'ready.json'
            self.assertTrue(callable(getattr(app, 'wait_worker_ready', None)))
            with self.assertRaises(TimeoutError):
                app.wait_worker_ready(ready, 'parent', timeout=0)
            ready.write_text('parent', encoding='utf-8')
            app.wait_worker_ready(ready, 'parent', timeout=.1)
            with self.assertRaises(TimeoutError):
                app.wait_worker_ready(ready, 'another-parent', timeout=0)

    def test_equal_form_historical_conversion_uses_readonly_engine(self):
        app = self.app()
        with patch.object(app, 'resolve_layout') as resolver, \
             patch.object(app, '_engine', return_value=0) as engine, \
             patch.object(app, 'run_guarded') as guard:
            self.assertEqual(app.main(['run-winupdate', '--from-regression=old.json']), 0)
            engine.assert_called_once()
            guard.assert_not_called()

    def test_historical_conversion_keeps_legacy_argparse_abbreviations_readonly(self):
        app = self.app()
        for option in ('--f', '--fr', '--from-r', '--from-regression'):
            with self.subTest(option=option):
                self.assertTrue(app.historical_conversion(['run-winupdate', option+'=old.json']))
        self.assertFalse(app.historical_conversion(['run-winupdate', '--from-regression-invalid=x']))

    def test_legacy_subcommand_help_reaches_engine_parser(self):
        app = self.app()
        with patch.object(app, 'resolve_layout'), \
             patch.object(app, '_engine', return_value=0) as engine, \
             patch.object(app, 'run_guarded') as guard:
            self.assertEqual(app.main(['verify-install-package', '--help']), 0)
            self.assertEqual(engine.call_args.args[1], ['verify-install-package', '--help'])
            guard.assert_not_called()

    def test_diagnostics_invalid_optional_sections_report_missing(self):
        app = self.app()
        from bellalunauto.runtime import Layout
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root/'config.json'
            config.write_text(json.dumps({'viewer':None,'xipl':None,'dicom':None}), encoding='utf-8')
            rows = app.diagnostics(Layout(root, root, config), check_connections=False)
            self.assertFalse(next(row for row in rows if row['name']=='Viewer')['ok'])
            self.assertFalse(next(row for row in rows if row['name']=='Tesseract OCR')['ok'])

    def test_diagnostics_reports_workspace_path_too_long_for_evidence(self):
        """작업 폴더가 깊으면 Viewer Export 증거 경로가 Windows 260자 한도를 넘는다.

        2026-10-18 실측: 증거 상대 경로는 최대 117자(Viewer가 쓰는 Export 결과)였고
        LongPathsEnabled는 이 PC와 LTSC 기본값 모두 0이다. 실행 중간에 실패하기 전에
        자체진단이 알린다.
        """
        app = self.app()
        from bellalunauto.runtime import Layout
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root/'config.json'
            config.write_text('{}', encoding='utf-8')
            short = app.diagnostics(Layout(root, root, config), check_connections=False)
            row = next(r for r in short if r['name'] == '작업 폴더 경로 길이')
            self.assertTrue(row['ok'], row)
            deep = Path('D:/') / ('가' * (app.WORKSPACE_PATH_LIMIT + 1))
            rows = app.diagnostics(Layout(root, deep, config), check_connections=False)
            row = next(r for r in rows if r['name'] == '작업 폴더 경로 길이')
            self.assertFalse(row['ok'])
            self.assertIn(str(app.WORKSPACE_PATH_LIMIT), row['detail'])
            self.assertIn('짧은', row['fix'])

    def test_diagnostics_reports_percent_in_workspace_path(self):
        """작업 폴더 경로에 %가 있으면 Viewer Export 저장 대화상자가 경로를 거부한다.

        2026-10-20 실측: 작업 폴더 `...O'Brien %TEMP% #한글` 아래 `WF14_Baseline_Settings.vms`를
        Windows 저장 대화상자가 "파일 이름이 올바르지 않습니다"로 거부해 WF14가 300초 뒤 FAIL했다.
        """
        app = self.app()
        from bellalunauto.runtime import Layout
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root/'config.json'
            config.write_text('{}', encoding='utf-8')
            ok = app.diagnostics(Layout(root, root/"O'Brien & (1) #한글", config), check_connections=False)
            self.assertTrue(next(r for r in ok if r['name'] == '작업 폴더 경로 문자')['ok'])
            rows = app.diagnostics(Layout(root, root/'검증 %TEMP% 폴더', config), check_connections=False)
            row = next(r for r in rows if r['name'] == '작업 폴더 경로 문자')
            self.assertFalse(row['ok'])
            self.assertIn('%', row['detail'])
            self.assertIn('%', row['fix'])

    def test_product_run_refuses_workspace_with_percent_before_ui(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)/'검증 %TEMP% 폴더'
            workspace.mkdir()
            (workspace/'config.json').write_text('{}', encoding='utf-8')
            with patch.object(app, 'run_guarded') as guarded, patch.object(app, '_elevate') as elevate:
                code = app.main(['--workspace', str(workspace), 'run-regression'])
            self.assertEqual(2, code)
            guarded.assert_not_called()
            elevate.assert_not_called()

    def test_diagnostics_reports_missing_xipl_path(self):
        """Viewer는 XIPL_PATH가 없으면 E2100 뒤 PC 전원을 끈다(2026-10-18 실측).

        9784 포트 점검만으로는 이 상태를 못 잡았다. 자체진단이 실행 환경 기준으로 알린다.
        """
        from unittest import mock
        from core import product_env
        app = self.app()
        from bellalunauto.runtime import Layout
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root/'config.json'
            config.write_text('{}', encoding='utf-8')
            without_xipl = {k: v for k, v in os.environ.items() if k.upper() != 'XIPL_PATH'}
            with mock.patch.object(product_env, 'registered_environment', return_value={}), \
                    mock.patch.dict(os.environ, without_xipl, clear=True):
                rows = app.diagnostics(Layout(root, root, config), check_connections=False)
            row = next(r for r in rows if r['name'] == 'XIPL 설치 경로(XIPL_PATH)')
            self.assertFalse(row['ok'])
            self.assertIn('전원', row['fix'])
            server = root/'xipl'/'SERVER_X64'
            server.mkdir(parents=True)
            (server/'XIPL.KEEPALIVE.exe').write_bytes(b'')
            with mock.patch.object(product_env, 'registered_environment',
                                   return_value={'XIPL_PATH': str(root/'xipl')}), \
                    mock.patch.dict(os.environ, without_xipl, clear=True):
                rows = app.diagnostics(Layout(root, root, config), check_connections=False)
            row = next(r for r in rows if r['name'] == 'XIPL 설치 경로(XIPL_PATH)')
            self.assertTrue(row['ok'], row)

    def test_guard_preserves_abnormal_exit_notification_and_cleanup(self):
        import io
        from contextlib import nullcontext
        from types import SimpleNamespace
        from bellalunauto.runtime import Layout
        from core import automation_health, ui
        from bellalunauto import processes
        import run
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root/'config.json'
            config.write_text('{}', encoding='utf-8')
            child = SimpleNamespace(pid=123, stdout=io.StringIO('synthetic worker failure\n'),
                                    poll=lambda:17, returncode=17)
            with patch.object(app, 'RunLock', return_value=nullcontext()), \
                 patch.object(ui, 'foreground_unlocked', return_value=nullcontext()), \
                 patch.object(ui, 'taskbar_autohidden', return_value=nullcontext()), \
                 patch.object(processes, 'WindowsJob'), \
                 patch.object(app.subprocess, 'Popen', return_value=child), \
                 patch.object(app, 'completed_report', return_value=None), \
                 patch.object(automation_health, 'write_state'), \
                 patch.object(automation_health, 'process_exit_message', return_value={}), \
                 patch.object(automation_health, 'notify_windows') as notice, \
                 patch.object(run, 'shutdown_viewer', return_value={'state':'synthetic closed'}) as close:
                self.assertEqual(app.run_guarded(Layout(root, root, config), ['run-regression']), 17)
            close.assert_called_once()
            notice.assert_called_once()
            self.assertEqual(list((root/'work').glob('worker-ready-*')), [])


if __name__ == '__main__':
    unittest.main()
