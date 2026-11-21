"""선택한 설치판 회귀의 기록·해시·기존 판정 기준을 읽기 전용으로 확인한다."""
from datetime import datetime
import json
from pathlib import Path


def combined_report(report):
    """기본+WU 결합 실행(REQ-SPEEDUP-001)의 리포트인지. 릴리스 수용 전체 회귀로 세지 않는다."""
    return ((report or {}).get("meta") or {}).get("run_scope") == "combined"


def selected_report(report):
    """선택 회귀(REQ-SPEEDUP-002)의 리포트인지. 릴리스 수용 전체 회귀로 세지 않는다."""
    return ((report or {}).get("meta") or {}).get("run_scope") == "selected"


def _verified_restoration(workspace, command, product, meta):
    from core.run_preservation import PreservationError, RunPreservation
    restored = meta.get("restoration") or {}
    roots = restored.get("roots") or {}
    required = {"Config", "Image", "ImageTemp", "Export", "ExportSettingTemp", "xipl"}
    if command == "run-winupdate":
        required.add("usb")
    if not (restored == product.get("restoration") and restored.get("status") == "verified"
            and restored.get("run_id") == product["run_id"]
            and required <= roots.keys()
            and all(value.get("status") == "verified"
                    or (value.get("status") == "no_prior_copy" and value.get("restoration_status") == "verified")
                    for value in roots.values())
            and (restored.get("db") or {}).get("status") == "verified"
            and restored.get("services")):
        return False
    journal_path = workspace / "preservation" / product["run_id"] / "journal.json"
    try:
        pending = RunPreservation.pending(workspace)
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        return journal.get("state") == "verified" and not pending
    except (OSError, ValueError, PreservationError):
        return False


