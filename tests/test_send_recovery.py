"""REQ-REGRESSION-001: 후발 Queue와 공유 SCP 수신 관측의 오프라인 재현."""
import io
import json
import struct
import zipfile
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from core import send_verify as sv, storagescp
from core.result import TCResult, StepFailed


def clock(monkeypatch):
    timer = SimpleNamespace(now=0.0)
    timer.time = lambda: timer.now
    timer.sleep = lambda seconds: setattr(timer, 'now', timer.now + seconds)
    monkeypatch.setattr(sv, 'time', timer)
    return timer


class QueueDb:
    def __init__(self, timer, late_done=14, missing=False, late_registration=2):
        self.timer, self.late_done, self.missing = timer, late_done, missing
        self.late_registration = late_registration

    def query(self, database, sql, params=None):
        assert database == 'DATA'
        rows = [dict(Key=14, State=7, InstanceUID='1.2.1', DataType=0),
                dict(Key=15, State=7, InstanceUID='1.2.2', DataType=0)]
        if self.timer.now >= self.late_registration and not self.missing:
            rows.append(dict(Key=16, State=7 if self.timer.now >= self.late_done else 1,
                             InstanceUID='1.2.3', DataType=0))
        return rows


def test_first_queue_batch_does_not_finish_before_delayed_last_source(monkeypatch):
    timer = clock(monkeypatch)
    ctx = SimpleNamespace(db=QueueDb(timer))
    # 실제 구 API 경로를 먼저 검사한다. 첫 2개를 반환하면 후발 16을 누락한다.
    keys = sv.wait_queue_registered(ctx, set(), wait=20, poll=1)
    assert keys == [14, 15, 16]


def test_expected_source_coverage_and_late_done_are_both_required(monkeypatch):
    timer = clock(monkeypatch)
    ctx = SimpleNamespace(db=QueueDb(timer, late_registration=7))
    keys = sv.wait_queue_registered(ctx, set(), wait=20, poll=1,
                                    expected_uids={'1.2.1', '1.2.2', '1.2.3'})
    states = sv.wait_queue_settled(ctx, keys, wait=20, poll=1)
    assert keys == [14, 15, 16]
    assert states[16] == 7
    assert timer.now >= 14


def dicom_blob(patient='TEST', study='1.2', sop='1.2.1', sop_class=sv.SOP_CLASS_DBT):
    tags = [(0x0008, 0x0016, 'UI', sop_class),
            (0x0008, 0x0018, 'UI', sop), (0x0010, 0x0020, 'LO', patient),
            (0x0020, 0x000D, 'UI', study), (0x0020, 0x000E, 'UI', '1.2.9')]
    data = b'\0' * 128 + b'DICM'
    # Explicit VR little endian의 File Meta Transfer Syntax.
    tags.insert(0, (0x0002, 0x0010, 'UI', '1.2.840.10008.1.2.1'))
    fields = []
    for group, element, vr, value in tags:
        raw = value.encode('ascii')
        raw += b'\0' if len(raw) % 2 else b''
        fields.append(struct.pack('<HH', group, element) + vr.encode() + struct.pack('<H', len(raw)) + raw)
    return data + struct.pack('<HH2sHI', 2, 0, b'UL', 4, len(fields[0])) + b''.join(fields)


def archive(*blobs):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zf:
        for index, blob in enumerate(blobs):
            zf.writestr(f'{index}.dcm', blob)
    return output.getvalue()


def server(monkeypatch, *, studies=None, blob=None, failure=None):
    srv = storagescp.StorageServer('http://offline.invalid')
    studies = studies if studies is not None else [dict(patient_id='TEST', study_instance_uid='1.2', instance_count=1)]
    def request(path, method='GET'):
        if failure:
            raise failure
        return studies
    monkeypatch.setattr(srv, '_req', request)
    monkeypatch.setattr(srv, '_bytes', lambda path, timeout=None: blob if blob is not None else archive(dicom_blob()))
    monkeypatch.setattr(storagescp, 'server', lambda ctx: srv)
    return srv


