# -*- coding: utf-8 -*-
"""`flows.close_examine_confirmed` 의 재시도 판단을 고정한다.

2026-08-31 `WF_07` Step 5 에서 Close 클릭이 삼켜져 검사가 열린 채 남은 사례가
있었다(재현율 1/3). 재시도는 **삼켜졌을 때만** 해야 한다 — 팝업 없이 정상
종료되는 경로가 따로 있어 무조건 다시 누르면 다음 검사를 건드릴 수 있다.
"""
import unittest
from unittest import mock

from core import flows


class _FakeDb:
    """`StudyStatus` 를 정해진 순서로 돌려주는 최소 DB."""

    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.reads = 0

    def one(self, database, sql, params=None):
        self.reads += 1
        value = self.statuses[min(self.reads - 1, len(self.statuses) - 1)]
        return None if value is None else {"StudyStatus": value}


class CloseExamineConfirmedTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def _stub(self, returns):
        """`close_examine` 을 가짜로 바꾼다.

        모듈 속성에 직접 대입하지 않고 `mock.patch.object` 를 쓴다 —
        `tools/check_module_attrs.py` 가 모듈 속성 대입을 경고하기 때문이다.
        """
        def fake(ui, option="close", **kwargs):
            self.calls.append(option)
            return returns[min(len(self.calls) - 1, len(returns) - 1)]

        patcher = mock.patch.object(flows, "close_examine", fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_swallowed_click_is_pressed_again(self):
        """팝업도 안 뜨고 StudyStatus 도 안 바뀌면 다시 누른다."""
        self._stub([{"dialog": False}, {"dialog": True, "option": "close"}])
        db = _FakeDb([flows.STUDY_STATUS_EXAMINING, 3])
        out = flows.close_examine_confirmed(None, db, 42, verify_timeout=0)
        self.assertEqual(2, out["attempts"])
        self.assertEqual(["close", "close"], self.calls)

    def test_dialog_path_is_not_retried(self):
        """종료 옵션 팝업이 떴으면 정상 경로다 — 다시 누르지 않는다."""
        self._stub([{"dialog": True, "option": "close"}])
        db = _FakeDb([flows.STUDY_STATUS_EXAMINING])
        out = flows.close_examine_confirmed(None, db, 42, verify_timeout=0)
        self.assertEqual(1, out["attempts"])
        self.assertEqual(["close"], self.calls)

    def test_no_dialog_but_actually_closed_is_not_retried(self):
        """팝업 없이 정상 종료된 경로(미촬영 Step 없음)도 다시 누르지 않는다."""
        self._stub([{"dialog": False}])
        db = _FakeDb([3])
        out = flows.close_examine_confirmed(None, db, 42, verify_timeout=0)
        self.assertEqual(1, out["attempts"])
        self.assertTrue(out["verify"]["closed"])
        self.assertEqual(["close"], self.calls)

    def test_retry_is_bounded(self):
        """계속 삼켜져도 attempts 상한을 넘지 않는다."""
        self._stub([{"dialog": False}])
        db = _FakeDb([flows.STUDY_STATUS_EXAMINING])
        out = flows.close_examine_confirmed(
            None, db, 42, attempts=3, verify_timeout=0)
        self.assertEqual(3, out["attempts"])
        self.assertEqual(3, len(self.calls))
        self.assertFalse(out["verify"]["closed"])

    def test_missing_study_row_is_not_treated_as_closed(self):
        """행을 못 읽으면 '닫혔다'고 단정하지 않는다."""
        db = _FakeDb([None])
        out = flows.wait_study_closed(db, 42, timeout=0)
        self.assertIsNone(out["status"])
        self.assertFalse(out["closed"])


if __name__ == "__main__":
    unittest.main()
