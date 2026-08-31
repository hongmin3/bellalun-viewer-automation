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


class ConfidentlyVisibleTest(unittest.TestCase):
    """2026-09-01 실측: `dicom.tag_mapping`/`qc.scheduler`는 목록을 담는
    `ScrollWnd` 뷰포트 높이가 행 높이의 정확한 배수가 아니다(뷰포트
    bottom=460, 행 높이 35px — 7행은 꽉 차고 8번째 행은 top=437부터
    시작해 bottom=472, 즉 12px 가 뷰포트 밖으로 튀어나온다). **행 자체의
    `rect`는 이 클리핑을 반영하지 않는다** — `GetWindowRect`가 명목상
    크기(35px)를 그대로 주므로, 처음 시도한 "행 높이 비교"는 틀렸다(라이브
    재검증에서 드러남). 뷰포트(부모 `ScrollWnd`) rect 와 행 rect 를 직접
    대조해야 한다. 잘린 행을 OCR 하면 끝에 잡음이 붙는 게 아니라 단어
    **중간** 글자가 바뀐다(`"Age"`→`"Aae"`, `"Study"`→`"Studv"`) —
    `_rows_match()`의 접두사+길이차 fuzzy 매칭이 전제하는 패턴과 달라
    걸러지지 않고 `overlap()`을 매번 0으로 떨어뜨렸다."""

    def test_drops_the_row_that_overflows_the_viewport_bottom(self):
        rows = [_FakeControl((420, 192 + i * 35, 1049, 192 + i * 35 + 35))
                for i in range(8)]  # row7 rect bottom=472, 실측과 동일
        viewport = (420, 192, 1049, 460)  # 실측 뷰포트
        kept = setting_lists._confidently_visible(rows, viewport)
        self.assertEqual(len(kept), 7)

    def test_keeps_rows_fully_inside_the_viewport(self):
        rows = [_FakeControl((0, i * 35, 400, i * 35 + 35)) for i in range(5)]
        viewport = (0, 0, 400, 175)  # 정확히 5행만큼(배수) — 클리핑 없음
        kept = setting_lists._confidently_visible(rows, viewport)
        self.assertEqual(kept, rows)

    def test_no_viewport_found_keeps_all_rows(self):
        """뷰포트를 못 찾으면(`None`) 아무것도 빼지 않는다 — 추측으로 정상
        행을 잘못 빼는 것보다 낫다."""
        rows = [_FakeControl((0, 0, 400, 35))]
        self.assertEqual(setting_lists._confidently_visible(rows, None), rows)

    def test_single_row_is_never_dropped(self):
        """뷰포트가 행 하나보다 작아 첫 행부터 잘려 보이는 극단적인 경우도
        빈 목록으로 만들지 않는다 — 통째로 없는 것보다 낫다."""
        rows = [_FakeControl((0, 0, 400, 35))]
        viewport = (0, 0, 400, 17)
        self.assertEqual(
            setting_lists._confidently_visible(rows, viewport), rows)

    def test_screen_excludes_clipped_row_from_signature(self):
        """`_screen()` 전체가 뷰포트로 잘린 행을 서명 목록에서 빼는지 —
        실제 라이브 캡처값(`"Patient Aae (0010.1010) (0010.1010) ~"`)과
        실측 뷰포트/행 rect 로 확인한다."""
        rows = [_FakeControl((420, 192 + i * 35, 1049, 192 + i * 35 + 35))
                for i in range(8)]
        clipped = rows[-1]
        sig_by_id = {id(r): f"row{i}" for i, r in enumerate(rows)}
        sig_by_id[id(clipped)] = "Patient Aae (0010.1010) (0010.1010) ~"
        viewport_ctrl = _FakeControl((420, 192, 1049, 460))
        viewport_ctrl.text = "ScrollWnd"
        with mock.patch.object(setting_lists, "visible_rows",
                              return_value=rows), \
             mock.patch.object(setting_lists.setting_values, "pane_controls",
                              return_value=[viewport_ctrl]), \
             mock.patch.object(
                 setting_lists, "row_signature",
                 side_effect=lambda r, tess=None: sig_by_id[id(r)]), \
             mock.patch.object(setting_lists, "_child_signature",
                              return_value=None):
            kept_rows, sigs, used_ocr = setting_lists._screen(mock.Mock())
        self.assertEqual(len(kept_rows), 7)
        self.assertNotIn("Patient Aae (0010.1010) (0010.1010) ~", sigs)
        self.assertTrue(used_ocr)


