"""SRS 03-50-230: 조정툴 기본값과 img에 저장한 실제 적용값을 구분한다."""
from core.result import TCResult
from tests import xipl_flows as flow
from tests.test_imginfo_and_waits import write_sample, SAMPLE_XML
from types import SimpleNamespace
import pytest

CHANGED = {
    'Recon.Background Masking': 'Not use', 'Recon.Contrast': 14,
    'Recon.Sharpness': 16, 'Recon.Brightness': 14, 'Recon.Tone type': 15,
    'Syn.Background Masking': 'Not use', 'Syn.Contrast': 6,
    'Syn.Sharpness': 14, 'Syn.Brightness': 6, 'Syn.Tone type': 15,
}
DEFAULT = {**CHANGED, 'Recon.Contrast': 10, 'Syn.Contrast': 10}
OVERLAYS = {
    'Recon': {'values': {'Background Masking':'Not use', 'Contrast':14,
                         'Sharpness':16, 'Brightness':14, 'Tone type':15}},
    'Syn': {'values': {'Background Masking':'Not use', 'Contrast':6,
                       'Sharpness':14, 'Brightness':6, 'Tone type':15}},
}


def test_reads_all_ten_applied_values_from_real_img_tail(tmp_path):
    image = tmp_path / 'Image81.img'
    write_sample(image, SAMPLE_XML.replace('TEST_3D_NARROW', 'TEST_3D_FLOW'))
    state = {'instances': [{'Key': 81, 'InstanceType': 2}],
             'files': {str(image): {'size': image.stat().st_size}}}
    evidence = flow._post_recon_file_evidence(state)
    assert evidence[str(image)]['values'] == CHANGED
    assert evidence[str(image)]['parameter'] == 'TEST_3D_FLOW.xtp'


def test_default_controls_are_not_mistaken_for_lost_applied_values(tmp_path):
    image = tmp_path / 'Image81.img'
    write_sample(image, SAMPLE_XML.replace('TEST_3D_NARROW', 'TEST_3D_FLOW'))
    state = {'instances': [{'Key': 81, 'InstanceType': 2}, {'Key': 82, 'InstanceType': 3}],
             'files': {str(image): {}}}
    # 2 outputs but only one backing file must fail; empty evidence must never pass.
    evidence = flow._post_recon_file_evidence(state)
    result = TCResult('TC_XIPL_compatibility_03', 'synthetic')
    flow._record_post_recon_applied(result, DEFAULT, DEFAULT, CHANGED,
        'TEST_3D_FLOW.xtp', 'TEST_3D_FLOW.xtp', state, evidence, 'after_apply')
    assert result.checks[0].status == 'PASS'
    assert result.checks[1].status == 'FAIL'


def test_no_gpu_log_cannot_skip_missing_or_wrong_saved_values(tmp_path):
    image = tmp_path / 'Image81.img'
    write_sample(image, SAMPLE_XML.replace('PostContrast="14"', 'PostContrast="10"'))
    state = {'instances': [{'Key': 81, 'InstanceType': 2}], 'files': {str(image): {}}}
    result = TCResult('TC_XIPL_compatibility_03', 'synthetic')
    flow._record_post_recon_applied(result, DEFAULT, DEFAULT, CHANGED,
        'TEST_3D_FLOW.xtp', 'TEST_3D_FLOW.xtp', state,
        flow._post_recon_file_evidence(state), 'after_apply')
    assert result.checks[1].status == 'FAIL'
    assert not any(check.status == 'SKIP' for check in result.checks)


