# -*- coding: utf-8 -*-
r"""FAIL·BLOCKED·Viewer 종료 순간의 **주변 증거**를 한 JSON으로 남긴다.

NEXT_WORK.md 3-B(Setting 전 페이지 순회 중 Viewer 종료)와 3-C(`WF_14` 진입에서
`my_settings` 미발견)는 간헐 증상이라, 재현된 그 회차에 주변 상태를 남기지 못하면
원인을 좁힐 근거가 없다. 이 모듈은 다음을 **판정과 무관하게** 수집한다.

* 사건 시각 ±N초의 Viewer 로그 구간(`extract_log_window`)
* Viewer 프로세스의 GDI/USER 핸들 수(`gui_handles`)
* 시스템 가용 메모리(`memory_status`)
* 캡처 직전 전경 창의 프로세스·제목(`foreground_window_info`)과 오염 여부
  (`looks_contaminated`) — 콘솔·다른 앱이 위에 떠 있던 캡처를 판정 근거로
  오인하지 않기 위함
* WER 크래시 덤프 — **새로 탐지하지 않고** `core.automation_health`의
  `find_crash_dumps`/`process_exit_message`를 그대로 재사용한다.

원칙

* 이 모듈은 **판정을 바꾸지 않는다.** 원인 단정도 하지 않는다. 핸들 증가는
  관측값일 뿐 3-B의 확정 원인이 아니다.
* 어떤 함수도 예외를 밖으로 던지지 않는다(`collect_failure_evidence`). 실패는
  해당 항목의 ``error``로 남긴다 — 증거 수집이 회귀를 깨면 본말전도다.
* ctypes는 공유 ``ctypes.windll.*`` 함수의 ``restype``/``argtypes``를 건드리지
  않도록 **모듈 전용** ``WinDLL`` 인스턴스만 쓴다. 다른 모듈의 ctypes 호출
  서명을 바꾸면 무관한 곳이 조용히 깨진다.
* 결과 파일은 Git 제외 대상인 ``Evidence/`` 아래에 둔다. 로그 구간·창 제목에는
  환경·환자 정보가 섞일 수 있으므로 공개 저장소로 옮기지 않는다.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
from datetime import datetime, timedelta


GR_GDIOBJECTS = 0
GR_USEROBJECTS = 1
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

#: 기대 프로세스가 아닌데 전경에 있으면 특히 흔한 오염원(콘솔·터미널·편집기).
CONSOLE_PROCESSES = frozenset({
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe",
    "conhost.exe", "openconsole.exe", "python.exe", "pythonw.exe",
    "py.exe", "code.exe", "notepad.exe",
})

#: Viewer 로그 줄 머리의 시각. `tests/xipl_flows._LOG_LINE_TS`와 같은 형식이다
#: (`[2026/09/08 17:18:08.123] ...`).
LOG_TIMESTAMP = re.compile(
    r"^\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\]")

#: 증거 JSON이 지나치게 커지지 않도록 하는 상한.
MAX_LOG_LINES = 2000
MAX_TITLE_CHARS = 200


# --------------------------------------------------------------------------
# 모듈 전용 DLL — 공유 ctypes.windll 함수 서명을 바꾸지 않는다
# --------------------------------------------------------------------------
_DLLS = {}


def _dll(name):
    if os.name != "nt":
        raise OSError("Windows 전용 기능입니다.")
    if name not in _DLLS:
        lib = ctypes.WinDLL(name, use_last_error=True)
        _configure(name, lib)
        _DLLS[name] = lib
    return _DLLS[name]


def _configure(name, lib):
    """전용 인스턴스에만 서명을 지정한다(64bit 핸들 잘림 방지)."""
    from ctypes import wintypes as w

    if name == "kernel32":
        lib.OpenProcess.restype = w.HANDLE
        lib.OpenProcess.argtypes = (w.DWORD, w.BOOL, w.DWORD)
        lib.CloseHandle.restype = w.BOOL
        lib.CloseHandle.argtypes = (w.HANDLE,)
        lib.QueryFullProcessImageNameW.restype = w.BOOL
        lib.QueryFullProcessImageNameW.argtypes = (
            w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD))
        lib.GlobalMemoryStatusEx.restype = w.BOOL
        lib.GlobalMemoryStatusEx.argtypes = (ctypes.c_void_p,)
    elif name == "user32":
        lib.GetGuiResources.restype = w.DWORD
        lib.GetGuiResources.argtypes = (w.HANDLE, w.DWORD)
        lib.GetForegroundWindow.restype = w.HWND
        lib.GetForegroundWindow.argtypes = ()
        lib.GetWindowThreadProcessId.restype = w.DWORD
        lib.GetWindowThreadProcessId.argtypes = (w.HWND, ctypes.POINTER(w.DWORD))
        lib.GetWindowTextLengthW.restype = ctypes.c_int
        lib.GetWindowTextLengthW.argtypes = (w.HWND,)
        lib.GetWindowTextW.restype = ctypes.c_int
        lib.GetWindowTextW.argtypes = (w.HWND, w.LPWSTR, ctypes.c_int)


def _last_error():
    try:
        return ctypes.get_last_error()
    except Exception:                                  # noqa: BLE001
        return 0


# --------------------------------------------------------------------------
# 프로세스 자원
# --------------------------------------------------------------------------
def gui_handles(pid, *, user32=None, kernel32=None):
    """프로세스의 GDI/USER 객체 수. 실패는 ``error``로 남기고 값은 None.

    ``GetGuiResources``는 실패 시 0을 돌려주므로, 0이면서 last error가 있으면
    실패로 본다(GUI 객체가 정말 0개인 프로세스와 구분).
    """
    out = {"gdi": None, "user": None, "error": None}
    if not pid:
        out["error"] = "pid 없음"
        return out
    handle = None
    try:
        k32 = kernel32 or _dll("kernel32")
        u32 = user32 or _dll("user32")
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            out["error"] = "OpenProcess 실패(pid=%s, WinError %s)" % (
                pid, _last_error())
            return out
        errors = []
        for key, flag in (("gdi", GR_GDIOBJECTS), ("user", GR_USEROBJECTS)):
            # 성공한 호출은 last error를 지우지 않으므로 먼저 0으로 맞춘다
            # (정말 0개인 프로세스를 앞선 호출의 오류 코드로 오판하지 않기 위함).
            ctypes.set_last_error(0)
            value = int(u32.GetGuiResources(handle, flag))
            code = _last_error() if value == 0 else 0
            if value == 0 and code:
                errors.append("%s: WinError %s" % (key, code))
            else:
                out[key] = value
        out["error"] = "; ".join(errors) or None
    except Exception as exc:                           # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if handle:
            try:
                (kernel32 or _dll("kernel32")).CloseHandle(handle)
            except Exception:                          # noqa: BLE001
                pass
    return out


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def memory_status(*, kernel32=None):
    """시스템 물리 메모리·커밋(페이지 파일 포함) 가용량(MB)."""
    out = {"available_mb": None, "total_mb": None, "load_percent": None,
           "commit_available_mb": None, "commit_total_mb": None, "error": None}
    try:
        k32 = kernel32 or _dll("kernel32")
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not k32.GlobalMemoryStatusEx(ctypes.byref(status)):
            out["error"] = "GlobalMemoryStatusEx 실패(WinError %s)" % _last_error()
            return out
        mb = 1024 * 1024
        out.update(available_mb=status.ullAvailPhys // mb,
                   total_mb=status.ullTotalPhys // mb,
                   load_percent=int(status.dwMemoryLoad),
                   commit_available_mb=status.ullAvailPageFile // mb,
                   commit_total_mb=status.ullTotalPageFile // mb)
    except Exception as exc:                           # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out


def handle_growth(page_handles):
    """`read_all`의 ``page_handles``에서 페이지 순서대로 증가량을 요약한다.

    관측 요약일 뿐 원인 판정이 아니다(3-B). 값이 없는 페이지는 건너뛴다.
    """
    rows = [(page, v) for page, v in (page_handles or {}).items()
            if isinstance(v, dict) and v.get("gdi") is not None
            and v.get("user") is not None]
    summary = {"pages": len(page_handles or {}), "measured": len(rows),
               "first": None, "last": None, "gdi_delta": None,
               "user_delta": None, "gdi_per_page": None, "user_per_page": None}
    if not rows:
        return summary
    (first_page, first), (last_page, last) = rows[0], rows[-1]
    summary.update(first={"page": first_page, "gdi": first["gdi"], "user": first["user"]},
                   last={"page": last_page, "gdi": last["gdi"], "user": last["user"]},
                   gdi_delta=last["gdi"] - first["gdi"],
                   user_delta=last["user"] - first["user"])
    if len(rows) > 1:
        steps = len(rows) - 1
        summary["gdi_per_page"] = round(summary["gdi_delta"] / steps, 1)
        summary["user_per_page"] = round(summary["user_delta"] / steps, 1)
    return summary


# --------------------------------------------------------------------------
# 전경 창과 캡처 오염
# --------------------------------------------------------------------------
def _process_image(pid, kernel32):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        raise OSError("OpenProcess 실패(pid=%s, WinError %s)" % (pid, _last_error()))
    try:
        from ctypes import wintypes as w
        size = w.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            raise OSError("QueryFullProcessImageNameW 실패(WinError %s)" % _last_error())
        return buf.value
    finally:
        kernel32.CloseHandle(handle)


def foreground_window_info(*, user32=None, kernel32=None):
    """지금 전경 창의 hwnd·pid·실행 파일명·제목. 실패는 ``error``.

    스크린샷 헬퍼가 **캡처 직전에** 불러 `looks_contaminated`에 넘기도록 설계했다.
    호출 비용은 Win32 호출 몇 번뿐이라 캡처마다 불러도 된다.
    """
    out = {"hwnd": None, "pid": None, "exe": None, "title": None, "error": None}
    try:
        from ctypes import wintypes as w
        u32 = user32 or _dll("user32")
        k32 = kernel32 or _dll("kernel32")
        hwnd = u32.GetForegroundWindow()
        if not hwnd:
            out["error"] = "전경 창 없음(잠금 화면·데스크톱 전환 중일 수 있음)"
            return out
        out["hwnd"] = int(hwnd)
        pid = w.DWORD(0)
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out["pid"] = int(pid.value) or None
        length = max(0, int(u32.GetWindowTextLengthW(hwnd)))
        buf = ctypes.create_unicode_buffer(length + 1)
        u32.GetWindowTextW(hwnd, buf, length + 1)
        out["title"] = buf.value[:MAX_TITLE_CHARS]
        if out["pid"]:
            try:
                out["exe"] = os.path.basename(_process_image(out["pid"], k32))
            except Exception as exc:                   # noqa: BLE001
                out["error"] = "%s: %s" % (type(exc).__name__, exc)
    except Exception as exc:                           # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out


def _norm_exe(name):
    name = os.path.basename(str(name or "")).strip().lower()
    return name if name.endswith(".exe") or not name else name + ".exe"


def looks_contaminated(foreground_info, expected_process_names):
    """캡처 시점 전경 창이 기대 프로세스가 아닌가.

    반환: ``True``(다른 프로세스가 전경 — 그 캡처는 판정 근거로 쓰지 않는다),
    ``False``(기대 프로세스), ``None``(전경 정보를 못 얻어 판단 불가).
    "근거가 없다"와 "근거가 오염됐다"를 구분하려고 None을 False로 접지 않는다.
    """
    info = foreground_info if isinstance(foreground_info, dict) else {}
    exe = _norm_exe(info.get("exe"))
    if not exe:
        return None
    if isinstance(expected_process_names, str):
        expected_process_names = [expected_process_names]
    expected = {_norm_exe(n) for n in (expected_process_names or ()) if n}
    if not expected:
        return None
    return exe not in expected


def contamination_reason(foreground_info, expected_process_names):
    """`looks_contaminated` 판단을 사람이 읽는 한 문장으로."""
    verdict = looks_contaminated(foreground_info, expected_process_names)
    info = foreground_info if isinstance(foreground_info, dict) else {}
    if verdict is None:
        return "전경 창 정보를 얻지 못해 오염 여부를 판단할 수 없습니다(%s)." % (
            info.get("error") or "프로세스명 없음")
    if not verdict:
        return "전경 창이 기대 프로세스(%s)입니다." % info.get("exe")
    kind = ("콘솔·편집기" if _norm_exe(info.get("exe")) in CONSOLE_PROCESSES
            else "다른 앱")
    return "전경 창이 %s(%s, 제목=%r)입니다 — 캡처가 오염됐을 수 있습니다." % (
        kind, info.get("exe"), info.get("title"))


def capture_guard(expected_process_names, *, info_reader=None):
    """스크린샷 직전 호출용: 전경 정보와 오염 판단을 함께 돌려준다. 예외 없음."""
    try:
        info = (info_reader or foreground_window_info)()
    except Exception as exc:                           # noqa: BLE001
        info = {"error": "%s: %s" % (type(exc).__name__, exc)}
    return {"foreground": info,
            "contaminated": looks_contaminated(info, expected_process_names),
            "reason": contamination_reason(info, expected_process_names)}


# --------------------------------------------------------------------------
# Viewer 로그 구간
# --------------------------------------------------------------------------
def parse_log_timestamp(line):
    """Viewer 로그 줄 머리의 시각(naive local). 없으면 None."""
    match = LOG_TIMESTAMP.match(line)
    if not match:
        return None
    raw = match.group(1)
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _as_local_naive(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone().replace(tzinfo=None)
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value))
    if isinstance(value, str):
        return _as_local_naive(datetime.fromisoformat(value))
    raise TypeError("event_time은 datetime/epoch/ISO 문자열이어야 합니다: %r" % (value,))


def decode_log_bytes(data):
    """BOM이 있으면 UTF-16, 아니면 UTF-8 → CP949 순서. (text, encoding)."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        enc = "utf-16-le" if data[:2] == b"\xff\xfe" else "utf-16-be"
        return data[2:].decode(enc, errors="replace"), enc
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    for enc in ("utf-8", "cp949"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8(replace)"


def extract_log_window(log_path, event_time, before=30, after=30, *,
                       parse=parse_log_timestamp, max_lines=MAX_LOG_LINES):
    """사건 시각 ±초 범위의 로그 줄을 돌려준다.

    시각이 없는 줄(스택 트레이스·여러 줄 메시지)은 **바로 앞 시각 있는 줄**에
    붙여 같은 구간으로 본다. 첫 시각 줄보다 앞선 무시각 줄은 시각을 모르므로
    버린다. 파일 끝에 쓰인 순서가 아니라 각 줄의 시각으로 거른다
    (`tests/xipl_flows._log_lines_from`과 같은 이유 — 로그 기록이 버퍼링된다).

    반환: {"path", "found", "encoding", "window": [시작, 끝], "lines",
           "truncated", "error"}
    """
    out = {"path": os.fspath(log_path) if log_path else None, "found": False,
           "encoding": None, "window": None, "lines": [], "truncated": False,
           "error": None}
    try:
        center = _as_local_naive(event_time)
        start = center - timedelta(seconds=float(before))
        end = center + timedelta(seconds=float(after))
        out["window"] = [start.isoformat(timespec="milliseconds"),
                         end.isoformat(timespec="milliseconds")]
        if not log_path or not os.path.isfile(log_path):
            out["error"] = "로그 파일 없음"
            return out
        with open(log_path, "rb") as stream:
            data = stream.read()
        out["found"] = True
        text, out["encoding"] = decode_log_bytes(data)
        current = None
        kept = []
        for line in text.splitlines():
            stamp = parse(line)
            if stamp is not None:
                current = stamp
            if current is not None and start <= current <= end:
                kept.append(line)
        if len(kept) > max_lines:
            # 사건 시각 주변이 중요하므로 앞뒤를 반씩 남긴다.
            half = max_lines // 2
            kept = kept[:half] + ["... (%d줄 생략) ..." % (len(kept) - 2 * half)] + kept[-half:]
            out["truncated"] = True
        out["lines"] = kept
    except Exception as exc:                           # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out


# --------------------------------------------------------------------------
# 증거 묶음
# --------------------------------------------------------------------------
def _crash_info(process_name, since):
    """`automation_health` 재사용. WER 덤프 탐지를 이 모듈에서 다시 구현하지 않는다."""
    from core import automation_health

    info = automation_health.process_exit_message(process_name, since)
    return {"since": datetime.fromtimestamp(since).isoformat(timespec="seconds"),
            **info}


def _safe(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as exc:                           # noqa: BLE001
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _slug(text):
    return re.sub(r"[^0-9A-Za-z._-]+", "_", str(text or "unknown")).strip("_") or "unknown"


def collect_failure_evidence(evidence_dir, *, tc_id, reason, event_time=None,
                             viewer_pid=None, log_path=None, before=30, after=30,
                             process_name="VIEWER", expected_processes=None,
                             crash_since=None, include_crash=True,
                             now=None, readers=None):
    """실패 주변 증거를 ``evidence_dir``에 JSON으로 쓰고 ``(path, payload)``를 돌려준다.

    **절대 예외를 던지지 않는다.** 쓰기에 실패하면 path는 None이고 이유는
    ``payload["write_error"]``에 있다.

    ``crash_since``(epoch 초)는 `automation_health.process_exit_message`의
    ``started``와 같은 뜻이다 — TC 시작 시각을 넘기는 것이 원칙이다. 주지 않으면
    사건 시각에서 ``before``초를 뺀 시각을 쓴다(그보다 오래된 덤프는 이번 사건의
    근거로 쓰지 않는다).

    ``readers``는 시험용 주입점이다: {"handles", "memory", "foreground",
    "log", "crash"} 중 일부를 호출 가능 객체로 바꾼다.
    """
    readers = dict(readers or {})
    payload = {"tc_id": tc_id, "reason": str(reason), "event_time": None,
               "collected": None, "viewer_pid": viewer_pid, "process_name": process_name,
               "note": ("판정과 무관한 주변 증거다. 핸들·메모리 수치는 관측값일 뿐 "
                        "종료 원인으로 단정하지 않는다.")}
    path = None
    try:
        current = now or datetime.now()
        payload["collected"] = _as_local_naive(current).isoformat(timespec="seconds")
        try:
            event = _as_local_naive(event_time if event_time is not None else current)
        except Exception as exc:                       # noqa: BLE001
            payload["event_time_error"] = "%s: %s" % (type(exc).__name__, exc)
            event = _as_local_naive(current)
        payload["event_time"] = event.isoformat(timespec="milliseconds")

        payload["handles"] = _safe(readers.get("handles") or gui_handles, viewer_pid)
        payload["memory"] = _safe(readers.get("memory") or memory_status)
        fg = _safe(readers.get("foreground") or foreground_window_info)
        expected = expected_processes or [process_name]
        payload["foreground"] = fg
        payload["foreground_contaminated"] = looks_contaminated(fg, expected)
        payload["foreground_reason"] = _safe(contamination_reason, fg, expected)
        payload["log"] = _safe(readers.get("log") or extract_log_window,
                               log_path, event, before, after)
        if include_crash:
            since = crash_since if crash_since is not None else (
                event.timestamp() - float(before))
            payload["crash"] = _safe(readers.get("crash") or _crash_info,
                                     process_name, since)
    except Exception as exc:                           # noqa: BLE001
        payload["collect_error"] = "%s: %s" % (type(exc).__name__, exc)

    try:
        os.makedirs(evidence_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(evidence_dir, "failure_%s_%s.json" % (_slug(tc_id), stamp))
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, default=str)
            stream.write("\n")
    except Exception as exc:                           # noqa: BLE001
        payload["write_error"] = "%s: %s" % (type(exc).__name__, exc)
        path = None
    return path, payload
