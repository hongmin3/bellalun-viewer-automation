# -*- coding: utf-8 -*-
"""Windows 알림 배너가 Viewer 를 가리지 않게 알림 센터로 옮긴다 (REQ-FOLLOWUP-005).

화면 오른쪽 아래의 알림 배너는 `ShellExperienceHost.exe` 의 `새 알림` 창
(`Windows.UI.Core.CoreWindow`, 항상 위)이다. 2026-11-15 run699 에서 Defender 의
"Microsoft로 보낼 파일 검토" 배너가 사라지지 않고 떠 있어 회귀를 시작하지
못했고, run690 은 같은 자리의 배너 때문에 WF01 클릭이 막혔다. 알림 표시기를
재시작해도 같은 배너가 다시 떴다.

그래서 제품을 조작하는 동안 이 배너를 보는 즉시 배너 머리의 닫기 버튼
(`DismissButton`, 이름 "이 알림을 알림 센터로 이동")을 UI Automation 으로
누른다. 이 버튼은 알림을 알림 센터로 옮기기만 한다. 알림 내용은 알림 센터에
남고, 알림이 묻는 결정(예: 파일 보내기)은 하지 않는다.

지킬 것:

* 알림 안의 동작 버튼(`VerbButton`: 해제·파일 보내기·검토 등)과 설정 버튼
  (`SettingsButton`)은 누르지 않는다.
* `SystemApps\\ShellExperienceHost_*` 의 `새 알림` 창만 다룬다. 다른 프로그램
  창, OS 알림 설정, Defender 설정은 바꾸지 않는다.
* 알림 제목·본문은 기록하지 않는다(메일 제목 같은 개인 정보가 들 수 있다).
  보낸 앱 이름과 개수만 남긴다.

VXvue 자동화(`VXvue/auto/core/ui.py` `_aim`)는 가린 창을 최소화하며 재시도한다.
알림 배너는 최소화할 수 없는 셸 창이라, 같은 목적을 배너 자체의 닫기 버튼으로
이룬다.
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import subprocess
import threading
import time

TOAST_TITLES = frozenset({"새 알림", "New notification"})
TOAST_CLASS = "Windows.UI.Core.CoreWindow"
HOST_EXE = "shellexperiencehost.exe"
HOST_DIR_MARK = "\\systemapps\\shellexperiencehost_"
TOAST_VIEW_IDS = ("NormalToastView", "PriorityToastView")
DISMISS_ID = "DismissButton"
DISABLE_ENV = "BELLALUN_DISABLE_TOAST_GUARD"

_lock = threading.Lock()

# 배너 하나마다 UIA 로 닫기 버튼만 누른다. 동작 버튼은 찾지도 않는다.
_DISMISS_SCRIPT = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A=[System.Windows.Automation.AutomationElement]
$root=$A::FromHandle([IntPtr]__HWND__)
$p=Get-Process -Id $root.Current.ProcessId -ErrorAction Stop
if($p.Path -notmatch '\\SystemApps\\ShellExperienceHost_[^\\]+\\ShellExperienceHost\.exe$'){throw 'unexpected_host'}
$senders=@(); $failed=0; $views=0
foreach($id in @('NormalToastView','PriorityToastView')){
 $vc=New-Object System.Windows.Automation.PropertyCondition($A::AutomationIdProperty,$id)
 foreach($v in $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$vc)){
  $views++
  $bc=New-Object System.Windows.Automation.AndCondition(
   (New-Object System.Windows.Automation.PropertyCondition($A::AutomationIdProperty,'DismissButton')),
   (New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)))
  $b=$v.FindAll([System.Windows.Automation.TreeScope]::Descendants,$bc)
  if($b.Count -ne 1){$failed++;continue}
  $sc=New-Object System.Windows.Automation.PropertyCondition($A::AutomationIdProperty,'SenderName')
  $s=$v.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$sc)
  try{$b[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke();$senders+=$(if($s){$s.Current.Name}else{''})}catch{$failed++}
 }
}
[pscustomobject]@{views=$views;senders=$senders;failed=$failed} | ConvertTo-Json -Compress
'''

_u32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
_k32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None
if _u32 is not None:
    _u32.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    _u32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    _u32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    _u32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    _u32.IsWindow.argtypes = [w.HWND]
    _u32.IsWindowVisible.argtypes = [w.HWND]
    _u32.FindWindowExW.argtypes = [w.HWND, w.HWND, w.LPCWSTR, w.LPCWSTR]
    _u32.FindWindowExW.restype = w.HWND
    _k32.OpenProcess.restype = w.HANDLE
    _k32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR,
                                                ctypes.POINTER(w.DWORD)]
    _k32.CloseHandle.argtypes = [w.HANDLE]


def _process_path(pid):
    handle = _k32.OpenProcess(0x1000, False, int(pid))   # QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        size = w.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if _k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        _k32.CloseHandle(handle)


def window_info(hwnd):
    """창의 제목·클래스·크기·프로세스 경로. 창이 없으면 None."""
    if _u32 is None or not hwnd or not _u32.IsWindow(hwnd):
        return None
    cls = ctypes.create_unicode_buffer(256)
    _u32.GetClassNameW(hwnd, cls, 256)
    title = ctypes.create_unicode_buffer(256)
    _u32.GetWindowTextW(hwnd, title, 256)
    rect = w.RECT()
    _u32.GetWindowRect(hwnd, ctypes.byref(rect))
    pid = w.DWORD()
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return {"hwnd": int(hwnd), "cls": cls.value, "title": title.value,
            "visible": bool(_u32.IsWindowVisible(hwnd)),
            "rect": (rect.left, rect.top, rect.right, rect.bottom),
            "pid": int(pid.value), "path": _process_path(pid.value)}


def is_toast_info(info):
    """보이는 알림 배너 창인가. 높이 0 인 빈 배너 창은 가림이 아니다."""
    if not info or not info.get("visible"):
        return False
    left, top, right, bottom = info["rect"]
    path = (info.get("path") or "").lower()
    return (info.get("cls") == TOAST_CLASS and info.get("title") in TOAST_TITLES
            and right > left and bottom > top
            and path.endswith("\\" + HOST_EXE) and HOST_DIR_MARK in path)


def is_toast_window(hwnd):
    try:
        return is_toast_info(window_info(hwnd))
    except Exception:                                   # noqa: BLE001
        return False


def visible_toasts():
    """지금 화면에 보이는 알림 배너 창의 hwnd 목록."""
    if _u32 is None:
        return []
    found = []
    for title in sorted(TOAST_TITLES):
        after = None
        while True:
            hwnd = _u32.FindWindowExW(None, after, TOAST_CLASS, title)
            if not hwnd:
                break
            if is_toast_window(hwnd):
                found.append(int(hwnd))
            after = hwnd
    return found


def _run_powershell(script, timeout):
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def dismiss(hwnd, log=None, runner=None, timeout=20):
    """그 배너 창의 알림을 모두 알림 센터로 옮긴다.

    반환: status(dismissed/none/error), views, senders, failed, cleared.
    cleared 는 처리 뒤 창이 더는 보이는 배너가 아닌지다.
    """
    result = {"status": "error", "hwnd": int(hwnd), "views": 0, "senders": [],
              "failed": 0, "cleared": False}
    if not is_toast_window(hwnd):
        result.update(status="none", cleared=True)
        return result
    with _lock:
        try:
            code, out = (runner or _run_powershell)(
                _DISMISS_SCRIPT.replace("__HWND__", str(int(hwnd))), timeout)
            data = json.loads(out.strip().splitlines()[-1]) if code == 0 and out.strip() else {}
            senders = data.get("senders") or []
            if isinstance(senders, str):
                senders = [senders]
            result.update(views=int(data.get("views") or 0), senders=list(senders),
                          failed=int(data.get("failed") or 0))
            if senders:
                result["status"] = "dismissed"
            elif code == 0 and not result["failed"]:
                result["status"] = "none"
        except Exception as exc:                        # noqa: BLE001
            result["error"] = type(exc).__name__
        deadline = time.monotonic() + 2.0
        while True:
            result["cleared"] = not is_toast_window(hwnd)
            if result["cleared"] or time.monotonic() >= deadline:
                break
            time.sleep(0.2)
    if log is not None:
        try:
            log("[toast-guard] Windows 알림 %d개를 알림 센터로 옮김(보낸 앱: %s), 배너 %s%s" % (
                len(result["senders"]), ", ".join(s or "?" for s in result["senders"]) or "-",
                "사라짐" if result["cleared"] else "남아 있음",
                "" if result["status"] != "error" else " — 처리 오류 " + result.get("error", "")))
        except Exception:                               # noqa: BLE001
            pass
    return result


def dismiss_visible(log=None, runner=None):
    """지금 보이는 배너를 모두 처리한다. 처리 결과 목록을 돌려준다."""
    return [dismiss(hwnd, log=log, runner=runner) for hwnd in visible_toasts()]


class toasts_dismissed:                                 # noqa: N801
    """제품을 조작하는 동안 알림 배너를 보는 즉시 알림 센터로 옮긴다.

    `taskbar_autohidden` 과 같은 위치에서 쓴다. 시작할 때 이미 떠 있는 배너도
    처리한다. 같은 배너 창을 2초 안에 다시 처리하지 않는다.

        with toasts_dismissed():
            ...  # UI 자동화
    """

    def __init__(self, interval=1.0, log=print, scan=None, handle=None):
        self.interval = interval
        self.log = log
        self.scan = scan or visible_toasts
        self.handle = handle or (lambda hwnd: dismiss(hwnd, log=self.log))
        self.results = []
        self._stop = threading.Event()
        self._thread = None
        self._last = {}

    def sweep(self):
        now = time.monotonic()
        for hwnd in self.scan():
            if now - self._last.get(hwnd, -1e9) < 2.0:
                continue
            self._last[hwnd] = now
            self.results.append(self.handle(hwnd))

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                self.sweep()
            except Exception:                           # noqa: BLE001
                pass

    def __enter__(self):
        if os.environ.get(DISABLE_ENV) == "1" or _u32 is None:
            return self
        try:
            self.sweep()
        except Exception:                               # noqa: BLE001
            pass
        self._thread = threading.Thread(target=self._loop, name="toast-guard", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 25)
        return False
