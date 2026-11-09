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
    combo = SimpleNamespace(hwnd=1, visible=True, rect=(0, 0, 40, 20))
    popup = SimpleNamespace(hwnd=2, text='ItemList', visible=True, rect=(0, 20, 40, 60))
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
    combo = SimpleNamespace(hwnd=1, visible=True, rect=(0, 0, 40, 20))
    popup = SimpleNamespace(hwnd=2, text='ItemList', visible=True, rect=(0, 20, 40, 60))
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


@pytest.mark.parametrize('competitor', ['Study Date', 'Patient ID'])
@pytest.mark.parametrize('repeat', [1, 2])
def test_catalogue_reveals_clipped_competitor_and_returns_fresh_target(tmp_path, competitor, repeat):
    from PIL import Image
    state = {'offset': 0}
    catalogue = SimpleNamespace(hwnd=10, visible=True, rect=(0, 0, 100, 60))
    scroll = SimpleNamespace(hwnd=11, text='Scroll', visible=True)
    up = SimpleNamespace(hwnd=12, ctrl_id=1, visible=True)
    down = SimpleNamespace(hwnd=13, ctrl_id=2, visible=True)
    def rows():
        dy = state['offset']
        return [SimpleNamespace(hwnd=20+i, ctrl_id=i, text='ListItem', visible=True,
                                rect=(0, i*35-dy, 90, (i+1)*35-dy)) for i in range(2)]
    def tree(hwnd, depth):
        return [up, down] if hwnd == 11 else [scroll, *(rows() * repeat)]
    ui = mock.Mock()
    ui.by_id.return_value = [catalogue]
    ui.click.side_effect = lambda c, **kw: state.update(offset=10 if c is down else 0)
    captures = []
    def grab(bbox, **kw):
        assert 0 <= bbox[1] < bbox[3] <= 60, 'clipped row must be revealed'
        captures.append(bbox)
        return Image.new('RGB', (90, 35))
    with mock.patch.object(po, 'children', side_effect=tree), \
         mock.patch.object(ocr_selection.ImageGrab, 'grab', side_effect=grab), \
         mock.patch.object(ocr_selection, 'run_ocr', side_effect=[
             {'text':['Patient ID'], 'conf':[95]}, {'text':[competitor], 'conf':[90]}] * 4):
        if competitor == 'Patient ID':
            with pytest.raises(ocr_selection.SelectionError) as error:
                po._catalogue_row(ui, 42, 0, 'Patient ID', None, tmp_path)
            assert error.value.reason == 'ambiguous'
            assert list(tmp_path.rglob('selection.json'))
            return
        target, detail = po._catalogue_row(ui, 42, 0, 'Patient ID', None, tmp_path)
    assert target.hwnd == 20
    assert target.rect == (0, 0, 90, 35)
    assert len(captures) == 2
    assert detail['scores'][0] == 1.0
    assert detail['scores'][1] < .85


def test_catalogue_reveal_rejects_disappearing_control():
    ui = mock.Mock()
    catalogue = SimpleNamespace(hwnd=10, rect=(0, 0, 100, 60))
    row = SimpleNamespace(hwnd=20, ctrl_id=3, rect=(0, 35, 90, 70))
    with mock.patch.object(po, 'children', return_value=[]):
        with pytest.raises(RuntimeError, match='catalogue'):
            po._reveal_catalogue_row(ui, catalogue, row, object(), object())


@pytest.mark.parametrize('changed_id', [False, True])
def test_catalogue_never_uses_changed_or_permanently_clipped_row(changed_id):
    catalogue = SimpleNamespace(hwnd=10, rect=(0, 0, 100, 60))
    row = SimpleNamespace(hwnd=20, ctrl_id=3, text='ListItem', visible=True,
                          rect=(0, 35, 90, 70))
    fresh = SimpleNamespace(**vars(row))
    if changed_id:
        fresh.ctrl_id = 4
    ui = mock.Mock()
    with mock.patch.object(po, 'children', return_value=[fresh]):
        with pytest.raises(RuntimeError, match='catalogue'):
            po._reveal_catalogue_row(ui, catalogue, row, object(), object())
    assert ui.click.call_count == (0 if changed_id else 50)
