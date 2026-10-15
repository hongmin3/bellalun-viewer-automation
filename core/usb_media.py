# -*- coding: utf-8 -*-
"""USB 이동식 드라이브 탐지와 Examined 창 Import Study 자동화.

Windows Update 체크리스트 TC_WindowsUpdate_09(Study Export) 의 USB 경로
대응. Export 는 `core/export_manager.py` 를 그대로 재사용하고(경로만 USB),
이 모듈은 **되읽기 Import** 를 담당한다.

## Import Study 대화상자 컨트롤 (2026-09-07 실측)

Examined 창에서 대상 검사를 선택하지 않고 **2184(Import)** 를 누르면
"Import Study" 대화상자가 뜬다(툴팁 "Import" 로 확인 — 아이콘 추정 아님).

  2062  드라이브 표시(초기 "C:\\") + 오른쪽 끝 화살표(자식 ctrl_id=1).
        화살표를 누르면 'ItemList' **최상위 팝업 창**이 뜨고 그 안에
        드라이브 수만큼 TextButton 이 들어 있다.
  2065  Edit — 경로 입력란. **읽기 전용으로만 쓴다**(아래 참고).
  2063  CircleButton — 검색이 아니라 **폴더 찾아보기(SHBrowseForFolder)** 를
        여는 버튼. 2062 에서 고른 드라이브 루트에서 트리가 시작한다.
  2066  ListCtrl — 결과 목록(owner-draw). `ListItem` 슬롯이 **9개** 존재하고
        `visible=False` 로 시작한다. 즉 `list_rows()` 의 최대값은 9다.
  2064  Import 버튼, 1102 Close 버튼.

## 스캔 트리거 — 2026-09-09 확정

**경로 Edit(2065)에 `set_text` + Enter 로는 스캔이 절대 시작되지 않는다.**
루트 폴더든 하위 폴더든, 대기를 90초까지 늘려도 목록은 0행이었다(세 세션에
걸친 "0행" 조사의 진짜 원인이 이것이다). 값은 반영되고 되읽어지지만 앱이
입력으로 인지하지 않는다.

**진짜 트리거는 폴더 찾아보기(2063)로 폴더를 고르고 확인을 누르는 것**이다.
사용자가 수동으로 성공하는 화면을 보여줘 확인했고, 같은 절차를 자동화로
재현해 목록이 채워지는 것을 라이브로 검증했다(`D:\\BellalunWU09_imgonly`,
1행). 스캔은 **선택한 폴더 하위를 재귀 탐색**한다.

절차에서 반드시 지킬 것:

1. **2062 에서 대상 드라이브를 먼저 고른다.** 폴더 트리의 시작 위치를
   정하는 것이 이 드롭다운의 역할이다.
2. 드롭다운 항목은 `children()` 열거 순서가 **화면과 역순**이다(실측:
   ctrl_id 3,2,1 순으로 나온다). **y 좌표로 정렬해야** 드라이브 순서와
   맞는다 — 드라이브가 3개일 때는 가운데가 우연히 맞아 버그가 숨는다.
3. 폴더 다이얼로그가 열린 직후 **트리에는 포커스가 없다.** 그대로 Down 을
   보내면 버튼 그룹 이동으로 먹힌다. 루트 노드를 한 번 **클릭**해 포커스를
   준 뒤 Down N 번으로 내려간다(N 은 탐색기 정렬 순서 = 대소문자 무시).
4. 확인은 Enter 가 아니라 **WM_COMMAND(IDOK)** 로 보낸다. 포커스가 "새 폴더
   만들기"에 가 있으면 Enter 가 진짜로 폴더를 만든다(2026-09-09 실측 —
   `C:\\새 폴더` 가 생성돼 지웠다).
5. 선택 결과는 2065 Edit 텍스트로 **사후 검증**한다.

## 드라이브 루트를 선택하면 안 된다 (2026-09-09 실측, 중요)

스캔이 재귀적이라 `C:\\` 루트가 확정되면 **드라이브 전체를 훑는다**
(실측: "Find Images (n/710)" 진행 표시가 17분 넘게 돌았고 그 동안 Close
클릭이 전혀 먹지 않았다 — 중단할 방법이 없다). 그래서 이 모듈은 **드라이브
루트 자체를 대상으로 받지 않고**, 반드시 그 하위 폴더만 고른다.

`SHBrowseForFolder` 에 `BFFM_SETSELECTIONW`(WM_USER+103)를 크로스 프로세스로
보내 임의 깊이를 지정하는 방법도 시험했지만 **이 다이얼로그는 무시했다**
(선택이 초기값 C:\\ 그대로였고, 그 상태로 IDOK 이 나가 위의 전체 스캔이
일어났다). 그래서 키보드 탐색만 쓰고, 대상은 **드라이브 바로 아래 1단계
폴더**로 제한한다.
"""

