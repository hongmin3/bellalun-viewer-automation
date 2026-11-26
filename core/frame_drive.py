# -*- coding: utf-8 -*-
"""설치판 GUI 최종 검증에서 에이전트가 공용 실행 화면을 조작한다 (frame/FRAME.md 2.7).

`core/frame_ui.ps1`이 그린 WinForms 창을 찾아 사람이 누르는 것과 같은 버튼·확인 항목을 누른다.
창 제목은 `<제품 이름> · <단계>`이므로 제목의 단계로 지금 화면을 판단한다.
물리 마우스·키보드를 쓰지 않고 해당 컨트롤 HWND에 메시지를 보낸다.

제품 이름·버튼 문구·확인 항목은 호출하는 쪽이 넘긴다. 이 모듈은 사용자 승인 여부를 판단하지 않는다.
승인 확인과 기록은 제품의 설치판 GUI 실행 도구가 맡는다.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time

from core.frame_ui import STEPS

BM_CLICK = 0x00F5
LB_GETCOUNT, LB_GETITEMHEIGHT, LB_GETTOPINDEX, LB_SETTOPINDEX = 0x018B, 0x01A1, 0x018E, 0x0197
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_GETTEXT, WM_GETTEXTLENGTH = 0x0201, 0x0202, 0x000D, 0x000E
SEPARATOR = ' · '
SEND_TIMEOUT_MS = 3000


_USER32 = None
_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _user32():
    """이 모듈 전용 user32. 공용 `ctypes.windll`의 함수 형식을 바꾸지 않는다."""
    global _USER32
    if _USER32 is None:
        dll = ctypes.WinDLL('user32', use_last_error=True)
        dll.SendMessageTimeoutW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                            wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t))
        dll.SendMessageTimeoutW.restype = wintypes.LPARAM
        dll.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        dll.PostMessageW.restype = wintypes.BOOL
        dll.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        dll.EnumWindows.argtypes = (_ENUM_PROC, wintypes.LPARAM)
        dll.EnumChildWindows.argtypes = (wintypes.HWND, _ENUM_PROC, wintypes.LPARAM)
        dll.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        for name in ('IsWindowVisible', 'IsWindowEnabled', 'IsWindow'):
            getattr(dll, name).argtypes = (wintypes.HWND,)
        _USER32 = dll
    return _USER32


def _send(hwnd, msg, wparam=0, lparam=0):
    """응답 없는 창에 묶이지 않도록 SendMessageTimeoutW(SMTO_ABORTIFHUNG)로 보낸다."""
    result = ctypes.c_size_t(0)
    ok = _user32().SendMessageTimeoutW(hwnd, msg, wparam, lparam, 0x0002, SEND_TIMEOUT_MS,
                                       ctypes.byref(result))
    return result.value if ok else None


def window_text(hwnd):
    length = _send(hwnd, WM_GETTEXTLENGTH) or 0
    buffer = ctypes.create_unicode_buffer(length + 1)
    _send(hwnd, WM_GETTEXT, length + 1, ctypes.cast(buffer, ctypes.c_void_p).value or 0)
    return buffer.value


def class_name(hwnd):
    buffer = ctypes.create_unicode_buffer(256)
    _user32().GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def screen_of(title, product):
    """창 제목에서 단계 이름을 읽는다. 이 제품의 공용 화면이 아니면 None."""
    prefix = product + SEPARATOR
    if not title.startswith(prefix):
        return None
    step = title[len(prefix):]
    return step if step in STEPS else None


def frame_windows(product):
    """보이는 공용 화면 창 [(hwnd, 단계)]. 다른 제품·다른 창은 제외한다."""
    user32, found = _user32(), []
    proc = _ENUM_PROC

    def collect(hwnd, _):
        if user32.IsWindowVisible(hwnd) and class_name(hwnd).startswith('WindowsForms10.'):
            step = screen_of(window_text(hwnd), product)
            if step:
                found.append((hwnd, step))
        return True

    user32.EnumWindows(proc(collect), 0)
    return found


def controls(hwnd):
    """창 안의 자식 컨트롤 [(hwnd, 클래스, 글자, 사용 가능)]."""
    user32, found = _user32(), []
    proc = _ENUM_PROC

    def collect(child, _):
        if user32.IsWindowVisible(child):
            found.append((child, class_name(child), window_text(child), bool(user32.IsWindowEnabled(child))))
        return True

    user32.EnumChildWindows(hwnd, proc(collect), 0)
    return found


def texts(hwnd):
    """창에 보이는 문구(제목·결론·안내). 조작 기록의 증거로 남긴다."""
    return [text for _, cls, text, _ in controls(hwnd)
            if text.strip() and ('STATIC' in cls.upper() or 'BUTTON' in cls.upper())]


def wait_screen(product, steps, timeout, poll=0.5, clock=time.time, sleep=time.sleep):
    """`steps` 중 하나의 화면이 뜰 때까지 기다린다. (hwnd, 단계) 또는 시간 초과 시 None."""
    end = clock() + timeout
    while True:
        for hwnd, step in frame_windows(product):
            if step in steps:
                return hwnd, step
        if clock() >= end:
            return None
        sleep(poll)


def _button(hwnd, label):
    for child, cls, text, enabled in controls(hwnd):
        if 'BUTTON' in cls.upper() and text.replace('&', '').strip() == label:
            return child, enabled
    return None, False


def click(hwnd, label, timeout=30, poll=0.5, clock=time.time, sleep=time.sleep):
    """문구가 `label`인 버튼이 사용 가능해지면 누른다(조건 대기). 못 누르면 RuntimeError."""
    end = clock() + timeout
    while True:
        button, enabled = _button(hwnd, label)
        if button and enabled:
            if not _user32().PostMessageW(button, BM_CLICK, 0, 0):
                raise RuntimeError(f'"{label}" 버튼에 누름을 보내지 못했습니다.')
            return
        if clock() >= end:
            state = '비활성' if button else '없음'
            raise RuntimeError(f'"{label}" 버튼을 누를 수 없습니다({state}). 화면 문구: {texts(hwnd)[:12]}')
        sleep(poll)


def check_all(hwnd, settle=0.5, sleep=time.sleep):
    """확인 목록(CheckedListBox)의 모든 항목을 클릭해 체크한다. 체크한 항목 수.

    목록은 CheckOnClick이라 항목 한 번 클릭이 체크 한 번이다. 이미 체크된 목록에 다시 부르지 않는다.
    체크 결과는 화면이 돌려주는 답(`checked`)과 다음 화면으로 확인한다.
    지금 보이는 항목들을 서로 다른 위치에서 차례로 누르고(클릭 메시지는 목록의 메시지 큐에 순서대로 쌓인다),
    처리될 때까지 기다린 뒤 남은 항목이 보이게 한 번 스크롤해 다음 묶음을 누른다. 항목이 목록 높이보다
    많은 화면(예: baseline 안내 줄이 더해진 경우)에서도 모든 항목을 누른다.
    """
    lists = [child for child, cls, _, _ in controls(hwnd) if 'LISTBOX' in cls.upper()]
    if len(lists) != 1:
        raise RuntimeError(f'확인 목록을 하나로 찾지 못했습니다(후보 {len(lists)}개).')
    box = lists[0]
    count = _send(box, LB_GETCOUNT)
    height = _send(box, LB_GETITEMHEIGHT, 0, 0)
    if not count or not height:
        raise RuntimeError('확인 목록의 항목 수나 높이를 읽지 못했습니다.')
    rect = wintypes.RECT()
    if not _user32().GetClientRect(box, ctypes.byref(rect)):
        raise RuntimeError('확인 목록의 크기를 읽지 못했습니다.')
    visible = max(1, rect.bottom // height)
    user32 = _user32()
    done = 0
    while done < count:
        if done:
            _send(box, LB_SETTOPINDEX, done)
            sleep(settle)
        top = _send(box, LB_GETTOPINDEX) or 0
        last = min(count, top + visible)
        if not top <= done < last:
            raise RuntimeError(f'확인 목록 {done + 1}번째 항목을 화면에 보이게 하지 못했습니다.')
        for index in range(done, last):
            y = (index - top) * height + height // 2
            point = (y << 16) | 8
            user32.PostMessageW(box, WM_LBUTTONDOWN, 1, point)  # MK_LBUTTON
            user32.PostMessageW(box, WM_LBUTTONUP, 0, point)
        done = last
        sleep(settle)
    return count
