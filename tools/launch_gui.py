# -*- coding: utf-8 -*-
"""에이전트·Hub·스크립트가 BellalunAuto 화면을 무인 실행으로 연다 (REQ-FOLLOWUP-003).

명령줄 `--unattended`와 환경 변수 `QA_AUTOMATION_UNATTENDED=1`을 함께 넘긴다. 그래서 회귀가
정상 완주하면 결과 창이 60초 뒤 닫혀 다음 무인 실행을 막지 않는다. 사람이 바탕화면 아이콘으로
연 화면에는 이 신호가 없어 결과 창이 남는다.

잠긴 화면이나 다른 데스크톱에서는 열지 않는다(잠금을 우회하지 않는다). 프로세스 번호와
실행 정보를 `--out` JSON에 남긴다. 화면 조작(버튼 누르기)은 이 도구가 하지 않는다.

사용 예:
    python tools/launch_gui.py --out work/run-01/gui-launch.json
    python tools/launch_gui.py --exe "D:/BellalunAuto/BellalunAuto.exe" --out gui-launch.json
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bellalunauto.auto_close import UNATTENDED_ENV, UNATTENDED_OPTION  # noqa: E402

DEFAULT_EXE = Path(r"C:\Program Files\BellalunAuto\BellalunAuto.exe")


def build_command(exe, workspace):
    return [str(exe), "--workspace", str(workspace), UNATTENDED_OPTION]


def child_environment(base):
    return dict(base, **{UNATTENDED_ENV: "1"})


def input_desktop_is_default():
    """사용자가 로그인해 잠금이 풀린 기본 데스크톱일 때만 True."""
    import ctypes
    import ctypes.wintypes as w
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenInputDesktop.argtypes = (w.DWORD, w.BOOL, w.DWORD)
    user32.OpenInputDesktop.restype = w.HANDLE
    desktop = user32.OpenInputDesktop(0, False, 0x0001)
    if not desktop:
        return False
    try:
        name, size = ctypes.create_unicode_buffer(128), w.DWORD()
        if not user32.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(size)):
            return False
        return name.value.casefold() == "default"
    finally:
        user32.CloseDesktop(desktop)


def main(argv=None):
    parser = argparse.ArgumentParser(description="BellalunAuto 화면을 무인 실행 신호와 함께 연다.")
    parser.add_argument("--exe", default=str(DEFAULT_EXE))
    parser.add_argument("--workspace", help="기본값: EXE 옆 '작업' 폴더")
    parser.add_argument("--out", required=True, help="프로세스 번호와 실행 정보를 쓸 JSON 파일")
    args = parser.parse_args(argv)
    exe = Path(args.exe)
    if not exe.is_file():
        print(f"[FAIL] EXE가 없습니다: {exe}")
        return 2
    if not input_desktop_is_default():
        print("[FAIL] 화면이 잠겼거나 기본 데스크톱이 아닙니다. 잠금을 우회하지 않고 멈춥니다.")
        return 2
    workspace = Path(args.workspace) if args.workspace else exe.parent / "작업"
    argv_out = build_command(exe, workspace)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
             | 0x01000000)  # CREATE_BREAKAWAY_FROM_JOB: 호출한 세션이 끝나도 화면을 닫지 않는다.
    with (out.parent / (out.stem + "-stdout.log")).open("wb") as log:
        process = subprocess.Popen(argv_out, cwd=str(exe.parent), env=child_environment(os.environ),
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=flags, close_fds=True)
    record = {
        "pid": process.pid, "exe": str(exe), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "argv": argv_out, "unattended_signal": {"option": UNATTENDED_OPTION, "environment": f"{UNATTENDED_ENV}=1"},
        "launched": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
