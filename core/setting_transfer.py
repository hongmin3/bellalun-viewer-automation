# -*- coding: utf-8 -*-
r"""Setting > System > My Settings 의 Export / Import 를 구동한다 (WF_14).

## 사양 근거

사양서1 "60. Setting Export/Import" (SRS 는 `core/specs.py` 로 인용한다)

- `Setting > System > My Setting에서 뷰어 설정을 내보내거나 가져올 수 있다.`
- Export: `선택한 위치에 설정 정보를 .vms 확장자로 저장한다`,
  저장 Data 는 `Study 정보를 제외한 모든 설정 정보 (DB / sql file)` +
  `External Input 설정 파일` + `XIPL Parameter 정보`
- Export 개발 사양: `.zip 파일로 설정을 내보낸다. (확장자 변경 .vms)`,
  `DATA를 제외한 모든 DB 백업파일(CONFIGURATION, ACCOUNT, PROCEDURE)`,
  `XIPL Parameter 폴더 내에 있는 모든 Parameter 파일을 Export\PARAMETER 폴더에`,
  `ExternalInput.xml 파일을 Export\Config 폴더에`
- Import: `System / Account / Procedure 중 사용자가 선택한 설정 값만 가져와서
  적용할 수 있다`, `Import 한 설정은 Viewer를 재시작해야 적용된다`,
  `Import 한 후 재시작 전에 변경한 내용은 적용되지 않는다. (해당 내용
  메시지박스로 사용자에게 표시)`

## 실측 (2026-08-21, Bellalun 1.0.12.105 / 1920x1080 / 96DPI)

`Export`(2293) 는 **Windows 표준 저장 대화상자**(`#32770` "다른 이름으로 저장")를
띄운다. 파일 이름 Edit 은 `1148`(cls=`Edit`), 저장 버튼은 `1`, 취소는 `2`,
파일 형식 콤보(`1136`)는 `vms file (*.vms)` 였다. 저장이 끝나면 버튼 하나(`500`)
짜리 완료 팝업이 뜬다.

`Import`(2294) 는 표준 열기 대화상자가 **아니라 제품 자체 모달**이다
(캡처: `Evidence/ui/wf14_import_dialog.png`). OCR 로 문구를 읽어 확정했다.

| 컨트롤 | 정체 |
|---|---|
| `2075` (cls=`Edit`) | File Path 입력 |
| `2073` CircleButton | `...` 파일 찾아보기 |
| `2076` / `2077` / `2078` CheckBox | **System / Account / Procedure** — 사양의 선택 항목 |
| `2074` TextButton | `Import` |
| `1102` TextButton | `Close` |
| `-4` IconButton | 창 닫기(x) |

기본 상태는 **System 만 체크**돼 있다(핑크 채움, 나머지는 회색).
체크 여부는 `core/screen.radio_selected` 로 읽는다(이 저장소가 커스텀
라디오/체크 판정에 쓰는 방식과 같다).
"""

from __future__ import annotations

import os
import time
import zipfile

from core import flows, screen, uitext
from core.ui import children

# --- Export: Windows 표준 저장 대화상자 -------------------------------
SAVE_DIALOG = {
    "file_name": 1148,      # cls=Edit
    "file_type": 1136,      # cls=ComboBox  ("vms file (*.vms)")
    "save": 1,              # cls=Button
    "cancel": 2,            # cls=Button
}
SAVE_DIALOG_TITLES = ("다른 이름으로 저장", "save as")

# --- Import: 제품 자체 모달 -------------------------------------------
IMPORT_DIALOG = {
    "file_path": 2075,      # cls=Edit
    "browse": 2073,
    "opt_system": 2076,
    "opt_account": 2077,
    "opt_procedure": 2078,
    "import": 2074,
    "close": 1102,
}
IMPORT_OPTIONS = {"system": 2076, "account": 2077, "procedure": 2078}

# 사양서1 Export 개발 사양이 요구하는 .vms 구성.
#   `PARAMETER_QC/` 와 `RECON_PARAMETER/` 는 사양 본문이 `PARAMETER` 로만
#   적었지만 제품은 용도별로 나눠 담는다(2026-08-21 실측). 사양보다 세분화된
#   것이므로 결함으로 보지 않고, 요구된 내용이 들어 있는지로 판정한다.
VMS_REQUIRED = ("CONFIGURATION.bak", "ACCOUNT.bak", "PROCEDURE.bak",
                "Config/ExternalInput.xml")
