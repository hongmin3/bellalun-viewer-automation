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
import re
import time

from core.ui import ViewerUi

PROCESS = "EXPORT.MANAGER"

# 실측 컨트롤 ID (2026-08-18, Bellalun 1.0.12.105)
# File Format 그리드는 2026-09-08 재실측으로 전부 확정됐다(WU_09 조사).
# 기존 FORMAT_DICOM=1009는 이름이 잘못 붙어 있었다 — 실제로는 DICOMDIR
# 버튼이다(선택하면 Portable Viewer(1032)가 활성화되고 DICOMDIR 파일 +
# PortView\ 폴더가 생성됨을 라이브로 확인). 진짜 "DICOM" 버튼은 1008이다.
FORMAT_DICOM = 1008
FORMAT_DICOMDIR = 1009      # 선택하면 Portable Viewer(1032)가 활성화된다
FORMAT_IMG = 1010           # Import Study 가 되읽을 수 있는 유일한 포맷(실측)
FORMAT_JPEG = 1011
FORMAT_TIF8 = 1012
FORMAT_TIF16 = 1013
FORMAT_BMP = 1014
FORMAT_RAW = 1015

# File Format 그리드 전체(독립 체크박스) — `select_only_format`이 쓴다.
ALL_FORMATS = (FORMAT_DICOM, FORMAT_DICOMDIR, FORMAT_IMG, FORMAT_JPEG,
               FORMAT_TIF8, FORMAT_TIF16, FORMAT_BMP, FORMAT_RAW)
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


# A timed-out export must not be interrupted by callers' finally/cancel cleanup.
_PENDING_EXPORTS = set()
_CONFIRMED_EXPORTS = set()


def _manager_window(ui):
    matches = [window for window in ui.windows() if window.visible
               and any(control.visible for control in ui.by_id(PATH_EDIT, window))]
    return matches[0] if len(matches) == 1 else None


def _manager_modals(ui, manager):
    return [window for window in ui.windows()
            if window.visible and window.hwnd != manager.hwnd
            and window.cls == "#32770"
            and window.rect[2] > window.rect[0] and window.rect[3] > window.rect[1]]


def _alive(pid):
    return bool(pid and ViewerUi._alive(pid))


def _wait_exit(pid, timeout):
    end = time.monotonic() + max(0, timeout)
    while _alive(pid):
        if time.monotonic() >= end:
            return False
        time.sleep(min(.5, max(0, end - time.monotonic())))
    _PENDING_EXPORTS.discard(pid)
    _CONFIRMED_EXPORTS.discard(pid)
    return True


def cancel(ui, timeout=10):
    """Close an idle manager; preserve active exports and unknown modals."""
    pid = ui.pid
    if not pid:
        return True
    end = time.monotonic() + max(0, timeout)
    if pid in _CONFIRMED_EXPORTS:
        return _wait_exit(pid, max(0, end-time.monotonic()))
    manager = _manager_window(ui)
    if manager is None:
        return not _alive(pid)
    modals = _manager_modals(ui, manager)
    if pid in _PENDING_EXPORTS or modals:
        completion = wait_export_completion(ui, timeout=max(0, end-time.monotonic()))
        if not (completion["observed"] and completion["dismissed"] and not completion["error"]):
            return not _alive(pid)
        # The product closes itself after acknowledging success. No Cancel input.
        return _wait_exit(pid, max(0, end-time.monotonic()))
    buttons = [button for button in ui.by_id(CANCEL, manager) if button.visible]
    if len(buttons) != 1:
        return False
    ui.click(buttons[0], settle=.3)
    return _wait_exit(pid, max(0, end-time.monotonic()))



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


def _set_toggle(ui, ctrl_id, enabled, what, attempts=3):
    """체크/라디오 컨트롤을 원하는 상태로 만든다(공용).

    누르기 전에 현재 상태를 확인하고, 누른 뒤 실제로 바뀌었는지 다시 확인한다
    (운영 지침 11절 - 조작 전후 상태 확인). `set_anonymous`/`set_portable_viewer`가
    공유한다.
    """
    clicked = 0
    for _ in range(attempts):
        state = is_checked(ui, ctrl_id)
        if state is enabled:
            return {"requested": bool(enabled), "final": state,
                    "clicked": clicked}
        hits = [c for c in ui.by_id(ctrl_id) if c.visible]
        if not hits:
            raise ExportManagerError(f"{what}(ID {ctrl_id})을 찾지 못했습니다.")
        ui.click(hits[0], settle=.8)
        clicked += 1
    return {"requested": bool(enabled), "final": is_checked(ui, ctrl_id),
            "clicked": clicked}


def set_anonymous(ui, enabled=True, attempts=3):
    """Anonymous 옵션(1031)을 원하는 상태로 만든다.

    반환: {"requested": bool, "final": bool|None, "clicked": int}
    """
    return _set_toggle(ui, ANONYMOUS, enabled, "Anonymous 옵션", attempts)


