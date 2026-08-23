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
        # 2026-08-24: `소요시간`(붙여쓰기)을 찾고 있었는데 HTML 은 그 전부터
        # `소요 시간 분해`(띄어쓰기)를 쓰고 있었다. 이 저장소의 유일한 단위
        # 시험이 그동안 실패 상태로 방치돼 있었다(아무도 돌리지 않았다).
        # 문구를 그대로 박는 대신 **HTML 이 실제로 내는 제목**을 확인한다.
        self.assertIn("<h3>소요 시간 분해</h3>", html)
        self.assertIn('"duration_seconds"', json_text)
        self.assertIn('"timings"', json_text)


if __name__ == "__main__":
    unittest.main()
