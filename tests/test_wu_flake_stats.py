# -*- coding: utf-8 -*-
"""회차별 판정 분포 도구: 옛 스키마·읽기 실패·갈린 단계 계산."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "tools"))
_cwd = os.getcwd()
try:
    import wu_flake_stats as stats  # noqa: E402  (_paths 없이 단독 import 된다)
finally:
    os.chdir(_cwd)


def _write(folder, name, data):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as stream:
        if isinstance(data, str):
            stream.write(data)
        else:
            json.dump(data, stream, ensure_ascii=False)
    return path


def _run(verdict, step_status, extra=None):
    checks = [{"step": 1, "title": "Setting 전 메뉴 정상 오픈", "status": step_status},
              {"step": 2, "title": "탭 빠른 클릭", "status": "PASS"}]
    rows = [{"tc_id": "TC_WindowsUpdate_10", "title": "Setting", "verdict": verdict,
             "checks": checks}]
    if extra:
        rows.append(extra)
    return {"generated": "2026-09-08T17:00:00", "meta": {}, "results": rows}


class FlakeStatsTests(unittest.TestCase):
    def make(self, folder):
        _write(folder, "Result_WindowsUpdate_20260907_100000.json", _run("PASS", "PASS"))
        _write(folder, "Result_WindowsUpdate_20260908_100000.json", _run("FAIL", "FAIL"))
        # 옛 스키마: meta·generated 없음, checks 키 일부만.
        _write(folder, "Result_20260801_100000.json", {"results": [
            {"tc_id": "TC_Basic_WorkFlow_14", "verdict": "PASS",
             "checks": [{"step": 7, "title": "복원", "status": "PASS"}]},
            {"tc_id": "TC_NoChecks"}]})
        _write(folder, "Result_20260802_100000.json", {"results": [
            {"tc_id": "TC_Basic_WorkFlow_14", "verdict": "FAIL",
             "checks": [{"step": 7, "title": "복원", "status": "FAIL"},
                        {"step": 7, "title": "복원", "status": "PASS"}]}]})
        _write(folder, "Result_20260803_100000.json", "{broken")
        _write(folder, "Result_20260804_100000.json", {"no": "results"})

    def test_divergence_and_unreadable(self):
        with tempfile.TemporaryDirectory() as folder:
            self.make(folder)
            runs, bad = stats.load_runs(stats.expand_inputs([folder]))
            report = stats.analyze(runs)
        self.assertEqual(report["runs"], 4)
        self.assertEqual(len(bad), 2)
        steps = {(s["tc_id"], s["step"]): dict(s["statuses"])
                 for s in report["divergent_steps"]}
        self.assertEqual(steps[("TC_WindowsUpdate_10", 1)], {"PASS": 1, "FAIL": 1})
        # 같은 회차의 중복 키는 한 번만, 더 나쁜 상태로 센다.
        self.assertEqual(steps[("TC_Basic_WorkFlow_14", 7)], {"PASS": 1, "FAIL": 1})
        self.assertNotIn(("TC_WindowsUpdate_10", 2), steps)
        tcs = {t["tc_id"] for t in report["divergent_tcs"]}
        self.assertEqual(tcs, {"TC_WindowsUpdate_10", "TC_Basic_WorkFlow_14"})

    def test_glob_tc_filter_and_since(self):
        with tempfile.TemporaryDirectory() as folder:
            self.make(folder)
            paths = stats.expand_inputs([os.path.join(folder, "Result_WindowsUpdate_*.json"),
                                         os.path.join(folder, "Result_WindowsUpdate_*.json")])
            self.assertEqual(len(paths), 2)
            runs, _ = stats.load_runs(stats.expand_inputs([folder]))
            self.assertEqual(len(stats._filter_since(runs, "2026-08-02")), 3)
            report = stats.analyze(runs, tc_filter=["TC_Basic"])
        self.assertEqual({s["tc_id"] for s in report["steps"]}, {"TC_Basic_WorkFlow_14"})

    def test_text_and_json_output(self):
        with tempfile.TemporaryDirectory() as folder:
            self.make(folder)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(stats.main([folder]), 0)
            text = buf.getvalue()
            self.assertIn("판정이 갈린 단계", text)
            self.assertIn("건너뛴 파일] 2개", text)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                stats.main([folder, "--json"])
            data = json.loads(buf.getvalue())
        self.assertEqual(data["runs"], 4)
        self.assertEqual(len(data["unreadable"]), 2)
        self.assertTrue(any(s["step"] == 1 for s in data["divergent_steps"]))


if __name__ == "__main__":
    unittest.main()
