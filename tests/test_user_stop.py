"""화면 안전 중단의 TC 사이 정지·리포트·실행 기록(REQ-QA-002, #246 WU r2).

원본: 1.0.0.012 WU r2 `20261127-073915-7f9ee6b9`는 13/17 단계에서 안전 중단 버튼(중지 파일)을 받자
감독 프로세스가 작업 프로세스를 바로 끝냈다. 그래서 리포트가 없고(`reports: []`) 원상복원이 돌지 않았으며,
요약은 "TC를 시작하기 전에 멈췄을 수 있다"였고 `stop_requested`는 false였다.
"""
import json
import threading
import time
from types import SimpleNamespace

import pytest

import run
from bellalunauto import app
from bellalunauto.runs import RunRecord
from core import wu_chain
from core.result import BLOCKED, FAIL, PASS, TCResult


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


def test_stage_monitor_sees_stop_request_before_any_limit():
    """2026-11-27 사용자 결정: 진행 중인 TC를 끝까지 기다리지 않는다."""
    monitor = wu_chain.StageMonitor('S', 3600, clock=lambda: 0.0, responding=lambda pid: True,
                                    pid_getter=lambda: 1, stop_requested=lambda: True)
    monitor._started = 0.0
    kind, reason = monitor.check_once()
    assert kind == 'user_stop' and '안전 중단' in reason


def test_stage_monitor_default_reads_stop_file(tmp_path, monkeypatch):
    stop = tmp_path / 'stop.json'
    monkeypatch.setenv('BELLALUN_STOP_FILE', str(stop))
    monitor = wu_chain.StageMonitor('S', 3600, clock=lambda: 0.0, responding=lambda pid: True,
                                    pid_getter=lambda: 1)
    monitor._started = 0.0
    assert monitor.check_once() is None
    stop.write_text('stop', encoding='utf-8')
    assert monitor.check_once()[0] == 'user_stop'


def _real_monitor(*args, **kwargs):
    return wu_chain.StageMonitor(*args, responding=lambda pid: True, pid_getter=lambda: None,
                                 poll=0.01, **kwargs)


def _guarded(fn, ctx, tc_id, title):
    return run.guarded(fn, ctx, tc_id, title)


def test_running_tc_is_cut_quickly_without_failure_evidence(tmp_path, monkeypatch):
    stop = tmp_path / 'stop.json'
    monkeypatch.setenv('BELLALUN_STOP_FILE', str(stop))
    killed, evidence = threading.Event(), []

    def stage(ctx):
        stop.write_text('stop', encoding='utf-8')     # 이 TC가 도는 중에 중단 버튼을 눌렀다.
        if not killed.wait(5):                       # UI 대기는 Viewer가 끝나면 예외로 빠져나온다.
            return []
        raise RuntimeError('Viewer 종료됨')

    started = time.monotonic()
    produced, trip = wu_chain.run_stage(
        stage, SimpleNamespace(cfg={}), 'TC_Basic_WorkFlow_04', '2D Send', guarded=_guarded,
        timeout=3600, monitor_factory=_real_monitor, kill=killed.set, interrupt=lambda: None,
        before_kill=lambda m: evidence.append(m.kind))
    assert time.monotonic() - started < 3
    assert trip['kind'] == 'user_stop' and evidence == []
    assert [r.verdict for r in produced] == [BLOCKED]
    assert '사용자 안전 중단' in produced[0].checks[0].title


def test_tc_ignoring_viewer_exit_is_interrupted_after_short_grace(tmp_path, monkeypatch):
    stop = tmp_path / 'stop.json'
    monkeypatch.setenv('BELLALUN_STOP_FILE', str(stop))

    def stuck(ctx):
        stop.write_text('stop', encoding='utf-8')
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:           # Viewer가 없어도 빠져나오지 않는 코드
            time.sleep(0.01)
        return []

    started = time.monotonic()
    produced, trip = wu_chain.run_stage(
        stuck, SimpleNamespace(cfg={}), 'TC_Basic_WorkFlow_04', '2D Send', guarded=_guarded,
        timeout=3600, monitor_factory=_real_monitor, kill=lambda: None, user_grace=0.2)
    assert time.monotonic() - started < 3             # 주 스레드 중단 신호로 바로 빠져나왔다.
    assert trip['kind'] == 'user_stop'
    assert [r.verdict for r in produced] == [BLOCKED]


@pytest.mark.parametrize('stage_id,earlier', [
    ('TC_Basic_WorkFlow_01', ()),
    ('TC_Basic_WorkFlow_02', ('TC_Basic_WorkFlow_01',)),
    ('TC_Basic_WorkFlow_03', ()),
    ('TC_Basic_WorkFlow_06', ('TC_Basic_WorkFlow_04', 'TC_Basic_WorkFlow_05')),
    ('TC_Basic_WorkFlow_08', ()),
    ('TC_XIPL_compatibility_subset', ()),
])
def test_wu_partial_report_keeps_interrupted_stage_once(tmp_path, monkeypatch, stage_id, earlier):
    from contextlib import nullcontext

    ctx = SimpleNamespace(root=tmp_path, cfg={}, partial_results=[_wu(tc_id) for tc_id in earlier])
    interrupted = wu_chain.blocked_results(stage_id, '재현', 'user_stop', '사용자 안전 중단')
    report = []

    def finish(_ctx, rows, _elapsed, **_kwargs):
        report.extend(rows)

    monkeypatch.delenv('BELLALUN_STOP_FILE', raising=False)
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    monkeypatch.setattr(run, '_wu_chain_stages', lambda: [(None, stage_id, '재현')])
    monkeypatch.setattr(run, '_wu_preflight', lambda _ctx: {
        'blocked': False, 'items': [], 'environment': {}, 'fingerprint': {}})
    monkeypatch.setattr(run, 'shutdown_viewer', lambda *_: {})
    monkeypatch.setattr(run, '_finish_winupdate', finish)
    monkeypatch.setattr(wu_chain, 'keep_awake', nullcontext)
    monkeypatch.setattr(wu_chain, 'run_stage', lambda *args, **kwargs: (interrupted, {'kind': 'user_stop', 'reason': '사용자 안전 중단'}))
    monkeypatch.setattr('core.env_preflight.summary_for_report', lambda _: {})

    assert run._run_winupdate_chain_impl(ctx) == 130
    blocked = [row for row in report if row.verdict == BLOCKED]
    assert all(row.verdict != FAIL for row in report)
    assert [row.tc_id for row in blocked] == [stage_id]
    assert all(row.checks[0].actual['kind'] == 'user_stop' for row in blocked)
    assert not any(row.tc_id in ('TC_WindowsUpdate_09', 'TC_WindowsUpdate_10') for row in report)
