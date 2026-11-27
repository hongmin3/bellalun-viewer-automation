# -*- coding: utf-8 -*-
"""사람 확인 반영 리포트(REQ-REPORT-003, frame/FRAME.md 4절 8).

Validates: REQ-REPORT-003
"""
import hashlib
import json
import re

import pytest

from core import manual_review as mr
from core.automation_health import completed_report_data
from core.result import BLOCKED, FAIL, MANUAL, PASS, SKIP, TCResult, write_reports


def _results():
    ok = TCResult('TC_Basic_WorkFlow_01', 'pass')
    ok.add(1, 'ok', PASS)
    failed = TCResult('TC_Basic_WorkFlow_03', 'fail')
    failed.add(1, 'saved', PASS)
    failed.add(2, 'overlay shown', FAIL, 'a', 'b', stop=False)
    failed.add(3, 'Step 3 미수행', BLOCKED, note='앞 Step 실패')
    manual = TCResult('TC_Basic_WorkFlow_15', 'manual')
    manual.add(3, 'dose read', MANUAL, 'value', 'unread')
    human = TCResult('TC_Basic_QC_01', 'human only')
    human.skip(0, '사람 전용 TC — 자동화 수행 제외', 'reason')
    optional = TCResult('TC_WindowsUpdate_09', 'cd optional')
    optional.add(1, 'usb', PASS)
    optional.skip(0, 'CD Export/Import', 'not target', blocks_verdict=False)
    rows = [ok, failed, manual, human, optional]
    for row in rows:
        row.finalize()
    return rows


def _write(tmp_path, run_id='20261127-000000-aaaa'):
    rows = _results()
    paths = write_reports(rows, str(tmp_path / 'Reports'), '20261127_120000',
                          meta={'run_id': run_id, 'execution_mode': 'live', 'chain_completed': True})
    return rows, paths


def _record(paths, decisions, reviewer='검토자', run_id=None):
    """리포트 HTML 안의 자료로 브라우저가 만드는 것과 같은 기록을 만든다."""
    page = open(paths['html'], encoding='utf-8').read()
    data = json.loads(re.search(r"<script type='application/json' id='review-data'>(.*?)</script>", page, re.S)
                      .group(1))
    boxes = re.findall(r"<div class='review-box' data-idx='([^']*)' data-tc='([^']*)' data-step='([^']*)' "
                       r"data-seq='([^']*)' data-title='([^']*)' data-auto='([^']*)'", page)
    items = []
    for key, tc_id, step, seq, title, auto in boxes:
        if (tc_id, step) in decisions:
            decision, memo = decisions[(tc_id, step)]
            items.append({'tc_id': tc_id, 'key': key, 'step': step, 'seq': seq, 'title': title,
                          'auto_status': auto, 'decision': decision, 'memo': memo})
    return {'format': mr.FORMAT, 'fingerprint': data['fingerprint'] if run_id is None else 'x',
            'run_id': data['run_id'], 'reviewer': reviewer, 'reviewed_at': '2026-11-27T12:00:00Z',
            'items': items}, boxes, data


