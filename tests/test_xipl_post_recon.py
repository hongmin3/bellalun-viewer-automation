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


def test_overlay_buttons_are_scoped_to_the_processing_popup(tmp_path, monkeypatch):
    popup = SimpleNamespace(hwnd=10,text='Post Reconstruction',visible=True,rect=(10,10,1000,1000))
    background = SimpleNamespace(hwnd=1,rect=(0,0,1920,1080),visible=True)
    recon = SimpleNamespace(hwnd=11,rect=(110,900,170,940),visible=True)
    syn = SimpleNamespace(hwnd=12,rect=(180,900,240,940),visible=True)
    clicked = []
    def by_id(control_id, window=None):
        button = recon if control_id == 2123 else syn
        return [button] if window is popup else [background, button]
    ui = SimpleNamespace(windows=lambda:[popup], by_id=by_id,
                         click=lambda control, **k:clicked.append(control.hwnd))
    ctx = SimpleNamespace(evidence_root=str(tmp_path))
    monkeypatch.setattr(flow.vp, 'capture', lambda *a:None)
    monkeypatch.setattr(flow.screen, 'grab', lambda *a,**k:None)
    monkeypatch.setattr(flow.vp, '_pink_count', lambda control: 100 if clicked and clicked[-1] == control.hwnd else 1)
    monkeypatch.setattr(flow, '_read_post_recon_overlay', lambda *a:{'values': {'Contrast':6}})
    evidence = flow._collect_post_recon_overlays(ctx, ui, 'synthetic')
    assert clicked == [11, 12]
    assert all(item.get('values') == {'Contrast':6} for item in evidence.values())
