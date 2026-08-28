# -*- coding: utf-8 -*-
r"""`core/image_overlay.py` 의 선량·패널 종류 판정 단위 시험.

**실측 OCR 문구를 그대로 고정한다.** 이 판정들은 사양서1 233쪽 SRS 03-50-10
(Dose kVp/mAs: 2D O / 3D Raw O / 3D Recon X / 3D Sync X)을 화면에서 확인하는
경로인데, OCR 결과가 지저분해서 정규식을 조금만 손봐도 조용히 뒤집힌다.
2026-08-28 실행에서 실제로 읽힌 문자열을 여기 박아 둔다 — 전처리나 정규식을
바꿀 때 이 시험이 먼저 깨져야 한다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import image_overlay as io_


class DoseStateTest(unittest.TestCase):
    """선량 Overlay 가 **값**인지 `--`(미표시)인지 가른다."""

    def test_2d_panel_reads_numeric_dose(self):
        # 2026-08-26 실측 크롭 02_preview_panel1_bottom.png 의 판독 결과.
        # `kVp` 의 V 가 `¥` 로 읽히는 것이 정상 범위다.
        for text in ("28 k¥p\n32 mAs", "28 kVp\n32 mAs", "28 k¥p\n32 MAS"):
            with self.subTest(text=text):
                state = io_.dose_state({"bottom": text})
                self.assertEqual(state["Dose kVp"], "value")
                self.assertEqual(state["Dose mAs"], "value")

    def test_3d_recon_panel_reads_dashes(self):
        # 02_preview_panel2_bottom.png — 3D-N Recon. 사양표가 X 인 자리다.
        for text in ("--k¥p\n-- mAs", "-- kVp\n-- mAs"):
            with self.subTest(text=text):
                state = io_.dose_state({"bottom": text})
                self.assertEqual(state["Dose kVp"], "dash")
                self.assertEqual(state["Dose mAs"], "dash")

    def test_missing_label_is_none(self):
        # 선량 항목이 Overlay 설정에 없으면 라벨조차 없다(WF_03 미수행 상태).
        state = io_.dose_state({"bottom": "ee"})
        self.assertEqual(state["Dose kVp"], "none")
        self.assertEqual(state["Dose mAs"], "none")

    def test_value_wins_over_dash(self):
        """한 변형에서 대시로 잘못 읽혀도 값이 읽혔으면 값으로 본다."""
        state = io_.dose_state({"a": "28 k¥p", "b": "-- k¥p"})
        self.assertEqual(state["Dose kVp"], "value")


class PanelKindTest(unittest.TestCase):
    """패널이 2D 인지 3D 인지 View Position 표기로 가른다."""

    def test_3d_panels_have_mode_in_parentheses(self):
        # 실측: 제품이 패널 왼쪽 위에 `LCC (3D-N)` 처럼 모드를 붙인다.
        self.assertEqual(io_.panel_kind({"t": "LCC (3D-N)\nID: DATA_FLOW"}), "3D")
        self.assertEqual(io_.panel_kind({"t": "RCC (3D-W)\nID: X"}), "3D")

    def test_2d_panel_has_no_mode_suffix(self):
        self.assertEqual(
            io_.panel_kind({"t": "ID: DATA_FLOW_MWL_O1\nName: AUTO MWL"}), "2D")


class DoseSpecTableTest(unittest.TestCase):
    """사양서1 233쪽 SRS 03-50-10 표를 코드가 그대로 들고 있는지."""

    def test_value_expected_only_for_2d_and_raw(self):
        self.assertTrue(io_.dose_expected(0))      # 2D
        self.assertTrue(io_.dose_expected(1))      # 3D Raw
        self.assertFalse(io_.dose_expected(2))     # 3D Recon
        self.assertFalse(io_.dose_expected(3))     # 3D Sync


if __name__ == "__main__":
    unittest.main()