def _hash(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def test_report_offers_boxes_only_for_reviewable_steps_and_one_panel(tmp_path):
    rows, paths = _write(tmp_path)
    page = open(paths['html'], encoding='utf-8').read()
    _, boxes, data = _record(paths, {})
    assert sorted((tc, step, auto) for _, tc, step, _, _, auto in boxes) == sorted([
        ('TC_Basic_WorkFlow_03', '2', 'FAIL'), ('TC_Basic_WorkFlow_03', '3', 'BLOCKED'),
        ('TC_Basic_WorkFlow_15', '3', 'MANUAL'), ('TC_Basic_QC_01', '0', 'SKIP')])
    assert page.count("id='review-panel'") == 1 and page.count("id='review-script'") == 1
    assert data['fingerprint'] == mr.fingerprint(rows, '20261127-000000-aaaa')
    assert "id='overview-headline'" in page and "data-status='FAIL'" in page
    # 사유가 필요한 항목에만 경고 문구가 붙는다.
    assert page.count("class='rv-warn'") == 2


def test_partial_review_builds_reviewed_copy_and_keeps_originals(tmp_path):
    rows, paths = _write(tmp_path)
    before = {kind: _hash(paths[kind]) for kind in ('html', 'json')}
    review, _, _ = _record(paths, {('TC_Basic_WorkFlow_15', '3'): ('PASS', '캡처 값 28 kVp 확인'),
                                   ('TC_Basic_QC_01', '0'): ('PASS', '')})
    out = mr.build(paths['json'], review)
    assert {kind: _hash(paths[kind]) for kind in ('html', 'json')} == before        # 원본 보존
    assert out['html'].replace('\\', '/').endswith('Reports/reviewed/Result_20261127_120000_reviewed.html')
    assert out['applied'] == 2 and out['remaining'] == 2                              # 부분 검토
    data = json.load(open(out['json'], encoding='utf-8'))
    verdicts = {row['tc_id']: row['verdict'] for row in data['results']}
    assert verdicts['TC_Basic_WorkFlow_15'] == PASS and verdicts['TC_Basic_QC_01'] == PASS
    assert verdicts['TC_Basic_WorkFlow_03'] == FAIL                                   # 미확인 FAIL은 그대로
    assert data['meta']['report_role'] == mr.REVIEW_ROLE and data['meta']['chain_completed'] is False
    assert data['meta']['human_review']['auto_result']['sha256'] == before['json']
    assert not completed_report_data(data, 'run-regression')                          # 게이트 입력 아님
    page = open(out['html'], encoding='utf-8').read()
    assert "id='human-review-summary'" in page and "class='review-box'" not in page
    assert '종합 FAIL' in page and '사람 확인(검토자' in page


def test_fail_and_blocked_need_reason_and_full_review_recomputes_overall(tmp_path):
    rows, paths = _write(tmp_path)
    decisions = {('TC_Basic_WorkFlow_03', '2'): ('PASS', ''), ('TC_Basic_WorkFlow_03', '3'): ('PASS', '직접 수행')}
    review, _, _ = _record(paths, decisions)
    with pytest.raises(mr.ReviewError, match='사유'):
        mr.build(paths['json'], review)
    assert not (tmp_path / 'Reports' / 'reviewed').exists()                         # 하나라도 틀리면 반영하지 않는다
    decisions = {('TC_Basic_WorkFlow_03', '2'): ('PASS', '자동화 판독 오류, 화면 정상'),
                 ('TC_Basic_WorkFlow_03', '3'): ('PASS', '직접 수행 정상'),
                 ('TC_Basic_WorkFlow_15', '3'): ('PASS', ''), ('TC_Basic_QC_01', '0'): ('FAIL', '버튼 없음')}
    review, _, _ = _record(paths, decisions)
    out = mr.build(paths['json'], review)
    data = json.load(open(out['json'], encoding='utf-8'))
    verdicts = {row['tc_id']: row['verdict'] for row in data['results']}
    assert verdicts == {'TC_Basic_WorkFlow_01': PASS, 'TC_Basic_WorkFlow_03': PASS, 'TC_Basic_WorkFlow_15': PASS,
                        'TC_Basic_QC_01': FAIL, 'TC_WindowsUpdate_09': PASS}
    assert out['remaining'] == 0
    page = open(out['html'], encoding='utf-8').read()
    assert '종합 FAIL' in page and "<div class='n FAIL' data-status='FAIL'>1</div>" in page


def test_previous_run_and_stale_result_reviews_are_rejected(tmp_path):
    rows, paths = _write(tmp_path / 'r1', run_id='20261127-061323-847ee574')
    review, _, _ = _record(paths, {('TC_Basic_WorkFlow_15', '3'): ('PASS', '')})
    # 다음 회차: 같은 TC·Step이어도 실행 번호가 달라 이전 회차 기록을 받지 않는다.
    _, next_paths = _write(tmp_path / 'r2', run_id='20261127-073915-7f9ee6b9')
    with pytest.raises(mr.ReviewError, match='다른 회차'):
        mr.build(next_paths['json'], review)
    # 오래된 결과 파일: 같은 회차라도 자동 판정이 바뀐 결과에는 반영하지 않는다.
    data = json.load(open(paths['json'], encoding='utf-8'))
    data['results'][2]['checks'][0]['status'] = PASS
    stale = tmp_path / 'r1' / 'Reports' / 'Result_stale.json'
    stale.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(mr.ReviewError, match='결과 파일이 바뀜'):
        mr.build(str(stale), review)
    # 검토본을 다시 원본으로 쓰지 않는다.
    out = mr.build(paths['json'], review)
    with pytest.raises(mr.ReviewError, match='검토본'):
        mr.build(out['json'], review)


def test_reviewed_html_record_round_trips_into_build(tmp_path):
    rows, paths = _write(tmp_path)
    review, _, _ = _record(paths, {('TC_Basic_WorkFlow_15', '3'): ('FAIL', '값 다름')})
    downloaded = tmp_path / 'Result_20261127_120000_reviewed.html'
    downloaded.write_text('<html><body><script type="application/json" id="human-review">%s</script></body></html>'
                          % json.dumps(review, ensure_ascii=False).replace('<', '\\u003c'), encoding='utf-8')
    assert mr.read_reviewed_html(str(downloaded)) == review
    out = mr.build(str(paths['json']), str(downloaded))
    data = json.load(open(out['json'], encoding='utf-8'))
    assert {row['tc_id']: row['verdict'] for row in data['results']}['TC_Basic_WorkFlow_15'] == FAIL
    with pytest.raises(mr.ReviewError):
        mr.read_reviewed_html(paths['html'])


def test_verdict_rules_match_tcresult():
    for checks in ([(PASS, False)], [(SKIP, False)], [(SKIP, True), (PASS, False)], [(MANUAL, False), (FAIL, False)],
                   [(BLOCKED, False), (MANUAL, False)], [(PASS, False), (SKIP, False)]):
        row = TCResult('TC', 't')
        for status, blocks in checks:
            row.add(1, 'x', status, stop=False, blocks_verdict=blocks or None)
        assert mr.verdict_of(checks) == row.verdict
    assert mr.overall_of([PASS, SKIP, MANUAL]) == MANUAL and mr.overall_of([]) is None


def test_review_window_opens_this_runs_html_report(tmp_path):
    """수동 검토 창(REQ-QA-003)에서 이번 실행의 HTML 리포트를 열어 사람 확인을 반영한다."""
    from types import SimpleNamespace
    from bellalunauto.qa_dialogs import review_report
    html_path, json_path = tmp_path / 'Result_1.html', tmp_path / 'Result_1.json'
    html_path.write_text('<html></html>', encoding='utf-8')
    json_path.write_text('{}', encoding='utf-8')
    assert review_report(SimpleNamespace(data={'reports': [str(json_path), str(html_path)]})) == str(html_path)
    assert review_report(SimpleNamespace(data={'reports': [str(json_path)]})) is None
    assert review_report(SimpleNamespace(data={'reports': [str(tmp_path / 'gone.html')]})) is None