class ListViewportTest(unittest.TestCase):
    """`_list_viewport()`가 행과 좌우 경계가 일치하는 `ScrollWnd`만 고르고,
    후보가 여럿이면(중첩된 `ScrollWnd`) 가장 안쪽(좁은) 것을 고르는지 확인."""

    def test_picks_the_scrollwnd_matching_row_bounds(self):
        rows = [_FakeControl((420, 192, 1049, 227)),
                _FakeControl((420, 227, 1049, 262))]
        other_panel = _FakeControl((1030, 192, 1278, 382))
        other_panel.text = "ScrollWnd"
        viewport = _FakeControl((420, 192, 1049, 460))
        viewport.text = "ScrollWnd"
        with mock.patch.object(setting_lists.setting_values, "pane_controls",
                              return_value=[other_panel, viewport]):
            found = setting_lists._list_viewport(mock.Mock(), rows)
        self.assertEqual(found, (420, 192, 1049, 460))

    def test_picks_the_narrowest_nested_scrollwnd(self):
        rows = [_FakeControl((420, 192, 1049, 227))]
        outer = _FakeControl((419, 162, 1033, 460))
        outer.text = "ScrollWnd"
        inner = _FakeControl((420, 192, 1049, 460))
        inner.text = "ScrollWnd"
        with mock.patch.object(setting_lists.setting_values, "pane_controls",
                              return_value=[outer, inner]):
            found = setting_lists._list_viewport(mock.Mock(), rows)
        self.assertEqual(found, inner.rect)

    def test_returns_none_when_no_rows(self):
        self.assertIsNone(setting_lists._list_viewport(mock.Mock(), []))

    def test_returns_none_when_no_matching_scrollwnd(self):
        rows = [_FakeControl((420, 192, 1049, 227))]
        unrelated = _FakeControl((0, 0, 50, 50))
        unrelated.text = "ScrollWnd"
        with mock.patch.object(setting_lists.setting_values, "pane_controls",
                              return_value=[unrelated]):
            found = setting_lists._list_viewport(mock.Mock(), rows)
        self.assertIsNone(found)


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


class RowsMatchFuzzyTest(unittest.TestCase):
    """2026-08-31 실측: `tool.predefined_text`(Setting > Tool > Predefined
    Text)를 라이브로 스크롤하며 잡은 실제 OCR 잡음 사례로 `_rows_match()`가
    노이즈는 봐주고 진짜 다른 행은 안 봐주는지 확인한다."""

    def test_exact_match_without_fuzzy(self):
        self.assertTrue(setting_lists._rows_match("LCC", "LCC", fuzzy=False))

    def test_noisy_match_rejected_without_fuzzy(self):
        """자식 텍스트 기반(잡음 없음) 목록은 여전히 완전 일치만 인정한다 —
        2026-08-25 재발 방지 설계를 그대로 지킨다."""
        self.assertFalse(setting_lists._rows_match("LCC", "LCC i", fuzzy=False))

    def test_real_ocr_noise_samples_match_with_fuzzy(self):
        """실측 잡음 — 진짜 문구 뒤에 짧은 잡음이 붙은 경우."""
        samples = [("L", "L i"), ("R", "R f)"), ("LCC", "LCC i"),
                  ("RCC", "RCC i"), ("RCC", "RCC (]"), ("LMLO", "LMLO v"),
                  ("LMLO", "LMLO i"), ("IMPLANT", "IMPLANT .")]
        for clean, noisy in samples:
            with self.subTest(clean=clean, noisy=noisy):
                self.assertTrue(setting_lists._rows_match(clean, noisy,
                                                          fuzzy=True))

    def test_different_rows_with_shared_prefix_are_not_confused(self):
        """`"ACR Phantom"` 대 `"ACR Phantom (3D-N)"` 처럼 접두사 관계지만
        **실제로 다른 행**은 fuzzy 를 켜도 같다고 보면 안 된다 — 정규화 후
        차이가 3자("3dn")라 `MAX_OCR_NOISE_CHARS`(2)를 넘는다."""
        self.assertFalse(setting_lists._rows_match(
            "ACR Phantom", "ACR Phantom (3D-N)", fuzzy=True))

    def test_completely_different_rows_are_not_confused(self):
        self.assertFalse(setting_lists._rows_match("LCC", "RMLO", fuzzy=True))


