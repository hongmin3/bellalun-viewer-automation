"""REQ-WU-003: 원본 중단으로 빠진 Tool 단계는 사람 전용 SKIP이 아니다."""
import pytest
from tests import winupdate


@pytest.mark.parametrize('steps', [[], [1, 2, 3], [6], [7]])
def test_wu03_missing_tool_steps_fail_with_source_reason(steps):
    source = {'tc_id': 'TC_Basic_WorkFlow_02', 'verdict': 'FAIL',
              'checks': [{'step': n, 'title': 'synthetic performed', 'status': 'PASS'} for n in steps]
                       + [{'step': 0, 'title': 'TC_Basic_WorkFlow_02 실행', 'status': 'FAIL',
                           'actual': 'synthetic source abort'}]}
    result = winupdate._wu_03({source['tc_id']: source})
    assert result.verdict == 'FAIL'
    assert any('synthetic source abort' in str(c.actual) for c in result.checks)


def test_wu03_complete_tool_checks_preserve_their_verdicts():
    source = {'tc_id': 'TC_Basic_WorkFlow_02', 'verdict': 'PASS',
              'checks': [{'step': n, 'title': 'synthetic tool', 'status': 'PASS'} for n in (6, 7)]}
    assert winupdate._wu_03({source['tc_id']: source}).verdict == 'PASS'
    source['checks'][1]['status'] = 'FAIL'
    assert winupdate._wu_03({source['tc_id']: source}).verdict == 'FAIL'
