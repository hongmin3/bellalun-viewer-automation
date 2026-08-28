# -*- coding: utf-8 -*-
"""Bellalun Viewer UI 드라이버.

VIEWER.exe는 MFC(AfxWnd140u) 네이티브 앱이다. 확인해 보니 각 컨트롤이
**MFC 컨트롤 ID**를 그대로 노출하므로(UIA의 AutomationId == 컨트롤 ID),
화면 좌표 대신 컨트롤 ID로 제어할 수 있다. 해상도·테마·모니터 배치가 바뀌어도
깨지지 않으므로 기존 좌표 기반 스크립트보다 안정적이다.

중요: Viewer는 관리자 권한으로 동작한다. 이 모듈을 쓰는 프로세스도
관리자 권한이어야 한다. 그렇지 않으면 Windows UIPI가 합성 입력과
윈도우 메시지를 전부 차단한다(무반응처럼 보인다).
"""

import ctypes
import ctypes.wintypes as w
import time

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

# Keep Win32 control rectangles, mouse coordinates, and screenshots in the
# same physical-pixel coordinate space on 125/150% DPI systems.
try:
    u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # Per-Monitor V2
except Exception:
    try:
        u32.SetProcessDPIAware()
    except Exception:
        pass

WM_SETTEXT, WM_GETTEXT, WM_GETTEXTLENGTH = 0x000C, 0x000D, 0x000E
BM_CLICK = 0x00F5
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
VK = {"F5": 0x74, "F8": 0x77, "ENTER": 0x0D, "TAB": 0x09, "ESC": 0x1B}

_EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)


# --- SendInput (유니코드 타이핑) --------------------------------------
class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(w.ULONG))]


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUT이 64비트에서 32바이트라 union도 32바이트여야 한다.
    # 이 값이 작으면 INPUT 전체 크기가 어긋나 SendInput이 조용히 실패한다.
    _fields_ = [("ki", _KEYBDINPUT), ("padding", ctypes.c_byte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004

u32.SendInput.argtypes = (w.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
u32.SendInput.restype = w.UINT

u32.WindowFromPoint.argtypes = (w.POINT,)
u32.WindowFromPoint.restype = w.HWND
GA_ROOT = 2
u32.GetAncestor.argtypes = (w.HWND, ctypes.c_uint)
u32.GetAncestor.restype = w.HWND


def send_unicode(ch):
    """문자 1개를 유니코드 스캔코드로 입력한다. 전송된 이벤트 수를 반환."""
    sent = 0
    for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
        inp = _INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = _KEYBDINPUT(wVk=0, wScan=ord(ch), dwFlags=flags,
                               time=0, dwExtraInfo=None)
        sent += u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    return sent


def send_ascii(ch):
    """ASCII 문자를 가상키로 입력한다 (SendInput이 막힌 환경의 대비책)."""
    vk = u32.VkKeyScanW(ord(ch))
    if vk == -1:
        return False
    code, shift = vk & 0xFF, (vk >> 8) & 0xFF
    if shift & 1:
        u32.keybd_event(0x10, 0, 0, 0)              # Shift down
    u32.keybd_event(code, 0, 0, 0)
    time.sleep(0.02)
    u32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)
    if shift & 1:
        u32.keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0)
    return True


class Control:
    __slots__ = ("hwnd", "ctrl_id", "cls", "text", "rect", "visible", "depth")

    def __init__(self, hwnd, ctrl_id, cls, text, rect, visible, depth):
        self.hwnd, self.ctrl_id, self.cls = hwnd, ctrl_id, cls
        self.text, self.rect, self.visible, self.depth = text, rect, visible, depth

    @property
    def center(self):
        l, t, r, b = self.rect
        return (l + r) // 2, (t + b) // 2

    def __repr__(self):
        l, t, r, b = self.rect
        return (f"{'  ' * self.depth}id={self.ctrl_id:<6} cls={self.cls:<14} "
                f"text={self.text!r:<24} rect=({l},{t},{r - l}x{b - t}) "
                f"{'' if self.visible else '[hidden]'}")


# ---------------------------------------------------------------------
def _text_of(hwnd):
    n = u32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(n + 2)
    u32.SendMessageW(hwnd, WM_GETTEXT, n + 1, buf)
    return buf.value


def _class_of(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _rect_of(hwnd):
    r = w.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def _rect_contains_point(rect, point):
    """`rect`(l, t, r, b) 가 `point`(x, y) 를 담는지. 다중 모니터 겹침 판정용."""
    left, top, right, bottom = rect
    x, y = point
    return left <= x < right and top <= y < bottom


def _pid_of(hwnd):
    pid = w.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) or None


def _window_at_point(point):
    """그 화면 좌표를 실제로 담고 있는 **최상위** 창의 hwnd (없으면 None).

    `WindowFromPoint` 는 그 좌표의 가장 안쪽(자식) 창을 돌려주므로,
    `SetForegroundWindow` 에 쓸 수 있는 최상위 창까지 `GetAncestor(GA_ROOT)`
    로 올라간다.
    """
    pt = w.POINT(int(point[0]), int(point[1]))
    hwnd = u32.WindowFromPoint(pt)
    if not hwnd:
        return None
    return u32.GetAncestor(hwnd, GA_ROOT) or hwnd


def top_windows(pid):
    """지정 프로세스의 보이는 최상위 창 목록."""
    out = []

    def cb(hwnd, _):
        p = w.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(hwnd):
            out.append(Control(hwnd, u32.GetDlgCtrlID(hwnd), _class_of(hwnd),
                               _text_of(hwnd), _rect_of(hwnd), True, 0))
        return True

    u32.EnumWindows(_EnumProc(cb), 0)
    return out


def children(hwnd, max_depth=4, _depth=1):
    """자식 컨트롤 트리를 평탄화해서 반환한다."""
    out = []

    def cb(child, _):
        out.append(Control(child, u32.GetDlgCtrlID(child), _class_of(child),
                           _text_of(child), _rect_of(child),
                           bool(u32.IsWindowVisible(child)), _depth))
        if _depth < max_depth:
            out.extend(children(child, max_depth, _depth + 1))
        return True

    u32.EnumChildWindows(hwnd, _EnumProc(cb), 0)
    return out


# ---------------------------------------------------------------------
# Windows 셸 창. 이것들이 최전면인 것은 **가림이 아니다.**
#
# `Program Manager`는 데스크톱 자체이고, Viewer를 새로 띄운 직후에는 창이 아직
# 올라오지 않아 최전면이 데스크톱인 정상 순간이 있다. 2026-08-19 회귀에서 이걸
# 가림으로 오판해 로그인을 중단시켜 14개 TC가 연쇄 FAIL했다.
SHELL_WINDOW_TITLES = ("Program Manager",)
SHELL_WINDOW_CLASSES = ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd")


#: `SystemParametersInfoW` 의 포그라운드 잠금 타임아웃 항목.
#  Windows 는 사용자가 다른 창을 쓰는 동안 프로그램이 포커스를 뺏지 못하도록
#  이 시간(ms) 만큼 `SetForegroundWindow` 를 거부한다. UI 자동화는 그 잠금을
#  **일시적으로** 0 으로 두고 바로 되돌린다.
SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x02


def _foreground_lock_timeout():
    """현재 포그라운드 잠금 타임아웃(ms). 읽지 못하면 0 을 돌려준다."""
    value = ctypes.c_uint(0)
    try:
        ok = u32.SystemParametersInfoW(
            SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(value), 0)
    except Exception:                                  # noqa: BLE001
        return 0
    return int(value.value) if ok else 0


def _set_foreground_lock_timeout(ms):
    """포그라운드 잠금 타임아웃을 설정한다. 실패해도 예외를 내지 않는다.

    **되돌리기 위해서만** 쓴다 — `force_foreground` 가 0 으로 낮췄다가
    `finally` 에서 원래 값으로 복원한다. 값을 낮춘 채로 두면 이 PC 를 쓰는
    사람이 다른 작업을 할 때 창이 멋대로 튀어나온다.
    """
    # 이 항목은 값을 **pvParam 자리에 그대로** 넣는다(uiParam 아님).
    try:
        u32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0, ctypes.c_void_p(int(ms)),
            SPIF_SENDCHANGE)
    except Exception:                                  # noqa: BLE001
        pass


