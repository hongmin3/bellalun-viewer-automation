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
from unittest import mock

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


class RowSignatureOCRTest(unittest.TestCase):
    """2026-08-31 실측: 일부 목록(예 `System > Account`)은 행이 owner-draw 라
    자식 창이 없다 - `row_signature()`가 그때만 화면 OCR 로 폴백하는지 확인한다.
    """

    def test_uses_child_text_without_ocr(self):
        row = _FakeControl((0, 0, 100, 20))
        row.hwnd = 1
        child = _FakeControl((0, 0, 50, 20))
        child.visible = True
        child.text = "Alice"
        with mock.patch.object(setting_lists, "children", return_value=[child]), \
             mock.patch("core.uitext.ocr") as ocr:
            sig = setting_lists.row_signature(row)
        self.assertEqual(sig, "Alice")
        ocr.assert_not_called()

    def test_falls_back_to_ocr_when_no_children(self):
        row = _FakeControl((0, 0, 100, 20))
        row.hwnd = 1
        with mock.patch.object(setting_lists, "children", return_value=[]), \
             mock.patch("core.uitext.ocr", return_value="service") as ocr:
            sig = setting_lists.row_signature(row, tesseract_exe="tess.exe")
        self.assertEqual(sig, "service")
        ocr.assert_called_once_with(row, "tess.exe")

    def test_ocr_failure_still_reports_unreadable(self):
        row = _FakeControl((0, 0, 100, 20))
        row.hwnd = 1
        with mock.patch.object(setting_lists, "children", return_value=[]), \
             mock.patch("core.uitext.ocr", side_effect=RuntimeError("boom")):
            sig = setting_lists.row_signature(row)
        self.assertEqual(sig, "")


class WalkOCRShortCircuitTest(unittest.TestCase):
    """2026-08-31 실측: OCR 로 읽은 서명은 같은 화면을 다시 캡처해도 완전히
    같다는 보장이 없어, 정지/연속 증명(완전 일치 요구)에 넣으면 잡음을 "행을
    건너뛰었다"로 오판한다. `walk()`가 첫 화면에서 이미 DB 원천 행 수와 정확히
    같은 개수를 OCR 로 다 봤을 때만 재확인 스크롤을 건너뛰는지 확인한다."""

    def test_skips_rescroll_when_ocr_rows_already_match_expected_count(self):
        rows = [_FakeControl((0, 0, 100, 20)), _FakeControl((0, 20, 100, 40))]
        with mock.patch.object(
                setting_lists, "_screen",
                side_effect=[(rows, ["service", "admin"], True)]):
            result = setting_lists.walk(mock.Mock(), mock.Mock(),
                                        expected_count=2)
        self.assertTrue(result["complete"])
        self.assertEqual(result["steps"], 0)
        self.assertEqual(result["signatures"], ["service", "admin"])

    def test_does_not_short_circuit_when_child_text_based(self):
        """자식 텍스트로 읽어 잡음이 없는 목록은 기존 재확인 스크롤을 그대로
        거친다 - OCR 과 무관한 경로는 동작을 바꾸지 않는다."""
        rows = [_FakeControl((0, 0, 100, 20)), _FakeControl((0, 20, 100, 40))]
        with mock.patch.object(
                setting_lists, "_screen",
                side_effect=[(rows, ["A", "B"], False),
                            (rows, ["A", "B"], False)]):
            result = setting_lists.walk(mock.Mock(), mock.Mock(),
                                        expected_count=2)
        self.assertTrue(result["complete"])
        self.assertEqual(result["steps"], 1)

    def test_does_not_short_circuit_when_count_mismatches(self):
        rows = [_FakeControl((0, 0, 100, 20))] * 3
        with mock.patch.object(
                setting_lists, "_screen",
                side_effect=[(rows, ["a", "b", "c"], True),
                            (rows, ["a", "b", "c"], True)]):
            result = setting_lists.walk(mock.Mock(), mock.Mock(),
                                        expected_count=0)
        self.assertEqual(result["steps"], 1)

    def test_does_not_short_circuit_when_some_rows_unreadable(self):
        rows = [_FakeControl((0, 0, 100, 20)), _FakeControl((0, 20, 100, 40))]
        with mock.patch.object(
                setting_lists, "_screen",
                side_effect=[(rows, ["service", ""], True),
                            (rows, ["service", ""], True)]):
            result = setting_lists.walk(mock.Mock(), mock.Mock(),
                                        expected_count=2)
        self.assertFalse(result["complete"])


class CollectOCRKeyingTest(unittest.TestCase):
    """2026-08-31 실측: OCR 서명은 Export 전/후 두 `collect()` 호출 사이에서
    미세하게 달라질 수 있어, 서명을 키로 쓰면 **값이 안 바뀐 행도** 문구가
    달라 짝이 안 맞을 수 있다(조용히 대조 대상에서 빠진다 — FAIL 로도 안
    드러난다). 식별 컬럼이 없으면 행 순서로 짝짓는 기존 관례(`compare_sweep`
    이전부터 있던 설계, `../프로젝트_상세.md` B.14)를 OCR 행에도 적용했는지
    확인한다."""

    def test_ocr_rows_are_keyed_by_position_not_noisy_text(self):
        rows = [_FakeControl((0, 0, 100, 20)), _FakeControl((0, 20, 100, 40))]
        with mock.patch.object(setting_lists, "_child_signature",
                              return_value=None), \
             mock.patch.object(
                setting_lists, "_screen",
                side_effect=[(rows, ["service noisy1", "admin noisy1"], True)]), \
             mock.patch.object(setting_lists, "read_details",
                              side_effect=[{"a": 1}, {"b": 2}]):
            result = setting_lists.collect(mock.Mock(), mock.Mock(),
                                           expected_count=2)
        self.assertEqual(set(result["details"]),
                         {"<OCR 행 #0>", "<OCR 행 #1>"})
        self.assertEqual(result["details"]["<OCR 행 #0>"], {"a": 1})
        self.assertEqual(result["duplicate_signatures"], [])
        self.assertEqual(result["stale_rows"], [])

    def test_child_text_rows_keep_signature_based_keying(self):
        """OCR 과 무관한(자식 텍스트) 목록은 기존처럼 서명을 키로 쓴다 —
        동작을 바꾸지 않는다."""
        rows = [_FakeControl((0, 0, 100, 20))]
        with mock.patch.object(setting_lists, "_child_signature",
                              return_value="Alice"), \
             mock.patch.object(setting_lists, "row_signature",
                              return_value="Alice"), \
             mock.patch.object(
                setting_lists, "_screen",
                side_effect=[(rows, ["Alice"], False),
                            (rows, ["Alice"], False)]), \
             mock.patch.object(setting_lists, "read_details",
                              return_value={"a": 1}):
            result = setting_lists.collect(mock.Mock(), mock.Mock(),
                                           expected_count=1)
        self.assertEqual(set(result["details"]), {"Alice"})


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
