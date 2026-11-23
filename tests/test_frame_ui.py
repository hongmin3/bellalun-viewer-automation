# -*- coding: utf-8 -*-
"""공용 실행 화면(core/frame_ui) 시험. VXvue selfcheck/test_frame_ui.py와 같은 내용이다.

Validates: REQ-FRAME-002
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from core import frame_ui as ui


class ScreenDataTests(unittest.TestCase):
    def test_every_screen_carries_step_indicator_and_palette(self):
        screens = [
            ui.home('P', '무엇을 할까요?', ['한 줄'], [ui.button('inspect', '준비 점검 시작', primary=True)]),
            ui.inspect('P', '준비 점검', {'text': 'ok', 'level': 'ok'}, [], [], []),
            ui.confirm('P', '확인', ['사실'], ['동의'], '시작'),
            ui.progress('P', '진행', [], 'events.jsonl', 123),
            ui.result('P', '결과', {'text': 'ok', 'level': 'ok'}, [], [], []),
        ]
        for index, data in enumerate(screens):
            self.assertEqual(index, data['step_index'])
            self.assertEqual(list(ui.STEPS), data['steps'])
            self.assertEqual(ui.PALETTE, data['palette'])
            json.dumps(data, ensure_ascii=False)

    def test_unknown_screen_is_rejected(self):
        with self.assertRaises(ValueError):
            ui._base('wizard', 'P', 'x')

    def test_confirm_normalises_checks_and_keeps_toggles(self):
        data = ui.confirm('P', '확인', [], ['문장', {'key': 'k', 'label': '키 있음'}], '시작',
                          toggles=[{'key': 'restore', 'label': '복원', 'value': True}])
        self.assertEqual([{'key': '문장', 'label': '문장'}, {'key': 'k', 'label': '키 있음'}], data['checks'])
        self.assertEqual('restore', data['toggles'][0]['key'])
        self.assertTrue(data['buttons'][0]['primary'])

    def test_open_button_keeps_window_and_carries_path(self):
        self.assertEqual('C:/x', ui.button('report', '레포트 열기', open_path='C:/x')['open'])
        self.assertNotIn('open', ui.button('home', '처음으로'))

    def test_outcome_headline_levels(self):
        self.assertEqual('bad', ui.outcome_headline({'PASS': 3, 'FAIL': 1})['level'])
        self.assertEqual('warn', ui.outcome_headline({'PASS': 3, 'MANUAL': 1})['level'])
        self.assertEqual('ok', ui.outcome_headline({'PASS': 3, 'SKIP': 2})['level'])
        self.assertEqual('bad', ui.outcome_headline({})['level'])
        self.assertEqual('bad', ui.outcome_headline({'PASS': 3}, aborted=True)['level'])

    def test_palette_matches_report_badges(self):
        from core import report_layout
        for verdict, level in ui.VERDICT_LEVEL.items():
            self.assertIn(ui.PALETTE[level], report_layout.STYLE, verdict)


class EventTests(unittest.TestCase):
    def test_append_event_writes_one_json_line_per_call(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'run' / 'events.jsonl'
            ui.append_event(path, 'TC_A', '실행 시작', 1, 3)
            ui.append_event(path, '', '메모')
            lines = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual({'tc_id': 'TC_A', 'message': '실행 시작', 'index': 1, 'total': 3}.items() <= lines[0].items(), True)
        self.assertNotIn('total', lines[1])
        self.assertRegex(lines[0]['time'], r'^\d\d:\d\d:\d\d$')

    def test_empty_path_is_ignored(self):
        ui.append_event('', 'TC', 'x')


class ShowTests(unittest.TestCase):
    def test_show_reads_answer_and_cleans_temp_files(self):
        seen = {}

        def runner(command, **kwargs):
            seen['command'] = command
            out = command[command.index('-Out') + 1]
            source = command[command.index('-In') + 1]
            seen['payload'] = json.loads(Path(source).read_text(encoding='utf-8'))
            Path(out).write_text('{"action":"inspect"}', encoding='utf-8')
            return subprocess.CompletedProcess(command, 0, b'', b'')

        answer = ui.show(ui.home('P', 'h', [], []), runner=runner)
        self.assertEqual('inspect', answer['action'])
        self.assertEqual('home', seen['payload']['screen'])
        self.assertIn('-STA', seen['command'])
        self.assertFalse(Path(seen['command'][seen['command'].index('-In') + 1]).exists())

    def test_show_failure_is_runtime_error(self):
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, b'', b'boom')
        with self.assertRaises(RuntimeError):
            ui.show(ui.home('P', 'h', [], []), runner=runner)

    def test_script_is_ascii_so_powershell_51_reads_it(self):
        Path(ui.SCRIPT).read_bytes().decode('ascii')


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell'), 'Windows PowerShell 필요')
class RenderTests(unittest.TestCase):
    """실제 WinForms로 그려 PNG를 저장한다. 창은 그린 즉시 닫힌다."""

    def test_each_screen_renders_to_png(self):
        screens = {
            'home': ui.home('P', '무엇을 할까요?', ['한 줄'], [ui.button('inspect', '준비 점검 시작', primary=True)],
                            last_result={'text': 'PASS 1', 'level': 'ok'}),
            'inspect': ui.inspect('P', '준비 점검', {'text': '문제 1개', 'level': 'bad'},
                                  [{'status': '조치 필요', 'level': 'bad', 'item': 'DPI', 'result': '125%', 'fix': '100%'}],
                                  [ui.button('run', '실행', primary=True, enabled=False, target=True)], []),
            'confirm': ui.confirm('P', '확인', ['사실'], ['동의'], '시작', details='계획\n두 줄',
                                  toggles=[{'key': 'r', 'label': '복원', 'value': True}]),
            'result': ui.result('P', '결과', {'text': '통과', 'level': 'ok'}, ['줄'],
                                [{'status': 'MANUAL', 'level': 'warn', 'item': 'TC', 'reason': '확인'}], []),
        }
        with tempfile.TemporaryDirectory() as folder:
            events = Path(folder) / 'events.jsonl'
            ui.append_event(events, 'TC_A', '실행 시작', 1, 2)
            screens['progress'] = ui.progress('P', '진행', ['줄'], events, 0, stop_path=Path(folder) / 'stop')
            for name, data in screens.items():
                png = Path(folder) / f'{name}.png'
                self.assertEqual({'action': 'snapshot'}, ui.show(data, snapshot=png), name)
                self.assertGreater(png.stat().st_size, 5000, name)


if __name__ == '__main__':
    unittest.main()
