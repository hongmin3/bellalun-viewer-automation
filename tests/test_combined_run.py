# -*- coding: utf-8 -*-
"""기본+WU 결합 실행(`run-winupdate --with-basic`)의 단계 구성과 표시.

Validates: REQ-SPEEDUP-001
"""
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import run
from core import flows, wu_chain
from core.result import TCResult, PASS
from tests import winupdate

BASIC_ORDER = [
    "TC_Basic_Install_01", "TC_Basic_Install_02", "DICOM_Server_Setup",
    "TC_Basic_WorkFlow_01", "TC_Basic_WorkFlow_02", "TC_Basic_WorkFlow_03",
    "TC_Basic_WorkFlow_04", "TC_Basic_WorkFlow_05", "TC_Basic_WorkFlow_06",
    "TC_Basic_WorkFlow_07", "TC_Basic_WorkFlow_08", "TC_Basic_WorkFlow_09",
    "TC_Basic_WorkFlow_10", "TC_Basic_WorkFlow_11", "TC_Basic_WorkFlow_12",
    "TC_Basic_WorkFlow_13", "TC_Basic_WorkFlow_14", "TC_Basic_WorkFlow_15",
    "TC_Basic_WorkFlow_16", "TC_XIPL_compatibility",
]
WU_ORDER = [
    "AUTOMATION_ENVIRONMENT_RESET", "TC_Basic_Install_01", "TC_Basic_Install_02",
    "DICOM_Server_Setup", "AUTOMATION_SCREEN_CONTRACT", "TC_Basic_WorkFlow_01",
    "TC_Basic_WorkFlow_02", "TC_Basic_WorkFlow_03", "TC_Basic_WorkFlow_04",
    "TC_Basic_WorkFlow_05", "TC_Basic_WorkFlow_06", "TC_XIPL_compatibility_subset",
    "TC_Basic_WorkFlow_08", "TC_Basic_WorkFlow_09", "TC_Basic_WorkFlow_14",
]


def _ids(stages):
    return [stage_id for _, stage_id, _ in stages]


class StageCompositionTests(unittest.TestCase):
    def test_existing_chains_are_unchanged(self):
        self.assertEqual(_ids(run._basic_chain_stages()), BASIC_ORDER)
        self.assertEqual(_ids(run._wu_chain_stages()), WU_ORDER)

    def test_combined_stage_order(self):
        ids = _ids(run._combined_chain_stages())
        expected = (["AUTOMATION_ENVIRONMENT_RESET"] + BASIC_ORDER[:3]
                    + ["AUTOMATION_SCREEN_CONTRACT"] + BASIC_ORDER[3:])
        self.assertEqual(ids, expected)
        # WU 매핑이 쓰는 기본 TC는 모두 결합 체인 안에서 실시간으로 실행된다.
        for stage_id in WU_ORDER:
            if stage_id != "TC_XIPL_compatibility_subset":
                self.assertIn(stage_id, ids)

    def test_combined_reset_regenerates_xipl_parameters(self):
        reset = run._combined_chain_stages()[0][0]
        self.assertIs(reset, run._basic_reset_stage)

    def test_full_xipl_stage_has_timeout_and_blocked_outputs(self):
        self.assertGreaterEqual(wu_chain.stage_timeout("TC_XIPL_compatibility"), 60 * 60)
        blocked = wu_chain.blocked_results("TC_XIPL_compatibility", "XIPL", "timeout", "사유")
        self.assertEqual([r.tc_id for r in blocked],
                         [f"TC_XIPL_compatibility_{i:02}" for i in range(1, 8)])

    def test_identity_differs_from_wu_chain(self):
        combined = _ids(run._combined_chain_stages()) + list(run.WU_TAIL_STAGES)
        wu = _ids(run._wu_chain_stages()) + list(run.WU_TAIL_STAGES)
        self.assertNotEqual(wu_chain.chain_identity(combined), wu_chain.chain_identity(wu))


class BasicReportTests(unittest.TestCase):
    def test_basic_rows_drop_wu_and_contract_results(self):
        rows = [TCResult(t, t) for t in ("AUTOMATION_ENVIRONMENT_RESET",
                                           "AUTOMATION_SCREEN_CONTRACT",
                                           "TC_Basic_WorkFlow_01", "TC_WindowsUpdate_10")]
        kept = [r.tc_id for r in run._combined_basic_rows(rows)]
        self.assertEqual(kept, ["AUTOMATION_ENVIRONMENT_RESET", "TC_Basic_WorkFlow_01"])


class ArgumentTests(unittest.TestCase):
    def test_with_basic_and_from_regression_are_refused_together(self):
        with patch("sys.argv", ["run.py", "run-winupdate", "--with-basic",
                                "--from-regression", "x.json"]):
            with self.assertRaises(SystemExit) as raised:
                run.main()
        self.assertEqual(raised.exception.code, 2)


class PlanTests(unittest.TestCase):
    def test_combined_plan_label_and_xipl_policy(self):
        from bellalunauto import runplan
        with tempfile.TemporaryDirectory() as tmp:
            layout = SimpleNamespace(workspace=tmp, resource_dir=tmp)
            with patch.object(runplan, "bundled_config", side_effect=lambda c, r: c), \
                    patch.object(runplan, "source_dir", return_value=tmp):
                plan = runplan.build_plan(layout, {}, "run-winupdate", combined=True)
                single = runplan.build_plan(layout, {}, "run-winupdate")
        self.assertEqual(plan["label"], "기본기능+Windows Update 결합 수행")
        self.assertTrue(plan["changes"]["usb"]["enabled"])
        self.assertIn("삭제 후 재생성", plan["changes"]["xipl"]["policy"])
        self.assertEqual(plan.get("run_scope"), "combined")
        self.assertNotEqual(plan["plan_id"], single["plan_id"])
        self.assertNotIn("run_scope", single)


