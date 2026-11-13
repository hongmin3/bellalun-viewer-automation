# -*- coding: utf-8 -*-
"""전경 회복은 자기 창 활성화만 수행하고, 안전한 입력 전 확인을 유지한다.

run672의 외부 알림 가림은 제한된 시간 안에서 재관측한다. 이전 외부 창 Z-order
변경·합성키 성공 시험은 현재 허용 범위와 충돌하여 금지 동작 검증으로 교체했다.
로그인의 ForegroundError 재시도 계약은 유지한다.
"""
import unittest
from unittest import mock

from core import flows, ui as ui_mod


class _FrontUi:
    """`bring_to_front` 가 쓰는 최소 인터페이스.

    `wins_on` 에 적힌 전환 함수가 불린 뒤에만 Viewer 가 최전면이 된다.
    호출 횟수가 아니라 **어떤 수단이 통했는지**로 상태를 바꾼다.
    """

    pid = 4321

    def __init__(self, calls, wins_on=None, blocking=None, start_front=False):
        self._calls = calls
        self._wins_on = wins_on
        self._blocking = blocking
        self._start_front = start_front

    def _front(self):
        if self._start_front:
            return True
        if self._wins_on == "nudge":
            # 가상키 직후의 force_foreground 가 통한다.
            seen = self._calls
            return ("nudge_foreground_input" in seen
                    and seen[-1] == "force_foreground")
        return self._wins_on in self._calls

    def main_window(self):
        return mock.Mock(hwnd=111)

    def is_foreground(self):
        return self._front()

    def blocking_window(self):
        return None if self._front() else self._blocking


