# -*- coding: utf-8 -*-
r"""`core/setting_lists.py` 의 판정 로직 단위 시험.

UI 없이 검증할 수 있는 것만 본다 — **겹침 계산**과 **상세값 대조**다. 이 둘이
`TC_Basic_WorkFlow_14` 의 "스크롤 아래 숨은 목록 행" 판정을 지탱한다.

특히 `overlap` 은 2026-08-25 오인("일부 행만 읽고 끝으로 착각")의 재발 방지
장치이므로, 겹치지 않는 경우가 **0 으로 나오는지**를 반드시 확인한다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import setting_lists                            # noqa: E402


class OverlapTest(unittest.TestCase):
    def test_full_overlap_when_screen_did_not_move(self):
        rows = ["a", "b", "c"]
        self.assertEqual(setting_lists.overlap(rows, rows), 3)

    def test_partial_overlap_after_scrolling_one_row(self):
        self.assertEqual(
            setting_lists.overlap(["a", "b", "c"], ["b", "c", "d"]), 2)

    def test_no_overlap_when_a_screen_was_skipped(self):
        """겹침 0 — 화면을 통째로 건너뛴 경우. 전수 열거로 인정하면 안 된다."""
        self.assertEqual(
            setting_lists.overlap(["a", "b", "c"], ["g", "h", "i"]), 0)

    def test_prefers_the_longest_overlap(self):
        """반복 문구가 있으면 짧은 겹침이 우연히 맞는다. 긴 쪽을 고른다."""
        self.assertEqual(
            setting_lists.overlap(["x", "a", "a"], ["a", "a", "y"]), 2)

    def test_empty_previous(self):
        self.assertEqual(setting_lists.overlap([], ["a"]), 0)


class _FakeControl:
    def __init__(self, rect):
        self.rect = rect
        self.center = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)


class RowClickPointTest(unittest.TestCase):
    def test_click_point_avoids_the_row_centre(self):
        """행 가운데의 버튼(⚙)을 누르지 않도록 좌측 첫 열을 누른다."""
        row = _FakeControl((100, 200, 900, 240))
        x, y = setting_lists.row_click_point(row)
        self.assertLess(x, row.center[0])
        self.assertGreaterEqual(x, 100)
        self.assertEqual(y, 220)

    def test_narrow_row_still_moves_off_the_left_edge(self):
        row = _FakeControl((100, 200, 130, 220))
        x, _ = setting_lists.row_click_point(row)
        self.assertGreater(x, 100)
        self.assertLess(x, 130)


def _details(rows):
    return {"details": {name: {key: {"kind": "edit", "value": value}
                               for key, value in items.items()}
                        for name, items in rows.items()}}


class CompareTest(unittest.TestCase):
    def test_identical_details_report_no_change(self):
        before = _details({"STORAGE": {"2240@10,10": "11116"}})
        after = _details({"STORAGE": {"2240@10,10": "11116"}})
        out = setting_lists.compare(before, after)
        self.assertEqual(out["changed"], [])
        self.assertEqual(out["compared_rows"], 1)
        self.assertEqual(out["compared_items"], 1)

    def test_changed_value_is_reported_with_row_and_item(self):
        before = _details({"STORAGE": {"2240@10,10": "11116"}})
        after = _details({"STORAGE": {"2240@10,10": "104"}})
        out = setting_lists.compare(before, after)
        self.assertEqual(len(out["changed"]), 1)
        self.assertEqual(out["changed"][0]["row"], "STORAGE")
        self.assertEqual(out["changed"][0]["before"], "11116")
        self.assertEqual(out["changed"][0]["after"], "104")

    def test_row_present_on_only_one_side(self):
        before = _details({"A": {"1@0,0": "x"}, "B": {"1@0,0": "y"}})
        after = _details({"A": {"1@0,0": "x"}})
        out = setting_lists.compare(before, after)
        self.assertEqual(out["only_before"], ["B"])
        self.assertEqual(out["only_after"], [])
        self.assertEqual(out["compared_rows"], 1)

    def test_item_present_on_only_one_side(self):
        before = _details({"A": {"1@0,0": "x"}})
        after = _details({"A": {"1@0,0": "x", "2@0,20": "z"}})
        out = setting_lists.compare(before, after)
        self.assertEqual(out["only_after"], ["A:2@0,20"])


def _pages(page_rows):
    return {"pages": {page: _details(rows) for page, rows in page_rows.items()}}


class CompareSweepTest(unittest.TestCase):
    """`compare_sweep()` 반환 키가 호출부(`tests/workflow14.py`)의 가정과
    맞는지 확인한다. `"changed"` 는 없고 `"changed_total"`(정수)만 있다 —
    2026-08-31 라이브 실행에서 이 불일치로 `KeyError: 'changed'`가 났다."""

    def test_no_change_reports_zero_total_and_no_flattened_items(self):
        before = _pages({"STORAGE": {"A": {"2240@10,10": "11116"}}})
        after = _pages({"STORAGE": {"A": {"2240@10,10": "11116"}}})
        out = setting_lists.compare_sweep(before, after)
        self.assertNotIn("changed", out)
        self.assertEqual(out["changed_total"], 0)
        flattened = [item for v in out["pages"].values() for item in v["changed"]]
        self.assertEqual(flattened, [])

    def test_changed_value_is_reachable_through_pages(self):
        before = _pages({"STORAGE": {"A": {"2240@10,10": "11116"}}})
        after = _pages({"STORAGE": {"A": {"2240@10,10": "104"}}})
        out = setting_lists.compare_sweep(before, after)
        self.assertEqual(out["changed_total"], 1)
        flattened = [item for v in out["pages"].values() for item in v["changed"]]
        self.assertEqual(len(flattened), 1)
        self.assertEqual(flattened[0]["row"], "A")


if __name__ == "__main__":
    unittest.main()
