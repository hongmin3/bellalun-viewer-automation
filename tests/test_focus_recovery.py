# -*- coding: utf-8 -*-
"""콘솔 창이 최전면을 쥐었을 때 Viewer 를 되찾는 단계와 로그인 재시도를 고정한다.

2026-10-15 후보6 실시간 WU 전체에서 `DICOM_Server_Setup` 의 기동 단계가 PW 빈칸
로그인 화면에서 약 11초 만에 FAIL 했다. 2026-10-17 재현: 최전면을 쥔 콘솔 창
하나가 `force_foreground`(AttachThreadInput + 잠금 해제)와 `push_window_back` 을
모두 이겨 `bring_to_front` 가 6회 실패했고, `require_front` 의 예외가 로그인
재시도 루프 밖으로 빠져나가 전제 준비가 바로 끝났다. 같은 콘솔 창을 상대로
`SwitchToThisWindow` 는 1회에 Viewer 를 올렸다.
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
    CONSOLE = {"title": "THIEF_CONSOLE", "pid": 1128, "hwnd": 5}

    def setUp(self):
        self.calls = []
        for name in ("force_foreground", "push_window_back",
                     "switch_to_window", "nudge_foreground_input"):
            patcher = mock.patch.object(
                ui_mod, name, side_effect=lambda *a, _n=name: self.calls.append(_n) or True)
            patcher.start()
            self.addCleanup(patcher.stop)
        sleeper = mock.patch.object(ui_mod.time, "sleep", lambda *_: None)
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def test_console_that_beats_force_foreground_is_overcome_by_switch(self):
        ui = _FrontUi(self.calls, wins_on="switch_to_window", blocking=self.CONSOLE)
        out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertTrue(out["ok"])
        self.assertIn("push_window_back", self.calls, "기존 단계를 먼저 모두 쓴다")
        self.assertLess(self.calls.index("push_window_back"),
                        self.calls.index("switch_to_window"))
        self.assertNotIn("nudge_foreground_input", self.calls,
                         "키 입력 없는 전환이 통하면 가상키를 보내지 않는다")
        self.assertEqual("switch", out.get("escalation"))

    def test_nudge_is_used_only_while_another_program_is_in_front(self):
        ui = _FrontUi(self.calls, wins_on="nudge", blocking=self.CONSOLE)
        out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertTrue(out["ok"])
        self.assertLess(self.calls.index("switch_to_window"),
                        self.calls.index("nudge_foreground_input"))
        self.assertEqual("nudge", out.get("escalation"))

    def test_failure_still_reports_the_blocking_window(self):
        ui = _FrontUi(self.calls, wins_on=None, blocking=self.CONSOLE)
        out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertFalse(out["ok"])
        self.assertEqual("THIEF_CONSOLE", out["blocking"]["title"])

    def test_no_escalation_when_nothing_blocks(self):
        """셸이 최전면(가린 창 없음)이면 키가 Viewer 로 갈 수 있어 가상키를 보내지 않는다."""
        ui = _FrontUi(self.calls, wins_on=None, blocking=None)
        out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertFalse(out["ok"])
        self.assertNotIn("nudge_foreground_input", self.calls)

    def test_already_in_front_touches_nothing(self):
        ui = _FrontUi(self.calls, start_front=True)
        out = ui_mod.ViewerUi.bring_to_front(ui)
        self.assertTrue(out["ok"])
        self.assertEqual([], self.calls)

    def test_require_front_raises_foreground_error(self):
        """호출부가 최전면 실패만 골라 재시도할 수 있게 전용 예외를 쓴다."""
        fake = mock.Mock()
        fake.is_foreground.return_value = False
        fake.blocking_window.return_value = {"title": "THIEF", "pid": 1, "hwnd": 2}
        fake.bring_to_front.return_value = {
            "ok": False, "blocking": {"title": "THIEF", "pid": 1, "hwnd": 2}}
        with self.assertRaises(ui_mod.ForegroundError) as caught:
            ui_mod.ViewerUi.require_front(fake, "비밀번호 입력")
        self.assertIsInstance(caught.exception, RuntimeError)
        self.assertIn("THIEF", str(caught.exception))


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
