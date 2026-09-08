# -*- coding: utf-8 -*-
"""USB 이동식 드라이브 탐지와 Examined 창 Import Study 자동화.

Windows Update 체크리스트 TC_WindowsUpdate_09(Study Export) 의 USB 경로
대응. **신규 구현이다** — 이 저장소에 기존 Export/Import 자동화가 없었다
(Export 는 `core/export_manager.py` 가 로컬 경로만 다뤘고, Import Study 는
컨트롤 ID(2184) 만 실측된 채 자동화가 없었다. 아이콘 추정 오류 이력 때문에
`core/flows.py` 주석에만 남아 있었다).

## 2026-09-07 실측 (`Temp/probe_import*.py`, 저장소에는 남기지 않음)

Examined 창에서 대상 검사를 선택하지 않고 **2184(Import)** 를 누르면
"Import Study" 대화상자가 뜬다(툴팁 "Import" 로 확인 — 아이콘 추정 아님).

  2062  드라이브 표시(현재 "C:\\") + 옆의 화살표(ctrl_id=1, x≈642~676)를
        누르면 이 PC 의 드라이브 목록(C:\\/D:\\/E:\\ 등)이 드롭다운으로 뜬다.
  2065  Edit — 경로/검색어로 보이는 큰 입력란. `WM_SETTEXT` 로 값은 그대로
        반영되고 되읽어진다(Export Manager의 `PATH_EDIT`처럼).
  2063  CircleButton — **주의: 검색/새로고침이 아니라 "폴더 찾아보기"
        (`SHBrowseForFolder`) 를 여는 버튼이다.**
  2066  ListCtrl — 검색 결과 목록(ID/Name/Age/Birth Date/Image 열, owner-draw).
  2064  Import 버튼. 1102 Close 버튼(Edit Information 의 Cancel 과 같은 ID —
        이 제품은 기능별로 ID 가 일관된다는 기존 관찰과 일치).

**미해결로 남긴 것**: 2065 에 실제 Export 결과 폴더 경로를 넣고 Enter/포커스
이동을 시도했지만 목록(2066)이 채워지지 않았다. 드라이브 드롭다운
(C:\\/D:\\/E:\\ 선택)이 진짜 트리거일 가능성이 높지만(경로 대신 **미디어
자체**를 고르는 UX로 보인다), 드롭다운 항목의 정확한 컨트롤 ID를 이 세션
안에서 확정하지 못했다. 그래서 `import_study()` 는 **경로 설정까지만 자동화
하고, 목록에 실제로 행이 나타나는지를 결과에 정직하게 담는다** — 채워지지
않으면 추측으로 Import 를 누르지 않고 MANUAL 로 남긴다.
"""

import ctypes
import os
import string
import time

DRIVE_REMOVABLE = 2

IMPORT_BUTTON_TOOLBAR = 2184     # Examined 툴바
DIALOG_DRIVE_LABEL = 2062
DIALOG_DRIVE_ARROW = 1           # 2062 옆 드롭다운 화살표(자식 ctrl_id)
DIALOG_PATH_EDIT = 2065
DIALOG_BROWSE_BUTTON = 2063      # 폴더 찾아보기(SHBrowseForFolder) 를 연다
DIALOG_RESULT_LIST = 2066
DIALOG_IMPORT_BUTTON = 2064
DIALOG_CLOSE_BUTTON = 1102


def find_usb_drive():
    """이동식(USB) 드라이브의 루트 경로를 찾는다. 없으면 None.

    `GetDriveTypeW(root) == DRIVE_REMOVABLE` 로 판별한다 — 고정 디스크(C:\\
    등 `DRIVE_FIXED`)나 네트워크 드라이브는 대상이 아니다.
    """
    kernel32 = ctypes.windll.kernel32
    bitmask = kernel32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if not (bitmask >> i) & 1:
            continue
        root = f"{letter}:\\"
        try:
            drive_type = kernel32.GetDriveTypeW(root)
        except Exception:
            continue
        if drive_type == DRIVE_REMOVABLE:
            return root
    return None


def open_import_dialog(ui, timeout=10):
    """Examined 창에서 Import Study 대화상자를 연다(검사 미선택 상태로 호출)."""
    from core.flows import FlowError
    hits = [c for c in ui.by_id(IMPORT_BUTTON_TOOLBAR) if c.visible]
    if not hits:
        raise FlowError(f"Import 버튼({IMPORT_BUTTON_TOOLBAR})을 찾지 못했습니다.")
    ui.click(hits[0], settle=1.5)
    end = time.time() + timeout
    while time.time() < end:
        d = ui.dialog()
        if d and [c for c in ui.by_id(DIALOG_PATH_EDIT) if c.visible]:
            return d
        time.sleep(.3)
    raise FlowError("Import Study 대화상자가 열리지 않았습니다.")


def set_import_path(ui, path):
    """검색 경로 Edit(2065)에 경로를 써넣고 되읽어 확인한다."""
    from core.flows import FlowError
    hits = [c for c in ui.by_id(DIALOG_PATH_EDIT) if c.visible]
    if not hits:
        raise FlowError(f"Import 경로 Edit({DIALOG_PATH_EDIT})을 찾지 못했습니다.")
    ui.set_text(hits[0], path)
    ui.key("enter", settle=1.5)
    got = (ui.get_text(hits[0]) or "").strip()
    if os.path.normcase(os.path.normpath(got)) != os.path.normcase(os.path.normpath(path)):
        raise FlowError(f"Import 경로가 반영되지 않았습니다(기대 {path!r}, 실제 {got!r}).")
    return got


def list_rows(ui):
    """결과 목록(2066)의 owner-draw 행 개수. 내용 텍스트는 읽지 않는다(미해결)."""
    hits = [c for c in ui.by_id(DIALOG_RESULT_LIST) if c.visible]
    if not hits:
        return 0
    from core.ui import children
    seen = set()
    count = 0
    for c in children(hits[0].hwnd, 4):
        if c.text == "ListItem" and c.visible and c.hwnd not in seen:
            seen.add(c.hwnd)
            count += 1
    return count


def close_import_dialog(ui, timeout=8):
    hits = [c for c in ui.by_id(DIALOG_CLOSE_BUTTON) if c.visible]
    if hits:
        ui.click(hits[0], settle=1.0)
    end = time.time() + timeout
    while time.time() < end:
        if not ui.dialog():
            return True
        time.sleep(.3)
    return False


def attempt_import(ui, path):
    """Import Study 대화상자를 열어 경로를 설정하고, 목록에 행이 나타나면
    Import 까지 수행한다. 행이 안 나타나면 **누르지 않고** 그 사실을 그대로
    돌려준다(추측으로 Import 버튼을 누르지 않는다).

    반환: {"opened": bool, "path_set": str|None, "rows": int,
           "imported_clicked": bool, "closed": bool}
    """
    outcome = {"opened": False, "path_set": None, "rows": 0,
              "imported_clicked": False, "closed": False}
    open_import_dialog(ui)
    outcome["opened"] = True
    outcome["path_set"] = set_import_path(ui, path)
    time.sleep(1.5)
    outcome["rows"] = list_rows(ui)
    if outcome["rows"] > 0:
        hits = [c for c in ui.by_id(DIALOG_IMPORT_BUTTON) if c.visible]
        if hits:
            ui.click(hits[0], settle=2.0)
            outcome["imported_clicked"] = True
    outcome["closed"] = close_import_dialog(ui)
    return outcome
