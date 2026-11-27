"""WF03·WF08 실제 진입점에서 OCR 증거와 기존 차단 판정을 함께 확인한다."""
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

from PIL import Image
import pytest

from core import ocr_selection as sel
from core.ui import ForegroundError
from tests import workflow03 as wf
from tests import workflow08 as wf08


@pytest.fixture
def trial(tmp_path, monkeypatch):
    ui = Mock()
    ui.by_id.return_value = []
    ui.windows.return_value = []
    ui.dialog.return_value = None
    ui.is_foreground.return_value = True
    ctx = SimpleNamespace(evidence_root=str(tmp_path), db=Mock(),
                          cfg={'dicom': {'servers_to_register': [{'name': 'TEST_PRINT', 'kind': 'Print'}]}})
    monkeypatch.setattr(wf.vp, 'open_test_study', Mock(return_value={'ui': ui}))
    monkeypatch.setattr(wf.flows, 'ensure_patient_screen', Mock(return_value=True))
    monkeypatch.setattr(wf.vp, 'add_image_overlay_items', Mock(return_value={'after': {115: (1, 0), 118: (1, 1)}}))
    po = {'overlay': {'Key': 99, 'HeaderPosition': 1, 'HeaderLayout': 2}, 'items': [{'Position': pos, 'FieldID': fid} for pos, fields in wf.print_overlay.PRINT_EXPECTED_BY_POSITION.items() for fid in fields]}
    monkeypatch.setattr(wf.print_overlay, 'ensure_print_overlay', Mock(return_value=po))
    monkeypatch.setattr(wf.print_overlay, 'header_matches', Mock(return_value=True))
    monkeypatch.setattr(wf.print_overlay, 'matches_expected_areas', Mock(return_value=True))
    monkeypatch.setattr(wf.print_overlay, '_saved', Mock(return_value=None))
    monkeypatch.setattr(wf.print_overlay, 'apply_to_print_server', Mock())
    monkeypatch.setattr(sel, '_environment', lambda _: {})
    monkeypatch.setattr(sel.ImageGrab, 'grab', lambda **kw: Image.new('RGB', (80, 16), 'black'))
    monkeypatch.setattr(sel, 'run_ocr', lambda *a: {'text': ['TC_WF03_O'], 'conf': [20]})
    return ctx, ui, po


@pytest.mark.parametrize('step', [2, 3])
def test_actual_run_keeps_only_ocr_selection_manual_and_crops(trial, step):
    ctx, ui, po = trial
    select = wf.print_overlay.ensure_print_overlay if step == 2 else wf.print_overlay.apply_to_print_server
    def uncertain(*args, evidence_dir, **kwargs):
        ctrl = SimpleNamespace(hwnd=22, rect=(0, 0, 80, 16))
        sel.select([ctrl], 'TC_WF03_OVERLAY', evidence_dir=evidence_dir)
    select.side_effect = uncertain
    result, = wf.run(ctx)
    assert result.verdict == 'MANUAL' and not result.aborted, [(c.title, c.actual) for c in result.checks]
    check, = [c for c in result.checks if c.status == 'MANUAL']
    assert check.step == step
    row, = check.reading_evidence['rows']
    assert row['expected'] == 'TC_WF03_OVERLAY' and row['outcome'] == 'unread'
    assert len(row['reads']) == 4 and all('TC_WF03_O' in read for _, read in row['reads'])
    assert Path(row['source_image']).is_file()
    assert any(Path(p).name == 'selection.json' for p in result.evidence)
    assert bool([c for c in result.checks if c.step == 2 and c.status == 'PASS']) == (step == 3)
    assert wf.vp.open_test_study.call_count == 1
    ui.click.assert_not_called()