VMS_REQUIRED_PREFIX = ("PARAMETER/",)


class SettingTransferError(RuntimeError):
    pass


def _visible(ui, ctrl_id, min_w=20):
    return [c for c in ui.controls(max_depth=8)
            if c.ctrl_id == ctrl_id and c.visible
            and c.rect[2] - c.rect[0] > min_w]


def open_my_settings(ui, wait=3.0):
    return flows.open_system_setting(ui, "my_settings", wait=wait)


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------
def click_export(ui, timeout=20):
    """Export Setting(2293) 을 누르고 저장 대화상자가 뜰 때까지 기다린다.

    반환: (dialog, {"title":.., "file_type":.., "default_name":..})
    """
    hits = _visible(ui, flows.SETTING_MY_SETTINGS["export"])
    if not hits:
        raise SettingTransferError(
            f"Export Setting 버튼({flows.SETTING_MY_SETTINGS['export']})을 "
            "찾지 못했습니다. Setting > System > My Settings 화면인지 확인하십시오.")
    ui.click(hits[0], settle=1.5)
    dlg = ui.wait_dialog(timeout=timeout)
    if not dlg:
        raise SettingTransferError(
            "Export 저장 대화상자가 열리지 않았습니다(제한시간 "
            f"{timeout}초).")
    kids = children(dlg.hwnd, 5)
    info = {"title": dlg.text}
    ftype = next((c for c in kids if c.ctrl_id == SAVE_DIALOG["file_type"]
                  and c.cls == "ComboBox"), None)
    info["file_type"] = ftype.text if ftype else None
    name = next((c for c in kids if c.ctrl_id == SAVE_DIALOG["file_name"]
                 and c.cls == "Edit"), None)
    info["default_name"] = name.text if name else None
    return dlg, info


def save_export(ui, dlg, target, timeout=300, poll=2.0):
    """저장 대화상자에 경로를 넣고 저장한다. 파일이 안정될 때까지 기다린다.

    반환: {"path":.., "size":.., "seconds":.., "done_dialog": bool}
    """
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    if os.path.exists(target):
        os.remove(target)

    kids = children(dlg.hwnd, 5)
    edit = next((c for c in kids if c.ctrl_id == SAVE_DIALOG["file_name"]
                 and c.cls == "Edit"), None)
    save = next((c for c in kids if c.ctrl_id == SAVE_DIALOG["save"]
                 and c.cls == "Button"), None)
    if edit is None or save is None:
        raise SettingTransferError(
            "저장 대화상자에서 파일 이름 Edit(1148) 또는 저장 버튼(1)을 "
            "찾지 못했습니다.")
    ui.set_text(edit, target)
    got = ui.get_text(edit)
    if os.path.normcase(os.path.normpath(got or "")) != \
            os.path.normcase(os.path.normpath(target)):
        raise SettingTransferError(
            f"저장 경로가 반영되지 않았습니다(기대 {target!r}, 실제 {got!r}).")

    started = time.time()
    ui.click(save, settle=1.5)

    # 파일이 생기고 **크기가 멈출 때까지** 기다린다. 고정 대기를 쓰지 않는다.
    last, stable = -1, 0
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(target):
            size = os.path.getsize(target)
            if size > 0 and size == last:
                stable += 1
                if stable >= 3:
                    break
            else:
                stable = 0
            last = size
        time.sleep(poll)
    seconds = round(time.time() - started, 1)
    if not os.path.exists(target):
        raise SettingTransferError(
            f"Export 파일이 생성되지 않았습니다: {target} ({seconds}초 대기)")

    # 완료 팝업(버튼 500 하나)을 닫는다. 방치하면 이후 클릭이 전부 삼켜진다
    # (운영 지침: 조작 후 확인 없는 코드 금지 — Overlay Update 팝업 사례).
    done = _dismiss_done_popup(ui)
    return {"path": target, "size": os.path.getsize(target),
            "seconds": seconds, "done_dialog": done}


