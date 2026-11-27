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


# --- 글자 차이 기록 `compare`(frame/FRAME.md 2.9 3항, 4절 7-보완) -----------------------------
#: 1.0.0.012 기본 r1 `20261127-061323-847ee574` WF_03 Step 5 panel2 위 영역의 실제 판독 원문 일부.
REAL_PANEL2_TOP = {
    'top_auto_x6_psm6': 'LCC (3D-N)\nID: DATA _FLOY MY¥YL_O1\nName: AUTO MY¥L\nBirth Date: 1980/01/01',
    'top_line2_auto_x6_psm7': 'ID: DATA_FLOY_MYWL_0O1',
    'top_line4_auto_x6_psm7': 'Birth Date: 1980/01/01',
}


def test_compare_picks_closest_phrase_and_strips_field_prefix():
    found = reading_evidence.compare('DATA_FLOW_MWL_01', '', REAL_PANEL2_TOP.items(), '규칙')
    assert found['expected'] == 'DATA_FLOW_MWL_01' and found['read'] == 'DATA_FLOY_MYWL_0O1'
    assert found['label'].startswith('규칙 · 가장 비슷한 판독: top_line2_auto_x6_psm7')
    used = reading_evidence.compare('19800101', 'Birth Date: 1980/01/01', REAL_PANEL2_TOP.items())
    assert used['read'] == '1980/01/01' and used['label'] == '판정에 쓴 판독'
    header = reading_evidence.compare('DATAFLOW_MWL_01', '', [('x12', 'DATAFLOW_MWL_0l 19800101')])
    assert header['read'] == 'DATAFLOW_MWL_0l'          # 같은 줄의 다른 값(생년월일)은 대조하지 않는다
    assert reading_evidence.compare('', 'x', [('a', 'x')]) is None
    assert reading_evidence.compare('VALUE', '', [('a', ''), ('b', '<OCR ERR timeout>')]) is None


def test_compare_survives_json_checkpoint_and_marks_differences_in_card(tmp_path):
    crop = _glyph_png(tmp_path / '05_panel2_top.png', 'ID')
    marks = {'panel2': {'Patient ID': False, 'Birth Date': True}}
    reads = {'panel2': REAL_PANEL2_TOP}
    rows = image_overlay.reading_rows(
        marks, reads, ['Patient ID', 'Birth Date'], str(tmp_path), '05_panel', 'top',
        {'Patient ID': 'DATA_FLOW_MWL_01', 'Birth Date': '19800101'}, 'unread',
        compare_labels=image_overlay.PATIENT_MARKERS)
    assert rows[0]['outcome'] == 'unread' and rows[0]['compare']['read'] == 'DATA_FLOY_MYWL_0O1'
    assert rows[1]['outcome'] == 'match' and rows[1]['compare']['read'] == '1980/01/01'
    dose = image_overlay.reading_rows(marks, reads, ['Dose kVp'], str(tmp_path), '05_panel', 'bottom',
                                      image_overlay.LABEL_TEXT, 'mismatch')
    assert 'compare' not in dose[0]                     # 단위 라벨만 아는 칸은 진짜 텍스트가 없다
    evidence = reading_evidence.pack(rows)
    result = TCResult('TC_Basic_WorkFlow_03', 'overlay')
    result.add(5, 'patient', MANUAL, reading_evidence=evidence)
    result.finalize()
    restored = result_from_dict(json.loads(json.dumps(result.as_dict())))     # 회차 JSON → 저장점 재개
    assert restored.checks[0].reading_evidence == evidence
    paths = write_reports([restored], str(tmp_path / 'out'), 'compare')
    html = open(paths['html'], encoding='utf-8').read()
    card = html[html.index("id='manual'"):]
    card = card[:card.index('</section>')]
    assert '다른 글자 강조' in card and '<mark class="diff">' in card and 'DATA_FLOW_MWL_01' not in card.split(
        '확인할 진짜 텍스트')[0]
    saved = json.loads(open(paths['json'], encoding='utf-8').read())
    assert saved['results'][0]['checks'][0]['reading_evidence']['rows'][0]['compare'] == rows[0]['compare']