#: `SetWindowPos` 로 창을 Z-order 맨 뒤로 보낼 때 쓰는 값.
HWND_BOTTOM = 1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010


class foreground_unlocked:                             # noqa: N801
    """자동화가 도는 동안 **포그라운드 잠금을 풀어 둔다.**

    `force_foreground` 안에서만 잠깐 0 으로 낮췄다 되돌리면, **Viewer 가 새로
    뜨는 순간**에는 잠금이 다시 걸려 있어 새 창이 포그라운드를 잡지 못한다.
    2026-08-28 실측: 이 PC 의 `ForegroundLockTimeout` 이 `2147483647`(INT_MAX)
    이라 `cold_start(force_restart=True)` 로 재기동한 Viewer 가 끝내 올라오지
    못했고, 로그인 직전 게이트가 다섯 번 연속 TC 를 중단시켰다.

    그래서 명령 실행 전체를 감싸 **세션 동안 0 으로 유지**하고, 끝나면 원래
    값으로 되돌린다. 되돌리지 않으면 이 PC 를 쓰는 사람이 다른 작업을 할 때
    창이 멋대로 튀어나온다.

        with foreground_unlocked():
            ...  # UI 자동화
    """

    def __init__(self):
        self.before = 0

    def __enter__(self):
        self.before = _foreground_lock_timeout()
        if not self.before:
            return self
        _set_foreground_lock_timeout(0)
        if _foreground_lock_timeout():
            # **설정이 거부됐다.** `SPI_SETFOREGROUNDLOCKTIMEOUT` 은 호출
            # 프로세스가 포그라운드일 때만 받아들여진다(2026-08-28 실측:
            # 콘솔이 최소화된 상태에서 `SystemParametersInfoW` 가 0 을 돌려줬다).
            # **자기 콘솔 창**을 잠깐 앞으로 올려 조건을 만든 뒤 다시 시도한다 —
            # 남의 창을 건드리는 것이 아니라 이 프로세스의 창이다.
            console = k32.GetConsoleWindow()
            if console:
                u32.SetForegroundWindow(console)
                time.sleep(0.2)
                _set_foreground_lock_timeout(0)
        return self

    def __exit__(self, *exc):
        if self.before:
            _set_foreground_lock_timeout(self.before)
        return False


def push_window_back(hwnd):
    """가리는 창을 **Z-order 맨 뒤로** 보낸다. 최소화도 종료도 하지 않는다.

    `SetForegroundWindow` 는 다른 프로세스가 포그라운드를 쥐고 있으면
    `AttachThreadInput` 과 포그라운드 잠금 해제를 함께 써도 거부될 때가 있다
    (2026-08-28 실측 — 자동화를 띄운 콘솔 창이 계속 포그라운드를 쥐어 로그인이
    다섯 번 연속 막혔다). 그때 **가리는 창을 뒤로 보내면** 포그라운드가 비어
    Viewer 가 올라온다.

    최소화하지 않는 이유: 최소화는 사용자가 창을 잃어버렸다고 느끼고 작업
    표시줄에서 복구해야 한다. Z-order 만 바꾸면 클릭 한 번으로 돌아오고,
    창 크기·위치·상태가 그대로다. `SWP_NOACTIVATE` 라 포커스도 옮기지 않는다.
    """
    try:
        return bool(u32.SetWindowPos(
            hwnd, HWND_BOTTOM, 0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE))
    except Exception:                                  # noqa: BLE001
        return False


def force_foreground(hwnd):
    """`SetForegroundWindow` 가 **무시될 때** 쓰는 표준 우회.

    Windows 는 포그라운드를 쥐고 있지 않은 프로세스의 `SetForegroundWindow` 를
    조용히 거부한다(반환값만 0이고 예외는 없다). 그래서 호출만 하고 넘어가면
    "올렸다고 생각하는데 실제로는 안 올라간" 상태가 된다.

    2026-08-25 실측: Claude Code 데스크톱 앱이 최전면을 쥐고 있어 Viewer 가 끝내
    올라오지 못했고, 그 상태에서 물리 키 입력이 나가 **계정 ID 가 그 앱의
    입력란에 타이핑됐다.**

    두 가지를 함께 쓴다.

    `AttachThreadInput` 으로 최전면 창의 입력 스레드에 우리 스레드를 붙이면 같은
    입력 큐를 공유하게 되어 호출이 받아들여진다(2026-08-25 실측: Claude 앱이
    최전면인 상태에서 **1회 시도로** Viewer 가 올라왔다).

    **널리 쓰이는 "Alt 키 탭" 우회는 쓰지 않는다.** 처음에는 대비책으로 넣었는데,
    Viewer 는 MFC 앱이라 Alt 가 메뉴 활성화로 해석된다. 그 한 번의 Alt 때문에
    Setting 창의 Q.C. 그룹 페이지 5개를 통째로 읽지 못했다(2026-08-25 실측).
    포커스를 얻으려고 **시험 대상에 입력을 주입하면 안 된다.**

    성공 여부는 이 함수가 판정하지 않는다. 호출자(`bring_to_front`)가 실제
    최전면 창을 다시 읽어 확인한다.
    """
    fg = u32.GetForegroundWindow()
    our_tid = k32.GetCurrentThreadId()
    target_tid = u32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    if target_tid and target_tid != our_tid:
        attached = bool(u32.AttachThreadInput(our_tid, target_tid, True))
    lock_timeout = _foreground_lock_timeout()
    if lock_timeout:
        # 포그라운드 **잠금 타임아웃**이 남아 있으면 `AttachThreadInput` 을
        # 붙여도 Windows 가 전환을 거부한다. 0 으로 두는 동안만 허용되므로
        # 값을 읽어 두고 `finally` 에서 **반드시 원래 값으로 되돌린다.**
        _set_foreground_lock_timeout(0)
    try:
        # **최소화됐을 때만** 복원한다. `ShowWindow(hwnd, SW_RESTORE)` 를 무조건
        # 부르면 **최대화된 창이 이전 크기로 줄어든다.** Viewer 는 전체화면으로
        # 쓰는 앱이고 이 저장소의 판정은 창 크기에 딸린 좌표·rect 를 쓰므로,
        # 줄어드는 순간 콘텐츠 패널이 최소 크기(700x400) 밑으로 내려가
        # "패널을 찾지 못했습니다" 가 난다(2026-08-25 실측 — Setting 52페이지째
        # 에서 그렇게 무너졌다).
        #
        # 이 줄은 `bring_to_front` 에 원래 있었지만 **그 함수를 부르는 곳이
        # 없어서** 부작용이 드러난 적이 없었다.
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, 9)                  # SW_RESTORE
        u32.BringWindowToTop(hwnd)
        u32.SetForegroundWindow(hwnd)
    finally:
        if lock_timeout:
            _set_foreground_lock_timeout(lock_timeout)
        if attached:
            u32.AttachThreadInput(our_tid, target_tid, False)