def _dismiss_done_popup(ui, timeout=15):
    """확인 버튼(500) 하나뿐인 완료 팝업을 닫는다. 없으면 False."""
    end = time.time() + timeout
    while time.time() < end:
        dlg = ui.dialog()
        if dlg:
            btns = [c for c in children(dlg.hwnd, 4)
                    if c.ctrl_id == flows.SETTING_CONFIRM_OK
                    and c.rect[2] - c.rect[0] > 20]
            if btns:
                ui.click(btns[0], settle=1.2)
                return True
        time.sleep(0.5)
    return False


def inspect_vms(path):
    """`.vms` 가 사양서1 개발 사양대로 구성됐는지 확인한다.

    반환: {"is_zip":.., "entries":[..], "missing":[..], "version":..}
    """
    out = {"is_zip": zipfile.is_zipfile(path), "entries": [], "missing": [],
           "version": None}
    if not out["is_zip"]:
        with open(path, "rb") as f:
            out["head"] = f.read(16).hex()
        out["missing"] = list(VMS_REQUIRED) + list(VMS_REQUIRED_PREFIX)
        return out
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        out["entries"] = names
        if "Version.txt" in names:
            try:
                out["version"] = z.read("Version.txt").decode(
                    "utf-8", "replace").strip()
            except Exception:                          # noqa: BLE001
                out["version"] = "<읽기 실패>"
    lower = [n.replace("\\", "/") for n in names]
    for want in VMS_REQUIRED:
        if want not in lower:
            out["missing"].append(want)
    for prefix in VMS_REQUIRED_PREFIX:
        if not any(n.startswith(prefix) for n in lower):
            out["missing"].append(prefix + "*")
    return out


# ---------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------
def click_import(ui, timeout=20, tesseract_exe=None):
    """Import Setting(2294) 을 누르고 제품 모달이 뜰 때까지 기다린다.

    반환: (dialog, {"labels": [...], "buttons": {...}, "options": {...}})
    """
    hits = _visible(ui, flows.SETTING_MY_SETTINGS["import"])
    if not hits:
        raise SettingTransferError(
            f"Import Setting 버튼({flows.SETTING_MY_SETTINGS['import']})을 "
            "찾지 못했습니다.")
    ui.click(hits[0], settle=1.5)
    dlg = ui.wait_dialog(timeout=timeout)
    if not dlg:
        raise SettingTransferError(
            f"Import 대화상자가 열리지 않았습니다(제한시간 {timeout}초).")
    kids = children(dlg.hwnd, 5)
    info = {"labels": [], "buttons": {}, "options": {}}
    for c in kids:
        if c.ctrl_id == 1001:
            info["labels"].append(uitext.ocr(c, tesseract_exe))
    for name, cid in (("import", IMPORT_DIALOG["import"]),
                      ("close", IMPORT_DIALOG["close"])):
        hit = next((c for c in kids if c.ctrl_id == cid), None)
        info["buttons"][name] = uitext.ocr(hit, tesseract_exe) if hit else None
    for name, cid in IMPORT_OPTIONS.items():
        hit = next((c for c in kids if c.ctrl_id == cid), None)
        info["options"][name] = {
            "found": hit is not None,
            "label": uitext.ocr(hit, tesseract_exe) if hit else None,
            "checked": screen.radio_selected(hit) if hit else None,
        }
    return dlg, info


def set_import_option(ui, dlg, name, enabled=True, attempts=3):
    """Import 옵션 체크박스를 원하는 상태로 만든다.

    토글이므로 **누르기 전에 상태를 읽고, 누른 뒤 실제로 바뀌었는지 다시 읽는다.**
    """
    cid = IMPORT_OPTIONS[name]
    clicked = 0
    for _ in range(attempts):
        hit = next((c for c in children(dlg.hwnd, 5) if c.ctrl_id == cid), None)
        if hit is None:
            raise SettingTransferError(
                f"Import 옵션 {name}({cid}) 을 찾지 못했습니다.")
        state = screen.radio_selected(hit)
        if state is enabled:
            return {"option": name, "final": state, "clicked": clicked}
        ui.click(hit, settle=0.8)
        clicked += 1
    hit = next((c for c in children(dlg.hwnd, 5) if c.ctrl_id == cid), None)
    return {"option": name, "final": screen.radio_selected(hit) if hit else None,
            "clicked": clicked}


