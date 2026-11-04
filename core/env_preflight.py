# -*- coding: utf-8 -*-
"""실행 전 PC 환경 점검과 검증된 환경 대조 (조회 전용).

`core.preflight`가 제품 전제(XIPL·SQL·DB·패키지)를 본다면, 이 모듈은 **PC 상태**
중 자동화 결과를 흔드는 것들을 시작 전에 한 번에 모아 보여 준다. 실행 중간에
드러나면 "제품 FAIL"로 오인되는 것들이다(작업표시줄이 버튼을 가림, USB 없음으로
WU_09 단계 SKIP, 재부팅 대기 중인 Update, 메모리 부족 등).

각 항목은 다음 dict다.

    {"key", "label", "level": "OK"|"WARN"|"BLOCK", "actual", "expected",
     "blocks_run": bool, "hint"}

`level == "BLOCK"`이고 `blocks_run`이 True인 항목이 하나라도 있으면 실행을
막는다(`result["blocked"]`). WARN은 기록만 한다. BLOCK은 이미 다른 곳에서 실행을
막는 조건(해상도·DPI는 run.py 환경 gate, 작업 폴더 `%`는 bellalunauto 실행 전
거부)과 1 GiB 미만 메모리에만 쓴다.

조회는 모두 읽기 전용이다. Viewer를 띄우거나 화면 해상도를 바꾸지 않는다
(`display.normalize`는 `enforce=False`로만 부른다). ctypes는 공용
`ctypes.windll.<dll>` 함수 객체의 `argtypes`/`restype`을 바꾸지 않도록 이 모듈
전용 `WinDLL` 인스턴스를 쓴다 — 공용 객체를 바꾸면 다른 모듈의 호출이 깨진다.

실행: `python -m core.env_preflight [--config config.json] [--work-dir <경로>]`
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as _dt
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

from core import environment_match
from core.environment_match import probe_value

OK, WARN, BLOCK = "OK", "WARN", "BLOCK"

#: 메모리 여유 기준(바이트). 미만이면 WARN / BLOCK.
MEMORY_WARN_BYTES = 2 * 1024 ** 3
MEMORY_BLOCK_BYTES = 1 * 1024 ** 3

#: 시계 정상 범위. 이보다 이른 연도는 CMOS 배터리·시간 동기화 이상으로 본다.
CLOCK_MIN_YEAR = 2024
CLOCK_MAX_YEAR = 2100
#: 방금 쓴 임시 파일의 수정 시각과 시스템 시각의 허용 차이(초).
CLOCK_SKEW_LIMIT_SECONDS = 5 * 60

#: 외부 조회(파일 버전 PowerShell) 시간 상한(초).
PROBE_TIMEOUT_SECONDS = 15

REBOOT_PENDING_KEYS = (
    ("Windows Update",
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"),
    ("Component Based Servicing",
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"),
)

USB_SKIP_TEXT = "WU_09 USB 단계 SKIP 예정"


def _item(key, label, level, actual, expected, hint="", blocks_run=None):
    return {"key": key, "label": label, "level": level, "actual": actual,
            "expected": expected,
            "blocks_run": (level == BLOCK) if blocks_run is None else bool(blocks_run),
            "hint": hint if level != OK else ""}


def _unknown(key, label, expected):
    return _item(key, label, WARN, "조회 불가", expected,
                 "이 PC에서 값을 읽지 못했습니다. 기록만 남기고 실행은 계속합니다.")


# ---------------------------------------------------------------- 실제 조회

if os.name == "nt":
    import ctypes.wintypes as _w

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", _w.DWORD), ("dwMemoryLoad", _w.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    class APPBARDATA(ctypes.Structure):
        _fields_ = [("cbSize", _w.DWORD), ("hWnd", _w.HWND),
                    ("uCallbackMessage", _w.UINT), ("uEdge", _w.UINT),
                    ("rc", _w.RECT), ("lParam", _w.LPARAM)]

    _GlobalMemoryStatusEx = _k32.GlobalMemoryStatusEx
    _GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
    _GlobalMemoryStatusEx.restype = _w.BOOL

    _SHAppBarMessage = _shell32.SHAppBarMessage
    _SHAppBarMessage.argtypes = [_w.DWORD, ctypes.POINTER(APPBARDATA)]
    _SHAppBarMessage.restype = ctypes.c_size_t

ABM_GETSTATE = 0x4
ABS_AUTOHIDE = 0x1


def real_memory():
    """`{"avail": bytes, "total": bytes}`."""
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not _GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"avail": int(status.ullAvailPhys), "total": int(status.ullTotalPhys)}


def real_taskbar_autohide():
    data = APPBARDATA()
    data.cbSize = ctypes.sizeof(APPBARDATA)
    return bool(int(_SHAppBarMessage(ABM_GETSTATE, ctypes.byref(data))) & ABS_AUTOHIDE)


def real_reboot_pending():
    """재부팅 대기 표시가 있는 키의 이름 목록(없으면 빈 목록)."""
    import winreg
    found = []
    for name, path in REBOOT_PENDING_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
                found.append(name)
        except FileNotFoundError:
            continue
    return found


def real_clock_skew_seconds():
    """방금 만든 임시 파일의 수정 시각 - 현재 시각(초)."""
    fd, path = tempfile.mkstemp(prefix="bellalun_clock_", suffix=".tmp")
    try:
        os.write(fd, b"0")
        os.close(fd)
        return os.path.getmtime(path) - time.time()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def real_display(cfg):
    """`display.normalize`를 조회 전용(`enforce=False`)으로 부른다."""
    from core import display
    spec = dict((cfg or {}).get("display") or {})
    spec["enforce"] = False
    return display.normalize(dict(cfg or {}, display=spec))


def _with_timeout(fn, timeout=PROBE_TIMEOUT_SECONDS):
    """`fn()`을 별도 스레드에서 실행하고 `timeout`초가 지나면 None."""
    box = {}

    def target():
        try:
            box["value"] = fn()
        except Exception:
            box["value"] = None

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    return box.get("value")


def real_viewer_version(cfg):
    exe = ((cfg or {}).get("viewer") or {}).get("exe")
    if not exe or not os.path.exists(exe):
        return None
    from core import sysinfo
    return _with_timeout(lambda: sysinfo.file_version(exe))


def real_probe(cfg):
    """실제 PC를 조회하는 probe. 값은 필요할 때만 호출되는 함수다."""
    from core import usb_media
    return {
        "display": lambda: real_display(cfg),
        "taskbar_autohide": real_taskbar_autohide,
        "usb_drive": usb_media.find_usb_drive,
        "reboot_pending": real_reboot_pending,
        "now": _dt.datetime.now,
        "clock_skew_seconds": real_clock_skew_seconds,
        "memory": real_memory,
        "os_edition": environment_match.real_os_edition,
        "build_ubr": environment_match.real_build_ubr,
        "viewer_version": lambda: real_viewer_version(cfg),
    }


# ---------------------------------------------------------------- 항목 판정

def _display_expected(cfg):
    spec = (cfg or {}).get("display") or {}
    return (int(spec.get("width", 1920)), int(spec.get("height", 1080)),
            int(spec.get("expected_dpi", 96)))


def check_display(shown, cfg=None):
    """해상도·DPI 두 항목. run.py 환경 gate가 FAIL로 막는 조건이므로 BLOCK."""
    width, height, dpi = _display_expected(cfg)
    if not shown:
        return [_unknown("resolution", "화면 해상도", f"{width}x{height}"),
                _unknown("dpi", "Windows 배율(DPI)", f"{dpi} DPI")]
    actual = tuple(shown.get("actual") or ())
    res_text = f"{actual[0]}x{actual[1]}" if len(actual) == 2 else "조회 불가"
    items = [_item("resolution", "화면 해상도",
                   OK if actual == (width, height) else BLOCK, res_text,
                   f"{width}x{height}",
                   f"Windows 디스플레이에서 주 모니터를 {width}x{height}으로 설정하세요.")]
    got_dpi = shown.get("dpi")
    items.append(_item("dpi", "Windows 배율(DPI)",
                       OK if got_dpi == dpi else BLOCK,
                       f"{got_dpi} DPI" if got_dpi is not None else "조회 불가",
                       f"{dpi} DPI (100%)",
                       "Windows 배율을 100%로 설정하세요(변경 후 로그아웃 필요)."))
    return items


def check_taskbar(autohide):
    if autohide is None:
        return _unknown("taskbar_autohide", "작업표시줄 자동 숨김", "꺼짐")
    return _item("taskbar_autohide", "작업표시줄 자동 숨김",
                 WARN if autohide else OK, "켜짐" if autohide else "꺼짐", "꺼짐",
                 "자동 숨김 작업표시줄이 화면 하단 버튼 위로 나타날 수 있습니다. 기록만 남깁니다.")


def check_usb(drive):
    return _item("usb_drive", "이동식 드라이브",
                 OK if drive else WARN, drive or "없음", "연결됨",
                 f"{USB_SKIP_TEXT} — 이동식 드라이브를 연결하면 WU_09 USB Export·Import까지 수행합니다.")


def check_reboot_pending(found):
    if found is None:
        return _unknown("reboot_pending", "Windows Update 재부팅 대기", "없음")
    return _item("reboot_pending", "Windows Update 재부팅 대기",
                 WARN if found else OK, ", ".join(found) if found else "없음", "없음",
                 "재부팅 대기 중에는 실행 도중 Update 재시작이 끼어들 수 있습니다. "
                 "가능하면 재부팅 후 실행하세요.")


def check_clock(now, skew_seconds):
    problems = []
    if now is None:
        problems.append("현재 시각 조회 불가")
    elif not CLOCK_MIN_YEAR <= now.year <= CLOCK_MAX_YEAR:
        problems.append(f"연도 {now.year}")
    if skew_seconds is not None and abs(skew_seconds) > CLOCK_SKEW_LIMIT_SECONDS:
        problems.append(f"파일 시각 차이 {skew_seconds:+.0f}초")
    actual = now.strftime("%Y-%m-%d %H:%M:%S") if now else "조회 불가"
    if problems:
        actual += " (" + ", ".join(problems) + ")"
    return _item("clock", "시스템 시계", WARN if problems else OK, actual,
                 f"{CLOCK_MIN_YEAR}~{CLOCK_MAX_YEAR}년, 파일 시각 차이 "
                 f"{CLOCK_SKEW_LIMIT_SECONDS // 60}분 이내",
                 "시계가 틀리면 Study 날짜·Today 검색·로그 시각 대조가 어긋납니다. "
                 "Windows 시간 동기화를 확인하세요.")


def check_memory(memory):
    if not memory or memory.get("avail") is None:
        return _unknown("memory", "사용 가능 메모리", "2 GiB 이상")
    avail = int(memory["avail"])
    level = BLOCK if avail < MEMORY_BLOCK_BYTES else WARN if avail < MEMORY_WARN_BYTES else OK
    total = memory.get("total")
    actual = f"{avail / 1024 ** 3:.1f} GiB"
    if total:
        actual += f" / 전체 {int(total) / 1024 ** 3:.1f} GiB"
    return _item("memory", "사용 가능 메모리", level, actual,
                 f"{MEMORY_WARN_BYTES / 1024 ** 3:.0f} GiB 이상 "
                 f"({MEMORY_BLOCK_BYTES / 1024 ** 3:.0f} GiB 미만이면 실행 차단)",
                 "다른 프로그램을 닫아 메모리를 확보한 뒤 실행하세요. Viewer 영상 처리 중 "
                 "메모리가 부족하면 처리 지연이 제품 FAIL처럼 보입니다.")


def check_work_dir(work_dir):
    """작업 폴더 경로 자체진단. 판정은 `bellalunauto.app`의 기존 구현을 그대로 쓴다.

    - `%` 포함: bellalunauto가 제품 조작 실행을 시작 전에 거부하는 조건 → BLOCK.
    - 길이 초과: 자체진단만 FAIL로 안내하고 실행은 거부하지 않는다 → WARN.
    """
    from bellalunauto.app import (WORKSPACE_CHAR_FIX, WORKSPACE_PATH_LIMIT,
                                  workspace_path_problem)
    text = str(work_dir)
    items = []
    char_problem = workspace_path_problem(text)
    items.append(_item("work_dir_chars", "작업 폴더 경로 문자",
                       BLOCK if char_problem else OK, char_problem or text, "'%' 없음",
                       WORKSPACE_CHAR_FIX))
    length = len(text)
    items.append(_item("work_dir_length", "작업 폴더 경로 길이",
                       WARN if length > WORKSPACE_PATH_LIMIT else OK,
                       f"{length}자", f"{WORKSPACE_PATH_LIMIT}자 이하",
                       "작업 폴더를 더 짧은 경로로 다시 선택하세요. Viewer Export 증거 경로가 "
                       "Windows 260자 한도를 넘으면 시험이 중간에 실패합니다."))
    return items


def check_environment(env_result):
    """검증된 환경 대조. 미등록은 WARN이며 실행을 막지 않는다."""
    verified = env_result.get("status") == "verified"
    return _item("environment", "검증된 환경 대조", OK if verified else WARN,
                 environment_match.describe(env_result), "verified_environments.json 등록 환경",
                 "전체 실행이 검증되지 않은 환경입니다. FAIL은 환경 차이일 수 있으니 차이 항목과 "
                 "함께 검토하세요.", blocks_run=False)


# ---------------------------------------------------------------- 전체 실행

def run_preflight(cfg, work_dir, probe=None, entries=None):
    """전체 사전 점검.

    반환: `{"items": [...], "blocked": bool, "environment": match 결과,
    "fingerprint": 지문}`. `probe`가 없으면 이 PC를 조회한다.
    """
    cfg = cfg or {}
    if probe is None:
        probe = real_probe(cfg)
    shown = probe_value(probe, "display")
    items = check_display(shown, cfg)
    items.append(check_taskbar(probe_value(probe, "taskbar_autohide")))
    items.append(check_usb(probe_value(probe, "usb_drive")))
    items.append(check_reboot_pending(probe_value(probe, "reboot_pending")))
    items.append(check_clock(probe_value(probe, "now"),
                             probe_value(probe, "clock_skew_seconds")))
    items.append(check_memory(probe_value(probe, "memory")))
    items.extend(check_work_dir(work_dir))

    fp_probe = dict(probe) if hasattr(probe, "keys") else {}
    fp_probe["display"] = shown  # 해상도·DPI는 한 번만 조회한다
    fp = environment_match.fingerprint(fp_probe)
    if entries is None:
        entries = environment_match.load_entries()
    env_result = environment_match.match(fp, entries)
    items.append(check_environment(env_result))

    blocked = any(i["level"] == BLOCK and i["blocks_run"] for i in items)
    return {"items": items, "blocked": blocked, "environment": env_result,
            "fingerprint": fp}


def counts(result):
    out = {OK: 0, WARN: 0, BLOCK: 0}
    for item in result.get("items") or []:
        out[item["level"]] = out.get(item["level"], 0) + 1
    return out


def format_lines(result):
    """콘솔 출력용 한국어 줄 목록."""
    lines = ["실행 전 점검 (조회 전용)"]
    for item in result.get("items") or []:
        lines.append(f"  [{item['level']:<5}] {item['label']}: {item['actual']}"
                     f" (기대: {item['expected']})")
        if item["level"] != OK and item.get("hint"):
            lines.append(f"          해결 방법: {item['hint']}")
    fp = result.get("fingerprint") or {}
    lines.append("  지문: " + ", ".join(
        f"{environment_match.FIELD_LABELS[k]}={fp.get(k) if fp.get(k) is not None else '조회 불가'}"
        for k in environment_match.FIELDS))
    c = counts(result)
    lines.append(f"  요약: OK {c[OK]} / WARN {c[WARN]} / BLOCK {c[BLOCK]}"
                 + (" — 실행 차단" if result.get("blocked") else " — 실행 가능"))
    return lines


def summary_for_report(result):
    """리포트 meta/HTML 실행 환경 표에 넣을 평평한 dict."""
    env = result.get("environment") or {}
    if env.get("status") == "verified":
        env_text = environment_match.describe(env)
    else:
        diffs = "; ".join(d["text"] for d in env.get("differences") or []) or "차이 불명"
        env_text = f"미등록 환경(WARN): 차이 {diffs}"
    c = counts(result)
    summary = {
        "환경 대조": env_text,
        "사전 점검": f"OK {c[OK]} / WARN {c[WARN]} / BLOCK {c[BLOCK]}",
    }
    problems = [f"{i['label']}({i['level']}): {i['actual']}"
                for i in result.get("items") or [] if i["level"] != OK]
    if problems:
        summary["사전 점검 상세"] = "; ".join(problems)
    return summary


def _load_cfg(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m core.env_preflight",
        description="실행 전 PC 점검과 검증된 환경 대조 (조회 전용, Viewer를 띄우지 않음)")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--work-dir", default=None,
                        help="작업 폴더(기본: BELLALUN_WORKSPACE 또는 현재 폴더)")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    cfg = _load_cfg(args.config)
    if cfg is None:
        print(f"설정 파일을 읽지 못해 기본값으로 점검합니다: {args.config}")
        cfg = {}
    work_dir = args.work_dir or os.environ.get("BELLALUN_WORKSPACE") or os.getcwd()
    result = run_preflight(cfg, work_dir)
    print("\n".join(format_lines(result)))
    return 2 if result["blocked"] else 0


if __name__ == "__main__":
    sys.exit(main())