def _is_shell_window(front):
    """최전면 창이 Windows 셸(데스크톱/작업표시줄)인지."""
    if not front:
        return False
    if front.get("title") in SHELL_WINDOW_TITLES:
        return True
    try:
        buf = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(front["hwnd"], buf, 256)
        return buf.value in SHELL_WINDOW_CLASSES
    except Exception:
        return False


class ViewerUi:
    """Viewer 프로세스 1개를 대상으로 하는 드라이버."""

    def __init__(self, process_name="VIEWER"):
        self.process_name = process_name
        self._pid = None

    # --- 프로세스 ------------------------------------------------------
    @property
    def pid(self):
        if self._pid and self._alive(self._pid):
            return self._pid
        self._pid = self._find_pid()
        return self._pid

    def _find_pid(self):
        import subprocess
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Process {self.process_name} -ErrorAction SilentlyContinue "
             f"| Select-Object -First 1).Id"],
            capture_output=True).stdout.decode("utf-8", "replace").strip()
        return int(out) if out.isdigit() else None

    @staticmethod
    def _alive(pid):
        h = k32.OpenProcess(0x1000, False, pid)
        if h:
            k32.CloseHandle(h)
            return True
        return False

    def launch(self, exe_path, wait=15):
        import os
        import subprocess
        # Bellalun creates/cleans Cache, Log and Temp relative to its current
        # working directory.  Always launch from the installation directory so
        # a caller's automation workspace cannot be treated as application
        # runtime storage.
        subprocess.Popen([exe_path], cwd=os.path.dirname(os.path.abspath(exe_path)))
        time.sleep(wait)
        self._pid = None
        return self.pid

    # --- 창 / 컨트롤 ---------------------------------------------------
    def windows(self):
        return top_windows(self.pid) if self.pid else []

    def main_window(self):
        """실제 컨트롤을 담고 있는 가장 큰 창.

        Viewer는 'FrameTransparent'라는 자식 없는 전체화면 오버레이 창을 함께
        띄우므로, 크기만으로 고르면 빈 창을 잡는다. 자식 수를 우선한다.
        """
        wins = self.windows()
        if not wins:
            return None
        return max(wins, key=lambda c: (len(children(c.hwnd, 1)),
                                        (c.rect[2] - c.rect[0]) * (c.rect[3] - c.rect[1])))

    # 메인 화면으로 간주할 최소 크기. 이보다 작은 #32770은 대화상자로 본다.
    MAIN_WINDOW_MIN_AREA = 1_000_000

    def dialog(self, title=None):
        """현재 떠 있는 대화상자.

        Viewer는 두 종류의 팝업을 쓴다.
          - 표준 메시지 박스: #32770 + 제목 있음 (예: 'Information')
          - 앱 커스텀 팝업 : #32770 + 제목 빈 문자열, 내부는 커스텀 렌더링
        후자를 놓치면 이후 모든 조작이 막혀 자동화가 멈춘 것처럼 보이므로,
        제목이 아니라 '메인 창이 아닌 작은 #32770'인지로 판정한다.
        """
        for c in self.windows():
            if c.cls != "#32770":
                continue
            l, t, r, b = c.rect
            area = (r - l) * (b - t)
            if area >= self.MAIN_WINDOW_MIN_AREA:
                continue                      # 메인 화면
            if title is not None and c.text != title:
                continue
            return c
        return None

    # 커스텀 팝업의 확인 버튼으로 쓰이는 컨트롤 ID (실측: 500 = OK)
    DIALOG_OK_IDS = (500, 1, 2)

    def dialog_buttons(self, dlg, min_size=12):
        """대화상자의 실제 클릭 가능한 버튼 (좌 → 우 순서).

        커스텀 팝업에는 크기 0인 숨은 IconButton이 함께 붙어 있다. 이걸 걸러내지
        않으면 좌표 정렬 시 맨 앞에 끼어들어 엉뚱한 버튼을 누르게 된다
        (종료 옵션 팝업에서 실제로 발생).
        """
        out = []
        for c in children(dlg.hwnd, 3):
            if not c.visible:
                continue
            l, t, r, b = c.rect
            if (r - l) < min_size or (b - t) < min_size:
                continue
            if c.cls == "Button":
                out.append(c)
            elif c.cls.startswith("AfxWnd") and c.text in ("TextButton", "IconButton"):
                out.append(c)
        return sorted(out, key=lambda c: c.rect[0])

    def controls(self, window=None, max_depth=5, visible_only=True, all_windows=True):
        """컨트롤 목록. 기본은 프로세스의 모든 최상위 창을 훑는다.

        Viewer는 화면 전환 시 새 최상위 창을 띄우기도 하므로, 한 창만 보면
        컨트롤을 놓친다. hwnd 기준으로 중복을 제거한다.
        """
        if window is not None:
            wins = [window]
        elif all_windows:
            wins = self.windows()
        else:
            win = self.main_window()
            wins = [win] if win else []

        seen, items = set(), []
        for wnd in wins:
            for c in children(wnd.hwnd, max_depth):
                if c.hwnd in seen:
                    continue
                seen.add(c.hwnd)
                items.append(c)
        return [c for c in items if c.visible] if visible_only else items

    @staticmethod
    def combo_value(control):
        """콤보/드롭다운의 실제 표시값.

        커스텀 콤보는 표시 텍스트가 잘려 있고(예: 'Any Moda'), 숨겨진
        자식 Edit(컨트롤 ID 3)에 전체 값이 들어 있다. 그 값을 우선한다.
        """
        for ch in children(control.hwnd, 1):
            if ch.cls == "Edit" and ch.ctrl_id == 3 and ch.text:
                return ch.text
        return control.text

    def by_id(self, ctrl_id, window=None):
        return [c for c in self.controls(window) if c.ctrl_id == ctrl_id]

    def by_text(self, text, window=None, exact=False):
        t = text.lower()
        return [c for c in self.controls(window)
                if (c.text.lower() == t if exact else t in c.text.lower())]

    # --- 조작 ----------------------------------------------------------
    def require_front_for_pointer(self, what="클릭", point=None):
        """포인터 조작 **직전**에 Viewer 가 최전면인지 보장한다.

        `click` 은 `SetCursorPos` + `mouse_event` 로 **실제 마우스**를 움직인다.
        화면 좌표로 누르므로 **그 좌표를 덮고 있는 창이 클릭을 가져간다.**
        컨트롤 ID 로 좌표를 구했다는 사실은 아무 보호가 되지 않는다.

        2026-08-25 실측: Claude Code 앱 창이 Viewer 를 덮고 있어 로그인 클릭이
        전부 그 앱으로 들어갔고, Viewer 는 로그인 화면에 그대로 멈췄다.
        보고서에는 "Patient 화면이 준비되지 않았습니다" 만 남아 원인이 보이지
        않았다.

        **가려진 채로는 누르지 않는다.** 조용히 진행하면 (1) 시험이 무의미해지고
        (2) 사용자의 다른 프로그램을 임의로 클릭하게 된다. 후자가 더 나쁘다.

        비용: 정상 경로는 `foreground_pid()` 한 번(마이크로초)이다.

        **다중 모니터 — `point` 가 그 창의 실제 화면 사각형 밖이면 막지 않는다**
        (2026-08-28 실측). 최전면 창이 **다른 모니터**에 있으면 클릭 좌표를
        전혀 덮지 않으므로 실제로는 위험하지 않다. 그런데도 `bring_to_front()`
        를 부르면 `main_window()` 를 최전면으로 올리는 과정에서 **지금 조작하려는
        다른 최상위 창(예: Q.C 테스트 창)이 그 뒤로 밀릴 수 있다** — 안 눌러도
        되는 걸 누르려다 오히려 대상 창을 가리는 역효과다. `point` 를 안 주면
        (기존 호출부, 키 입력처럼 좌표가 없는 경우) 이 판단을 할 수 없으므로
        **예전처럼 보수적으로** 막는다.
        """
        if self.is_foreground():
            return True
        blocking = self.blocking_window()
        if blocking is None:
            # **가리는 창이 없다** — 최전면이 Windows 셸(데스크톱/작업표시줄)
            # 이거나 화면 전환 중인 순간이다. 클릭이 다른 프로그램으로 갈 위험이
            # 없으므로 **창을 건드리지 않고** 그대로 진행한다.
            #
            # 이 구분을 빼면 정상 상황을 가림으로 오판한다. 2026-08-19 회귀가
            # 바로 그것 때문에 로그인을 중단시켜 14개 TC 가 연쇄 FAIL 했다.
            # 여기서 `bring_to_front()` 를 부르는 것조차 해롭다 — 그것이
            # 시험 대상 창을 재배치한다.
            return True
        if point is not None and not _rect_contains_point(
                _rect_of(blocking["hwnd"]), point):
            return True
        result = self.bring_to_front(point=point)
        if result["ok"]:
            return True
        raise RuntimeError(
            f"{what} 전에 Viewer 를 최전면으로 올리지 못했습니다"
            f"(가린 창: {result['blocking'] or blocking}). 클릭이 다른 "
            f"프로그램으로 들어가므로 중단합니다.")

    def click(self, target, settle=0.4):
        """Control 또는 (x, y)를 클릭한다. **Viewer 가 최전면일 때만** 누른다."""
        x, y = target.center if isinstance(target, Control) else target
        self.require_front_for_pointer("클릭", point=(x, y))
        u32.SetCursorPos(int(x), int(y))
        time.sleep(0.08)
        u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.06)
        u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(settle)

    def double_click(self, target, settle=1.2, gap=0.08):
        """진짜 더블클릭. 두 클릭 사이 간격을 시스템 임계값 안으로 유지한다.

        `click()` 을 두 번 부르면 `settle` 때문에 간격이 수백 ms 로 벌어져 Windows
        가 더블클릭으로 인식하지 않는다(기본 임계값 500ms). 인라인 편집이 열리지
        않아 "편집할 수 없다"고 오판한 적이 있다(2026-08-20 Hospital Code).
        """
        x, y = target.center if isinstance(target, Control) else target
        self.require_front_for_pointer("더블클릭", point=(x, y))
        u32.SetCursorPos(int(x), int(y))
        time.sleep(0.06)
        for _ in range(2):
            u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.03)
            u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(gap)
        time.sleep(settle)

    def hover(self, target, settle=1.5):
        """커서만 올린다(클릭하지 않는다).

        커스텀 렌더 아이콘의 기능을 **툴팁으로** 확인할 때 쓴다. 아이콘 모양 추정은
        이 저장소에서 두 번 틀렸다(2184 를 Send 로 추정했으나 Import Study,
        2196 을 검사 내 검색으로 추정했으나 Pre-send Preview). 파괴적일 수 있는
        버튼은 누르기 전에 이걸로 먼저 확인한다.
        """
        self.require_front_for_pointer("호버")
        x, y = target.center if isinstance(target, Control) else target
        u32.SetCursorPos(int(x), int(y))
        time.sleep(settle)
        return (int(x), int(y))

    def right_click(self, target, settle=0.8):
        """Control 또는 (x, y)를 우클릭한다.

        커스텀 렌더 목록에서 컨텍스트 메뉴를 확인할 때 쓴다. 좌클릭과 같은 방식으로
        물리 입력을 보낸다 — `WM_CONTEXTMENU` 주입은 이 UI 에서 통하지 않는다.
        """
        self.require_front_for_pointer("우클릭")
        x, y = target.center if isinstance(target, Control) else target
        u32.SetCursorPos(int(x), int(y))
        time.sleep(0.08)
        u32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        time.sleep(0.06)
        u32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        time.sleep(settle)

    def drag(self, start, end, duration=.4, settle=.4):
        """Drag between physical screen coordinates."""
        self.require_front_for_pointer("드래그")
        sx, sy = start.center if isinstance(start, Control) else start
        ex, ey = end.center if isinstance(end, Control) else end
        u32.SetCursorPos(int(sx), int(sy))
        time.sleep(.08)
        u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        steps = max(4, int(duration / .03))
        for i in range(1, steps + 1):
            x = sx + (ex - sx) * i / steps
            y = sy + (ey - sy) * i / steps
            u32.SetCursorPos(int(x), int(y))
            time.sleep(duration / steps)
        u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(settle)

    def wheel(self, target, notches, settle=.5):
        """Scroll at a control/point. Positive is up, negative is down."""
        self.require_front_for_pointer("휠 스크롤")
        x, y = target.center if isinstance(target, Control) else target
        u32.SetCursorPos(int(x), int(y))
        time.sleep(.08)
        delta = ctypes.c_ulong(int(notches * 120) & 0xFFFFFFFF).value
        u32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
        time.sleep(settle)

    def click_button(self, hwnd):
        """표준 Button에 BM_CLICK을 보낸다(마우스를 움직이지 않음)."""
        u32.SendMessageW(hwnd, BM_CLICK, 0, 0)
        time.sleep(0.4)

    def set_text(self, control, text):
        u32.SendMessageW(control.hwnd, WM_SETTEXT, 0, ctypes.c_wchar_p(text))
        time.sleep(0.15)

    def get_text(self, control):
        return _text_of(control.hwnd)

    def focus(self, control):
        u32.SetForegroundWindow(control.hwnd)
        time.sleep(0.1)

    def type_text(self, control, text, clear=True, settle=0.3):
        """컨트롤을 클릭해 포커스를 준 뒤 실제 키 입력으로 타이핑한다.

        WM_SETTEXT는 창의 텍스트만 바꿀 뿐 앱이 입력으로 인지하지 못하는 경우가
        있다(비밀번호 필드, 입력 검증이 붙은 필드에서 실제로 발생). 사용자가
        타이핑한 것과 동일한 경로를 쓰는 이 방식이 안전하다.

        **물리 키 입력이므로 Viewer 가 최전면이어야 한다.** 가려져 있으면 입력이
        다른 프로그램으로 들어간다(`require_front` 주석 참고).
        """
        self.require_front("텍스트 입력")
        self.click(control, settle=0.25)
        if clear:
            self.key_combo(0x11, 0x41)          # Ctrl+A
            self.raw_key(0x2E)                  # Delete
        for ch in text:
            self._unicode_char(ch)
            time.sleep(0.02)
        time.sleep(settle)

    @staticmethod
    def _unicode_char(ch):
        """문자 1개 입력. SendInput이 실패하면 가상키 방식으로 대체한다."""
        if send_unicode(ch) == 0:
            send_ascii(ch)

    # `raw_key` / `key_combo` 는 원래 `@staticmethod` 였다. 인스턴스 메서드로
    # 바꾼 이유: 이 둘을 **직접 부르는 곳**이 `core/xipl.py`(Ctrl+O, Ctrl+A,
    # Delete)와 `core/dicom_settings.py`(Home, Enter)에 있는데, 거기에는
    # 최전면 확인이 없었다. 호출부를 하나씩 고치는 대신 **가드를 안쪽에** 두면
    # 새 호출부가 생겨도 자동으로 보호된다. 호출 형태(`ui.raw_key(...)`)는
    # 그대로라 바꿔야 하는 곳이 없다.
    def raw_key(self, vk, settle=0.05):
        self.require_front(f"키 입력(VK {vk:#04x})")
        u32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        u32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(settle)

    def key_combo(self, mod_vk, vk):
        self.require_front(f"키 조합(VK {mod_vk:#04x}+{vk:#04x})")
        u32.keybd_event(mod_vk, 0, 0, 0)
        u32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        u32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        u32.keybd_event(mod_vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.08)

    def key(self, name, settle=0.3):
        """가상 키 입력. **Viewer 가 최전면임을 보장한 뒤** 보낸다.

        예전 주석은 "포커스가 Viewer에 있어야 한다" 였는데, 그 조건을 확인하는
        코드가 없어 가려진 상태에서도 그냥 보냈다(`require_front` 주석 참고).
        """
        self.require_front(f"키 입력({name})")
        vk = VK[name.upper()] if name.upper() in VK else ord(name.upper())
        u32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        u32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(settle)

    def activate(self):
        win = self.main_window()
        if win:
            u32.SetForegroundWindow(win.hwnd)
            time.sleep(0.3)
        return win

    def foreground_window(self):
        """현재 최전면 창의 (hwnd, 제목, 프로세스 ID)."""
        hwnd = u32.GetForegroundWindow()
        if not hwnd:
            return None
        length = u32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        u32.GetWindowTextW(hwnd, buf, length + 1)
        pid = w.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return {"hwnd": hwnd, "title": buf.value, "pid": int(pid.value)}

    def is_foreground(self):
        """최전면 창이 **Viewer 프로세스의 것인지**.

        `main_window()`의 hwnd와 비교하지 않는다. Viewer는 로그인 화면이나
        대화상자에서 다른 최상위 창을 최전면에 두는데, hwnd로 비교하면 그 정상
        상황을 "가려졌다"고 오판해 로그인을 중단시킨다(2026-08-19 실측으로 확인).

        막아야 하는 것은 키 입력이 **다른 프로그램**으로 들어가는 것이므로
        프로세스 동일성으로 판정한다.
        """
        front_pid = self.foreground_pid()
        return bool(front_pid and self.pid and front_pid == self.pid)

    def blocking_window(self):
        """Viewer 를 **가리고 있는 다른 프로세스의 창**. 없으면 None.

        `bring_to_front` 가 쓰던 판정과 같은 규칙을 한 곳에 모은 것이다.
        Windows 셸(데스크톱/작업표시줄)이 최전면인 것은 **가림이 아니다** —
        Viewer 를 새로 띄운 직후에 흔히 나타나는 정상 순간이다.
        """
        front = self.foreground_window()
        if not front or not self.pid:
            return None
        if front["pid"] == self.pid or _is_shell_window(front):
            return None
        return {"title": front["title"], "pid": front["pid"], "hwnd": front["hwnd"]}

    def foreground_pid(self):
        """최전면 창의 프로세스 ID 만 읽는다(제목까지 읽지 않아 싸다).

        `click` 이 클릭마다 부르므로 비용이 중요하다.
        """
        hwnd = u32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = w.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None

    def bring_to_front(self, attempts=6, settle=0.6, point=None):
        """Viewer를 최전면으로 올리고 **실제로 올라왔는지 확인**한다.

        `SetForegroundWindow`는 Windows가 무시할 수 있다(다른 프로세스가 포커스를
        쥐고 있을 때). 그래서 호출만 하고 넘어가면, 가려진 상태에서 물리 키 입력을
        보내 **비밀번호가 다른 창으로 들어간다.**

        올리지 못하면 마지막으로 최전면이던 창 정보를 함께 돌려준다. 호출자가
        "무엇이 가리고 있었는지" 보고할 수 있게 하는 것이 목적이다.

        **`point` 가 있으면 그 좌표를 실제로 담고 있는 우리 창을 올린다** —
        없으면 `main_window()` 를 올린다. `main_window()` 만 올리면 지금 누르려는
        창이 메인 프레임과 **다른 최상위 창**(예: Q.C 테스트 창, XIPL Studio)일 때
        메인 프레임이 그 앞으로 나와 **오히려 대상 창을 가릴 수 있다** — 2026-08-28
        실측: `_qc_recover` 의 Cancel 클릭이 예외 없이 "성공"했는데도 Q.C 테스트
        창이 닫히지 않았다(클릭이 새로 최전면이 된 메인 프레임으로 들어갔다).

        반환: {"ok": bool, "blocking": {...}|None, "attempts": int}
        """
        hwnd = None
        if point is not None:
            candidate = _window_at_point(point)
            if candidate and self.pid and _pid_of(candidate) == self.pid:
                hwnd = candidate
        if hwnd is None:
            win = self.main_window()
            hwnd = win.hwnd if win else None
        if not hwnd:
            return {"ok": False, "blocking": None, "attempts": 0}
        pushed_back = []
        for attempt in range(1, attempts + 1):
            if self.is_foreground():
                return {"ok": True, "blocking": None,
                        "attempts": attempt - 1,
                        "pushed_back": pushed_back or None}
            # `SetForegroundWindow` 만으로는 다른 앱이 최전면을 쥐고 있을 때
            # 거부당한다. `force_foreground` 가 그 잠금을 푼다(주석 참고).
            force_foreground(hwnd)
            time.sleep(settle)
            # **절반을 써도 안 올라오면 가리는 창을 뒤로 보낸다.**
            # 잠금 해제와 `AttachThreadInput` 만으로 뚫리지 않는 경우가 있다
            # (2026-08-28 실측 — 자동화를 띄운 콘솔 창). 최소화·종료가 아니라
            # Z-order 만 낮추므로 사용자가 클릭 한 번으로 되돌릴 수 있다.
            if attempt >= max(1, attempts // 2) and not self.is_foreground():
                blocking = self.blocking_window()
                if blocking and blocking.get("hwnd") not in pushed_back:
                    if push_window_back(blocking["hwnd"]):
                        pushed_back.append(blocking["hwnd"])
                        force_foreground(hwnd)
                        time.sleep(settle)
        return {"ok": self.is_foreground(),
                "blocking": self.blocking_window(), "attempts": attempts,
                "pushed_back": pushed_back or None}

    def require_front(self, what="키 입력"):
        """물리 키 입력 **직전**에 Viewer 가 최전면인지 보장한다.

        `keybd_event` / `SendInput` 은 창을 지정할 수 없다 — **그 순간 최전면인
        창**으로 들어간다. Viewer 가 가려져 있으면 아이디·비밀번호·설정값이
        **다른 프로그램에 타이핑된다.**

        2026-08-25 실측: WF_14 4차 실행에서 로그인이 `service` 를 **다른 창의
        입력란에 쳐 넣었고**, Viewer 는 로그인 화면에 그대로 멈춰 전제 단계가
        FAIL 했다. `bring_to_front()` 는 그때 이미 이 위험을 주석에 적어 두고
        있었지만 **호출하는 곳이 한 군데도 없었다** — 가드를 만들어 두고 연결하지
        않은 것이다.

        올리지 못하면 **무엇이 가리고 있었는지** 담아 예외를 던진다. 조용히
        진행하면 키 입력이 어디로 갔는지 모르게 된다.
        """
        if self.is_foreground():
            return {"ok": True, "blocking": None, "attempts": 0}
        blocking = self.blocking_window()
        if blocking is None:
            # 가리는 창이 없다(셸이 최전면이거나 전환 중). 키가 **다른
            # 프로그램으로 새지는 않는다** — 허공으로 갈 수는 있지만 그것은
            # 호출부의 확인(비밀번호 길이 대조, 로그인 화면 이탈 확인,
            # 설정값 DB 대조)이 잡는다. 여기서 막으면 정상 상황을 오판한다.
            return {"ok": False, "blocking": None, "attempts": 0}
        result = self.bring_to_front()
        if result["ok"]:
            return result
        raise RuntimeError(
            f"{what} 전에 Viewer 를 최전면으로 올리지 못했습니다"
            f"(가린 창: {result['blocking'] or blocking}). 키 입력이 다른 "
            f"프로그램으로 들어가므로 중단합니다.")

    # --- 대기 ----------------------------------------------------------
    def wait_dialog(self, title=None, timeout=20, poll=0.5):
        end = time.time() + timeout
        while time.time() < end:
            d = self.dialog(title)
            if d:
                return d
            time.sleep(poll)
        return None

    def dialog_text(self, dlg):
        """대화상자 문구. 표준 메시지 박스는 Static에서 읽는다.

        커스텀 팝업은 문구를 직접 그리기 때문에 컨트롤에서 읽을 수 없다.
        그 경우 빈 문자열을 반환하므로, 호출부는 capture_dialog()로 캡처 증거를
        남겨 사람이 확인할 수 있게 해야 한다.
        """
        parts = [c.text for c in children(dlg.hwnd, 3)
                 if c.cls == "Static" and c.text]
        return " / ".join(parts)

    def capture_dialog(self, dlg, path):
        """대화상자 영역을 캡처해 증거로 남긴다."""
        import os
        from PIL import ImageGrab
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        ImageGrab.grab(bbox=dlg.rect, all_screens=True).save(path)
        return path

    def dismiss_dialog(self, title=None, timeout=20, evidence_path=None):
        """대화상자를 닫는다. 닫았으면 문구(없으면 '(문구 미노출)')를 반환.

        표준 Button이 없으면 커스텀 버튼(컨트롤 ID 500 등)을 클릭한다.
        """
        d = self.wait_dialog(title, timeout)
        if not d:
            return None

        msg = self.dialog_text(d)
        if evidence_path:
            try:
                self.capture_dialog(d, evidence_path)
            except Exception:
                pass

        buttons = self.dialog_buttons(d)
        # 확인 성격의 버튼을 우선 (ID 500/1/2), 없으면 첫 번째
        buttons.sort(key=lambda c: (c.ctrl_id not in self.DIALOG_OK_IDS,
                                    c.rect[0]))
        for b in buttons:
            if b.cls == "Button":
                self.click_button(b.hwnd)
            else:
                self.click(b, settle=0.5)
            return msg or "(문구 미노출)"
        return msg or "(문구 미노출, 버튼 없음)"

    # --- 로그인 --------------------------------------------------------
    LOGIN_ID_COMBO = 2001
    LOGIN_PW_EDIT = 2002
    LOGIN_BUTTON = 2003

    def at_login_screen(self):
        """로그인 화면 여부. PW 입력 컨트롤(2002, Edit) 존재로 판단한다."""
        return any(c.cls == "Edit" and c.ctrl_id == self.LOGIN_PW_EDIT
                   for c in self.controls())

    def current_login_id(self):
        c = self.by_id(self.LOGIN_ID_COMBO)
        return c[0].text if c else None

    def login(self, user_id, password, timeout=30):
        """로그인하고 성공 여부를 반환한다.

        ID 콤보(2001)는 커스텀 컨트롤이라 텍스트 주입이 통하지 않는다.
        현재 선택된 ID가 다르면 예외를 던져, 잘못된 계정으로 진행하는 것을 막는다.
        (계정 전환이 필요하면 콤보 드롭다운(ID 1)의 항목 지도를 먼저 확보할 것)
        """
        if not self.at_login_screen():
            return True  # 이미 로그인된 상태

        cur = (self.current_login_id() or "").strip()
        # 콤보는 긴 ID를 **잘라서** 보여준다(`TEST_USER_FLOW` -> `TEST_USE`).
        # 그래서 완전일치가 아니라 **접두사**로 본다. 너무 짧은 표시로 오판하지
        # 않도록 최소 길이를 둔다. `service`는 `TEST_USER_FLOW`의 접두사가 아니므로
        # 엉뚱한 계정으로 진행하는 것은 그대로 막힌다.
        want = user_id.strip().lower()
        if cur and not (cur.lower() == want
                        or (len(cur) >= 4 and want.startswith(cur.lower()))):
            raise RuntimeError(
                f"로그인 ID가 '{cur}'로 선택되어 있습니다. 요청한 ID는 '{user_id}'입니다. "
                f"ID 콤보(컨트롤 {self.LOGIN_ID_COMBO})를 먼저 변경하십시오.")

        pw = self.by_id(self.LOGIN_PW_EDIT)
        btn = self.by_id(self.LOGIN_BUTTON)
        if not pw or not btn:
            raise RuntimeError("로그인 컨트롤을 찾지 못했습니다. ui-probe로 화면을 확인하십시오.")

        # 비밀번호는 실제 키 입력으로 넣는다. WM_SETTEXT는 앱이 입력으로
        # 인지하지 못해 조용히 실패하는 경우가 있다(1.0.12에서 실제 발생).
        # 물리 키 입력은 반대로 **유실될 수 있어서** 넣은 뒤 길이를 대조한다
        # (`fill_password` 주석 참고 — 2026-08-24 에 전부 유실된 실측 사례).
        self.last_password_fill = self.fill_password(pw[0], password)
        self.click(btn[0], settle=1.2)

        # **"로그인 화면이 안 보인다"를 성공으로 보지 않는다.**
        #
        # 예전에는 로그인 화면이 연속 2회 안 보이면 True 를 돌려줬다. 그런데
        # 화면 전환 중이나 오류 팝업(잘못된 자격증명)이 떠 있을 때도 로그인
        # 화면의 컨트롤이 열거되지 않는다. 2026-08-25 실측: 비밀번호가 유실돼
        # 로그인이 안 됐는데 `login()` 이 True 를 돌려줬고, 호출부는 로그인된
        # 줄 알고 진행했다(캡처로 확인 — PW 칸이 비어 있고 로그인 화면 그대로).
        #
        # 그래서 **Viewer 화면이 실제로 올라왔다는 긍정 신호**를 요구한다.
        # 전환 중 뜨는 팝업은 걷어내면서 기다린다.
        end = time.time() + timeout
        while time.time() < end:
            if self.dialog():
                self.dismiss_dialog(timeout=2)
            if not self.at_login_screen():
                window = self.main_window()
                if window and len(self.controls(window, max_depth=3)) >= 5:
                    return True
            time.sleep(0.7)
        return False

    def wait_screen_ready(self, timeout=180, poll=1.0, sweep=True):
        """기동 후 **화면이 실제로 올라올 때까지** 기다린다.

        `launch()` 의 고정 대기(기본 15초)만으로는 부족하다. 2026-08-24 실측:
        `reset-environment` 직후 Viewer 가 꺼진 상태에서 `run-xipl-07` 을 단독
        실행했더니, 로그인 화면은 떴지만 아직 입력을 받지 못해 **비밀번호 문자가
        전부 유실**됐다(PW 필드 길이 0). `flows.cold_start` 는 같은 이유로 이미
        `startup_timeout` 만큼 화면을 기다리는데 이 헬퍼에는 그것이 없었다.

        **기다리는 동안 팝업을 계속 걷어낸다**(`sweep`). 기동 직후 뜨는
        `Running in demo mode.` 모달이 로그인 화면을 가리기 때문에, 한 번만 닫고
        기다리면 그 사이에 뜬 팝업에 막혀 그대로 시간 초과된다(2026-08-24 실측:
        180초를 다 쓰고 실패했다). `cold_start` 도 대기 루프 안에서 매 회
        `DialogGuard.sweep` 을 부른다.

        반환: `"login"`(로그인 화면) / `"loaded"`(이미 로그인된 화면) / `""`(시간 초과)
        """
        end = time.time() + timeout
        while time.time() < end:
            if sweep and self.dialog():
                self.dismiss_dialog(timeout=2)
            if self.at_login_screen():
                return "login"
            window = self.main_window()
            if window and len(self.controls(window, max_depth=3)) >= 5:
                return "loaded"
            time.sleep(poll)
        return ""

    #: 비밀번호 타이핑 재시도 횟수. `flows.cold_start` 의 `login_attempts` 와 같은
    #: 이유다 — 포커스가 잡히기 전 물리 키 입력은 유실될 수 있다.
    PW_TYPE_ATTEMPTS = 3

    def fill_password(self, control, password):
        """비밀번호를 넣고, **읽을 수 있을 때만** 들어갔는지 확인한다.

        `type_text` 는 물리 키 입력이라 조용히 유실될 수 있다(2026-08-24 실측:
        콜드 스타트에서 전부 유실됐다). 그래서 넣은 뒤 글자 수를 대조한다.

        **다만 읽을 수 없으면 다시 치지 않는다.** 로그인 화면의 PW 필드는 표준
        `Edit`(`2002`)이지만 password 스타일이라 다른 프로세스의 `WM_GETTEXT` 에는
        **빈 문자열**을 돌려준다. 처음에는 그것을 "유실"로 보고 상한까지 다시 쳤고,
        그래서 **로그인할 때마다 비밀번호를 3번 입력**했다(2026-08-25 사용자 관찰).
        확인할 수 없는 것을 실패로 단정하면 느려지기만 하고 얻는 것이 없다.

        판정 순서
          1. 읽은 길이 == 비밀번호 길이  -> 확인됨(`verified=True`)
          2. 읽은 길이 == 0             -> **확인 불가**(`verified=None`). 다시 치지
                                          않는다. 최종 판정은 `login()` 의
                                          "로그인 화면을 벗어났는가" 가 한다.
          3. 읽히는데 길이가 다르다      -> 실제 유실이다. 그때만 다시 친다.

        **값은 절대 읽어서 로그로 남기지 않는다. 길이만 본다.**
        """
        want = len(password)
        self.require_front("비밀번호 입력")
        self.type_text(control, password)
        got = len(self.get_text(control) or "")
        if got == want:
            return {"attempts": 1, "chars": got, "verified": True}
        if got == 0:
            return {"attempts": 1, "chars": 0, "verified": None,
                    "detail": "PW 필드를 읽을 수 없어 확인하지 않음"
                              "(password 스타일 Edit). 로그인 성공 여부로 판정한다."}
        for attempt in range(2, self.PW_TYPE_ATTEMPTS + 1):
            time.sleep(0.6)
            self.type_text(control, password)
            got = len(self.get_text(control) or "")
            if got == want:
                return {"attempts": attempt, "chars": got, "verified": True}
        return {"attempts": self.PW_TYPE_ATTEMPTS, "chars": got,
                "expected": want, "verified": False}

    def sweep_dialogs(self, rounds=4, timeout=6):
        """떠 있는 안내 팝업을 **없어질 때까지** 닫는다(상한 있음).

        `dismiss_dialog` 을 한 번만 부르면 **연달아 뜨는 팝업**을 놓친다.
        `flows.cold_start` 는 같은 이유로 `watchdog.DialogGuard.sweep` 을 여러
        시점에 부른다. 이 헬퍼는 그 최소판이다.

        반환: 닫은 팝업 문구 목록(없으면 빈 목록).
        """
        closed = []
        wait = timeout
        for _ in range(rounds):
            message = self.dismiss_dialog(timeout=wait)
            if not message:
                break
            closed.append(message)
            wait = 2                # 첫 팝업 뒤에는 짧게만 확인한다
        return closed

    def ensure_ready(self, exe_path=None, user_id=None, password=None,
                     dismiss_demo=True, startup_timeout=180, login_attempts=3):
        """Viewer 기동 → Demo 안내 팝업 닫기 → 로그인까지 한 번에 처리한다.

        **로그인하지 못하면 예외를 던진다.** 예전에는 실패를 `notes` 에만 적고
        그냥 반환했는데, 아무도 그 note 를 읽지 않아 호출부가 로그인 화면에서
        계속 진행했다. 그러면 15초 뒤 `open_main_menu` 가
        `"메인 메뉴 버튼(2015)을 찾지 못했습니다"` 로 죽어 **원인과 무관한
        메시지**가 남는다(2026-08-24 실측). 실패는 실패한 자리에서 드러낸다.
        """
        notes = []
        launched = False
        if not self.pid and exe_path:
            self.launch(exe_path)
            notes.append("Viewer 실행")
            launched = True
        if not self.pid:
            raise RuntimeError("Viewer가 실행되어 있지 않습니다.")
        # **순서가 중요하다.** 기동 팝업을 먼저 걷어내야 로그인 화면이 보인다.
        # 화면을 먼저 기다리면 `Running in demo mode.` 모달에 가려 시간 초과된다.
        if dismiss_demo:
            closed = self.sweep_dialogs(timeout=8)
            if closed:
                notes.append("로그인 전 팝업 닫음: " + "; ".join(closed))
        if launched:
            state = self.wait_screen_ready(timeout=startup_timeout)
            notes.append(f"화면 준비: {state or '시간 초과'}")
            if not state:
                raise RuntimeError(
                    f"Viewer가 {startup_timeout}초 안에 로그인/준비 화면을 "
                    "표시하지 않았습니다. 기동 실패를 로그인 완료로 간주하지 않고 "
                    "안전하게 중단합니다.")
        if user_id and password:
            # **재시도는 타이핑이 아니라 로그인 단위로 한다.** PW 필드를 읽을 수
            # 없어 타이핑 성공 여부를 확인할 수 없으므로(`fill_password` 주석),
            # "로그인 화면을 벗어났는가" 라는 확실한 신호로 판단하고 그때만 다시
            # 시도한다. `flows.cold_start` 의 `login_attempts` 와 같은 방식이다.
            ok = False
            for attempt in range(1, login_attempts + 1):
                ok = self.login(user_id, password)
                if ok:
                    if attempt > 1:
                        notes.append(f"로그인 {attempt}회차에 성공")
                    break
                notes.append(f"로그인 {attempt}회차 실패 — 재시도")
                self.sweep_dialogs(timeout=3)
                time.sleep(1.0)
            if not ok:
                # `core/ui.py` 는 모듈 최상단에 `os`/`PIL` 을 두지 않는다
                # (`capture_dialog` 과 같은 지역 import 방식을 따른다).
                import os
                from PIL import ImageGrab
                shot = os.path.join("Evidence", "ui", "login_not_completed.png")
                try:
                    window = self.main_window()
                    box = window.rect if window else None
                    os.makedirs(os.path.dirname(shot) or ".", exist_ok=True)
                    ImageGrab.grab(bbox=box, all_screens=True).save(shot)
                    notes.append(f"실패 화면 캡처: {shot}")
                except Exception:                          # noqa: BLE001
                    shot = ""
                raise RuntimeError(
                    f"로그인이 완료되지 않았습니다(ID={user_id!r}). 로그인 화면을 "
                    f"벗어나지 못했습니다. {'캡처: ' + shot if shot else ''} "
                    f"진행 기록={notes}")
            notes.append("로그인 성공")
            # **로그인 직후에도 팝업을 걷어낸다.** Demo 모드 안내
            # (`Running in demo mode.`)는 로그인 *뒤에* 뜬다(2026-08-24 실측).
            # 예전에는 로그인 전에만 한 번 닫았기 때문에 이 모달이 그대로 남아
            # 이후 모든 클릭을 삼켰고, 15초 뒤 `open_main_menu` 가 "메인 메뉴
            # 버튼(2015)을 찾지 못했습니다" 로 죽었다 — 원인과 무관한 메시지였다.
            if dismiss_demo:
                closed = self.sweep_dialogs(timeout=8)
                if closed:
                    notes.append("로그인 후 팝업 닫음: " + "; ".join(closed))
            # 팝업을 걷어낸 뒤 **실제로 Viewer 화면이 올라왔는지** 확인한다.
            # 여기서 드러내지 않으면 다음 조작이 엉뚱한 메시지로 죽는다.
            state = self.wait_screen_ready(timeout=60)
            notes.append(f"로그인 후 화면: {state or '시간 초과'}")
            if state != "loaded":
                raise RuntimeError(
                    "로그인 후 Viewer 화면이 올라오지 않았습니다"
                    f"(상태={state or '시간 초과'}). 진행 기록={notes}")
        return notes

    # --- Demo 가상 촬영 -------------------------------------------------
    def demo_exposure(self, wait_after=10):
        """Demo 모드 가상 촬영(F8).

        근거: Service Manual 5.2.3 '데모 버전에서 가상 촬영하기' —
        촬영 준비 완료 상태에서 F8 키를 누르면 가상 촬영이 진행되고 영상이 획득된다.
        실제 X-ray/팬텀이 필요 없으므로 촬영이 전제인 TC를 자동화할 수 있다.

        주의: 같은 매뉴얼에 '선택한 스텝 정보와 가상 획득 영상은 서로 어떠한
        연관성도 없다'고 명시되어 있다. 따라서 획득 영상의 **내용**을 근거로
        View Position/Laterality/화질을 판정해서는 안 된다.
        """
        self.require_front("Demo 촬영(F8)")
        self.key("F8", settle=0.5)
        time.sleep(wait_after)


# ---------------------------------------------------------------------
def dump(process_name="VIEWER", max_depth=4, visible_only=True):
    """현재 화면의 컨트롤 트리를 출력한다. 화면별 컨트롤 ID 지도를 만들 때 쓴다."""
    ui = ViewerUi(process_name)
    if not ui.pid:
        return f"{process_name} 프로세스를 찾을 수 없습니다."
    lines = [f"PID {ui.pid}"]
    for win in ui.windows():
        lines.append(f"\n[WINDOW] {win!r}")
        for c in ui.controls(win, max_depth, visible_only):
            lines.append(repr(c))
    return "\n".join(lines)
