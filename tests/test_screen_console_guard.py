"""screen.grab: 잠깐 뜬 콘솔·터미널 창이 덮은 순간을 캡처하지 않는다.

2026-11-27 job270: 다른 예약 작업이 10분마다 띄운 Windows Terminal 창이 약 2초간
Viewer 를 덮었고, 그 순간의 Setting 패널 캡처로 라디오 값을 잘못 읽었다.
"""
import unittest
from unittest.mock import patch

from core import screen
from core import ui as ui_mod

BOX = (100, 100, 500, 400)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class ConsoleGuardTests(unittest.TestCase):
    def setUp(self):
        screen._persistent_consoles.clear()

    def tearDown(self):
        screen._persistent_consoles.clear()

    def patch_windows(self, classes):
        """classes: 호출마다 돌려줄 클래스 목록(마지막 값을 계속 쓴다)."""
        state = {"i": 0}

        def cls(hwnd):
            value = classes[min(state["i"], len(classes) - 1)]
            return value
        return patch.object(ui_mod, '_window_at_point', return_value=77), \
            patch.object(ui_mod, '_class_of', side_effect=cls), state

    def test_viewer_window_is_not_console(self):
        a, b, _ = self.patch_windows(["AfxFrameOrView140u"])
        with a, b:
            self.assertIsNone(screen._console_over(BOX))

    def test_terminal_window_is_console(self):
        a, b, _ = self.patch_windows(["CASCADIA_HOSTING_WINDOW_CLASS"])
        with a, b:
            self.assertEqual(screen._console_over(BOX), 77)

    def test_waits_until_transient_console_leaves(self):
        clock = Clock()
        seq = iter([77, 77, 77, None])
        with patch.object(screen, '_console_over', side_effect=lambda box: next(seq)):
            waited = screen.wait_console_clear(BOX, timeout=5, clock=clock, sleep=clock.sleep)
        self.assertAlmostEqual(waited, 0.75)
        self.assertEqual(screen._persistent_consoles, set())

    def test_long_lived_console_is_remembered_and_not_waited_again(self):
        clock = Clock()
        with patch.object(screen, '_console_over', return_value=77):
            waited = screen.wait_console_clear(BOX, timeout=1, clock=clock, sleep=clock.sleep)
        self.assertGreaterEqual(waited, 1)
        self.assertIn(77, screen._persistent_consoles)
        a, b, _ = self.patch_windows(["CASCADIA_HOSTING_WINDOW_CLASS"])
        with a, b:
            self.assertIsNone(screen._console_over(BOX))

    def test_grab_retakes_when_console_appears_during_capture(self):
        shots = []

        class Img:
            def __init__(self, n):
                self.n = n

            def convert(self, mode):
                return self
        over = iter([77, None])   # 첫 캡처 직후 덮임 → 다시 뜬 뒤 깨끗
        with patch.object(screen, 'wait_console_clear', return_value=0), \
             patch.object(screen, '_console_over', side_effect=lambda box: next(over)), \
             patch('PIL.ImageGrab.grab', side_effect=lambda **k: shots.append(1) or Img(len(shots))):
            img = screen.grab(BOX)
        self.assertEqual(len(shots), 2)
        self.assertEqual(img.n, 2)


if __name__ == '__main__':
    unittest.main()
