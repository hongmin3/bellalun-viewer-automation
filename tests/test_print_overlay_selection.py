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
    row = SimpleNamespace(hwnd=3, text='TextButton', visible=True, rect=(0, 20, 40, 40))
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
    row = SimpleNamespace(hwnd=3, text='TextButton', visible=True, rect=(0, 20, 40, 40))
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
    assert len([box for box in captures if box != catalogue.rect]) == 2
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
    arrow = SimpleNamespace(hwnd=13, ctrl_id=2, visible=True)
    scroll = SimpleNamespace(hwnd=11, text='Scroll', visible=True)
    with mock.patch.object(po, 'children', side_effect=lambda hwnd, depth:
                           [arrow] if hwnd == 11 else [scroll, fresh]), mock.patch.object(po.time, 'sleep'):
        with pytest.raises(RuntimeError, match='catalogue'):
            po._reveal_catalogue_row(ui, catalogue, row, arrow, arrow)
    assert ui.click.call_count == (0 if changed_id else 3)

@pytest.mark.parametrize('late_polls,noop_clicks', [(4, 0), (2, 1)])
@pytest.mark.parametrize('competitor', ['Study Date', 'Patient ID'])
def test_twenty_rows_recover_partial_last_row_and_reveal_target_again(
        tmp_path, late_polls, noop_clicks, competitor):
    from PIL import Image
    state = {'offset': 0, 'pending': 0, 'down': 0}
    catalogue = SimpleNamespace(hwnd=10, ctrl_id=42, visible=True, rect=(0, 0, 100, 695))
    scroll = SimpleNamespace(hwnd=11, text='Scroll', visible=True)
    up = SimpleNamespace(hwnd=12, ctrl_id=1, visible=True)
    down = SimpleNamespace(hwnd=13, ctrl_id=2, visible=True)
    def rows():
        return [SimpleNamespace(hwnd=20+i, ctrl_id=i, text='ListItem', visible=True,
                                rect=(0, i*35-state['offset'], 90, (i+1)*35-state['offset']))
                for i in range(20)]
    def tree(hwnd, depth):
        if hwnd == 11:
            return [up, down]
        if state['pending']:
            state['pending'] -= 1
            if not state['pending']:
                state['offset'] = 10
        return [scroll, *rows()]
    def click(c, **kw):
        if c is down:
            state['down'] += 1
            if state['down'] > noop_clicks:
                # 새 클릭마다 재시작되는 비동기 렌더를 기다려야 한다.
                state['pending'] = late_polls
        elif c is up:
            state.update(offset=0, pending=0)
    ui = mock.Mock()
    ui.by_id.return_value = [catalogue]
    ui.click.side_effect = click
    captured = []
    def grab(bbox, **kw):
        assert 0 <= bbox[1] < bbox[3] <= 695
        captured.append(tuple(bbox))
        return Image.new('RGB', (90, 35))
    labels = ['Patient ID', *[f'Field {i}' for i in range(1, 19)], competitor]
    with mock.patch.object(po, 'children', side_effect=tree), \
         mock.patch.object(po.time, 'sleep'), \
         mock.patch.object(ocr_selection.ImageGrab, 'grab', side_effect=grab), \
         mock.patch.object(ocr_selection, 'run_ocr', side_effect=[
             {'text':[label], 'conf':[95]} for label in labels] * 4):
        if competitor == 'Patient ID':
            with pytest.raises(ocr_selection.SelectionError) as failure:
                po._catalogue_row(ui, 42, 0, 'Patient ID', None, tmp_path)
            assert failure.value.reason == 'ambiguous'
            assert failure.value.detail['attempts'] == 4
            assert len(failure.value.detail['reads']) == 20
            assert list(tmp_path.rglob('catalogue-raw.png'))
            return
        target, detail = po._catalogue_row(ui, 42, 0, 'Patient ID', None, tmp_path)
    assert target.hwnd == 20
    assert target.rect == (0, 0, 90, 35)
    assert len([box for box in captured if box != catalogue.rect]) == 20
    assert state['down'] == noop_clicks + 1
    assert detail['attempts'] == 1


