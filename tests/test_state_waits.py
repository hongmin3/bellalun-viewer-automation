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