class WalkFuzzyIntegrationTest(unittest.TestCase):
    """2026-08-31 `tool.predefined_text` 라이브 스크롤에서 그대로 캡처한 값으로
    fuzzy 겹침 증명이 실제로 사양서 기본값 7개(L/R/LCC/RCC/LMLO/RMLO/IMPLANT)를
    전부 복원하는지 확인한다 — 이 값은 실측이라 재현 가능한 회귀 시험이다.
    이 시험은 fuzzy 없이(구 코드) 돌리면 1회차 스크롤에서 겹침 0으로 실패한다."""

    def test_real_captured_ocr_sequence_completes_with_fuzzy_overlap(self):
        rows5 = [_FakeControl((0, i * 35, 400, i * 35 + 35)) for i in range(5)]
        screens = [
            (rows5, ["L i", "R |", "LCC", "RCC", "LMLO v"], True),
            (rows5, ["R f)", "LCC i", "RCC i", "LMLO", "RMLO v"], True),
            (rows5, ["LCC", "RCC (]", "LMLO i", "RMLO", "IMPLANT ."], True),
            (rows5, ["LCC", "RCC (]", "LMLO i", "RMLO", "IMPLANT ."], True),
        ]
        with mock.patch.object(setting_lists, "_screen", side_effect=screens):
            result = setting_lists.walk(mock.Mock(), mock.Mock(),
                                        expected_count=7)
        self.assertTrue(result["complete"], result["reasons"])
        self.assertEqual(len(result["signatures"]), 7)

    def test_a_real_skip_is_still_caught_despite_fuzzy_matching(self):
        """2026-08-25 재발 방지 — fuzzy 를 켜도 진짜로 건너뛴 행은 겹침 0 으로
        여전히 잡혀야 한다. `"ACR Phantom"` 뒤에 중간 행 없이 바로
        `"ACR Phantom (3D-N)"` 이 나오면(실제로는 그 사이 다른 QC 항목들을
        건너뛴 것) 접두사 관계라도 길이 차이가 커서 겹침으로 안 봐준다."""
        rows2 = [_FakeControl((0, i * 35, 400, i * 35 + 35)) for i in range(2)]
        # current_notches 는 3에서 시작하고 겹침이 0이면 1로 줄여 한 번 더
        # 재시도한다(재시도는 step 으로 안 센다) — 그다음에야 진짜 gap 으로
        # 본다. 재시도도 같은 내용을 읽는다고 가정해 3개를 준다.
        screens = [
            (rows2, ["ACR Phantom", "Artifact"], True),
            (rows2, ["ACR Phantom (3D-N)", "MTF (3D-N)"], True),
            (rows2, ["ACR Phantom (3D-N)", "MTF (3D-N)"], True),
        ]
        with mock.patch.object(setting_lists, "_screen", side_effect=screens):
            result = setting_lists.walk(mock.Mock(), mock.Mock(),
                                        expected_count=23)
        self.assertFalse(result["complete"])
        self.assertTrue(any("겹치는 행이 없다" in r for r in result["reasons"]))


