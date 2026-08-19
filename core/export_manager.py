# -*- coding: utf-8 -*-
"""Export Manager 제어.

Examined 창의 Export 버튼(`2191`)을 누르면 **별도 최상위 프로세스**
`EXPORT.MANAGER.exe`가 뜬다. Viewer 프로세스에 붙은 `ViewerUi()`로는 이 창의
컨트롤이 보이지 않으므로 `ViewerUi("EXPORT.MANAGER")`로 따로 붙어야 한다
(2026-08-18 실측).

경로는 **제품 기본값을 그대로 쓴다**(사용자 확정). `CONFIGURATION.EXPORT.
ExportDirPath`가 `None`이어도 경로 Edit(`1023`)에는
`<data_dir>\\Export`가 이미 채워져 있고 폴더 선택 창은 뜨지 않는다. 그래서
config에 경로를 하드코딩하지 않고 **화면에 표시된 값을 읽어** 그 폴더를 검증한다.
"""

import os
import time

from core.ui import ViewerUi

PROCESS = "EXPORT.MANAGER"

# 실측 컨트롤 ID (2026-08-18, Bellalun 1.0.12.105)
FORMAT_DICOM = 1009
PATH_DRIVE = 1019
PATH_EDIT = 1023            # cls=Edit, 기본값 <data_dir>\Export
TYPE_PROCESSED = 1025
TYPE_NOT_PROCESSED = 1024
TYPE_SYNTHETIC = 1026
OPT_DOSE_SR = 1027
OPT_PORTABLE_VIEWER = 1032
ANONYMOUS = 1031
STUDY_LIST = 1033
START = 1017
CANCEL = 1018


class ExportManagerError(RuntimeError):
    pass


def attach(timeout=20):
    """Export Manager 창이 뜰 때까지 기다린 뒤 그 UI 드라이버를 돌려준다."""
    end = time.time() + timeout
    while time.time() < end:
        ui = ViewerUi(PROCESS)
        if ui.pid and ui.main_window():
            return ui
        time.sleep(.5)
    raise ExportManagerError(
        f"Export Manager({PROCESS}) 창이 {timeout}초 안에 열리지 않았습니다.")


def read_path(ui):
    """경로 Edit에 표시된 Export 폴더를 읽는다(제품 기본값)."""
    hits = [c for c in ui.by_id(PATH_EDIT) if c.cls == "Edit"]
    if not hits:
        raise ExportManagerError(f"Export 경로 Edit({PATH_EDIT})을 찾지 못했습니다.")
    return (ui.get_text(hits[0]) or "").strip()


def _click(ui, ctrl_id, what, settle=1.0):
    hits = [c for c in ui.by_id(ctrl_id) if c.visible]
    if not hits:
        raise ExportManagerError(f"{what}(ID {ctrl_id})을 찾지 못했습니다.")
    ui.click(hits[0], settle=settle)
    return hits[0]


def cancel(ui, timeout=10):
    """창을 닫는다(Export 전에는 Cancel, 완료 후에는 Close 역할).

    완료 안내 팝업이 떠 있으면 그 모달이 이 버튼 클릭을 삼킨다(2026-08-18 실측:
    Cancel이 계속 실패하고 프로세스가 남았다). 그래서 **먼저 팝업을 닫는다.**
    """
    _confirm_done(ui, timeout=3)
    try:
        _click(ui, CANCEL, "Export Cancel/Close", settle=1.5)
    except ExportManagerError:
        return False
    end = time.time() + timeout
    while time.time() < end:
        if not ViewerUi(PROCESS).pid:
            return True
        time.sleep(.5)
    return False


def set_path(ui, path):
    """Export 경로 Edit(1023)에 경로를 써넣고 되읽어 확인한다.

    `PATH_EDIT`은 실제 `Edit` 컨트롤이라 `set_text`가 통한다(실측). 폴더 선택
    창을 띄우지 않으므로 경로를 직접 지정할 수 있다.

    개정본 WF_09는 Normal 과 Anonymous 를 **별도 경로**로 내보내라고 한다
    (Step 6 "Anonymous 옵션과 별도 경로를 선택한다"). 같은 경로에 두 번 내보내면
    덮어써서 두 결과를 비교할 수 없다.
    """
    hits = [c for c in ui.by_id(PATH_EDIT) if c.cls == "Edit"]
    if not hits:
        raise ExportManagerError(f"Export 경로 Edit({PATH_EDIT})을 찾지 못했습니다.")
    os.makedirs(path, exist_ok=True)
    ui.set_text(hits[0], path)
    got = (ui.get_text(hits[0]) or "").strip()
    if os.path.normcase(os.path.normpath(got)) != os.path.normcase(
            os.path.normpath(path)):
        raise ExportManagerError(
            f"Export 경로가 반영되지 않았습니다(기대 {path!r}, 실제 {got!r}).")
    return got


