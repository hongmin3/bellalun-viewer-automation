"""Validates: REQ-TRACE-001, REQ-TRACE-002, REQ-REPORT-001."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from openpyxl import Workbook, load_workbook

import run
from core import evidence_evaluation, tc_basis
from core.result import PASS, TCResult, write_reports

WF04 = "TC_Basic_WorkFlow_04"
WU02 = "TC_WindowsUpdate_02"


def workbook(path, sheet, tc_id, title):
    book = Workbook()
    book.active.title = sheet
    book.active.append(["TC ID", "Title", "Step Description", "Expected Result", "Previous result"])
    book.active.append([tc_id, title, "1. Send", "1. Receiver observed", "Pass"])
    book.save(path)
    book.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def project(tmp_path):
    revised = tmp_path / "revised.xlsx"
    wu = tmp_path / "wu.xlsx"
    sha = workbook(revised, "개정 TC", WF04, "2D 수동 DICOM Send")
    wu_sha = workbook(wu, "Checklist", WU02, "MWL")
    trace = {
        "_baseline": {"sha256": sha}, "_baseline_windows_update": {"sha256": wu_sha},
        "tc": [
            {"tc_id": WF04, "title": "2D 수동 DICOM Send", "level": "FULL",
             "module": "tests/workflow04.py::run"},
            {"tc_id": WU02, "title": "MWL", "level": "FULL",
             "module": "tests/winupdate.py::_wu_02", "checklist": "windows_update",
             "reuses": [WF04]},
        ],
    }
    (tmp_path / "traceability.json").write_text(json.dumps(trace), encoding="utf-8")
    return SimpleNamespace(cfg={"checklist_xlsx": str(revised), "winupdate_checklist_xlsx": str(wu)},
                           root=tmp_path, resource_root=tmp_path, sha=sha)


def test_same_id_in_older_sheet_cannot_supply_expected_or_claim_pass(project):
    old = project.root / "old.xlsx"
    workbook(old, "Basic Function Checklist", WF04, "Overlay")
    project.cfg["checklist_xlsx"] = str(old)
    basis = tc_basis.resolve(project, "basic")
    assert basis["source"]["status"] == "conflict"
    assert basis["rows"] == {}
    expected = evidence_evaluation.reference(basis, WF04)
    example = Path(__file__).resolve().parents[1] / "docs/examples/conflict-claim.json"
    claim = json.loads(example.read_text(encoding="utf-8"))
    assert evidence_evaluation.grade(expected, claim)["passed"]
    bad = dict(expected, verdict="PASS")
    assert evidence_evaluation.grade(expected, bad)["mismatched_fields"] == ["verdict"]
    report = write_reports([TCResult(WF04, "fixture")], project.root, "conflict",
                           meta=run._tc_report_meta(project, "basic"))
    assert "기준서 확인 보류" in Path(report["html"]).read_text(encoding="utf-8")
    assert "기대 결과 (Expected Result)" not in Path(report["html"]).read_text(encoding="utf-8")


@pytest.mark.parametrize(("kind", "tc_id", "entrypoint"), [
    ("basic", "TC_Basic_WorkFlow_99", "tests/workflow04.py::run"),
    ("windows_update", "TC_WindowsUpdate_99", "tests/winupdate.py::_wu_02"),
])
def test_new_tc_requires_trace_and_full_implementation_before_grading(project, kind, tc_id, entrypoint):
    key, _, _, sheet = tc_basis.SOURCES[kind]
    path = Path(project.cfg[key])
    book = load_workbook(path)
    book[sheet].append([tc_id, "신규 시험", "1. 확인", "1. 기록", None])
    book.save(path)
    book.close()
    trace_path = project.root / "traceability.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    baseline = "_baseline" if kind == "basic" else "_baseline_windows_update"
    trace[baseline]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    trace_path.write_text(json.dumps(trace), encoding="utf-8")
    assert tc_basis.resolve(project, kind)["source"]["status"] == "invalid"

    item = {"tc_id": tc_id, "title": "신규 시험", "checklist": kind, "level": "FULL"}
    trace["tc"].append(item)
    trace_path.write_text(json.dumps(trace), encoding="utf-8")
    incomplete = tc_basis.resolve(project, kind)
    assert incomplete["source"]["status"] == "invalid"
    assert tc_id in incomplete["source"]["reason"]

    item["module"] = entrypoint
    trace_path.write_text(json.dumps(trace), encoding="utf-8")
    basis = tc_basis.capture(project, kind)
    meta = {**run._tc_report_meta(project, kind), "execution_mode": "single"}
    assert meta["modules"][tc_id][0] == entrypoint
    tc = TCResult(tc_id, "신규 시험")
    tc.add(1, "확인", PASS, expected="기록", actual="기록")
    report = Path(write_reports([tc], project.root, "new-tc", meta=meta)["json"])
    claim = {
        "tc_id": tc_id, "verdict": "PASS", "basis_status": "verified",
        "citation": {"sha256": trace[baseline]["sha256"], "sheet": sheet, "id_cell": "A3",
                     "expected_cell": "D3", "implementation": entrypoint},
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }
    assert evidence_evaluation.grade(evidence_evaluation.reference(basis, tc_id, report), claim)["passed"]
    assert not evidence_evaluation.grade(evidence_evaluation.reference(basis, tc_id), claim)["passed"]


def test_scope_only_tc_and_missing_wu_trace_are_detected(project, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(run.__file__).parent / "tools"))
    from tools import traceability

    monkeypatch.chdir(project.root)
    monkeypatch.setattr(traceability._Ctx, "resource_root", project.root, raising=False)
    trace_path = project.root / "traceability.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace["tc"] = [row for row in trace["tc"] if row["tc_id"] != WU02]
    trace_path.write_text(json.dumps(trace), encoding="utf-8")
    scope = [{"tc_id": WU02, "level": "FULL"}, {"tc_id": "helper", "level": "SUPPORT"}]
    (project.root / "automation_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    (project.root / "run.py").write_text("", encoding="utf-8")
    config_path = project.root / "config.json"
    config_path.write_text(json.dumps(project.cfg), encoding="utf-8")
    _, problems = traceability.check(config_path)
    assert f"범위 원장에 있으나 추적성에 없다: {WU02}" in problems
    assert f"{WF04}: 범위 원장에 없다" in problems
    assert any("WU 기준서 invalid" in problem for problem in problems)
    assert not any("helper" in problem for problem in problems)


@pytest.mark.parametrize(("kind", "tc_id", "entrypoint"), [
    ("basic", WF04, "tests/workflow04.py::run"),
    ("windows_update", WU02, "tests/winupdate.py::_wu_02"),
])
def test_report_and_grader_use_displayed_cell_function_and_actual_run(project, kind, tc_id, entrypoint):
    meta = {**run._tc_report_meta(project, kind),
            "execution_mode": "live", "chain_completed": True}
    assert meta["modules"][tc_id][0] == entrypoint
    tc = TCResult(tc_id, "fixture")
    tc.add(1, "Send", PASS, expected="receipt", actual="receipt")
    paths = write_reports([tc], project.root, "fixture", meta=meta)
    source = meta["checklist_basis"]
    html = Path(paths["html"]).read_text(encoding="utf-8")
    assert source["sha256"] in html and "A2, C2, D2" in html and entrypoint in html
    expected = {
        "tc_id": tc_id, "basis_status": "verified", "verdict": "PASS",
        "citation": {"sha256": source["sha256"], "sheet": source["sheet"], "id_cell": "A2",
                     "expected_cell": "D2", "implementation": entrypoint},
        "report_sha256": hashlib.sha256(Path(paths["json"]).read_bytes()).hexdigest(),
    }
    basis = tc_basis.capture(project, kind)
    assert evidence_evaluation.reference(basis, tc_id, paths["json"]) == expected
    static_only = evidence_evaluation.reference(basis, tc_id)
    assert static_only["verdict"] == "UNVERIFIED"  # 이전 회차의 XLSX Pass 열만 있음
    assert not evidence_evaluation.grade(static_only, expected)["passed"]
    assert evidence_evaluation.grade(expected, dict(expected, citation={}))["mismatched_fields"] == ["citation"]
    historical = write_reports([tc], project.root, "historical", meta={**meta, "execution_mode": "historical"})
    assert evidence_evaluation.reference(basis, tc_id, historical["json"]) == static_only


def test_normal_cli_grades_independent_claim_without_product_context(project, monkeypatch):
    monkeypatch.setenv("BELLALUN_RESOURCE_DIR", str(project.root))
    config, claim = project.root / "config.json", project.root / "claim.json"
    config.write_text(json.dumps(project.cfg), encoding="utf-8")
    payload = {"tc_id": WF04, "basis_status": "verified", "verdict": "UNVERIFIED",
               "citation": {"sha256": project.sha, "sheet": "개정 TC", "id_cell": "A2",
                            "expected_cell": "D2", "implementation": "tests/workflow04.py::run"}}
    command = [sys.executable, str(Path(run.__file__)), "--config", str(config),
               "evidence-basis", "--tc", WF04, "--claim", str(claim)]
    for verdict, exit_code in (("UNVERIFIED", 0), ("PASS", 2)):
        claim.write_text(json.dumps(dict(payload, verdict=verdict)), encoding="utf-8")
        result = subprocess.run(command, capture_output=True, encoding="utf-8",
                                env=os.environ | {"PYTHONIOENCODING": "utf-8"})
        assert result.returncode == exit_code, result.stderr
        assert json.loads(result.stdout)["passed"] == (exit_code == 0)