def set_portable_viewer(ui, enabled=True, attempts=3):
    """Portable Viewer 옵션(1032)을 원하는 상태로 만든다.

    DICOMDIR 포맷(`FORMAT_DICOMDIR`)을 먼저 선택해야 이 옵션이 활성화된다
    (2026-09-08 실측 — DICOM 포맷에서는 비활성 상태라 클릭이 반영되지 않을 수
    있다). 반환: {"requested": bool, "final": bool|None, "clicked": int}
    """
    return _set_toggle(ui, OPT_PORTABLE_VIEWER, enabled, "Portable Viewer 옵션",
                        attempts)


def select_format(ui, ctrl_id, attempts=3):
    """File Format 그리드에서 지정한 포맷 버튼을 **체크**한다.

    **주의 — 라디오 그룹이 아니라 독립 체크박스다**(2026-09-08 실측 정정 —
    이전 docstring은 "라디오 방식 그룹"이라 잘못 적어 뒀었다). `FORMAT_DICOMDIR`를
    고른 뒤 이 함수로 `FORMAT_IMG`를 추가로 고르면 **DICOMDIR을 해제하지 않고
    IMG가 함께 켜진 채로 Export 된다**(라이브로 두 체크박스가 동시에 True인
    것을 확인). 다른 포맷만 단독으로 export 하려면 먼저 켜져 있는 포맷을
    `_set_toggle(ui, other_ctrl_id, False, ...)`로 직접 꺼야 한다. 이미
    선택돼 있으면 클릭하지 않는다. 반환:
    {"requested": ctrl_id, "final": bool|None, "clicked": int}
    """
    result = _set_toggle(ui, ctrl_id, True, "Format 버튼", attempts)
    return {"requested": ctrl_id, "final": result["final"],
            "clicked": result["clicked"]}


def select_only_format(ui, ctrl_id, attempts=3):
    """지정 포맷만 켜고 나머지 File Format 체크박스는 전부 끈다.

    `select_format`은 독립 체크박스를 하나 켤 뿐이라 이전에 켜져 있던 포맷이
    함께 Export 된다(2026-09-08 실측: DICOMDIR+IMG 동시 산출). Import 되읽기
    처럼 **산출물 포맷을 정확히 하나로 고정해야** 하는 곳에서 이걸 쓴다.

    1008(DICOM)은 클릭이 반영되지 않는 경우가 관찰됐다 — `_set_toggle`이
    예외를 던지지 않고 최종 상태를 그대로 돌려주므로 호출부가 확인할 수 있다.

    반환: {"selected": {...}, "turned_off": {ctrl_id: {...}}}
    """
    selected = select_format(ui, ctrl_id, attempts)
    turned_off = {}
    for other in ALL_FORMATS:
        if other == ctrl_id:
            continue
        if is_checked(ui, other):
            turned_off[other] = _set_toggle(ui, other, False,
                                            f"Format 버튼({other})", attempts)
    return {"selected": selected, "turned_off": turned_off}


def parse_export_completion(text):
    """Accept only the measured success message, with an optional OK label."""
    raw = text if isinstance(text, str) else ""
    observed = re.fullmatch(
        r"\s*Export\s+was\s+successful\.\s*The\s+Export\s+Manager\s+closes\.\s*(?:OK\s*)?",
        raw, flags=re.I) is not None
    return {"observed": observed, "signal": "export-success-message" if observed else "",
            "raw_text": raw, "error": None if observed else "Export 실제 성공 문구를 확인하지 못했습니다."}


def _export_completion_popup(ui, manager):
    modals = _manager_modals(ui, manager)
    if len(modals) != 1:
        return None
    popup = modals[0]
    left, top, right, bottom = manager.rect
    pl, pt, pr, pb = popup.rect
    if not (left <= pl < pr <= right and top <= pt < pb <= bottom):
        return None
    buttons = ui.dialog_buttons(popup)
    if len(buttons) != 1 or buttons[0].ctrl_id not in (1, 500):
        return None
    return popup


def _completion_evidence_path(evidence_path):
    if evidence_path is not None:
        return os.fspath(evidence_path)
    from bellalunauto.runtime import resolve_layout
    layout = resolve_layout(workspace=os.environ.get("BELLALUN_WORKSPACE"))
    return os.path.join(layout.workspace, "Evidence", "Export",
                        f"ExportCompletion_{time.time_ns()}.png")


