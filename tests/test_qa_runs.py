"""제품을 조작하지 않는 실행·검수 기록 계약."""
import json
import os
import time

import pytest


def complete_rows(extra):
    return extra + [{'tc_id': tc, 'verdict': 'PASS'} for tc in (
        'AUTOMATION_ENVIRONMENT_RESET', 'DICOM_Server_Setup',
        'TC_Basic_WorkFlow_14', 'TC_XIPL_compatibility_07')]


def test_run_separates_consent_and_reports_and_rejects_old_result(tmp_path):
    from bellalunauto.runs import RunRecord
    folder = tmp_path / 'Reports'
    folder.mkdir()
    old = folder / 'Result_old.json'
    old.write_text('{"results": []}', encoding='utf-8')
    os.utime(old, (1, 1))
    record = RunRecord.create(tmp_path, 'run-regression', {'target': 'synthetic'}, consent=True)
    new = folder / 'Result_new.json'
    new.write_text(json.dumps({'results': complete_rows([{'tc_id': 'TC1', 'verdict': 'FAIL'}])}), encoding='utf-8')
    record.finish(0)
    data = json.loads(record.path.read_text(encoding='utf-8'))
    assert data['consent']['source'] == 'GUI'
    assert data['consent']['user'] and data['consent']['at']
    assert data['status'] == 'completed'
    assert data['reports'] == [str(new)]
    assert data['review_status'] == '자동 실행 완료(검토 전)'
    assert 'TC1' in record.review_targets()
    assert '수동 검토' in data['next_action']


def test_review_requires_reviewer_and_each_nonpass_and_preserves_report(tmp_path):
    from bellalunauto.runs import RunRecord
    record = RunRecord.create(tmp_path, 'run-regression', {}, consent=False)
    folder = tmp_path / 'Reports'
    folder.mkdir()
    report = folder / 'Result_new.json'
    original = json.dumps({'results': complete_rows([{'tc_id': 'TC1', 'verdict': 'MANUAL'},
                                      {'tc_id': 'TC2', 'verdict': 'PASS'}])})
    report.write_text(original, encoding='utf-8')
    record.finish(0)
    with pytest.raises(ValueError):
        record.save_review('담당자', {}, complete=True)
    with pytest.raises(ValueError):
        record.save_review('', {'TC1': {'result': '확인 완료'}}, complete=True)
    record.save_review('담당자', {'TC1': {'result': '재시험 필요', 'comment': '확인'}}, complete=False)
    assert record.data['review_status'] == '검토 중'
    record.save_review('담당자', {'TC1': {'result': '결함 등록', 'issue': '#test'}}, complete=True)
    assert record.data['review_status'] == '검수 완료'
    assert report.read_text(encoding='utf-8') == original
    assert record.data['consent']['source'] == '화면 동의 없음(CLI)'


@pytest.mark.parametrize('code,stop,want', [(1223, False, 'uac_cancelled'), (9, False, 'abnormal'), (0, True, 'stopped')])
def test_run_terminal_states(tmp_path, code, stop, want):
    from bellalunauto.runs import RunRecord
    record = RunRecord.create(tmp_path, 'run-regression', {})
    if stop:
        record.request_stop()
    record.finish(code)
    assert record.data['status'] == want
    with pytest.raises(ValueError):
        record.save_review('담당자', {}, complete=True)


def test_progress_ignores_stale_state_and_reports_completed_count(tmp_path):
    from bellalunauto.runs import RunRecord
    record = RunRecord.create(tmp_path, 'run-regression', {})
    folder = tmp_path / 'work'
    folder.mkdir()
    state = folder / 'regression_state.json'
    state.write_text(json.dumps({'status': 'running', 'current_tc': 'TC3', 'index': 3, 'total': 10}), encoding='utf-8')
    record.refresh_progress()
    assert record.data['progress']['completed'] == 2
    assert record.data['progress']['current_tc'] == 'TC3'
    os.utime(state, (1, 1))
    record.data['progress'] = {}
    record.refresh_progress()
    assert not record.data['progress'].get('current_tc')


def test_controller_requires_explicit_consent_before_spawning(tmp_path, monkeypatch):
    from bellalunauto.gui import RunController
    from types import SimpleNamespace
    controller = RunController(SimpleNamespace(workspace=tmp_path, config_path=tmp_path / 'config.json'), {})
    monkeypatch.setattr(controller, 'start_argv', lambda argv: None)
    with pytest.raises(ValueError, match='동의'):
        controller.start('run-regression')
    assert controller.process is None


