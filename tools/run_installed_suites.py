# -*- coding: utf-8 -*-
"""설치판 EXE로 승인받은 기본기능·WU 묶음 또는 WF/XIPL 단독 TC를 실행한다.

REQ-DIST-004 의 최종 실행 검증 도구다. 하는 일:

1. 설치 폴더의 EXE 와 모든 파일이 `build-info.json` 의 크기·SHA256 과 같은지 대조한다.
2. 설치 폴더와 작업 폴더 밖 CWD에서 선택한 명령만 실행하고 출력 전체를 로그로 남긴다.
3. 실행마다 작업 폴더에서 새로 생긴 Reports/Evidence/Log 파일을 복사하고 SHA256 을
   다시 대조한다(다음 실행이 같은 이름의 증거를 덮어쓰기 전에 보존한다).
4. 새 리포트인지(전체는 완료 표식, 단독은 명령·TC 일치)와 WU 목표를 기록한다.
   제품 판정의 배포 수용 여부는 release_gate.py --installed-verification으로 별도 확인한다.

판정 기준은 바꾸지 않는다. 리포트가 없거나 조기 중단이면 그대로 미완료로 기록한다.

사용 예:
    python tools/run_installed_suites.py --exe "D:/설치 폴더/BellalunAuto.exe" \
        --build-info "D:/설치 폴더/build-info.json" --workspace "D:/작업 폴더" \
        --out "D:/실행 기록/run-01" --suites run-winupdate
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
#: 사람이 직접 하는 범위(REQ-VERDICT-002, 판정 SKIP). 목표 판정에서 빼고 나머지 10건의 PASS 를 요구한다.
WU_MANUAL = {"TC_WindowsUpdate_01", "TC_WindowsUpdate_12", "TC_WindowsUpdate_13"}
SNAPSHOT_DIRS = ("Reports", "Evidence", "Log")
SINGLE_COMMANDS = {
    **{f"run-wf{i:02}": f"TC_Basic_WorkFlow_{i:02}" for i in range(1, 17)},
    **{f"run-xipl-{i:02}": f"TC_XIPL_compatibility_{i:02}" for i in range(1, 8)},
}


def validate_selection(suites, expected_tcs):
    """범위를 빠뜨렸거나 단독 명령과 TC가 다르면 제품 실행 전에 거부한다."""
    commands = [c.strip() for c in suites.split(",") if c.strip()]
    full = {"run-regression", "run-winupdate"}
    if commands and len(commands) == len(set(commands)) and set(commands) <= full:
        if not expected_tcs:
            return commands
    if (len(commands) == 1 and commands[0] in SINGLE_COMMANDS
            and list(expected_tcs) == [SINGLE_COMMANDS[commands[0]]]):
        return commands
    raise ValueError("--suites에 전체 묶음을 지정하거나 단독 명령 하나와 맞는 --expected-tc를 지정하세요")


def selected_report(reports_dir, command, since, expected_tcs):
    """선택 TC와 실행 명령이 일치하는 새 리포트만 찾는다."""
    for path in sorted(Path(reports_dir).glob("Result_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True):
        if path.stat().st_mtime < since:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        recorded_command = str((data.get("meta") or {}).get("command") or "").split()
        rows = data.get("results") or []
        ids = {row.get("tc_id") for row in rows if str(row.get("tc_id", "")).startswith("TC_")}
        if not recorded_command or recorded_command[-1] != command or ids != set(expected_tcs):
            continue
        verdicts = {}
        for row in rows:
            verdict = row.get("verdict", "UNKNOWN")
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
        return {"path": str(path), "verdicts": verdicts, "tc_count": len(rows)}
    return None

#: `--clean-env` 에서 Windows 기본값 외에 남기는 환경 변수.
#  XIPL_PATH 같은 제품 등록 변수도 일부러 뺀다. 줄어든 환경에서 시작돼도 설치판이
#  Viewer 실행 전에 레지스트리 값으로 보충하는지(core/product_env.py)를 함께 확인한다.
KEEP_ENV = {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "TEMP", "TMP",
            "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "ALLUSERSPROFILE",
            "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES",
            "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "PUBLIC", "HOMEDRIVE",
            "HOMEPATH", "USERNAME", "USERDOMAIN", "COMPUTERNAME", "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "PROCESSOR_LEVEL",
            "PROCESSOR_REVISION", "OS", "SESSIONNAME", "LOGONSERVER", "DRIVERDATA"}
#: 다른 PC에 깨진 Python이 있어도 설치판이 영향받지 않는지 보려고 일부러 넣는 경로.
POISON_DIR = r"C:\BellalunAuto-clean-env-no-such-dir"


def clean_environment(base=None):
    """Python·Git·Node가 없는 PC를 흉내 낸 최소 환경 변수.

    PATH는 Windows 기본값만 둔다. PYTHONHOME/PYTHONPATH는 존재하지 않는 경로로
    채워, 설치판 EXE가 PC의 다른 Python 설정을 읽지 않는지도 함께 확인한다.
    """
    base = os.environ if base is None else base
    env = {k: v for k, v in base.items() if k.upper() in KEEP_ENV}
    root = next((v for k, v in env.items() if k.upper() == "SYSTEMROOT"), r"C:\Windows")
    env["PATH"] = ";".join([root + r"\system32", root, root + r"\System32\Wbem",
                            root + r"\System32\WindowsPowerShell\v1.0",
                            root + r"\System32\OpenSSH"])
    env["PYTHONHOME"] = POISON_DIR + r"\home"
    env["PYTHONPATH"] = POISON_DIR + r"\path"
    return env


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
    """WU_01/12/13 은 SKIP, 나머지 10건은 모두 PASS 인지(릴리스 게이트와 같은 기준).

    없는 행은 PASS 가 아니고, 사람 전용 밖의 SKIP 도 PASS 가 아니다.
    """
    by_id = {row.get("tc_id"): row.get("verdict") for row in rows}
    not_pass = [(tc, by_id.get(tc) or "MISSING") for tc in WU_IDS
                if by_id.get(tc) != ("SKIP" if tc in WU_MANUAL else "PASS")]
    return {"met": not not_pass, "required": len(WU_IDS) - len(WU_MANUAL),
            "passed": sum(1 for tc in WU_IDS
                          if tc not in WU_MANUAL and by_id.get(tc) == "PASS"),
            "not_pass": not_pass,
            "manual_scope": {tc: by_id.get(tc) or "MISSING" for tc in sorted(WU_MANUAL)}}


def _report_rows(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("meta") or {}, data.get("results", [])


def run_suite(exe, workspace, config, command, out_dir, cwd, clean_env=False, expected_tcs=()):
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
    env = dict(clean_environment() if clean_env else os.environ, PYTHONIOENCODING="utf-8")
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write(f"# command: {args}\n# cwd: {cwd}\n# started: {started_at}\n")
        log.flush()
        proc = subprocess.run(args, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, env=env)
    ended_at = datetime.now().astimezone().isoformat(timespec="seconds")
    reports = Path(workspace) / "Reports"
    if command == "run-regression":
        report = health.latest_full_regression(str(reports), since=started - 1)
    elif command == "run-winupdate":
        report = completed_report(reports, command, started - 1)
    else:
        report = selected_report(reports, command, started - 1, expected_tcs)
    result = {"command": command, "args": args, "cwd": str(cwd), "exit_code": proc.returncode,
              "started": started_at, "ended": ended_at,
              "minutes": round((time.time() - started) / 60, 1),
              "log": str(log_path), "log_sha256": sha256(log_path),
              "report": report, "completed": bool(report)}
    if report:
        result["report_sha256"] = sha256(report["path"])
        meta, rows = _report_rows(report["path"])
        result["meta"] = {k: meta.get(k) for k in ("execution_mode", "chain_completed", "command",
                                                   "source_commit", "source_dirty",
                                                   "source_identity_origin")}
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
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="설치판에서 승인받은 묶음 또는 단독 TC 실행 기록")
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--build-info", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--config", type=Path, help="기본값: 작업 폴더의 config.json")
    parser.add_argument("--out", required=True, type=Path, help="비어 있거나 없는 실행 기록 폴더")
    parser.add_argument("--suites", required=True, help="승인받은 실행 명령(여러 묶음은 쉼표로 구분)")
    parser.add_argument("--expected-tc", action="append", default=[], help="단독 실행의 TC ID")
    parser.add_argument("--clean-env", action="store_true",
                        help="PATH를 Windows 기본값만 두고 Python 관련 변수를 깨진 값으로 바꿔 실행")
    args = parser.parse_args(argv)
    args.exe, args.build_info, args.workspace = args.exe.resolve(), args.build_info.resolve(), args.workspace.resolve()
    if args.config:
        args.config = args.config.resolve()
    try:
        commands = validate_selection(args.suites, args.expected_tc)
    except ValueError as error:
        parser.error(str(error))

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
                    "build_info": str(args.build_info.resolve()),
                    "build_info_sha256": sha256(args.build_info),
                    "selected_commands": commands, "expected_tcs": args.expected_tc,
                    "config": str(config), "cwd": str(cwd), "clean_env": args.clean_env,
                    "install": verify_install(args.exe, args.build_info),
                    "runs": []}
    path = out / "verification.json"

    def save():
        path.write_text(json.dumps(verification, ensure_ascii=False, indent=1), encoding="utf-8")

    save()
    if not verification["install"]["ok"]:
        print("[FAIL] 설치 파일이 build-info 와 다릅니다. 실행하지 않습니다.")
        return 2
    for command in commands:
        print(f"[{datetime.now():%H:%M:%S}] {command} 시작", flush=True)
        verification["current"] = command
        save()
        result = run_suite(args.exe, args.workspace, config, command, out, cwd,
                           clean_env=args.clean_env, expected_tcs=args.expected_tc)
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
