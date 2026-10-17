# -*- coding: utf-8 -*-
"""설치판 EXE 로 기본기능 전체와 실시간 Windows Update 전체를 차례로 실행한다.

REQ-DIST-004 의 최종 실행 검증 도구다. 하는 일:

1. 설치 폴더의 EXE 와 모든 파일이 `build-info.json` 의 크기·SHA256 과 같은지 대조한다.
2. 설치 폴더와 작업 폴더 밖의 실행 폴더(CWD)에서 `run-regression`, `run-winupdate` 를
   차례로 실행하고 출력 전체를 로그로 남긴다.
3. 실행마다 작업 폴더에서 새로 생긴 Reports/Evidence/Log 파일을 복사하고 SHA256 을
   다시 대조한다(다음 실행이 같은 이름의 증거를 덮어쓰기 전에 보존한다).
4. 새 전체 리포트인지(기본: 전체 회귀 TC 표식, WU: live·chain_completed·13 TC)와
   WU 목표(WU_01/12/13 기존 수동 외 10건 PASS)를 판정해 `verification.json` 에 쓴다.

판정 기준은 바꾸지 않는다. 리포트가 없거나 조기 중단이면 그대로 미완료로 기록한다.

사용 예:
    python tools/run_installed_suites.py --exe "D:/설치 폴더/BellalunAuto.exe" \
        --build-info "D:/설치 폴더/build-info.json" --workspace "D:/작업 폴더" \
        --out "D:/실행 기록/run-01"
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WU_IDS = [f"TC_WindowsUpdate_{i:02}" for i in range(1, 14)]
#: 기존 사용자 지정 수동 범위. 목표 판정에서 빼고 나머지 10건의 PASS 를 요구한다.
WU_MANUAL = {"TC_WindowsUpdate_01", "TC_WindowsUpdate_12", "TC_WindowsUpdate_13"}
SNAPSHOT_DIRS = ("Reports", "Evidence", "Log")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_install(exe, build_info):
    """설치 폴더 파일이 build-info 와 같은지. 다른 파일 목록을 돌려준다."""
    info = json.loads(Path(build_info).read_text(encoding="utf-8"))
    base = Path(exe).parent
    mismatched = []
    for entry in info.get("files", []):
        path = base / entry["path"]
        if not path.is_file():
            mismatched.append({"path": entry["path"], "problem": "missing"})
            continue
        if path.stat().st_size != entry["size"] or sha256(path) != entry["sha256"]:
            mismatched.append({"path": entry["path"], "problem": "changed"})
    exe_sha = sha256(exe)
    app = info.get("application") or {}
    return {"ok": not mismatched and exe_sha == app.get("sha256"),
            "exe_sha256": exe_sha, "expected_sha256": app.get("sha256"),
            "source_commit": info.get("source_commit"),
            "source_dirty": info.get("source_dirty"),
            "files_checked": len(info.get("files", [])), "mismatched": mismatched}


def snapshot(workspace, since, destination):
    """`since` 이후 바뀐 Reports/Evidence/Log 파일을 복사하고 해시를 다시 대조한다."""
    files = []
    verified = True
    for top in SNAPSHOT_DIRS:
        base = Path(workspace) / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.stat().st_mtime < since:
                continue
            rel = path.relative_to(workspace).as_posix()
            target = Path(destination) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            src_hash, dst_hash = sha256(path), sha256(target)
            same = src_hash == dst_hash and path.stat().st_size == target.stat().st_size
            verified = verified and same
            files.append({"path": rel, "size": path.stat().st_size,
                          "sha256": src_hash, "copy_matches": same})
    return {"files": files, "count": len(files), "verified": verified}


def wu_target(rows):
    """WU_01/12/13 외 10건이 모두 PASS 인지. 없는 행·SKIP 은 PASS 가 아니다."""
    by_id = {row.get("tc_id"): row.get("verdict") for row in rows}
    not_pass = [(tc, by_id.get(tc) or "MISSING") for tc in WU_IDS
                if tc not in WU_MANUAL and by_id.get(tc) != "PASS"]
    return {"met": not not_pass, "required": len(WU_IDS) - len(WU_MANUAL),
            "passed": sum(1 for tc in WU_IDS
                          if tc not in WU_MANUAL and by_id.get(tc) == "PASS"),
            "not_pass": not_pass,
            "manual_scope": {tc: by_id.get(tc) or "MISSING" for tc in sorted(WU_MANUAL)}}


def _report_rows(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("meta") or {}, data.get("results", [])


def run_suite(exe, workspace, config, command, out_dir, cwd):
    """설치판 EXE 로 한 전체 실행을 수행하고 결과 근거를 모은다."""
    from bellalunauto.app import completed_report
    from core import automation_health as health

    log_path = Path(out_dir) / f"{command}.log"
    args = [str(exe), "--workspace", str(workspace)]
    if config:
        args += ["--config", str(config)]
    args.append(command)
    started = time.time()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write(f"# command: {args}\n# cwd: {cwd}\n# started: {started_at}\n")
        log.flush()
        proc = subprocess.run(args, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, env=env)
    ended_at = datetime.now().astimezone().isoformat(timespec="seconds")
    reports = Path(workspace) / "Reports"
    if command == "run-regression":
        report = health.latest_full_regression(str(reports), since=started - 1)
    else:
        report = completed_report(reports, command, started - 1)
    result = {"command": command, "args": args, "cwd": str(cwd), "exit_code": proc.returncode,
              "started": started_at, "ended": ended_at,
              "minutes": round((time.time() - started) / 60, 1),
              "log": str(log_path), "log_sha256": sha256(log_path),
              "report": report, "completed": bool(report)}
    if report:
        result["report_sha256"] = sha256(report["path"])
        meta, rows = _report_rows(report["path"])
        result["meta"] = {k: meta.get(k) for k in ("execution_mode", "chain_completed", "command")}
        result["tc_verdicts"] = {row.get("tc_id"): row.get("verdict") for row in rows}
        if command == "run-winupdate":
            result["wu_target"] = wu_target(rows)
    result["snapshot"] = snapshot(workspace, started - 1,
                                  Path(out_dir) / "snapshots" / command)
    state = Path(workspace) / "work" / "regression_state.json"
    if state.is_file():
        result["regression_state"] = json.loads(state.read_text(encoding="utf-8"))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="설치판 기본기능·실시간 WU 전체 실행 검증")
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--build-info", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--config", type=Path, help="기본값: 작업 폴더의 config.json")
    parser.add_argument("--out", required=True, type=Path, help="비어 있거나 없는 실행 기록 폴더")
    parser.add_argument("--suites", default="run-regression,run-winupdate")
    args = parser.parse_args(argv)

    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error(f"실행 기록 폴더가 비어 있지 않습니다: {out}")
    out.mkdir(parents=True, exist_ok=True)
    config = args.config or (args.workspace / "config.json")
    cwd = out / "cwd"
    cwd.mkdir()
    verification = {"tool": "tools/run_installed_suites.py",
                    "created": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "exe": str(args.exe), "workspace": str(args.workspace),
                    "config": str(config), "cwd": str(cwd),
                    "install": verify_install(args.exe, args.build_info),
                    "runs": []}
    path = out / "verification.json"

    def save():
        path.write_text(json.dumps(verification, ensure_ascii=False, indent=1), encoding="utf-8")

    save()
    if not verification["install"]["ok"]:
        print("[FAIL] 설치 파일이 build-info 와 다릅니다. 실행하지 않습니다.")
        return 2
    for command in [c.strip() for c in args.suites.split(",") if c.strip()]:
        print(f"[{datetime.now():%H:%M:%S}] {command} 시작", flush=True)
        verification["current"] = command
        save()
        result = run_suite(args.exe, args.workspace, config, command, out, cwd)
        verification["runs"].append(result)
        save()
        print(f"[{datetime.now():%H:%M:%S}] {command} 종료: exit={result['exit_code']} "
              f"completed={result['completed']} "
              f"verdicts={(result.get('report') or {}).get('verdicts')}", flush=True)
    verification.pop("current", None)
    verification["finished"] = datetime.now().astimezone().isoformat(timespec="seconds")
    save()
    return 0 if all(run["completed"] for run in verification["runs"]) else 1


if __name__ == "__main__":
    sys.exit(main())