def test_wu_progress_uses_checkpoint_and_live_current_tc(tmp_path):
    from bellalunauto.runs import RunRecord, engine_progress
    record = RunRecord.create(tmp_path, 'run-winupdate', {})
    engine_progress(tmp_path, record.data['run_id'], 'TC4', 4, 20)
    (tmp_path / 'work' / 'winupdate_checkpoint.json').write_text(json.dumps({
        'payload': {'identity': 'hash-string', 'order': ['a', 'b', 'c']}}), encoding='utf-8')
    record.refresh_progress()
    assert record.data['progress']['completed'] == 3
    assert record.data['progress']['total'] == 20
    assert record.data['progress']['current_tc'] == 'TC4'


def test_diagnostic_resolution_keeps_only_safe_settings_destinations():
    from bellalunauto.qa_dialogs import remediation_target
    assert remediation_target('화면 해상도') == 'ms-settings:display'
    assert remediation_target('SQL 서비스') == 'services.msc'
    assert remediation_target('OCR 실행파일') == 'config'
    assert remediation_target('http://untrusted') == 'config'


def test_cli_product_run_records_no_gui_consent(tmp_path, monkeypatch):
    from bellalunauto import app
    from bellalunauto.runtime import Layout
    layout = Layout(tmp_path, tmp_path, tmp_path / 'config.json')
    layout.config_path.write_text('{}', encoding='utf-8')
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    monkeypatch.setattr(app, 'resolve_layout', lambda **kwargs: layout)
    monkeypatch.setattr(app.ctypes.windll.shell32, 'IsUserAnAdmin', lambda: True)
    monkeypatch.setattr(app, 'run_guarded', lambda *args: 1223)
    from bellalunauto import runplan
    monkeypatch.setattr(runplan, 'build_plan', lambda *args: {'target': 'synthetic'})
    assert app.main(['run-regression']) == 1223
    records = list((tmp_path / 'Runs').glob('*/run.json'))
    assert len(records) == 1
    data = json.loads(records[0].read_text(encoding='utf-8'))
    assert data['consent']['source'] == '화면 동의 없음(CLI)'
    assert data['status'] == 'uac_cancelled'


def test_full_run_with_failed_tc_is_completed_and_reviewable(tmp_path):
    from bellalunauto.runs import RunRecord
    record = RunRecord.create(tmp_path, 'run-regression', {})
    folder = tmp_path / 'Reports'
    folder.mkdir()
    (folder / 'Result_complete.json').write_text(json.dumps({
        'results': complete_rows([{'tc_id': 'TC1', 'verdict': 'FAIL'}])}), encoding='utf-8')
    record.finish(1)
    assert record.data['status'] == 'completed'
    record.save_review('검토자', {'TC1': {'result': '결함 등록'}}, complete=True)
    assert record.data['review_status'] == '검수 완료'


def test_partial_report_does_not_mean_automatic_completion(tmp_path):
    from bellalunauto.runs import RunRecord
    record = RunRecord.create(tmp_path, 'run-regression', {})
    folder = tmp_path / 'Reports'
    folder.mkdir()
    (folder / 'Result_partial.json').write_text('{"results": [{"tc_id":"only", "verdict":"PASS"}]}', encoding='utf-8')
    record.finish(0)
    assert record.data['status'] == 'abnormal'


def test_progress_accepts_new_file_with_coarse_timestamp_but_not_unchanged_old_state(tmp_path):
    from bellalunauto.runs import RunRecord
    folder = tmp_path / 'work'
    folder.mkdir()
    state = folder / 'regression_state.json'
    state.write_text('{"current_tc":"OLD","index":9}', encoding='utf-8')
    record = RunRecord.create(tmp_path, 'run-regression', {})
    record.refresh_progress()
    assert not record.data['progress'].get('current_tc')
    state.write_text('{"current_tc":"NEW","index":2,"total":3}', encoding='utf-8')
    epoch_second = int(record.data['started_epoch'])
    record.data['started_epoch'] = epoch_second + .9
    os.utime(state, (epoch_second, epoch_second))
    record.refresh_progress()
    assert record.data['progress']['current_tc'] == 'NEW'
    assert record.data['progress']['completed'] == 1
