"""REQ-REPORT-001: 리포트 첫머리의 결론과 TC별 원인 한 줄(사용자 요청 2026-11-05)."""

import tempfile
import unittest
from pathlib import Path

from core.result import FAIL, MANUAL, PASS, SKIP, TCResult, outcome_summary, write_reports


def tc(tc_id, *checks):
    result = TCResult(tc_id, f"{tc_id} 제목")
    for step, title, status, expected, actual, note in checks:
        result.add(step, title, status, expected, actual, note, stop=False)
    return result


class OutcomeSummaryTests(unittest.TestCase):
    def test_all_pass_says_so_and_lists_no_problem_rows(self):
        summary = outcome_summary([tc("TC_A", (1, "확인", PASS, "a", "a", "근거"))])
        self.assertEqual(summary["level"], "ok")
        self.assertIn("모든 TC가 통과", summary["headline"])
        self.assertEqual(summary["rows"], [])

    def test_new_failure_shows_first_failed_step_expected_actual_and_recorded_reason(self):
        summary = outcome_summary([
            tc("TC_A", (1, "앞 단계", PASS, "x", "x", "ok"),
               (2, "저장 값 확인", FAIL, "10", "3", "DB 값이 바뀌지 않았다. 추가 설명은 뒤에 있다.")),
            tc("TC_B", (1, "확인", PASS, "a", "a", "근거"))])
        self.assertEqual(summary["level"], "bad")
        self.assertIn("실패 TC 1개", summary["headline"])
        row = summary["rows"][0]
        self.assertEqual((row["tc_id"], row["verdict"], row["step"]), ("TC_A", FAIL, "2"))
        self.assertEqual(row["check"], "저장 값 확인")
        self.assertEqual((row["expected"], row["actual"]), ("10", "3"))
        self.assertEqual(row["reason"], "DB 값이 바뀌지 않았다.")
        self.assertFalse(row["known_defect"])

    def test_old_wrong_ups_expectation_is_not_labelled_a_product_defect(self):
        title = "Setting > Device > UPS 설정이 Export 시점 값으로 복원"
        summary = outcome_summary([tc("TC_Basic_WorkFlow_14", (7, title, FAIL, "복원", "None", "UPS 미복원"))])
        self.assertFalse(summary["rows"][0]["known_defect"])
        self.assertEqual(summary["level"], "bad")

    def test_manual_and_skip_need_person_and_keep_their_recorded_reason(self):
        summary = outcome_summary([tc("TC_M", (1, "사람 확인", MANUAL, "-", "-", "기준 자료가 없다")),
                                   tc("TC_S", (1, "사람 전용", SKIP, "-", "-", "사람이 직접 수행"))])
        self.assertEqual(summary["level"], "warn")
        self.assertIn("사람 확인", summary["headline"])
        self.assertEqual([r["reason"] for r in summary["rows"]], ["기준 자료가 없다", "사람이 직접 수행"])

    def test_new_failure_mixed_with_known_defect_is_not_hidden(self):
        """리뷰 지적: 같은 TC의 알려진 결함이 새 실패를 가리면 게이트(거부)와 리포트 결론이 어긋난다."""
        known = "Setting > Device > UPS 설정이 Export 시점 값으로 복원"
        summary = outcome_summary([tc("TC_Basic_WorkFlow_14",
                                      (7, known, FAIL, "복원", "None", "UPS 미복원"),
                                      (9, "새로 깨진 항목", FAIL, "A", "B", "새 원인이다."))])
        row = summary["rows"][0]
        self.assertFalse(row["known_defect"])
        self.assertEqual((row["step"], row["check"], row["reason"]), ("7", known, "UPS 미복원"))
        self.assertEqual(summary["level"], "bad")

    def test_no_results_is_not_success(self):
        summary = outcome_summary([])
        self.assertNotEqual(summary["level"], "ok")
        self.assertIn("결과가 없습니다", summary["headline"])

    def test_empty_note_says_no_recorded_reason(self):
        summary = outcome_summary([tc("TC_A", (1, "확인", FAIL, "a", "b", ""))])
        self.assertEqual(summary["rows"][0]["reason"], "(판정 근거 없음)")

    def test_html_and_text_reports_open_with_the_conclusion(self):
        results = [tc("TC_A", (2, "저장 값 확인", FAIL, "10", "3", "DB 값이 바뀌지 않았다."))]
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_reports(results, tmp, "Summary_test")
            html = Path(paths["html"]).read_text(encoding="utf-8")
            text = Path(paths["txt"]).read_text(encoding="utf-8")
        self.assertLess(html.index("결론 — 한눈에 보기"), html.index("요약 대시보드"))
        self.assertIn("DB 값이 바뀌지 않았다.", html)
        self.assertIn("결론:", text.split("판정 합계")[0] if "판정 합계" in text else text[:800])


if __name__ == "__main__":
    unittest.main()