import ctypes
import os
import re
import string
import time

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

DRIVE_REMOVABLE = 2

IMPORT_BUTTON_TOOLBAR = 2184     # Examined 툴바
DIALOG_DRIVE_LABEL = 2062
DIALOG_DRIVE_ARROW = 1           # 2062 옆 드롭다운 화살표(자식 ctrl_id)
DIALOG_PATH_EDIT = 2065
DIALOG_BROWSE_BUTTON = 2063      # 폴더 찾아보기(SHBrowseForFolder) 를 연다
DIALOG_RESULT_LIST = 2066
DIALOG_IMPORT_BUTTON = 2064
DIALOG_CLOSE_BUTTON = 1102

RESULT_LIST_SLOTS = 9            # owner-draw 행 슬롯 수 = list_rows() 최대값

# "Select Patient Information" — 같은 Patient ID 가 이미 있을 때 Import 를
# 누르면 뜨는 팝업(2026-09-09 실측). 안내 문구가 "You must use existing data
# to import this study." 이므로 되읽기를 진행하려면 1101 을 눌러야 한다.
DUP_RESULT_LIST = 2108
DUP_USE_EXISTING = 1101          # "Use existing data"
DUP_NOT_CHANGE = 1102            # "Not change data" — 아래 경고 참고
# **1102 는 Import Study 의 Close 와 같은 ID 다.** 이 팝업이 떠 있는 동안
# `by_id(1102)` 로 Close 를 찾으면 팝업의 "Not change data" 를 누를 수 있다.
# 그래서 이 모듈은 Close 를 **Import Study 창 범위로 한정해서** 찾는다.

WM_COMMAND = 0x0111
IDOK, IDCANCEL = 1, 2
TVM_ENDEDITLABELNOW = 0x1116     # TV_FIRST + 22
TVM_GETITEMHEIGHT = 0x111C       # TV_FIRST + 28
VK_DOWN = 0x28

FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04


def find_usb_drive():
    """이동식(USB) 드라이브의 루트 경로를 찾는다. 없으면 None.

    `GetDriveTypeW(root) == DRIVE_REMOVABLE` 로 판별한다 — 고정 디스크(C:\\
    등 `DRIVE_FIXED`)나 네트워크 드라이브는 대상이 아니다.
    """
    bitmask = k32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if not (bitmask >> i) & 1:
            continue
        root = f"{letter}:\\"
        try:
            drive_type = k32.GetDriveTypeW(root)
        except Exception:
            continue
        if drive_type == DRIVE_REMOVABLE:
            return root
    return None


def logical_drives():
    """이 PC 의 논리 드라이브 루트 목록(드롭다운 항목 순서와 같다)."""
    bitmask = k32.GetLogicalDrives()
    return [f"{chr(65 + i)}:\\" for i in range(26) if (bitmask >> i) & 1]


def browsable_dirs(root):
    """폴더 트리에 실제로 보이는 `root` 하위 폴더를 화면 순서대로 돌려준다.

    숨김/시스템 폴더(System Volume Information 등)는 트리에 안 나오므로 뺀다.
    정렬은 탐색기와 같은 대소문자 무시 순 — Down 횟수 계산의 근거다.
    """
    out = []
    for name in os.listdir(root):
        full = os.path.join(root, name)
        if not os.path.isdir(full):
            continue
        attrs = k32.GetFileAttributesW(full)
        if attrs != -1 and attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM):
            continue
        out.append(name)
    return sorted(out, key=lambda s: s.lower())


