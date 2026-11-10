"""선택은 문자 인식 실패와 잘못된 클릭을 구분한다."""
from types import SimpleNamespace
from unittest import mock
import json

import pytest
from PIL import Image

from core import ocr_selection as selection


def test_default_failure_evidence_uses_context_root_after_cwd_changes(tmp_path, monkeypatch):
    token = selection.set_evidence_root(tmp_path / 'run')
    try:
        monkeypatch.chdir(tmp_path)
        with mock.patch.object(selection, '_environment', return_value={}):
            selection.save_failure({}, [], None, None)
        assert list((tmp_path / 'run' / 'OCR').glob('ocr-*/selection.json'))
        assert not (tmp_path / 'Evidence').exists()
    finally:
        selection.reset_evidence_root(token)


def test_reveal_failure_never_returns_stale_selected_control(tmp_path):
    calls = []
    row = control()
    def reveal(c):
        calls.append(c)
        if len(calls) > 1:
            raise RuntimeError('row disappeared after scrolling')
        return c
    with mock.patch.object(selection.ImageGrab, 'grab', return_value=Image.new('RGB', (120, 30))), \
         mock.patch.object(selection, 'run_ocr', return_value=data('Top')):
        with pytest.raises(selection.SelectionError) as failure:
            selection.select([row], 'Top', reveal=reveal, evidence_dir=tmp_path)
    assert failure.value.reason == 'capture-failed'
    assert list(tmp_path.rglob('selection.json'))


def control(number=1):
    return SimpleNamespace(hwnd=number, ctrl_id=number, rect=(0, 0, 120, 30))


def data(text, confidence=90):
    return {'text': [text], 'conf': [confidence]}


def test_fallback_recovers_text_from_same_capture():
    row = control()
    with mock.patch.object(selection.ImageGrab, 'grab', return_value=Image.new('RGB', (120, 30))) as grab, \
         mock.patch.object(selection, 'run_ocr', side_effect=[data(''), data('HVL'), data('HVL'), data('HVL')]):
        chosen, detail = selection.select([row], 'HVL')
    assert chosen is row
    assert detail['attempts'] == 2
    assert grab.call_count == 1


def test_duplicate_label_is_not_selected_and_writes_evidence(tmp_path):
    with mock.patch.object(selection.ImageGrab, 'grab', return_value=Image.new('RGB', (120, 30))), \
         mock.patch.object(selection, 'run_ocr', return_value=data('HVL')):
        with pytest.raises(selection.SelectionError) as failure:
            selection.select([control(1), control(2)], 'HVL', evidence_dir=tmp_path)
    assert failure.value.reason == 'ambiguous'
    records = list(tmp_path.rglob('selection.json'))
    assert len(records) == 1
    saved = json.loads(records[0].read_text(encoding='utf-8'))
    assert saved['reason'] == 'ambiguous'
    assert len(list(records[0].parent.glob('*raw.png'))) == 2


@pytest.mark.parametrize('text,confidence', [('HVL', 10), ('HVI', 95), ('', 95)])
def test_low_confidence_short_near_match_and_empty_fail(text, confidence):
    with mock.patch.object(selection.ImageGrab, 'grab', return_value=Image.new('RGB', (120, 30))), \
         mock.patch.object(selection, 'run_ocr', return_value=data(text, confidence)):
        with pytest.raises(selection.SelectionError):
            selection.select([control()], 'HVL')


def test_close_fuzzy_candidates_fail():
    with mock.patch.object(selection.ImageGrab, 'grab', return_value=Image.new('RGB', (120, 30))), \
         mock.patch.object(selection, 'run_ocr', side_effect=lambda *a, **kw: data('Patient 1D')):
        with pytest.raises(selection.SelectionError):
            selection.select([control(1), control(2)], 'Patient ID')


def test_exact_fast_path_reads_all_candidates_once():
    rows = [control(1), control(2)]
    with mock.patch.object(selection.ImageGrab, 'grab', return_value=Image.new('RGB', (120, 30))), \
         mock.patch.object(selection, 'run_ocr', side_effect=[data('Top'), data('Bottom')]) as read:
        chosen, detail = selection.select(rows, 'Top')
    assert chosen is rows[0]
    assert read.call_count == 2
    assert detail['attempts'] == 1