def evaluate(path, expected_commit, scope, *, expected_tcs=(), language=False):
    from tools import release_gate as gate
    from tools.run_installed_suites import (SINGLE_COMMANDS, recorded_subcommand, sha256, supervised_receipt,
                                            validate_selection, verify_install)

    checks, reasons = [], []
    result = {"passed": False, "scope": scope, "source_commit": expected_commit,
              "checks": checks, "reasons": reasons}

    def check(name, ok, detail):
        gate._check(checks, reasons, name, ok, detail)

    try:
        record = gate.load_report(path)
        result["verification_sha256"] = sha256(path)
        commands = record.get("selected_commands") or []
        result["executed"] = list(commands)
        # 승인 기록에 미수행 범위를 남긴다. 부분 시험을 전체 회귀로 읽지 않게 한다(REQ-DIST-005 5).
        result["not_executed"] = [suite for suite in ("run-regression", "run-winupdate") if suite not in commands]
        validate_selection(",".join(commands), record.get("expected_tcs") or [])
        required = {"both": {"run-regression", "run-winupdate"},
                    "basic": {"run-regression"}, "wu": {"run-winupdate"}}
        if scope == "tc":
            valid = bool(expected_tcs) and set(expected_tcs) == set(record.get("expected_tcs") or [])
            valid = valid and len(commands) == 1 and commands[0] in SINGLE_COMMANDS
        else:
            valid = scope in required and set(commands) == required.get(scope) and not expected_tcs
        check("선택 범위", valid, f"요청 {scope}, 기록 {commands}, TC {list(expected_tcs)}")
        exe, info_path = Path(record["exe"]), Path(record["build_info"])
        info = gate.load_report(info_path)
        skipped = info.get("skipped") or {}
        check("생략 없는 빌드", skipped.get("compile") is False
              and skipped.get("tests") is False, "컴파일과 소스 시험을 생략한 빌드는 배포하지 않습니다")
        installed = verify_install(exe, info_path)
        result["exe_sha256"] = sha256(exe)
        check("시험한 설치 파일", record.get("install", {}).get("ok") is True
              and installed["ok"] and installed["files_checked"] > 0
              and installed["exe_sha256"] == record["install"].get("exe_sha256")
              and sha256(info_path) == record.get("build_info_sha256"), "EXE·설치 파일·build-info 해시 대조")
        gate._identity("빌드", {"meta": info}, expected_commit, checks, reasons)
        version = info.get("version")
        from bellalunauto.versioning import windows_version
        versioned = "windows_version" in info or (isinstance(version, str) and ".(" in version)
        numeric = windows_version(version) if versioned else None
        if versioned:
            check("빌드 숫자형 버전", info.get("windows_version") == numeric, version)
        runs = record.get("runs") or []
        check("선택 실행 완료", bool(record.get("finished")) and len(runs) == len(commands)
              and [r.get("command") for r in runs] == commands
              and all(r.get("completed") is True and r.get("exit_code") in (0, 1) for r in runs),
              "선택한 실행의 완료 기록 확인")
        for run in runs:
            command = run["command"]
            report_path = Path(run["report"]["path"])
            started = datetime.fromisoformat(run["started"]).timestamp()
            check(f"{command} 리포트 해시·시각", sha256(report_path) == run.get("report_sha256")
                  and report_path.stat().st_mtime >= started - 1, report_path.name)
            report = gate.load_report(report_path)
            meta = report.get("meta") or {}
            gate._identity(command, report, expected_commit, checks, reasons)
            report_version = meta.get("automation_version")
            if (versioned or "windows_version" in meta
                    or (isinstance(report_version, str) and ".(" in report_version)):
                check(f"{command} 빌드와 보고서 버전",
                      versioned and report_version == version and meta.get("windows_version") == numeric,
                      "build-info 표시 및 숫자형 버전과 보고서 대조")
            if versioned and command in {"run-regression", "run-winupdate"}:
                log = Path(run["log"]).resolve()
                workspace = Path(record["workspace"]).resolve()
                supervisor = supervised_receipt(workspace, log, command, run["exit_code"])
                logged = run.get("supervisor") or {}
                valid_supervisor = False
                if supervisor and sha256(log) == run.get("log_sha256"):
                    product = supervisor["record"]
                    plan = product.get("plan") or {}
                    started_epoch = product.get("started_epoch")
                    ended = datetime.fromisoformat(product["ended"])
                    valid_supervisor = (
                        supervisor["run_id"] == logged.get("run_id") == meta.get("run_id")
                        and supervisor["sha256"] == logged.get("sha256")
                        and type(started_epoch) in (int, float)
                        and ended.utcoffset() is not None
                        and started <= started_epoch <= report_path.stat().st_mtime < ended.timestamp() + 1
                        and log.parent == Path(path).resolve().parent
                        and report_path.resolve().parent == workspace / "Reports"
                        and str(report_path.resolve()) in product.get("reports", [])
                        and bool(plan.get("plan_id")) and plan["plan_id"] == meta.get("plan_id")
                        and (plan.get("source_identity") or {}).get("source_commit") == expected_commit
                    )
                check(f"{command} 감독 실행 기록", valid_supervisor,
                      "실행 로그의 번호, 감독 기록 해시·계획·기간과 원본 리포트 대조")
                restoration_ok = (valid_supervisor and record.get("restore_after") is True
                                  and _verified_restoration(workspace, command, supervisor["record"], meta))
                check(f"{command} 원상복원", restoration_ok,
                      "감독과 보고서의 원상복원, 완료 일지와 남은 복원 대기 대조")
            check(f"{command} 단독 묶음 실행", not combined_report(report),
                  "기본+WU 결합 실행 결과는 릴리스 수용 전체 회귀로 세지 않습니다")
            check(f"{command} 전체 실행", not selected_report(report),
                  "선택 회귀 결과는 릴리스 수용 전체 회귀로 세지 않습니다")
            check(f"{command} 설치판 출처", meta.get("source_identity_origin") == "build-info",
                  "리포트 출처가 build-info여야 합니다")
            actual_command = recorded_subcommand(meta.get("command"))
            check(f"{command} 명령 일치", actual_command == command,
                  "실행 기록과 리포트 명령 대조")
            rows = report.get("results") or []
            ids = [r.get("tc_id") for r in rows]
            valid_rows = bool(rows) and all(isinstance(tc, str) and tc for tc in ids) and len(set(ids)) == len(ids)
            for row in rows:
                verdict, details = row.get("verdict"), row.get("checks") or []
                valid_rows = valid_rows and verdict in {"PASS", "FAIL", "MANUAL", "SKIP", "BLOCKED"}
                valid_rows = valid_rows and bool(details)
                if verdict == "FAIL":
                    valid_rows = valid_rows and any(c.get("status") == "FAIL" for c in details)
            check(f"{command} 판정 기록", valid_rows, "빈 결과·중복 TC·판정 누락·근거 없는 FAIL 거부")
            if command == "run-winupdate":
                gate._evaluate_wu(report, checks, reasons)
            else:
                if scope == "tc":
                    product_ids = {tc for tc in ids if str(tc).startswith("TC_")}
                    check("단독 TC 범위", product_ids == set(expected_tcs),
                          f"기대 {list(expected_tcs)}, 실제 {sorted(product_ids)}")
                    verdicts = [row.get("verdict") for row in rows if row.get("tc_id") in product_ids]
                    check("단독 TC 실제 수행", any(v != "SKIP" for v in verdicts),
                          "모든 TC가 SKIP이면 검증한 것이 없습니다")
                gate._evaluate_basic(report, checks, reasons, gate.KNOWN_DEFECT_EXCLUDE,
                                     require_full=command == "run-regression")
            if language:
                problems = gate.check_report_language(report, command)
                check("리포트 문장 점검", not problems, "; ".join(problems) or "문제 없음")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        check("설치판 검증 기록", False, f"기록을 확인할 수 없습니다: {error}")
    result["passed"] = not reasons
    return result
