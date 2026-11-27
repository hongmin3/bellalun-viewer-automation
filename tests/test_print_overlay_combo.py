"""Print 서버 Overlay 콤보(2474) 팝업 대기 재현 시험(REQ-OCR-001, #246).

원본: 1.0.0.012 기본 r1 `20261127-061323-847ee574` WF_03 Step 0
`SelectionError: OCR 선택 중단(unreadable): 'TC_WF03_OVERLAY'`.
저장된 `selection.json`은 후보 0개(`rectangles: []`, `reads: []`), 4회 시도, 진단 없음이었다.
`apply_to_print_server`가 콤보를 누른 뒤 0.4초만 기다리고, 보이지 않거나 콤보와 떨어진
`ItemList` 창 중 마지막 것을 골라 항목을 0개로 읽으면 이 모양이 된다.
"""
from types import SimpleNamespace
from unittest import mock

import pytest

from core import ocr_selection, print_overlay


def ctrl(hwnd, cid=0, text='', rect=(100, 200, 300, 220), visible=True):
    return SimpleNamespace(hwnd=hwnd, ctrl_id=cid, text=text, rect=rect, visible=visible)


SERVER_LIST, SERVER_ROW = ctrl(1, 2429), ctrl(2, 0, 'ListItem', (100, 100, 300, 120))
COMBO = ctrl(3, 2474, rect=(100, 200, 300, 220))
#: 앞 단계 Header Layout 콤보가 남긴 숨은 팝업(항목도 보이지 않는다).
STALE = ctrl(10, text='ItemList', rect=(500, 500, 600, 600), visible=False)
#: 이번 콤보 아래에 뜨는 팝업과 항목.
POPUP = ctrl(11, text='ItemList', rect=(100, 220, 300, 280))
NONE_ITEM = ctrl(12, 1, 'TextButton', (100, 222, 300, 240))
TARGET = ctrl(13, 2, 'TextButton', (100, 242, 300, 260))


def _children(hwnd, depth):
    return {SERVER_LIST.hwnd: [SERVER_ROW], STALE.hwnd: [ctrl(20, 1, 'TextButton', visible=False)],
            POPUP.hwnd: [NONE_ITEM, TARGET]}.get(hwnd, [])


@pytest.fixture
def ui(monkeypatch):
    fake = mock.Mock()
    fake.by_id.side_effect = lambda cid: {2429: [SERVER_LIST], 2474: [COMBO]}.get(cid, [])
    fake.dialog.return_value = None
    monkeypatch.setattr(print_overlay, 'children', _children)
    monkeypatch.setattr(print_overlay.flows, 'open_dicom_setting', mock.Mock())
    monkeypatch.setattr(print_overlay.flows, 'setting_update', mock.Mock())
    monkeypatch.setattr(print_overlay, '_select_print_server',
                        mock.Mock(return_value=(SERVER_ROW, {'method': 'name_field', 'names': ['TEST_PRINT']})))
    monkeypatch.setattr(print_overlay.time, 'sleep', lambda _: None)
    monkeypatch.setattr('core.combo_popup.time.sleep', lambda _: None)
    return fake


def _db(overlay=99):
    db = mock.Mock()
    db.one.return_value = {'Key': 1, 'Name': 'TEST_PRINT', 'Overlay': overlay}
    return db


def test_late_popup_after_stale_one_still_offers_its_items(ui, monkeypatch):
    """원본 회차 모양: 첫 조회에는 숨은 옛 팝업만 있고, 이번 팝업은 다음 조회에 뜬다."""
    ui.windows.side_effect = [[STALE], [STALE, POPUP]] + [[STALE, POPUP]] * 5
    seen = []

    def choose(options, wanted, *args, **kwargs):
        seen.append(list(options))
        return TARGET, {'reads': []}
    monkeypatch.setattr(print_overlay.ocr_selection, 'select', choose)
    applied = print_overlay.apply_to_print_server(ui, _db(), 'TEST_PRINT', 99)
    assert seen == [[NONE_ITEM, TARGET]]
    assert applied['Overlay'] == 99
    assert ui.click.call_args_list[-1].args[0] is TARGET


def test_old_lookup_shape_reproduces_unreadable_with_zero_candidates(tmp_path, monkeypatch):
    """옛 코드가 넘기던 빈 후보 목록은 원본 `selection.json`과 같은 판독 불가가 된다."""
    monkeypatch.setattr(ocr_selection, '_environment', lambda _: {})
    with pytest.raises(ocr_selection.SelectionError) as raised:
        ocr_selection.select([], print_overlay.OVERLAY_NAME, evidence_dir=str(tmp_path))
    detail = raised.value.detail
    assert (raised.value.reason, detail['attempts'], detail['rectangles'], detail['reads']) == \
        ('unreadable', 4, [], [])


def test_popup_never_ready_stops_before_selection_or_save(ui, monkeypatch):
    """팝업이 끝내 뜨지 않으면 OCR 판독 불가로 기록하지 않고 준비 실패로 멈춘다."""
    ui.windows.return_value = [STALE]
    monkeypatch.setattr('core.combo_popup.time.monotonic', iter(range(100)).__next__)
    select = mock.Mock()
    monkeypatch.setattr(print_overlay.ocr_selection, 'select', select)
    with pytest.raises(RuntimeError, match='ItemList 준비 시간 초과') as raised:
        print_overlay.apply_to_print_server(ui, _db(), 'TEST_PRINT', 99)
    assert not isinstance(raised.value, ocr_selection.SelectionError)
    select.assert_not_called()
    print_overlay.flows.setting_update.assert_not_called()
