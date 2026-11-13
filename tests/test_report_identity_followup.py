"""Validates: REQ-FOLLOWUP-001. 결과 신원과 표시 전용 보고서 경계."""
import json
from pathlib import Path
import tempfile
import unittest

from core import automation_health, wu_chain
from core.result import TCResult, write_reports


class ReportIdentityFollowupTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / 'work/followup-identity'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_reused_results_survive_json_and_html_reports(self):
        original = TCResult('TC_A', '합성 단계')
        original.add(1, '확인', 'PASS')
        reused = wu_chain.result_from_dict(original.as_dict())
        paths = write_reports([reused], str(self.folder), 'reused')
        data = json.loads(Path(paths['json']).read_text(encoding='utf-8'))
        self.assertTrue(data['results'][0].get('reused_from_checkpoint'))
        self.assertIn('저장점 재사용', Path(paths['html']).read_text(encoding='utf-8'))

    def test_html_exposes_execution_identity_and_restore_status(self):
        result = TCResult('TC_A', '합성 단계')
        result.add(1, '확인', 'PASS')
        meta = {'run_id': 'run-example', 'automation_version': 'auto-1.2',
                'source_commit': 'a' * 40, 'source_dirty': None,
                'source_identity_origin': 'git', 'plan_id': 'plan-example',
                'config_fingerprint': 'config-example',
                'viewer_identity': {'version': 'viewer-3.4', 'sha256': 'viewer-hash'},
                'restoration': {'status': 'verified', 'manifest': 'manifest-example'}}
        paths = write_reports([result], str(self.folder), 'identity', meta=meta)
        text = Path(paths['html']).read_text(encoding='utf-8')
        for value in ('run-example', 'auto-1.2', 'a' * 40, 'plan-example',
                      'config-example', 'viewer-3.4', 'verified', 'manifest-example', '확인 불가'):
            self.assertIn(value, text)

    def test_presentation_copy_and_partial_chain_are_not_completed_reports(self):
        payload = {'generated': '2026-11-13T12:00:00',
                   'results': [{'tc_id': tc_id, 'verdict': 'PASS'}
                               for tc_id in automation_health.FULL_REGRESSION_MARKERS]}
        for marker in ({'presentation_only': True}, {'report_role': 'presentation'},
                       {'chain_completed': False}):
            with self.subTest(marker=marker):
                payload['meta'] = marker
                (self.folder / 'Result_copy.json').write_text(json.dumps(payload), encoding='utf-8')
                self.assertIsNone(automation_health.latest_full_regression(str(self.folder)))
