"""Validates: REQ-FOLLOWUP-003. 무인 신호 판별·사람 입력 취소·자동 닫힘 알림과 확인 안 한 결과 기록."""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class Scheduler:
    def __init__(self):
        self.pending = {}
        self.next_id = 0

    def after(self, delay, callback):
        self.next_id += 1
        self.pending[self.next_id] = callback
        return self.next_id

    def after_cancel(self, token):
        self.pending.pop(token, None)

    def tick(self):
        _, callback = self.pending.popitem()
        callback()


def make_timer(unattended):
    from bellalunauto.auto_close import CompletionAutoClose
    scheduler, now, updates, closed = Scheduler(), [100.0], [], []
    timer = CompletionAutoClose(scheduler, lambda: closed.append(True), updates.append,
                                clock=lambda: now[0], unattended=unattended)
    return timer, scheduler, now, updates, closed


@pytest.mark.parametrize('option,environ,expected', [
    (True, {}, 'option'),
    (False, {'QA_AUTOMATION_UNATTENDED': '1'}, 'environment'),
    (True, {'QA_AUTOMATION_UNATTENDED': '1'}, 'option'),
    (False, {}, None),
    (False, {'QA_AUTOMATION_UNATTENDED': '0'}, None),
    (False, {'QA_AUTOMATION_UNATTENDED': 'true'}, None),
    (False, {'QA_AUTOMATION_UNATTENDED': ''}, None),
    (False, {'QA_AUTOMATION_UNATTENDED': ' 1'}, None),
])
def test_unattended_comes_only_from_explicit_signal(option, environ, expected):
    from bellalunauto.auto_close import unattended_signal
    assert unattended_signal(option, environ) == expected


def test_mode_labels_match_the_shared_wording():
    from bellalunauto.auto_close import mode_label
    assert mode_label(False) == '자동 닫기 꺼짐(사람 실행)'
    assert mode_label(True) == '60초 뒤 자동 닫힘(무인 실행)'
    assert mode_label(True, 7) == '7초 뒤 자동 닫힘(무인 실행)'


def test_human_run_never_arms_even_after_complete_regression():
    timer, scheduler, now, updates, closed = make_timer(False)
    assert not timer.start({'action': 'run-regression', 'status': 'completed', 'exit_code': 0})
    now[0] = 10_000
    assert not timer.active and not scheduler.pending and not closed


def test_unattended_run_closes_at_sixty_seconds():
    timer, scheduler, now, updates, closed = make_timer(True)
    assert timer.start({'action': 'run-winupdate', 'status': 'completed', 'exit_code': 1})
    assert updates[-1] == 60
    now[0] = 160
    scheduler.tick()
    assert closed == [True]


def test_interaction_cancels_only_this_round_and_old_callback_cannot_close():
    timer, scheduler, now, updates, closed = make_timer(True)
    completed = {'action': 'run-regression', 'status': 'completed'}
    timer.start(completed)
    old = next(iter(scheduler.pending.values()))
    assert timer.interaction() is True
    assert not timer.active and not scheduler.pending and updates[-1] is None
    now[0] = 1_000
    old()
    assert not closed
    # 새 회귀 완료 때만 다시 시작하고, 예전 콜백은 새 회차도 닫지 못한다.
    timer.start(completed)
    now[0] = 1_100
    old()
    assert not closed and timer.active


def test_interaction_without_countdown_does_nothing():
    timer, scheduler, _, updates, closed = make_timer(True)
    assert timer.interaction() is False
    assert updates == [] and not scheduler.pending and not closed


def record(**extra):
    data = {'run_id': '20261116-120000-abcdef12', 'action': 'run-regression', 'status': 'completed',
            'verdicts': {'PASS': 15, 'FAIL': 1, 'SKIP': 2},
            'reports': [r'C:\작업\Reports\Result_20261116.json', r"C:\작업\Reports\Result_<O'Neil>&.html"]}
    data.update(extra)
    return data


def test_verdict_totals_always_list_five_verdicts_and_keep_others():
    from bellalunauto.completion_notice import verdict_totals
    assert verdict_totals({'PASS': 2}) == 'PASS 2 / FAIL 0 / MANUAL 0 / SKIP 0 / BLOCKED 0'
    assert verdict_totals({'FAIL': 1, 'UNKNOWN': 3}) == 'PASS 0 / FAIL 1 / MANUAL 0 / SKIP 0 / BLOCKED 0 / UNKNOWN 3'
    assert verdict_totals(None) == 'PASS 0 / FAIL 0 / MANUAL 0 / SKIP 0 / BLOCKED 0'


def test_toast_xml_holds_run_id_totals_and_html_report_escaped():
    import xml.etree.ElementTree as ET
    from bellalunauto.completion_notice import toast_xml
    texts = [node.text for node in ET.fromstring(toast_xml(record())).iter('text')]
    assert len(texts) == 3
    assert '20261116-120000-abcdef12' in texts[1]
    assert 'PASS 15 / FAIL 1 / MANUAL 0 / SKIP 2 / BLOCKED 0' in texts[1]
    assert texts[2] == "리포트: C:\\작업\\Reports\\Result_<O'Neil>&.html"