@pytest.mark.parametrize('problem', ['database', 'no_candidates', 'capture_failed', 'missing_evidence', 'real_layout', 'real_header', 'foreground'])
def test_actual_run_keeps_non_ocr_failures(trial, problem):
    ctx, ui, po = trial
    def fail(*args, evidence_dir, **kwargs):
        if problem == 'database':
            raise RuntimeError('database value mismatch')
        if problem == 'no_candidates':
            sel.select([], 'TC_WF03_OVERLAY', evidence_dir=evidence_dir)
        if problem == 'foreground':
            raise ForegroundError('unsafe')
        if problem in ('real_layout', 'real_header'):
            wf.print_overlay._saved.return_value = po
            wf.print_overlay.matches_expected_areas.return_value = problem != 'real_layout'
            wf.print_overlay.header_matches.return_value = problem != 'real_header'
            sel.select([SimpleNamespace(hwnd=22, rect=(0, 0, 80, 16))], 'TC_WF03_OVERLAY', evidence_dir=evidence_dir)
        raise sel.SelectionError('capture-failed' if problem == 'capture_failed' else 'unreadable',
                                 {'wanted': 'TC_WF03_OVERLAY', 'evidence': str(Path(evidence_dir)/'absent')})
    wf.print_overlay.ensure_print_overlay.side_effect = fail
    result, = wf.run(ctx)
    assert result.verdict == 'FAIL' and result.aborted
    assert not any(c.status == 'MANUAL' for c in result.checks)
    wf.print_overlay.apply_to_print_server.assert_not_called()

@pytest.mark.parametrize('case', ['owned', 'other_foreground', 'old_popup', 'stays_open', 'patient_unconfirmed', 'recovery_error'])
def test_unread_selection_only_leaves_verified_popup_and_patient_screen(trial, case):
    ctx, ui, _ = trial
    popup = SimpleNamespace(hwnd=35, text='ItemList', visible=True, rect=(-1, -1, 90, 18))
    windows = [popup] if case == 'old_popup' else []
    ui.windows.side_effect = lambda: list(windows)
    ui.foreground_window.return_value = {'hwnd': 20 if case == 'other_foreground' else popup.hwnd}
    def uncertain(*args, evidence_dir, **kwargs):
        windows[:] = [popup]
        sel.select([SimpleNamespace(hwnd=22, rect=(0, 0, 80, 16))], 'TC_WF03_OVERLAY', evidence_dir=evidence_dir)
    wf.print_overlay.apply_to_print_server.side_effect = uncertain
    if case != 'stays_open':
        ui.key.side_effect = lambda key: windows.clear()
    wf.flows.ensure_patient_screen.side_effect = [True, OSError('unreadable UI') if case == 'recovery_error' else case != 'patient_unconfirmed']
    result, = wf.run(ctx)
    if case == 'owned':
        assert result.verdict == 'MANUAL' and not result.aborted
    else:
        assert result.verdict == 'FAIL' and result.aborted
        assert any(isinstance(e, ForegroundError) for e in result._abort_exceptions)
    if case in ('old_popup', 'other_foreground'):
        ui.key.assert_not_called()
    else:
        ui.key.assert_called_once_with('ESC')
    ui.click.assert_not_called()