def test_both_result_files_keep_applied_values_while_controls_show_defaults(tmp_path):
    paths = [tmp_path / f'Image{key}.img' for key in (81, 82)]
    for image in paths:
        write_sample(image, SAMPLE_XML.replace('TEST_3D_NARROW', 'TEST_3D_FLOW'))
    state = {'instances': [{'Key': 81, 'InstanceType': 2}, {'Key': 82, 'InstanceType': 3}],
             'files': {str(path): {} for path in paths}}
    result = TCResult('TC_XIPL_compatibility_03', 'synthetic')
    flow._record_post_recon_applied(result, DEFAULT, DEFAULT, CHANGED,
        'TEST_3D_FLOW.xtp', 'TEST_3D_FLOW.xtp', state,
        flow._post_recon_file_evidence(state), 'after_restart', OVERLAYS)
    assert [check.status for check in result.checks] == ['PASS', 'PASS', 'PASS']
    paths[1].write_bytes(b'truncated image')
    broken = TCResult('TC_XIPL_compatibility_03', 'synthetic')
    flow._record_post_recon_applied(broken, DEFAULT, DEFAULT, CHANGED,
        'TEST_3D_FLOW.xtp', 'TEST_3D_FLOW.xtp', state,
        flow._post_recon_file_evidence(state), 'after_restart')
    assert broken.checks[1].status == 'FAIL'
    assert broken.checks[2].status == 'FAIL'


def test_result_state_reads_latest_study_copy_after_reopening(tmp_path):
    for folder, content in [('Study48_20260821_100000', b'old'),
                            ('Study48_20260821_110000', b'latest')]:
        directory = tmp_path / 'Image' / folder
        directory.mkdir(parents=True)
        (directory / 'Image81.img').write_bytes(content)
    db = SimpleNamespace(query=lambda *a: [{'Key':81,'InstanceType':2,'GroupKey':54}])
    ctx = SimpleNamespace(cfg={'data_dir':str(tmp_path)}, db=db)
    result = flow._result_state(ctx, 48, 54)
    assert len(result['files']) == 1
    path = next(iter(result['files']))
    assert path.endswith('Study48_20260821_110000\\Image81.img')
    assert result['files'][path]['size'] == 6


def test_overlay_parser_uses_applied_five_values_and_rejects_partial_reading():
    text = 'Background Masking: X\nContrast: 6\nSharpness: 14\nBrightness: 6\nTone Type: 15'
    assert flow._parse_post_recon_overlay(text) == {
        'Background Masking':'Not use','Contrast':6,'Sharpness':14,'Brightness':6,'Tone type':15}
    assert flow._parse_post_recon_overlay('Contrast: 6') is None


@pytest.mark.parametrize('evidence_fault', [None, 'state', 'json'])
def test_apply_timeout_keeps_actual_database_and_file_evidence(tmp_path, monkeypatch, evidence_fault):
    import json
    from datetime import datetime
    from unittest.mock import Mock
    ui = SimpleNamespace(by_id=lambda *a: [SimpleNamespace(visible=True)], click=lambda *a, **k: None)
    ctx = SimpleNamespace(cfg={'xipl': {}}, evidence_root=str(tmp_path))
    session = {'ui': ui, 'step_3d': 2, 'study_key': 48,
               'instances': [{'Key':80,'InstanceType':1,'ImageInstanceUID':'synthetic','GroupKey':54}]}
    for name in ('select_3d_raw', 'open_post_reconstruction', 'change_all_3d_parameters', 'capture', 'cancel_window'):
        monkeypatch.setattr(flow.vp, name, lambda *a, **k: None)
    monkeypatch.setattr(flow.vp, 'select_test_parameter', lambda *a: 'TEST_3D_FLOW.xtp')
    baseline = {key: 'Use' if key.endswith('Masking') else 0 for key in CHANGED}
    monkeypatch.setattr(flow, '_read_state_retry', Mock(side_effect=[baseline, CHANGED]))
    monkeypatch.setattr(flow, '_viewer_log_mark', lambda *a: (tmp_path / 'viewer.log', 0))
    monkeypatch.setattr(flow, '_viewer_log_since', lambda *a: '')
    monkeypatch.setattr(flow, '_preview_delta', lambda *a: {'changed_ratio':1})
    monkeypatch.setattr(flow, '_poll_completion', Mock(side_effect=[{}, RuntimeError('synthetic Apply timeout')]))
    monkeypatch.setattr(flow, '_click_3d_apply_confirmed', lambda *a: {
        'mark':(tmp_path / 'viewer.log', 0), 'clicked':datetime.now()})
    before = {'instances': [], 'files': {}}
    after = {'instances': [{'Key':81,'InstanceType':2}], 'files': {}}
    monkeypatch.setattr(flow, '_result_state', Mock(side_effect=[before,
        PermissionError('synthetic image still locked') if evidence_fault == 'state' else after]))
    if evidence_fault == 'json':
        from pathlib import Path
        write_text = Path.write_text
        def denied(path, *a, **k):
            if path.name.endswith('_applied.json'):
                raise OSError('synthetic evidence write denied')
            return write_text(path, *a, **k)
        monkeypatch.setattr(Path, 'write_text', denied)
    result = flow.compatibility_03(ctx, session)
    artifact = tmp_path / 'Viewer_XIPL/TC_XIPL_compatibility_03_applied.json'
    if evidence_fault is None:
        assert artifact.exists(), 'Apply timeout must retain DB and file collection before aborting'
        assert json.loads(artifact.read_text(encoding='utf-8'))['after'] == after
    assert result.verdict == 'FAIL'
    assert result.aborted
    assert ctx.execution_incomplete is True
    assert ctx.execution_block['tc_id'] == 'TC_XIPL_compatibility_03'


