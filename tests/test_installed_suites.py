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
from pathlib import Path
import subprocess
import sys

from tools import run_installed_suites as runner


def _wu_rows(verdicts):
    return [{"tc_id": f"TC_WindowsUpdate_{i:02}", "verdict": v}
            for i, v in enumerate(verdicts, start=1)]


class WuTargetTests(unittest.TestCase):
    def test_all_ten_pass_meets_target(self):
        rows = _wu_rows(["SKIP"] + ["PASS"] * 10 + ["SKIP", "SKIP"])
        out = runner.wu_target(rows)
        self.assertTrue(out["met"])
        self.assertEqual([], out["not_pass"])

    def test_one_fail_misses_target_and_names_it(self):
        rows = _wu_rows(["SKIP"] + ["PASS"] * 8 + ["FAIL", "PASS"] + ["SKIP"] * 2)
        out = runner.wu_target(rows)
        self.assertFalse(out["met"])
        self.assertEqual([("TC_WindowsUpdate_10", "FAIL")], out["not_pass"])

    def test_missing_row_is_not_a_pass(self):
        rows = _wu_rows(["SKIP"] + ["PASS"] * 9)          # WU_11~13 없음
        out = runner.wu_target(rows)
        self.assertFalse(out["met"])
        self.assertIn(("TC_WindowsUpdate_11", "MISSING"), out["not_pass"])

    def test_human_only_tc_must_be_skip_like_release_gate(self):
        # 2026-11-05 부터 사람 전용 TC 는 SKIP 이다(REQ-VERDICT-002). MANUAL 이면 목표 미달.
        rows = _wu_rows(["MANUAL"] + ["PASS"] * 10 + ["SKIP", "SKIP"])
        out = runner.wu_target(rows)
        self.assertFalse(out["met"])
        self.assertIn(("TC_WindowsUpdate_01", "MANUAL"), out["not_pass"])

    def test_skip_is_not_accepted_as_pass(self):
        rows = _wu_rows(["SKIP"] + ["PASS"] * 8 + ["SKIP", "PASS"] + ["SKIP"] * 2)
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


class SelectedScopeTests(unittest.TestCase):
    def test_cli_requires_scope_before_creating_output_or_reading_install(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "output"
            script = Path(__file__).resolve().parents[1] / "tools/run_installed_suites.py"
            proc = subprocess.run([sys.executable, str(script), "--exe", "missing.exe",
                "--build-info", "missing.json", "--workspace", folder, "--out", str(out)],
                capture_output=True)
            self.assertEqual(proc.returncode, 2)
            self.assertFalse(out.exists())

    def test_cli_help_is_utf8_with_ascii_stdout_environment(self):
        script = Path(__file__).resolve().parents[1] / "tools/run_installed_suites.py"
        proc = subprocess.run([sys.executable, str(script), "--help"],
            env={**os.environ, "PYTHONIOENCODING": "ascii"}, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("승인받은", proc.stdout.decode("utf-8"))

    def test_single_tc_report_is_found_and_unrelated_report_ignored(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Result_single.json"
            report = {"meta": {"command": "exe run-wf14"}, "results": [
                {"tc_id": "TC_Basic_WorkFlow_14", "verdict": "PASS"}]}
            path.write_text(json.dumps(report), encoding="utf-8")
            found = runner.selected_report(folder, "run-wf14", 0, ["TC_Basic_WorkFlow_14"])
            self.assertEqual(found["path"], str(path))
            self.assertIsNone(runner.selected_report(folder, "run-wf03", 0,
                                                     ["TC_Basic_WorkFlow_03"]))

    def test_scope_must_be_explicit_and_invalid_choices_never_start_product(self):
        for commands, expected in (("", []), ("reset-environment", []),
                                   ("run-wf14", []), ("run-wf14,run-winupdate", ["TC_Basic_WorkFlow_14"]),
                                   ("run-wf14", ["TC_Basic_WorkFlow_03"])):
            with self.subTest(commands=commands), self.assertRaises(ValueError):
                runner.validate_selection(commands, expected)
        self.assertEqual(runner.validate_selection("run-winupdate", []), ["run-winupdate"])
        self.assertEqual(runner.validate_selection("run-wf14", ["TC_Basic_WorkFlow_14"]), ["run-wf14"])


class CleanEnvironmentTests(unittest.TestCase):
    """개발 도구 없는 PC를 흉내 내는 최소 환경(`--clean-env`)."""

    BASE = {"SystemRoot": r"C:\WINDOWS", "windir": r"C:\WINDOWS", "TEMP": r"C:\T",
            "USERPROFILE": r"C:\Users\u", "COMPUTERNAME": "PC",
            "PATH": r"C:\Python312;C:\Program Files\Git\cmd;C:\WINDOWS\system32",
            "PYTHONPATH": r"C:\src", "VIRTUAL_ENV": r"C:\venv", "GIT_DIR": r"C:\g",
            "NODE_PATH": r"C:\n", "CONDA_PREFIX": r"C:\c"}

    def test_path_is_windows_default_only(self):
        env = runner.clean_environment(self.BASE)
        parts = env["PATH"].split(";")
        self.assertIn(r"C:\WINDOWS\system32", parts)
        self.assertIn(r"C:\WINDOWS\System32\WindowsPowerShell\v1.0", parts)
        self.assertFalse(any("Python" in p or "Git" in p for p in parts), parts)

    def test_developer_variables_are_dropped_and_python_vars_poisoned(self):
        env = runner.clean_environment(self.BASE)
        for key in ("VIRTUAL_ENV", "GIT_DIR", "NODE_PATH", "CONDA_PREFIX"):
            self.assertNotIn(key, env)
        self.assertTrue(env["PYTHONHOME"].startswith(runner.POISON_DIR))
        self.assertTrue(env["PYTHONPATH"].startswith(runner.POISON_DIR))
        self.assertEqual(r"C:\Users\u", env["USERPROFILE"])
        self.assertEqual("PC", env["COMPUTERNAME"])


if __name__ == "__main__":
    unittest.main()