def test_invalid_scroll_stops_bounded_and_records_geometry():
    catalogue = SimpleNamespace(hwnd=10, rect=(0, 0, 100, 60))
    row = SimpleNamespace(hwnd=20, ctrl_id=3, text='ListItem', visible=True,
                          rect=(0, 35, 90, 70))
    ui = mock.Mock()
    arrow = SimpleNamespace(hwnd=13, ctrl_id=2, visible=True)
    scroll = SimpleNamespace(hwnd=11, text='Scroll', visible=True)
    with mock.patch.object(po, 'children', side_effect=lambda hwnd, depth:
                           [arrow] if hwnd == 11 else [scroll, row]), mock.patch.object(po.time, 'sleep'):
        with pytest.raises(RuntimeError, match='no movement'):
            po._reveal_catalogue_row(ui, catalogue, row, arrow, arrow)
    assert ui.click.call_count <= 3


def test_recreated_row_is_rejected_even_with_same_control_id():
    catalogue = SimpleNamespace(hwnd=10, rect=(0, 0, 100, 60))
    row = SimpleNamespace(hwnd=20, ctrl_id=3, text='ListItem', visible=True,
                          rect=(0, 35, 90, 70))
    replaced = SimpleNamespace(**{**vars(row), 'hwnd': 21})
    ui = mock.Mock()
    with mock.patch.object(po, 'children', return_value=[replaced]):
        with pytest.raises(RuntimeError, match='row changed'):
            po._reveal_catalogue_row(ui, catalogue, row, object(), object())
    ui.click.assert_not_called()


def test_scroll_waits_for_stable_geometry_after_first_change():
    catalogue = SimpleNamespace(hwnd=10, rect=(0, 0, 100, 60))
    arrow = SimpleNamespace(hwnd=13, ctrl_id=2, rect=(90, 40, 100, 60), visible=True)
    scroll = SimpleNamespace(hwnd=11, text='Scroll', visible=True)
    state = {'clicked': False, 'polls': 0}
    def tree(hwnd, depth):
        if hwnd == 11:
            return [arrow]
        if state['clicked']:
            state['polls'] += 1
        offset = min(state['polls'], 3)
        return [scroll, SimpleNamespace(hwnd=20, ctrl_id=3, text='ListItem', visible=True,
                                rect=(0, 35-offset, 90, 70-offset))]
    ui = mock.Mock()
    ui.click.side_effect = lambda *a, **kw: state.update(clicked=True)
    with mock.patch.object(po, 'children', side_effect=tree), mock.patch.object(po.time, 'sleep'):
        assert po._scroll_catalogue(ui, catalogue, arrow)
    assert state['polls'] >= 5, 'first motion is not render completion'


@pytest.mark.parametrize('wanted,duplicate', [('Patient ID', False), ('Thickness', False), ('Patient ID', True)])
def test_fixed_twenty_slots_recover_every_partial_logical_row_and_recheck_target(tmp_path, wanted, duplicate):
    _fixed_catalogue_case(tmp_path, wanted, duplicate)


