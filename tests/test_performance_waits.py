import tempfile
import unittest
from pathlib import Path

from core.result import PASS, TCResult, write_reports
from tests.xipl_flows import _poll_completion


class PerformanceWaitTests(unittest.TestCase):
    def test_poll_completion_records_early_success(self):
        result = TCResult("TC_TEST", "timing")
        calls = {"count": 0}

        def predicate():
            calls["count"] += 1
            done = calls["count"] == 2
            return done, "DB condition satisfied", {"calls": calls["count"]}

        detail = _poll_completion(result, "DB row", predicate, timeout=1, poll=.001)
        self.assertEqual(2, detail["calls"])
        self.assertEqual("DB condition satisfied", result.timings[-1]["outcome"])
        self.assertLess(result.timings[-1]["duration_seconds"], 1)

    def test_report_keeps_checks_and_adds_timing_metadata(self):
        result = TCResult("TC_TEST", "compatible report")
        result.add(1, "existing check", PASS, expected="yes", actual="yes")
        result.finalize()
        with tempfile.TemporaryDirectory() as directory:
            paths = write_reports([result], directory, "timing")
            html = Path(paths["html"]).read_text(encoding="utf-8")
            json_text = Path(paths["json"]).read_text(encoding="utf-8")
        self.assertIn("existing check", html)
        # 2026-09-08 사용자 요청: Step 단위 소요시간은 항상 0초에 가깝게
        # 찍혀 쓸모가 없었다 — `TCResult.add()`가 더 이상 재지 않고
        # (`core/result.py`), 리포트도 "소요 시간 분해" 접이식 섹션을
        # 아예 내지 않는다. TC 전체 소요시간은 TC 헤더의 "소요 Ns"로
        # 여전히 나온다(위 `<div class='meta'>` 검증은 별도 테스트가
        # 없으므로 여기서는 섹션이 사라졌다는 것만 지킨다).
        self.assertNotIn("소요 시간 분해", html)
        self.assertIn('"duration_seconds"', json_text)
        self.assertIn('"timings"', json_text)


if __name__ == "__main__":
    unittest.main()
