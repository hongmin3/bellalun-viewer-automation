# -*- coding: utf-8 -*-
r"""`core/dicom_settings.py` 의 Use 동기화 로직 단위 시험.

UI 전체를 띄우지 않고 검증할 수 있는 것만 본다 — `_sync_use()` 가 DB 를
읽을 때 Storage 의 전송 작업 사본 행(`SCPUseType<>0`)을 걸러내는지가 핵심이다.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import dicom_settings                            # noqa: E402


class SyncUseIgnoresJobCopiesTest(unittest.TestCase):
    """2026-09-01 실측: Storage 는 전송 작업 사본 행(`SCPUseType<>0`)도 설정
    행과 같은 `Name` 을 쓰고 늘 `Use=1` 이다. `_sync_use()`가 필터 없이 DB 를
    읽으면 사본 행의 `Use=1` 이 설정 행의 진짜 상태(예: `Use=0`)를 덮어써,
    이미 꺼진 항목을 "켜져 있다"고 오판해 화면 체크박스를 잘못 클릭한다
    (꺼야 할 항목을 오히려 켠다 — `setup-dicom` 실행 중 `BUNNY_TEST` 가 다시
    켜진 원인). `active_storage_rows()`/"Use 단일 선택" 판정과 같은
    `SCPUseType=0` 필터를 걸어 사본 행을 무시하는지 확인한다."""

    def test_storage_query_filters_job_copy_rows(self):
        """DB 쿼리에 `SCPUseType` 필터가 실제로 걸리는지 확인한다."""
        db = mock.Mock()
        db.query.return_value = []
        with mock.patch.object(dicom_settings, "_server_items", return_value=[]):
            dicom_settings._sync_use(mock.Mock(), db, "Storage", "STORAGE")
        sql = db.query.call_args.args[1]
        self.assertIn(f"SCPUseType={dicom_settings.STORAGE_SCP_USE_TYPE}", sql)

    def test_mwl_query_has_no_scpusetype_filter(self):
        """MWL/Print 테이블엔 이 개념이 없으니 필터를 걸지 않는다."""
        db = mock.Mock()
        db.query.return_value = []
        with mock.patch.object(dicom_settings, "_server_items", return_value=[]):
            dicom_settings._sync_use(mock.Mock(), db, "MWL", "MWL_TEST")
        sql = db.query.call_args.args[1]
        self.assertNotIn("SCPUseType", sql)

    def test_does_not_click_an_already_off_setting_row_despite_stale_job_copy(self):
        """실측 재현 — 설정 행(`Use=0`)은 이미 꺼져 있는데 같은 이름의 사본
        행(`Use=1`)이 섞여 있어도, 필터링된 쿼리 결과만 보면 목표가 아닌
        항목을 잘못 켜는 클릭이 일어나지 않아야 한다."""
        db = mock.Mock()
        # 필터링된 쿼리는 설정 행만 돌려준다고 가정한다(사본 행의 Use=1은
        # 이 결과에 안 섞인다 — 그게 이번 수정의 목적이다).
        db.query.return_value = [{"Name": "BUNNY_TEST", "Use": 0},
                                 {"Name": "STORAGE", "Use": 1}]
        item_bunny, item_storage = mock.Mock(), mock.Mock()
        item_bunny.hwnd, item_storage.hwnd = 111, 222
        ui = mock.Mock()

        def fake_select_name(_ui, item):
            return "BUNNY_TEST" if item is item_bunny else "STORAGE"

        with mock.patch.object(dicom_settings, "_server_items",
                              return_value=[item_bunny, item_storage]), \
             mock.patch.object(dicom_settings, "_select_name",
                              side_effect=fake_select_name), \
             mock.patch.object(dicom_settings, "children", return_value=[]):
            changed = dicom_settings._sync_use(ui, db, "Storage", "STORAGE")

        # BUNNY_TEST 는 이미 Use=0(목표도 off), STORAGE 는 이미 Use=1(목표도
        # on) — 상태가 이미 목표와 같으니 둘 다 클릭이 필요 없다.
        self.assertFalse(changed)
        ui.click.assert_not_called()

    def test_clicks_the_non_target_row_that_is_still_on(self):
        """설정 행 기준으로 목표가 아닌 항목이 아직 켜져 있으면(`Use=1`)
        정상적으로 꺼야 한다 — 필터링이 "아예 클릭을 안 하게" 만든 게
        아니라 "올바른 근거로" 클릭하는지 확인한다."""
        db = mock.Mock()
        db.query.return_value = [{"Name": "BUNNY_TEST", "Use": 1},
                                 {"Name": "STORAGE", "Use": 0}]
        item_bunny, item_storage = mock.Mock(), mock.Mock()
        item_bunny.hwnd, item_storage.hwnd = 111, 222
        ui = mock.Mock()

        def fake_select_name(_ui, item):
            return "BUNNY_TEST" if item is item_bunny else "STORAGE"

        checkbox_bunny, checkbox_storage = mock.Mock(), mock.Mock()

        def fake_children(hwnd, _depth):
            return [checkbox_bunny] if hwnd == 111 else [checkbox_storage]

        with mock.patch.object(dicom_settings, "_server_items",
                              return_value=[item_bunny, item_storage]), \
             mock.patch.object(dicom_settings, "_select_name",
                              side_effect=fake_select_name), \
             mock.patch.object(dicom_settings, "children",
                              side_effect=fake_children):
            changed = dicom_settings._sync_use(ui, db, "Storage", "STORAGE")

        self.assertTrue(changed)
        clicked = [c.args[0] for c in ui.click.call_args_list]
        self.assertIn(checkbox_bunny, clicked)
        self.assertIn(checkbox_storage, clicked)


if __name__ == "__main__":
    unittest.main()
