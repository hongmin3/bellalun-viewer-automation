# -*- coding: utf-8 -*-
import csv
import json
import os
import tempfile
import unittest

from core.result import BLOCKED, PASS, TCResult, write_reports


class ResultReportTests(unittest.TestCase):
    def _result(self):
        result = TCResult("TC_SAMPLE", "사용자용 결과 문서")
        result.add(1, "자동 확인", PASS, "정상", "정상")
        result.blocked(
            2, "실물 장치 확인",
            "필수 장치가 연결되지 않았다. "
            "**해제 조건**: 시험용 장치를 연결한 뒤 다시 실행한다. "
            "**이 실행으로 말할 수 없는 것**: 장치 연결 후 통신 성공 여부.")
        result.finalize()
        return result

    def test_blocked_is_distinct_tc_verdict(self):
        result = self._result()
        self.assertEqual(BLOCKED, result.verdict)
        self.assertEqual(1, result.counts[BLOCKED])
        check = result.checks[-1]
        self.assertEqual("시험용 장치를 연결한 뒤 다시 실행한다.",
                         check.unblock_condition)
        self.assertEqual("장치 연결 후 통신 성공 여부.", check.not_verified)

    def test_all_four_reports_include_common_context(self):
        result = self._result()
        meta = {"command": "python run.py sample",
                "env": {"호스트": "QA-PC", "Viewer 버전": "1.2.3"},
                "checklist": {"TC_SAMPLE": {
                    "steps": "1. 자동 확인 버튼을 누른다.\n2. 실물 장치를 연결한다.",
                    "expected": "1. 상태가 정상으로 표시된다.\n"
                                "2. 장치 통신이 시작된다."}}}
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports([result], directory, "sample", meta=meta)

            with open(paths["json"], encoding="utf-8") as stream:
                payload = json.load(stream)
            self.assertEqual(meta, payload["meta"])
            blocked = payload["results"][0]["checks"][1]
            self.assertEqual("실물 장치를 연결한다.",
                             blocked["step_description"])
            self.assertEqual("장치 통신이 시작된다.",
                             blocked["source_expected_result"])
            self.assertEqual("시험용 장치를 연결한 뒤 다시 실행한다.",
                             blocked["unblock_condition"])
            self.assertEqual("장치 연결 후 통신 성공 여부.",
                             blocked["not_verified"])

            with open(paths["csv"], encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertIn(["# 실행 환경", "호스트", "QA-PC"], rows)
            header = next(row for row in rows if row and row[0] == "TC ID")
            self.assertIn("기준 수행 절차", header)
            self.assertIn("기준 기대 결과", header)
            self.assertIn("해제 조건", header)
            self.assertIn("이 실행으로 말할 수 없는 것", header)

            for kind in ("txt", "html"):
                with open(paths[kind], encoding="utf-8") as stream:
                    text = stream.read()
                self.assertIn("BLOCKED", text)
                self.assertIn("QA-PC", text)
                self.assertIn("python run.py sample", text)
                self.assertIn("장치 연결 후 통신 성공 여부", text)
                self.assertIn("실물 장치를 연결한다", text)
                self.assertIn("장치 통신이 시작된다", text)

            self.assertEqual({"csv", "json", "html", "txt"}, set(paths))
            self.assertTrue(all(os.path.isfile(path) for path in paths.values()))


if __name__ == "__main__":
    unittest.main()