def test_malformed_compare_is_dropped_with_the_record():
    bad = {'rows': [{'field': 'x', 'outcome': 'unread', 'compare': {'expected': 1}}]}
    assert not reading_evidence.valid(bad)
    assert reading_evidence.safe(lambda: bad) is None


def test_film_and_post_recon_rows_compare_confirmed_values(tmp_path):
    prefix = str(tmp_path / '06_film_overlay')
    target = {'PatientID': 'DATAFLOW_MWL_01', 'PatientBirthDate': '19800101'}
    texts = {'header': {'x12': 'DATAFLOW_MWL_01 19800101'}, 'top': {'x12': '0.0 cm 99 N'},
             'bottom': {'x12': 'HYL: Not valid'}}
    expect = print_overlay.film_expectations(target)
    seen = print_overlay.judge_film_areas(texts, expect)
    rows = {row['field']: row for row in print_overlay.film_reading(texts, seen, expect, target, prefix)['rows']}
    force = rows['Top · Compression Force']
    assert force['outcome'] == 'mismatch' and force['compare']['expected'] == '35 N'
    assert force['compare']['read'] == '99 N'
    assert rows['Header · Birth Date']['compare']['read'] == '19800101'
    evidence = flow._post_recon_reading({'Recon': _overlay(None, seen={'Contrast': ['13']},
                                                           settled={'Contrast': '13'}, unsure=['Contrast'])},
                                        {'Recon': {'Contrast': 14}})
    contrast = next(row for row in evidence['rows'] if row['field'] == 'Recon · Contrast')
    assert contrast['compare']['expected'] == '14' and contrast['compare']['read'] == '13'


def test_post_recon_cells_crop_each_named_line_from_saved_region(tmp_path, monkeypatch):
    """XIPL_03 칸별 크롭: 저장된 판독 영역에서 칸 이름 줄만 자른다(화면 조작 없음).

    줄 위치는 1.0.0.012 `TC_XIPL_compatibility_03_after_apply_Recon_overlay.png` 판독 영역의 실측값이다.
    """
    import pytesseract
    region = tmp_path / 'overlay_ocr_region.png'
    Image.new('RGB', (653, 244), 'black').save(region)
    lines = [((446, 76, 635, 92), 'Background Masking: X'), ((535, 100, 636, 113), 'Contrast: 14'),
             ((522, 124, 635, 140), 'Sharpness: 16'), ((519, 148, 636, 164), 'Brightness: 14'),
             ((519, 172, 635, 188), 'Tone Type: 15'), ((10, 10, 60, 20), 'Recon')]
    data = {key: [] for key in ('text', 'left', 'top', 'width', 'height', 'block_num', 'par_num', 'line_num')}
    for number, ((left, top, right, bottom), text) in enumerate(lines, 1):
        data['text'].append(text)
        data['left'].append(left * 3)
        data['top'].append(top * 3)
        data['width'].append((right - left) * 3)
        data['height'].append((bottom - top) * 3)
        data['block_num'].append(1)
        data['par_num'].append(1)
        data['line_num'].append(number)
    monkeypatch.setattr(pytesseract, 'image_to_data', lambda *a, **k: data)
    cells = flow._post_recon_cells(region)
    assert sorted(cells) == sorted(flow._POST_RECON_KEYS)
    with Image.open(cells['Contrast']) as crop:
        assert crop.size == (636 - 535 + 8, 113 - 100 + 8)
    assert cells['Tone type'].endswith('_ocr_region_Tone_type.png')