class WalkEmptyListTest(unittest.TestCase):
    """2026-09-01 실측: `patient.physician`의 Referring/Reading/Performing
    Physician 세 목록은 컨트롤을 찾았는데도(호출부가 이미 확인) 행이 0개다
    — DB `PHYSICIAN`도 0행이라 이건 "못 찾았다"가 아니라 진짜 빈 목록이다.
    그런데 `walk()`는 "행이 안 보이면 무조건 실패"로 처리해 항상 불완전으로
    판정했다. `expected_count=0`일 때만 빈 목록을 완전한 열거로 인정하는지
    확인한다."""

    def test_empty_list_with_expected_zero_is_complete(self):
        with mock.patch.object(setting_lists, "_screen",
                               return_value=([], [], False)):
            result = setting_lists.walk(mock.Mock(), mock.Mock(),
                                        expected_count=0)
        self.assertTrue(result["complete"])
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["signatures"], [])

    def test_empty_list_with_unknown_expected_is_still_incomplete(self):
        with mock.patch.object(setting_lists, "_screen",
                               return_value=([], [], False)):
            result = setting_lists.walk(mock.Mock(), mock.Mock(),
                                        expected_count=None)
        self.assertFalse(result["complete"])
        self.assertTrue(any("보이지 않는다" in r for r in result["reasons"]))

    def test_empty_list_with_nonzero_expected_is_still_incomplete(self):
        with mock.patch.object(setting_lists, "_screen",
                               return_value=([], [], False)):
            result = setting_lists.walk(mock.Mock(), mock.Mock(),
                                        expected_count=3)
        self.assertFalse(result["complete"])


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


class CollectOverlayTest(unittest.TestCase):
    """2026-09-01 실측: `display.overlay` 는 카탈로그/Top/Bottom 세 목록이
    한 패널에 섞여 있어 일반 `visible_rows()`가 셋을 구분하지 못한다(실측
    28행 = 카탈로그 화면표시분 20 + Top 6 + Bottom 2 — DB `OVERLAY_ITEM`
    8행과는 무관한 합이었다). `_collect_overlay()`가 Top/Bottom 두 컨트롤만
    각각 `collect()`에 넘기고 결과를 병합하는지 확인한다."""

    def _fake_control(self, hwnd):
        c = _FakeControl((0, 0, 10, 10))
        c.hwnd = hwnd
        c.visible = True
        return c

    def test_splits_by_control_id_and_merges_results(self):
        top_ctrl = self._fake_control(111)
        bottom_ctrl = self._fake_control(222)

        def fake_by_id(ctrl_id):
            from core import viewer_processing as vp
            if ctrl_id == vp.OVERLAY_LIST_TOP:
                return [top_ctrl]
            if ctrl_id == vp.OVERLAY_LIST_BOTTOM:
                return [bottom_ctrl]
            return []

        ui = mock.Mock()
        ui.by_id.side_effect = fake_by_id

        def fake_collect(ui_arg, pane, expected_count=None, **kwargs):
            if pane is top_ctrl:
                return {"signatures": ["A", "B"], "screens": [], "steps": 1,
                        "complete": True, "reasons": [],
                        "expected_count": expected_count,
                        "unreadable_rows": 0,
                        "details": {"A": {}, "B": {}},
                        "duplicate_signatures": [], "stale_rows": []}
            if pane is bottom_ctrl:
                return {"signatures": ["C"], "screens": [], "steps": 0,
                        "complete": True, "reasons": [],
                        "expected_count": expected_count,
                        "unreadable_rows": 0, "details": {"C": {}},
                        "duplicate_signatures": [], "stale_rows": []}
            raise AssertionError("unexpected pane")

        db = mock.Mock()
        with mock.patch("core.viewer_processing._overlay_positions",
                       return_value={1: (0, 0), 2: (0, 1), 3: (1, 0)}), \
             mock.patch.object(setting_lists, "collect", side_effect=fake_collect):
            result = setting_lists._collect_overlay(ui, db)

        self.assertEqual(result["signatures"], ["A", "B", "C"])
        self.assertEqual(result["expected_count"], 3)  # top 2개 + bottom 1개
        self.assertTrue(result["complete"])
        self.assertEqual(result["details"], {"top:A": {}, "top:B": {},
                                             "bottom:C": {}})

    def test_missing_control_marks_incomplete(self):
        ui = mock.Mock()
        ui.by_id.return_value = []  # top/bottom 둘 다 못 찾음
        db = mock.Mock()
        with mock.patch("core.viewer_processing._overlay_positions",
                       return_value={}):
            result = setting_lists._collect_overlay(ui, db)
        self.assertFalse(result["complete"])
        self.assertEqual(result["signatures"], [])
        self.assertTrue(any("찾지 못했다" in r for r in result["reasons"]))

    def test_sweep_routes_display_overlay_through_collect_overlay(self):
        """`sweep()`이 `display.overlay` 키에서 일반 `collect(pane, ...)`
        대신 `_collect_overlay()`를 쓰는지 — 페이지 진입 자체는 목(mock)한다."""
        pane = self._fake_control(999)
        with mock.patch("core.flows.open_group_page", return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "setting_window",
                              return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "pane_control",
                              return_value=pane), \
             mock.patch.object(setting_lists.time, "sleep"), \
             mock.patch.object(
                 setting_lists, "_collect_overlay",
                 return_value={"signatures": [], "complete": True}) as co:
            result = setting_lists.sweep(mock.Mock(), mock.Mock(),
                                         [("display", "overlay")])
        co.assert_called_once()
        self.assertIn("display.overlay", result["pages"])


