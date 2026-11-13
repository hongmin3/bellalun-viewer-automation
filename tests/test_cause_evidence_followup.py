"""제품 로그의 명시 관찰을 연결하되 판정·원인은 추정하지 않는다."""
from datetime import datetime
from types import SimpleNamespace

from core import failure_evidence as fe


def test_current_sql_timeout_and_disk_warning_are_separate_linked_observations(tmp_path):
    path = tmp_path / 'viewer.log'
    path.write_text(
        '[2026/11/13 11:58:00] System.Data.SqlClient.SqlException: Timeout expired.\n'
        '[2026/11/13 12:00:01] System.Data.SqlClient.SqlException: Execution Timeout Expired.\n'
        ' at ViewPositionPreset.Select()\n'
        '[2026/11/13 12:00:02] [Warning] The disk space is less than 12GB.\n', encoding='utf-8')
    window = fe.extract_log_window(path, datetime(2026, 11, 13, 12), before=5, after=5)
    causes = fe.log_cause_evidence(window, tc_id='TC_SAMPLE', step=3)
    assert [c['category'] for c in causes] == ['sql-timeout', 'disk-space-warning']
    assert all(c['source'] == 'viewer-log' and c['attribution'] == 'undetermined' for c in causes)
    assert all(c['tc_id'] == 'TC_SAMPLE' and c['step'] == 3 for c in causes)
    assert causes[0]['evidence']['path'] == str(path)
    assert 'ViewPositionPreset.Select' in causes[0]['evidence']['text']
    assert '11:58:00' not in str(causes)
    assert '12GB' in causes[1]['evidence']['text']


def test_unscoped_log_or_generic_timeout_does_not_become_product_cause(tmp_path):
    assert fe.log_cause_evidence({'lines': ['SQL timeout expired']}, tc_id='TC') == []
    path = tmp_path / 'viewer.log'
    path.write_text('[2026/11/13 12:00:01] Automation wait timeout expired\n'
                    '[2026/11/13 12:00:02] SQL Server query completed\n', encoding='utf-8')
    window = fe.extract_log_window(path, datetime(2026, 11, 13, 12), before=5, after=5)
    assert fe.log_cause_evidence(window, tc_id='TC') == []


def test_linked_causes_survive_json_and_html_without_changing_checks(tmp_path):
    from core.result import TCResult, PASS, _render_html
    result = TCResult('TC_SAMPLE', 'sample')
    result.add(1, 'existing check', PASS)
    cause = {'tc_id': 'TC_SAMPLE', 'step': 1, 'source': 'viewer-log', 'category': 'sql-timeout',
             'attribution': 'undetermined', 'evidence': {'path': 'local.log', 'line_start': 1,
                'line_end': 2, 'text': '<SQL timeout>'}}
    fe.link_cause_evidence(result, [cause])
    fe.link_cause_evidence(result, [cause])
    assert result.as_dict()['cause_evidence'] == [cause]
    assert result.verdict == 'PASS' and len(result.checks) == 1
    html = _render_html([result], {})
    assert 'sql-timeout' in html and '&lt;SQL timeout&gt;' in html
    assert '<SQL timeout>' not in html


def test_failure_bundle_links_current_log_causes_to_given_result(tmp_path):
    path = tmp_path / 'viewer.log'
    path.write_text('[2026/11/13 12:00:01] SqlException: Timeout expired\n', encoding='utf-8')
    result = SimpleNamespace(tc_id='TC_SAMPLE')
    evidence, payload = fe.collect_failure_evidence(
        tmp_path / 'evidence', tc_id='TC_SAMPLE', reason='synthetic', result=result,
        event_time=datetime(2026, 11, 13, 12), log_path=path, include_crash=False,
        readers={'handles': lambda pid: {}, 'memory': lambda: {},
                 'foreground': lambda: {'exe': 'VIEWER.exe'}})
    assert evidence and payload['cause_evidence'][0]['category'] == 'sql-timeout'
    assert result.cause_evidence == payload['cause_evidence']
