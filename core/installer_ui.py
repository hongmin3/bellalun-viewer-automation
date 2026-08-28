# -*- coding: utf-8 -*-
"""Bellalun Install Wizard(`Install.exe`) 전용 UI 드라이버.

Viewer 와 같은 MFC 커스텀 컨트롤 체계라 `core/ui.py` 의 `ViewerUi` 를 그대로
상속한다. 다만 **인스톨러에만 있는 실측 사실 세 가지** 때문에 별도 드라이버를 둔다
(2026-08-26 Bellalun1.0.12.105 패키지 실측).

1. 하단 버튼(Next/Back/Cancel)은 컨트롤이 **두 벌**이다.
   - 숨은 표준 `Button`                : id 1000~1002, text 'Cancel' / '< Back' / 'Next >'
   - 실제로 보이는 커스텀 `AfxWnd140su` : **같은 id**, text 'TextButton'
   숨은 Button 에 `BM_CLICK` 을 보내면 **아무 일도 일어나지 않는다**(실측).
   반드시 커스텀 쪽 좌표를 눌러야 한다.

2. 그 커스텀 버튼은 **누르는 시간이 짧으면 무시한다.** `ViewerUi.click()` 은 down
   후 0.06초에 up 하는데, 그것으로 Next 는 눌리지만 Back 은 눌리지 않는다.
   2026-08-26 실측 중 이것을 "Back 버튼이 동작하지 않는다(매뉴얼 불일치)" 로
   오판할 뻔했다 — 누름 시간을 0.2초로 늘리자 정상 동작했다. 그래서 `press()` 는
   누름 시간을 명시적으로 잡는다. **이 값을 줄이지 말 것.**

3. 콤보(Language/Theme/KIOSK)는 열면 **별도 최상위 창** `AfxWnd140su 'ItemList'`
   이 뜨고, 항목은 그 창의 'TextButton' 자식들이다. 항목 텍스트는 커스텀
   렌더링이라 `WM_GETTEXT` 로 읽히지 않으므로, **항목을 선택한 뒤 콤보 자신의
   숨은 Edit(id 3) 값을 읽어** 정확한 문자열을 얻는다(`ViewerUi.combo_value`).

현재 페이지는 **자식 `#32770` 창의 visible 여부**로 판정한다. 페이지 창은 처음부터
전부 만들어져 있고 현재 것만 보인다. 신규 설치는 6개, 업그레이드는 Welcome /
Summary / Install Software 3개만 만들어진다(SRS 08-10-20).
"""

import time

from core import screen
from core.ui import (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, ViewerUi,
                     children, u32)

PROCESS_NAME = "Install"
WIZARD_TITLE = "Install Wizard"
POPUP_TITLE = "Install"          # 표준 MessageBox 의 캡션
MENU_WINDOW = "CDlgMenu"

# 신규 설치에서 만들어지는 6개 페이지 (SRS 08-10-10 / Service Manual 설치 절차)
PAGES_NEW_INSTALL = ("Welcome", "Configure Path", "Register Options",
                     "Input License", "Summary", "Install Software")
# 업그레이드 시에만 만들어지는 축약 구성 (SRS 08-10-20)
PAGES_UPGRADE = ("Welcome", "Summary", "Install Software")

# --- 컨트롤 ID (전부 실측) ------------------------------------------------
BTN_CANCEL, BTN_BACK, BTN_NEXT = 1000, 1001, 1002
MENU_FIRST_ID = 1100                     # 좌측 메뉴 1100 + n

WELCOME_TITLE, WELCOME_GUIDE, WELCOME_EULA = 1200, 1201, 1202
WELCOME_ACCEPT, WELCOME_DISACCEPT = 1203, 1204

PATH_TITLE, PATH_GUIDE = 1300, 1301
PATH_VIEWER_LABEL, PATH_VIEWER_EDIT = 1302, 1303
PATH_DB_LABEL, PATH_DB_EDIT = 1304, 1305
PATH_BROWSE, PATH_DRIVE_LIST = 1306, 1307

