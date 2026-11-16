# -*- coding: utf-8 -*-
"""영향 기반 선택 회귀(`run-regression --select`)의 해석·표시·집계.

Validates: REQ-SPEEDUP-002
"""
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import run
from core import automation_health as health
from core import selection
from core.result import TCResult, PASS


def _ids(stages):
    return [stage_id for _, stage_id, _ in stages]


class ResolveTests(unittest.TestCase):
    def test_chain_ids_match_basic_chain(self):
        self.assertEqual(list(selection.BASIC_CHAIN_IDS), _ids(run._basic_chain_stages()))

    def test_short_names_add_smoke_precondition_and_fixture(self):
        picked = selection.resolve(["wf04"])
        self.assertEqual(picked["requested"], ["TC_Basic_WorkFlow_04"])
        self.assertEqual(picked["smoke"], ["TC_Basic_Install_02", "TC_Basic_WorkFlow_01"])
        self.assertEqual(picked["dependencies"], ["TC_Basic_WorkFlow_02"])
        self.assertEqual(picked["executed"], [
            "TC_Basic_Install_02", "DICOM_Server_Setup", "TC_Basic_WorkFlow_01",
            "TC_Basic_WorkFlow_02", "TC_Basic_WorkFlow_04"])

    def test_overlay_readers_pull_in_wf03(self):
        picked = selection.resolve(["TC_Basic_WorkFlow_15", "wf08"])
        self.assertEqual(picked["requested"], ["TC_Basic_WorkFlow_08", "TC_Basic_WorkFlow_15"])
        self.assertIn("TC_Basic_WorkFlow_03", picked["dependencies"])
        self.assertEqual(picked["executed"][-4:], [
            "TC_Basic_WorkFlow_02", "TC_Basic_WorkFlow_03",
            "TC_Basic_WorkFlow_08", "TC_Basic_WorkFlow_15"])

    def test_xipl_individual_id_maps_to_whole_stage(self):
        for name in ("TC_XIPL_compatibility_04", "xipl", "xipl-04", "XIPL04"):
            picked = selection.resolve([name])
            self.assertEqual(picked["requested"], ["TC_XIPL_compatibility"], name)
            self.assertEqual(picked["executed"][-1], "TC_XIPL_compatibility")
            self.assertIn("TC_Basic_WorkFlow_02", picked["executed"])

    def test_smoke_only_selection_has_no_extra_dependencies(self):
        picked = selection.resolve(["install02"])
        self.assertEqual(picked["dependencies"], [])
        self.assertEqual(picked["executed"], [
            "TC_Basic_Install_02", "DICOM_Server_Setup", "TC_Basic_WorkFlow_01"])

    def test_unknown_or_empty_is_rejected(self):
        for bad in (["wf99"], ["TC_WindowsUpdate_10"], [], [" "]):
            with self.assertRaises(ValueError):
                selection.resolve(bad)

    def test_selection_equal_to_full_chain_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            selection.resolve(list(selection.BASIC_CHAIN_IDS))
        self.assertIn("run-regression", str(raised.exception))

    def test_from_arguments(self):
        self.assertIsNone(selection.from_arguments(["run-regression", "--restore-after"]))
        picked = selection.from_arguments(["run-regression", "--select", "wf04,wf05"])
        self.assertEqual(picked["requested"], ["TC_Basic_WorkFlow_04", "TC_Basic_WorkFlow_05"])
        same = selection.from_arguments(["run-regression", "--select=wf05,wf04"])
        self.assertEqual(same["executed"], picked["executed"])
        with self.assertRaises(ValueError):
            selection.from_arguments(["run-regression", "--select"])