def run_import(ui, dlg, source, options=("system",), timeout=300,
               tesseract_exe=None):
    """Import 모달에 파일 경로와 옵션을 넣고 Import 를 실행한다.

    반환: {"path":.., "options":{..}, "message":.., "seconds":.., "closed":..}
    """
    if not os.path.isfile(source):
        raise SettingTransferError(f"Import 대상 파일이 없습니다: {source}")

    kids = children(dlg.hwnd, 5)
    edit = next((c for c in kids if c.ctrl_id == IMPORT_DIALOG["file_path"]),
                None)
    if edit is None:
        raise SettingTransferError(
            f"Import File Path Edit({IMPORT_DIALOG['file_path']}) 을 "
            "찾지 못했습니다.")
    ui.set_text(edit, source)
    got = ui.get_text(edit)
    if os.path.normcase(os.path.normpath(got or "")) != \
            os.path.normcase(os.path.normpath(source)):
        # 표준 Edit 이 아니면 set_text 가 통하지 않을 수 있어 키 입력으로 재시도
        ui.type_text(edit, source, clear=True, settle=0.5)
        got = ui.get_text(edit)
        if os.path.normcase(os.path.normpath(got or "")) != \
                os.path.normcase(os.path.normpath(source)):
            raise SettingTransferError(
                f"Import 경로가 반영되지 않았습니다(기대 {source!r}, "
                f"실제 {got!r}).")

    applied = {}
    for name in IMPORT_OPTIONS:
        applied[name] = set_import_option(ui, dlg, name, name in options)

    btn = next((c for c in children(dlg.hwnd, 5)
                if c.ctrl_id == IMPORT_DIALOG["import"]), None)
    if btn is None:
        raise SettingTransferError(
            f"Import 버튼({IMPORT_DIALOG['import']}) 을 찾지 못했습니다.")
    started = time.time()
    ui.click(btn, settle=2.0)

    # 사양: "Import 한 후 재시작 전에 변경한 내용은 적용되지 않는다.
    #        (해당 내용 메시지박스로 사용자에게 표시)"
    # → 안내 메시지가 뜨는 것이 정상이다. 읽어서 증거로 남기고 닫는다.
    #
    # **끝나는 조건을 둘 다 본다**: 새 대화상자가 뜨거나, Import 모달이 사라지거나.
    # 하나만 기다리면 다른 쪽으로 끝났을 때 제한시간을 그대로 소모한다.
    message = None
    end = time.time() + timeout
    while time.time() < end:
        d = ui.dialog()
        if d and d.hwnd != dlg.hwnd:
            message = flows.read_dialog_message(ui, d, tesseract_exe)
            btns = [c for c in children(d.hwnd, 4)
                    if c.ctrl_id == flows.SETTING_CONFIRM_OK
                    and c.rect[2] - c.rect[0] > 20]
            if btns:
                ui.click(btns[0], settle=1.2)
            else:
                ui.dismiss_dialog(timeout=5)
            break
        if not any(w.hwnd == dlg.hwnd for w in ui.windows()):
            break
        time.sleep(0.5)

    seconds = round(time.time() - started, 1)
    closed = _wait_dialog_gone(ui, dlg, timeout=30)
    if not closed:
        # 안내 메시지를 닫았는데도 모달이 남아 있으면 Close 로 닫는다.
        # 남겨 두면 이후 모든 클릭이 삼켜진다(운영 지침: 팝업 방치 금지).
        close_import(ui, dlg)
        closed = _wait_dialog_gone(ui, dlg, timeout=10)
    return {"path": source, "options": applied, "message": message,
            "seconds": seconds, "closed": closed}


def _wait_dialog_gone(ui, dlg, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if not any(w.hwnd == dlg.hwnd for w in ui.windows()):
            return True
        time.sleep(0.5)
    return False


def close_import(ui, dlg):
    """Import 모달을 Close(1102) 로 닫는다."""
    btn = next((c for c in children(dlg.hwnd, 5)
                if c.ctrl_id == IMPORT_DIALOG["close"]), None)
    if btn is None:
        return False
    ui.click(btn, settle=1.5)
    return _wait_dialog_gone(ui, dlg, timeout=15)