def _uniq(controls):
    """`children()` 은 같은 hwnd 를 여러 번 돌려준다 — 중복을 제거한다."""
    seen, out = set(), []
    for c in controls:
        if c.hwnd not in seen:
            seen.add(c.hwnd)
            out.append(c)
    return out


def open_import_dialog(ui, timeout=10):
    """Examined 창에서 Import Study 대화상자를 연다(검사 미선택 상태로 호출)."""
    from core.flows import FlowError
    if [c for c in ui.by_id(DIALOG_PATH_EDIT) if c.visible]:
        return ui.dialog()                      # 이미 열려 있으면 그대로 쓴다
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


def import_path_text(ui):
    """경로 Edit(2065)의 현재 값. 폴더 선택 결과를 검증할 때 쓴다."""
    hits = [c for c in ui.by_id(DIALOG_PATH_EDIT) if c.visible]
    if not hits:
        return None
    return (ui.get_text(hits[0]) or "").strip()


def set_import_path(ui, path):
    """경로 Edit(2065)에 값을 써넣는다.

    **주의: 이것만으로는 스캔이 시작되지 않는다**(2026-09-09 확정, 모듈
    docstring 참고). 경로를 실제로 반영하려면 `select_import_folder()` 를
    써라. 이 함수는 값 주입 자체를 확인해야 할 때만 남겨 둔다.
    """
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


