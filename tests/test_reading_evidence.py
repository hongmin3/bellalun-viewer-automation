# -*- coding: utf-8 -*-
"""OCR 판독 대조표(REQ-REPORT-002, TEST-REPORT-002, frame/FRAME.md 2.9).

Validates: REQ-REPORT-002
"""
import json
import re

import pytest
from PIL import Image, ImageDraw

from core import image_overlay, print_overlay, reading_evidence
from core.result import FAIL, MANUAL, PASS, StepFailed, TCResult, write_reports
from core.wu_chain import result_from_dict
from tests import xipl_flows as flow

CHANGED = {
    'Recon.Background Masking': 'Not use', 'Recon.Contrast': 14, 'Recon.Sharpness': 16,
    'Recon.Brightness': 14, 'Recon.Tone type': 15,
    'Syn.Background Masking': 'Not use', 'Syn.Contrast': 6, 'Syn.Sharpness': 14,
    'Syn.Brightness': 6, 'Syn.Tone type': 15,
}
RECON = {'Background Masking': 'Not use', 'Contrast': 14, 'Sharpness': 16, 'Brightness': 14, 'Tone type': 15}
SYN = {'Background Masking': 'Not use', 'Contrast': 6, 'Sharpness': 14, 'Brightness': 6, 'Tone type': 15}


def _glyph_png(path, text='14', size=(240, 60)):
    image = Image.new('RGB', size, 'white')
    ImageDraw.Draw(image).text((90, 20), text, fill='black')
    image.save(path)
    return str(path)


def _overlay(values, seen=None, settled=None, unsure=(), image=None):
    item = {'values': values, 'seen': seen if seen is not None else
            {key: [str(value)] for key, value in (values or settled or {}).items()},
            'settled': settled if settled is not None else {key: str(value) for key, value in (values or {}).items()},
            'unsure': list(unsure), 'votes': {}, 'reads': {}}
    if image:
        item['image'], item['images'] = image, [image]
    return item


def _record(overlays):
    result = TCResult('TC_XIPL_compatibility_03', 'synthetic')
    state = {'instances': [], 'files': {}}
    flow._record_post_recon_applied(result, CHANGED, CHANGED, CHANGED, 'TEST_3D_FLOW.xtp',
                                    'TEST_3D_FLOW.xtp', state, {}, 'after_restart', overlays,
                                    verify_saved=False)
    return result.checks[-1]


def _outcomes(check):
    return {row['field']: row['outcome'] for row in check.reading_evidence['rows']}


def test_table_embeds_field_capture_and_escapes_values(tmp_path):
    from core.report_layout import render_reading_evidence
    crop = _glyph_png(tmp_path / 'age.png', '43y')
    evidence = reading_evidence.pack(
        [reading_evidence.row('<Age>', '43Y"', 'unread', read='<script>4y</script>',
                              reads=[('컬러 판독', '4y'), ('흑백 판독', '43y')], image=crop)],
        [('행 전체 캡처', crop)])
    row = evidence['rows'][0]
    assert row['source_image'] == crop and row['image'].endswith('_view.png')
    with Image.open(row['image']) as view, Image.open(crop) as source:
        assert view.width < source.width * reading_evidence.VIEW_SCALE      # 글자 부분만 잘랐다
    html = render_reading_evidence(evidence)
    assert html.count('src="data:image/png;base64,') == 2
    assert '<script>' not in html and '&lt;script&gt;' in html and '&lt;Age&gt;' in html
    assert '컬러 판독' in html and '43y' in html and '판독 불가' in html


def test_missing_large_or_non_image_capture_is_not_embedded(tmp_path):
    import os
    from core import report_layout
    text = tmp_path / 'note.txt'
    text.write_text('x', encoding='utf-8')
    big = str(tmp_path / 'big.png')
    Image.frombytes('RGB', (600, 600), os.urandom(600 * 600 * 3)).save(big)
    assert os.path.getsize(big) > report_layout.READING_IMAGE_MAX_BYTES
    for image in (str(tmp_path / 'none.png'), str(text), big):
        html = report_layout.render_reading_evidence(
            {'rows': [{'field': 'F', 'expected': 'E', 'outcome': 'match', 'image': image}]})
        assert 'data:image' not in html and '칸 캡처 없음' in html


