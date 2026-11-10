"""REQ-REGRESSION-001: XIPL_04가 고른 Step이 실제로 선택됐는지 Viewer 로그로 확인한다(UI 없음)."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import flows, viewer_processing as vp
from tests import xipl_flows as flow


def selected(step_id):
    return (f"[2026/11/10 22:53:36.776] [Info] [UI] "
            f"[Select Image. (Study Key: 52, Step ID: {step_id})] "
            f"[CFrameImageView::OnNotifySelectImage]\n")


class XiplStepSelectionTests(unittest.TestCase):
    def run_select(self, logs):
        """logs[i]는 i번째 선택 시도 뒤 새로 쌓인 Viewer 로그다."""
        attempts = []

        def select(ui, index):
            attempts.append(index)

        def since(mark):
            return logs[min(len(attempts), len(logs)) - 1] if attempts else ""

        ctx = SimpleNamespace(cfg={"data_dir": "offline"})
        with patch.object(vp, "select_2d", side_effect=select), \
                patch.object(flow, "_viewer_log_mark", return_value=(Path("log"), 0)), \
                patch.object(flow, "_viewer_log_since", side_effect=since), \
                patch.object(flow.time, "sleep"):
            try:
                return flow._select_2d_confirmed(ctx, object(), 5, timeout=1), attempts
            except flows.FlowError as exc:
                return exc, attempts

    def test_selection_log_for_the_requested_step_is_confirmation(self):
        # Step 5(1부터) = 제품 로그 Step ID 4.
        result, attempts = self.run_select([selected(4)])
        self.assertEqual([5], attempts)
        self.assertEqual({"step": 5, "step_id": 4, "attempts": 1}, result)

    def test_swallowed_click_is_retried_before_reading_parameter(self):
        # 1.0.8 run110: A 영상 선택 클릭이 로그 없이 무시돼 직전 B 영상을 읽었다.
        result, attempts = self.run_select(["", selected(4)])
        self.assertEqual([5, 5], attempts)
        self.assertEqual(2, result["attempts"])

    def test_other_step_selection_is_not_confirmation(self):
        result, attempts = self.run_select([selected(5)])
        self.assertIsInstance(result, flows.FlowError)
        self.assertEqual(3, len(attempts))
        self.assertIn("Step ID: 4", str(result))


if __name__ == "__main__":
    unittest.main()