def test_run_xipl_stops_before_next_tc_if_processing_is_unconfirmed(monkeypatch):
    ctx = SimpleNamespace()
    monkeypatch.setattr(flow, '_prepare', lambda *a: {})
    for number in (1, 2):
        monkeypatch.setattr(flow, f'compatibility_{number:02}', lambda *a: TCResult('synthetic', 'fixture'))
    def timeout(*a):
        ctx.execution_block = {'tc_id':'TC_XIPL_compatibility_03','causes':[]}
        row = TCResult('TC_XIPL_compatibility_03','fixture')
        row.abort(9, 'processing incomplete', RuntimeError('timeout'))
        return row
    monkeypatch.setattr(flow, 'compatibility_03', timeout)
    for number in (4, 5, 6, 7):
        def forbidden(*a): raise AssertionError('busy Viewer must not receive later TC input')
        monkeypatch.setattr(flow, f'compatibility_{number:02}', forbidden)
    rows = flow.run_xipl(ctx)
    assert len(rows) == 3


@pytest.mark.parametrize('external_duplicate', [False, True])
def test_overlay_buttons_are_scoped_to_the_processing_popup(tmp_path, monkeypatch, external_duplicate):
    popup = SimpleNamespace(hwnd=10,text='',visible=True,rect=(10,10,1000,1000))
    background = SimpleNamespace(hwnd=1,text='Post Reconstruction',rect=(0,0,1920,1080),visible=True)
    recon = SimpleNamespace(hwnd=11,rect=(110,900,170,940),visible=True)
    syn = SimpleNamespace(hwnd=12,rect=(180,900,240,940),visible=True)
    clicked = []
    def by_id(control_id, window=None):
        if control_id in (flow.vp.PARAM_COMBO, 2043):
            return [SimpleNamespace(hwnd=control_id, visible=True, rect=(700,100,800,150))] if window is popup else []
        button = recon if control_id == 2123 else syn
        return ([background,button] if external_duplicate else [button]) if window is popup else [background, button]
    ui = SimpleNamespace(windows=lambda:[background,popup], by_id=by_id,
                         click=lambda control, **k:clicked.append(control.hwnd))
    ctx = SimpleNamespace(evidence_root=str(tmp_path))
    monkeypatch.setattr(flow.vp, 'capture', lambda *a:None)
    monkeypatch.setattr(flow.screen, 'grab', lambda *a,**k:None)
    monkeypatch.setattr(flow.vp, '_pink_count', lambda control: 100 if clicked and clicked[-1] == control.hwnd else 1)
    monkeypatch.setattr(flow, '_read_post_recon_overlay', lambda *a:{'values': {'Contrast':6}})
    evidence = flow._collect_post_recon_overlays(ctx, ui, 'synthetic')
    assert clicked == [11, 12]
    assert all(item.get('values') == {'Contrast':6} for item in evidence.values())


