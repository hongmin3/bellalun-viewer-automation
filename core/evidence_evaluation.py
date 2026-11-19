"""에이전트의 기준서 인용과 제품 판정을 기계적으로 채점한다."""
import hashlib
import json
from pathlib import Path

from core import tc_basis


def reference(basis, tc_id, report_path=None, *, expected_run_id=None):
    """기준서와 지정된 이번 실행 JSON에서 채점에 사용할 값을 얻는다."""
    meta = tc_basis.report_meta(basis)
    source = meta["checklist_basis"]
    row = meta["tc_basis"].get(tc_id)
    expected = {"tc_id": tc_id, "basis_status": source["status"], "verdict": "UNVERIFIED"}
    if not row:
        return expected
    expected["citation"] = {
        "sha256": source["sha256"], "sheet": source["sheet"],
        "id_cell": row["cells"]["tc_id"], "expected_cell": row["cells"]["expected"],
        "implementation": row["implementation"],
    }
    if report_path is None or not expected_run_id:
        return expected
    data = Path(report_path).read_bytes()
    report = json.loads(data)
    run = report["meta"]
    saved = run.get("checklist_basis") or {}
    if (run.get("run_id") != expected_run_id
            or run.get("execution_mode") not in ("live", "single")
            or (run.get("execution_mode") == "live" and run.get("chain_completed") is not True)
            or any(saved.get(key) != source[key] for key in ("kind", "status", "sha256", "sheet"))):
        return expected
    matches = [result for result in report["results"] if result.get("tc_id") == tc_id]
    if len(matches) != 1:
        return expected
    result = matches[0]
    if result.get("tc_basis") != row or result.get("reused_from_checkpoint"):
        return expected
    verdict = result.get("verdict")
    if verdict not in ("PASS", "FAIL", "SKIP", "MANUAL", "BLOCKED"):
        return expected
    checks = result.get("checks", [])
    if not any(check.get("status") == verdict and check.get("actual") not in (None, "", "None")
               for check in checks):
        return expected
    if verdict == "PASS" and any(check.get("status") in ("FAIL", "BLOCKED", "MANUAL")
                                 and check.get("blocks_verdict") is not False for check in checks):
        return expected
    expected["verdict"] = verdict
    expected["report_sha256"] = hashlib.sha256(data).hexdigest()
    return expected


def grade(expected, claim):
    """필수 인용·판정의 정확성을 검사하고 제출된 근거를 각각 채점한다."""
    if not isinstance(claim, dict):
        raise ValueError("판정 제출물은 JSON 객체여야 합니다.")
    errors = [key for key in expected.keys() | claim.keys()
              if expected.get(key) != claim.get(key) or (key in expected) != (key in claim)]
    return {"passed": not errors, "mismatched_fields": sorted(errors)}
