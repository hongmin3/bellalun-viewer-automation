# -*- coding: utf-8 -*-
"""로그인 직후 Patient 화면 계약 — 가짜 UI로 핵심 Control ID 표시 여부 확인."""
import unittest
from types import SimpleNamespace

from core import flows, screen_contract


class FakeUi:
    def __init__(self, visible_ids, hidden_ids=()):
        self.visible_ids, self.hidden_ids = set(visible_ids), set(hidden_ids)
        self.clicked = []

    def by_id(self, cid):
        if cid in self.visible_ids:
            return [SimpleNamespace(ctrl_id=cid, visible=True)]
        if cid in self.hidden_ids:
            return [SimpleNamespace(ctrl_id=cid, visible=False)]
        return []

    def click(self, *_a, **_k):  # 계약 확인은 클릭하면 안 된다
        self.clicked.append(_a)


class ScreenContractTests(unittest.TestCase):
    def test_core_controls_come_from_flows_constants(self):
        self.assertEqual((flows.PATIENT["tab_patient_list"], flows.PATIENT["tab_new_patient"],
                          flows.STATUS_BAR["menu"]), screen_contract.CORE_CONTROLS)
        self.assertIn(2015, screen_contract.CORE_CONTROLS)

    def test_all_visible_is_ok(self):
        ui = FakeUi(screen_contract.CORE_CONTROLS)
        result = screen_contract.check(ui)
        self.assertTrue(result["ok"])
        self.assertEqual([], result["missing"])
        self.assertEqual(list(screen_contract.CORE_CONTROLS), result["checked"])
        self.assertEqual([], ui.clicked)
        self.assertEqual("OK", screen_contract.to_item(result)["level"])

    def test_missing_and_hidden_controls_are_reported(self):
        ui = FakeUi([2284], hidden_ids=[2015])
        result = screen_contract.check(ui)
        self.assertFalse(result["ok"])
        self.assertEqual([2285, 2015], result["missing"])
        item = screen_contract.to_item(result)
        self.assertEqual("BLOCK", item["level"])
        self.assertTrue(item["blocks_run"])
        self.assertIn("2285", item["actual"])

    def test_by_id_error_counts_as_missing(self):
        class Broken:
            def by_id(self, cid):
                raise RuntimeError("창 없음")
        result = screen_contract.check(Broken(), required=(2285,))
        self.assertEqual({"ok": False, "missing": [2285], "checked": [2285]}, result)


if __name__ == "__main__":
    unittest.main()
