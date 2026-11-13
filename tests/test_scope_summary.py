"""범위 원본에서 기본기능·WU·준비를 구분해 문서를 생성한다."""
import json

import pytest


def rows():
    return [
        {'tc_id': 'TC_BASIC', 'title': 'basic', 'level': 'FULL',
         'coverage': {'category': '자동', 'gap': '승인 기준 필요', 'unblock': '기준 등록'}},
        {'tc_id': 'PREPARATION', 'title': 'prepare', 'level': 'SUPPORT'},
        {'tc_id': 'TC_WU', 'title': 'wu', 'level': 'SKIP', 'checklist': 'windows_update',
         'coverage': {'category': '사람 전용', 'gap': '시험 PC 필요', 'unblock': 'PC 확보'}},
    ]


def test_scope_document_keeps_support_out_of_checklist_count_and_real_constraints():
    from tools.scope_summary import render_scope
    text = render_scope(rows())
    assert '| 기본기능 | 1 | 1 | 0 | 0 | 0 | 1 |' in text
    assert '| Windows Update | 1 | 0 | 0 | 0 | 1 | 0 |' in text
    assert '승인 기준 필요' in text and '기준 등록' in text
    assert '시험 PC 필요' in text and 'PC 확보' in text
    assert '실행 PASS 수치' in text


def test_scope_cli_check_detects_stale_document_without_overwriting(tmp_path):
    from tools.scope_summary import main
    source, output = tmp_path / 'scope.json', tmp_path / 'scope.md'
    source.write_text(json.dumps(rows()), encoding='utf-8')
    argv = ['--source', str(source), '--output', str(output)]
    assert main(argv) == 0
    original = output.read_bytes()
    assert main(argv + ['--check']) == 0
    source.write_text(json.dumps(rows()[:-1]), encoding='utf-8')
    assert main(argv + ['--check']) == 1
    assert output.read_bytes() == original
    assert main(argv) == 0
    assert output.read_bytes() != original


@pytest.mark.parametrize('change', ['duplicate', 'unknown-level'])
def test_scope_rejects_ambiguous_source(change):
    from tools.scope_summary import render_scope
    data = rows()
    if change == 'duplicate':
        data.append(data[0])
    else:
        data[0]['level'] = 'UNKNOWN'
    with pytest.raises(ValueError):
        render_scope(data)
