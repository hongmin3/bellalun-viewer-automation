"""tools/wu_selfcheck.py — WU 매핑·예외 경로 PASS·공유 ctypes 정적 검사 회귀 시험."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

from tools import wu_selfcheck as sc


ROOT = Path(__file__).resolve().parents[1]


def _repo_inputs():
    source = (ROOT / sc.WU_SOURCE).read_text(encoding="utf-8")
    scope = json.loads((ROOT / sc.SCOPE_PATH).read_text(encoding="utf-8"))
    trace = json.loads((ROOT / sc.TRACE_PATH).read_text(encoding="utf-8"))
    return source, scope, trace


def _row(rows, tc_id):
    return next(r for r in rows if r["tc_id"] == tc_id)


class MappingCheckTests(unittest.TestCase):
    def setUp(self):
        self.source, self.scope, self.trace = _repo_inputs()

    def check(self, source=None, scope=None, trace=None):
        return sc.check_mapping(source or self.source,
                                self.scope if scope is None else scope,
                                self.trace if trace is None else trace)

    def test_current_repo_passes(self):
        self.assertEqual(sc.repo_mapping_problems(), [])

    def test_repo_lists_thirteen_wu_entries_in_both_files(self):
        for rows in (self.scope, self.trace["tc"]):
            wu = [r for r in rows if r.get("checklist") == sc.WU_CHECKLIST]
            self.assertEqual(len(wu), 13)

    def test_missing_reused_tc_in_json_is_detected(self):
        scope = copy.deepcopy(self.scope)
        row = _row(scope, "TC_WindowsUpdate_06")
        row["reuses"] = [r for r in row["reuses"] if r["tc_id"] != "TC_Basic_WorkFlow_06"]
        problems = self.check(scope=scope)
        self.assertTrue(any("TC_WindowsUpdate_06" in p and "TC_Basic_WorkFlow_06" in p
                            for p in problems), problems)

    def test_extra_reused_tc_in_trace_is_detected(self):
        trace = copy.deepcopy(self.trace)
        _row(trace["tc"], "TC_WindowsUpdate_08")["reuses"].append("TC_Basic_WorkFlow_10")
        problems = self.check(trace=trace)
        self.assertTrue(any("코드가 참조하지 않는다" in p for p in problems), problems)

    def test_code_reference_change_is_detected(self):
        source = self.source.replace('lookup.get("TC_Basic_WorkFlow_08")',
                                     'lookup.get("TC_Basic_WorkFlow_07")')
        self.assertNotEqual(source, self.source)
        problems = self.check(source=source)
        self.assertTrue(any("TC_Basic_WorkFlow_07" in p for p in problems), problems)

    def test_missing_wu_entry_and_marker_are_detected(self):
        scope = [r for r in self.scope if r["tc_id"] != "TC_WindowsUpdate_13"]
        self.assertTrue(any("TC_WindowsUpdate_13" in p for p in self.check(scope=scope)))
        scope = copy.deepcopy(self.scope)
        del _row(scope, "TC_WindowsUpdate_02")["checklist"]
        self.assertTrue(any("checklist 표식" in p for p in self.check(scope=scope)))

    def test_title_mismatch_is_detected(self):
        trace = copy.deepcopy(self.trace)
        _row(trace["tc"], "TC_WindowsUpdate_04")["title"] = "다른 제목"
        self.assertTrue(any("title" in p for p in self.check(trace=trace)))

    def test_only_steps_mismatch_is_detected(self):
        scope = copy.deepcopy(self.scope)
        _row(scope, "TC_WindowsUpdate_03")["reuses"][0]["only_steps"] = [6]
        self.assertTrue(any("only_steps" in p for p in self.check(scope=scope)))

    def test_known_defect_mismatch_is_detected(self):
        scope = copy.deepcopy(self.scope)
        _row(scope, "TC_WindowsUpdate_05")["known_defect_exclude"] = [
            {'tc_id': 'TC_XIPL_compatibility_03', 'title': 'synthetic unregistered failure'}]
        problems = self.check(scope=scope)
        self.assertTrue(any("known_defect_exclude" in p for p in problems), problems)
        source = self.source.replace('KNOWN_DEFECT_EXCLUDE = {}',
            'KNOWN_DEFECT_EXCLUDE = {("TC_XIPL_compatibility_03", "synthetic failure"): '
            '{"wu_tc": "TC_WindowsUpdate_04"}}')
        self.assertNotEqual(source, self.source)
        self.assertTrue(self.check(source=source))

    def test_unparsable_source_is_reported_not_raised(self):
        problems = self.check(source="def broken(:\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("파싱 실패", problems[0])


class ExceptPassCheckTests(unittest.TestCase):
    def found(self, source):
        return [key for key, _line in
                sc.check_except_pass({"tests/candidate.py": textwrap.dedent(source)})]

    def test_direct_pass_records_in_except_are_detected(self):
        found = self.found("""
            def run(r):
                try:
                    work()
                except Exception:
                    r.add(1, "확인", PASS, expected="x")
                    r.cleanup(0, "정리", status=PASS)
                    r.assert_true(2, "확인", True)
                    r.status = PASS
                    rows.append({"status": "PASS"})
            """)
        self.assertEqual(len(found), 5, found)
        self.assertTrue(all(key.startswith("tests/candidate.py::run:") for key in found))

    def test_pass_outside_except_and_conditional_pass_are_allowed(self):
        found = self.found("""
            def run(r, ok):
                r.add(1, "확인", PASS)
                try:
                    work()
                except Exception:
                    r.add(1, "확인", PASS if ok else FAIL)
                    r.add(1, "확인", FAIL)
                    def later():
                        r.add(1, "확인", PASS)
            """)
        self.assertEqual(found, [])

    def test_nested_handler_is_reported_once(self):
        found = self.found("""
            try:
                a()
            except Exception:
                try:
                    b()
                except Exception:
                    r.add(1, "x", PASS)
            """)
        self.assertEqual(len(found), 1)

    def test_current_repo_matches_baseline(self):
        new, gone = sc.baseline_diff(sc.repo_except_pass(), sc.EXCEPT_PASS_BASELINE)
        self.assertEqual((new, gone), ([], []))


class WindllCheckTests(unittest.TestCase):
    def found(self, source):
        return [key for key, _line in
                sc.check_windll({"core/candidate.py": textwrap.dedent(source)})]

    def test_shared_windll_assignments_and_aliases_are_detected(self):
        found = self.found("""
            import ctypes
            from ctypes import windll as W
            ctypes.windll.user32.GetFocus.restype = ctypes.c_void_p
            u32 = ctypes.windll.user32
            u32.SendInput.argtypes = ()
            fn = u32.GetAncestor
            fn.errcheck = None
            W.kernel32.CloseHandle.argtypes = ()
            def inner():
                k = ctypes.windll.kernel32
                k.OpenProcess.restype = None
            """)
        self.assertEqual(len(found), 5, found)
        self.assertIn("core/candidate.py::inner: k.OpenProcess.restype = ...", found)

    def test_private_windll_instance_is_allowed(self):
        found = self.found("""
            import ctypes
            lib = ctypes.WinDLL("user32", use_last_error=True)
            lib.SendInput.argtypes = ()
            ctypes.windll.user32.GetForegroundWindow()
            before = ctypes.windll.user32.GetFocus.restype
            """)
        self.assertEqual(found, [])

    def test_current_repo_matches_baseline(self):
        new, gone = sc.baseline_diff(sc.repo_windll(), sc.WINDLL_BASELINE)
        self.assertEqual((new, gone), ([], []))

    def test_baseline_diff_reports_new_and_resolved(self):
        new, gone = sc.baseline_diff([("a::f: x", 1), ("a::f: x", 2)], ["a::f: x", "b::g: y"])
        self.assertEqual(new, ["a::f: x"])
        self.assertEqual(gone, ["b::g: y"])


class CliTests(unittest.TestCase):
    def test_cli_exits_zero_with_empty_baselines(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "wu_selfcheck.py")],
                                capture_output=True, text=True, encoding="utf-8",
                                timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # 기준선이 모두 비어 있다(core/ui.py 6건은 전용 WinDLL 사본으로 옮겼다).
        self.assertNotIn("(기준선)", result.stdout)
        self.assertIn("현재 0건 / 기준선 0건", result.stdout)


if __name__ == "__main__":
    unittest.main()
