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
    def click(self, target, settle=0.4):
        """Control 또는 (x, y)를 클릭한다."""
        x, y = target.center if isinstance(target, Control) else target
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
        x, y = target.center if isinstance(target, Control) else target
        u32.SetCursorPos(int(x), int(y))
        time.sleep(settle)
        return (int(x), int(y))

    def right_click(self, target, settle=0.8):
        """Control 또는 (x, y)를 우클릭한다.

        커스텀 렌더 목록에서 컨텍스트 메뉴를 확인할 때 쓴다. 좌클릭과 같은 방식으로
        물리 입력을 보낸다 — `WM_CONTEXTMENU` 주입은 이 UI 에서 통하지 않는다.
        """
        x, y = target.center if isinstance(target, Control) else target
        u32.SetCursorPos(int(x), int(y))
        time.sleep(0.08)
        u32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        time.sleep(0.06)
        u32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        time.sleep(settle)

    def drag(self, start, end, duration=.4, settle=.4):
        """Drag between physical screen coordinates."""
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
        """
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

    @staticmethod
    def raw_key(vk, settle=0.05):
        u32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        u32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(settle)

    @staticmethod
    def key_combo(mod_vk, vk):
        u32.keybd_event(mod_vk, 0, 0, 0)
        u32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        u32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        u32.keybd_event(mod_vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.08)

    def key(self, name, settle=0.3):
        """가상 키 입력. 포커스가 Viewer에 있어야 한다."""
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
        front = self.foreground_window()
        return bool(front and self.pid and front["pid"] == self.pid)

    def bring_to_front(self, attempts=4, settle=0.4):
        """Viewer를 최전면으로 올리고 **실제로 올라왔는지 확인**한다.

        `SetForegroundWindow`는 Windows가 무시할 수 있다(다른 프로세스가 포커스를
        쥐고 있을 때). 그래서 호출만 하고 넘어가면, 가려진 상태에서 물리 키 입력을
        보내 **비밀번호가 다른 창으로 들어간다.**

        올리지 못하면 마지막으로 최전면이던 창 정보를 함께 돌려준다. 호출자가
        "무엇이 가리고 있었는지" 보고할 수 있게 하는 것이 목적이다.

        반환: {"ok": bool, "blocking": {...}|None, "attempts": int}
        """
        win = self.main_window()
        if not win:
            return {"ok": False, "blocking": None, "attempts": 0}
        for attempt in range(1, attempts + 1):
            if self.is_foreground():
                return {"ok": True, "blocking": None, "attempts": attempt - 1}
            # 최소화되어 있으면 먼저 복원한다(SW_RESTORE = 9).
            u32.ShowWindow(win.hwnd, 9)
            u32.SetForegroundWindow(win.hwnd)
            u32.BringWindowToTop(win.hwnd)
            time.sleep(settle)
        front = self.foreground_window()
        blocking = None
        if front and front["pid"] != self.pid and not _is_shell_window(front):
            blocking = {"title": front["title"], "pid": front["pid"]}
        return {"ok": self.is_foreground(), "blocking": blocking,
                "attempts": attempts}

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

        # 전환 중 컨트롤이 잠깐 사라질 수 있으므로 연속 2회 확인으로 확정한다.
        end = time.time() + timeout
        gone = 0
        while time.time() < end:
            if self.at_login_screen():
                gone = 0
            else:
                gone += 1
                if gone >= 2:
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
        """비밀번호를 넣고 **실제로 들어갔는지 길이로 확인**한다.

        `type_text` 는 물리 키 입력이라 조용히 유실될 수 있다(위 주석의 실측 사례).
        로그인 화면의 PW 필드는 표준 `Edit`(`2002`)이라 `WM_GETTEXT` 로 **길이를
        읽을 수 있다**(2026-08-24 확인). 그래서 넣은 뒤 글자 수를 대조하고 어긋나면
        다시 타이핑한다 — 조작 후 확인을 붙이는 규칙(`AGENTS.md` 3절)의 적용이다.

        **값은 절대 읽어서 로그로 남기지 않는다. 길이만 본다.**

        길이를 읽을 수 없는 환경(빈 문자열만 돌려주는 빌드)에서도 진행을 막지
        않는다. 최종 성공 판정은 `login()` 의 "로그인 화면을 벗어났는가" 가 한다.
        """
        want = len(password)
        got = -1
        for attempt in range(1, self.PW_TYPE_ATTEMPTS + 1):
            self.activate()
            self.type_text(control, password)
            got = len(self.get_text(control) or "")
            if got == want:
                return {"attempts": attempt, "chars": got, "verified": True}
            time.sleep(1.0)
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
            wait = 2                # 첫 팝업 뒤에는 짧게만 더 확인한다
        return closed

    def ensure_ready(self, exe_path=None, user_id=None, password=None,
                     dismiss_demo=True, startup_timeout=180):
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
            ok = self.login(user_id, password)
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
        self.activate()
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
