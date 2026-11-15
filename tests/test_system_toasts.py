# -*- coding: utf-8 -*-
"""Windows 알림 배너는 닫기 버튼으로만 알림 센터로 옮긴다.

Validates: REQ-FOLLOWUP-005

run699 의 실제 배너(ShellExperienceHost `새 알림`, PriorityToastView,
동작 버튼 해제·파일 보내기·검토)를 근거로 만든 시험이다.
"""
import json
import unittest
from unittest import mock

from core import system_toasts as st
from core import ui as ui_mod

HOST = r"C:\WINDOWS\SystemApps\ShellExperienceHost_cw5n1h2txyewy\ShellExperienceHost.exe"
RUN699 = {"hwnd": 197626, "cls": "Windows.UI.Core.CoreWindow", "title": "새 알림",
          "visible": True, "rect": (1524, 805, 1920, 1080), "pid": 11956, "path": HOST}


class ToastIdentityTests(unittest.TestCase):
    def test_run699_banner_is_toast(self):
        self.assertTrue(st.is_toast_info(RUN699))

    def test_collapsed_banner_window_is_not_cover(self):
        self.assertFalse(st.is_toast_info(dict(RUN699, rect=(1524, 1080, 1920, 1080))))

    def test_other_process_or_title_is_not_toast(self):
        self.assertFalse(st.is_toast_info(dict(RUN699, path=r"C:\Tools\ShellExperienceHost.exe")))
        self.assertFalse(st.is_toast_info(dict(RUN699, title="설정")))
        self.assertFalse(st.is_toast_info(dict(RUN699, cls="#32770")))
        self.assertFalse(st.is_toast_info(dict(RUN699, visible=False)))
        self.assertFalse(st.is_toast_info(None))


class DismissScriptTests(unittest.TestCase):
    def test_script_presses_only_dismiss_button(self):
        script = st._DISMISS_SCRIPT
        self.assertIn("'DismissButton'", script)
        self.assertNotIn("VerbButton", script)
        self.assertNotIn("SettingsButton", script)
        self.assertIn("ShellExperienceHost", script)

    def _dismiss(self, runner, visible):
        clock = [0.0]
        with mock.patch.object(st, "is_toast_window", side_effect=visible), \
                mock.patch.object(st.time, "monotonic", lambda: clock[0]), \
                mock.patch.object(st.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s)):
            logs = []
            return st.dismiss(197626, log=logs.append, runner=runner), logs

    def test_dismiss_reports_sender_only_and_clears(self):
        calls = []
        def runner(script, timeout):
            calls.append(script)
            return 0, json.dumps({"views": 1, "senders": "Windows 보안", "failed": 0})
        result, logs = self._dismiss(runner, [True, False])
        self.assertEqual("dismissed", result["status"])
        self.assertEqual(["Windows 보안"], result["senders"])
        self.assertTrue(result["cleared"])
        self.assertIn("[IntPtr]197626", calls[0])
        self.assertNotIn("파일 검토", logs[0])

    def test_runner_failure_is_error_without_raising(self):
        def runner(script, timeout):
            raise TimeoutError()
        result, logs = self._dismiss(runner, [True] + [True] * 50)
        self.assertEqual("error", result["status"])
        self.assertFalse(result["cleared"])
        self.assertIn("남아 있음", logs[0])

    def test_missing_dismiss_button_is_error(self):
        result, _ = self._dismiss(lambda s, t: (0, '{"views":1,"senders":[],"failed":1}'),
                                  [True] + [True] * 50)
        self.assertEqual("error", result["status"])

    def test_gone_window_is_not_touched(self):
        runner = mock.Mock()
        result, _ = self._dismiss(runner, [False])
        self.assertEqual("none", result["status"])
        runner.assert_not_called()


