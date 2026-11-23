"""선택한 설치판 회귀의 기록·해시·기존 판정 기준을 읽기 전용으로 확인한다."""
from datetime import datetime
from pathlib import Path


def combined_report(report):
    """기본+WU 결합 실행(REQ-SPEEDUP-001)의 리포트인지. 릴리스 수용 전체 회귀로 세지 않는다."""
    return ((report or {}).get("meta") or {}).get("run_scope") == "combined"


def selected_report(report):
    """선택 회귀(REQ-SPEEDUP-002)의 리포트인지. 릴리스 수용 전체 회귀로 세지 않는다."""
    return ((report or {}).get("meta") or {}).get("run_scope") == "selected"


def evaluate(path, expected_commit, scope, *, expected_tcs=(), language=False):
    from tools import release_gate as gate
    from tools.run_installed_suites import sha256, validate_selection, verify_install

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
            valid = valid and not set(commands) & {"run-regression", "run-winupdate"}
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
        from bellalunauto.versioning import is_development_version, windows_version
        versioned = "windows_version" in info or is_development_version(version)
        numeric = windows_version(version, allow_legacy=True) if versioned else None
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
            check(f"{command} 단독 묶음 실행", not combined_report(report),
                  "기본+WU 결합 실행 결과는 릴리스 수용 전체 회귀로 세지 않습니다")
            check(f"{command} 전체 실행", not selected_report(report),
                  "선택 회귀 결과는 릴리스 수용 전체 회귀로 세지 않습니다")
            check(f"{command} 설치판 출처", meta.get("source_identity_origin") == "build-info",
                  "리포트 출처가 build-info여야 합니다")
            report_version = meta.get("automation_version")
            if (versioned or "windows_version" in meta
                    or is_development_version(report_version)):
                check(f"{command} 빌드와 보고서 버전",
                      versioned and report_version == version and meta.get("windows_version") == numeric,
                      "build-info 표시 및 숫자형 버전과 보고서 대조")
            actual_command = str(meta.get("command") or "").split()
            check(f"{command} 명령 일치", bool(actual_command) and actual_command[-1] == command,
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
