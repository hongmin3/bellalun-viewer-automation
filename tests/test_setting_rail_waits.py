# -*- coding: utf-8 -*-
"""Setting 그룹·페이지 레일 클릭 뒤 고정 대기를 화면 신호로 끝낸다.

Validates: REQ-SPEEDUP-009
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import flows, setting_values


def _control(ctrl_id, hwnd=0, cls="Button", visible=True, rect=(0, 0, 120, 30)):
    return SimpleNamespace(ctrl_id=ctrl_id, hwnd=hwnd, cls=cls, visible=visible, rect=rect)


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.slept = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds


class FakeUi:
    def __init__(self, on_click=None):
        self.clicks = []
        self.on_click = on_click

    def click(self, target, settle=0.4):
        self.clicks.append((target.ctrl_id, settle))
        if self.on_click:
            self.on_click(target)


class RailWaitTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.rail = []          # Setting 창 얕은 자식
        self.patches = [
            patch.object(flows.time, "time", side_effect=self.clock.time),
            patch.object(flows.time, "sleep", side_effect=self.clock.sleep),
            patch.object(setting_values, "setting_window", return_value=object()),
            patch.object(setting_values, "shallow", side_effect=lambda ui, window: list(self.rail)),
            patch.object(setting_values, "pane_controls", side_effect=lambda pane, depth=6: [1, 2, 3]),
            patch.object(setting_values, "_wait_page_settled",
                         side_effect=lambda ui, pane, controls, tries=4, gap=0.25: (controls, True)),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_open_group_is_not_clicked_again(self):
        page = flows.SETTING_DICOM_PAGES["mwl"]
        self.rail = [_control(page)]
        ui = FakeUi()
        self.assertIsNone(flows.open_setting_group(ui, "dicom"))
        self.assertEqual(ui.clicks, [])

    def test_group_click_ends_when_its_pages_appear(self):
        group = flows.SETTING_GROUPS["dicom"]
        page = flows.SETTING_DICOM_PAGES["general"]
        self.rail = [_control(group)]
        ui = FakeUi(on_click=lambda target: self.rail.append(_control(page)))
        flows.open_setting_group(ui, "dicom", wait=2.0)
        self.assertEqual(ui.clicks, [(group, 0.1)])
        self.assertEqual(flows.last_setting_wait["signal"], "rail")
        self.assertLess(self.clock.slept, 1.0)

    def test_other_group_pages_are_not_a_signal(self):
        group = flows.SETTING_GROUPS["dicom"]
        other = flows.SETTING_SYSTEM_PAGES["general"]
        self.rail = [_control(group), _control(other)]
        ui = FakeUi()
        flows.open_setting_group(ui, "dicom", wait=2.0)
        self.assertEqual(flows.last_setting_wait["signal"], "timeout")
        # 신호가 없으면 예전 고정 대기(클릭 1.0 + wait 2.0)만큼 기다린다.
        self.assertGreaterEqual(self.clock.slept + 0.1, 3.0 - 1e-6)

    def test_page_click_ends_when_new_pane_is_drawn(self):
        page = flows.SETTING_DICOM_PAGES["mwl"]
        old_pane = _control(0, hwnd=11, cls="#32770", rect=(400, 80, 1800, 900))
        new_pane = _control(0, hwnd=22, cls="#32770", rect=(400, 80, 1800, 900))
        self.rail = [_control(page, rect=(160, 100, 370, 130)), old_pane]

        def draw(target):
            self.rail.remove(old_pane)
            self.rail.append(new_pane)
        ui = FakeUi(on_click=draw)
        with patch.object(setting_values, "pane_control",
                          side_effect=lambda ui, rail, window=None: next(
                              (c for c in self.rail if c.cls == "#32770"), None)):
            flows._click_setting_control(ui, page, "page", wait=2.5)
        self.assertEqual(flows.last_setting_wait["signal"], "pane")
        self.assertLess(self.clock.slept, 1.0)

    def test_same_pane_waits_full_old_duration(self):
        page = flows.SETTING_DICOM_PAGES["mwl"]
        pane = _control(0, hwnd=11, cls="#32770", rect=(400, 80, 1800, 900))
        self.rail = [_control(page, rect=(160, 100, 370, 130)), pane]
        ui = FakeUi()
        with patch.object(setting_values, "pane_control", return_value=pane):
            flows._click_setting_control(ui, page, "page", wait=2.5)
        self.assertEqual(flows.last_setting_wait["signal"], "timeout")
        self.assertGreaterEqual(self.clock.slept + 0.1, 3.5 - 1e-6)

    def test_unsettled_new_pane_is_not_a_signal(self):
        page = flows.SETTING_DICOM_PAGES["mwl"]
        new_pane = _control(0, hwnd=22, cls="#32770", rect=(400, 80, 1800, 900))
        self.rail = [_control(page, rect=(160, 100, 370, 130))]
        ui = FakeUi(on_click=lambda target: self.rail.append(new_pane))
        with patch.object(setting_values, "pane_control", return_value=new_pane), \
                patch.object(setting_values, "_wait_page_settled",
                             side_effect=lambda ui, pane, controls, tries=4, gap=0.25: (controls, False)):
            flows._click_setting_control(ui, page, "page", wait=1.2)
        self.assertEqual(flows.last_setting_wait["signal"], "timeout")

    def test_update_button_keeps_fixed_wait(self):
        update = _control(flows.SETTING_UPDATE_BUTTON)
        ui = FakeUi()
        ui.controls = lambda max_depth=7: [update]
        flows.setting_update(ui, wait=3)
        self.assertEqual(ui.clicks, [(flows.SETTING_UPDATE_BUTTON, 1.0)])
        self.assertGreaterEqual(self.clock.slept, 3.0)

    def test_rail_targets(self):
        self.assertEqual(flows._setting_rail_target(flows.SETTING_GROUPS["qc"]), ("group", "qc"))
        self.assertEqual(flows._setting_rail_target(flows.SETTING_QC_PAGES["scheduler"]), ("page", "qc"))
        self.assertIsNone(flows._setting_rail_target(flows.SETTING_UPDATE_BUTTON))


if __name__ == "__main__":
    unittest.main()


class ProcessExitWaitTests(unittest.TestCase):
    def test_returns_soon_after_process_exits(self):
        clock = Clock()
        states = iter([True, True, False])
        with patch.object(flows.time, "time", side_effect=clock.time), \
                patch.object(flows.time, "sleep", side_effect=clock.sleep):
            self.assertTrue(flows.wait_process_exit(5, limit=3.0, alive=lambda pid: next(states)))
        self.assertLess(clock.slept, 1.0)

    def test_waits_full_limit_while_alive(self):
        clock = Clock()
        with patch.object(flows.time, "time", side_effect=clock.time), \
                patch.object(flows.time, "sleep", side_effect=clock.sleep):
            self.assertFalse(flows.wait_process_exit(5, limit=3.0, alive=lambda pid: True))
        self.assertGreaterEqual(clock.slept, 3.0 - 1e-6)
