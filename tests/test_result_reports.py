# -*- coding: utf-8 -*-
import csv
import json
import os
import tempfile
import unittest

from core.result import BLOCKED, PASS, TCResult, write_reports


class ResultReportTests(unittest.TestCase):
    def test_common_layout_filters_and_unique_repeated_tc_details(self):
        results = [TCResult('TC_REPEAT', '반복 시험'), TCResult('TC_REPEAT', '반복 시험')]
        for result in results:
            result.add(1, '검증', PASS, 0, {'value': False})
            result.finalize()
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports(results, directory, 'layout')
            with open(paths['html'], encoding='utf-8') as stream:
                text = stream.read()
        self.assertIn('report-layout-version', text)
        self.assertIn('id="report-search"', text)
        self.assertIn('id="TC_REPEAT"', text)
        self.assertIn('id="TC_REPEAT-2"', text)
        self.assertIn('PASS 검증 1개', text)
        self.assertIn('False', text)

    def test_repeated_tc_failure_links_target_the_failed_instance(self):
        passed, failed = TCResult('TC_REPEAT', '첫 시험'), TCResult('TC_REPEAT', '둘째 시험')
        passed.add(1, '확인', PASS, 1, 1)
        failed.add(1, '확인', 'FAIL', 1, 0, stop=False)
        for result in (passed, failed):
            result.finalize()
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports([passed, failed], directory, 'repeat')
            with open(paths['html'], encoding='utf-8') as stream:
                text = stream.read()
        self.assertGreaterEqual(text.count("href='#TC_REPEAT-2'>TC_REPEAT</a>"), 3)
        self.assertIn('class="failure-card"', text)

    def test_execution_window_overrides_wu_aggregation_times(self):
        result = self._result()
        meta = {'execution_mode': 'live', 'report_title': 'WU',
                'execution': {'started': '2026-11-06T13:55:49',
                              'completed': '2026-11-06T15:47:26'}}
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports([result], directory, 'timing', meta=meta)
            with open(paths['html'], encoding='utf-8') as stream:
                text = stream.read()
        self.assertIn('111.6', text)
        self.assertIn('2026-11-06 13:55:49', text)
        self.assertIn('2026-11-06 15:47:26', text)

    def test_invalid_execution_window_is_not_claimed_as_total(self):
        for end in ('not-a-time', '2026-11-06T13:00:00'):
            with self.subTest(end=end), tempfile.TemporaryDirectory() as directory:
                paths = write_reports([self._result()], directory, 'invalid', meta={
                    'execution': {'started': '2026-11-06T14:00:00', 'completed': end}})
                with open(paths['html'], encoding='utf-8') as stream:
                    self.assertIn('전체 실행 시간 미기록', stream.read())

    def test_overlapping_tc_durations_are_not_added_twice(self):
        from datetime import datetime
        results = [self._result(), self._result()]
        for result in results:
            result.started = datetime(2026, 11, 6, 14, 0)
            result.completed = datetime(2026, 11, 6, 14, 20)
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports(results, directory, 'overlap')
            with open(paths['html'], encoding='utf-8') as stream:
                text = stream.read()
        self.assertIn("class='n'>20.0<span", text)
        self.assertNotIn("class='n'>40.0<span", text)

    def test_old_wu_without_execution_window_does_not_claim_total_time(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports([self._result()], directory, 'old',
                                  meta={'execution_mode': 'historical'})
            with open(paths['html'], encoding='utf-8') as stream:
                text = stream.read()
        self.assertIn('전체 실행 시간 미기록', text)

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