def test_check_json_round_trip_and_invalid_record_is_dropped(tmp_path):
    result = TCResult('TC_X', 'synthetic')
    evidence = reading_evidence.pack([reading_evidence.row('Contrast', 14, 'match', read='14')])
    result.add(9, 'Overlay', PASS, reading_evidence=evidence)
    result.add(9, 'broken', MANUAL, reading_evidence={'rows': [{'field': 'x', 'outcome': 'maybe'}]})
    result.finalize()
    data = json.loads(json.dumps(result.as_dict()))
    assert data['checks'][0]['reading_evidence'] == evidence
    assert 'reading_evidence' not in data['checks'][1]
    restored = result_from_dict(data)
    assert restored.checks[0].reading_evidence == evidence
    assert restored.checks[1].reading_evidence is None


def test_failure_and_manual_cards_open_table_and_step_detail_folds_it(tmp_path):
    crop = _glyph_png(tmp_path / 'cell.png', '4y')
    failed, manual = TCResult('TC_F', 'fail'), TCResult('TC_M', 'manual')
    failed.add(1, 'Overlay', FAIL, 'a', 'b', stop=False, reading_evidence=reading_evidence.pack(
        [reading_evidence.row('FIELD_FAIL', 'EXPECTED_FAIL', 'mismatch', read='READ_FAIL', image=crop)]))
    manual.add(1, 'Overlay', MANUAL, 'a', 'b', reading_evidence=reading_evidence.pack(
        [reading_evidence.row('FIELD_MANUAL', 'EXPECTED_MANUAL', 'unread', image=crop)]))
    for item in (failed, manual):
        item.finalize()
    paths = write_reports([failed, manual], str(tmp_path / 'out'), 'reading')
    html = open(paths['html'], encoding='utf-8').read()
    for section, field in (("id='failures'", 'FIELD_FAIL'), ("id='manual'", 'FIELD_MANUAL')):
        start = html.index(section)
        card = html[start:html.index('</section>', start)]
        assert field in card and 'class="reading"' in card and 'data:image/png;base64,' in card
        assert "<details class='more'><summary>판독 대조표" not in card          # 카드에서는 펼친다
    details = html[html.index("id='tc-results'"):]
    assert details.count("<details class='more'><summary>판독 대조표 · 칸 1개") == 2
    saved = json.loads(open(paths['json'], encoding='utf-8').read())
    row = saved['results'][0]['checks'][0]['reading_evidence']['rows'][0]
    assert row['source_image'] == crop and not row['image'].startswith('data:')   # JSON은 경로로 남긴다


def test_failed_builder_keeps_verdict_and_fail_still_stops():
    def broken(*_args):
        raise KeyError('synthetic')
    assert reading_evidence.safe(broken) is None
    assert reading_evidence.safe(lambda: {'rows': 'not a list'}) is None
    result = TCResult('TC_X', 'synthetic')
    with pytest.raises(StepFailed):
        result.add(1, 'Overlay', FAIL, reading_evidence=reading_evidence.safe(broken))
    assert result.checks[0].status == FAIL and result.checks[0].reading_evidence is None


@pytest.mark.parametrize('overlays, status, expected', [
    # 모두 합의·일치 → PASS, 모두 일치
    ({'Recon': _overlay(RECON), 'Syn': _overlay(SYN)}, PASS, {}),
    # 합의한 값이 다르고 기대값을 읽은 판독이 없다 → FAIL, 그 칸만 불일치
    ({'Recon': _overlay({**RECON, 'Contrast': 41}), 'Syn': _overlay(SYN)}, FAIL,
     {'Recon · Contrast': 'mismatch'}),
    # 합의한 값은 다르지만 기대값을 읽은 판독이 있다 → MANUAL, 불일치로 표시하지 않는다
    ({'Recon': _overlay({**RECON, 'Contrast': 41}, seen={'Contrast': ['14', '41']}), 'Syn': _overlay(SYN)},
     MANUAL, {'Recon · Contrast': 'unread'}),
    # 정하지 못한 칸 → MANUAL, 그 칸은 판독 불가. 합의했지만 다른 칸도 불일치로 표시하지 않는다
    ({'Recon': _overlay(None, settled={**{k: str(v) for k, v in RECON.items()}, 'Contrast': None,
                                        'Sharpness': '61'}, unsure=['Contrast']),
      'Syn': _overlay(SYN)}, MANUAL, {'Recon · Contrast': 'unread', 'Recon · Sharpness': 'unread'}),
    # 캡처·선택 실패 → FAIL, 칸은 판독 불가(불일치로 단정하지 않는다)
    ({'Recon': {'error': 'RuntimeError', 'image': None}, 'Syn': _overlay(SYN)}, FAIL,
     {'Recon · ' + key: 'unread' for key in RECON}),
])
def test_post_recon_table_copies_the_verdict(overlays, status, expected):
    check = _record(overlays)
    assert check.status == status
    outcomes = _outcomes(check)
    assert len(outcomes) == 10
    assert outcomes == {**{'%s · %s' % (label, key): 'match' for label, values in (('Recon', RECON), ('Syn', SYN))
                           for key in values}, **expected}
    # 불일치 칸이 있는 것과 판정의 확정 불일치(FAIL)가 같은 규칙이다.
    assert ('mismatch' in outcomes.values()) == (status == FAIL and 'error' not in overlays['Recon'])