def wait_export_completion(ui, timeout=120, poll=.5, evidence_path=None):
    """Observe throughout the export; acknowledge only verified scoped success."""
    from core import screen
    result = dict(parse_export_completion(""), dismissed=False, evidence=None,
                  source=None, popup_hwnd=None)
    end = time.monotonic() + max(0, timeout)
    pid = ui.pid

    def read(popup):
        native = ui.dialog_text(popup) or ""
        if native.strip():
            return native, "native"
        return screen.ocr(popup.rect, scale=3, psm=6), "ocr"

    try:
        while True:
            if not _alive(pid):
                result["error"] = "Export 완료 문구 확인 전에 대상 프로세스가 종료됐습니다."
                return result
            manager = _manager_window(ui)
            if manager is None:
                result["error"] = "Export Manager 창을 유일하게 식별하지 못했습니다."
                return result
            popup = _export_completion_popup(ui, manager)
            if popup is not None:
                saved = ui.capture_dialog(popup, _completion_evidence_path(evidence_path))
                if saved and os.path.isfile(saved) and os.path.getsize(saved) > 0:
                    result["evidence"] = os.fspath(saved)
                raw, source = read(popup)
                result.update(parse_export_completion(raw), source=source, popup_hwnd=popup.hwnd)
                if not result["evidence"]:
                    result["error"] = "Export 완료 팝업 증거 이미지를 저장하지 못했습니다."
                    return result
                if not result["observed"]:
                    return result
                if not _alive(pid) or ui.pid != pid:
                    result["error"] = "Export 완료 확인 전에 대상 프로세스가 바뀌었습니다."
                    return result
                fresh = _export_completion_popup(ui, manager)
                if fresh is None or fresh.hwnd != popup.hwnd or not parse_export_completion(read(fresh)[0])["observed"]:
                    result["error"] = "증거 저장 후 Export 완료 팝업이 달라졌습니다."
                    return result
                ui.click(ui.dialog_buttons(fresh)[0], settle=.3)
                while True:
                    if not _alive(pid) or not any(window.hwnd == popup.hwnd and window.visible for window in ui.windows()):
                        result["dismissed"] = True
                        _CONFIRMED_EXPORTS.add(pid)
                        if _alive(pid) and _manager_modals(ui, manager):
                            result["error"] = "Export 완료 팝업 뒤에 다른 대화상자가 남아 있습니다."
                        return result
                    if time.monotonic() >= end:
                        result["error"] = "Export 완료 팝업이 확인 후에도 닫히지 않았습니다."
                        return result
                    time.sleep(min(.25, max(0, end-time.monotonic())))
            elif _manager_modals(ui, manager):
                modals = _manager_modals(ui, manager)
                result["error"] = "알 수 없는 Export 대화상자 구성을 보존했습니다."
                if len(modals) == 1:
                    saved = ui.capture_dialog(modals[0], _completion_evidence_path(evidence_path))
                    if saved and os.path.isfile(saved) and os.path.getsize(saved) > 0:
                        result["evidence"] = os.fspath(saved)
                    raw, source = read(modals[0])
                    result.update(raw_text=raw, source=source, popup_hwnd=modals[0].hwnd)
                return result
            if time.monotonic() >= end:
                result["error"] = "제한 시간 안에 Export 실제 성공 문구를 확인하지 못했습니다."
                return result
            time.sleep(min(max(.05, poll), max(0, end-time.monotonic())))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def export(ui, wait=120, poll=2.0, *, close_wait=60, evidence_path=None):
    """Wait for actual success, then process exit, before collecting all outputs."""
    path = read_path(ui)
    if not path:
        raise ExportManagerError("Export 경로가 비어 있습니다.")
    pid = ui.pid
    manager = _manager_window(ui)
    if not pid or manager is None or _manager_modals(ui, manager):
        raise ExportManagerError("다른 팝업 없이 Export Manager 창을 확인해야 시작할 수 있습니다.")
    buttons = [button for button in ui.by_id(START, manager) if button.visible]
    if len(buttons) != 1:
        raise ExportManagerError("Export Start 버튼을 유일하게 확인하지 못했습니다.")
    before = _snapshot(path)
    if not _alive(pid) or ui.pid != pid:
        raise ExportManagerError("Export 시작 전에 대상 프로세스가 바뀌었습니다.")
    _PENDING_EXPORTS.add(pid)
    ui.click(buttons[0], settle=.3)
    completion = wait_export_completion(ui, timeout=wait, poll=poll, evidence_path=evidence_path)
    if not (completion["observed"] and completion["dismissed"] and not completion["error"]):
        message = completion["error"] or "Export 실제 완료를 확인하지 못했습니다."
        failure = ExportManagerError(f"{message} (문구={completion['raw_text']!r}, 증거={completion['evidence']!r})")
        failure.completion = completion
        raise failure
    if not _wait_exit(pid, close_wait):
        raise ExportManagerError("Export 완료 확인 후에도 대상 프로세스가 제한 시간 안에 종료되지 않았습니다.")
    after = _snapshot(path)
    created = sorted(name for name, metadata in after.items() if before.get(name) != metadata)
    if not created:
        raise ExportManagerError("Export 완료 후 실제 생성 또는 갱신된 파일이 없습니다.")
    return {"path": path, "files": created, "closed": True,
            "done_confirmed": True, "completion": completion}


def _confirm_done(ui, timeout=10):
    """Compatibility wrapper; unknown dialogs are never acknowledged."""
    if not ui.pid:
        return None
    result = wait_export_completion(ui, timeout=timeout)
    return bool(result["observed"] and result["dismissed"] and not result["error"])



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