class SingleListControlTest(unittest.TestCase):
    """2026-09-01 실측: `procedure.procedure`는 Procedure 카탈로그(id=2560,
    15행=DB 일치)와 무관한 View Position 약어 목록(id=2561, 4행)이 한 패널에
    섞여 19행(15+4)으로 잡혔다 — `display.overlay`와 같은 교차 오염
    (`../프로젝트_상세.md` B.29). `sweep()`이 `SINGLE_LIST_CONTROL`에 있는
    키를 만나면 그 컨트롤 ID만 `pane` 삼는지 확인한다."""

    def _fake_control(self, hwnd):
        c = _FakeControl((0, 0, 10, 10))
        c.hwnd = hwnd
        c.visible = True
        return c

    def test_sweep_scopes_to_the_registered_control_id(self):
        catalogue_pane = self._fake_control(999)     # 일반 pane(=섞인 패널)
        real_list_ctrl = self._fake_control(2560)    # SINGLE_LIST_CONTROL 대상

        def fake_by_id(ctrl_id):
            if ctrl_id == 2560:
                return [real_list_ctrl]
            return []

        ui = mock.Mock()
        ui.by_id.side_effect = fake_by_id

        with mock.patch("core.flows.open_group_page", return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "setting_window",
                              return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "pane_control",
                              return_value=catalogue_pane), \
             mock.patch.object(setting_lists.time, "sleep"), \
             mock.patch.object(setting_lists, "expected_row_count",
                              return_value=15), \
             mock.patch.object(
                 setting_lists, "collect",
                 return_value={"signatures": [], "complete": True}) as co:
            result = setting_lists.sweep(ui, mock.Mock(),
                                         [("procedure", "procedure")])

        co.assert_called_once()
        # `collect()`의 두 번째 위치 인자(`pane`)가 섞인 패널이 아니라
        # 등록된 컨트롤이어야 한다.
        self.assertIs(co.call_args.args[1], real_list_ctrl)
        self.assertIn("procedure.procedure", result["pages"])

    def test_sweep_skips_page_when_registered_control_missing(self):
        ui = mock.Mock()
        ui.by_id.return_value = []
        with mock.patch("core.flows.open_group_page", return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "setting_window",
                              return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "pane_control",
                              return_value=self._fake_control(1)), \
             mock.patch.object(setting_lists.time, "sleep"):
            result = setting_lists.sweep(ui, mock.Mock(),
                                         [("procedure", "procedure")])
        self.assertNotIn("procedure.procedure", result["pages"])
        self.assertIn("procedure.procedure", result["skipped"])


