# -*- coding: utf-8 -*-
"""늦게 열린 Export Manager 창이 다음 TC의 로그인을 막지 않게 한다.

2026-10-20 후보10 실시간 WU 실측: WF09가 Export 버튼을 누른 뒤 20초 안에 창이 열리지
않아 FAIL했고, 창은 그 뒤(20:15:41)에 열렸다. 닫히지 않은 그 창이 최전면을 쥐어
WU_10·WU_11의 Viewer 재기동 로그인이 `최전면 창이 Viewer가 아닙니다: 'Export Manager'`로
연달아 실패했다.
"""
import unittest
from unittest import mock

from core import export_manager as em
from core import flows


class AttachTimeoutTests(unittest.TestCase):
    def test_default_wait_covers_measured_late_open(self):
        import inspect
        default = inspect.signature(em.attach).parameters["timeout"].default
        self.assertGreaterEqual(default, 60)


class LeftoverExportManagerTests(unittest.TestCase):
    def test_leftover_is_killed_and_reported(self):
        killed, said = [], []
        with mock.patch.object(flows, "_find_process_pid", return_value=8684), \
                mock.patch.object(flows, "_kill_viewer", side_effect=killed.append):
            flows.close_leftover_export_manager(said.append)
        self.assertEqual([8684], killed)
        self.assertTrue(any("Export Manager" in line and "8684" in line for line in said))

    def test_nothing_running_does_nothing(self):
        with mock.patch.object(flows, "_find_process_pid", return_value=None), \
                mock.patch.object(flows, "_kill_viewer") as kill:
            flows.close_leftover_export_manager(lambda _: None)
        kill.assert_not_called()

    def test_cold_start_clears_leftover_before_launching_viewer(self):
        order = []
        cfg = {"viewer": {"exe": r"C:\B\VIEWER.exe", "launch_wait": 0}}

        class FakeUi:
            pid = None

            def launch(self, exe, wait=0):
                order.append("launch")
                raise flows.FlowError("stop here")

        with mock.patch.object(flows, "ViewerUi", return_value=FakeUi()), \
                mock.patch.object(flows, "close_leftover_export_manager",
                                  side_effect=lambda say: order.append("clear")):
            with self.assertRaises(flows.FlowError):
                flows.cold_start(cfg, db=mock.Mock(), force_restart=False)
        self.assertEqual(["clear", "launch"], order)


if __name__ == "__main__":
    unittest.main()