def _fixed_catalogue_case(tmp_path, wanted='Patient ID', duplicate=False, fault=None,
                           viewport_height=695):
    from PIL import Image, ImageDraw
    labels = ['Patient ID', *[f'Field {i}' for i in range(1, 22)], 'Thickness',
              'Patient ID' if duplicate else 'Study Date']
    if fault == 'overlap':
        labels[1:22] = ['Repeated Field'] * 21
    state = {'offset': 0, 'pending': None, 'polls': 0, 'down': 0, 'ranked': False,
             'restore_noop': False}
    catalogue = SimpleNamespace(hwnd=10, ctrl_id=42, visible=True,
                                rect=(0, 0, 100, viewport_height))
    scroll = SimpleNamespace(hwnd=11, text='Scroll', visible=True)
    up = SimpleNamespace(hwnd=12, ctrl_id=1, visible=True, rect=(90, 0, 100, 15))
    down = SimpleNamespace(hwnd=13, ctrl_id=2, visible=True, rect=(90, 680, 100, 695))
    def tree(hwnd, depth):
        if hwnd == 11:
            return [up, down]
        if state['pending'] is not None:
            state['polls'] += 1
            if state['polls'] >= 4:
                state['offset'], state['pending'] = state['pending'], None
        return [scroll, *[SimpleNamespace(hwnd=1007 if fault == 'identity' and i == 7 and
                        state['offset'] >= 2 else 20+i, ctrl_id=i+1, text='ListItem',
                    visible=state['offset']+i < len(labels), rect=(0, i*35, 90, (i+1)*35))
                    for i in range(20)]]
    def click(target, **kw):
        if target.ctrl_id == 2:
            state['down'] += 1
            if state['down'] == 1:  # 첫 입력은 무효이고 이후는 비동기 내용 변경이다.
                return
            if fault == 'restore-noop' and state['ranked'] and not state['restore_noop']:
                state['restore_noop'] = True
                return
        step = -1 if target.ctrl_id == 1 else 1
        full_count = 20 if fault == 'unresolved' else viewport_height // 35
        state.update(pending=max(0, min(len(labels)-full_count, state['offset']+step)), polls=0)
    def frame():
        image = Image.new('RGB', (100, viewport_height), 'white')
        draw = ImageDraw.Draw(image)
        for slot in range(20):
            logical = state['offset'] + slot
            if logical < len(labels):
                draw.text((5, slot*35+8), labels[logical], fill='black')
                if slot*35+3 < viewport_height:
                    image.putpixel((3, slot*35+3), (0 if fault == 'overlap' else logical, 100, 100))
        draw.rectangle((82, 0, 99, viewport_height-1), fill=(state['offset']*20, 90, 90))
        if fault in {'viewport-border', 'viewport-border-text', 'border-insufficient'}:
            draw.line((0, viewport_height-1, 81, viewport_height-1), fill=(224, 224, 224))
        if fault in {'partial', 'viewport-border-text'} and state['offset'] == 0:
            image.putpixel((3, 19*35+3), (255, 100, 100))
        if fault == 'return-race' and state['ranked']:
            image.putpixel((4, 4), (255, 0, 0))
        return image
    ui = mock.Mock()
    ui.by_id.return_value = [catalogue]
    ui.click.side_effect = click
    def read(image, executable=None, profile=ocr_selection.PROFILES[0]):
        logical = image.getpixel((3, 3))[0]
        if logical == len(labels)-1:
            state['ranked'] = True
        return {'text': labels[logical], 'confidence': 95, 'profile': list(profile), 'error': None}
    with mock.patch.object(po, 'children', side_effect=tree), \
         mock.patch.object(po.time, 'sleep'), \
         mock.patch.object(ocr_selection.ImageGrab, 'grab', side_effect=lambda bbox, **kw: frame().crop(bbox)), \
         mock.patch.object(ocr_selection, 'read_image', side_effect=read), \
         mock.patch.object(ocr_selection, '_environment', return_value={}):
        errors = {'identity': 'row changed', 'unresolved': 'unresolved partial',
                  'partial': 'partial row mismatch', 'return-race': 'target population not found',
                  'overlap': 'insufficient overlap', 'viewport-border-text': 'partial row mismatch',
                  'border-insufficient': 'insufficient partial evidence'}
        if fault in errors:
            with pytest.raises(ocr_selection.SelectionError) as failure:
                po._catalogue_row(ui, 42, 0, wanted, None, tmp_path)
            assert failure.value.reason == 'capture-failed'
            saved = failure.value.detail
            assert errors[fault] in saved['capture_errors'][-1]['message']
            assert list(tmp_path.rglob('selection.json'))
            assert list(tmp_path.rglob('catalogue-raw.png'))
            if fault in {'viewport-border-text', 'border-insufficient'}:
                from pathlib import Path
                raw_index = saved['partial_captures'][0]['image_index']
                raw = Image.open(Path(saved['evidence']) / f'{raw_index:03d}-raw.png')
                assert raw.getpixel((4, raw.height-1)) == (224, 224, 224)
                assert saved['partial_comparisons'][0]['excluded_bottom_border_pixels'] == 1
        elif duplicate:
            with pytest.raises(ocr_selection.SelectionError) as failure:
                po._catalogue_row(ui, 42, 0, wanted, None, tmp_path)
            assert failure.value.reason == 'ambiguous'
            assert len(failure.value.detail['reads']) == len(labels)
        else:
            target, detail = po._catalogue_row(ui, 42, 0, wanted, None, tmp_path)
            assert labels[state['offset'] + target.ctrl_id - 1] == wanted
            assert target.rect[3] <= viewport_height
            assert len(detail['reads']) == len(labels)
            assert detail['attempts'] <= 4
            if fault == 'viewport-border':
                assert detail['partial_comparisons']
                assert all(item['excluded_bottom_border_pixels'] == 1
                           for item in detail['partial_comparisons'])
    assert ui.click.call_count < 150