class CollectMultiListTest(unittest.TestCase):
    """2026-09-01 실측: `patient.physician`은 독립된 목록이 넷(2x2 그리드) —
    라벨을 OCR로 읽어 "Referring/Reading/Performing Physician"(id 2318/2319/
    2320, 진짜 대상, 현재 모두 0행)과 "Performing Physician Order"(id 2321,
    MWL 역할 매핑 콤보 — 의사 명단 아님)를 구분했다. `_collect_multi_list()`가
    등록된 컨트롤들만 합치는지 확인한다."""

    def _fake_control(self, hwnd):
        c = _FakeControl((0, 0, 10, 10))
        c.hwnd = hwnd
        c.visible = True
        return c

    def test_merges_all_registered_controls(self):
        ctrl_a, ctrl_b = self._fake_control(1), self._fake_control(2)

        def fake_by_id(ctrl_id):
            return {1: [ctrl_a], 2: [ctrl_b]}.get(ctrl_id, [])

        ui = mock.Mock()
        ui.by_id.side_effect = fake_by_id

        def fake_collect(ui_arg, pane, expected_count=None, **kwargs):
            if pane is ctrl_a:
                return {"signatures": ["A1"], "steps": 0, "complete": True,
                        "reasons": [], "details": {"A1": {}}}
            if pane is ctrl_b:
                return {"signatures": ["B1", "B2"], "steps": 1,
                        "complete": True, "reasons": [],
                        "details": {"B1": {}, "B2": {}}}
            raise AssertionError("unexpected pane")

        with mock.patch.object(setting_lists, "collect", side_effect=fake_collect):
            result = setting_lists._collect_multi_list(ui, (1, 2),
                                                        expected_count=3)

        self.assertEqual(result["signatures"], ["A1", "B1", "B2"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["details"], {"1:A1": {}, "2:B1": {}, "2:B2": {}})

    def test_expected_zero_propagates_to_each_sub_list(self):
        """합계가 0이면 각 목록에도 0을 넘겨야 `walk()`가 빈 목록을 실패로
        오판하지 않는다(2026-09-01 실측, `patient.physician`)."""
        ctrl_a = self._fake_control(1)

        def fake_by_id(ctrl_id):
            return {1: [ctrl_a]}.get(ctrl_id, [])

        ui = mock.Mock()
        ui.by_id.side_effect = fake_by_id

        with mock.patch.object(
                setting_lists, "collect",
                return_value={"signatures": [], "steps": 0, "complete": True,
                              "reasons": [], "details": {}}) as co:
            setting_lists._collect_multi_list(ui, (1,), expected_count=0)

        self.assertEqual(co.call_args.kwargs.get("expected_count"), 0)

    def test_missing_control_is_noted_but_others_still_collected(self):
        ctrl_a = self._fake_control(1)

        def fake_by_id(ctrl_id):
            return {1: [ctrl_a]}.get(ctrl_id, [])

        ui = mock.Mock()
        ui.by_id.side_effect = fake_by_id

        with mock.patch.object(
                setting_lists, "collect",
                return_value={"signatures": ["A1"], "steps": 0,
                              "complete": True, "reasons": [],
                              "details": {"A1": {}}}):
            result = setting_lists._collect_multi_list(ui, (1, 2, 3))

        self.assertEqual(result["signatures"], ["A1"])
        self.assertFalse(result["complete"])
        self.assertTrue(any("id=2" in r for r in result["reasons"]))
        self.assertTrue(any("id=3" in r for r in result["reasons"]))

    def test_expected_count_mismatch_marks_incomplete(self):
        ui = mock.Mock()
        ui.by_id.return_value = []
        result = setting_lists._collect_multi_list(ui, (), expected_count=0)
        self.assertTrue(result["complete"])  # 0개 기대, 0개 열거 — 일치
        result2 = setting_lists._collect_multi_list(ui, (), expected_count=5)
        self.assertFalse(result2["complete"])


class CollectPrintOverlayTest(unittest.TestCase):
    """2026-09-01 실측: `dicom.print_overlay`는 Overlay 이름 목록에서 행을
    선택해야만 우측 Position 목록 셋(id 2486/2487/2488)이 채워진다(선택 전엔
    셋 다 0행). 합치면 DB `PRINT_OVERLAY_ITEM`과 정확히 같은 것을 센다
    (실측: Overlay 1개 x Position 0/1/2 각 2개 = 6행). `_collect_print_overlay()`
    가 이름마다 선택하며 Position 목록을 모으는지 확인한다."""

    def _fake_control(self, hwnd, rect=(0, 0, 10, 10)):
        c = _FakeControl(rect)
        c.hwnd = hwnd
        c.visible = True
        return c

    def test_selects_each_name_row_and_merges_positions(self):
        name_list_ctrl = self._fake_control(100)
        name_row = self._fake_control(101)
        name_row.text = "ListItem"
        pos_ctrls = {2486: self._fake_control(2486),
                    2487: self._fake_control(2487),
                    2488: self._fake_control(2488)}

        def fake_by_id(ctrl_id):
            if ctrl_id == setting_lists.PRINT_OVERLAY_NAME_LIST:
                return [name_list_ctrl]
            return [pos_ctrls[ctrl_id]] if ctrl_id in pos_ctrls else []

        ui = mock.Mock()
        ui.by_id.side_effect = fake_by_id

        def fake_collect(ui_arg, pane, expected_count=None, **kwargs):
            for cid, ctrl in pos_ctrls.items():
                if pane is ctrl:
                    return {"signatures": [f"field{cid}"], "steps": 0,
                            "complete": True, "reasons": [],
                            "details": {f"field{cid}": {}}}
            raise AssertionError("unexpected pane")

        with mock.patch.object(setting_lists, "children",
                              return_value=[name_row]), \
             mock.patch.object(setting_lists, "collect", side_effect=fake_collect), \
             mock.patch.object(setting_lists, "expected_row_count",
                              return_value=3):
            result = setting_lists._collect_print_overlay(ui, mock.Mock())

        ui.click.assert_called_once()
        self.assertEqual(sorted(result["signatures"]),
                         ["field2486", "field2487", "field2488"])
        self.assertTrue(result["complete"])

    def test_no_name_list_control_is_incomplete(self):
        ui = mock.Mock()
        ui.by_id.return_value = []
        with mock.patch.object(setting_lists, "expected_row_count",
                              return_value=6):
            result = setting_lists._collect_print_overlay(ui, mock.Mock())
        self.assertFalse(result["complete"])
        self.assertEqual(result["signatures"], [])
        self.assertTrue(any("찾지 못했다" in r for r in result["reasons"]))


class SweepRoutesPhysicianAndPrintOverlayTest(unittest.TestCase):
    """`sweep()`이 `patient.physician`/`dicom.print_overlay` 키에서 전용
    함수를 쓰는지 확인한다."""

    def _fake_control(self, hwnd):
        c = _FakeControl((0, 0, 10, 10))
        c.hwnd = hwnd
        c.visible = True
        return c

    def test_sweep_routes_patient_physician(self):
        pane = self._fake_control(1)
        with mock.patch("core.flows.open_group_page", return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "setting_window",
                              return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "pane_control",
                              return_value=pane), \
             mock.patch.object(setting_lists.time, "sleep"), \
             mock.patch.object(setting_lists, "expected_row_count",
                              return_value=0), \
             mock.patch.object(
                 setting_lists, "_collect_multi_list",
                 return_value={"signatures": [], "complete": True}) as cm:
            result = setting_lists.sweep(mock.Mock(), mock.Mock(),
                                         [("patient", "physician")])
        cm.assert_called_once()
        self.assertEqual(cm.call_args.args[1],
                         setting_lists.PHYSICIAN_LIST_CONTROLS)
        self.assertIn("patient.physician", result["pages"])

    def test_sweep_routes_dicom_print_overlay(self):
        pane = self._fake_control(1)
        with mock.patch("core.flows.open_group_page", return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "setting_window",
                              return_value=mock.Mock()), \
             mock.patch.object(setting_lists.setting_values, "pane_control",
                              return_value=pane), \
             mock.patch.object(setting_lists.time, "sleep"), \
             mock.patch.object(
                 setting_lists, "_collect_print_overlay",
                 return_value={"signatures": [], "complete": True}) as cpo:
            result = setting_lists.sweep(mock.Mock(), mock.Mock(),
                                         [("dicom", "print_overlay")])
        cpo.assert_called_once()
        self.assertIn("dicom.print_overlay", result["pages"])


if __name__ == "__main__":
    unittest.main()
