# -*- coding: utf-8 -*-
"""`core/setting_changes.py` 단위 테스트 (UI/DB 없이 도는 것만).

여기서 잡으려는 것은 **변경 세트가 조용히 무력해지는 것**이다.

WF_14 의 Step 7 은 설정 테이블 전수 대조인데, 바꾸지 않은 테이블은 그 대조가
아무것도 증명하지 못한다. 그래서 변경 세트가 비거나, 한 테이블에 몰리거나,
`snapshot` 이 보지 않는 테이블을 가리키게 되면 **TC 는 통과하는데 검증 범위는
사라진다.** 그 상태는 실행해 봐도 초록색이라 눈에 띄지 않으므로 테스트로 막는다.
"""

import unittest

from core import setting_changes as sc
from core import setting_values as sv
from core import snapshot


class ChangePlanTest(unittest.TestCase):
    def test_plan_is_not_empty(self):
        self.assertTrue(sc.CHANGE_PLAN, "변경 세트가 비면 WF_14 Step 7 이 무의미해진다")

    def test_keys_unique(self):
        keys = [i.key for i in sc.CHANGE_PLAN]
        self.assertEqual(len(keys), len(set(keys)))

    def test_kinds_are_supported(self):
        for item in sc.CHANGE_PLAN:
            self.assertIn(item.kind, ("digits", "slider", "toggle"), item.key)

    def test_sections_are_compared_by_snapshot(self):
        """가리키는 섹션이 전수 대조 대상에 실제로 들어 있어야 한다.

        `snapshot.CONFIG_SECTIONS` 밖의 테이블을 바꾸면 Step 7 이 그 변경을
        아예 보지 못한다.
        """
        for item in sc.CHANGE_PLAN:
            self.assertIn(item.section, snapshot.CONFIG_SECTIONS, item.key)

    def test_sections_are_distinct(self):
        """한 테이블에 몰리면 넓힌 의미가 없다."""
        sections = [i.section for i in sc.CHANGE_PLAN]
        self.assertEqual(len(sections), len(set(sections)))

    def test_covers_several_menus(self):
        groups = {i.group for i in sc.CHANGE_PLAN}
        self.assertGreaterEqual(
            len(groups), 5, f"메뉴가 {len(groups)}개뿐이다: {sorted(groups)}")

    def test_sections_match_snapshot_queries(self):
        """항목이 적은 테이블 이름이 그 섹션의 실제 쿼리와 같아야 한다."""
        for item in sc.CHANGE_PLAN:
            _db, sql = snapshot.SNAPSHOT_QUERIES[item.section]
            self.assertIn(item.table, sql, item.key)

    def test_excluded_columns_are_not_touched(self):
        """되돌리지 못하면 회귀를 무너뜨리는 항목은 세트에 없어야 한다.

        Theme / Language / 자동 로그오프 / DICOM 통신 파라미터 / 노출 인터록.
        새 항목을 추가할 때 실수로 이런 걸 넣으면 여기서 걸린다.
        """
        banned = {"Theme", "Language", "AutoLogoffUse", "AutoLogoffTime",
                  "UseStrongPwd", "StationPort", "StationAETitle",
                  "DateFormat", "DateDelimiter", "GainCalPreventExposure",
                  "MagTablePreventExposure", "ImplantPreventExposure",
                  "AutoDeleteUse", "AutoDeleteType", "AutoDeleteUse"}
        for item in sc.CHANGE_PLAN:
            self.assertNotIn(item.column, banned, item.key)

    def test_volatile_fields_are_not_targets(self):
        """세션마다 저절로 바뀌는 값은 변경 대상이 될 수 없다."""
        for item in sc.CHANGE_PLAN:
            self.assertNotIn((item.section, item.column),
                             snapshot.VOLATILE_FIELDS, item.key)

    def test_slider_items_declare_their_display_edit(self):
        """슬라이더는 **값 표시 Edit** 을 반드시 선언해야 한다.

        선언하지 않으면 한 칸 눌렀을 때 실제로 움직였는지 확인할 수 없고,
        클릭이 삼켜져도 조용히 넘어간다 — 2026-08-25 WF_14 실행에서 실제로
        이 항목만 안 바뀌었다.
        """
        for item in sc.CHANGE_PLAN:
            if item.kind == "slider":
                self.assertIsNotNone(item.edit_id, item.key)

    def test_toggle_partner_ids_belong_to_plan(self):
        plan_ids = {i.ctrl_id for i in sc.CHANGE_PLAN}
        for ctrl_id in sc.TOGGLE_PARTNER:
            self.assertIn(ctrl_id, plan_ids)