def test_engine_errors_fail_closed(tmp_path):
    with mock.patch.object(selection.ImageGrab, 'grab', return_value=Image.new('RGB', (120, 30))), \
         mock.patch.object(selection, 'run_ocr', side_effect=RuntimeError('engine missing')):
        with pytest.raises(selection.SelectionError) as failure:
            selection.select([control()], 'Top', evidence_dir=tmp_path)
    assert failure.value.reason == 'unreadable'
    assert list(tmp_path.rglob('selection.json'))


def test_empty_controls_fail_without_screen_capture():
    with mock.patch.object(selection.ImageGrab, 'grab') as grab:
        with pytest.raises(selection.SelectionError):
            selection.select([], 'Top')
    grab.assert_not_called()


def test_unreadable_competing_row_cannot_establish_unique_match():
    selected, _, reason = selection.rank([
        [{'text':'Top', 'confidence':90}], [{'text':'Top', 'confidence':10}]], 'Top')
    assert selected is None
    assert reason == 'unreadable'


def test_partial_capture_failure_is_reported_as_capture_failure(tmp_path):
    with mock.patch.object(selection.ImageGrab, 'grab', side_effect=[
            Image.new('RGB', (120, 30)), OSError('capture failed')]), \
         mock.patch.object(selection, 'run_ocr', return_value=data('Top')):
        with pytest.raises(selection.SelectionError) as failure:
            selection.select([control(1), control(2)], 'Top', evidence_dir=tmp_path)
    assert failure.value.reason == 'capture-failed'


def test_failure_preserves_stage_controlled_error_and_failure_list_image(tmp_path):
    row = control()
    row.rect = (0, 35, 90, 70)
    def reveal(c):
        raise RuntimeError('Print Overlay catalogue row could not be fully revealed')
    context = {'rect': [0, 0, 100, 60], 'rows': [{'hwnd': 1, 'ctrl_id': 1,
               'rect': [0, 35, 90, 70]}]}
    with mock.patch.object(selection.ImageGrab, 'grab', return_value=Image.new('RGB', (100, 60))), \
         mock.patch.object(selection, '_environment', return_value={}):
        with pytest.raises(selection.SelectionError) as failure:
            selection.select([row], 'Top', reveal=reveal, evidence_dir=tmp_path,
                             diagnostics=lambda: context)
    saved = json.loads(next(tmp_path.rglob('selection.json')).read_text(encoding='utf-8'))
    error = saved['capture_errors'][0]
    assert error['stage'] == 'reveal'
    assert error['message'] == 'Print Overlay catalogue row could not be fully revealed'
    assert saved['catalogue'] == context
    assert list(tmp_path.rglob('catalogue-raw.png'))
    assert failure.value.reason == 'capture-failed'


def test_untrusted_error_text_is_not_saved(tmp_path):
    with mock.patch.object(selection.ImageGrab, 'grab', side_effect=RuntimeError(
            'unexpected token=secret-value; patient=private-person C:/private/home/file')), \
         mock.patch.object(selection, '_environment', return_value={}):
        with pytest.raises(selection.SelectionError):
            selection.select([control()], 'Top', evidence_dir=tmp_path)
    saved = next(tmp_path.rglob('selection.json')).read_text(encoding='utf-8')
    assert 'secret-value' not in saved and 'private-person' not in saved
    error = json.loads(saved)['capture_errors'][0]
    assert error['stage'] == 'capture'
    assert len(error['message_sha256']) == 64


def test_selection_reveal_failure_records_final_stage(tmp_path):
    calls = 0
    def reveal(c):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('Print Overlay catalogue row changed during scroll')
        return c
    with mock.patch.object(selection.ImageGrab, 'grab', return_value=Image.new('RGB', (120, 30))), \
         mock.patch.object(selection, 'run_ocr', return_value=data('Top')), \
         mock.patch.object(selection, '_environment', return_value={}):
        with pytest.raises(selection.SelectionError) as failure:
            selection.select([control()], 'Top', reveal=reveal, evidence_dir=tmp_path)
    assert failure.value.detail['capture_errors'][-1]['stage'] == 'selection-reveal'


def test_foreground_gate_error_keeps_branch_without_window_title():
    error = RuntimeError('클릭 전에 Viewer 를 최전면으로 올리지 못했습니다(가린 창: private-title). 클릭이 다른 프로그램으로 들어가므로 중단합니다.')
    detail = selection._error_detail(error, 'reveal')
    assert detail['message'].startswith('클릭 전에 Viewer 를 최전면으로 올리지 못했습니다')
    assert 'private-title' not in detail['message']
