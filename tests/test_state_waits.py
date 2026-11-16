# -*- coding: utf-8 -*-
"""고정 대기를 상태 확인으로 바꾼 곳: 설정 페이지 이동과 Viewer 준비.

Validates: REQ-SPEEDUP-004
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import flows, setting_values
from core.ui import ViewerUi


def _control(ctrl_id, visible=True, width=120):
    return SimpleNamespace(ctrl_id=ctrl_id, visible=visible, rect=(0, 0, width, 30))


class GroupPageTests(unittest.TestCase):
    def run_open(self, rail, window=object()):
        clicks = []
        with patch.object(flows, "open_setting", return_value=True), \
                patch.object(flows, "open_setting_group",
                             side_effect=lambda ui, group, wait=2.0: clicks.append(("group", group))), \
                patch.object(flows, "_click_setting_control",
                             side_effect=lambda ui, ctrl_id, what, wait=1.5: clicks.append(("page", ctrl_id))), \
                patch.object(setting_values, "setting_window", return_value=window), \
                patch.object(setting_values, "shallow", return_value=rail):
            flows.open_group_page(object(), "dicom", "mwl", wait=1.2)
        return clicks

    def test_visible_page_skips_group_click(self):
        page = flows.SETTING_DICOM_PAGES["mwl"]
        self.assertEqual(self.run_open([_control(page)]), [("page", page)])

    def test_missing_page_clicks_group_first(self):
        page = flows.SETTING_DICOM_PAGES["mwl"]
        other = flows.SETTING_SYSTEM_PAGES[next(iter(flows.SETTING_SYSTEM_PAGES))]
        self.assertEqual(self.run_open([_control(other)]), [("group", "dicom"), ("page", page)])

    def test_hidden_or_tiny_page_is_not_trusted(self):
        page = flows.SETTING_DICOM_PAGES["mwl"]
        for rail in ([_control(page, visible=False)], [_control(page, width=10)]):
            self.assertEqual(self.run_open(rail)[0], ("group", "dicom"))

    def test_no_setting_window_falls_back_to_group_click(self):
        page = flows.SETTING_DICOM_PAGES["mwl"]
        self.assertEqual(self.run_open([_control(page)], window=None)[0], ("group", "dicom"))

    def test_page_ids_are_unique_across_groups(self):
        seen = []
        for group in flows.SETTING_GROUPS:
            seen.extend(flows.setting_pages(group).values())
        self.assertEqual(len(seen), len(set(seen)))
        self.assertFalse(set(seen) & set(flows.SETTING_GROUPS.values()))


class EnsureReadyTests(unittest.TestCase):
    def make_ui(self, *, running=True, dialog=False, at_login=False):
        ui = ViewerUi.__new__(ViewerUi)
        ui.sweeps = []
        state = {"pid": 100 if running else None, "login": at_login}
        ui._state = state
        ui.launch = lambda exe: state.update(pid=100)
        ui.dialog = lambda title=None: object() if dialog else None
        ui.sweep_dialogs = lambda rounds=4, timeout=6: ui.sweeps.append(timeout) or []
        ui.wait_screen_ready = lambda timeout=60: "loaded"
        ui.at_login_screen = lambda: state["login"]

        def login(user, password):
            state["login"] = False
            return True
        ui.login = login
        return ui

    def ensure(self, ui, exe=None):
        with patch.object(ViewerUi, "pid", property(lambda self: self._state["pid"])):
            return ui.ensure_ready(exe, "user", "pw")

    def test_running_logged_in_viewer_does_not_wait_for_popups(self):
        ui = self.make_ui()
        self.ensure(ui)
        self.assertEqual(ui.sweeps, [])

    def test_running_viewer_with_open_popup_still_closes_it(self):
        ui = self.make_ui(dialog=True)
        self.ensure(ui)
        self.assertEqual(ui.sweeps, [8, 8])

    def test_launch_waits_before_and_after_login(self):
        ui = self.make_ui(running=False, at_login=True)
        self.ensure(ui, exe="viewer.exe")
        self.assertEqual(ui.sweeps, [8, 8])

    def test_running_viewer_at_login_screen_waits_after_login(self):
        ui = self.make_ui(at_login=True)
        self.ensure(ui)
        self.assertEqual(ui.sweeps, [8])


if __name__ == "__main__":
    unittest.main()


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0.0, float(seconds))


class FakeExamineUi:
    """Close·종료 옵션·삭제 확인·Patient 화면 전환만 흉내 낸다(시각은 FakeClock)."""

    def __init__(self, clock, *, options=True, patient_after=2.0, linger=0.0,
                 delete_confirm=False, never_patient=False):
        self.clock = clock
        self.options = options
        self.patient_after = patient_after
        self.linger = linger
        self.delete_confirm = delete_confirm
        self.never_patient = never_patient
        self.popup = None          # None / "options" / "delete"
        self.popup_until = None    # 닫힌 팝업이 화면에 남아 있는 시각
        self.patient_at = None
        self.clicks = []

    def _button(self, ctrl_id, x):
        return SimpleNamespace(ctrl_id=ctrl_id, visible=True, hwnd=ctrl_id,
                               rect=(x, 500, x + 100, 540))

    def _showing(self):
        if self.popup:
            return self.popup
        if self.popup_until is not None and self.clock.now < self.popup_until:
            return "options"
        return None

    def by_id(self, ctrl_id):
        showing = self._showing()
        if ctrl_id == flows.EXAMINE["close"]:
            return [self._button(ctrl_id, 10)]
        if ctrl_id == flows.PATIENT["tab_new_patient"]:
            ready = (self.patient_at is not None and self.clock.now >= self.patient_at
                     and not showing)
            return [self._button(ctrl_id, 20)] if ready else []
        if showing == "options" and ctrl_id in (500, 501, 502):
            return [self._button(ctrl_id, {502: 100, 501: 300, 500: 500}[ctrl_id])]
        if showing == "delete" and ctrl_id in (500, 501):
            return [self._button(ctrl_id, {501: 100, 500: 300}[ctrl_id])]
        return []

    def dialog(self):
        return object() if self._showing() else None

    def click(self, control, settle=0.0):
        self.clicks.append(control.ctrl_id)
        self.clock.sleep(settle)
        if control.ctrl_id == flows.EXAMINE["close"]:
            if self.options:
                self.popup = "options"
            else:
                self._leave()
        elif self.popup == "options":
            self.popup = None
            self.popup_until = self.clock.now + self.linger
            if self.delete_confirm:
                self.popup = "delete"
            else:
                self._leave()
        elif self.popup == "delete":
            self.popup = None
            self._leave()

    def _leave(self):
        if not self.never_patient:
            self.patient_at = self.clock.now + self.linger + self.patient_after


class CloseExamineWaitTests(unittest.TestCase):
    def close(self, ui, clock, **kwargs):
        with patch.object(flows, "time", SimpleNamespace(time=clock.time, sleep=clock.sleep)):
            started = clock.now
            result = flows.close_examine(ui, **kwargs)
        return result, clock.now - started

    def test_options_popup_ends_unsaved_wait_and_patient_ends_settle(self):
        clock = FakeClock()
        ui = FakeExamineUi(clock, patient_after=2.0)
        result, spent = self.close(ui, clock, option="suspend", wait=10)
        self.assertEqual(ui.clicks, [flows.EXAMINE["close"], 502])
        self.assertEqual(result["settle"]["signal"], "patient")
        # 이전 구현: 1.5 + 저장 확인 6 + 1.5 + 대기 10 + 삭제 확인 4 = 23초
        self.assertLess(spent, 8.0)

    def test_without_screen_signal_waits_full_cap(self):
        clock = FakeClock()
        ui = FakeExamineUi(clock, never_patient=True)
        result, spent = self.close(ui, clock, option="suspend", wait=10)
        self.assertEqual(result["settle"]["signal"], "timeout")
        self.assertGreaterEqual(result["settle"]["waited"], 10.0)
        self.assertGreaterEqual(spent, 1.5 + 1.5 + 10 + 4)

    def test_lingering_option_popup_is_not_a_settle_signal(self):
        clock = FakeClock()
        ui = FakeExamineUi(clock, patient_after=1.0, linger=3.0)
        result, _spent = self.close(ui, clock, option="suspend", wait=10)
        self.assertEqual(result["settle"]["signal"], "patient")
        self.assertGreaterEqual(result["settle"]["waited"], 3.0)

    def test_delete_confirm_popup_is_handled(self):
        clock = FakeClock()
        ui = FakeExamineUi(clock, delete_confirm=True, patient_after=1.0)
        result, _spent = self.close(ui, clock, option="close", wait=10)
        self.assertEqual(result["settle"]["signal"], "dialog")
        self.assertEqual(ui.clicks, [flows.EXAMINE["close"], 501, 501])
        self.assertTrue(result["dialog"])

    def test_no_option_popup_returns_when_patient_screen_appears(self):
        clock = FakeClock()
        ui = FakeExamineUi(clock, options=False, patient_after=2.0)
        result, spent = self.close(ui, clock, option="suspend", wait=8)
        self.assertFalse(result["dialog"])
        self.assertEqual(result["settle"]["signal"], "patient")
        # 이전 구현: 1.5 + 저장 확인 6 + 옵션 대기 6 + 대기 8 = 21.5초
        self.assertLess(spent, 6.0)


class MenuVisibilityTests(unittest.TestCase):
    def test_hidden_pages_share_one_window_per_group(self):
        from tests import workflow13
        clock = FakeClock()
        groups = {"g1": 1, "g2": 2}
        pages = {"g1": {"a": 11, "late": 12, "x1": 13, "x2": 14},
                 "g2": {"b": 21, "y1": 22, "y2": 23}}
        opened = {}

        def open_group(ui, group, wait=2.0):
            opened["at"] = clock.now
            clock.sleep(wait)

        def controls(max_depth=8):
            out = [SimpleNamespace(ctrl_id=11, visible=True, rect=(0, 0, 100, 30)),
                   SimpleNamespace(ctrl_id=21, visible=True, rect=(0, 0, 100, 30)),
                   SimpleNamespace(ctrl_id=13, visible=True, rect=(0, 0, 10, 30))]
            if clock.now >= opened["at"] + 3.0:
                out.append(SimpleNamespace(ctrl_id=12, visible=True, rect=(0, 0, 100, 30)))
            return out
        ui = SimpleNamespace(controls=controls)
        with patch.object(workflow13, "time", SimpleNamespace(time=clock.time, sleep=clock.sleep)), \
                patch.object(flows, "SETTING_GROUPS", groups), \
                patch.object(flows, "setting_pages", side_effect=lambda g: pages[g]), \
                patch.object(flows, "open_setting", side_effect=lambda ui, wait=2.5: clock.sleep(wait)), \
                patch.object(flows, "open_setting_group", side_effect=open_group):
            started = clock.now
            seen = workflow13._menu_visibility(ui)
            spent = clock.now - started
        self.assertEqual(seen, {"g1": {"a": True, "late": True, "x1": False, "x2": False},
                                "g2": {"b": True, "y1": False, "y2": False}})
        # 그룹마다 열기 4.5초 + 공용 3초 안팎. 이전 구현은 숨김 페이지마다 3초(4개 × 3 = 12초 추가).
        self.assertLess(spent, 2 * (4.5 + 3.5))
