"""REQ-REPORT-001: 사용자가 직접 확인할 TC Step 을 체크리스트 Step 기준으로 보인다."""
import os
import tempfile
from types import SimpleNamespace
from unittest import mock

from openpyxl import Workbook, load_workbook

import run
from core import checklist
from core.result import FAIL, MANUAL, PASS, TCResult, user_actions, write_reports

STEPS = "1. Image Overlay 를 추가한다.\n2. Print Overlay 를 추가한다.\n3. Overlay 를 선택한다."
EXPECTED = "1. 저장된다.\n2. Print Overlay 구성이 저장된다.\n3. 적용된다."
ROWS = {'TC_X': {'steps': STEPS, 'expected': EXPECTED}}


def aborted_result():
    result = TCResult('TC_X', 'Overlay 설정')
    result.add(1, '자동화 Image Overlay 확인', PASS, stop=False)
    result.abort(0, 'TC_X 실행', RuntimeError("OCR 선택 중단(unreadable): '1 X 2'"))
    return result


def padded():
    result = aborted_result()
    ctx = SimpleNamespace()
    with mock.patch.object(checklist, 'source_path', return_value='x.xlsx'), \
         mock.patch.object(checklist, 'read_tc_rows', return_value=ROWS):
        run.pad_aborted_steps(ctx, [result])
    result.finalize()
    return result


def test_abort_keeps_its_step_and_records_the_checklist_step_being_run():
    result = padded()
    abort = next(c for c in result.checks if c.title == 'TC_X 실행')
    assert abort.step == 0
    assert abort.interrupted_step == 2
    assert abort.as_dict()['interrupted_step'] == 2
    # 판정 기록은 예전과 같다: WU 변환이 Step 번호로 복사하므로 중단 Step 도 채운다.
    assert sorted(c.step for c in result.checks if c.title.endswith('미수행')) == [2, 3]


def test_user_actions_name_checklist_steps_not_automation_internals():
    result = padded()
    result_manual = TCResult('TC_X', 'Overlay 설정')
    result_manual.add(3, '자동화 표시 비교', MANUAL, note='화면 비교는 사람이 본다.', stop=False)
    actions = user_actions([result, result_manual], ROWS)
    assert [(a['step'], a['kind']) for a in actions] == [
        (2, '자동화 중단 — 이 Step 부터 직접 수행'),
        (3, '미수행 — 직접 수행'),
        (3, '수동 확인 — 직접 확인')]
    first = actions[0]
    assert first['step_description'] == 'Print Overlay 를 추가한다.'
    assert first['expected_result'] == 'Print Overlay 구성이 저장된다.'
    assert '1 X 2' in first['automation_reference']


def test_plain_fail_is_marked_for_recheck_on_its_own_step():
    result = TCResult('TC_X', 'Overlay 설정')
    result.add(3, '자동화 Overlay 비교', FAIL, '적용', '미적용', stop=False)
    action = user_actions([result], ROWS)[0]
    assert (action['step'], action['kind']) == (3, '실패 — 직접 재확인')
    assert action['step_description'] == 'Overlay 를 선택한다.'


def test_txt_html_and_json_list_the_user_steps():
    result = padded()
    with tempfile.TemporaryDirectory() as directory:
        paths = write_reports([result], directory, 'actions', meta={'checklist': ROWS})
        txt = open(paths['txt'], encoding='utf-8').read()
        html = open(paths['html'], encoding='utf-8').read()
        import json
        data = json.load(open(paths['json'], encoding='utf-8'))
    assert '[ 직접 확인할 TC Step ]' in txt
    assert 'TC_X Step 2 [자동화 중단 — 이 Step 부터 직접 수행] Print Overlay 를 추가한다.' in txt
    assert '직접 확인할 TC Step' in html and 'Print Overlay 구성이 저장된다.' in html
    assert [a['step'] for a in data['user_actions']] == [2, 3]


def test_checklist_columns_use_checklist_step_text():
    result = padded()
    with tempfile.TemporaryDirectory() as directory:
        source = os.path.join(directory, 'source.xlsx')
        book = Workbook()
        sheet = book.active
        sheet.append(['TC ID', 'Step Description', 'Expected Result'])
        sheet.append(['TC_X', STEPS, EXPECTED])
        book.save(source)
        with mock.patch.object(checklist, 'read_tc_rows', return_value=ROWS):
            info = checklist.write_results(source, [result],
                                           out_path=os.path.join(directory, 'out.xlsx'))
        sheet = load_workbook(info['path']).active
        header = {sheet.cell(1, c).value: c for c in range(1, sheet.max_column + 1)}
        fails = sheet.cell(2, header['실패 항목']).value
    assert fails.splitlines()[0].startswith(
        '[Step 2] 자동화 중단 — 이 Step 부터 직접 수행: Print Overlay 를 추가한다.')
    assert '기대: Print Overlay 구성이 저장된다.' in fails
    assert '[Step 3] 미수행 — 직접 수행: Overlay 를 선택한다.' in fails