def test_toast_script_is_encoded_and_quotes_xml_literal():
    import base64
    from bellalunauto.completion_notice import toast_command, POWERSHELL_AUMID
    argv = toast_command(record())
    assert argv[:2] == ['powershell', '-NoProfile'] and argv[-2] == '-EncodedCommand'
    script = base64.b64decode(argv[-1]).decode('utf-16-le')
    assert "O''Neil" in script and 'ToastNotificationManager' in script
    assert POWERSHELL_AUMID in script and "'20261116-120000-abcdef12'" in script


@pytest.mark.parametrize('outcome,reason', [
    (subprocess.CompletedProcess([], 0, stdout='', stderr=''), None),
    (subprocess.CompletedProcess([], 1, stdout='', stderr='Exception'), 'exit-1'),
    (subprocess.TimeoutExpired('powershell', 20), 'timeout'),
    (FileNotFoundError('powershell'), 'FileNotFoundError'),
])
def test_show_reports_result_and_never_raises(outcome, reason):
    from bellalunauto.completion_notice import show

    def runner(*args, **kwargs):
        assert kwargs['timeout'] > 0 and kwargs['stdin'] == subprocess.DEVNULL
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    result = show(record(), runner=runner)
    assert result['status'] == ('shown' if reason is None else 'failed')
    assert result.get('reason') == reason
    assert result['at']


def test_run_record_keeps_auto_close_trace_and_finds_latest_unseen(tmp_path):
    from bellalunauto.runs import RunRecord, latest_unseen
    older = RunRecord.create(tmp_path, 'run-regression', {})
    older.data['run_id'] = '20261116-100000-aaaaaaaa'
    older.path = tmp_path / 'Runs' / older.data['run_id'] / 'run.json'
    older.save()
    newer = RunRecord.create(tmp_path, 'run-winupdate', {})
    newer.data['run_id'] = '20261116-110000-bbbbbbbb'
    newer.path = tmp_path / 'Runs' / newer.data['run_id'] / 'run.json'
    newer.save()
    assert latest_unseen(tmp_path) is None
    older.record_auto_close({'mode': 'unattended', 'signal': 'option',
                             'notification': {'status': 'failed', 'reason': 'timeout'}})
    saved = json.loads(older.path.read_text(encoding='utf-8'))
    assert saved['result_seen'] is False
    assert saved['auto_close']['notification'] == {'status': 'failed', 'reason': 'timeout'}
    assert saved['auto_close']['closed_at']
    assert latest_unseen(tmp_path).data['run_id'] == older.data['run_id']
    newer.record_auto_close({'mode': 'unattended', 'signal': 'environment', 'notification': {'status': 'shown'}})
    assert latest_unseen(tmp_path).data['run_id'] == newer.data['run_id']
    newer.mark_result_seen()
    assert json.loads(newer.path.read_text(encoding='utf-8'))['result_seen'] is True
    assert latest_unseen(tmp_path).data['run_id'] == older.data['run_id']


def test_main_passes_option_or_environment_signal_to_gui(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from bellalunauto import app, gui
    calls = []
    monkeypatch.setattr(app, 'resolve_layout', lambda **kwargs: SimpleNamespace(workspace=tmp_path))
    from bellalunauto import frame_launch
    monkeypatch.setattr(gui, 'launch', lambda layout, **kwargs: calls.append(kwargs) or 0)
    # 사람 실행은 공용 화면으로 간다(REQ-FRAME-002). 무인 실행만 기존 화면에 신호를 넘긴다.
    monkeypatch.setattr(frame_launch, 'launch', lambda layout, **kwargs: calls.append('frame') or 0)
    monkeypatch.delenv('QA_AUTOMATION_UNATTENDED', raising=False)
    assert app.main(['--unattended']) == 0
    assert app.main([]) == 0
    monkeypatch.setenv('QA_AUTOMATION_UNATTENDED', '1')
    assert app.main([]) == 0
    assert [call if call == 'frame' else call.get('unattended') for call in calls] == ['option', 'frame', 'environment']


def test_unattended_wrappers_pass_the_signal(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('launch_gui', ROOT / 'tools' / 'launch_gui.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    exe = tmp_path / 'BellalunAuto.exe'
    assert launcher.build_command(exe, tmp_path / '작업') == [str(exe), '--workspace', str(tmp_path / '작업'), '--unattended']
    assert launcher.child_environment({'PATH': 'x'})['QA_AUTOMATION_UNATTENDED'] == '1'

    spec = importlib.util.spec_from_file_location('run_installed_suites', ROOT / 'tools' / 'run_installed_suites.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner.suite_environment({'PATH': 'x'})['QA_AUTOMATION_UNATTENDED'] == '1'

    source = (ROOT / 'remote' / 'winrm_executor.py').read_text(encoding='utf-8')
    assert "$env:QA_AUTOMATION_UNATTENDED='1'" in source
