"""지속 저장 실패가 실제 체인의 완료 결과를 유실시키는 회귀를 막는다."""
from unittest.mock import patch

from core import wu_chain
from tests.test_wu_chain import ChainResumeTests


class PartialReportTests(ChainResumeTests):
    def test_completed_stage_survives_persistent_checkpoint_failure(self):
        original = wu_chain.Checkpoint.complete

        def fail_after_result(checkpoint, stage_id, results, **kwargs):
            if stage_id == 'TC_A':
                raise PermissionError('synthetic persistence failure')
            return original(checkpoint, stage_id, results, **kwargs)

        with patch.object(wu_chain.Checkpoint, 'complete', fail_after_result):
            code = self.run_chain(False)
        self.assertNotEqual(code, 0)
        self.assertNotIn('TC_B', self.calls)
        self.assertFalse(self.finished[-1]['chain_completed'])
        meta = self.finished[-1]['extra_meta']
        self.assertEqual(meta['checkpoint_save_failed']['type'], 'PermissionError')
        self.assertIn('TC_A', [r['tc_id'] for r in meta['partial_source_results']])

    def test_final_marker_failure_does_not_publish_complete_report(self):
        with patch.object(wu_chain.Checkpoint, 'finish', side_effect=PermissionError):
            code = self.run_chain(False)
        self.assertNotEqual(code, 0)
        self.assertFalse(self.finished[-1]['chain_completed'])
