from types import SimpleNamespace as C
from unittest import mock
import pytest
from core import flows


def ctrl(hwnd, cid=0, text='', rect=(10, 40, 100, 60)):
    return C(hwnd=hwnd, ctrl_id=cid, text=text, rect=rect, visible=True)


def test_examined_waits_for_its_popup_ignores_unrelated_and_uses_id():
    ui = mock.Mock()
    ui.dialog.return_value = None
    field, edit, search = ctrl(1), ctrl(2), ctrl(3)
    ui.by_id.side_effect = lambda cid: {
        2177: [field], 2178: [edit], 2179: [search]}.get(cid, [])
    unrelated = ctrl(4, text='ItemList', rect=(500, 500, 600, 600))
    popup = ctrl(5, text='ItemList', rect=(10, 30, 100, 100))
    wrong, target = ctrl(6, 3, 'TextButton'), ctrl(7, 2, 'TextButton')
    ui.windows.side_effect = [[unrelated], [unrelated, popup]]
    with mock.patch.object(flows, 'children', side_effect=lambda hwnd, depth:
                           [wrong] if hwnd == 4 else [wrong, target]), \
         mock.patch('time.sleep'), mock.patch.object(flows, 'examined_cards', return_value=['new']):
        assert flows.examined_search(ui, 'SYNTHETIC-ID') == ['new']
    assert ui.click.call_args_list[1].args[0] is target
    ui.set_text.assert_called_once_with(edit, 'SYNTHETIC-ID')


def test_examined_ambiguous_popups_never_set_search_text():
    ui = mock.Mock()
    ui.dialog.return_value = None
    ui.by_id.return_value = [ctrl(1)]
    ui.windows.return_value = [ctrl(4, text='ItemList', rect=(10, 30, 100, 100)),
                               ctrl(5, text='ItemList', rect=(10, 30, 100, 100))]
    with mock.patch.object(flows, 'children', return_value=[ctrl(7, 2, 'TextButton')]), \
         mock.patch('time.sleep'):
        with pytest.raises(flows.FlowError):
            flows.examined_search(ui, 'SYNTHETIC-ID')
    ui.set_text.assert_not_called()


def test_missing_popup_times_out_without_input():
    ui = mock.Mock()
    ui.dialog.return_value = None
    ui.by_id.return_value = [ctrl(1)]
    ui.windows.return_value = []
    with mock.patch('time.monotonic', side_effect=range(100)), mock.patch('time.sleep'):
        with pytest.raises(flows.FlowError, match='시간'):
            flows.examined_search(ui, 'SYNTHETIC-ID')
    ui.set_text.assert_not_called()


@pytest.mark.parametrize('items', [[], [ctrl(8, 3, 'TextButton')]])
def test_popup_missing_required_item_times_out_without_input(items):
    ui = mock.Mock()
    ui.dialog.return_value = None
    ui.by_id.return_value = [ctrl(1)]
    ui.windows.return_value = [ctrl(4, text='ItemList', rect=(10,30,100,100))]
    with mock.patch.object(flows, 'children', return_value=items), \
         mock.patch('time.monotonic', side_effect=range(100)), mock.patch('time.sleep'):
        with pytest.raises(flows.FlowError, match='시간'):
            flows.examined_search(ui, 'SYNTHETIC-ID')
    ui.set_text.assert_not_called()


def test_popup_waits_until_required_id_exists():
    ui = mock.Mock()
    ui.dialog.return_value = None
    field, edit, search = ctrl(1), ctrl(2), ctrl(3)
    ui.by_id.side_effect = lambda cid: {2177:[field], 2178:[edit], 2179:[search]}.get(cid, [])
    ui.windows.return_value = [ctrl(4, text='ItemList', rect=(10,30,100,100))]
    target = ctrl(7, 2, 'TextButton')
    with mock.patch.object(flows, 'children', side_effect=[[], [target]]), \
         mock.patch('time.sleep'), mock.patch.object(flows, 'examined_cards', return_value=[]):
        flows.examined_search(ui, 'SYNTHETIC-ID')
    assert ui.click.call_args_list[1].args[0] is target


def test_wait_items_excludes_slots_outside_the_popup_viewport():
    """Header Layout 실측: 9개 슬롯 중 6개만 팝업 안에 보였고 나머지는 아래 다른 UI를 가렸다."""
    from core import combo_popup
    ui = mock.Mock()
    ui.dialog.return_value = None
    combo = ctrl(1, rect=(1579, 390, 1721, 416))
    ui.windows.return_value = [ctrl(4, text='ItemList', rect=(1579, 416, 1721, 622))]
    slots = [ctrl(10 + i, i, 'TextButton', (1579, 417 + 34 * i, 1721, 451 + 34 * i))
             for i in range(9)]
    items = combo_popup.wait_items(ui, combo, lambda hwnd, depth: slots)
    assert [c.hwnd for c in items] == [10, 11, 12, 13, 14, 15]


def test_wait_items_keeps_waiting_when_no_slot_is_inside_the_popup():
    from core import combo_popup
    ui = mock.Mock()
    ui.dialog.return_value = None
    ui.windows.return_value = [ctrl(4, text='ItemList', rect=(10, 30, 100, 40))]
    outside = [ctrl(8, 0, 'TextButton', (10, 50, 100, 80))]
    with mock.patch('time.monotonic', side_effect=range(100)), mock.patch('time.sleep'):
        with pytest.raises(RuntimeError, match='시간'):
            combo_popup.wait_items(ui, ctrl(1), lambda hwnd, depth: outside)