def test_http_observation_failure_is_not_normal_empty_result(monkeypatch):
    server(monkeypatch, failure=HTTPError('http://private/secret?patient=NAME', 503, 'private NAME', {}, None))
    with pytest.raises(storagescp.StorageScpError) as error:
        sv.wait_received_stable(SimpleNamespace(), 'TEST', wait=0)
    assert error.value.diagnostics['status'] == 'http_error'
    assert 'NAME' not in str(error.value)
    assert 'private' not in json.dumps(error.value.diagnostics)


def test_invalid_zip_is_diagnosed_without_response_body(monkeypatch):
    server(monkeypatch, blob=b'patient=PRIVATE; not a zip')
    with pytest.raises(storagescp.StorageScpError) as error:
        sv.received(SimpleNamespace(), 'TEST')
    evidence = error.value.diagnostics
    assert evidence['status'] == 'zip_error'
    assert evidence['downloads'][0]['sha256']
    assert evidence['observed_at']
    assert 'PRIVATE' not in str(error.value) + json.dumps(evidence)


def test_corrupt_dicom_cannot_disappear_in_study_filter(monkeypatch):
    server(monkeypatch, blob=archive(b'\0' * 128 + b'DICMbroken'))
    with pytest.raises(storagescp.StorageScpError) as error:
        sv.received(SimpleNamespace(), 'TEST')
    assert error.value.diagnostics['status'] == 'parse_error'
    assert error.value.diagnostics['parse_errors']


def test_patient_filter_excludes_historical_study_before_download(monkeypatch):
    srv = server(monkeypatch, studies=[
        dict(patient_id='TEST', study_instance_uid='9.9', instance_count=10),
        dict(patient_id='OTHER', study_instance_uid='8.8', instance_count=1),
        dict(patient_id='TEST', study_instance_uid='1.2', instance_count=1)])
    def download(uid, timeout=180):
        if uid != '1.2':
            raise AssertionError('과거 또는 타 환자의 ZIP을 내려받았다')
        return archive(dicom_blob())
    monkeypatch.setattr(srv, 'download', download)
    evidence = {}
    objects = sv.received(SimpleNamespace(), 'TEST', study_uids={'1.2'}, diagnostics=evidence)
    assert [o['SOPInstanceUID'] for o in objects] == ['1.2.1']
    assert evidence['studies_before_filter'] == 3
    assert evidence['studies_after_filter'] == 1
    assert evidence['objects_before_filter'] == evidence['objects_after_filter'] == 1


def test_normal_zero_is_distinct_from_current_study_mismatch(monkeypatch):
    server(monkeypatch, studies=[])
    evidence = {}
    assert sv.received(SimpleNamespace(), 'TEST', study_uids={'1.2'}, diagnostics=evidence) == []
    assert evidence['status'] == 'empty'
    server(monkeypatch, studies=[dict(patient_id='TEST', study_instance_uid='9.9', instance_count=1)])
    evidence = {}
    assert sv.received(SimpleNamespace(), 'TEST', study_uids={'1.2'}, diagnostics=evidence) == []
    assert evidence['status'] == 'study_mismatch'


def test_downloaded_identity_mismatch_remains_failure(monkeypatch):
    server(monkeypatch, blob=archive(dicom_blob(patient='OTHER', study='9.9')))
    with pytest.raises(storagescp.StorageScpError) as error:
        sv.received(SimpleNamespace(), 'TEST', study_uids={'1.2'})
    assert error.value.diagnostics['status'] == 'identity_mismatch'


def test_non_dicom_archive_is_parse_failure_not_zero(monkeypatch):
    server(monkeypatch, blob=archive(b'not dicom'))
    with pytest.raises(storagescp.StorageScpError) as error:
        sv.received(SimpleNamespace(), 'TEST')
    assert error.value.diagnostics['status'] == 'parse_error'