def test_post_recon_context_is_the_ocr_region_and_original_is_kept(tmp_path):
    capture = _glyph_png(tmp_path / 'TC_XIPL_compatibility_03_after_restart_Recon_overlay.png', 'Contrast: 14',
                         size=(400, 200))
    before = open(capture, 'rb').read()
    item = _overlay(RECON, image=capture)
    item['reads'] = {'Contrast': [['반전 회색조 1회차', '14'], ['흑백 변환 1회차', '14']]}
    check = _record({'Recon': item, 'Syn': _overlay(SYN)})
    context = check.reading_evidence['context']
    assert [entry['label'] for entry in context] == ['Recon 영상 Overlay 판독 영역 · 1회차 캡처']
    region = context[0]['image']
    assert region.endswith('_ocr_region.png') and open(capture, 'rb').read() == before
    with Image.open(region) as image:
        assert image.size == (int(400 * .37), int(200 * .25))
    contrast = next(row for row in check.reading_evidence['rows'] if row['field'] == 'Recon · Contrast')
    assert contrast['reads'] == [['반전 회색조 1회차', '14'], ['흑백 변환 1회차', '14']]


def test_post_recon_table_failure_does_not_change_verdict(monkeypatch):
    def broken(*_args):
        raise OSError('synthetic disk error')
    monkeypatch.setattr(flow, '_post_recon_reading', broken)
    check = _record({'Recon': _overlay({**RECON, 'Contrast': 41}), 'Syn': _overlay(SYN)})
    assert check.status == FAIL and check.reading_evidence is None


def test_image_overlay_rows_copy_labels_seen(tmp_path):
    crop = _glyph_png(tmp_path / '05_panel1_bottom.png', '-- kVp')
    marks = {'panel1': {'Dose kVp': True, 'Dose mAs': False, 'Patient ID': False, 'Birth Date': True}}
    reads = {'panel1': {'bottom_bin150_psm6': '-- kVp', 'top_bin150_psm6': 'DATAFL 19800101'}}
    rows = image_overlay.reading_rows(marks, reads, ['Dose kVp', 'Dose mAs'], str(tmp_path), '05_panel',
                                      'bottom', image_overlay.LABEL_TEXT, 'mismatch')
    assert [(row['outcome'], row['expected']) for row in rows] == [('match', 'kVp'), ('mismatch', 'mAs')]
    assert rows[0]['read'] == '-- kVp' and rows[0]['source_image'] == crop
    patient = image_overlay.reading_rows(marks, reads, ['Patient ID', 'Birth Date'], str(tmp_path), '05_panel',
                                         'top', {'Patient ID': 'DATAFLOW_X', 'Birth Date': '19800101'}, 'unread')
    assert [row['outcome'] for row in patient] == ['unread', 'match']   # MANUAL 판정은 불일치로 쓰지 않는다
    none = image_overlay.reading_rows({}, {}, ['Dose kVp'], str(tmp_path), '05_panel', 'bottom',
                                      image_overlay.LABEL_TEXT, 'mismatch')
    assert none[0]['outcome'] == 'unread'


