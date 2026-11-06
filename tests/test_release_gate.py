"""릴리스 게이트 판정과 배포 빌드 후보 표시. Viewer/DB/빌드 도구를 실행하지 않는다."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
KNOWN = ("TC_Basic_WorkFlow_14", "Setting > Device > UPS 설정이 Export 시점 값으로 복원")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load("release_gate_under_test", "tools/release_gate.py")


def _check(step, title, status, actual="확인함"):
    return {"step": step, "title": title, "status": status, "expected": "기대",
            "actual": actual, "note": ""}


def _tc(tc_id, verdict, checks=None):
    return {"tc_id": tc_id, "verdict": verdict,
            "checks": checks if checks is not None else [_check(1, "확인", verdict)]}


def _identity(commit=SHA, dirty=False):
    return {"source_commit": commit, "source_dirty": dirty, "source_identity_origin": "git"}


def wu_report(**meta):
    rows = [_tc(tc, "SKIP" if tc in gate.WU_HUMAN_ONLY else "PASS") for tc in gate.WU_IDS]
    base = {"execution_mode": "live", "chain_completed": True, **_identity()}
    base.update(meta)
    return {"meta": base, "results": rows}


def basic_report(extra=None, **meta):
    rows = [_tc(tc, "PASS") for tc in sorted(gate.FULL_REGRESSION_MARKERS)]
    rows.append(_tc("TC_Basic_Install_01", "MANUAL"))
    rows.extend(extra or [])
    base = _identity()
    base.update(meta)
    return {"meta": base, "results": rows}


def wf14_known_defect(extra_checks=()):
    return _tc("TC_Basic_WorkFlow_14", "FAIL", [
        _check(6, "앞 단계", "PASS"),
        _check(7, KNOWN[1], "FAIL", "UPS 값 다름"),
        _check(0, "TC_Basic_WorkFlow_14 실행", "FAIL",
               "StepFailed: Step 7 FAIL — 이후 Step 을 수행하지 않고 이 TC 를 중단합니다: x"),
        _check(8, "Step 8 미수행", "FAIL", gate.PAD_ACTUAL),
        *extra_checks])


class EvaluateTests(unittest.TestCase):
    def _run(self, wu=None, basic=None, commit=SHA, **kw):
        return gate.evaluate(wu if wu is not None else wu_report(),
                             basic if basic is not None else basic_report(), commit, **kw)

    def test_clean_reports_from_expected_commit_pass(self):
        result = self._run()
        self.assertTrue(result["passed"], result["reasons"])
        self.assertEqual(result["reasons"], [])

    def test_missing_identity_is_rejected_with_reason(self):
        wu = wu_report()
        for key in ("source_commit", "source_dirty", "source_identity_origin"):
            wu["meta"].pop(key)
        result = self._run(wu=wu)
        self.assertFalse(result["passed"])
        self.assertTrue(any("source_commit 이 없어" in r for r in result["reasons"]))

    def test_other_commit_and_dirty_source_are_rejected(self):
        self.assertFalse(self._run(basic=basic_report(source_commit="b" * 40))["passed"])
        result = self._run(wu=wu_report(source_dirty=True))
        self.assertTrue(any("커밋되지 않은 변경" in r for r in result["reasons"]))
        self.assertFalse(self._run(wu=wu_report(source_dirty=None))["passed"])
        self.assertFalse(self._run(commit="")["passed"])

    def test_missing_report_is_rejected(self):
        result = gate.evaluate(None, basic_report(), SHA)
        self.assertFalse(result["passed"])
        self.assertTrue(any("WU 리포트 존재" in r for r in result["reasons"]))

    def test_wu_must_be_live_complete_chain(self):
        self.assertFalse(self._run(wu=wu_report(execution_mode="historical"))["passed"])
        self.assertFalse(self._run(wu=wu_report(chain_completed=False))["passed"])
        self.assertFalse(self._run(wu=wu_report(chain_completed="true"))["passed"])

    def test_wu_requires_exactly_13_tcs_and_pass10_skip3(self):
        wu = wu_report()
        wu["results"].pop()
        self.assertFalse(self._run(wu=wu)["passed"])
        wu = wu_report()
        wu["results"][1]["verdict"] = "MANUAL"     # WU_02 가 수동이 되면 목표 미달
        result = self._run(wu=wu)
        self.assertTrue(any("WU 목표 판정" in r for r in result["reasons"]))
        wu = wu_report()
        wu["results"][0]["verdict"] = "PASS"       # WU_01 은 사람 전용 SKIP 이어야 한다
        self.assertFalse(self._run(wu=wu)["passed"])
        wu = wu_report()
        wu["results"][0]["verdict"] = "MANUAL"     # 사람 전용 TC 는 2026-11-05 부터 SKIP
        self.assertFalse(self._run(wu=wu)["passed"])
        wu = wu_report()
        wu["results"][8]["verdict"] = "SKIP"       # 사람 전용 밖의 SKIP 은 목표 미달
        self.assertFalse(self._run(wu=wu)["passed"])
        wu = wu_report()
        wu["results"][4]["verdict"] = "FAIL"
        self.assertFalse(self._run(wu=wu)["passed"])

    def test_basic_skip_only_for_human_only_tcs_and_reported(self):
        ok = self._run(basic=basic_report([_tc("TC_Basic_WorkFlow_16", "SKIP")]))
        self.assertTrue(ok["passed"], ok["reasons"])
        listed = [c for c in ok["checks"] if "SKIP" in c["name"]]
        self.assertTrue(listed and "TC_Basic_WorkFlow_16" in listed[0]["detail"])
        bad = self._run(basic=basic_report([_tc("TC_Basic_WorkFlow_07", "SKIP")]))
        self.assertFalse(bad["passed"])
        self.assertTrue(any("TC_Basic_WorkFlow_07" in r for r in bad["reasons"]))

    def test_single_tc_basic_report_is_not_full_regression(self):
        single = {"meta": _identity(), "results": [_tc("TC_Basic_WorkFlow_03", "PASS")]}
        result = self._run(basic=single)
        self.assertTrue(any("전체 회귀가 아닙니다" in r for r in result["reasons"]))

    def test_known_defect_with_stepfailed_and_padding_is_tolerated_and_reported(self):
        result = self._run(basic=basic_report([wf14_known_defect()]))
        self.assertTrue(result["passed"], result["reasons"])
        details = {c["name"]: c["detail"] for c in result["checks"]}
        self.assertIn(KNOWN[1], details["허용된 알려진 결함"])
        self.assertIn("Step 8 미수행", details["알려진 결함 중단으로 미검증된 Step"])

    def test_unknown_fail_rejects_whole_tc_including_cascade_rows(self):
        tc = wf14_known_defect([_check(9, "다른 결함", "FAIL", "값 다름")])
        result = self._run(basic=basic_report([tc]))
        self.assertFalse(result["passed"])
        self.assertTrue(any("다른 결함" in r and "Step 8 미수행" in r for r in result["reasons"]))

    def test_cascade_rows_without_known_defect_are_rejected(self):
        tc = _tc("TC_Basic_WorkFlow_05", "FAIL", [
            _check(0, "실행", "FAIL", "StepFailed: Step 2 FAIL — x"),
            _check(3, "Step 3 미수행", "FAIL", gate.PAD_ACTUAL)])
        self.assertFalse(self._run(basic=basic_report([tc]))["passed"])

    def test_exception_abort_on_known_defect_tc_is_real_failure(self):
        tc = wf14_known_defect([_check(0, "정리", "FAIL", "KeyError: 'x'")])
        self.assertFalse(self._run(basic=basic_report([tc]))["passed"])

    def test_known_defect_key_is_tc_specific(self):
        tc = _tc("TC_Basic_WorkFlow_13", "FAIL", [_check(7, KNOWN[1], "FAIL", "UPS")])
        self.assertFalse(self._run(basic=basic_report([tc]))["passed"])
        self.assertTrue(self._run(basic=basic_report([tc]),
                                  known_defects={("TC_Basic_WorkFlow_13", KNOWN[1])})["passed"])

    def test_any_blocked_rejects(self):
        tc = _tc("TC_Basic_WorkFlow_09", "BLOCKED", [_check(1, "선행 환경", "BLOCKED", "없음")])
        result = self._run(basic=basic_report([tc]))
        self.assertTrue(any("BLOCKED" in r for r in result["reasons"]))

    def test_language_check_is_optional_and_flags_empty_actual_and_placeholders(self):
        basic = basic_report([wf14_known_defect()])
        basic["results"][-1]["checks"][1]["actual"] = "None"
        basic["results"][0]["checks"][0]["note"] = "값 {value} 확인"
        self.assertTrue(self._run(basic=basic)["passed"])
        result = self._run(basic=basic, language=True)
        self.assertFalse(result["passed"])
        problems = [r for r in result["reasons"] if "문장 점검" in r][0]
        self.assertIn("실제값이 비어", problems)
        self.assertIn("미치환", problems)

    def test_language_check_does_not_treat_dict_repr_as_placeholder(self):
        report = {"results": [_tc("X", "FAIL", [_check(1, "t", "FAIL", "{'a': 1}")])]}
        self.assertEqual(gate.check_report_language(report), [])


class IdentityTests(unittest.TestCase):
    def test_git_identity_in_repository(self):
        identity = gate.source_identity(ROOT)
        self.assertEqual(identity["source_identity_origin"], "git")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        self.assertEqual(identity["source_commit"], head)
        self.assertIsInstance(identity["source_dirty"], bool)

    def test_installed_identity_reads_build_info_next_to_exe(self):
        with tempfile.TemporaryDirectory(prefix="설치 폴더 ") as temp:
            folder = Path(temp)
            (folder / "build-info.json").write_text(json.dumps(
                {"source_commit": SHA, "source_dirty": False}), encoding="utf-8")
            identity = gate.source_identity(folder / "resources", executable=folder / "BellalunAuto.exe")
            self.assertEqual(identity, {"source_commit": SHA, "source_dirty": False,
                                        "source_identity_origin": "build-info"})

    def test_installed_exe_build_info_wins_over_git_workspace(self):
        # 설치판을 저장소 checkout 작업 폴더에서 돌려도 EXE 의 빌드 커밋을 기록한다.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "build-info.json").write_text(json.dumps(
                {"source_commit": SHA, "source_dirty": False}), encoding="utf-8")
            identity = gate.source_identity(ROOT, executable=folder / "BellalunAuto.exe")
        self.assertEqual(identity["source_identity_origin"], "build-info")
        self.assertEqual(identity["source_commit"], SHA)

    def test_unknown_identity_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as temp:
            identity = gate.source_identity(temp, executable=Path(temp) / "x.exe")
        self.assertIsNone(identity["source_commit"])
        self.assertEqual(identity["source_identity_origin"], "unknown")

    def test_commit_changed_during_run_is_reported_dirty(self):
        # 실행 도중 HEAD 가 바뀌면 리포트 시점 커밋만 보고 깨끗하다고 하면 안 된다.
        from core.source_identity import combine_run_identity
        start, end = _identity(SHA), _identity("b" * 40)
        merged = combine_run_identity(start, end)
        self.assertEqual(merged["source_commit"], "b" * 40)
        self.assertEqual(merged["source_commit_at_start"], SHA)
        self.assertIs(merged["source_dirty"], True)
        self.assertFalse(gate.evaluate(wu_report(**merged), basic_report(), "b" * 40)["passed"])

    def test_dirty_at_start_stays_dirty_and_unchanged_run_keeps_end_identity(self):
        from core.source_identity import combine_run_identity
        self.assertIs(combine_run_identity(_identity(dirty=True), _identity())["source_dirty"], True)
        same = combine_run_identity(_identity(), _identity())
        self.assertEqual(same, {**_identity(), "source_commit_at_start": SHA})
        self.assertEqual(combine_run_identity(None, _identity()), _identity())

    def test_report_meta_uses_identity_captured_at_run_start(self):
        import run
        ctx = type("Ctx", (), {"root": str(ROOT),
                               "source_identity_at_start": _identity("c" * 40)})()
        meta = run._source_identity_meta(ctx)
        self.assertEqual(meta["source_commit_at_start"], "c" * 40)
        self.assertIs(meta["source_dirty"], True)


class CliTests(unittest.TestCase):
    def _write(self, folder, name, data):
        path = Path(folder) / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def test_cli_exit_codes_and_korean_verdict(self):
        with tempfile.TemporaryDirectory(prefix="게이트 ") as temp:
            wu = self._write(temp, "wu.json", wu_report())
            basic = self._write(temp, "basic.json", basic_report())
            with patch.object(gate, "resolve_commit", return_value=SHA), \
                    patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(gate.main(["--wu", wu, "--basic", basic, "--commit", "aaaaaaa"]), 0)
            self.assertIn("릴리스 게이트 통과", out.getvalue())
            bad = self._write(temp, "bad.json", wu_report(chain_completed=False))
            with patch.object(gate, "resolve_commit", return_value=SHA), \
                    patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(gate.main(["--wu", bad, "--basic", basic, "--commit-from-git"]), 1)
            self.assertIn("릴리스 게이트 거부", out.getvalue())

    def test_resolve_commit_expands_head(self):
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        self.assertEqual(gate.resolve_commit(head[:7]), head)
        with self.assertRaises(ValueError):
            gate.resolve_commit("존재하지않는참조")


class BuildIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.builder = _load("distribution_builder_gate", "tools/build_distribution.py")
        self.temp = tempfile.TemporaryDirectory(prefix="빌드 게이트 ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def _paths(self, wu=None):
        wu_path = self.home / "wu.json"
        basic_path = self.home / "basic.json"
        wu_path.write_text(json.dumps(wu or wu_report(), ensure_ascii=False), encoding="utf-8")
        basic_path.write_text(json.dumps(basic_report(), ensure_ascii=False), encoding="utf-8")
        return wu_path, basic_path

    def test_without_gate_inputs_build_is_candidate(self):
        result = self.builder._release_gate().gate_for_build(None, None, SHA, False)
        self.assertEqual(result["status"], "candidate")
        self.assertEqual(result["label"], "게이트 미통과 후보")
        self.assertEqual(self.builder.installer_filename("1.0.0", result),
                         "BellalunAuto-1.0.0-candidate-setup.exe")
        marker = self.builder.write_candidate_marker(self.home, result)
        self.assertIn("게이트 입력", marker.read_text(encoding="utf-8"))

    def test_passing_gate_keeps_formal_names_and_writes_no_marker(self):
        result = self.builder._release_gate().gate_for_build(*self._paths(), SHA, False)
        self.assertTrue(result["passed"], result["reasons"])
        self.assertEqual(self.builder.installer_filename("1.0.0", result),
                         "BellalunAuto-1.0.0-setup.exe")
        self.assertIsNone(self.builder.write_candidate_marker(self.home, result))
        self.assertFalse((self.home / self.builder.CANDIDATE_MARKER).exists())

    def test_dirty_build_source_or_failed_reports_make_candidate(self):
        lib = self.builder._release_gate()
        self.assertEqual(lib.gate_for_build(*self._paths(), SHA, True)["status"], "candidate")
        failed = lib.gate_for_build(*self._paths(wu_report(execution_mode="historical")), SHA, False)
        self.assertEqual(failed["status"], "candidate")
        self.assertTrue(failed["reasons"])

    def test_cli_accepts_gate_arguments(self):
        with patch.object(self.builder, "build", return_value=0) as build:
            self.assertEqual(self.builder.main(["--assets", "a", "--output", "o", "--iscc", "i",
                                                "--gate-wu", "w.json", "--gate-basic", "b.json"]), 0)
        args = build.call_args[0][0]
        self.assertEqual((args.gate_wu, args.gate_basic), (Path("w.json"), Path("b.json")))


if __name__ == "__main__":
    unittest.main()
