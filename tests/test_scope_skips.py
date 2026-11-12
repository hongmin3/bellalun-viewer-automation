"""Validates: REQ-TCUP-001. 사람 전용 TC가 리포트에서 사라지는 결함 방지."""
import json
from pathlib import Path
from core.result import TCResult


def test_regression_retains_ten_human_only_cases_as_reasoned_skips():
    from core import scope_results
    scope = json.loads((Path(__file__).resolve().parents[1] / 'automation_scope.json').read_text(encoding='utf-8'))
    rows = scope_results.regression_skips(scope, [])
    wanted = {f'TC_Basic_Install_{n:02}' for n in range(3, 7)} | {
        'TC_Basic_QC_01', 'TC_Basic_QC_02', 'TC_Basic_Performance_01',
        'TC_Basic_Performance_02', 'TC_Basic_Performance_03', 'TC_Basic_WorkFlow_16'}
    assert {r.tc_id for r in rows} == wanted
    assert all(r.verdict == 'SKIP' and r.checks[0].note for r in rows)


def test_skip_insertion_preserves_existing_verdict_and_excludes_wu():
    from core import scope_results
    prior = TCResult('TC_Basic_WorkFlow_16', 'existing')
    prior.add(1, 'observation', 'FAIL', stop=False)
    scope = [dict(tc_id=prior.tc_id, title='Kiosk', level='SKIP', reason='human'),
             dict(tc_id='TC_WindowsUpdate_01', title='WU', checklist='windows_update', level='SKIP', reason='human'),
             dict(tc_id='TC_Basic_Install_07', title='deferred', level='PARTIAL', reason='later')]
    assert scope_results.regression_skips(scope, [prior]) == []
    assert prior.verdict == 'FAIL'


def test_coverage_counts_human_skip_without_converting_result_manual(tmp_path):
    import re
    from core.result import write_reports
    result = TCResult('TC_Basic_Install_01', 'baseline pending')
    result.add(1, 'baseline', 'MANUAL', actual='approved values missing')
    coverage = [dict(tc_id=f'TC_Basic_Install_0{n}', level='SKIP', category='사람 전용(SKIP)',
                     gap='synthetic human reason') for n in (3, 4)]
    coverage.append(dict(tc_id='TC_WindowsUpdate_01', level='SKIP', checklist='windows_update'))
    paths = write_reports([result], str(tmp_path), 'current-scope', meta={'coverage': coverage})
    text = Path(paths['html']).read_text(encoding='utf-8')
    assert re.search(r"class='n SKIP'>2</div>\s*<div class='k'>SKIP — 사람 전용", text)
    assert 'MANUAL — 수동 전용' not in text
    assert 'synthetic human reason' in text
    assert json.loads(Path(paths['json']).read_text(encoding='utf-8'))['results'][0]['verdict'] == 'MANUAL'


def test_legacy_manual_scope_stays_visible_as_legacy(tmp_path):
    from core.result import write_reports
    paths = write_reports([], str(tmp_path), 'legacy-scope', meta={'coverage': [
        dict(tc_id='TC_Basic_Install_03', level='MANUAL', category='legacy')]})
    text = Path(paths['html']).read_text(encoding='utf-8')
    assert 'MANUAL — 수동 전용(이전 등급)' in text
