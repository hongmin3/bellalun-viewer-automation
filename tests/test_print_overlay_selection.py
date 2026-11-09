from types import SimpleNamespace
from unittest import mock

import pytest

from core import print_overlay as po, uitext, ocr_selection


def test_print_ocr_uses_common_reader():
    with mock.patch.object(uitext, 'ocr', return_value='Top') as read:
        row = object()
        assert po._ocr(row, 'engine') == 'Top'
    read.assert_called_once_with(row, 'engine')


def test_header_combo_uses_unique_common_selection(tmp_path):
    combo = SimpleNamespace(hwnd=1, visible=True)
    popup = SimpleNamespace(hwnd=2, text='ItemList')
    row = SimpleNamespace(hwnd=3, text='TextButton', visible=True, rect=(0, 0, 40, 20))
    ui = mock.Mock()
    ui.by_id.return_value = [combo]
    ui.windows.return_value = [popup]
    with mock.patch.object(po, 'children', return_value=[row]), \
         mock.patch.object(ocr_selection, 'select', return_value=(row, {'attempts': 2})) as choose:
        result = po._pick_combo_by_text(ui, 42, 'Top', 'engine', '位置', evidence_dir=tmp_path)
    assert choose.call_args.kwargs['match'] == 'exact'
    assert choose.call_args.kwargs['evidence_dir'] == tmp_path
    assert result['wanted'] == 'Top'
    assert ui.click.call_args_list[-1].args[0] is row


def test_ambiguous_header_never_clicks_a_row(tmp_path):
    combo = SimpleNamespace(hwnd=1, visible=True)
    popup = SimpleNamespace(hwnd=2, text='ItemList')
    row = SimpleNamespace(hwnd=3, text='TextButton', visible=True, rect=(0, 0, 40, 20))
    ui = mock.Mock()
    ui.by_id.return_value = [combo]
    ui.windows.return_value = [popup]
    with mock.patch.object(po, 'children', return_value=[row]), \
         mock.patch.object(ocr_selection, 'select', side_effect=ocr_selection.SelectionError('ambiguous', {'wanted':'Top'})):
        with pytest.raises(ocr_selection.SelectionError):
            po._pick_combo_by_text(ui, 42, 'Top', None, 'Header', evidence_dir=tmp_path)
    assert ui.click.call_count == 1  # 콤보를 여는 클릭만 허용한다.


def test_workflow_passes_evidence_before_print_configuration(tmp_path):
    from tests import workflow03 as wf
    ctx = SimpleNamespace(cfg={}, db=mock.Mock(), evidence_root=str(tmp_path))
    ui = mock.Mock()
    ui.by_id.return_value = []
    with mock.patch.object(wf.vp, 'open_test_study', return_value={'ui':ui}), \
         mock.patch.object(wf.flows, 'ensure_patient_screen'), \
         mock.patch.object(wf.vp, 'add_image_overlay_items', return_value={'after':{115:(1,0),118:(1,1)}}), \
         mock.patch.object(wf.print_overlay, 'ensure_print_overlay', side_effect=RuntimeError('stop after reaching print')) as start:
        wf.workflow_03(ctx)
    assert start.call_count == 1
    assert start.call_args.kwargs['evidence_dir'] == str(tmp_path/'Flow'/'03_Overlay')