def test_direct_caller_error_contains_safe_observation_evidence(monkeypatch):
    server(monkeypatch, blob=b'PRIVATE invalid ZIP')
    with pytest.raises(storagescp.StorageScpError) as error:
        sv.received(SimpleNamespace(), 'TEST')
    # workflow05/06/07/15는 기존 TC.abort가 str(exc)를 저장한다.
    assert 'zip_error' in str(error.value)
    assert 'sha256' in str(error.value)
    assert 'PRIVATE' not in str(error.value)


class SendDb(QueueDb):
    def __init__(self, timer, missing=False):
        super().__init__(timer, missing=missing, late_registration=7)
        self.started = False

    def query(self, database, sql, params=None):
        if 'FROM INSTANCE' in sql:
            return [dict(ImageInstanceUID=f'1.2.{index}', InstanceType=kind,
                         SeriesInstanceUID='1.2.9', StudyInstanceUID='1.2')
                    for index, kind in [(1, 0), (2, 2), (3, 2)]]
        return super().query(database, sql, params) if self.started else []

    def one(self, database, sql, params=None):
        return {'StationName': ''}


def send_context(monkeypatch, *, missing=False, blob=None, studies=None):
    timer = clock(monkeypatch)
    db = SendDb(timer, missing)
    ctx = SimpleNamespace(db=db, cfg={})
    server(monkeypatch, studies=studies, blob=blob if blob is not None else archive(
        dicom_blob(sop='1.2.1'), dicom_blob(sop='1.2.2'), dicom_blob(sop='1.2.3')))
    def send(scope):
        db.started = True
        return scope
    return timer, ctx, send


def test_public_send_waits_all_original_sops_then_checks_actual_objects(monkeypatch):
    timer, ctx, sender = send_context(monkeypatch)
    result = TCResult('OFFLINE', '전송 재현')
    outcome = sv.send_and_verify(ctx, None, result, 'TEST', scope='all', wait=20, sender=sender)
    assert outcome['queue_added'] == [14, 15, 16]
    assert outcome['received_objects'] == 3
    assert outcome['observation']['status'] == 'ok'
    assert timer.now >= 14
    assert all(check.status != 'FAIL' for check in result.checks)


def test_missing_last_source_fails_queue_even_if_visible_rows_are_done(monkeypatch):
    _, ctx, sender = send_context(monkeypatch, missing=True)
    result = TCResult('OFFLINE', '누락 재현')
    with pytest.raises(StepFailed):
        sv.send_and_verify(ctx, None, result, 'TEST', scope='all', wait=20,
                           sender=sender, study_key=11)
    check = result.checks[-1]
    assert check.step == 3 and check.status == 'FAIL'
    assert check.actual['observation']['queue_missing_images'] == 1


def test_public_send_observation_error_is_fail_with_evidence_not_received_zero(monkeypatch):
    _, ctx, sender = send_context(monkeypatch, blob=b'PRIVATE not a zip')
    result = TCResult('OFFLINE', '관측 실패 재현')
    with pytest.raises(StepFailed):
        sv.send_and_verify(ctx, None, result, 'TEST', scope='all', wait=20, sender=sender)
    check = result.checks[-1]
    assert check.step == 4 and check.status == 'FAIL'
    assert check.actual['status'] == 'zip_error'
    assert 'received_objects' not in check.actual


def test_requested_tag_subset_preserves_objects_public_contract(monkeypatch):
    srv = server(monkeypatch)
    assert srv.objects(study_uids=['1.2'], tags=['SOPInstanceUID'])[0]['SOPInstanceUID'] == '1.2.1'


class MultiStudyDb(SendDb):
    def query(self, database, sql, params=None):
        if 'FROM INSTANCE' in sql:
            current = super().query(database, sql, params)
            other = [dict(ImageInstanceUID='9.9.1', InstanceType=0,
                          SeriesInstanceUID='9.9.9', StudyInstanceUID='9.9')]
            return current if params.get('study') == 11 else current + other
        return super().query(database, sql, params)


def multi_study_context(monkeypatch, *, missing=False):
    timer, ctx, _ = send_context(monkeypatch, missing=missing)
    ctx.db = MultiStudyDb(timer, missing=missing)
    def send(scope):
        ctx.db.started = True
        return scope
    return timer, ctx, send