class BringToFrontEscalationTests(unittest.TestCase):
    """외부 창 이동/합성키 정책은 현재 사용자 금지 조건으로 교체한다."""
    CONSOLE = {"title": "새 알림", "pid": 1128, "hwnd": 5}

    def setUp(self):
        self.calls = []
        self.clock = 0.0
        def sleep(seconds):
            self.clock += seconds
        for name in ("force_foreground", "push_window_back",
                     "switch_to_window", "nudge_foreground_input"):
            patcher = mock.patch.object(ui_mod, name,
                side_effect=lambda *a, _n=name: self.calls.append(_n) or True)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (("sleep", sleep), ("monotonic", lambda: self.clock)):
            patcher = mock.patch.object(ui_mod.time, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (("_pid_of", lambda h: 4321),):
            patcher = mock.patch.object(ui_mod, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(ui_mod.u32, "IsWindow", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_uses_only_own_window_activation(self):
        ui = _FrontUi(self.calls, wins_on="switch_to_window", blocking=self.CONSOLE)
        out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertTrue(out["ok"])
        self.assertNotIn("push_window_back", self.calls)
        self.assertNotIn("nudge_foreground_input", self.calls)

    def test_transient_blocker_is_retried_with_one_deadline(self):
        ui = _FrontUi(self.calls, blocking=self.CONSOLE)
        ui.is_foreground = lambda: self.clock >= 6
        out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertTrue(out["ok"])
        self.assertLessEqual(self.clock, 10)

    def test_persistent_blocker_stops_without_touching_foreign_window(self):
        ui = _FrontUi(self.calls, blocking=self.CONSOLE)
        out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertFalse(out["ok"])
        self.assertEqual(self.CONSOLE, out["blocking"])
        self.assertGreaterEqual(self.clock, 9.75)
        self.assertLessEqual(self.clock, 10)
        self.assertNotIn("push_window_back", self.calls)
        self.assertNotIn("nudge_foreground_input", self.calls)

    def test_lost_target_stops_without_activation(self):
        ui = _FrontUi(self.calls, blocking=self.CONSOLE)
        with mock.patch.object(ui_mod.u32, "IsWindow", return_value=False):
            out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertFalse(out["ok"])
        self.assertEqual([], self.calls)

    def test_reused_target_handle_from_other_process_is_rejected(self):
        ui = _FrontUi(self.calls, blocking=self.CONSOLE)
        with mock.patch.object(ui_mod, "_pid_of", return_value=999):
            out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertFalse(out["ok"])
        self.assertEqual("target_lost", out["reason"])
        self.assertEqual([], self.calls)

    def test_changing_blocker_does_not_restart_or_extend_deadline(self):
        ui = _FrontUi(self.calls, blocking=self.CONSOLE)
        ui.blocking_window = lambda: {"pid": 999, "hwnd": int(self.clock) + 50}
        out = ui_mod.ViewerUi.bring_to_front(ui, timeout=30)
        self.assertFalse(out["ok"])
        self.assertEqual(10, self.clock)
        self.assertEqual(60, out["blocking"]["hwnd"])

    def test_main_window_read_time_counts_against_activation_retry_budget(self):
        ui = _FrontUi(self.calls, blocking=self.CONSOLE)
        def main_window():
            self.clock += 11
            return mock.Mock(hwnd=111)
        ui.main_window = main_window
        out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertFalse(out["ok"])
        self.assertEqual([], self.calls)
        self.assertEqual(11, out["elapsed_seconds"])

    def test_already_in_front_touches_nothing(self):
        ui = _FrontUi(self.calls, start_front=True)
        self.assertTrue(ui_mod.ViewerUi.bring_to_front(ui)["ok"])
        self.assertEqual([], self.calls)

    def test_require_front_raises_foreground_error(self):
        fake = mock.Mock()
        fake.is_foreground.return_value = False
        fake.blocking_window.return_value = self.CONSOLE
        fake.bring_to_front.return_value = {"ok": False, "blocking": self.CONSOLE}
        with self.assertRaises(ui_mod.ForegroundError):
            ui_mod.ViewerUi.require_front(fake)


class PointerSafetyTests(unittest.TestCase):
    def test_safe_hit_does_not_activate_other_viewer_window(self):
        fake = mock.Mock(pid=42)
        with mock.patch.object(ui_mod, "_window_at_point", return_value=9), \
             mock.patch.object(ui_mod, "_pid_of", return_value=42):
            self.assertTrue(ui_mod.ViewerUi.require_front_for_pointer(fake, point=(10, 10)))
        fake.bring_to_front.assert_not_called()

    def test_foreground_viewer_does_not_allow_foreign_window_at_click_point(self):
        fake = mock.Mock(pid=42)
        fake.is_foreground.return_value = True
        fake.blocking_window.return_value = {"hwnd": 9, "pid": 99}
        fake.bring_to_front.return_value = {"ok": False, "blocking": {"hwnd": 9}}
        with mock.patch.object(ui_mod, "_window_at_point", return_value=9), \
             mock.patch.object(ui_mod, "_pid_of", return_value=99):
            with self.assertRaises(ui_mod.ForegroundError):
                ui_mod.ViewerUi.require_front_for_pointer(fake, point=(10, 10))

    def test_force_does_not_change_global_foreground_settings(self):
        with mock.patch.object(ui_mod.u32, "GetForegroundWindow", return_value=1), \
             mock.patch.object(ui_mod.u32, "GetWindowThreadProcessId", return_value=2), \
             mock.patch.object(ui_mod.k32, "GetCurrentThreadId", return_value=3), \
             mock.patch.object(ui_mod.u32, "AttachThreadInput"), \
             mock.patch.object(ui_mod.u32, "IsIconic", return_value=False), \
             mock.patch.object(ui_mod.u32, "BringWindowToTop"), \
             mock.patch.object(ui_mod.u32, "SetForegroundWindow"), \
             mock.patch.object(ui_mod, "_set_foreground_lock_timeout") as settings:
            ui_mod.force_foreground(11)
        settings.assert_not_called()


class _LoginUi:
    """`cold_start` 의 로그인 분기를 지나가는 최소 가짜 Viewer."""

    pid = 1234

    def __init__(self, login_effects):
        self._effects = list(login_effects)
        self.logged_in = False
        self.login_calls = 0

    def at_login_screen(self):
        return not self.logged_in

    def main_window(self):
        return mock.Mock(rect=(0, 0, 1920, 1080), hwnd=9)

    def bring_to_front(self):
        return {"ok": True, "blocking": None, "attempts": 0}

    def foreground_window(self):
        return None

    def login(self, user_id, password):
        self.login_calls += 1
        effect = self._effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        self.logged_in = bool(effect)
        return bool(effect)

    def by_id(self, _ctrl):
        return []


class _Db:
    def ping(self):
        return True


class ColdStartLoginFocusRetryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {"viewer": {"force_restart": False, "login_attempts": 3,
                               "login": {"id": "service", "password": "pw"}},
                    "evidence_ui_dir": "Evidence/ui", "xipl": {}}
        for target, value in (
                ("core.display.screen_size", lambda: (1920, 1080)),
                ("core.watchdog.wait_until", lambda *a, **k: True),
                ("core.flows.select_login_id", lambda *a, **k: {"already": True}),
                ("core.flows.time.sleep", lambda *_: None)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, ui):
        with mock.patch.object(flows, "ViewerUi", lambda *a, **k: ui), \
                mock.patch("core.watchdog.DialogGuard") as guard:
            guard.return_value.sweep.return_value = []
            return flows.cold_start(self.cfg, _Db(), force_restart=False)

    def test_focus_loss_during_password_is_retried_not_fatal(self):
        ui = _LoginUi([ui_mod.ForegroundError("가린 창: THIEF_CONSOLE"), True])
        _ui, log = self._run(ui)
        self.assertEqual(2, ui.login_calls)
        self.assertTrue(any("THIEF_CONSOLE" in line for line in log),
                        "어떤 창이 가렸는지 기동 로그에 남긴다")
        self.assertIn("로그인 완료", log)

    def test_persistent_focus_loss_still_aborts_with_the_blocker_named(self):
        err = ui_mod.ForegroundError("가린 창: THIEF_CONSOLE")
        ui = _LoginUi([err, err, err])
        with self.assertRaises(flows.FlowError) as caught:
            self._run(ui)
        self.assertEqual(3, ui.login_calls)
        self.assertIn("THIEF_CONSOLE", str(caught.exception))

    def test_other_login_errors_are_not_swallowed(self):
        """잘못된 계정 선택 같은 다른 예외는 재시도로 덮지 않는다."""
        ui = _LoginUi([RuntimeError("로그인 ID가 'admin'로 선택되어 있습니다.")])
        with self.assertRaises(RuntimeError) as caught:
            self._run(ui)
        self.assertNotIsInstance(caught.exception, ui_mod.ForegroundError)
        self.assertEqual(1, ui.login_calls)


class EnsureReadyFocusRetryTests(unittest.TestCase):
    """XIPL 경로가 쓰는 `ViewerUi.ensure_ready` 도 같은 실패를 재시도한다."""

    def test_focus_loss_is_retried(self):
        fake = mock.Mock()
        fake.pid = 1
        fake.login.side_effect = [ui_mod.ForegroundError("가린 창: THIEF"), True]
        fake.sweep_dialogs.return_value = []
        fake.wait_screen_ready.return_value = "loaded"
        with mock.patch.object(ui_mod.time, "sleep", lambda *_: None):
            notes = ui_mod.ViewerUi.ensure_ready(fake, None, "service", "pw")
        self.assertEqual(2, fake.login.call_count)
        self.assertTrue(any("THIEF" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