class ToggleTargetTest(unittest.TestCase):
    def test_flips(self):
        self.assertEqual(sc.toggled_target(0), 1)
        self.assertEqual(sc.toggled_target(1), 0)

    def test_accepts_string_from_db(self):
        self.assertEqual(sc.toggled_target("0"), 1)


class _FakeControl:
    def __init__(self, cls, text, ctrl_id=0, visible=True):
        self.cls = cls
        self.text = text
        self.ctrl_id = ctrl_id
        self.visible = visible
        self.hwnd = id(self)
        self.rect = (0, 0, 100, 20)


class _FakeUi:
    def get_text(self, control):
        return control.text


class FindEditByValueTest(unittest.TestCase):
    """ID 가 겹치는 페이지에서 **값으로** 컨트롤을 고르는 규칙.

    2026-08-25 에 ID 로 `next(...)` 를 써서 엉뚱한 칸을 집었다. 후보가 하나가
    아니면 **집지 않는다**는 것이 이 규칙의 핵심이다.
    """

    def setUp(self):
        self.ui = _FakeUi()

    def test_picks_the_only_match(self):
        controls = [_FakeControl("Edit", "30"), _FakeControl("Edit", "100")]
        self.assertIs(sc.find_edit_by_value(self.ui, controls, 30), controls[0])

    def test_refuses_when_ambiguous(self):
        controls = [_FakeControl("Edit", "28"), _FakeControl("Edit", "28")]
        with self.assertRaises(sc.ChangeError):
            sc.find_edit_by_value(self.ui, controls, 28)

    def test_refuses_when_missing(self):
        controls = [_FakeControl("Edit", "28")]
        with self.assertRaises(sc.ChangeError):
            sc.find_edit_by_value(self.ui, controls, 30)

    def test_ignores_non_edit_and_hidden(self):
        controls = [_FakeControl("Static", "30"),
                    _FakeControl("Edit", "30", visible=False),
                    _FakeControl("Edit", "30")]
        self.assertIs(sc.find_edit_by_value(self.ui, controls, "30"),
                      controls[2])


class TypeDigitsGuardTest(unittest.TestCase):
    def test_rejects_non_digits(self):
        with self.assertRaises(sc.ChangeError):
            sc.type_digits(_FakeUi(), _FakeControl("Edit", ""), "12a")


class SummarizeTest(unittest.TestCase):
    def test_counts_and_sections(self):
        applied = [
            {"key": "a", "label": "A", "section": "system_common",
             "column": "T.C", "ok": True, "before": 1, "actual": 2},
            {"key": "b", "label": "B", "section": "overlay",
             "column": "T.D", "ok": False, "error": "실패함"},
        ]
        out = sc.summarize(applied)
        self.assertEqual(out["요청"], 2)
        self.assertEqual(out["적용됨"], 1)
        self.assertEqual(out["덮은 설정테이블"], ["system_common"])
        self.assertEqual(out["실패"], [{"항목": "b", "사유": "실패함"}])
        self.assertEqual(out["변경 내역"][0]["값"], "1 -> 2")

    def test_empty_is_reported_as_zero(self):
        """0개 적용을 성공처럼 요약하지 않는다."""
        out = sc.summarize([])
        self.assertEqual(out["적용됨"], 0)
        self.assertEqual(out["덮은 설정테이블"], [])