@pytest.mark.parametrize('fault', ['identity', 'unresolved', 'partial', 'return-race', 'overlap'])
def test_fixed_population_rejects_incomplete_changed_and_replaced_candidates(tmp_path, fault):
    _fixed_catalogue_case(tmp_path, fault=fault)


def test_fixed_population_target_restore_retries_transient_noop(tmp_path):
    _fixed_catalogue_case(tmp_path, wanted='Thickness', fault='restore-noop')


def test_scroll_never_clicks_stale_arrow_when_scroll_control_disappears():
    catalogue = SimpleNamespace(hwnd=10, rect=(0, 0, 100, 60))
    arrow = SimpleNamespace(hwnd=13, ctrl_id=2, rect=(90, 40, 100, 60))
    ui = mock.Mock()
    with mock.patch.object(po, 'children', return_value=[]):
        with pytest.raises(RuntimeError, match='scroll'):
            po._scroll_catalogue(ui, catalogue, arrow)
    ui.click.assert_not_called()


def test_catalogue_setup_failure_also_saves_selection_diagnostics(tmp_path):
    ui = mock.Mock()
    ui.by_id.return_value = []
    with mock.patch.object(ocr_selection, '_environment', return_value={}):
        with pytest.raises(ocr_selection.SelectionError) as failure:
            po._catalogue_row(ui, 42, 0, 'Patient ID', None, tmp_path)
    assert failure.value.detail['capture_errors'][0]['stage'] == 'catalogue-setup'
    assert list(tmp_path.rglob('selection.json'))


@pytest.mark.parametrize('mode', ['stable', 'unchanging', 'unstable'])
def test_slow_content_queries_keep_stabilization_samples_and_remain_bounded(mode):
    from PIL import Image
    catalogue = SimpleNamespace(hwnd=10, rect=(0, 0, 100, 60))
    arrow = SimpleNamespace(hwnd=13, ctrl_id=2, rect=(90, 40, 100, 60), visible=True)
    scroll = SimpleNamespace(hwnd=11, text='Scroll', visible=True)
    row = SimpleNamespace(hwnd=20, ctrl_id=3, text='ListItem', visible=True, rect=(0, 0, 90, 35))
    clock = {'now': 0, 'clicked': False, 'queries': 0}
    def tree(hwnd, depth):
        if hwnd == 11:
            return [arrow]
        if clock['clicked']:
            clock['now'] += .8
            clock['queries'] += 1
        return [scroll, row]
    def frame(*args, **kwargs):
        value = (clock['queries'] % 2 if mode == 'unstable' else
                 int(clock['clicked'] and mode == 'stable'))
        return Image.new('RGB', (100, 60), (value, 0, 0))
    ui = mock.Mock()
    ui.click.side_effect = lambda *a, **kw: clock.update(clicked=True)
    trace = []
    with mock.patch.object(po, 'children', side_effect=tree), \
         mock.patch.object(po.time, 'monotonic', side_effect=lambda: clock['now']), \
         mock.patch.object(po.time, 'sleep', side_effect=lambda n: clock.update(now=clock['now']+n)), \
         mock.patch.object(ocr_selection.ImageGrab, 'grab', side_effect=frame):
        if mode == 'unstable':
            with pytest.raises(RuntimeError, match='did not settle'):
                po._scroll_catalogue(ui, catalogue, arrow, trace=trace, observe=True)
            assert clock['queries'] == 31
        else:
            assert po._scroll_catalogue(ui, catalogue, arrow, trace=trace, observe=True) == (mode == 'stable')
            assert clock['queries'] == (3 if mode == 'stable' else 2)
    assert trace[-1]['elapsed_seconds'] >= 1.5
    assert trace[-1]['stable'] == (mode == 'stable')


