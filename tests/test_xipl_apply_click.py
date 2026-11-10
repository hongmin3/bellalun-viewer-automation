"""REQ-REGRESSION-001: XIPL_03 3D Apply 클릭이 Viewer에 받아들여졌는지 확인한다(UI 없음)."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import flows, viewer_processing as vp
from tests import xipl_flows as flow

ACCEPTED = ("[2026/11/11 00:33:28.181] [Info] [SYSTEM] "
            "[Terminate PostReconThread normally closed] "
            "[CDlgPostReconstruction::TerminatePostReconThread]\n")


class XiplApplyClickTests(unittest.TestCase):
    def run_click(self, logs, closed_after=None):
        """logs[i]는 i번째 Apply 클릭 뒤 새로 쌓인 Viewer 로그다."""
        clicks = []
        apply = SimpleNamespace(visible=True, enabled=True)

        def by_id(_):
            if closed_after is not None and len(clicks) >= closed_after:
                return []
            return [apply]

        ui = SimpleNamespace(by_id=by_id, click=lambda control, settle=0: clicks.append(control))

        def since(mark):
            return logs[min(len(clicks), len(logs)) - 1] if clicks else ""

        ctx = SimpleNamespace(cfg={"data_dir": "offline"})
        with patch.object(flow, "_viewer_log_mark", return_value=(Path("log"), 0)), \
                patch.object(flow, "_viewer_log_since", side_effect=since), \
                patch.object(flow, "_log_lines_from", side_effect=lambda text, _: text), \
                patch.object(flow.time, "sleep"):
            try:
                return flow._click_3d_apply_confirmed(ctx, ui, timeout=1), clicks
            except flows.FlowError as exc:
                return exc, clicks

    def test_thread_exit_after_click_is_acceptance(self):
        result, clicks = self.run_click([ACCEPTED])
        self.assertEqual(1, len(clicks))
        self.assertEqual(1, result["attempts"])

    def test_closed_window_is_acceptance(self):
        result, clicks = self.run_click([""], closed_after=1)
        self.assertEqual(1, len(clicks))
        self.assertTrue(result["window_closed"])

    def test_ignored_click_is_retried(self):
        # 1.0.9 run111 회귀·1.0.10 run112: Preview 영상이 막 그려지던 때(eNoti:5 0.6초 뒤)
        # 누른 Apply는 로그도 창 변화도 없이 무시됐다.
        result, clicks = self.run_click(["", ACCEPTED])
        self.assertEqual(2, len(clicks))
        self.assertEqual(2, result["attempts"])

    def test_never_accepted_click_stops_without_guessing(self):
        result, clicks = self.run_click([""])
        self.assertIsInstance(result, flows.FlowError)
        self.assertEqual(3, len(clicks))


if __name__ == "__main__":
    unittest.main()
