"""WF_02 실제 run 경로의 촬영 대기. UI/SQL을 대체하며 화면에 접근하지 않는다.

Validates: REQ-REGRESSION-001. 후보8의 85.196초 완료 기록을 바탕으로
Recon/Syn 도착을 84초로 재현한다. 기존 기대값·FAIL 조건은 그대로 검사한다.
"""
from types import SimpleNamespace

import pytest

from core import flows, viewer_processing as vp, viewer_tools
from tests import workflow02 as wf


class AcquisitionDb:
    def __init__(self, clock, delays, missing=False, unrelated=False):
        self.clock = clock
        self.delays = delays
        self.missing = missing
        self.unrelated = unrelated
        self.shots = {}

    def instances(self):
        rows = []
        for step, started in self.shots.items():
            age = self.clock.time() - started
            types = [0] if step == 1 else [1, 2, 3]
            for kind in types:
                ready = 1 if kind in (0, 1) else self.delays.get(step, 22)
                if age < ready or (self.missing and step == 3 and kind in (2, 3)):
                    continue
                key = step * 10 + kind
                rows.append({'Key': key, 'InstanceType': kind, 'SeriesKey': step,
                             'GroupKey': step, 'InstanceNumber': 1,
                             'ImageInstanceUID': f'1.2.3.{key}'})
        if self.unrelated and 3 in self.shots and self.clock.time() - self.shots[3] >= 10:
            for kind in (2, 3):
                rows.append({'Key': 90 + kind, 'InstanceType': kind, 'SeriesKey': 2,
                             'GroupKey': 2, 'InstanceNumber': 2,
                             'ImageInstanceUID': f'1.2.3.{90 + kind}'})
        return rows

    def query(self, database, sql, params=None):
        rows = self.instances()
        if 'GROUP BY InstanceType' in sql:
            return [{'InstanceType': kind, 'Cnt': sum(r['InstanceType'] == kind for r in rows)}
                    for kind in sorted({r['InstanceType'] for r in rows})]
        if 'FROM INSTANCE_GROUP' in sql:
            return [{'Key': step, 'Type': int(step != 1), 'ExposureMode': step - 1,
                     'SeriesKey': step, 'StereoType': 0, 'SortOrder': step}
                    for step, started in self.shots.items() if self.clock.time() - started >= 1]
        if 'FROM SERIES' in sql:
            return [{'Key': step, 'SeriesInstanceUID': f'1.2.4.{step}'}
                    for step in sorted({r['SeriesKey'] for r in rows})]
        if 'FROM INSTANCE' in sql:
            if params and 'grp' in params:
                rows = [r for r in rows if r['GroupKey'] == params['grp']]
            return rows
        raise AssertionError(f'예상 밖 SQL: {sql}')

    def one(self, database, sql, params=None):
        return {'StudyStatus': 0, 'Instances': len(self.instances())}


def run_acquisition(monkeypatch, delays, *, missing=False, skipped=False, unrelated=False):
    clock = SimpleNamespace(now=0.0)
    clock.time = lambda: clock.now
    clock.sleep = lambda seconds: setattr(clock, 'now', clock.now + seconds)
    for module in (wf, flows, vp):
        monkeypatch.setattr(module, 'time', clock)
    db = AcquisitionDb(clock, delays, missing, unrelated)
    state = SimpleNamespace(steps=0)
    ui = SimpleNamespace(by_id=lambda _id: [], main_window=lambda: None)
    ctx = SimpleNamespace(db=db, cfg={'viewer': {'demo_mode': True}}, evidence_root='unused')

    def acquire(ui, index, **kwargs):
        if skipped and index == 3:
            return {'step': index, 'ready': False, 'skipped': True}
        db.shots[index] = clock.time()
        return {'step': index, 'ready': True, 'skipped': False}

    patches = [
        (wf, '_study', lambda ctx: {'Key': 48, 'StudyStatus': 4, 'StudyDate': '20261106', 'StudyTime': '000000'}),
        (wf, '_study_card_number', lambda *a: 1),
        (wf, '_open_suspended', lambda *a: 1),
        (wf, '_capture', lambda *a: None),
        (wf, '_examined_search', lambda *a: [object()]),
        (flows, 'cold_start', lambda *a, **k: (ui, {})),
        (flows, 'ensure_patient_screen', lambda *a, **k: True),
        (flows, 'read_edit_information', lambda *a: {'patient_id': wf.PATIENT_ID, 'patient_name': 'AUTO MWL', 'study_datetime': '20261106000000'}),
        (flows, 'step_items', lambda *a: list(range(state.steps))),
        (flows, 'demo_acquire_step', acquire),
        (flows, 'select_step', lambda *a: None),
        (flows, 'close_examine', lambda *a, **k: {}),
        (vp, 'ensure_tc01_overlay', lambda *a: None),
        (vp, 'add_view_position', lambda *a: setattr(state, 'steps', state.steps + 1)),
        (viewer_tools, 'apply_tool_sequence', lambda *a, **k: []),
        (viewer_tools, 'select_recon', lambda *a: None),
    ]
    for module, name, value in patches:
        monkeypatch.setattr(module, name, value)
    result = wf.run(ctx)
    return result, clock, db


@pytest.mark.parametrize('delayed_step', [2, 3])
def test_delayed_recon_syn_reaches_existing_wf02_assertions(monkeypatch, delayed_step):
    result, clock, db = run_acquisition(monkeypatch, {delayed_step: 84})
    checks = {check.title: check for check in result.checks}
    title = ('3D Raw/Recon/Syn 영상 데이터 생성' if delayed_step == 2
             else '3D-W 영상 데이터 생성 (픽스처 확장)')
    assert checks[title].status == 'PASS', checks[title].actual
    assert not result.aborted
    wide = checks['3D-W 영상 데이터 생성 (픽스처 확장)'].actual
    assert wide['instance_types'] == {0: 1, 1: 2, 2: 2, 3: 2}


def test_missing_recon_syn_remains_fail(monkeypatch):
    result, clock, db = run_acquisition(monkeypatch, {}, missing=True)
    check = next(c for c in result.checks if c.title == '3D-W 영상 데이터 생성 (픽스처 확장)')
    assert check.status == 'FAIL'
    assert check.actual['instance_types'] == {0: 1, 1: 2, 2: 1, 3: 1}
    assert clock.now < 240, '타임아웃 뒤 별도 75초 대기를 다시 수행하지 않는다'


def test_skipped_exposure_never_passes_on_previous_group(monkeypatch):
    result, clock, db = run_acquisition(monkeypatch, {}, skipped=True)
    check = next(c for c in result.checks if c.title == '3D-W 영상 데이터 생성 (픽스처 확장)')
    assert check.status == 'FAIL'
    assert 3 not in db.shots
    assert clock.now < 40, '촬영하지 않았으면 새 영상 도착을 기다리지 않는다'


def test_old_group_results_cannot_complete_the_current_shot(monkeypatch):
    result, clock, db = run_acquisition(monkeypatch, {}, missing=True, unrelated=True)
    check = next(c for c in result.checks if c.title == '3D-W 영상 데이터 생성 (픽스처 확장)')
    assert check.actual['instance_types'] == {0: 1, 1: 2, 2: 2, 3: 2}
    assert check.status == 'FAIL', '전체 건수가 같아도 이번 그룹에 Recon/Syn이 없으면 실패'


def test_fast_completion_returns_without_sleeping_to_timeout(monkeypatch):
    result, clock, db = run_acquisition(monkeypatch, {2: 3, 3: 4})
    assert not result.aborted
    assert clock.now < 15
