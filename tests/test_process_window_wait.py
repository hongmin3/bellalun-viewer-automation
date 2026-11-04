# -*- coding: utf-8 -*-
"""Viewer Image Processing 창 열기·닫기의 상태 기반 대기. UI·제품 없이 돈다.

2026-11-05 WU 체인의 XIPL_04 Step 8에서 한 번 "window did not open" 예외가 났다.
촬영 직후 취소→다시 열기 흐름에서 클릭 2초 뒤 한 번만 확인하던 것이 원인 후보다.
"""
import unittest
from unittest import mock

from core import viewer_processing as vp


class _Ctrl:
    def __init__(self, visible=True):
        self.visible = visible


class _FakeUi:
    """`by_id`가 시각별로 다른 컨트롤 목록을 돌려주는 가짜 UI."""

    def __init__(self, script):
        self.script = script          # ctrl_id -> callable(clicks, polls) -> visible?
        self.clicks = []
        self.polls = 0

    def by_id(self, cid):
        self.polls += 1
        rule = self.script.get(cid)
        return [_Ctrl()] if rule and rule(self) else []

    def click(self, ctrl, settle=0):
        self.clicks.append(ctrl)


def _no_sleep():
    return mock.patch("time.sleep", lambda *_: None)


class OpenProcessTests(unittest.TestCase):
    def test_waits_for_window_that_appears_late(self):
        ui = _FakeUi({vp.PROC: lambda u: True,
                      vp.PARAM_COMBO: lambda u: u.polls > 12})
        with _no_sleep():
            vp.open_process(ui, timeout=60)
        self.assertEqual(len(ui.clicks), 1)

    def test_waits_for_process_button_before_clicking(self):
        ui = _FakeUi({vp.PROC: lambda u: u.polls > 6,
                      vp.PARAM_COMBO: lambda u: bool(u.clicks)})
        with _no_sleep():
            vp.open_process(ui, timeout=60)
        self.assertEqual(len(ui.clicks), 1)

    def test_clicks_once_more_when_first_click_is_lost(self):
        ui = _FakeUi({vp.PROC: lambda u: True,
                      vp.PARAM_COMBO: lambda u: len(u.clicks) >= 2})
        with _no_sleep(), mock.patch("time.time", side_effect=_clock()):
            vp.open_process(ui, timeout=10)
        self.assertEqual(len(ui.clicks), 2)

    def test_raises_same_message_when_window_never_opens(self):
        ui = _FakeUi({vp.PROC: lambda u: True, vp.PARAM_COMBO: lambda u: False})
        with _no_sleep(), mock.patch("time.time", side_effect=_clock()):
            with self.assertRaisesRegex(RuntimeError, "Image Processing window did not open"):
                vp.open_process(ui, timeout=10)
        self.assertEqual(len(ui.clicks), 2)


class CancelWindowTests(unittest.TestCase):
    def test_waits_until_processing_window_closes(self):
        ui = _FakeUi({vp.CANCEL: lambda u: not u.clicks,
                      vp.PARAM_COMBO: lambda u: u.polls < 10})
        with _no_sleep():
            self.assertTrue(vp.cancel_window(ui, timeout=60))
        self.assertGreaterEqual(ui.polls, 10)

    def test_without_cancel_button_does_nothing(self):
        ui = _FakeUi({})
        with _no_sleep():
            self.assertTrue(vp.cancel_window(ui))
        self.assertEqual(ui.clicks, [])


def _clock():
    t = [0.0]

    def tick():
        t[0] += 1.0
        return t[0]
    return lambda: tick()


if __name__ == "__main__":
    unittest.main()
