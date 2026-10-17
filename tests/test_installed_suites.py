# -*- coding: utf-8 -*-
"""`tools/run_installed_suites.py` 의 판정 부분을 고정한다.

이 도구는 설치판 EXE 로 기본기능 전체와 실시간 WU 전체를 차례로 실행하고,
결과가 실제 새 전체 실행인지와 WU 목표(기존 수동 3건 외 10건 PASS)를 따진다.
제품을 조작하는 실행 부분은 실제 설치판 실행으로만 검증한다.
"""
import hashlib
import json
import os
import tempfile
import unittest

from tools import run_installed_suites as runner


def _wu_rows(verdicts):
    return [{"tc_id": f"TC_WindowsUpdate_{i:02}", "verdict": v}
            for i, v in enumerate(verdicts, start=1)]


class WuTargetTests(unittest.TestCase):
    def test_all_ten_pass_meets_target(self):
        rows = _wu_rows(["MANUAL"] + ["PASS"] * 10 + ["MANUAL", "MANUAL"])
        out = runner.wu_target(rows)
        self.assertTrue(out["met"])
        self.assertEqual([], out["not_pass"])

    def test_one_fail_misses_target_and_names_it(self):
        rows = _wu_rows(["MANUAL"] + ["PASS"] * 8 + ["FAIL", "PASS"] + ["MANUAL"] * 2)
        out = runner.wu_target(rows)
        self.assertFalse(out["met"])
        self.assertEqual([("TC_WindowsUpdate_10", "FAIL")], out["not_pass"])

    def test_missing_row_is_not_a_pass(self):
        rows = _wu_rows(["MANUAL"] + ["PASS"] * 9)          # WU_11~13 없음
        out = runner.wu_target(rows)
        self.assertFalse(out["met"])
        self.assertIn(("TC_WindowsUpdate_11", "MISSING"), out["not_pass"])

    def test_skip_is_not_accepted_as_pass(self):
        rows = _wu_rows(["MANUAL"] + ["PASS"] * 8 + ["SKIP", "PASS"] + ["MANUAL"] * 2)
        self.assertFalse(runner.wu_target(rows)["met"])


class VerifyInstallTests(unittest.TestCase):
    def test_matching_files_pass_and_changed_file_is_reported(self):
        with tempfile.TemporaryDirectory() as root:
            exe = os.path.join(root, "BellalunAuto.exe")
            with open(exe, "wb") as fh:
                fh.write(b"exe")
            with open(os.path.join(root, "a.dll"), "wb") as fh:
                fh.write(b"dll")
            sha = lambda b: hashlib.sha256(b).hexdigest()
            info = {"application": {"path": "BellalunAuto.exe", "sha256": sha(b"exe")},
                    "files": [{"path": "BellalunAuto.exe", "size": 3, "sha256": sha(b"exe")},
                              {"path": "a.dll", "size": 3, "sha256": sha(b"dll")}]}
            path = os.path.join(root, "build-info.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(info, fh)
            ok = runner.verify_install(exe, path)
            self.assertTrue(ok["ok"], ok)
            with open(os.path.join(root, "a.dll"), "wb") as fh:
                fh.write(b"DLL")
            bad = runner.verify_install(exe, path)
            self.assertFalse(bad["ok"])
            self.assertEqual(["a.dll"], [m["path"] for m in bad["mismatched"]])


class SnapshotTests(unittest.TestCase):
    def test_only_files_changed_since_start_are_copied_and_hashed(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as dst:
            os.makedirs(os.path.join(ws, "Reports"))
            old = os.path.join(ws, "Reports", "old.json")
            new = os.path.join(ws, "Reports", "new.json")
            for p in (old, new):
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(p)
            os.utime(old, (1000, 1000))
            out = runner.snapshot(ws, 2000, dst)
            self.assertEqual(["Reports/new.json"], [f["path"] for f in out["files"]])
            self.assertTrue(out["verified"])
            self.assertTrue(os.path.isfile(os.path.join(dst, "Reports", "new.json")))


if __name__ == "__main__":
    unittest.main()