@contextmanager
def _null():
    yield


class _QuietMonitor:
    def __init__(self, *a, **k):
        self.kind = None
        self.reason = None

    def start(self):
        return self

    def stop(self):
        pass


def _passing(tc_id):
    def fn(ctx):
        r = TCResult(tc_id, tc_id)
        r.add(1, "ok", PASS)
        return [r]
    return fn


class CombinedChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = SimpleNamespace(cfg={}, db=object(), root=self.tmp.name,
                                   resource_root=os.path.dirname(os.path.dirname(
                                       os.path.abspath(__file__))),
                                   evidence_root=os.path.join(self.tmp.name, "Evidence"))
        self.calls, self.wu, self.basic = [], [], []

    def tearDown(self):
        self.tmp.cleanup()

    def run_combined(self):
        ids = ["AUTOMATION_ENVIRONMENT_RESET", "DICOM_Server_Setup",
               "AUTOMATION_SCREEN_CONTRACT", "TC_Basic_WorkFlow_01"]

        def stage(tc_id):
            def fn(ctx):
                self.calls.append(tc_id)
                return _passing(tc_id)(ctx)
            return fn

        stages = [(stage(t), t, t) for t in ids]
        preflight = {"items": [], "blocked": False, "environment": {}, "fingerprint": {}}

        def usb(ctx, ui):
            self.calls.append("WU09_USB")
            return {"drive": None}

        def wu10(ctx, ui):
            self.calls.append("TC_WindowsUpdate_10")
            return _passing("TC_WindowsUpdate_10")(ctx)[0]

        with patch.object(run, "_combined_chain_stages", return_value=stages), \
                patch.object(run, "_wu_chain_stages", side_effect=AssertionError), \
                patch.object(run, "_wu_preflight", return_value=preflight), \
                patch.object(run, "shutdown_viewer", return_value={}), \
                patch.object(run, "recover_viewer_after_termination"), \
                patch.object(run, "finish", side_effect=lambda ctx, rows: self.basic.append(
                    (list(rows), getattr(ctx, "run_scope", None))) or 0), \
                patch.object(run, "_finish_winupdate", side_effect=lambda ctx, rows, *a, **k:
                             self.wu.append((list(rows), k)) or 0), \
                patch.object(flows, "cold_start", return_value=(object(), {})), \
                patch.object(winupdate, "run_usb_export_import", side_effect=usb), \
                patch.object(winupdate, "run_setting_display", side_effect=wu10), \
                patch.object(wu_chain, "keep_awake", side_effect=lambda: _null()), \
                patch.object(wu_chain, "StageMonitor", _QuietMonitor), \
                patch("core.env_preflight.summary_for_report", return_value={}):
            return run._run_winupdate_chain(self.ctx, with_basic=True)

    def test_runs_basic_then_wu_tail_and_writes_both_reports(self):
        self.assertEqual(self.run_combined(), 0)
        self.assertEqual(self.calls, ["AUTOMATION_ENVIRONMENT_RESET", "DICOM_Server_Setup",
                                      "AUTOMATION_SCREEN_CONTRACT", "TC_Basic_WorkFlow_01",
                                      "WU09_USB", "TC_WindowsUpdate_10"])
        rows, scope = self.basic[-1]
        ids = [r.tc_id for r in rows]
        self.assertEqual(scope, "combined")
        self.assertIn("TC_Basic_WorkFlow_01", ids)
        self.assertNotIn("TC_WindowsUpdate_10", ids)
        self.assertNotIn("AUTOMATION_SCREEN_CONTRACT", ids)
        # 사람 전용 SKIP(REQ-TCUP-001)도 기본 리포트에 들어간다.
        self.assertIn("TC_Basic_QC_01", ids)
        wu_rows, kwargs = self.wu[-1]
        self.assertEqual(len(wu_rows), 13)
        self.assertEqual(kwargs["execution_mode"], "live")
        self.assertTrue(kwargs["chain_completed"])
        self.assertIn("결합", kwargs["source_note"])
        self.assertEqual(kwargs["extra_meta"]["run_scope"], "combined")


class ReleaseGateTests(unittest.TestCase):
    def test_combined_report_is_not_counted_as_basic_suite(self):
        from tools import installed_release_gate as gate
        self.assertTrue(gate.combined_report({"meta": {"run_scope": "combined"}}))
        self.assertFalse(gate.combined_report({"meta": {}}))


if __name__ == "__main__":
    unittest.main()


class InstalledSuiteTests(unittest.TestCase):
    def test_combined_suite_selection(self):
        from tools import run_installed_suites as suites
        self.assertEqual(suites.validate_selection("run-combined", []), ["run-combined"])
        for bad in ("run-combined,run-regression", "run-combined,run-winupdate"):
            with self.assertRaises(ValueError):
                suites.validate_selection(bad, [])

    def test_combined_suite_runs_winupdate_with_basic(self):
        from tools import run_installed_suites as suites
        seen = {}

        def fake_run(args, **kwargs):
            seen["args"] = args
            return SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(suites.subprocess, "run", side_effect=fake_run), \
                    patch("bellalunauto.app.completed_report", return_value=None), \
                    patch("core.automation_health.latest_full_regression", return_value=None), \
                    patch.object(suites, "snapshot", return_value={}):
                result = suites.run_suite("exe", tmp, None, "run-combined", tmp, tmp)
        self.assertEqual(seen["args"][-2:], ["run-winupdate", "--with-basic"])
        self.assertFalse(result["completed"])