def is_checked(ui, ctrl_id):
    """체크 상태를 읽는다. 커스텀 컨트롤이라 표준 메시지가 통하지 않는다.

    `core.screen.radio_selected`가 컨트롤 좌상단의 표시 색으로 판정한다
    (이 저장소가 라디오/체크 판정에 쓰는 방식과 같다).
    """
    hits = [c for c in ui.by_id(ctrl_id) if c.visible]
    if not hits:
        return None
    from core import screen
    try:
        return bool(screen.radio_selected(hits[0]))
    except Exception:
        return None


def set_anonymous(ui, enabled=True, attempts=3):
    """Anonymous 옵션(1031)을 원하는 상태로 만든다.

    토글이므로 **누르기 전에 현재 상태를 확인**하고, 누른 뒤 실제로 바뀌었는지
    다시 확인한다(운영 지침 11절 - 조작 전후 상태 확인).

    반환: {"requested": bool, "final": bool|None, "clicked": int}
    """
    clicked = 0
    for _ in range(attempts):
        state = is_checked(ui, ANONYMOUS)
        if state is enabled:
            return {"requested": bool(enabled), "final": state,
                    "clicked": clicked}
        hits = [c for c in ui.by_id(ANONYMOUS) if c.visible]
        if not hits:
            raise ExportManagerError(
                f"Anonymous 옵션({ANONYMOUS})을 찾지 못했습니다.")
        ui.click(hits[0], settle=.8)
        clicked += 1
    return {"requested": bool(enabled), "final": is_checked(ui, ANONYMOUS),
            "clicked": clicked}


def export(ui, wait=120, poll=2.0):
    """Start를 눌러 내보내고, 경로에 파일이 생길 때까지 기다린다.

    "내보냈다"를 버튼 클릭으로 판정하지 않는다. **경로에 실제로 생긴 파일**을
    증거로 삼고, 창이 닫히는 것까지 확인한다(운영 지침 2절).

    반환: {"path": ..., "files": [...], "closed": bool}
    """
    path = read_path(ui)
    if not path:
        raise ExportManagerError("Export 경로가 비어 있습니다.")
    before = _snapshot(path)
    _click(ui, START, "Export Start", settle=2.0)

    end = time.time() + wait
    created = []
    while time.time() < end:
        after = _snapshot(path)
        created = sorted(p for p, meta in after.items()
                         if before.get(p) != meta)
        if created:
            break
        time.sleep(poll)

    # 성공하면 "Export was successful. The Export Manager closes." 안내가 뜨고
    # (Status=Done) **OK를 눌러야 창이 닫힌다**(2026-08-18 실측). 이 모달을
    # 방치하면 이후 조작이 전부 막힌다 - 이 저장소에서 반복 확인된 문제다.
    confirmed = _confirm_done(ViewerUi(PROCESS))

    # 안내에서 "The Export Manager closes"라고 하지만 실제로 창이 사라지는 데
    # 시간이 걸리고, 남는 경우도 있다. 남아 있으면 Close로 정리한다 —
    # 모달이 남으면 이후 TC의 클릭이 전부 막힌다.
    closed = False
    end = time.time() + 20
    while time.time() < end:
        if not ViewerUi(PROCESS).pid:
            closed = True
            break
        time.sleep(.5)
    if not closed:
        closed = cancel(ViewerUi(PROCESS), timeout=15)
    return {"path": path, "files": created, "closed": closed,
            "done_confirmed": confirmed}


def _confirm_done(ui, timeout=10):
    """완료 안내 팝업의 OK를 누른다. 없으면 None."""
    if not ui.pid:
        return None
    end = time.time() + timeout
    while time.time() < end:
        dialog = ui.dialog()
        if dialog:
            from core.ui import children
            buttons = [c for c in children(dialog.hwnd, 3)
                       if c.visible and (c.rect[2] - c.rect[0]) >= 60
                       and 24 <= (c.rect[3] - c.rect[1]) <= 80]
            if buttons:
                # 안내 팝업은 OK 하나뿐이다. 여러 개면 가장 왼쪽(긍정)을 누른다.
                ui.click(min(buttons, key=lambda c: c.rect[0]), settle=1.5)
                return True
        time.sleep(.5)
    return False


def _snapshot(path):
    """경로 하위 파일의 {경로: (크기, mtime_ns)}.

    파일 **목록**만 비교하면 안 된다. Export는 같은 검사를 다시 내보낼 때
    **같은 경로·같은 파일명에 덮어쓰므로** 집합 차집합이 비어 "실패"로 오판된다
    (2026-08-18 실측: 로그에 `Export Manager export started/ended`가 남고 파일
    mtime도 갱신됐는데 판정만 FAIL이었다). 크기·수정시각까지 포함해 갱신을
    감지한다.
    """
    out = {}
    if not path or not os.path.isdir(path):
        return out
    for dirpath, _, files in os.walk(path):
        for name in files:
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            out[full] = (st.st_size, st.st_mtime_ns)
    return out
