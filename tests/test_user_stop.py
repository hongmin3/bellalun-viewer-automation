"""화면 안전 중단의 TC 사이 정지·리포트·실행 기록(REQ-QA-002, #246 WU r2).

원본: 1.0.0.012 WU r2 `20261127-073915-7f9ee6b9`는 13/17 단계에서 안전 중단 버튼(중지 파일)을 받자
감독 프로세스가 작업 프로세스를 바로 끝냈다. 그래서 리포트가 없고(`reports: []`) 원상복원이 돌지 않았으며,
요약은 "TC를 시작하기 전에 멈췄을 수 있다"였고 `stop_requested`는 false였다.
"""
import json
from types import SimpleNamespace

import pytest

import run
from bellalunauto import app
from bellalunauto.runs import RunRecord
from core.result import FAIL, PASS, TCResult


class _Child:
    def __init__(self, polls, code=0):
        self.polls, self.returncode = list(polls), code

    def poll(self):
        return self.polls.pop(0) if self.polls else self.returncode


def _clock(step):
    state = {'now': 0.0}

    def clock():
        state['now'] += step
        return state['now']
    return clock


def test_worker_without_stop_request_returns_its_code(tmp_path):
    assert app.wait_worker(_Child([None, None], 1), tmp_path / 'stop.json', sleep=lambda _: None) == (1, None)


def test_stop_request_waits_for_worker_to_finish_its_own_cleanup(tmp_path):
    stop = tmp_path / 'stop.json'
    stop.write_text('stop', encoding='utf-8')
    child = _Child([None] * 20, 130)
    assert app.wait_worker(child, stop, grace=60, clock=_clock(1), sleep=lambda _: None) == (130, 'graceful')
    assert child.polls == []          # 바로 끝내지 않고 작업 프로세스가 끝날 때까지 기다렸다.


def test_stop_request_is_forced_only_after_grace(tmp_path):
    stop = tmp_path / 'stop.json'
    stop.write_text('stop', encoding='utf-8')
    child = _Child([None] * 1000)
    assert app.wait_worker(child, stop, grace=30, clock=_clock(1), sleep=lambda _: None) == (None, 'forced')
    assert child.polls                # 유예가 끝나 더 기다리지 않았다.


def test_engine_sees_stop_file_between_tcs_and_records_position(tmp_path, monkeypatch):
    ctx = SimpleNamespace()
    monkeypatch.delenv('BELLALUN_STOP_FILE', raising=False)
    assert run._user_stop_requested(ctx, 'TC_A', 2, 5) is False
    stop = tmp_path / 'stop.json'
    monkeypatch.setenv('BELLALUN_STOP_FILE', str(stop))
    assert run._user_stop_requested(ctx, 'TC_A', 2, 5) is False
    stop.write_text('stop', encoding='utf-8')
    assert run._user_stop_requested(ctx, 'TC_B', 3, 5) is True
    assert ctx.execution_incomplete is True
    assert {k: ctx.user_stop[k] for k in ('before_tc', 'index', 'total', 'completed_stages')} == \
        {'before_tc': 'TC_B', 'index': 3, 'total': 5, 'completed_stages': 2}
    meta = run._execution_meta(ctx)
    assert meta['user_stop']['before_tc'] == 'TC_B' and meta['chain_completed'] is False


def _wu(tc_id, missing=False):
    row = TCResult(tc_id, tc_id)
    row.add(0, '[TC_Basic_WorkFlow_09] 근거 TC 결과 없음' if missing else 'ok', FAIL if missing else PASS,
            stop=False)
    return row


@pytest.mark.parametrize('live_extra,kept', [
    (None, ['TC_WindowsUpdate_01']),
    ({'usb': {'drive': 'E:\\'}, 'wu10': None}, ['TC_WindowsUpdate_01', 'TC_WindowsUpdate_09']),
])
def test_stopped_wu_rows_leave_unrun_tcs_as_not_run_not_fail(live_extra, kept):
    rows = [_wu('TC_WindowsUpdate_01'), _wu('TC_WindowsUpdate_02', missing=True),
            _wu('TC_WindowsUpdate_09'), _wu('TC_WindowsUpdate_10')]
    assert [r.tc_id for r in run.user_stop_wu_rows(rows, live_extra)] == kept


def test_run_record_keeps_stop_request_and_progress_summary_without_report(tmp_path):
    record = RunRecord.create(tmp_path, 'run-winupdate', {}, consent=True)
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    (work / 'qa_progress.json').write_text(json.dumps(
        {'run_id': record.data['run_id'], 'current_tc': 'TC_Basic_WorkFlow_09', 'index': 14, 'total': 17}),
        encoding='utf-8')
    record.finish(130, stop_requested=True)
    data = json.loads(record.path.read_text(encoding='utf-8'))
    assert data['status'] == 'stopped' and data['stop_requested'] is True
    assert '13/17' in data['summary'] and 'TC_Basic_WorkFlow_09' in data['summary']
    assert '시작하기 전에' not in data['summary']


def test_guarded_supervisor_passes_stop_request_to_final_record(tmp_path, monkeypatch):
    record = RunRecord.create(tmp_path, 'run-winupdate', {}, consent=True)
    monkeypatch.setenv('BELLALUN_QA_RUN', record.data['run_id'])
    stop = tmp_path / 'stop.json'
    stop.write_text('stop', encoding='utf-8')
    monkeypatch.setattr(app, '_run_guarded_impl', lambda *a: app.USER_STOP_EXIT)
    assert app.run_guarded(SimpleNamespace(workspace=tmp_path), ['run-winupdate'], stop) == 130
    data = json.loads(record.path.read_text(encoding='utf-8'))
    assert data['status'] == 'stopped' and data['stop_requested'] is True
