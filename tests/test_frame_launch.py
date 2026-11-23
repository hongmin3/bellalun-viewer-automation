# -*- coding: utf-8 -*-
"""Bellalun 기본 실행 흐름을 공용 화면으로 보이는 데이터와 동의 처리.

Validates: REQ-FRAME-002
"""
import json
from pathlib import Path
import tempfile
import unittest

from bellalunauto import frame_launch as fl


class FakeRecord:
    def __init__(self, folder, data, rows=()):
        self.path = Path(folder) / 'Runs' / data['run_id'] / 'run.json'
        self.data = data
        self._rows = list(rows)

    def result_rows(self):
        return self._rows


class ScreenTests(unittest.TestCase):
    def test_home_offers_one_primary_next_step_and_last_result(self):
        record = FakeRecord('.', {'run_id': 'R1', 'action': 'run-regression', 'status': 'completed',
                                  'verdicts': {'PASS': 3, 'MANUAL': 1}})
        data = fl.home_data(record)
        primary = [b for b in data['buttons'] if b['primary']]
        self.assertEqual(['inspect'], [b['key'] for b in primary])
        self.assertEqual('warn', data['last_result']['level'])
        self.assertIn('기본기능 체크리스트', data['last_result']['text'])
        self.assertIsNone(fl.home_data(None)['last_result'])

    def test_inspection_puts_problems_first_and_maps_levels(self):
        rows = fl.inspection_rows([
            {'name': '설정 파일', 'ok': True, 'detail': 'a', 'fix': 'x'},
            {'name': '관리자 권한', 'ok': False, 'detail': 'b', 'fix': 'y', 'notice': True},
            {'name': 'DB 접속', 'ok': False, 'detail': 'c', 'fix': 'z'},
        ])
        self.assertEqual(['DB 접속', '관리자 권한', '설정 파일'], [r['item'] for r in rows])
        self.assertEqual(['bad', 'info', 'ok'], [r['level'] for r in rows])
        self.assertEqual('', rows[2]['fix'])

    def test_empty_setting_and_same_named_check_are_one_row(self):
        rows = fl.inspection_rows([{'name': '기본기능 체크리스트', 'ok': False, 'detail': '미설정', 'fix': 'x'},
                                   {'name': 'DB 접속', 'ok': False, 'detail': '실패', 'fix': 'y'}],
                                  ['기본기능 체크리스트: 값을 입력하세요.'])
        self.assertEqual(['기본기능 체크리스트', 'DB 접속'], [r['item'] for r in rows])
        self.assertEqual('값을 입력하세요.', rows[0]['result'])
        rows = fl.inspection_rows([{'name': '승인 Baseline', 'ok': False, 'detail': '미설정', 'fix': 'x'},
                                   {'name': '근거 문서', 'ok': False, 'detail': '미설정', 'fix': 'x'}],
                                  ['승인 Baseline 폴더: 값을 입력하세요.', '사양 / 매뉴얼 폴더: 값을 입력하세요.'])
        self.assertEqual(['승인 Baseline 폴더', '사양 / 매뉴얼 폴더'], [r['item'] for r in rows])

    def test_config_errors_block_both_checklists(self):
        data = fl.inspect_data([], ['Viewer 실행 파일을 입력하세요.'])
        self.assertEqual('bad', data['headline']['level'])
        self.assertTrue(all(not t['enabled'] for t in data['targets']))
        self.assertEqual(['run-regression', 'run-winupdate'], [t['key'] for t in data['targets']])

    def test_diagnostic_failures_warn_without_blocking(self):
        data = fl.inspect_data([{'name': 'DB 접속', 'ok': False, 'detail': 'x', 'fix': 'y'}])
        self.assertEqual('warn', data['headline']['level'])
        self.assertTrue(all(t['enabled'] for t in data['targets']))
        self.assertEqual('ok', fl.inspect_data([{'name': 'a', 'ok': True, 'detail': '', 'fix': ''}])['headline']['level'])

    def test_result_lists_non_pass_tcs_with_reason_and_report_button(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'Reports' / 'Result_1.html'
            record = FakeRecord(folder, {'run_id': 'R2', 'action': 'run-winupdate', 'status': 'completed',
                                         'verdicts': {'PASS': 1, 'FAIL': 1}, 'reports': [str(report)],
                                         'summary': '요약', 'next_action': '확인'},
                                [{'tc_id': 'TC_A', 'title': 'A', 'verdict': 'PASS', 'checks': []},
                                 {'tc_id': 'TC_B', 'title': 'B', 'verdict': 'FAIL',
                                  'checks': [{'status': 'PASS', 'note': '좋음'}, {'status': 'FAIL', 'note': '값이 다름\n둘째 줄'}]}])
            data = fl.result_data(record, folder)
        self.assertEqual('bad', data['headline']['level'])
        self.assertEqual([{'status': 'FAIL', 'level': 'bad', 'item': 'TC_B B', 'reason': '값이 다름'}], data['rows'])
        self.assertEqual(str(report), data['buttons'][0]['open'])

    def test_uac_cancel_is_not_shown_as_failure(self):
        record = FakeRecord('.', {'run_id': 'R3', 'action': 'run-regression', 'status': 'uac_cancelled',
                                  'verdicts': {}, 'reports': []})
        self.assertEqual('info', fl.result_data(record, '.')['headline']['level'])

    def test_progress_reads_events_of_this_run(self):
        record = FakeRecord('C:/w', {'run_id': 'R4'})
        data = fl.progress_data(record, 42, 'C:/w/stop')
        self.assertEqual(str(Path('C:/w/Runs/R4/events.jsonl')), data['events_path'])
        self.assertEqual(42, data['process_id'])


class ConsentTests(unittest.TestCase):
    def plan(self):
        return {'action': 'run-regression'}

    def test_confirm_lists_preparation_items_and_agreement(self):
        from unittest import mock
        with mock.patch('bellalunauto.runplan.format_plan', return_value='계획'), \
             mock.patch('core.run_preparation.preparation_items', return_value=[{'key': 'usb', 'label': 'USB 준비'}]):
            data = fl.confirm_data(self.plan())
        self.assertEqual(['usb', 'agree'], [c['key'] for c in data['checks']])
        self.assertEqual('계획', data['details'])
        self.assertTrue(data['toggles'][0]['value'])

    def test_consent_requires_agreement_and_keeps_restore_choice(self):
        from unittest import mock
        with mock.patch('core.run_preparation.preparation_complete', return_value=True), \
             mock.patch('core.run_preparation.validate_preparation'):
            with self.assertRaises(ValueError):
                fl.apply_consent(self.plan(), {'checked': ['usb'], 'toggles': {}})
            plan = fl.apply_consent(self.plan(), {'checked': ['usb', 'agree'], 'toggles': {'restore_after': False}})
        self.assertEqual(['usb'], plan['preparation_checked'])
        self.assertFalse(plan['restore_after'])


class EngineEventTests(unittest.TestCase):
    def test_engine_progress_appends_event_for_progress_screen(self):
        from bellalunauto.runs import engine_progress
        with tempfile.TemporaryDirectory() as folder:
            engine_progress(folder, 'R5', 'TC_A', 2, 9)
            line = json.loads((Path(folder) / 'Runs' / 'R5' / 'events.jsonl').read_text(encoding='utf-8'))
            self.assertEqual((2, 9, 'TC_A'), (line['index'], line['total'], line['tc_id']))
            engine_progress(folder, None, 'TC_A', 2, 9)  # 실행 번호가 없으면 아무것도 쓰지 않는다
            self.assertEqual(1, len((Path(folder) / 'Runs' / 'R5' / 'events.jsonl').read_text(encoding='utf-8').splitlines()))


class FlowTests(unittest.TestCase):
    """가짜 화면·가짜 실행기로 시작부터 결과까지 한 바퀴 돈다. 제품은 조작하지 않는다."""

    def test_home_inspect_confirm_progress_result_close(self):
        from types import SimpleNamespace
        from unittest import mock
        with tempfile.TemporaryDirectory() as folder:
            config_path = Path(folder) / 'config.json'
            config_path.write_text('{}', encoding='utf-8')
            layout = SimpleNamespace(config_path=config_path, workspace=Path(folder), resource_dir=Path(folder))
            record = FakeRecord(folder, {'run_id': 'R9', 'action': 'run-regression', 'status': 'completed',
                                         'verdicts': {'PASS': 2}, 'reports': [], 'summary': '', 'next_action': ''})
            record.finish = mock.Mock()
            record.annotate = mock.Mock()
            record.mark_result_seen = mock.Mock()
            record.request_stop = mock.Mock()

            class Controller:
                def __init__(self, layout, config):
                    self.config, self.record, self.reader, self.stop_path = config, None, None, None
                    self.process = SimpleNamespace(pid=7, returncode=0)
                    self.polls = 0

                @property
                def running(self):
                    self.polls += 1
                    return self.polls == 1

                def start(self, action, consent, plan):
                    assert consent and plan['preparation_checked'] == [] and plan['restore_after'] is True
                    self.record = record

            answers = iter([{'action': 'inspect'}, {'action': 'run-regression'},
                            {'action': 'start', 'checked': ['agree'], 'toggles': {'restore_after': True}},
                            {'action': 'finished'}, {'action': 'close'}])
            screens = []

            def show(data):
                screens.append(data['screen'])
                return next(answers)

            with mock.patch('bellalunauto.gui.load_gui_config', return_value={}),                  mock.patch('bellalunauto.gui.RunController', Controller),                  mock.patch('bellalunauto.gui.validate_config', return_value=[]),                  mock.patch('bellalunauto.app.diagnostics', return_value=[]),                  mock.patch('bellalunauto.runs.latest_run', return_value=None),                  mock.patch('bellalunauto.runplan.build_plan', return_value={'action': 'run-regression'}),                  mock.patch('bellalunauto.runplan.format_plan', return_value='계획'),                  mock.patch('core.run_preparation.preparation_items', return_value=[]),                  mock.patch('core.run_preparation.preparation_complete', return_value=True),                  mock.patch('core.run_preparation.validate_preparation'):
                self.assertEqual(0, fl.launch(layout, show=show))
        self.assertEqual(['home', 'inspect', 'confirm', 'progress', 'result'], screens)
        record.finish.assert_called_once_with(0)
        record.mark_result_seen.assert_called()
        record.request_stop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