@pytest.mark.parametrize('wanted,duplicate', [('Thickness', False), ('Patient ID', True)])
def test_fully_visible_fixed_slots_scan_hidden_logical_candidates(tmp_path, wanted, duplicate):
    _fixed_catalogue_case(tmp_path, wanted=wanted, duplicate=duplicate, viewport_height=700)


@pytest.mark.parametrize('fault,height', [('viewport-border', 695),
                                         ('viewport-border-text', 695),
                                         ('border-insufficient', 666)])
def test_partial_identity_excludes_only_actual_bottom_viewport_border(tmp_path, fault, height):
    _fixed_catalogue_case(tmp_path, fault=fault, viewport_height=height)


@pytest.mark.parametrize('restore_fails', [False, True])
def test_fully_visible_moving_catalogue_probe_restores_exact_origin_before_ocr(tmp_path, restore_fails):
    from PIL import Image, ImageDraw
    state = {'offset': 0}
    catalogue = SimpleNamespace(hwnd=10, ctrl_id=42, visible=True, rect=(0, 0, 100, 100))
    scroll = SimpleNamespace(hwnd=11, text='Scroll', visible=True)
    up = SimpleNamespace(hwnd=12, ctrl_id=1, visible=True, rect=(90, 0, 100, 15))
    down = SimpleNamespace(hwnd=13, ctrl_id=2, visible=True, rect=(90, 85, 100, 100))
    def tree(hwnd, depth):
        if hwnd == 11:
            return [up, down]
        return [scroll, *[SimpleNamespace(hwnd=20+i, ctrl_id=i+1, text='ListItem', visible=True,
                         rect=(0, i*35-state['offset'], 90, (i+1)*35-state['offset']))
                         for i in range(2)]]
    def click(target, **kwargs):
        if target.ctrl_id == 2:
            state['offset'] = 10
        elif not restore_fails:
            state['offset'] = 0
    def grab(bbox, **kwargs):
        image = Image.new('RGB', (100, 100), 'white')
        draw = ImageDraw.Draw(image)
        draw.text((5, 8-state['offset']), 'Patient ID', fill='black')
        draw.text((5, 43-state['offset']), 'Study Date', fill='black')
        return image.crop(bbox)
    ui = mock.Mock()
    ui.by_id.return_value = [catalogue]
    ui.click.side_effect = click
    def read(image, *args, **kwargs):
        assert state['offset'] == 0, 'probe must restore before any OCR'
        return {'text': ['Patient ID' if reader.call_count == 1 else 'Study Date'], 'conf': [95]}
    with mock.patch.object(po, 'children', side_effect=tree), \
         mock.patch.object(po.time, 'sleep'), \
         mock.patch.object(ocr_selection.ImageGrab, 'grab', side_effect=grab), \
         mock.patch.object(ocr_selection, 'run_ocr', side_effect=read) as reader, \
         mock.patch.object(ocr_selection, '_environment', return_value={}):
        if restore_fails:
            with pytest.raises(ocr_selection.SelectionError) as failure:
                po._catalogue_row(ui, 42, 0, 'Patient ID', None, tmp_path)
            assert failure.value.detail['capture_errors'][0]['message'].endswith('origin restore mismatch')
            assert reader.call_count == 0
        else:
            row, detail = po._catalogue_row(ui, 42, 0, 'Patient ID', None, tmp_path)
            assert row.hwnd == 20 and row.rect == (0, 0, 90, 35)
            assert detail['attempts'] == 1 and reader.call_count == 2
    assert any(call.args[0] is down for call in ui.click.call_args_list)


