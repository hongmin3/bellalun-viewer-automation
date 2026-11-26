"""Setting 패널 캡처: 다른 프로그램 창이 덮은 순간의 픽셀로 값을 판정하지 않는다.

2026-11-27 job270 1.0.0.011 r1 WU_11: 10분마다 도는 다른 예약 작업의 콘솔 창이
00:50:01~03 동안 Setting 패널을 덮었다. 00:50:02 캡처로 patient.examined 라디오 9개를
False 로 읽어 '항목 단위 복원' Step 7 이 FAIL 했다(변경 전 캡처는 모두 True).
"""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import setting_values as sv
from core.ui import Control

PANE = (400, 100, 1800, 900)
FOREIGN = {"point": (402, 102), "pid": 999, "title": "Windows PowerShell",
           "class": "CASCADIA_HOSTING_WINDOW_CLASS"}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def run_grab(occluders, timeout=5.0):
    clock = Clock()
    grabs = []
    seq = iter(occluders)
    with patch.object(sv, '_pane_occluder', side_effect=lambda pane, pid: next(seq)), \
         patch.object(sv.screen, 'grab', side_effect=lambda pane: grabs.append(pane) or f"img{len(grabs)}"):
        image, info = sv.grab_unobscured(PANE, 10, timeout=timeout, poll=0.5,
                                         clock=clock, sleep=clock.sleep)
    return image, info, grabs


class GrabUnobscuredTests(unittest.TestCase):
    def test_clear_pane_is_captured_once(self):
        image, info, grabs = run_grab([None, None])
        self.assertEqual(image, "img1")
        self.assertIsNone(info)
        self.assertEqual(len(grabs), 1)

    def test_waits_until_foreign_window_leaves_before_capturing(self):
        image, info, grabs = run_grab([FOREIGN, FOREIGN, None, None])
        self.assertEqual(image, "img1")
        self.assertEqual(info, {"retries": 2})
        self.assertEqual(len(grabs), 1)

    def test_window_appearing_during_capture_discards_that_capture(self):
        # job270 사례: 캡처하는 동안 콘솔 창이 떴다.
        image, info, grabs = run_grab([None, FOREIGN, None, None])
        self.assertEqual(image, "img2")
        self.assertEqual(len(grabs), 2)

    def test_persistent_occlusion_returns_no_image_and_names_the_window(self):
        image, info, grabs = run_grab([FOREIGN] * 100, timeout=2.0)
        self.assertIsNone(image)
        self.assertEqual(info["pid"], 999)
        self.assertEqual(info["title"], "Windows PowerShell")
        self.assertEqual(grabs, [])


class PaneOccluderTests(unittest.TestCase):
    def test_any_sample_point_owned_by_other_process_is_occlusion(self):
        from core import ui as ui_mod
        owners = {(402, 102): 10}

        def at(point):
            return 1 if owners.get(tuple(point), 999) == 10 else 2
        with patch.object(ui_mod, '_window_at_point', side_effect=at), \
             patch.object(ui_mod, '_pid_of', side_effect=lambda h: 10 if h == 1 else 999), \
             patch.object(ui_mod, '_text_of', return_value='Windows PowerShell'), \
             patch.object(ui_mod, '_class_of', return_value='CASCADIA_HOSTING_WINDOW_CLASS'):
            found = sv._pane_occluder(PANE, 10)
        self.assertEqual(found["pid"], 999)
        self.assertEqual(found["title"], 'Windows PowerShell')

    def test_all_points_owned_by_viewer_is_clear(self):
        from core import ui as ui_mod
        with patch.object(ui_mod, '_window_at_point', return_value=1), \
             patch.object(ui_mod, '_pid_of', return_value=10):
            self.assertIsNone(sv._pane_occluder(PANE, 10))

    def test_sample_points_cover_pane_corners_and_stay_inside(self):
        points = sv._sample_points(PANE)
        self.assertEqual(len(points), 16)
        self.assertIn((402, 102), points)
        self.assertIn((1798, 898), points)
        self.assertTrue(all(400 <= x < 1800 and 100 <= y < 900 for x, y in points))


class ReadAllOcclusionTests(unittest.TestCase):
    def sweep(self, grab_result):
        pane = Control(20, 1200, '#32770', '', PANE, True, 1)
        rail = Control(10, 1200, 'AfxWnd140u', 'SettingMenuItem', (150, 100, 350, 140), True, 1)
        radio = Control(31, 1, 'AfxWnd140u', 'RadioButton', (443, 339, 467, 363), True, 1)
        with ExitStack() as stack:
            for name, value in (('_viewer_gone', False), ('setting_window', object()),
                                ('_open_page', rail), ('pane_control', pane),
                                ('grab_unobscured', grab_result)):
                stack.enter_context(patch.object(sv, name, return_value=value))
            stack.enter_context(patch.object(sv, '_wait_page_settled', return_value=([radio], True)))
            stack.enter_context(patch.object(sv.screen, 'radio_selected_in', return_value=False))
            stack.enter_context(patch.object(sv.flows, 'open_setting'))
            stack.enter_context(patch.object(sv.flows, 'open_setting_group'))
            stack.enter_context(patch.object(sv.flows, 'setting_pages',
                                              return_value={'examined': 100}))
            return sv.read_all(SimpleNamespace(pid=10, get_text=lambda c: c.text),
                               groups=['patient'], record_handles=False)

    def test_occluded_page_is_missing_not_false_values(self):
        result = self.sweep((None, dict(FOREIGN, retries=40)))
        self.assertNotIn('patient.examined', result['pages'])
        self.assertIn('가려', result['missing']['patient.examined'])
        self.assertEqual(result['occlusions']['patient.examined']['pid'], 999)

    def test_retried_capture_is_read_and_retry_is_recorded(self):
        result = self.sweep((object(), {"retries": 3}))
        self.assertIn('patient.examined', result['pages'])
        self.assertEqual(result['occlusions']['patient.examined'], {"retries": 3})
        self.assertNotIn('patient.examined', result['missing'])


if __name__ == '__main__':
    unittest.main()