class ChainTests(unittest.TestCase):
    def test_selected_chain_keeps_checklist_order_and_functions(self):
        stages = run._basic_chain_stages()
        picked = selection.resolve(["wf08"])
        chain = run._selected_chain_stages(stages, picked)
        self.assertEqual(_ids(chain), picked["executed"])
        by_id = {sid: fn for fn, sid, _ in stages}
        for fn, sid, _ in chain:
            self.assertIs(fn, by_id[sid])

    def test_selected_run_adds_no_human_skip_rows(self):
        ctx = SimpleNamespace(root=".", resource_root=os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        full = run._regression_scope_skips(ctx, [], None)
        self.assertTrue(any(r.tc_id == "TC_Basic_QC_01" for r in full))
        self.assertEqual(run._regression_scope_skips(ctx, [], selection.resolve(["wf04"])), [])


class CliTests(unittest.TestCase):
    def test_unknown_selection_stops_before_product(self):
        argv = ["run.py", "run-regression", "--select", "wf99", "--restore-after"]
        with patch.object(sys, "argv", argv), \
                patch.object(run, "Context", side_effect=AssertionError("제품 조작 전 거부")):
            self.assertEqual(run._main(), 2)

    def test_select_is_only_for_run_regression(self):
        with patch.object(sys, "argv", ["run.py", "run-wf04", "--select", "wf04"]):
            with self.assertRaises(SystemExit) as raised:
                run._main()
        self.assertEqual(raised.exception.code, 2)

    def test_meta_carries_scope_and_selection(self):
        picked = selection.resolve(["wf04"])
        ctx = SimpleNamespace(run_scope="selected", selection=picked)
        meta = run._execution_meta(ctx)
        self.assertEqual(meta["run_scope"], "selected")
        self.assertEqual(meta["selection"], picked)


class PlanTests(unittest.TestCase):
    def test_selected_plan_label_and_fingerprint(self):
        from bellalunauto import runplan
        with tempfile.TemporaryDirectory() as tmp:
            layout = SimpleNamespace(workspace=tmp, resource_dir=tmp)
            with patch.object(runplan, "bundled_config", side_effect=lambda c, r: c), \
                    patch.object(runplan, "source_dir", return_value=tmp):
                full = runplan.build_plan(layout, {}, "run-regression")
                a = runplan.build_plan(layout, {}, "run-regression",
                                       selected=selection.resolve(["wf04"])["executed"])
                b = runplan.build_plan(layout, {}, "run-regression",
                                       selected=selection.resolve(["wf05"])["executed"])
        self.assertEqual(a["label"], "기본기능 선택 수행(영향 TC+smoke)")
        self.assertEqual(a["run_scope"], "selected")
        self.assertEqual(a["selection"], selection.resolve(["wf04"])["executed"])
        self.assertNotIn("run_scope", full)
        self.assertEqual(len({full["plan_id"], a["plan_id"], b["plan_id"]}), 3)


class CountingTests(unittest.TestCase):
    def _report(self, folder, meta):
        rows = [{"tc_id": t, "verdict": "PASS"} for t in health.FULL_REGRESSION_MARKERS]
        path = os.path.join(folder, "Result_20261116_120000.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"meta": meta, "results": rows}, fh)
        return path

    def test_selected_report_is_not_full_regression(self):
        with tempfile.TemporaryDirectory() as folder:
            self._report(folder, {"run_scope": "selected"})
            self.assertIsNone(health.latest_full_regression(folder))
        self.assertFalse(health.completed_report_data(
            {"meta": {"run_scope": "selected"},
             "results": [{"tc_id": t} for t in health.FULL_REGRESSION_MARKERS]},
            "run-regression"))

    def test_completed_selected_run_is_found_only_as_selected(self):
        from bellalunauto.app import completed_report
        selected = {"run_scope": "selected", "chain_completed": True, "run_id": "r1",
                    "selection": selection.resolve(["wf04"])}
        with tempfile.TemporaryDirectory() as folder:
            path = self._report(folder, selected)
            found = completed_report(folder, "run-regression", 0, scope="selected")
            self.assertEqual(found["path"], path)
            self.assertIsNone(completed_report(folder, "run-regression", 0))
            self._report(folder, {**selected, "chain_completed": False})
            self.assertIsNone(completed_report(folder, "run-regression", 0, scope="selected"))
        self.assertFalse(health.completed_report_data(
            {"meta": {"chain_completed": True}, "results": []}, "run-regression", scope="selected"))

    def test_selected_scope_helpers(self):
        self.assertEqual(health.report_scope({"meta": {"run_scope": "selected"}}), "selected")
        self.assertIsNone(health.report_scope({"meta": {"run_scope": "combined"}}))
        self.assertEqual(selection.scope_of_arguments(["run-regression", "--select", "wf04"]), "selected")
        self.assertEqual(selection.scope_of_arguments(["run-regression", "--select=wf04"]), "selected")
        self.assertIsNone(selection.scope_of_arguments(["run-regression", "--restore-after"]))

    def test_legacy_release_gate_rejects_selected_report(self):
        from tools import release_gate
        rows = [{"tc_id": t, "verdict": "PASS", "checks": []} for t in health.FULL_REGRESSION_MARKERS]
        checks, reasons = [], []
        release_gate._evaluate_basic({"meta": {"run_scope": "selected"}, "results": rows},
                                     checks, reasons, {})
        self.assertTrue(any("선택 회귀" in reason for reason in reasons), reasons)
        checks, reasons = [], []
        release_gate._evaluate_basic({"meta": {}, "results": rows}, checks, reasons, {})
        self.assertFalse(any("선택 회귀" in reason for reason in reasons), reasons)

    def test_release_gate_flags_selected_report(self):
        from tools import installed_release_gate as gate
        self.assertTrue(gate.selected_report({"meta": {"run_scope": "selected"}}))
        self.assertFalse(gate.selected_report({"meta": {"run_scope": "combined"}}))

    def test_report_header_says_not_full_regression(self):
        from core import result
        r = TCResult("TC_Basic_WorkFlow_04", "x")
        r.add(1, "ok", PASS)
        with tempfile.TemporaryDirectory() as tmp:
            meta = {"run_scope": "selected", "run_id": "20261116-120000-abcdef12",
                    "selection": selection.resolve(["wf04"])}
            paths = result.write_reports([r], tmp, "selected", meta=meta)
            with open(paths["html"], encoding="utf-8") as fh:
                html = fh.read()
            with open(paths["csv"], encoding="utf-8-sig") as fh:
                csv_text = fh.read()
        self.assertIn("선택 실행(영향 TC+smoke) — 전체 회귀 아님", html)
        self.assertIn("선택 실행(영향 TC+smoke) — 전체 회귀 아님", csv_text)


class InstalledSuiteTests(unittest.TestCase):
    def test_run_selected_needs_expected_tcs(self):
        from tools import run_installed_suites as suites
        self.assertEqual(suites.validate_selection(
            "run-selected", ["TC_Basic_WorkFlow_04"]), ["run-selected"])
        for bad, tcs in (("run-selected", []), ("run-selected,run-regression", ["wf04"]),
                         ("run-selected", ["wf99"])):
            with self.assertRaises(ValueError):
                suites.validate_selection(bad, tcs)

    def test_run_selected_passes_select_and_restore_choice(self):
        from tools import run_installed_suites as suites
        args = suites.command_args("run-selected", True, expected_tcs=["wf04", "wf05"])
        self.assertEqual(args, ["run-regression", "--select", "wf04,wf05", "--restore-after"])
        with self.assertRaises(ValueError):
            suites.command_args("run-selected", None, expected_tcs=["wf04"])


if __name__ == "__main__":
    unittest.main()


def test_selected_cli_run_completes_and_cleans_generated_image(tmp_path, monkeypatch):
    """선택 실행도 보존·복원·정상완주 증거·생성 이미지 정리를 기본 전체와 같이 마친다."""
    from pathlib import Path
    from bellalunauto import runplan
    from core import dbreset, execution_session
    from core.result import write_reports
    images, storage, workspace = (tmp_path / name for name in ("Image", "nas", "work"))
    images.mkdir()
    storage.mkdir()
    (images / "original.img").write_bytes(b"original")
    generated = images / "generated.img"
    ctx = SimpleNamespace(root=str(workspace), resource_root=str(tmp_path),
                          reports_root=str(workspace / "Reports"),
                          cfg={"data_dir": str(tmp_path), "preservation": {"storage_dir": str(storage)}})

    class Database:
        def __init__(self, ctx): pass
        def estimate_bytes(self): return 0
        def backup(self, dest): return {"scope": "synthetic"}
        def verify_backup(self, *a): return True
        def restore(self, *a): pass
        def verify_restored(self, *a): return True
    monkeypatch.delenv("BELLALUN_QA_RUN", raising=False)
    monkeypatch.setattr(execution_session, "DatabasePreservation", Database)
    monkeypatch.setattr(execution_session, "plan_resources", lambda *a, **k: {"blocked": False})
    monkeypatch.setattr(execution_session, "stop_product", lambda *a: None)
    monkeypatch.setattr(execution_session, "start_services",
                        lambda: {name: "RUNNING" for name in dbreset.APP_SERVICES})
    monkeypatch.setattr(execution_session, "roots_from_config", lambda *a, **k: {"Image": images})
    plans = []
    monkeypatch.setattr(runplan, "build_plan", lambda *a, **k: plans.append(k) or
                        {"plan_id": "fixed", "execution_fingerprint": "fixed"})
    picked = selection.resolve(["wf04"])

    def dispatch(ctx, args):
        ctx.run_scope, ctx.selection = "selected", args.selection
        generated.write_bytes(b"generated")
        rows = []
        for tc_id in picked["executed"]:
            row = TCResult(tc_id, "synthetic")
            row.add(1, "result", "PASS")
            row.attach(str(generated))
            rows.append(row)
        write_reports(rows, ctx.reports_root, "fixture", meta=run._execution_meta(ctx))
        return 0
    monkeypatch.setattr(run, "_dispatch", dispatch)
    args = SimpleNamespace(cmd="run-regression", restore_after=True, selection=picked)
    assert run._execute_preserved(ctx, args) == 0
    assert plans == [{"selected": picked["executed"]}]
    final = json.loads((Path(ctx.reports_root) / "Result_fixture.json").read_text(encoding="utf-8"))
    assert final["meta"]["run_scope"] == "selected"
    assert final["meta"]["restoration"]["status"] == "verified"
    assert final["meta"]["restoration"]["image_cleanup"]["status"] == "completed"
    assert "phases" in final["meta"]["restoration"] and "timings" in final["meta"]["restoration"]
    assert not generated.exists()
    assert (images / "original.img").read_bytes() == b"original"
    assert health.latest_full_regression(ctx.reports_root) is None