@pytest.mark.parametrize('fault', ['ambiguous', 'external', 'missing_anchor'])
@pytest.mark.parametrize('missing_id', [flow.vp.PARAM_COMBO,2043,2123,2124])
def test_overlay_rejects_ambiguous_or_external_processing_controls(tmp_path, fault, missing_id):
    popup = SimpleNamespace(hwnd=10, text='Post Reconstruction', visible=True,
                            rect=(10,10,1000,1000))
    other = SimpleNamespace(hwnd=20, text='', visible=True, rect=(10,10,1000,1000))
    def by_id(control_id, window=None):
        if fault == 'missing_anchor' and control_id == missing_id:
            return []
        return [SimpleNamespace(hwnd=control_id, visible=True,
            rect=(2000,100,2100,150) if fault == 'external' else (100,100,200,150))]
    def forbidden(*a, **k):
        raise AssertionError('unverified popup must not receive clicks')
    ui = SimpleNamespace(windows=lambda:[popup,other] if fault == 'ambiguous' else [popup],
                         by_id=by_id, click=forbidden)
    evidence = flow._collect_post_recon_overlays(SimpleNamespace(evidence_root=str(tmp_path)), ui, 'test')
    assert evidence['error']['reason'] == 'processing_popup_not_unique'


@pytest.mark.parametrize('persist_fault', [None, 'missing_file', 'wrong_parameter',
    'unchanged_files', 'wrong_overlay', *CHANGED, 'save_exception', 'not_save',
    'wrong_study', 'stale_log', 'missing_log', 'duplicate_log', 'modal'])