OPT_TITLE, OPT_GUIDE = 1400, 1401
OPT_LANG_LABEL, OPT_THEME_LABEL, OPT_KIOSK_LABEL = 1403, 1404, 1405
OPT_LANG_COMBO, OPT_THEME_COMBO = 1410, 1411
# KIOSK 콤보만 1500 대역을 쓴다(1412 가 아니다). 리소스 ID 를 Input License 와
# 나눠 쓰는 구현상의 사정으로 보이며, 실측값이므로 그대로 둔다.
OPT_KIOSK_COMBO = 1513

LIC_TITLE, LIC_GUIDE, LIC_INFO = 1500, 1501, 1502
LIC_HWKEY_LABEL, LIC_LABEL = 1503, 1504
# 아래 두 상수는 **페이지가 열리기 전** 트리에서 보이는 입력 상자 래퍼다.
# 페이지가 열리면 입력칸이 페이지 창 직속 Edit 으로 바뀌어 이 ID 로는 잡히지
# 않는다(실측). 컨트롤 지도로 남겨 두고, 실제 조회는 라벨 기준으로 한다.
LIC_HWKEY_BOX = 1508
LIC_KEY_BOXES = (1509, 1510, 1511, 1512)

SUM_TITLE, SUM_GUIDE, SUM_TEXT = 1800, 1801, 1802
INSTALL_LIST = 1900

# 라이선스 입력칸의 자릿수 (실측: EM_GETLIMITTEXT = 4/5/4/5, 합 18자).
# 안내 문구(id 1501)의 "18-character license key" 와 일치한다.
LICENSE_SEGMENTS = (4, 5, 4, 5)
EM_GETLIMITTEXT = 0x00D5

# 커스텀 RadioButton 의 채움 원 중심 오프셋(실측). 컨트롤 좌상단 기준으로
# 원은 x 3~21, y 4~23 이고 선택 시 x 10~16 / y 11~17 이 테마색으로 찬다.
RADIO_DX, RADIO_DY, RADIO_TOL = 12, 14, 2