def test_legacy_all_sender_does_not_require_another_studys_queue(monkeypatch):
    _, ctx, sender = multi_study_context(monkeypatch)
    result = TCResult('OFFLINE', '복수 Study 기존 호출')
    outcome = sv.send_and_verify(ctx, None, result, 'TEST', scope='all', wait=20, sender=sender)
    assert outcome['queue_added'] == [14, 15, 16]
    assert outcome['received_objects'] == 3


def test_confirmed_study_requires_its_original_sops_without_other_study(monkeypatch):
    _, ctx, sender = multi_study_context(monkeypatch)
    result = TCResult('OFFLINE', '확인된 Study 호출')
    outcome = sv.send_and_verify(ctx, None, result, 'TEST', scope='all', wait=20,
                                 sender=sender, study_key=11)
    assert outcome['queue_added'] == [14, 15, 16]
    assert result.checks[0].actual['observation']['queue_expected_images'] == 3


def test_confirmed_study_still_fails_for_missing_original_sop(monkeypatch):
    _, ctx, sender = multi_study_context(monkeypatch, missing=True)
    result = TCResult('OFFLINE', '확인된 Study 누락')
    with pytest.raises(StepFailed):
        sv.send_and_verify(ctx, None, result, 'TEST', scope='all', wait=20,
                           sender=sender, study_key=11)
    assert result.checks[-1].actual['observation']['queue_missing_images'] == 1


def test_identity_type_and_receive_scope_follow_confirmed_study(monkeypatch):
    _, ctx, _ = multi_study_context(monkeypatch)
    assert sv.db_identity(ctx, 'TEST')['study_uids'] == {'1.2', '9.9'}
    identity = sv.db_identity(ctx, 'TEST', study_key=11)
    assert identity['study_uids'] == {'1.2'}
    assert identity['by_type'][0] == {'1.2.1'}
    assert len(sv.received(ctx, 'TEST', study_uids=identity['study_uids'])) == 3


class WorkflowDb(MultiStudyDb):
    def __init__(self, timer, missing=False):
        super().__init__(timer, missing=missing)
        self.started = False

    def query(self, database, sql, params=None):
        if 'GROUP BY SeriesKey' in sql:
            return [dict(SeriesKey=1, n=1), dict(SeriesKey=2, n=1)]
        rows = super().query(database, sql, params)
        if 'FROM INSTANCE' in sql:
            rows += [dict(ImageInstanceUID=f'1.2.{index}', InstanceType=kind,
                          SeriesInstanceUID='1.2.9', StudyInstanceUID='1.2')
                     for index, kind in [(4, 1), (5, 3)]]
        elif self.started:
            rows.append(dict(Key=17, State=7, InstanceUID=None, DataType=1))
        return rows

    def one(self, database, sql, params=None):
        if 'FROM DICOM_STORAGE' in sql:
            return dict(SendDoseSR=1)
        return super().one(database, sql, params)