@pytest.mark.parametrize('stage', ['definition', 'apply', 'server_offline', 'bad_film', 'no_received_file'])
def test_wf08_actual_entry_only_reviews_print_overlay_selection(trial, monkeypatch, stage):
    ctx, ui, po = trial
    ctx.cfg['dicom']['print_server_url'] = 'http://test.invalid'
    ctx.cfg['dicom']['servers_to_register'][0]['ae_title'] = 'TEST'
    ctx.cfg['test_data'] = {'include_3d_wide': False}
    monkeypatch.setattr(wf08, '_fixture', Mock(return_value={'PatientID': wf08.PATIENT_ID, 'Key': 1}))
    monkeypatch.setattr(wf08.flows, 'cold_start', Mock(return_value=(ui, {})))
    monkeypatch.setattr(wf08, '_close_setting', Mock())
    monkeypatch.setattr(wf08, '_open_examined_fixture', Mock(return_value=([1], 1)))
    monkeypatch.setattr(wf08, '_station_ae', Mock(return_value='TEST'))
    monkeypatch.setattr(wf08, '_ensure_thumbnails', Mock(return_value=[
        {'kind': kind, 'label': kind, 'rect': [0, 0, 80, 16], 'control': object()} for kind in ('2D', '3D-N')]))
    monkeypatch.setattr(wf08, '_film_from_selected_study', Mock(return_value=(
        SimpleNamespace(rect=(0, 0, 80, 16)), {'pane_ratio': 0.1 if stage == 'bad_film' else 0.95})))
    server = Mock()
    server.status.return_value = {'running': stage != 'server_offline', 'ae_title': 'TEST'}
    server.jobs.return_value = []
    monkeypatch.setattr(wf08, 'PrintServer', Mock(return_value=server))
    wf08.print_overlay.apply_to_print_server.return_value = {'Overlay': po['overlay']['Key']}
    if stage in ('definition', 'apply'):
        def uncertain(*args, evidence_dir, **kwargs):
            ctrl = SimpleNamespace(hwnd=22, rect=(0, 0, 80, 16))
            sel.select([ctrl], 'TC_WF03_OVERLAY', evidence_dir=evidence_dir)
        method = (wf08.print_overlay.ensure_print_overlay if stage == 'definition'
                  else wf08.print_overlay.apply_to_print_server)
        method.side_effect = uncertain
    if stage == 'no_received_file':
        ui.by_id.side_effect = lambda ident: [SimpleNamespace(visible=True)] if ident == 1149 else []
        for name in ('_film_expectations', '_ocr_areas', '_judge_areas'):
            monkeypatch.setattr(wf08, name, Mock(return_value={}))
        monkeypatch.setattr(wf08, '_all_ok', Mock(return_value=True))
        monkeypatch.setattr(wf08, '_wait_own_job', Mock(side_effect=TimeoutError('no matching received file')))
    result = wf08.run(ctx)
    if stage in ('definition', 'apply'):
        assert result.verdict == 'MANUAL' and not result.aborted
        c, = [c for c in result.checks if c.status == 'MANUAL']
        assert c.step == (1 if stage == 'definition' else 2)
        row, = c.reading_evidence['rows']
        assert Path(row['source_image']).is_file() and len(row['reads']) == 4
        assert row['expected'] == 'TC_WF03_OVERLAY'
        wf08.PrintServer.assert_not_called()
        ui.click.assert_not_called()
    else:
        assert result.verdict == 'FAIL' and not any(c.status == 'MANUAL' for c in result.checks)
        if stage == 'no_received_file':
            wf08._wait_own_job.assert_called_once()
        elif stage == 'bad_film':
            assert any(c.step == 5 and c.status == 'FAIL' for c in result.checks)
        else:
            assert any(c.step == 4 and c.status == 'FAIL' for c in result.checks)

def test_wf08_ambiguous_name_preserves_both_candidates(trial, monkeypatch):
    ctx, ui, _ = trial
    monkeypatch.setattr(wf08, '_fixture', Mock(return_value={'PatientID': wf08.PATIENT_ID}))
    monkeypatch.setattr(wf08.flows, 'cold_start', Mock(return_value=(ui, {})))
    monkeypatch.setattr(sel, 'run_ocr', lambda *a: {'text': ['TC_WF03_OVERLAY'], 'conf': [96]})
    def ambiguous(*args, evidence_dir, **kwargs):
        choices = [SimpleNamespace(hwnd=i, rect=(0, i, 80, i+16)) for i in (11, 31)]
        sel.select(choices, 'TC_WF03_OVERLAY', evidence_dir=evidence_dir)
    wf08.print_overlay.apply_to_print_server.side_effect = ambiguous
    result = wf08.run(ctx)
    check, = [c for c in result.checks if c.status == 'MANUAL']
    assert result.verdict == 'MANUAL' and 'ambiguous' in check.actual
    assert len({row['source_image'] for row in check.reading_evidence['rows']}) == 2
    ui.click.assert_not_called()


def test_foreground_error_inside_capture_remains_a_safety_stop(trial):
    ctx, ui, _ = trial
    wf.print_overlay.ensure_print_overlay.side_effect = sel.SelectionError(
        'capture-failed', {'wanted': 'TC_WF03_OVERLAY', 'capture_errors': [{'error': 'ForegroundError'}]})
    result, = wf.run(ctx)
    assert result.verdict == 'FAIL' and any(isinstance(e, ForegroundError) for e in result._abort_exceptions)
    wf.print_overlay._saved.assert_not_called()
    ui.key.assert_not_called()