def test_print_overlay_rows_copy_judged_areas(tmp_path):
    prefix = str(tmp_path / '06_film_overlay')
    for area in ('header', 'top', 'bottom'):
        _glyph_png(prefix + '_' + area + '.png', area)
    target = {'PatientID': 'DATAFLOW_MWL_01', 'PatientBirthDate': '19800101'}
    texts = {'header': {'x12': 'DATAFLOW_MWL_01 19800101', 'x8': '', 'x5': ''},
             'top': {'x12': '0.0 cm 99 N', 'x8': '', 'x5': ''},
             'bottom': {'x12': '', 'x8': '', 'x5': ''}}
    expect = print_overlay.film_expectations(target)
    seen = print_overlay.judge_film_areas(texts, expect)
    evidence = print_overlay.film_reading(texts, seen, expect, target, prefix)
    outcomes = {row['field']: row['outcome'] for row in evidence['rows']}
    assert outcomes == {'Header · Patient ID': 'match', 'Header · Birth Date': 'match',
                        'Top · Thickness': 'match', 'Top · Compression Force': 'mismatch',
                        'Bottom · HVL': 'unread', 'Bottom · AGD': 'unread'}
    assert print_overlay.film_all_ok(seen) is False
    force = next(row for row in evidence['rows'] if row['field'] == 'Top · Compression Force')
    assert force['expected'] == '35 N' and force['source_image'] == prefix + '_top.png'
    assert reading_evidence.valid(evidence)
    assert re.search(r'x12 확대 판독', json.dumps(evidence, ensure_ascii=False))


def test_wf15_dose_rows_follow_the_panel_kind_spec(tmp_path):
    # 2D는 값, 3D(Recon)는 `--`가 사양대로의 일치다(사양서 723쪽 SRS 03-50-10). 판정 코드와 같은 규칙이다.
    crop1 = _glyph_png(tmp_path / '02_preview_panel1_bottom.png', '28 kVp 32 mAs')
    _glyph_png(tmp_path / '02_preview_panel2_bottom.png', '-- kVp')
    reads = {'panel1': {'top_bin150_psm6': 'LCC', 'bottom_bin150_psm6': '28 kVp 32 mAs'},
             'panel2': {'top_bin150_psm6': 'LCC (3D-N)', 'bottom_bin150_psm6': '-- kVp 28 mAs'},
             'panel3': {'top_bin150_psm6': 'RCC (3D-W)', 'bottom_bin150_psm6': 'smudge'}}
    kinds = {name: image_overlay.panel_kind(value) for name, value in reads.items()}
    rows = image_overlay.dose_reading_rows(reads, kinds, str(tmp_path), '02_preview_panel')
    outcomes = {row['field']: row['outcome'] for row in rows}
    assert outcomes == {'Dose kVp (panel1, 2D)': 'match', 'Dose mAs (panel1, 2D)': 'match',
                        'Dose kVp (panel2, 3D)': 'match', 'Dose mAs (panel2, 3D)': 'mismatch',
                        'Dose kVp (panel3, 3D)': 'unread', 'Dose mAs (panel3, 3D)': 'unread'}
    first = rows[0]
    assert first['expected'] == '<숫자> kVp (값 표시)' and first['read'] == '28 kVp 32 mAs'
    assert first['source_image'] == crop1
    assert rows[2]['expected'] == '-- kVp (값 미표시)'
    assert reading_evidence.valid(reading_evidence.pack(rows))


def test_wf15_view_comparison_rows_copy_the_observation_verdict(tmp_path):
    view_marks = {'panel1': {'Dose kVp': True, 'Dose mAs': False, 'Patient ID': True, 'Birth Date': True}}
    view_reads = {'panel1': {'bottom_bin150_psm6': '28 kVp', 'top_bin150_psm6': 'DATAFLOW 19800101'}}
    preview_any = {'Dose kVp': True, 'Dose mAs': True, 'Patient ID': True, 'Birth Date': True}
    view_any = {'Dose kVp': True, 'Dose mAs': False, 'Patient ID': True, 'Birth Date': True}
    labels = ['Dose kVp', 'Dose mAs', 'Patient ID', 'Birth Date']
    rows = image_overlay.comparison_reading_rows(preview_any, view_any, view_marks, view_reads, labels,
                                                 str(tmp_path), '04_view_panel')
    assert [row['outcome'] for row in rows] == ['match', 'mismatch', 'match', 'match']
    assert rows[1]['expected'] == 'Preview와 같음 (Preview: 보임)' and rows[1]['read'] == 'View: 안 보임'
    assert rows[0]['source_image'].endswith('04_view_panel1_bottom.png')
    assert rows[2]['source_image'].endswith('04_view_panel1_top.png')
    empty = image_overlay.comparison_reading_rows(preview_any, {}, {}, {}, ['Dose kVp'], str(tmp_path), 'x')
    assert empty[0]['outcome'] == 'mismatch' and 'image' not in empty[0]