class VolatileControlsTest(unittest.TestCase):
    """장치 상태 칸을 비교에서 빼되, **뺐다는 사실은 보고**해야 한다."""

    @staticmethod
    def _pages(ups_values):
        return {"pages": {"device.ups": {
            "2536@10,10": {"kind": "value_text", "value": "EATON El"},
            "2539@216,293": {"kind": "edit", "value": ups_values[0]},
            "2540@216,337": {"kind": "edit", "value": ups_values[1]},
        }}, "missing": {}}

    def test_ups_status_change_is_not_a_difference(self):
        before = self._pages(("0 %", "Power Unknown"))
        after = self._pages(("Not Connected", "Not Connected"))
        out = sv.compare(before, after)
        self.assertEqual(out["changed"], [])
        self.assertEqual(len(out["volatile_skipped"]), 2)

    def test_real_setting_on_the_same_page_still_compared(self):
        before = self._pages(("0 %", "Power Unknown"))
        after = self._pages(("Not Connected", "Not Connected"))
        after["pages"]["device.ups"]["2536@10,10"]["value"] = "APC Sma"
        out = sv.compare(before, after)
        self.assertEqual(len(out["changed"]), 1)
        self.assertEqual(out["changed"][0]["control"], "2536@10,10")

    def test_other_pages_are_untouched_by_the_exclusion(self):
        before = {"pages": {"system.general": {
            "2232@1,1": {"kind": "edit", "value": "12"}}}, "missing": {}}
        after = {"pages": {"system.general": {
            "2232@1,1": {"kind": "edit", "value": "13"}}}, "missing": {}}
        out = sv.compare(before, after)
        self.assertEqual(len(out["changed"]), 1)
        self.assertEqual(out["volatile_skipped"], [])


class ForegroundGuardTest(unittest.TestCase):
    """물리 입력 가드는 **실제로 가리는 창이 있을 때만** 막아야 한다.

    이 저장소는 같은 오판을 두 번 겪었다.
      - 2026-08-19: 데스크톱이 최전면인 정상 순간을 가림으로 보고 로그인을
        중단시켜 14개 TC 가 연쇄 FAIL 했다.
      - 2026-08-25: 이 가드를 새로 넣으면서 같은 오판을 되살려 Q.C. 그룹 5개
        페이지를 통째로 놓쳤다(`가린 창: None`).
    """

    class _Ui:
        def __init__(self, result):
            self.result = result
            self.raise_calls = 0

        def is_foreground(self):
            return self.result.get("already", False)

        def blocking_window(self):
            return self.result["blocking"]

        def bring_to_front(self):
            self.raise_calls += 1
            return self.result

    def _pointer(self, result):
        from core.ui import ViewerUi
        return ViewerUi.require_front_for_pointer(self._Ui(result), "클릭")

    def _key(self, result):
        from core.ui import ViewerUi
        return ViewerUi.require_front(self._Ui(result), "키 입력")

    def test_raises_the_viewer_when_something_covers_it(self):
        """가린 창이 있으면 올려 보고, 올라왔으면 진행한다."""
        from core.ui import ViewerUi
        covered_then_ok = {"ok": True, "attempts": 1,
                           "blocking": {"title": "Claude", "pid": 9104}}
        ui = self._Ui(covered_then_ok)
        self.assertTrue(ViewerUi.require_front_for_pointer(ui, "클릭"))
        self.assertEqual(1, ui.raise_calls)

    def test_passes_when_nothing_is_blocking(self):
        """가리는 창이 없으면 **창을 건드리지 않고** 진행한다(셸/전환 중).

        `bring_to_front()` 를 부르는 것 자체가 시험 대상 창을 재배치하므로,
        호출하지 않았다는 것까지 확인한다.
        """
        from core.ui import ViewerUi
        shell = {"ok": False, "blocking": None, "attempts": 4}
        ui = self._Ui(shell)
        self.assertTrue(ViewerUi.require_front_for_pointer(ui, "클릭"))
        self.assertEqual(0, ui.raise_calls, "가리는 창이 없으면 창을 옮기지 않는다")
        ui2 = self._Ui(shell)
        ViewerUi.require_front(ui2, "키 입력")
        self.assertEqual(0, ui2.raise_calls)

    def test_already_in_front_does_nothing(self):
        from core.ui import ViewerUi
        ui = self._Ui({"ok": True, "blocking": None, "already": True})
        self.assertTrue(ViewerUi.require_front_for_pointer(ui, "클릭"))
        self.assertEqual(0, ui.raise_calls)

    def test_blocks_when_another_program_covers_the_viewer(self):
        covered = {"ok": False, "attempts": 4,
                   "blocking": {"title": "Claude", "pid": 9104}}
        with self.assertRaises(RuntimeError) as ctx:
            self._pointer(covered)
        self.assertIn("Claude", str(ctx.exception))
        with self.assertRaises(RuntimeError):
            self._key(covered)


if __name__ == "__main__":
    unittest.main()