class InstallerUi(ViewerUi):
    """Install Wizard 하나를 대상으로 하는 드라이버."""

    def __init__(self):
        super().__init__(PROCESS_NAME)

    # --- 창 ------------------------------------------------------------
    def wizard(self):
        """마법사 본체 창. 팝업이 떠 있어도 본체를 정확히 돌려준다."""
        for w in self.windows():
            if w.text == WIZARD_TITLE:
                return w
        return None

    def alive(self):
        return self.pid is not None and self.wizard() is not None

    def _tree(self, depth=5):
        """마법사 창의 컨트롤 목록. **hwnd 기준으로 중복을 없앤다.**

        `core.ui.children()` 은 재귀로 평탄화하면서 같은 컨트롤을 여러 번 담는다
        (페이지 창의 직접 자식으로 한 번, 중간 컨테이너를 거쳐 또 한 번).
        중복을 둔 채 좌표로 정렬해 앞에서 N개를 자르면 **같은 컨트롤이 자리를
        차지해 뒤쪽이 잘린다** — 2026-08-26 라이선스 입력칸 자릿수가 4/5/4/5 가
        아니라 4/4/5/5 로 읽힌 원인이 이것이었다(1·2번칸이 두 번씩 잡히고 3·4번칸이
        잘렸다). 컨트롤 조회는 전부 이 함수를 거치게 한다.
        """
        win = self.wizard()
        if win is None:
            return []
        seen, out = set(), []
        for c in children(win.hwnd, depth):
            if c.hwnd in seen:
                continue
            seen.add(c.hwnd)
            out.append(c)
        return out

    # --- 페이지 --------------------------------------------------------
    def page_windows(self):
        """{페이지 이름: 보이는가}. 만들어지지 않은 페이지는 키 자체가 없다."""
        out = {}
        for c in self._tree():
            if c.cls == "#32770" and c.text and c.text != MENU_WINDOW:
                out.setdefault(c.text, c.visible)
        return out

    def current_page(self):
        for name, visible in self.page_windows().items():
            if visible:
                return name
        return None

    def wait_page(self, name, timeout=20, poll=0.4):
        limit = time.time() + timeout
        while time.time() < limit:
            if self.current_page() == name:
                return True
            time.sleep(poll)
        return False

    def menu_items(self):
        """좌측 단계 메뉴 항목(위->아래). 커스텀 렌더링이라 텍스트는 비어 있고,
        **개수와 위치**로 신규 설치/업그레이드 구성을 판별한다."""
        items = {}
        for c in self._tree():
            if c.cls == "#32770" and c.text == MENU_WINDOW:
                for ch in children(c.hwnd, 2):
                    if ch.ctrl_id >= MENU_FIRST_ID and ch.cls == "AfxWnd140su":
                        items[ch.ctrl_id] = ch
        return [items[k] for k in sorted(items)]

    # --- 컨트롤 --------------------------------------------------------
    def find(self, ctrl_id, cls=None, visible=True, depth=5):
        for c in self._tree(depth):
            if c.ctrl_id != ctrl_id:
                continue
            if cls is not None and c.cls != cls:
                continue
            if visible is not None and c.visible != visible:
                continue
            return c
        return None

    def find_retry(self, ctrl_id, cls=None, visible=True, tries=8, gap=0.3):
        """페이지 전환 직후에는 컨트롤이 잠깐 잡히지 않는다. 기다렸다 다시 본다."""
        for _ in range(tries):
            c = self.find(ctrl_id, cls, visible)
            if c is not None:
                return c
            time.sleep(gap)
        return None

    def text_of(self, ctrl_id, cls=None):
        c = self.find(ctrl_id, cls)
        return c.text if c else None

    # --- 조작 ----------------------------------------------------------
    def hold_click(self, control, hold=0.20, settle=0.8):
        """**누름 시간을 확보한** 좌클릭.

        커스텀 버튼은 down->up 이 너무 빠르면 클릭으로 세지 않는다(모듈 주석 2번).
        """
        self.require_front_for_pointer("인스톨러 클릭")
        x, y = control.center
        u32.SetCursorPos(int(x), int(y))
        time.sleep(0.25)
        u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(hold)
        u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(settle)

    def press(self, ctrl_id, settle=1.3):
        """하단 버튼(Next/Back/Cancel)을 누른다. 눌렀으면 True."""
        btn = self.find(ctrl_id, "AfxWnd140su")
        if btn is None:
            return False
        self.hold_click(btn, settle=settle)
        return True

    def next_page(self, expect=None, timeout=20):
        """Next 를 누르고 페이지가 실제로 넘어갔는지까지 확인한다."""
        before = self.current_page()
        if not self.press(BTN_NEXT):
            return False, before
        if expect:
            self.wait_page(expect, timeout=timeout)
        return self.current_page() != before, self.current_page()

    def back_page(self, timeout=20):
        before = self.current_page()
        if not self.press(BTN_BACK):
            return False, before
        limit = time.time() + timeout
        while time.time() < limit and self.current_page() == before:
            time.sleep(0.3)
        return self.current_page() != before, self.current_page()

    # --- 라디오 --------------------------------------------------------
    def radio_selected(self, ctrl_id):
        """커스텀 RadioButton 선택 여부. 판정이 애매하면 None."""
        c = self.find(ctrl_id, "AfxWnd140su")
        if c is None:
            return None
        return screen.radio_selected(c, dx=RADIO_DX, dy=RADIO_DY, tol=RADIO_TOL)

    def select_radio(self, ctrl_id):
        c = self.find(ctrl_id, "AfxWnd140su")
        if c is None:
            return False
        self.hold_click(c, settle=0.6)
        return self.radio_selected(ctrl_id) is not False

    # --- 콤보 ----------------------------------------------------------
    def _item_list(self):
        """열려 있는 드롭다운 창의 항목들(위->아래)."""
        for w in self.windows():
            if w.cls == "AfxWnd140su" and w.text == "ItemList":
                items = {c.hwnd: c for c in children(w.hwnd, 3)
                         if c.cls == "AfxWnd140su" and c.text == "TextButton"
                         and c.visible}
                return sorted(items.values(), key=lambda c: c.rect[1])
        return []

    def _dropdown_open(self):
        return any(w.cls == "AfxWnd140su" and w.text == "ItemList"
                   for w in self.windows())

    def combo(self, ctrl_id):
        return self.find_retry(ctrl_id, "AfxWnd140su")

    def combo_text(self, ctrl_id):
        c = self.combo(ctrl_id)
        return self.combo_value(c) if c else None

    def combo_options(self, ctrl_id):
        """드롭다운의 **모든 선택지**를 실측한다. (목록, 원래값) 을 돌려준다.

        항목 텍스트를 직접 읽을 수 없으므로 항목을 차례로 선택하며 콤보 값을
        모은다. 끝나면 원래 값으로 되돌린다.

        드롭다운을 ESC 로 닫지 않는다 — ESC 는 MFC 대화상자에서 Cancel 로
        해석될 수 있고, 실측 중 ESC 직후 컨트롤 조회가 실패한 적이 있다.
        항목을 선택하는 것으로 닫는다.
        """
        original = self.combo_text(ctrl_id)
        values, index = [], 0
        while True:
            if not self._dropdown_open():
                combo = self.combo(ctrl_id)
                if combo is None:
                    break
                self.hold_click(combo, settle=0.8)
            items = self._item_list()
            if not items or index >= len(items):
                if items:                       # 열린 채로 끝나지 않게 닫는다
                    self.hold_click(items[0], settle=0.6)
                break
            self.hold_click(items[index], settle=0.8)
            values.append(self.combo_text(ctrl_id))
            index += 1
        if original is not None and original in values:
            self.select_combo(ctrl_id, original)
        return values, original

    def select_combo(self, ctrl_id, value):
        """콤보에서 `value` 를 고른다. 고른 뒤의 실제 값을 돌려준다."""
        if self.combo_text(ctrl_id) == value:
            return value
        # 값 -> 항목 위치를 모르므로 한 바퀴 돌며 맞는 것에서 멈춘다.
        for _ in range(2):
            if not self._dropdown_open():
                combo = self.combo(ctrl_id)
                if combo is None:
                    return None
                self.hold_click(combo, settle=0.8)
            for item in self._item_list():
                self.hold_click(item, settle=0.7)
                if self.combo_text(ctrl_id) == value:
                    return value
                combo = self.combo(ctrl_id)
                if combo is None:
                    return None
                self.hold_click(combo, settle=0.8)
            if self._dropdown_open():
                items = self._item_list()
                if items:
                    self.hold_click(items[0], settle=0.6)
        return self.combo_text(ctrl_id)

    def choose_option(self, ctrl_id, value, expected_options, capture_path=None):
        """드롭다운을 **한 번만 열어** 항목 수를 세고 원하는 값을 고른다.

        항목 텍스트는 커스텀 렌더링이라 읽을 수 없다. 그래서 예전에는 항목을 전부
        눌러 보며 값을 모았는데(`combo_options`), 이미 고를 값이 정해져 있을 때는
        **불필요하게 화면을 휘젓는다.** 항목 **순서가 사양 목록과 같다**는 것을
        실측으로 확인했으므로(언어 4 · 테마 3 · KIOSK 2 모두 일치) 그 위치를 눌러
        한 번에 고른다.

        순서 가정을 그대로 믿지는 않는다 — 누른 뒤 **콤보 값을 읽어 검증**하고,
        기대와 다르면 전수 순회로 되짚는다. 그래서 순서가 바뀐 빌드에서도 조용히
        틀리지 않는다.

        `value` 가 None 이면 **현재 값을 그대로 다시 골라** 값을 바꾸지 않고 닫는다.

        반환: {"count", "value", "by_order", "capture", "fell_back"}
        """
        combo = self.combo(ctrl_id)
        if combo is None:
            return None
        current = self.combo_value(combo)
        target = current if value is None else value

        self.hold_click(combo, settle=0.8)
        items = self._item_list()
        count = len(items)
        capture = None
        if capture_path and items:
            right = max(max(c.rect[2] for c in items), combo.rect[2])
            bottom = max(c.rect[3] for c in items)
            try:
                screen.grab((combo.rect[0], combo.rect[1], right, bottom), capture_path)
                capture = capture_path
            except Exception:
                capture = None

        index = (expected_options.index(target)
                 if target in expected_options else None)
        if index is not None and index < count:
            self.hold_click(items[index], settle=0.8)
            got = self.combo_text(ctrl_id)
            if got == target:
                return {"count": count, "value": got, "by_order": True,
                        "capture": capture, "fell_back": False}
        elif items:
            self.hold_click(items[0], settle=0.6)      # 열린 채로 두지 않는다

        got = self.select_combo(ctrl_id, target)       # 순서 가정이 빗나감 → 순회
        return {"count": count, "value": got, "by_order": False,
                "capture": capture, "fell_back": True}

    # --- 스크롤 --------------------------------------------------------
    def scroll_to_top(self, control, steps=15, notches=3):
        """스크롤 영역을 맨 위로 올린다. 앞선 조작이 남긴 위치를 지운다."""
        for _ in range(steps):
            self.wheel(control, notches, settle=0.12)

    def scroll_through(self, control, save_as, max_shots=12, notches=3):
        """맨 위부터 끝까지 내리며 화면을 캡처한다.

        긴 본문(EULA·Summary)은 한 화면에 다 담기지 않는다. 텍스트 자체는
        `WM_GETTEXT` 로 전문을 읽어 판정하고, **사람이 눈으로 되짚을 수 있게**
        여기서 화면을 남긴다.

        `save_as(index)` 가 저장 경로를 돌려준다. 직전 화면과 **픽셀이 같아지면**
        끝에 닿은 것으로 보고 멈춘다.
        """
        self.scroll_to_top(control)
        paths, previous = [], None
        for i in range(max_shots):
            try:
                image = screen.grab(control.rect)
            except Exception:
                break
            data = image.tobytes()
            if data == previous:
                break
            path = save_as(i)
            try:
                image.save(path)
                paths.append(path)
            except Exception:
                pass
            previous = data
            self.wheel(control, -notches, settle=0.35)
        return paths

    # --- 라이선스 ------------------------------------------------------
    def hardware_key(self):
        """Hardware Key 표시값. 라벨 아래의 **넓은** Edit 에 들어 있다."""
        label = self.find(LIC_HWKEY_LABEL, "Static")
        if label is None:
            return None
        for c in self._tree():
            if (c.cls == "Edit" and c.visible and c.rect[1] > label.rect[1]
                    and (c.rect[2] - c.rect[0]) > 300):
                return c.text
        return None

    def license_fields(self):
        """라이선스 입력칸 4개(좌->우)의 실제 `Edit` 컨트롤.

        페이지가 **열린 뒤에는** 입력칸이 래퍼(1509~1512) 없이 페이지 창의
        직속 `Edit`(컨트롤 ID 1)로 나타난다(실측). 그래서 ID 로 찾지 않고
        ' License :' 라벨 아래에 있는 **좁은** Edit 들을 좌->우로 고른다.
        Hardware Key 는 폭이 넓어 이 조건에서 자연히 빠진다.
        """
        label = self.find(LIC_LABEL, "Static")
        if label is None:
            return []
        row = [c for c in self._tree()
               if c.cls == "Edit" and c.visible and c.rect[1] >= label.rect[1]
               and (c.rect[2] - c.rect[0]) < 300]
        return sorted(row, key=lambda c: c.rect[0])[:len(LIC_KEY_BOXES)]

    def license_limits(self):
        """각 입력칸이 허용하는 최대 글자 수."""
        return [u32.SendMessageW(c.hwnd, EM_GETLIMITTEXT, 0, 0)
                for c in self.license_fields()]

    # --- 팝업 ----------------------------------------------------------
    def popup(self):
        for w in self.windows():
            if w.cls == "#32770" and w.text == POPUP_TITLE:
                return w
        return None

    def popup_text(self, popup=None):
        popup = popup or self.popup()
        if popup is None:
            return None
        parts = [c.text for c in children(popup.hwnd, 3)
                 if c.cls == "Static" and c.text.strip()]
        return " ".join(parts).strip()

    # 팝업은 **닫지 않는다.** 라이선스 입력처럼 사람이 화면에서 직접 처리하는
    # 단계에서 자동화가 팝업을 닫으면 사람이 문구를 보기 전에 사라진다.
    # 여기서는 읽기만 하고, 무엇이 떴는지 터미널에 알려 주는 데만 쓴다.