def _server_rows(*hwnds):
    return [SimpleNamespace(hwnd=h, text='ListItem', visible=True, rect=(0, h * 20, 200, h * 20 + 18))
            for h in hwnds]


def _name_field_ui(names):
    """행을 누르면 이름 칸(2434)에 그 행의 전체 이름이 보이는 가짜 UI."""
    ui = mock.Mock()
    field = SimpleNamespace(hwnd=99, visible=True)
    shown = {}
    ui.click.side_effect = lambda control, **kw: shown.update(name=names.get(control.hwnd))
    ui.by_id.side_effect = lambda cid: [field] if cid == 2434 else []
    ui.get_text.side_effect = lambda control: shown.get('name')
    return ui


def test_print_server_uses_full_name_field_when_list_text_is_truncated(tmp_path):
    # Validates: REQ-OCR-001 (목록에서 PRIN... 으로 잘려도 이름 칸으로 고른다)
    rows = _server_rows(1, 2)
    ui = _name_field_ui({1: 'OTHER_PRINT', 2: 'PRINT_TEST'})
    with mock.patch.object(ocr_selection, 'select') as ocr:
        chosen, detail = po._select_print_server(ui, rows, 'PRINT_TEST', None, evidence_dir=tmp_path)
    assert chosen is rows[1]
    assert detail['method'] == 'name_field' and detail['names'] == ['OTHER_PRINT', 'PRINT_TEST']
    assert ui.click.call_args_list[-1].args[0] is rows[1]
    ocr.assert_not_called()


def test_print_server_duplicate_names_never_pick_a_row(tmp_path):
    rows = _server_rows(1, 2)
    ui = _name_field_ui({1: 'PRINT_TEST', 2: 'PRINT_TEST'})
    with mock.patch.object(ocr_selection, 'select') as ocr:
        with pytest.raises(RuntimeError, match='2개'):
            po._select_print_server(ui, rows, 'PRINT_TEST', None, evidence_dir=tmp_path)
    ocr.assert_not_called()


def test_print_server_without_name_field_falls_back_to_common_ocr(tmp_path):
    rows = _server_rows(1)
    ui = mock.Mock()
    ui.by_id.return_value = []
    with mock.patch.object(ocr_selection, 'select', return_value=(rows[0], {'attempts': 1})) as ocr:
        chosen, detail = po._select_print_server(ui, rows, 'PRINT_TEST', 'engine', evidence_dir=tmp_path)
    assert chosen is rows[0] and detail['method'] == 'ocr'
    assert ocr.call_args.kwargs['match'] == 'contains' and ocr.call_args.kwargs['evidence_dir'] == tmp_path
    assert ui.click.call_args_list[-1].args[0] is rows[0]


def test_print_server_name_absent_falls_back_to_ocr_and_keeps_its_refusal(tmp_path):
    rows = _server_rows(1)
    ui = _name_field_ui({1: 'OTHER_PRINT'})
    with mock.patch.object(ocr_selection, 'select',
                           side_effect=ocr_selection.SelectionError('unreadable', {'wanted': 'PRINT_TEST'})):
        with pytest.raises(ocr_selection.SelectionError):
            po._select_print_server(ui, rows, 'PRINT_TEST', None, evidence_dir=tmp_path)