class GuardTests(unittest.TestCase):
    def test_sweep_handles_each_banner_once_per_two_seconds(self):
        handled, clock = [], [0.0]
        guard = st.toasts_dismissed(scan=lambda: [7], handle=handled.append)
        with mock.patch.object(st.time, "monotonic", lambda: clock[0]):
            guard.sweep()
            clock[0] = 1.0
            guard.sweep()
            clock[0] = 2.5
            guard.sweep()
        self.assertEqual([7, 7], handled)

    def test_disabled_guard_does_not_scan(self):
        scan = mock.Mock(return_value=[])
        with mock.patch.dict(st.os.environ, {st.DISABLE_ENV: "1"}):
            with st.toasts_dismissed(scan=scan):
                pass
        scan.assert_not_called()

    def test_guard_sweeps_at_start_and_stops(self):
        scan = mock.Mock(return_value=[])
        with mock.patch.dict(st.os.environ, {st.DISABLE_ENV: "0"}):
            with st.toasts_dismissed(interval=0.01, scan=scan) as guard:
                pass
        self.assertGreaterEqual(scan.call_count, 1)
        self.assertFalse(guard._thread.is_alive())


class BringToFrontToastTests(unittest.TestCase):
    """가린 창이 알림 배너면 배너만 알림 센터로 옮기고 다시 본다."""

    def setUp(self):
        self.clock = 0.0
        self.calls = []
        for name in ("force_foreground", "switch_to_window", "push_window_back",
                     "nudge_foreground_input"):
            p = mock.patch.object(ui_mod, name, side_effect=lambda *a, _n=name: self.calls.append(_n))
            p.start()
            self.addCleanup(p.stop)
        for name, value in (("sleep", lambda s: setattr(self, "clock", self.clock + s)),
                            ("monotonic", lambda: self.clock)):
            p = mock.patch.object(ui_mod.time, name, value)
            p.start()
            self.addCleanup(p.stop)
        for target, value in ((ui_mod, "_pid_of"),):
            p = mock.patch.object(target, value, lambda h: 4321 if h in (111, 112) else 11956)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(ui_mod.u32, "IsWindow", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def _ui(self):
        ui = mock.Mock(pid=4321)
        ui.main_window.return_value = mock.Mock(hwnd=111)
        ui.is_foreground.return_value = False
        ui.blocking_window.return_value = None
        return ui

    def test_pointer_cover_toast_is_dismissed_then_click_proceeds(self):
        covered = [True]
        def at_point(point):
            return 197626 if covered[0] else 112
        def dismiss(hwnd, log=None):
            covered[0] = False
            self.calls.append(("dismiss", hwnd))
            return {"status": "dismissed"}
        with mock.patch.object(ui_mod, "_window_at_point", at_point), \
                mock.patch.object(ui_mod.system_toasts, "is_toast_window", lambda h: h == 197626), \
                mock.patch.object(ui_mod.system_toasts, "dismiss", dismiss):
            out = ui_mod.ViewerUi.bring_to_front(self._ui(), point=(1700, 950))
        self.assertTrue(out["ok"])
        self.assertEqual([("dismiss", 197626)], self.calls)

    def test_persistent_toast_is_tried_twice_then_reported(self):
        dismiss = mock.Mock(return_value={"status": "error"})
        with mock.patch.object(ui_mod, "_window_at_point", lambda p: 197626), \
                mock.patch.object(ui_mod.system_toasts, "is_toast_window", lambda h: True), \
                mock.patch.object(ui_mod.system_toasts, "dismiss", dismiss):
            out = ui_mod.ViewerUi.bring_to_front(self._ui(), point=(1700, 950))
        self.assertFalse(out["ok"])
        self.assertEqual(2, dismiss.call_count)
        self.assertNotIn("push_window_back", self.calls)

    def test_non_toast_cover_is_never_dismissed(self):
        dismiss = mock.Mock()
        with mock.patch.object(ui_mod, "_window_at_point", lambda p: 999), \
                mock.patch.object(ui_mod.system_toasts, "is_toast_window", lambda h: False), \
                mock.patch.object(ui_mod.system_toasts, "dismiss", dismiss):
            out = ui_mod.ViewerUi.bring_to_front(self._ui(), point=(10, 10))
        self.assertFalse(out["ok"])
        dismiss.assert_not_called()


if __name__ == "__main__":
    unittest.main()
