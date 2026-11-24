"""설치판 기록으로 선택한 범위를 검증한다. 제품 UI/DB는 사용하지 않는다."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys

from tools import release_gate as gate

SHA = "a" * 40


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstalledGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / "BellalunAuto.exe"
        self.exe.write_bytes(b"tested exe")
        self.info = self.root / "build-info.json"
        self.info.write_text(json.dumps({
            "source_commit": SHA, "source_dirty": False,
            "skipped": {"compile": False, "tests": False},
            "application": {"path": self.exe.name, "sha256": digest(self.exe)},
            "files": [{"path": self.exe.name, "size": 10, "sha256": digest(self.exe)}],
        }), encoding="utf-8")
        self.tc = "TC_Basic_WorkFlow_14"
        self.report = self.root / "result.json"
        self.data = {"meta": {"source_commit": SHA, "source_dirty": False,
                              "source_identity_origin": "build-info", "command": "exe run-wf14"},
                     "results": [{"tc_id": self.tc, "verdict": "PASS", "checks": [
                         {"step": 1, "title": "설정 확인", "status": "PASS", "actual": "확인함"}]}]}
        self.record = {"exe": str(self.exe), "build_info": str(self.info),
                       "build_info_sha256": digest(self.info),
                       "install": {"ok": True, "exe_sha256": digest(self.exe)},
                       "selected_commands": ["run-wf14"], "expected_tcs": [self.tc],
                       "finished": "2026-11-05T11:00:00+09:00", "runs": []}

    def evaluate(self, scope="tc", expected_tcs=None):
        self.report.write_text(json.dumps(self.data), encoding="utf-8")
        self.record["runs"] = [{"command": "run-wf14", "completed": True, "exit_code": 0,
                                "started": "2020-01-01T00:00:00+09:00",
                                "report": {"path": str(self.report)},
                                "report_sha256": digest(self.report)}]
        return self.evaluate_record(scope, expected_tcs)

    def evaluate_record(self, scope="tc", expected_tcs=None):
        path = self.root / "verification.json"
        path.write_text(json.dumps(self.record), encoding="utf-8")
        return gate.evaluate_installed(path, SHA, scope,
                                       expected_tcs=[self.tc] if expected_tcs is None else expected_tcs)

    def test_single_tc_accepts_installed_result_without_other_suites(self):
        result = self.evaluate()
        self.assertTrue(result["passed"], result["reasons"])
        self.assertEqual(result["scope"], "tc")
        self.assertEqual(result["exe_sha256"], digest(self.exe))

    def test_development_report_must_match_both_build_versions(self):
        info = json.loads(self.info.read_text(encoding="utf-8"))
        info.update(version="1.0.0.001", windows_version="1.0.0.1")
        self.info.write_text(json.dumps(info), encoding="utf-8")
        self.record["build_info_sha256"] = digest(self.info)
        self.assertFalse(self.evaluate()["passed"])
        self.data["meta"].update(automation_version="1.0.0.001", windows_version="1.0.0.1")
        result = self.evaluate()
        self.assertTrue(result["passed"], result["reasons"])
        self.data["meta"]["windows_version"] = "1.0.0.2"
        self.assertFalse(self.evaluate()["passed"])

    def test_development_report_cannot_fall_back_to_legacy_build_info(self):
        self.data["meta"].update(automation_version="1.0.0.001", windows_version="1.0.0.1")
        self.assertFalse(self.evaluate()["passed"])

    def test_wrong_expected_tc_or_empty_scope_cannot_pass(self):
        self.assertFalse(self.evaluate(expected_tcs=["TC_Basic_WorkFlow_03"])["passed"])
        self.assertFalse(self.evaluate(expected_tcs=[])["passed"])
        self.assertFalse(self.evaluate(scope="both")["passed"])

    def test_single_tc_with_only_skip_verifies_nothing_and_is_rejected(self):
        # 사람 전용 WF16은 SKIP이 허용 판정이라, 단독 범위로는 검증한 것이 없다.
        self.tc = "TC_Basic_WorkFlow_16"
        self.data["meta"]["command"] = "exe run-wf16"
        self.data["results"] = [{"tc_id": self.tc, "verdict": "SKIP", "checks": [
            {"step": 1, "title": "사람이 직접 수행", "status": "SKIP", "actual": "사람 전용"}]}]
        self.record["selected_commands"], self.record["expected_tcs"] = ["run-wf16"], [self.tc]
        self.report.write_text(json.dumps(self.data), encoding="utf-8")
        self.record["runs"] = [{"command": "run-wf16", "completed": True, "exit_code": 0,
                                "started": "2020-01-01T00:00:00+09:00",
                                "report": {"path": str(self.report)},
                                "report_sha256": digest(self.report)}]
        result = self.evaluate_record()
        self.assertFalse(result["passed"])
        self.assertTrue(any("SKIP" in r for r in result["reasons"]), result["reasons"])

    def test_verdict_records_unexecuted_scope(self):
        result = self.evaluate()
        self.assertEqual(result["executed"], ["run-wf14"])
        self.assertIn("run-regression", result["not_executed"])
        self.assertIn("run-winupdate", result["not_executed"])

    def test_unrelated_tc_is_not_accepted_as_selected_single_tc(self):
        self.data["results"].append({"tc_id": "TC_Basic_WorkFlow_03", "verdict": "PASS", "checks": []})
        self.assertFalse(self.evaluate()["passed"])

    def test_source_report_other_commit_and_dirty_are_rejected(self):
        for field, value in (("source_identity_origin", "git"), ("source_commit", "b" * 40),
                             ("source_dirty", True)):
            with self.subTest(field=field):
                old = self.data["meta"][field]
                self.data["meta"][field] = value
                self.assertFalse(self.evaluate()["passed"])
                self.data["meta"][field] = old

    def test_old_wrong_expectation_does_not_bypass_new_failure_gate(self):
        row = self.data["results"][0]
        row["verdict"] = "FAIL"
        row["checks"][0]["status"] = "FAIL"
        self.assertFalse(self.evaluate()["passed"])
        row["checks"][0]["title"] = "Setting > Device > UPS 설정이 Export 시점 값으로 복원"
        self.assertFalse(self.evaluate()["passed"])
        row["verdict"] = "BLOCKED"
        self.assertFalse(self.evaluate()["passed"])

    def test_changed_exe_or_report_is_rejected(self):
        self.assertTrue(self.evaluate()["passed"])
        self.exe.write_bytes(b"other exe!")
        self.assertFalse(self.evaluate_record()["passed"])
        self.exe.write_bytes(b"tested exe")
        self.report.write_text("{}", encoding="utf-8")
        self.assertFalse(self.evaluate_record()["passed"])

    def test_build_with_skipped_validation_is_not_a_release(self):
        info = json.loads(self.info.read_text(encoding="utf-8"))
        info["skipped"]["tests"] = True
        self.info.write_text(json.dumps(info), encoding="utf-8")
        self.record["build_info_sha256"] = digest(self.info)
        self.assertFalse(self.evaluate()["passed"])

    def test_incomplete_run_unknown_verdict_and_fail_without_checks_are_rejected(self):
        self.assertTrue(self.evaluate()["passed"])
        self.record["runs"][0]["completed"] = False
        self.assertFalse(self.evaluate_record()["passed"])
        self.data["results"][0]["verdict"] = "UNKNOWN"
        self.assertFalse(self.evaluate()["passed"])
        self.data["results"][0].update(verdict="FAIL", checks=[])
        self.assertFalse(self.evaluate()["passed"])

    def test_missing_or_stale_report_does_not_pass(self):
        self.assertTrue(self.evaluate()["passed"])
        self.record["runs"][0]["started"] = "2099-01-01T00:00:00+09:00"
        self.assertFalse(self.evaluate_record()["passed"])
        self.report.unlink()
        self.assertFalse(self.evaluate_record()["passed"])

    def gui_full_record(self, command, consent="GUI", status="completed", operator="agent",
                        approval="1~4번 진행하고 기본기능 전체 실행도 승인할게"):
        """REQ-DIST-008: 설치판 GUI에서 동의하고 시작한 전체 회차 기록을 만든다."""
        run_id = "20261124-150000-0123abcd"
        self.data["meta"].update(command=f"exe --run-id {run_id} --workspace C:/w {command} --restore-after --prepared",
                                 execution_mode="live", chain_completed=True, run_id=run_id)
        if command == "run-winupdate":
            ids = [f"TC_WindowsUpdate_{i:02}" for i in range(1, 14)]
        else:
            ids = ["AUTOMATION_ENVIRONMENT_RESET", "DICOM_Server_Setup",
                   "TC_Basic_WorkFlow_14", "TC_XIPL_compatibility_07"]
        self.data["results"] = [{"tc_id": tc, "verdict": "SKIP" if tc in {
            "TC_WindowsUpdate_01", "TC_WindowsUpdate_12", "TC_WindowsUpdate_13"} else "PASS",
            "checks": [{"status": "PASS", "actual": "확인"}]} for tc in ids]
        self.report.write_text(json.dumps(self.data), encoding="utf-8")
        run_json = self.root / f"run-{command}.json"
        run_json.write_text(json.dumps({"run_id": run_id, "action": command, "status": status,
                                        "consent": {"source": consent}}), encoding="utf-8")
        self.record.update(selected_commands=[command], expected_tcs=[],
                           launch={"mode": "gui", "operator": operator, "approval": approval})
        self.record["runs"] = [{"command": command, "completed": True, "exit_code": 0,
            "started": "2020-01-01T00:00:00+09:00", "report": {"path": str(self.report)},
            "report_sha256": digest(self.report),
            "gui": {"run_record": str(run_json), "run_record_sha256": digest(run_json)}}]

    def test_full_scope_accepts_gui_run_with_option_flags_in_command(self):
        """Validates: REQ-DIST-008, REQ-DIST-005 — 옵션으로 끝나는 실제 명령도 실행 이름으로 대조한다."""
        for scope, command in (("wu", "run-winupdate"), ("basic", "run-regression")):
            with self.subTest(scope=scope):
                self.gui_full_record(command)
                result = self.evaluate_record(scope, [])
                self.assertTrue(result["passed"], result["reasons"])

    def test_full_scope_rejects_cli_or_unconsented_gui_records(self):
        """Validates: REQ-DIST-008 — 전체 범위는 화면 동의한 설치판 GUI 회차만 받는다."""
        cases = {
            "CLI 기록": lambda: (self.gui_full_record("run-winupdate"), self.record.pop("launch"),
                               self.record["runs"][0].pop("gui")),
            "CLI 동의": lambda: self.gui_full_record("run-winupdate", consent="화면 동의 없음(CLI)"),
            "미완료": lambda: self.gui_full_record("run-winupdate", status="abnormal"),
            "승인 없음": lambda: self.gui_full_record("run-winupdate", approval=""),
        }
        for name, build in cases.items():
            with self.subTest(name):
                build()
                result = self.evaluate_record("wu", [])
                self.assertFalse(result["passed"])
                self.assertTrue(any("GUI" in reason or "승인" in reason for reason in result["reasons"]),
                                result["reasons"])

    def test_gui_record_changed_after_run_is_rejected(self):
        """Validates: REQ-DIST-008 — 실행 기록 해시가 바뀌면 거부한다."""
        self.gui_full_record("run-winupdate")
        Path(self.record["runs"][0]["gui"]["run_record"]).write_text("{}", encoding="utf-8")
        self.assertFalse(self.evaluate_record("wu", [])["passed"])

    def test_wu_only_and_basic_only_do_not_require_other_suite(self):
        for scope, command in (("wu", "run-winupdate"), ("basic", "run-regression")):
            with self.subTest(scope=scope):
                self.gui_full_record(command)
                self.data["meta"].update(execution_mode="live", chain_completed=True)
                if scope == "wu":
                    ids = [f"TC_WindowsUpdate_{i:02}" for i in range(1, 14)]
                else:
                    ids = ["AUTOMATION_ENVIRONMENT_RESET", "DICOM_Server_Setup",
                           "TC_Basic_WorkFlow_14", "TC_XIPL_compatibility_07"]
                self.data["results"] = [{"tc_id": tc, "verdict": "SKIP" if tc in {
                    "TC_WindowsUpdate_01", "TC_WindowsUpdate_12", "TC_WindowsUpdate_13"} else "PASS",
                    "checks": [{"status": "PASS", "actual": "확인"}]} for tc in ids]
                self.report.write_text(json.dumps(self.data), encoding="utf-8")
                self.record["runs"][0]["report_sha256"] = digest(self.report)
                result = self.evaluate_record(scope, [])
                self.assertTrue(result["passed"], result["reasons"])

    def test_cli_reads_record_and_writes_scoped_verdict_without_product_execution(self):
        root = Path(__file__).resolve().parents[1]
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        self.data["meta"]["source_commit"] = head
        info = json.loads(self.info.read_text(encoding="utf-8"))
        info["source_commit"] = head
        self.info.write_text(json.dumps(info), encoding="utf-8")
        self.record["build_info_sha256"] = digest(self.info)
        self.evaluate()
        output = self.root / "approval.json"
        proc = subprocess.run([sys.executable, str(root / "tools/release_gate.py"),
            "--installed-verification", str(self.root / "verification.json"), "--scope", "tc",
            "--expected-tc", self.tc, "--commit", head, "--output", str(output)],
            cwd=root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        verdict = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(verdict["passed"])
        self.assertEqual(verdict["scope"], "tc")
        self.assertEqual(verdict["exe_sha256"], digest(self.exe))

