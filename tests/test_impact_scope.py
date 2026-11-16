# -*- coding: utf-8 -*-
"""변경 파일로 REQ-REGRESSION-002 UI 회귀 범위를 추천하는 `tools/impact_scope.py`.

Validates: REQ-SPEEDUP-002
"""
import unittest

from tools import impact_scope


class ClassifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = impact_scope.import_graph()

    def classify(self, *paths):
        return impact_scope.classify(list(paths), graph=self.graph)

    def test_docs_and_unit_tests_need_no_ui_run(self):
        result = self.classify("SPEC.md", "docs/regression-timing.md", "tests/test_wu_chain.py",
                               "tools/check_docs_sync.py")
        self.assertEqual(result["scope"], "none")
        self.assertEqual(result["tcs"], [])

    def test_tc_entry_file_selects_that_tc(self):
        result = self.classify("tests/workflow14.py")
        self.assertEqual(result["scope"], "selected")
        self.assertEqual(result["tcs"], ["TC_Basic_WorkFlow_14"])
        self.assertIn("--select TC_Basic_WorkFlow_14", result["command"])

    def test_helper_used_only_by_some_tcs_selects_them(self):
        result = self.classify("core/send_verify.py")
        self.assertEqual(result["scope"], "selected")
        self.assertIn("TC_Basic_WorkFlow_04", result["tcs"])
        self.assertIn("TC_Basic_WorkFlow_15", result["tcs"])
        self.assertNotIn("TC_Basic_WorkFlow_14", result["tcs"])

    def test_xipl_flows_selects_xipl_stage(self):
        self.assertEqual(self.classify("tests/xipl_flows.py")["tcs"], ["TC_XIPL_compatibility"])

    def test_wu_only_files(self):
        for path in ("core/winupdate_report.py", "core/update_evidence.py"):
            self.assertEqual(self.classify(path)["scope"], "wu", path)

    def test_tc_entry_used_by_other_tcs_or_wu_is_followed(self):
        # WF02 함수는 다른 WF와 XIPL이, WF03 함수는 WU 매핑이 쓴다. WU 매핑은 결과 계층이 쓴다.
        for path in ("tests/workflow02.py", "tests/workflow03.py", "tests/winupdate.py"):
            self.assertEqual(self.classify(path)["scope"], "full", path)

    def test_runner_import_of_entry_is_not_shared_use(self):
        graph = {"tests/workflow08.py": {"run.py"}, "core/x.py": {"tests/workflow08.py"}}
        self.assertEqual(impact_scope.classify(["core/x.py"], graph=graph)["tcs"],
                         ["TC_Basic_WorkFlow_08"])

    def test_shared_or_unmapped_behavior_needs_full(self):
        for path in ("run.py", "core/flows.py", "core/wu_chain.py", "core/ui.py", "core/result.py",
                     "core/dbreset.py", "bellalunauto/gui.py", "packaging/BellalunAuto.iss",
                     "automation_scope.json", "core/brand_new_module.py"):
            self.assertEqual(self.classify(path)["scope"], "full", path)

    def test_basic_and_wu_together_need_full(self):
        result = self.classify("tests/workflow14.py", "core/wu_chain.py")
        self.assertEqual(result["scope"], "full")

    def test_every_reason_names_the_file(self):
        result = self.classify("tests/workflow08.py", "SPEC.md")
        files = {row["path"] for row in result["files"]}
        self.assertEqual(files, {"tests/workflow08.py", "SPEC.md"})


if __name__ == "__main__":
    unittest.main()