def select_drive(ui, drive):
    """2062 드롭다운에서 `drive`(예 'D:\\')를 고른다. 반환: 반영된 표시 값.

    이미 그 드라이브면 드롭다운을 열지 않는다.
    """
    from core.flows import FlowError
    from core.ui import children
    hits = [c for c in ui.by_id(DIALOG_DRIVE_LABEL) if c.visible]
    if not hits:
        raise FlowError(f"드라이브 표시({DIALOG_DRIVE_LABEL})를 찾지 못했습니다.")
    label = hits[0]
    current = (ui.get_text(label) or "").strip()
    if os.path.normcase(current) == os.path.normcase(drive):
        return current

    before = {c.hwnd for c in ui.windows()}
    left, top, right, bottom = label.rect
    ui.click((right - 12, (top + bottom) // 2), settle=1.2)   # 오른쪽 끝 화살표

    items = []
    for c in ui.windows():
        if c.hwnd not in before:
            items = [x for x in _uniq(children(c.hwnd, 4))
                     if x.visible and x.text == "TextButton"]
            break
    if not items:
        raise FlowError("드라이브 드롭다운 항목을 찾지 못했습니다.")
    # 열거 순서가 화면과 역순이다 — y 좌표로 정렬해야 드라이브 순서와 맞는다.
    items.sort(key=lambda c: c.rect[1])

    drives = logical_drives()
    if drive not in drives:
        raise FlowError(f"드라이브 {drive} 가 이 PC 에 없습니다({drives}).")
    index = drives.index(drive)
    if index >= len(items):
        raise FlowError(f"드롭다운 항목 수({len(items)})가 드라이브 수({len(drives)})보다 적습니다.")
    ui.click(items[index], settle=1.2)

    got = (ui.get_text([c for c in ui.by_id(DIALOG_DRIVE_LABEL) if c.visible][0]) or "").strip()
    if os.path.normcase(got) != os.path.normcase(drive):
        raise FlowError(f"드라이브가 바뀌지 않았습니다(기대 {drive!r}, 실제 {got!r}).")
    return got


def _browse_dialog(ui):
    """폴더 찾아보기 대화상자와 그 트리. 없으면 (None, None).

    제목 문자열('폴더 찾아보기')은 로케일 의존이라 쓰지 않는다. Import Study
    도 같은 #32770 이므로 SysTreeView32 유무로 구분한다.
    """
    from core.ui import children
    for c in ui.windows():
        if c.cls != "#32770":
            continue
        for ch in children(c.hwnd, 3):
            if ch.cls == "SysTreeView32":
                return c, ch
    return None, None


def cancel_browse_dialog(ui, tries=4):
    """열려 있는 폴더 찾아보기를 취소로 닫는다(없으면 True).

    인라인 이름 편집이 살아 있으면 트리가 마우스를 캡처해 취소 버튼 **클릭이
    통하지 않는다.** 편집을 먼저 끝내고 IDCANCEL 을 메시지로 보낸다.
    """
    for _ in range(tries):
        dlg, tree = _browse_dialog(ui)
        if dlg is None:
            return True
        u32.SendMessageW(tree.hwnd, TVM_ENDEDITLABELNOW, 1, 0)
        time.sleep(0.3)
        u32.PostMessageW(dlg.hwnd, WM_COMMAND, IDCANCEL, 0)
        time.sleep(1.0)
    return _browse_dialog(ui)[0] is None


def select_import_folder(ui, path, settle=1.0):
    """폴더 찾아보기로 `path` 를 골라 Import 경로로 확정한다(스캔 트리거).

    `path` 는 **드라이브 바로 아래 1단계 폴더**여야 한다. 드라이브 루트는
    거부한다 — 재귀 스캔이 드라이브 전체로 번지면 중단할 수단이 없다
    (모듈 docstring 참고). 더 깊은 경로는 지금 트리 탐색으로 지정할 수
    없어 역시 거부한다(Down 횟수는 형제 인덱스라 한 단계만 계산된다).

    반환: 확정된 경로 문자열(2065 Edit 되읽기 값).
    """
    from core.flows import FlowError

    drive, rest = os.path.splitdrive(os.path.normpath(path))
    drive = drive + os.sep
    parts = [p for p in rest.split(os.sep) if p]
    if not parts:
        raise FlowError(
            f"드라이브 루트({path!r})는 Import 대상으로 쓸 수 없습니다 — "
            "재귀 스캔이 드라이브 전체로 번지면 중단할 수 없습니다.")
    if len(parts) > 1:
        raise FlowError(
            f"Import 경로는 드라이브 바로 아래 1단계 폴더만 지원합니다: {path!r} "
            "(폴더 트리를 키보드로 한 단계만 내려갈 수 있습니다).")
    folder = parts[0]

    entries = browsable_dirs(drive)
    if folder not in entries:
        raise FlowError(f"{drive} 트리에 {folder!r} 가 보이지 않습니다({entries}).")
    downs = entries.index(folder) + 1        # 루트 노드에서 아래로 N 번

    select_drive(ui, drive)

    hits = [c for c in ui.by_id(DIALOG_BROWSE_BUTTON) if c.visible]
    if not hits:
        raise FlowError(f"폴더 찾아보기 버튼({DIALOG_BROWSE_BUTTON})을 찾지 못했습니다.")
    ui.click(hits[0], settle=1.5)

    dlg, tree = _browse_dialog(ui)
    if dlg is None:
        raise FlowError("폴더 찾아보기 대화상자가 열리지 않았습니다.")

    try:
        # 트리에 포커스가 없는 상태로 열린다 — 루트 노드를 눌러 포커스를 준다.
        # 왼쪽 끝은 확장 화살표라 라벨 쪽(x+90)을 누른다.
        row_h = u32.SendMessageW(tree.hwnd, TVM_GETITEMHEIGHT, 0, 0) or 21
        ui.click((tree.rect[0] + 90, tree.rect[1] + row_h // 2 + 2), settle=0.6)
        for _ in range(downs):
            ui.raw_key(VK_DOWN, settle=0.15)
        # Enter 는 포커스가 "새 폴더 만들기"에 있으면 폴더를 만든다 — IDOK 를 보낸다.
        u32.PostMessageW(dlg.hwnd, WM_COMMAND, IDOK, 0)
        end = time.time() + 8
        while time.time() < end and _browse_dialog(ui)[0] is not None:
            time.sleep(0.4)
    finally:
        cancel_browse_dialog(ui)

    time.sleep(settle)
    got = import_path_text(ui)
    expected = os.path.join(drive, folder)
    if os.path.normcase(got or "") != os.path.normcase(expected):
        raise FlowError(
            f"폴더 선택이 반영되지 않았습니다(기대 {expected!r}, 실제 {got!r}). "
            "트리 Down 횟수가 화면 순서와 어긋났을 수 있습니다.")
    return got


def list_rows(ui):
    """결과 목록(2066)에 보이는 owner-draw 행 개수(최대 `RESULT_LIST_SLOTS`).

    행 텍스트는 owner-draw 라 읽히지 않는다 — 개수만 센다.
    """
    hits = [c for c in ui.by_id(DIALOG_RESULT_LIST) if c.visible]
    if not hits:
        return 0
    from core.ui import children
    count = 0
    for c in _uniq(children(hits[0].hwnd, 4)):
        if c.text == "ListItem" and c.visible:
            count += 1
    return count


def wait_for_rows(ui, timeout=30, stable=2):
    """목록에 행이 나타날 때까지 기다린다. 반환: 행 개수(0 이면 안 나타남).

    스캔은 폴더를 확정하는 순간 시작된다. 행이 하나 보인 뒤에도 더 늘 수
    있으므로 `stable` 회 연속 같은 값일 때 확정한다.
    """
    end = time.time() + timeout
    last, same = 0, 0
    while time.time() < end:
        n = list_rows(ui)
        if n and n == last:
            same += 1
            if same >= stable:
                return n
        else:
            same = 0
        last = n
        time.sleep(1.0)
    return last


def import_window(ui):
    """Import Study 창(경로 Edit 2065 를 품은 작은 #32770). 없으면 None."""
    from core.ui import children
    for c in ui.windows():
        if c.cls != "#32770":
            continue
        left, top, right, bottom = c.rect
        if (right - left) * (bottom - top) >= ui.MAIN_WINDOW_MIN_AREA:
            continue                      # 메인 화면
        for ch in children(c.hwnd, 4):
            if ch.ctrl_id == DIALOG_PATH_EDIT and ch.visible:
                return c
    return None


def result_rows(ui):
    """결과 목록(2066)의 보이는 행 컨트롤을 화면 순서(위→아래)로 돌려준다."""
    hits = [c for c in ui.by_id(DIALOG_RESULT_LIST) if c.visible]
    if not hits:
        return []
    from core.ui import children
    rows = [c for c in _uniq(children(hits[0].hwnd, 4))
            if c.text == "ListItem" and c.visible]
    return sorted(rows, key=lambda c: c.rect[1])


def select_row(ui, index=0):
    """결과 목록의 행을 클릭해 선택한다.

    **Import 전에 반드시 필요하다** — 행이 목록에 보이기만 하고 선택되지 않은
    상태로 Import 를 누르면 "Please select study to import." 경고만 뜬다
    (2026-09-09 실측).
    """
    from core.flows import FlowError
    rows = result_rows(ui)
    if not rows:
        raise FlowError("Import 결과 목록에 선택할 행이 없습니다.")
    if index >= len(rows):
        raise FlowError(f"행 {index} 가 없습니다(총 {len(rows)}개).")
    ui.click(rows[index], settle=1.0)
    return rows[index]


def duplicate_patient_popup(ui):
    """'Select Patient Information' 팝업. 없으면 None.

    제목이 비어 있는 커스텀 팝업이라 컨트롤 구성(1101/1102 버튼 + 2108 목록)
    으로 식별한다.
    """
    from core.ui import children
    for c in ui.windows():
        if c.cls != "#32770":
            continue
        ids = {ch.ctrl_id for ch in children(c.hwnd, 4) if ch.visible}
        if {DUP_USE_EXISTING, DUP_NOT_CHANGE, DUP_RESULT_LIST} <= ids:
            return c
    return None


def resolve_duplicate_patient(ui, timeout=10):
    """중복 팝업이 떠 있으면 'Use existing data'(1101)를 누른다.

    반환: 팝업을 처리했으면 True, 애초에 없었으면 False.

    팝업 안내가 "You must use existing data to import this study." 이므로
    되읽기를 진행하려면 이 버튼이어야 한다. 버튼 텍스트는 커스텀 렌더라
    OCR 로 읽히지 않았다(빈 문자열) — 위치가 아니라 **컨트롤 ID** 로 고른다.
    """
    popup = duplicate_patient_popup(ui)
    if popup is None:
        return False
    hits = [c for c in ui.by_id(DUP_USE_EXISTING, popup) if c.visible]
    if not hits:
        from core.flows import FlowError
        raise FlowError(f"중복 팝업에서 'Use existing data'({DUP_USE_EXISTING})를 찾지 못했습니다.")
    ui.click(hits[0], settle=1.5)
    end = time.time() + timeout
    while time.time() < end:
        if duplicate_patient_popup(ui) is None:
            return True
        time.sleep(0.4)
    from core.flows import FlowError
    raise FlowError("중복 환자 팝업이 'Use existing data' 선택 후에도 닫히지 않았습니다.")


def parse_import_completion(text, expected=1):
    """실측한 완료 문구와 선택 건수를 함께 검사한다. 입력 동작은 하지 않는다."""
    result = {"observed": False, "signal": "", "raw_text": text if isinstance(text, str) else "",
              "imported": None, "skipped": None, "error": None}
    if type(expected) is not int or expected <= 0:
        return dict(result, error="선택한 Import 기대 건수가 올바르지 않습니다.")
    match = re.fullmatch(
        r"\s*Import\s+completed\.\s*\(\s*Imported\s*:\s*(\d+)\s*/\s*Skipped\s*:\s*(\d+)\s*\)\s*(?:OK\s*)?",
        result["raw_text"], flags=re.I)
    if match is None:
        return dict(result, error="실측한 Import completed 완료 문구를 확인하지 못했습니다.")
    result.update(imported=int(match[1]), skipped=int(match[2]))
    if result["imported"] != expected or result["skipped"] != 0:
        return dict(result, error=f"Import 건수가 기대와 다릅니다(기대 {expected}, "
                                 f"Imported {result['imported']}, Skipped {result['skipped']}).")
    return dict(result, observed=True, signal="import-completed-counts")


def _small_dialogs(ui, import_dialog):
    out = []
    for window in ui.windows():
        if (window.hwnd == import_dialog.hwnd or window.cls != "#32770"
                or not window.visible):
            continue
        left, top, right, bottom = window.rect
        if 0 < (right - left) * (bottom - top) < ui.MAIN_WINDOW_MIN_AREA:
            out.append(window)
    return out


def _completion_popup(ui, import_dialog):
    left, top, right, bottom = import_dialog.rect
    matches = []
    for popup in _small_dialogs(ui, import_dialog):
        pl, pt, pr, pb = popup.rect
        if not (left <= pl < pr <= right and top <= pt < pb <= bottom):
            continue
        buttons = ui.dialog_buttons(popup)
        if len(buttons) == 1 and buttons[0].ctrl_id == 500:
            matches.append(popup)
    return matches[0] if len(matches) == 1 else None


def _completion_evidence_path(evidence_path):
    if evidence_path is not None:
        return os.fspath(evidence_path)
    from bellalunauto.runtime import resolve_layout
    layout = resolve_layout(workspace=os.environ.get("BELLALUN_WORKSPACE"))
    return os.path.join(layout.workspace, "Evidence", "USB", f"ImportCompletion_{time.time_ns()}.png")


def wait_import_completion(ui, timeout=90, expected=1, evidence_path=None):
    """자기 Import 창 안의 완료 팝업을 관찰하고 증거 저장 후에만 OK를 누른다.

    알 수 없는 문구·다른 건수·다른 버튼 구성은 보존한다. Import 창이 사라지거나
    중복 선택 팝업을 닫은 사실은 완료 신호로 취급하지 않는다.
    """
    from core import screen
    result = dict(parse_import_completion("", expected), source=None, evidence=None,
                  dismissed=False, popup_hwnd=None, duplicate_popup=False)
    deadline = time.monotonic() + max(0, timeout)

    def read(popup):
        text = ui.dialog_text(popup) or ""
        if text.strip():
            return text, "native"
        return screen.ocr(popup.rect, scale=3, psm=6), "ocr"

    try:
        while True:
            window = import_window(ui)
            if window is None:
                result["error"] = "Import Study 창이 없어 실제 완료 팝업을 확인할 수 없습니다."
                return result
            duplicate = duplicate_patient_popup(ui)
            if duplicate is not None:
                modals = _small_dialogs(ui, window)
                left, top, right, bottom = window.rect
                dl, dt, dr, db = duplicate.rect
                if (len(modals) != 1 or modals[0].hwnd != duplicate.hwnd
                        or not (left <= dl < dr <= right and top <= dt < db <= bottom)):
                    result["error"] = "다른 팝업과 겹친 중복 환자 대화상자를 보존했습니다."
                    return result
                remaining = deadline - time.monotonic()
                if remaining <= 0 or result["duplicate_popup"]:
                    result["error"] = "제한 시간 또는 반복 중복 환자 팝업 때문에 Import를 중단했습니다."
                    return result
                result["duplicate_popup"] = resolve_duplicate_patient(ui, timeout=min(10, remaining))
                continue
            popup = _completion_popup(ui, window)
            if popup is not None:
                raw, source = read(popup)
                result.update(parse_import_completion(raw, expected), source=source, popup_hwnd=popup.hwnd)
                if not result["observed"]:
                    return result
                path = _completion_evidence_path(evidence_path)
                saved = ui.capture_dialog(popup, path) or path
                if not os.path.isfile(saved) or os.path.getsize(saved) <= 0:
                    result["error"] = "Import 완료 팝업의 증거 이미지를 저장하지 못했습니다."
                    return result
                result["evidence"] = os.fspath(saved)
                # Revalidate the same modal and its text after capture, before
                # acknowledging. Never click an unknown replacement popup.
                fresh = _completion_popup(ui, window)
                if fresh is None or fresh.hwnd != popup.hwnd:
                    result["error"] = "증거 저장 후 Import 완료 팝업 구성이 달라졌습니다."
                    return result
                current, _ = read(fresh)
                if not parse_import_completion(current, expected)["observed"]:
                    result["error"] = "증거 저장 후 Import 완료 문구가 달라졌습니다."
                    return result
                button = ui.dialog_buttons(fresh)[0]  # exactly one scoped ID 500
                ui.click(button, settle=.3)
                while True:
                    if not any(item.hwnd == popup.hwnd and item.visible for item in ui.windows()):
                        result["dismissed"] = True
                        if _small_dialogs(ui, window):
                            result["error"] = "완료 팝업 뒤에 다른 대화상자가 남아 있습니다."
                        return result
                    if time.monotonic() >= deadline:
                        result["error"] = "Import 완료 팝업이 OK 선택 후에도 닫히지 않았습니다."
                        return result
                    time.sleep(.25)
            if time.monotonic() >= deadline:
                result["error"] = "실측한 Import 완료 팝업을 제한 시간 안에 확인하지 못했습니다."
                return result
            time.sleep(.25)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def close_import_dialog(ui, timeout=8):
    """Import Study 를 닫는다.

    Close(1102)는 환자 중복 팝업의 "Not change data" 와 ID 가 같다 — 팝업이
    떠 있으면 엉뚱한 버튼을 누르므로 **Import Study 창 범위로 한정**해서
    찾는다.
    """
    window = import_window(ui)
    if window is None:
        return True
    if _small_dialogs(ui, window):
        return False                         # preserve unknown/duplicate modal
    hits = [c for c in ui.by_id(DIALOG_CLOSE_BUTTON, window) if c.visible]
    if hits:
        ui.click(hits[0], settle=1.0)
    end = time.time() + timeout
    while time.time() < end:
        if import_window(ui) is None:
            return True
        time.sleep(.3)
    return False


def attempt_import(ui, path, wait=30, settle=90, *, expected=1, evidence_path=None):
    """Import Study 를 열어 `path` 를 고르고, 목록의 행을 선택해 Import 한다.

    전체 절차(2026-09-09 실측으로 확정):
      1. 폴더 찾아보기로 `path` 확정 → 스캔 시작
      2. 목록에 행이 나타날 때까지 대기
      3. **행을 클릭해 선택**(안 하면 "Please select study to import.")
      4. Import 클릭
      5. 같은 Patient ID 가 있으면 뜨는 중복 팝업에서 "Use existing data"

    행이 안 나타나면 **추측으로 Import 버튼을 누르지 않는다.** `path` 제약은
    `select_import_folder()` 를 따른다(드라이브 바로 아래 1단계 폴더).

    6. 실측한 Import completed 문구와 건수 확인 → 증거 저장 → scoped OK
    완료 신호는 신규 UID·영상 파일·Examined 재검색과 호출부에서 교차 확인한다.

    반환: {"opened", "path_set", "rows", "row_selected", "imported_clicked",
           "duplicate_popup", "completion", "dialog_closed_itself", "closed", "error"}
    """
    outcome = {"opened": False, "path_set": None, "rows": 0,
               "row_selected": False, "imported_clicked": False,
               "duplicate_popup": False, "dialog_closed_itself": False,
               "closed": False, "error": None, "completion": None, "cleanup_error": None}
    try:
        open_import_dialog(ui)
        outcome["opened"] = True
        outcome["path_set"] = select_import_folder(ui, path)
        outcome["rows"] = wait_for_rows(ui, timeout=wait)
        if outcome["rows"] > 0:
            select_row(ui, 0)
            outcome["row_selected"] = True
            window = import_window(ui)
            if window is None:
                from core.flows import FlowError
                raise FlowError("Import 버튼을 누르기 전에 Import Study 창이 사라졌습니다.")
            hits = [c for c in ui.by_id(DIALOG_IMPORT_BUTTON, window) if c.visible]
            if len(hits) == 1:
                ui.click(hits[0], settle=2.0)
                outcome["imported_clicked"] = True
                completion = wait_import_completion(ui, timeout=settle, expected=expected,
                                                    evidence_path=evidence_path)
                outcome["completion"] = completion
                outcome["duplicate_popup"] = bool(completion.get("duplicate_popup"))
                if not (completion.get("observed") and completion.get("dismissed") and not completion.get("error")):
                    outcome["error"] = completion.get("error") or "Import 완료를 확인하지 못했습니다."
                else:
                    outcome["dialog_closed_itself"] = import_window(ui) is None
            else:
                from core.flows import FlowError
                raise FlowError("Import Study 창에서 유일한 Import 버튼을 확인하지 못했습니다.")
    except Exception as exc:
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            cancel_browse_dialog(ui)
        except Exception as exc:
            outcome["cleanup_error"] = f"폴더 찾아보기 정리: {type(exc).__name__}: {exc}"
        completion = outcome["completion"] or {}
        safe_to_close = (not outcome["imported_clicked"] or
                         (completion.get("observed") and completion.get("dismissed") and not completion.get("error")))
        if outcome["opened"] and safe_to_close:
            try:
                outcome["closed"] = close_import_dialog(ui)
                if not outcome["closed"]:
                    outcome["cleanup_error"] = "다른 팝업 또는 처리 중 상태 때문에 Import Study를 닫지 못했습니다."
            except Exception as exc:
                outcome["cleanup_error"] = f"Import Study 정리: {type(exc).__name__}: {exc}"
        elif outcome["opened"]:
            outcome["cleanup_error"] = "실제 완료를 확인하지 못해 Import 팝업과 창을 보존했습니다."
        if outcome["cleanup_error"] and not outcome["error"]:
            outcome["error"] = outcome["cleanup_error"]
    return outcome
