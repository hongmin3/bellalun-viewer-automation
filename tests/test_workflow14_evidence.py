"""WF14 실패 진단 보존. 합성 스냅샷만 사용하며 UI/DB를 호출하지 않는다."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.result import StepFailed, TCResult
from tests import workflow14


class Workflow14EvidenceTests(unittest.TestCase):
    def test_complete_snapshot_and_diff_artifacts_survive_stop_on_fail(self):
        check = getattr(workflow14, '_assert_config_identical', None)
        self.assertIsNotNone(check, 'WF14 must save DB evidence before asserting equality')
        before = {'_taken': 'synthetic-before', '_sections': {
            'dicom_common': [{'Key': 1, 'LocalAET': 'EXPORTED'}],
            'tool_button': [{'Key': 2, 'Name': 'Before'}]}}
        after = {'_taken': 'synthetic-after', '_sections': {
            'dicom_common': [{'Key': 1, 'LocalAET': 'AFTER'}],
            'tool_button': [{'Key': 2, 'Name': 'After'}]}}
        result = TCResult('TC_Basic_WorkFlow_14', 'synthetic WF14')
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(TCResult, 'stop_on_fail', True), self.assertRaises(StepFailed):
                check(result, before, after, folder, 7)
            root = Path(folder)
            self.assertEqual(json.loads((root/'db_before_export_snapshot.json').read_text(encoding='utf-8')), before)
            self.assertEqual(json.loads((root/'db_after_import_snapshot.json').read_text(encoding='utf-8')), after)
            details = json.loads((root/'db_config_diff.json').read_text(encoding='utf-8'))
            self.assertEqual(set(details['sections']), {'dicom_common', 'tool_button'})
            self.assertEqual(details['sections']['dicom_common']['changed'][0]['fields']['LocalAET'],
                             {'pre': 'EXPORTED', 'post': 'AFTER'})
            self.assertEqual(details['sections']['tool_button']['changed'][0]['fields']['Name'],
                             {'pre': 'Before', 'post': 'After'})
            self.assertEqual({Path(path).name for path in result.evidence},
                             {'db_before_export_snapshot.json', 'db_after_import_snapshot.json', 'db_config_diff.json'})
        self.assertEqual(result.checks[0].status, 'FAIL')
        self.assertIn('db_config_diff.json', result.checks[0].note)


class Workflow14HandleEvidenceTests(unittest.TestCase):
    """REQ-WU-006: WF14 Setting 순회도 페이지별 GDI/USER 핸들을 남긴다(판정에는 쓰지 않음)."""

    def test_sweep_handle_evidence_summarises_both_passes(self):
        helper = getattr(workflow14, '_sweep_handle_evidence', None)
        self.assertIsNotNone(helper, 'WF14 must expose per-page handle evidence')
        before = {'page_handles': {'system.general': {'gdi': 100, 'user': 200, 'error': None},
                                   'system.security': {'gdi': 150, 'user': 282, 'error': None}}}
        after = {'page_handles': {}}
        out = helper(before, after)
        self.assertEqual(out['1회차 페이지별 핸들'], before['page_handles'])
        self.assertEqual(out['1회차 핸들 증가']['gdi_delta'], 50)
        self.assertEqual(out['1회차 핸들 증가']['user_delta'], 82)
        self.assertEqual(out['2회차 페이지별 핸들'], {})
        self.assertIsNone(out['2회차 핸들 증가']['gdi_delta'])

    def test_missing_page_handles_key_is_tolerated(self):
        out = workflow14._sweep_handle_evidence({}, {'page_handles': None})
        self.assertEqual(out['1회차 페이지별 핸들'], {})
        self.assertIsNone(out['2회차 핸들 증가']['gdi_delta'])


if __name__ == '__main__':
    unittest.main()