def test_compatibility03_checks_files_after_product_save_not_dirty_memory(tmp_path, monkeypatch, persist_fault):
    from datetime import datetime, timedelta
    from unittest.mock import Mock
    ui = SimpleNamespace(by_id=lambda *a: [SimpleNamespace(visible=True, text='TEST_3D_')],
                         click=lambda *a, **k:None,
                         dialog=lambda:object() if persist_fault == 'modal' else None)
    ctx = SimpleNamespace(cfg={'xipl':{}}, evidence_root=str(tmp_path))
    session = {'ui':ui, 'step_3d':2, 'study_key':48,
        'instances':[{'Key':80,'InstanceType':1,'ImageInstanceUID':'raw','GroupKey':54}]}
    for name in ('select_3d_raw','open_post_reconstruction','change_all_3d_parameters',
                 'capture','capture_viewer_window','cancel_window'):
        monkeypatch.setattr(flow.vp,name,lambda *a,**k:None)
    monkeypatch.setattr(flow.vp,'select_test_parameter',lambda *a:'TEST_3D_FLOW.xtp')
    baseline = {key:'Use' if key.endswith('Masking') else 0 for key in CHANGED}
    monkeypatch.setattr(flow,'_read_state_retry',Mock(side_effect=[baseline,CHANGED,baseline,baseline]))
    monkeypatch.setattr(flow,'_viewer_log_mark',lambda *a:(tmp_path/'viewer.log',0))
    close_requested = False
    def close(*a, **kwargs):
        nonlocal close_requested
        assert kwargs['option'] == 'suspend' and kwargs['save_changes'] is True
        close_requested = True
        if persist_fault == 'save_exception':
            raise RuntimeError('synthetic Save refused')
        return {'dialog':False,'option':None}
    monkeypatch.setattr(flow.flows,'close_examine',close)
    def log_since(*a):
        timestamp = datetime.now() + timedelta(seconds=1)
        message = 'Terminate PostReconThread normally closed'
        if close_requested:
            message = 'Closing Study(49) with save' if persist_fault == 'wrong_study' else 'Closing Study(48) with save'
            if persist_fault == 'not_save':
                message = 'Closing Study(48) with not save'
            if persist_fault == 'stale_log':
                timestamp -= timedelta(days=1)
            if persist_fault == 'missing_log':
                message = 'unrelated product log'
        stamp = timestamp.strftime('%Y/%m/%d %H:%M:%S.%f')[:-3]
        line = f'[{stamp}] [Info] [UI] [{message}]'
        return line + '\n' + line if close_requested and persist_fault == 'duplicate_log' else line
    monkeypatch.setattr(flow,'_viewer_log_since',log_since)
    monkeypatch.setattr(flow,'_preview_delta',lambda *a:{'changed_ratio':1})
    poll = flow._poll_completion
    monkeypatch.setattr(flow,'_poll_completion',lambda result,name,predicate,timeout,**k:
        poll(result,name,predicate,.005,poll=.001) if name == 'XIPL 3D Save' else {})
    monkeypatch.setattr(flow,'_click_3d_apply_confirmed',lambda *a:{
        'mark':(tmp_path/'viewer.log',0),'clicked':datetime.now()})
    monkeypatch.setattr(flow,'_collect_post_recon_overlays',
        lambda *a:{} if persist_fault == 'wrong_overlay' else OVERLAYS)
    rows = [{'Key':81,'InstanceType':2},{'Key':82,'InstanceType':3}]
    dirty = {'instances':rows,'files':{'81':{'sha256':'old'},'82':{'sha256':'old'}}}
    persisted = {'instances':rows,'files':{'81':{'sha256':'new'},'82':{'sha256':'new'}}}
    saved = False
    restart_calls = 0
    def reopen(*a):
        nonlocal saved, restart_calls
        restart_calls += 1
        saved = True
        return dict(session)
    monkeypatch.setattr(flow.vp,'open_test_study',reopen)
    monkeypatch.setattr(flow,'_result_state',
        lambda *a:persisted if saved and persist_fault != 'unchanged_files' else dirty)
    def read_files(state):
        values = CHANGED if saved else DEFAULT
        if saved and persist_fault in CHANGED:
            values = {**CHANGED,persist_fault:baseline[persist_fault]}
        files = {key:{'parameter':'TEST_3D_FLOW.xtp','values':values} for key in ('81','82')}
        if saved and persist_fault == 'wrong_parameter':
            files['82']['parameter'] = 'DBT_Standard_Default.xtp'
        if saved and persist_fault == 'missing_file':
            files.pop('82')
        return files
    monkeypatch.setattr(flow,'_post_recon_file_evidence',read_files)
    # The real driver reads Apply visibility after the accepted click.
    original = flow._click_3d_apply_confirmed
    def apply(*a):
        ui.by_id = lambda control_id,*a: [] if control_id == flow.vp.APPLY else [SimpleNamespace(visible=True,text='TEST_3D_')]
        return original(*a)
    monkeypatch.setattr(flow,'_click_3d_apply_confirmed',apply)
    result = flow.compatibility_03(ctx,session)
    if persist_fault in {'save_exception','not_save','wrong_study','stale_log','missing_log','duplicate_log','modal'}:
        assert close_requested
        assert result.aborted
        assert ctx.execution_incomplete is True
        assert ctx.execution_block['tc_id'] == result.tc_id
        assert restart_calls == 0
        assert (tmp_path/'Viewer_XIPL/TC_XIPL_compatibility_03_applied.json').exists()
        def forbidden(*a):
            raise AssertionError('Save failure must block the next TC input')
        monkeypatch.setattr(flow,'compatibility_04',forbidden)
        assert flow.run_xipl_sequence(ctx,session,(4,)) == []
        return
    assert not result.aborted, [(check.title, check.actual) for check in result.checks]
    assert result.verdict == ('PASS' if persist_fault is None else 'FAIL')
    assert not any('after_apply' in check.title and 'img' in check.title for check in result.checks)
    assert next(check for check in result.checks if check.step == 10).status == (
        'FAIL' if persist_fault == 'unchanged_files' else 'PASS')