def test_3d_acquisition_card_label_and_header_rows_copy_the_verdict(tmp_path):
    """3D 촬영 TC Step 1·2: 판독에 쓴 화면 조각을 남기고 판정 결과를 그대로 옮긴다."""
    from tests import system_compat as sc
    crop = _glyph_png(tmp_path / '01_card_label_3D-N.png', 'LCC')
    ok = sc.card_label_reading('LCCGD-N)', '3D-N', True, crop)['rows'][0]
    assert ok['outcome'] == 'match' and ok['expected'] == 'LCC (3D-N)' and ok['source_image'] == crop
    assert ok['compare']['read'] == 'LCCGD-N)'
    bad = sc.card_label_reading('LCC (3D-W)', '3D-N', False, crop)['rows'][0]
    assert bad['outcome'] == 'mismatch'
    blank = sc.header_reading('', 'SYS3D_N_01', False, None)['rows'][0]
    assert blank['outcome'] == 'unread' and 'compare' not in blank
    header = sc.header_reading('AUTO SYS3D_N_0l', 'SYS3D_N_01', False, None)['rows'][0]
    assert header['outcome'] == 'mismatch' and header['compare']['read'] == 'SYS3D_N_0l'


def test_wf08_step7_pixel_evidence_shows_compared_rasters_and_threshold(tmp_path):
    """WF_08 Step 7 픽셀 판정 근거: 비교에 쓴 정규화 영상과 유사도를 남기고 판정과 같은 결과를 적는다."""
    from tests import workflow08 as wf08
    film, web, other = tmp_path / '07_film_3dn.png', tmp_path / 'web.png', tmp_path / 'other.png'
    Image.new('L', (300, 380), 120).save(film)
    Image.new('L', (300, 380), 121).save(web)
    Image.new('L', (300, 380), 10).save(other)
    same = wf08._image_similarity(str(film), str(web))
    evidence = wf08.pixel_reading(str(film), str(web), same, str(tmp_path / 'cmp.png'))
    row = evidence['rows'][0]
    assert row['outcome'] == 'match' and row['expected'] == '유사도 0.96 이상'
    with Image.open(row['source_image']) as sheet:
        assert sheet.size == (256 * 3 + 16, 320)
    assert evidence['title'] == wf08.PIXEL_TITLE and reading_evidence.valid(evidence)
    far = wf08._image_similarity(str(film), str(other))
    assert wf08.pixel_reading(str(film), str(other), far, str(tmp_path / 'cmp2.png'))['rows'][0]['outcome'] == 'mismatch'
    panes = wf08.pane_reading({'crops': [str(film), str(web)], 'pairs': {'0-1': {'mean_delta': 0.4}}})
    assert panes['rows'][0]['outcome'] == 'mismatch' and len(panes['context']) == 2
    cross = wf08.cross_reading({'2D': {'scores': {'2D': .99, '3D-N': .9}, 'best_match': '2D'},
                                '3D-N': {'scores': {'2D': .97, '3D-N': .95}, 'best_match': '2D'}})
    assert [r['outcome'] for r in cross['rows']] == ['match', 'mismatch']


def test_xipl05_selection_evidence_and_custom_title_in_report(tmp_path):
    """XIPL_05 화면 선택용 OCR 근거: 규칙·읽은 값·고른 값. 리포트 제목도 선택 근거로 보인다."""
    picked = {'fiber': {'picked': 4.0, 'threshold': 4.0, 'items': [3.5, 4.0, 4.5], 'boundary': 'pass'},
              'speck': {'picked': 2.5, 'threshold': 3.0, 'items': [2.5, 3.0], 'boundary': 'fail'}}
    evidence = flow.qc_selection_reading(picked)
    assert [row['read'] for row in evidence['rows']] == ['4.0', '2.5']
    assert '이상 중 가장 낮은 값' in evidence['rows'][0]['expected']
    assert '미만 중 가장 높은 값' in evidence['rows'][1]['expected']
    result = TCResult('TC_XIPL_compatibility_05', 'qc')
    result.add(3, 'Q.C 채점', FAIL, stop=False, reading_evidence=evidence)
    result.finalize()
    paths = write_reports([result], str(tmp_path / 'out'), 'qc')
    html = open(paths['html'], encoding='utf-8').read()
    assert flow.QC_SELECTION_TITLE in html
    assert "<summary>%s · 2개</summary>" % flow.QC_SELECTION_TITLE in html
    assert not reading_evidence.valid(dict(evidence, title=3))