def workflow_context(monkeypatch, *, historical=True):
    from core import flows, viewer_processing as vp
    from tests import workflow05 as wf05, workflow06 as wf06
    from tests import workflow02 as wf02
    timer = clock(monkeypatch)
    db = WorkflowDb(timer)
    ctx = SimpleNamespace(db=db, cfg={'xipl': {'test_patient_id': 'TEST'}, 'data_dir': 'offline'})
    ui = SimpleNamespace(click=lambda *args, **kwargs: None)
    monkeypatch.setattr(flows, 'cold_start', lambda *args, **kwargs: (ui, None))
    monkeypatch.setattr(flows, 'ensure_patient_screen', lambda ui: True)
    monkeypatch.setattr(sv, 'ensure_transfer_syntax', lambda *args: True)
    monkeypatch.setattr(wf05, 'ensure_storage_reachable', lambda cfg: (True, {}))
    monkeypatch.setattr(wf06, 'ensure_storage_reachable', lambda cfg: (True, {}))
    monkeypatch.setattr(vp, 'open_test_study', lambda ctx: dict(ui=ui, study_key=11, step_3d=2))
    monkeypatch.setattr(vp, 'expand_tools', lambda ui: None)
    monkeypatch.setattr(flows, 'select_step', lambda *args: None)
    monkeypatch.setattr(wf02, '_examined_search', lambda *args: ['card'])
    def send(ui, scope):
        db.started = True
        return scope
    monkeypatch.setattr(flows, 'send_current_study', send)
    monkeypatch.setattr(flows, 'send_examined_study', send)
    studies = [dict(patient_id='TEST', study_instance_uid='1.2', instance_count=4)]
    if historical:
        studies.append(dict(patient_id='TEST', study_instance_uid='9.9', instance_count=1))
    srv = server(monkeypatch, studies=studies)
    def download(uid, timeout=180):
        if uid != '1.2':
            raise AssertionError('선택하지 않은 Study 다운로드')
        return archive(dicom_blob(sop='1.2.1'), dicom_blob(sop='1.2.2'),
                       dicom_blob(sop='1.2.3'),
                       dicom_blob(sop='1.2.10', sop_class=sv.SOP_CLASS_RDSR))
    monkeypatch.setattr(srv, 'download', download)
    return ctx


def test_workflow05_keeps_identity_queue_and_direct_receive_in_one_confirmed_study(monkeypatch):
    from tests import workflow05
    result = workflow05.workflow_05(workflow_context(monkeypatch))
    assert result.verdict == 'PASS'
    queue = next(c for c in result.checks if c.title == 'DICOM 창 Queue 모드에서 전송 상태 확인')
    assert queue.actual['observation']['queue_expected_images'] == 3


def test_workflow06_uses_fresh_selected_card_study_without_historical_download(monkeypatch):
    from core import usb_evidence
    from tests import workflow06
    ctx = workflow_context(monkeypatch)
    monkeypatch.setattr(usb_evidence, 'log_cursor', lambda data_dir: 'fresh cursor')
    monkeypatch.setattr(usb_evidence, 'selected_study_key', lambda cursor: 11)
    result = workflow06.workflow_06(ctx)
    assert result.verdict == 'PASS'
    queue = next(c for c in result.checks if c.title == 'DICOM 창 Queue 모드에서 전송 상태 확인')
    assert queue.actual['observation']['queue_expected_images'] == 3


def test_workflow06_without_selection_log_preserves_legacy_queue_contract(monkeypatch):
    from core import usb_evidence
    from tests import workflow06
    ctx = workflow_context(monkeypatch, historical=False)
    def unavailable(data_dir):
        raise usb_evidence.ObservationError('offline no selection log')
    monkeypatch.setattr(usb_evidence, 'log_cursor', unavailable)
    result = workflow06.workflow_06(ctx)
    assert result.verdict == 'PASS'
    queue = next(c for c in result.checks if c.title == 'DICOM 창 Queue 모드에서 전송 상태 확인')
    assert queue.actual['observation']['queue_expected_images'] == 0


def test_workflow15_receive_wait_downloads_only_its_patient_on_shared_scp(monkeypatch):
    # 1.0.8 run110: WF15가 환자 없이 기다려 공유 SCP 49개 Study를 모두 받았고,
    # 다른 장비가 보낸 태그 누락 객체 때문에 Storage SCP DICOM 파싱 오류로 중단됐다.
    from tests import workflow15
    timer = clock(monkeypatch)
    srv = server(monkeypatch, studies=[
        dict(patient_id='OTHER', study_instance_uid='8.8', instance_count=3),
        dict(patient_id=workflow15.PATIENT_ID, study_instance_uid='1.2', instance_count=1)])
    def download(uid, timeout=180):
        if uid != '1.2':
            raise AssertionError('다른 환자의 Study를 내려받았다')
        return archive(dicom_blob(patient=workflow15.PATIENT_ID))
    monkeypatch.setattr(srv, 'download', download)
    objects = workflow15._wait_received(SimpleNamespace())
    assert [o['PatientID'] for o in objects] == [workflow15.PATIENT_ID]
    assert timer.now < 90
