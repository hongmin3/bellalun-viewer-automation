# -*- coding: utf-8 -*-
"""Bellalun Viewer-integrated image processing automation.

The compatibility TCs must enter XIPL/PureImpact from the Viewer.  This
module intentionally never starts XIPL.STUDIO directly.
"""

from __future__ import annotations

import os
import re
import shutil
import time
import ctypes
import ctypes.wintypes as wintypes
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageGrab, ImageOps

from . import flows
from .ui import ViewerUi, children


PROC = 1151
XIPL_TOOL = 1160
POST_RECON = 1178
EXPAND_TOOLS = 1163
PARAM_COMBO = 2040
REFRESH = 2056
PREVIEW = 2054
APPLY = 2055
CANCEL = 1102
VIEW_RANGE_MONTH = 1108

TESSERACT_EXE = os.environ.get(
    "BELLALUN_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

SLIDER_NAMES_2D = {
    2057: "Contrast",
    2058: "Sharpness",
    2059: "Brightness",
    2060: "Tone type",
    2061: "Noise reduction",
}

SLIDER_NAMES_3D = {
    2043: "Recon.Contrast",
    2044: "Recon.Sharpness",
    2045: "Recon.Brightness",
    2046: "Recon.Tone type",
    2049: "Syn.Contrast",
    2050: "Syn.Sharpness",
    2051: "Syn.Brightness",
    2052: "Syn.Tone type",
}

TC01_OVERLAY_FIELDS = {
    113: ("Histogram", 5),
    134: ("Window Level (W1/W2)", 6),
}


def capture(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    rect = wintypes.RECT()
    if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom),
                       all_screens=True).save(path)
    else:
        ImageGrab.grab(all_screens=True).save(path)
    return path


def capture_viewer_window(ui, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    win = ui.main_window()
    if not win:
        raise RuntimeError("Viewer window is not available")
    ImageGrab.grab(bbox=win.rect, all_screens=True).save(path)
    return path


def read_viewer_w1_w2(image_path):
    """OCR the selected left 2D pane's W1/W2 overlay."""
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for Viewer overlay OCR") from exc
    if os.path.exists(TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    image = Image.open(image_path).convert("RGB")
    w, h = image.size
    # In the standard 1x2 Viewer layout the selected 2D pane occupies the
    # left 38% of the window. Its Histogram/W1/W2 overlay is upper-right.
    crop = image.crop((int(w * .25), int(h * .22),
                       int(w * .38), int(h * .42)))
    crop = crop.resize((crop.width * 5, crop.height * 5),
                       Image.Resampling.LANCZOS)
    text = pytesseract.image_to_string(
        crop,
        config="--psm 6 -c tessedit_char_whitelist=Ww0123456789: ")
    pairs = re.findall(
        r"W[1lI]\s*[:;]?\s*(\d+?)\s*W2\s*[:;]?\s*(\d+)", text, re.I)
    if not pairs:
        # Layout/DPI fallback: scan the whole Viewer window.  Duplicate pairs
        # are accepted only when every visible pane reports the same values.
        full = image.resize((image.width * 2, image.height * 2),
                            Image.Resampling.LANCZOS)
        fallback = pytesseract.image_to_string(
            full, config="--psm 11 -c tessedit_char_whitelist=Ww0123456789: ")
        text = text + "\n" + fallback
        pairs = re.findall(
            r"W[1lI]\s*[:;]?\s*(\d+?)\s*W2\s*[:;]?\s*(\d+)", text, re.I)
    if not pairs:
        raise RuntimeError(f"Viewer W1/W2 overlay OCR failed: {text!r}")
    values = {(int(w1), int(w2)) for w1, w2 in pairs}
    if len(values) != 1:
        raise RuntimeError(f"Viewer selected-pane W1/W2 is ambiguous: {values}")
    w1, w2 = values.pop()
    return {"w1": w1, "w2": w2, "ocr": text.strip()}


def find_text_boxes(image_path, wanted, scale=2):
    """OCR word boxes matching *wanted* (exact, case-insensitive) in
    original-image-relative pixels.

    Used to locate dynamically-named controls (added Preset aliases, files
    in a combo dropdown) that Bellalun's custom controls do not expose as
    real window text, so control-ID based lookups cannot find them.
    """
    import pytesseract
    if os.path.exists(TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    image = Image.open(image_path).convert("RGB")
    scaled = image.resize((image.width * scale, image.height * scale),
                          Image.Resampling.LANCZOS) if scale != 1 else image
    data = pytesseract.image_to_data(scaled, output_type=pytesseract.Output.DICT)
    target = wanted.strip().upper()

    def _collect(predicate):
        found = []
        for i, word in enumerate(data["text"]):
            text = word.strip().upper()
            if not text or not predicate(text):
                continue
            found.append((data["left"][i] / scale, data["top"][i] / scale,
                          data["width"][i] / scale, data["height"][i] / scale,
                          float(data["conf"][i]), text))
        return found

    exact = _collect(lambda text: text == target)
    if exact:
        return [b[:5] for b in exact]

    # 잘려 표시된 이름 보정. 콤보/목록 셀은 폭이 좁으면 뒤를 잘라 보여주므로
    # (예: 'TEST_QC_2D_M.pim' -> 'TEST_QC_2D_M....') 완전 일치만 허용하면 실제로
    # 화면에 있는 항목을 못 찾는다. 2026-08-18에 시험 파라미터 이름이 `_M`
    # 규칙으로 길어지면서 TC_05에서 실제로 발생했다.
    #
    # 다만 느슨하게 풀면 엉뚱한 항목을 누를 수 있다(TEST_2D_A_M.pim 과
    # TEST_2D_B_M.pim 처럼 접두사가 겹치는 이름이 있다). 그래서 (1) 잘림으로
    # 설명되는 접두사만 허용하고, (2) 서로 다른 문자열이 둘 이상 걸리면
    # **모호하므로 아무것도 반환하지 않는다.**
    def _looks_truncated(text):
        head = text.rstrip(".")
        return len(head) >= 6 and target.startswith(head) and head != target

    # 후보가 **정확히 하나**일 때만 받아들인다. 서로 다른 이름이 같은 문자열로
    # 잘리는 경우가 있어(예: PRESET_FLOW_A / PRESET_FLOW_B 가 둘 다
    # 'PRESET_FL...') "문자열 종류가 하나"만 확인하면 여러 행을 함께 반환해
    # 엉뚱한 행을 클릭한다.
    partial = _collect(_looks_truncated)
    if len(partial) == 1:
        return [partial[0][:5]]
    return []


def click_viewer_text(ui, wanted, settle=1.0, scale=2, evidence_path=None):
    """Screenshot the Viewer window, OCR-find *wanted*, and click its center.

    Returns True/False. Used for dynamically-named tiles/rows (e.g. a
    freshly-added Preset alias) whose position is not stable enough to
    hardcode a control ID or pixel offset for.
    """
    win = ui.main_window()
    if not win:
        return False
    tmp = evidence_path or os.path.join(
        os.environ.get("TEMP", "."), "bellalun_click_text_probe.png")
    capture_viewer_window(ui, tmp)
    boxes = find_text_boxes(tmp, wanted, scale=scale)
    if not boxes:
        return False
    x, y, w, h, _ = max(boxes, key=lambda b: b[4])
    ui.click((win.rect[0] + x + w / 2, win.rect[1] + y + h / 2), settle=settle)
    return True


# --- 시험용 XIPL 파라미터 파일 -------------------------------------------
#
# 파일명 규칙 (2026-08-18 사용자 확정): **모든 `.pim`은 `_M`으로 끝나야 한다.**
# 제품이 설치하는 기본 파라미터가 전부 그 형태다(`Standard_Default_M.pim`,
# `Spot_Default_M.pim` ...). `.xtp`/`.eap`에는 이 규칙이 없다.
# 파일명이 코드 곳곳에 흩어져 있으면 규칙을 어기기 쉬우므로 여기서만 정의하고
# 다른 모듈은 반드시 이 상수를 참조한다.
PARAM_2D_FLOW = "TEST_2D_FLOW_M.pim"
PARAM_2D_A = "TEST_2D_A_M.pim"
PARAM_2D_B = "TEST_2D_B_M.pim"
PARAM_XIPL_SAVED = "TEST_XIPL_SAVED_M.pim"
PARAM_3D_FLOW = "TEST_3D_FLOW.xtp"
PARAM_QC_2D = "TEST_QC_2D_M.pim"
PARAM_QC_3D = "TEST_QC_3D.eap"

# (원본 기본 파라미터, 만들 시험 파일). 원본을 그대로 복사하므로 내용은
# 제품 기본값과 byte-for-byte 동일하다.
_PARAM_SOURCES = {
    PARAM_2D_FLOW: "Standard_Default_M.pim",
    PARAM_2D_A: "Standard_Default_M.pim",
    PARAM_2D_B: "Standard_Default_M.pim",
    PARAM_XIPL_SAVED: "Standard_Default_M.pim",
    PARAM_QC_2D: "Standard_Default_M.pim",
    PARAM_3D_FLOW: "DBT_Standard_Default.xtp",
    # Q.C 3D는 `.xtp`가 아니라 `.eap`이다. 확장자만 다른 게 아니라 **포맷 자체가
    # 다르다**: `.pim`/`.xtp`는 평문 XML인데(`<?xml`), `.eap`/`.egp`는 암호화
    # 바이너리다(공통 매직 `FD 3A C7 0C 51 35 FC 24`, 2026-08-18 실측).
    # 그래서 `.xtp`를 복사해 `.eap`로 이름만 바꾸면 포맷이 틀린 파일이 되고,
    # Viewer 콤보에는 이름이 뜨더라도 실제 Reconstruction 파라미터로는 무효다.
    # Service Manual도 둘을 다른 것으로 규정한다 - Q.C > Setting은
    # "Q.C. Default Image Process Parameter"(영상 처리), Q.C > Setting(3D)은
    # "Q.C Default Image Reconstruction Param"(재구성)이다. 실측으로 Q.C 3D
    # 콤보는 `.eap`만 나열한다(common_qc_processing / common_qc_raw /
    # common_standard). 그중 Q.C 처리용인 common_qc_processing.eap을 원본으로 쓴다.
    PARAM_QC_3D: "common_qc_processing.eap",
}

TEST_PARAMETER_FILES = tuple(_PARAM_SOURCES)

# 규칙을 주석으로만 두면 언젠가 깨진다. import 시점에 강제한다.
for _name in _PARAM_SOURCES:
    if _name.lower().endswith(".pim") and not _name.endswith("_M.pim"):
        raise RuntimeError(
            f"시험 파라미터 이름 규칙 위반: {_name!r} - 모든 .pim은 '_M.pim'으로 "
            f"끝나야 한다(제품 기본 파라미터가 Standard_Default_M.pim 형태).")
del _name


def _param_specs(parameter_root):
    root = os.path.abspath(parameter_root)
    guard = os.path.normcase(root)
    specs = []
    for target_name, source_name in _PARAM_SOURCES.items():
        target = os.path.join(root, target_name)
        if os.path.commonpath([guard, os.path.normcase(os.path.abspath(target))]) != guard:
            raise RuntimeError(f"Unsafe test parameter target: {target}")
        specs.append((os.path.join(root, source_name), target))
    return specs


def _require_sources(specs):
    for source, _ in specs:
        if not os.path.exists(source):
            raise FileNotFoundError(source)


def reset_parameter_copies(parameter_root=r"C:\XIPL\PARAMETER"):
    """회귀 실행용: `TEST_*` 파라미터를 **전부 지우고** 새로 만든다.

    회귀는 알려진 기준에서 시작해야 하므로, 이전 실행이 남긴 시험 파라미터는
    물론 `TEST_XIPL_SAVED_M.pim.pi`처럼 제품이 부수적으로 만든 잔재와 예전
    이름 규칙(`_M` 없는 `TEST_*.pim`)까지 이름이 `TEST_`로 시작하는 파일을
    모두 삭제한 뒤 원본에서 다시 복사한다. `TEST_`로 시작하지 않는
    사용자/제품 파라미터는 절대 건드리지 않는다.
    """
    specs = _param_specs(parameter_root)
    _require_sources(specs)
    root = os.path.abspath(parameter_root)
    removed = []
    for name in sorted(os.listdir(root)):
        if not name.upper().startswith("TEST_"):
            continue
        path = os.path.join(root, name)
        if os.path.isfile(path):
            os.remove(path)
            removed.append(name)
    for source, target in specs:
        shutil.copy2(source, target)
    return {"removed": removed, "created": [t for _, t in specs]}


def ensure_parameter_copies(parameter_root=r"C:\XIPL\PARAMETER"):
    """개별 TC 실행용: **없는 것만** 만들고 있는 것은 그대로 쓴다.

    개별 자동화는 회귀와 달리 직전 실행이 만든 파라미터를 재사용해도 되고,
    매번 지우면 사용자가 손으로 검증하던 파일까지 날아간다. 그래서 누락된
    파일만 원본에서 복사한다(파일이 아예 없어도 이 함수만으로 실행 가능).
    """
    specs = _param_specs(parameter_root)
    _require_sources(specs)
    created = []
    for source, target in specs:
        if not os.path.exists(target):
            shutil.copy2(source, target)
            created.append(target)
    return {"created": created, "reused": [t for _, t in specs
                                          if t not in created]}


# Setting > Display > Overlay의 Item 카탈로그 순서(0-based). 2026-08-18 실측:
# Patient ID, Patient Name, Birth Date, Sex/Age, Gray value, Histogram,
# Window Level (W1/W2), Window Level (WW/WL), Dose kVp, Dose mA, Dose ms, Dose mAs, ...
# TC01_OVERLAY_FIELDS의 Histogram=5 / W1W2=6과 같은 기준이다.
OVERLAY_CATALOGUE = {
    "Patient ID": 0, "Patient Name": 1, "Birth Date": 2, "Sex / Age": 3,
    "Gray value": 4, "Histogram": 5, "Window Level (W1/W2)": 6,
    "Window Level (WW/WL)": 7, "Dose kVp": 8, "Dose mA": 9, "Dose ms": 10,
    "Dose mAs": 11,
}

# 카탈로그 index -> CONFIGURATION.OVERLAY_ITEM.FieldID (추가해 보고 실측한 값).
# WF04가 "요청한 항목이 실제로 저장됐는가"를 DB로 판정할 때 쓴다.
# Setting > Display > Overlay 화면의 목록과 버튼 (2026-08-19 실측).
# 버튼은 아이콘만 있어 텍스트로 구분할 수 없다. 눌러서 DB 변화로 확인한 값이다.
OVERLAY_LIST_AVAILABLE = 2382
OVERLAY_LIST_TOP = 2380
OVERLAY_LIST_BOTTOM = 2381
OVERLAY_ADD_TOP = 2383
OVERLAY_REMOVE_TOP = 2384
OVERLAY_ADD_BOTTOM = 2385
OVERLAY_REMOVE_BOTTOM = 2386

# CONFIGURATION.OVERLAY_ITEM.Position 값 (실측).
OVERLAY_POSITION = {"top": 0, "bottom": 1}
OVERLAY_ADD_BUTTON = {"top": OVERLAY_ADD_TOP, "bottom": OVERLAY_ADD_BOTTOM}
OVERLAY_REMOVE_BUTTON = {"top": OVERLAY_REMOVE_TOP,
                         "bottom": OVERLAY_REMOVE_BOTTOM}
OVERLAY_LIST = {"top": OVERLAY_LIST_TOP, "bottom": OVERLAY_LIST_BOTTOM}

OVERLAY_FIELD_IDS = {
    "Patient ID": 1, "Patient Name": 2, "Birth Date": 15, "Sex / Age": 100,
    "Histogram": 113, "Window Level (W1/W2)": 134,
    "Dose kVp": 115, "Dose mAs": 118,
}


def _overlay_positions(db):
    """{FieldID: (Position, Order)} 를 돌려준다."""
    return {int(r["FieldID"]): (int(r["Position"]), int(r["Order"]))
            for r in db.query(
                "CONFIGURATION",
                "SELECT FieldID,Position,[Order] FROM OVERLAY_ITEM")}


def _overlay_list_rows(ui, ctrl_id):
    hits = _visible(ui, ctrl_id)
    if not hits:
        return []
    return sorted({c.hwnd: c for c in children(hits[0].hwnd, 5)
                   if c.text == "ListItem" and c.visible}.values(),
                  key=lambda c: c.rect[1])


def add_image_overlay_items(ui, db, labels, position="top"):
    """Setting > Display > Overlay 의 Top 또는 Bottom 목록에 항목을 추가한다.

    `position`은 `"top"` / `"bottom"`이다. `CONFIGURATION.OVERLAY_ITEM.Position`이
    0/1로 저장되며 이 매핑은 실측했다(`OVERLAY_POSITION` 주석 참고).

    FieldID를 미리 알 수 없는 항목(예: Dose kVp/mAs)도 다룰 수 있게, 추가 전후
    `OVERLAY_ITEM`을 비교해 **실제로 생긴 FieldID와 Position을 실측으로 돌려준다.**

    **이미 다른 위치에 있으면 먼저 그 목록에서 제거한다.** 제품은 같은 항목을 Top과
    Bottom에 동시에 두지 않으므로, 제거하지 않으면 원하는 위치로 옮겨지지 않는다.
    회귀는 DB 기준 복원으로 시작해 목록이 깨끗하지만, 단독 실행에서는 앞선 실행이
    남긴 위치가 그대로 있다.

    반환: {"before": {...}, "after": {...}, "position": str,
           "expected_position": int, "added": {FieldID: (Position, Order)},
           "requested": [...], "removed_from": [...]}
    """
    if position not in OVERLAY_POSITION:
        raise RuntimeError(f"알 수 없는 Overlay 위치: {position!r}")
    unknown = [x for x in labels if x not in OVERLAY_CATALOGUE]
    if unknown:
        raise RuntimeError(f"카탈로그에 없는 Overlay 항목: {unknown}")

    want_position = OVERLAY_POSITION[position]
    before = _overlay_positions(db)

    flows.open_setting(ui, wait=3)
    flows.open_setting_group(ui, "display", wait=2)
    flows._click_setting_control(ui, 201, "Display > Overlay", wait=2)
    if not _visible(ui, OVERLAY_LIST_AVAILABLE):
        raise RuntimeError("Display > Overlay item controls not found")

    # 이미 반대편 목록에 있는 항목을 먼저 제거한다. 제품은 같은 항목을 Top과
    # Bottom에 동시에 두지 않으므로, 제거하지 않으면 원하는 위치로 옮겨지지 않는다.
    #
    # **행 위치는 DB의 Order로 계산한다.** 목록 행에서 FieldID를 화면으로 읽을 수
    # 없다고 "위에서부터 지운다"고 하면 엉뚱한 항목을 지운다 — 2026-08-19에 실제로
    # Dose kVp(Order=6)/mAs(Order=7)를 지우려다 Patient ID(0)/Patient Name(1)을
    # 삭제했다. `OVERLAY_ITEM.Order`가 표시 순서이므로 그 값이 곧 행 인덱스다.
    #
    # **Order가 큰 것부터** 지운다. 위쪽을 먼저 지우면 아래 항목의 인덱스가 당겨져
    # 어긋난다. 중간에 DB를 확인하지는 않는다 — Setting 변경은 Update를 누를 때까지
    # DB에 반영되지 않으므로(실측), 검증은 저장 뒤에 한 번 한다.
    removed_from = []
    targets = {OVERLAY_FIELD_IDS[label] for label in labels
               if label in OVERLAY_FIELD_IDS}
    for other in [k for k in OVERLAY_POSITION if k != position]:
        other_position = OVERLAY_POSITION[other]
        stale = sorted(
            ((order, fid) for fid, (pos, order) in before.items()
             if fid in targets and pos == other_position),
            reverse=True)
        if not stale:
            continue
        rows = _overlay_list_rows(ui, OVERLAY_LIST[other])
        for order, fid in stale:
            if order >= len(rows):
                raise RuntimeError(
                    f"Overlay {other} 목록에서 FieldID {fid}(Order {order}) 행을 "
                    f"찾지 못했습니다(보이는 행 {len(rows)}개). Order와 화면 행이 "
                    "어긋났을 수 있으므로 잘못된 행을 지우지 않도록 중단합니다.")
            ui.click(rows[order], settle=.4)
            remove = _visible(ui, OVERLAY_REMOVE_BUTTON[other])
            if not remove:
                raise RuntimeError(
                    f"Overlay {other} 제거 버튼"
                    f"({OVERLAY_REMOVE_BUTTON[other]})을 찾지 못했습니다.")
            ui.click(remove[0], settle=.6)
            if ui.dialog():
                flows.confirm_setting_dialog(ui, timeout=3)
            rows = _overlay_list_rows(ui, OVERLAY_LIST[other])
        removed_from.append(other)

    for label in labels:
        index = OVERLAY_CATALOGUE[label]
        rows = _overlay_list_rows(ui, OVERLAY_LIST_AVAILABLE)
        if len(rows) <= index:
            raise RuntimeError(
                f"Overlay 카탈로그에서 '{label}'(index {index}) 행이 보이지 "
                f"않습니다(보이는 행 {len(rows)}개).")
        ui.click(rows[index], settle=.4)
        add = _visible(ui, OVERLAY_ADD_BUTTON[position])
        if not add:
            raise RuntimeError(
                f"Overlay {position} 추가 버튼"
                f"({OVERLAY_ADD_BUTTON[position]})을 찾지 못했습니다.")
        ui.click(add[0], settle=.8)
        if ui.dialog():
            # 이미 추가된 항목이면 제품이 경고를 띄운다. 중복은 오류가 아니다.
            flows.confirm_setting_dialog(ui, timeout=3)

    flows.setting_update(ui, wait=3)
    flows.confirm_setting_dialog(ui)
    end_at = time.time() + 8
    after = _overlay_positions(db)
    while time.time() < end_at and after == before:
        time.sleep(1)
        after = _overlay_positions(db)
    flows.confirm_setting_dialog(ui, timeout=2)

    # 저장 뒤 최종 검증. **의도하지 않은 항목이 사라졌는지** 여기서 잡는다.
    # 제거 대상이 아닌 FieldID가 없어졌다면 잘못된 행을 지운 것이므로 즉시 알린다
    # (2026-08-19에 Patient ID/Name을 잃은 적이 있다).
    lost = sorted(set(before) - set(after) - targets)
    if lost:
        raise RuntimeError(
            f"의도하지 않은 Overlay 항목이 삭제됐습니다: FieldID {lost}. "
            f"제거 대상은 {sorted(targets)} 였습니다. "
            "Setting > Display > Overlay 목록을 확인하십시오.")

    return {
        "before": before,
        "after": after,
        "position": position,
        "expected_position": want_position,
        "added": {fid: after[fid] for fid in sorted(after) if fid in targets},
        "requested": list(labels),
        "removed_from": removed_from,
        "unintended_loss": lost,
    }


def ensure_tc01_overlay(ui, db):
    """Configure Histogram and W1/W2 through Setting > Display > Overlay."""
    def saved_fields():
        rows = db.query(
            "CONFIGURATION",
            "SELECT FieldID,Position,[Order] FROM OVERLAY_ITEM "
            "WHERE FieldID IN (113,134) ORDER BY FieldID")
        return {int(row["FieldID"]): row for row in rows}

    current = saved_fields()
    missing = [field_id for field_id in TC01_OVERLAY_FIELDS
               if field_id not in current]
    if not missing:
        return current

    flows.open_setting(ui, wait=3)
    flows.open_setting_group(ui, "display", wait=2)
    flows._click_setting_control(ui, 201, "Display > Overlay", wait=2)
    available = _visible(ui, 2382)
    add_top = _visible(ui, 2383)
    if not available or not add_top:
        raise RuntimeError("Display > Overlay item controls not found")

    for field_id in missing:
        label, catalogue_index = TC01_OVERLAY_FIELDS[field_id]
        rows = sorted({c.hwnd: c for c in children(available[0].hwnd, 5)
                       if c.text == "ListItem" and c.visible}.values(),
                      key=lambda c: c.rect[1])
        if len(rows) <= catalogue_index:
            raise RuntimeError(f"Overlay catalogue item not visible: {label}")
        ui.click(rows[catalogue_index], settle=.4)
        ui.click(add_top[0], settle=.8)
        dialog = ui.dialog()
        if dialog:
            message = ui.dismiss_dialog(timeout=2)
            raise RuntimeError(f"Failed to add Overlay item {label}: {message}")

    flows.setting_update(ui, wait=3)
    # Update를 누르면 "Display - Overlay Update successfully." 결과 팝업이 뜬다.
    # 이 모달을 닫지 않으면 이후 클릭이 전부 막혀, Setting 닫기(X)도 먹지 않고
    # "화면이 안 넘어간다"는 엉뚱한 증상으로 이어진다(2026-08-18 사용자 확인).
    # 다른 Setting 저장 흐름(TC_04/05)은 모두 setting_update와
    # confirm_setting_dialog를 쌍으로 쓴다 - 여기만 빠져 있었다.
    flows.confirm_setting_dialog(ui)
    end = time.time() + 8
    actual = saved_fields()
    while time.time() < end and any(x not in actual for x in missing):
        time.sleep(1)
        actual = saved_fields()
    if any(x not in actual for x in missing):
        raise RuntimeError(f"Overlay settings were not saved: {actual}")

    # 닫기 직전에도 모달이 남아 있으면 X 클릭이 삼켜지므로 한 번 더 걷어낸다.
    flows.confirm_setting_dialog(ui, timeout=2)
    closes = [c for c in ui.by_id(4) if c.visible
              and c.rect[2] - c.rect[0] <= 60
              and c.rect[3] - c.rect[1] <= 60]
    if closes:
        ui.click(min(closes, key=lambda c: c.rect[1]), settle=2)
    return actual


# Preset tab / LCC card control IDs per acquisition mode, measured live on
# Bellalun 1.0.12 (see the OCR'd card labels in the 3D-W probe): the three
# Preset tabs expose identical card grids whose IDs differ only by a fixed
# +50 offset, and the 2D tab is the dialog's default so it needs no tab click.
VIEW_POSITION_MODES = {
    "2d": {"tab": None, "lcc": 802, "label": "2D"},
    "3d": {"tab": 2083, "lcc": 852, "label": "3D-N"},
    "3d-w": {"tab": 2084, "lcc": 902, "label": "3D-W"},
}


def add_view_position(ui, mode):
    """Register the LCC view position of *mode* through Procedure +.

    mode is a key of VIEW_POSITION_MODES: "2d", "3d" (=3D-N) or "3d-w".
    """
    spec = VIEW_POSITION_MODES.get(mode)
    if not spec:
        raise RuntimeError(
            f"Unsupported View Position mode: {mode} "
            f"(expected one of {sorted(VIEW_POSITION_MODES)})")
    before = len(flows.step_items(ui))
    add = [c for c in ui.by_id(1171) if c.visible
           and c.rect[2] - c.rect[0] >= 12 and c.rect[3] - c.rect[1] >= 12]
    if not add:
        raise RuntimeError("Procedure add button (1171) not found")
    ui.click(add[0], settle=1)
    dlg = ui.wait_dialog(timeout=6)
    if not dlg:
        raise RuntimeError("View Position dialog did not open")
    l, t, r, b = dlg.rect
    width, height = r - l, b - t
    if width < 500 or height < 450:
        raise RuntimeError(f"Unexpected View Position dialog geometry: {dlg.rect}")

    # Bellalun 1.0.12 exposes stable IDs for tabs, LCC, OK and Cancel.
    # Use those before any window-relative fallback so dialog size changes do
    # not select LMLO or miss the OK button.
    if spec["tab"] is not None:
        tabs = [c for c in ui.by_id(spec["tab"]) if c.visible
                and c.rect[2] - c.rect[0] >= 100]
        if not tabs:
            raise RuntimeError(
                f"Preset ({spec['label']}) tab ({spec['tab']}) not found")
        ui.click(tabs[0], settle=.7)

    lcc_id = spec["lcc"]
    lcc = [c for c in ui.by_id(lcc_id) if c.visible
           and c.rect[2] - c.rect[0] >= 100]
    ok = [c for c in ui.by_id(1101) if c.visible
          and c.rect[2] - c.rect[0] >= 80]
    if not lcc or not ok:
        cancel = [c for c in ui.by_id(1102) if c.visible]
        if cancel:
            ui.click(cancel[0], settle=.5)
        raise RuntimeError(
            f"LCC ({spec['label']}) card ({lcc_id}) or OK button (1101) not found")
    ui.click(lcc[0], settle=.5)
    ui.click(ok[0], settle=1)
    after = len(flows.step_items(ui))
    if after != before + 1:
        raise RuntimeError(f"Procedure step registration failed: {before}->{after}")
    return after


def fixture_is_fresh(ctx, patient_id, today=None):
    """True if patient_id already has a study dated today with InstanceType 0/1/2/3.

    The View search screen's default date range is "Today", and the fixture
    is only ever re-created (not touched) between runs.  Without this check,
    a standalone XIPL run on a later day would try to reuse an older study
    that the default search range cannot even find.
    """
    today = today or datetime.now().strftime("%Y%m%d")
    row = ctx.db.one(
        "DATA", "SELECT TOP 1 s.[Key] FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid AND s.StudyDate=@today AND EXISTS (SELECT 1 FROM INSTANCE i "
        "WHERE i.StudyKey=s.[Key] AND i.InstanceType=1) ORDER BY s.[Key] DESC",
        {"pid": patient_id, "today": today})
    if not row:
        return False
    types = {int(x["InstanceType"]) for x in ctx.db.query(
        "DATA", "SELECT InstanceType FROM INSTANCE WHERE StudyKey=@study",
        {"study": row["Key"]})}
    return {0, 1, 2, 3}.issubset(types)


def open_test_study(ctx):
    """Open the dedicated 2D+3D Viewer fixture by Patient ID.

    DATA_FLOW_MWL_01 was prepared through Procedure + with LCC and LCC(3D-N)
    and contains InstanceType 0/1/2/3.  Reusing the fixture makes repeated
    processing tests deterministic and avoids a local Procedure's unrelated
    default steps.
    """
    patient_id = ctx.cfg.get("xipl", {}).get("test_patient_id", "DATA_FLOW_MWL_01")
    row = ctx.db.one(
        "DATA", "SELECT TOP 1 s.[Key] FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid AND EXISTS (SELECT 1 FROM INSTANCE i "
        "WHERE i.StudyKey=s.[Key] AND i.InstanceType=1) ORDER BY s.[Key] DESC",
        {"pid": patient_id})
    if not row:
        raise RuntimeError(f"Viewer XIPL fixture not found: PatientID={patient_id}")
    instance_rows = ctx.db.query(
        "DATA", "SELECT [Key],InstanceType,ImageInstanceUID,SeriesKey,GroupKey "
        "FROM INSTANCE WHERE StudyKey=@study ORDER BY [Key]", {"study": row["Key"]})
    types = {int(x["InstanceType"]) for x in instance_rows}
    if not {0, 1, 2, 3}.issubset(types):
        raise RuntimeError(f"Fixture requires InstanceType 0/1/2/3; actual={sorted(types)}")

    ui, _ = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
    # Open the completed local study through View, not through MWL Examine.
    # Re-opening the MWL row would create another study with the same UID.
    patient_ready = False
    last_error = None
    for _ in range(8):
        try:
            patient_ready = flows.ensure_patient_screen(ui)
        except Exception as exc:
            last_error = exc
        if patient_ready:
            break
        time.sleep(1)
    if not patient_ready:
        raise RuntimeError(
            f"Could not enter Patient screen after login: {last_error}")
    overlay_fields = ensure_tc01_overlay(ui, ctx.db)
    if not flows.open_main_menu(ui):
        raise RuntimeError("Viewer main menu did not open")
    view = [c for c in ui.by_id(flows.MAIN_MENU["item_view"])
            if c.visible and c.rect[2] - c.rect[0] > 20]
    if not view:
        raise RuntimeError("View menu item not found")
    ui.click(view[0], settle=5)

    # Examined 창은 열리는 데 시간이 걸린다. 즉시 조회해 "없다"고 단정하지 않고
    # 상한을 두고 기다린다(이 저장소에서 반복된 결함 형태 — 조작 대상이
    # 그려지기 전에 판정하는 것).
    present = flows.wait_controls(ui, (2177, 2178, 2179), timeout=20)
    field = [c for c in ui.by_id(2177) if c.visible]
    search = [c for c in ui.by_id(2178) if c.visible]
    button = [c for c in ui.by_id(2179) if c.visible]
    if not field or not search or not button:
        raise RuntimeError(
            f"View search controls not found: {present} "
            "(2177=검색항목 / 2178=입력 / 2179=검색버튼)")
    ui.click(field[0], settle=.5)
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    items, seen = [], set()
    for c in children(popups[0].hwnd, 3):
        if c.text == "TextButton" and c.visible and c.hwnd not in seen:
            seen.add(c.hwnd); items.append(c)
    patient_id_item = [c for c in items if c.ctrl_id == 2]
    if not patient_id_item:
        raise RuntimeError("Patient ID search option not found")
    ui.click(patient_id_item[0], settle=.5)
    ui.set_text(search[0], patient_id)
    # Default search range is "Today". The reusable fixture is created once
    # and reused across days (see docstring above), so widen the range to
    # Month before searching or an older fixture returns zero rows.
    month_range = [c for c in ui.by_id(VIEW_RANGE_MONTH) if c.visible]
    if month_range:
        ui.click(month_range[0], settle=1)
    ui.click(button[0], settle=3)

    study_list = [c for c in ui.by_id(2199) if c.visible]
    rows, seen = [], set()
    for c in children(study_list[0].hwnd, 4) if study_list else []:
        if c.text == "StudyListItem" and c.visible and c.hwnd not in seen:
            seen.add(c.hwnd); rows.append(c)
    if not rows:
        raise RuntimeError(f"View search returned no rows: {patient_id}")
    # View cards are newest-first.  The completed fixture is the oldest card;
    # any newer blank duplicate is intentionally ignored.
    ui.click(sorted(rows, key=lambda c: (c.rect[1], c.rect[0]))[-1], settle=1)
    open_button = [c for c in ui.by_id(2182) if c.visible]
    if not open_button:
        raise RuntimeError("View button not found")
    ui.click(open_button[0], settle=8)
    steps = flows.step_items(ui)
    if len(steps) != 2:
        raise RuntimeError(f"Fixture must expose exactly 2 acquired steps; actual={len(steps)}")
    return {"ui": ui, "study_key": row["Key"], "patient_id": patient_id,
            "step_2d": 1, "step_3d": 2, "initial_steps": 2,
            "overlay_fields": overlay_fields, "instances": instance_rows}


def _visible(ui, ctrl_id):
    return [c for c in ui.by_id(ctrl_id) if c.visible]


def expand_tools(ui, attempts=4):
    """Tool 레일을 펼쳐 Post Recon./XIPL 버튼이 보이게 한다.

    한 번 클릭하고 결과를 확인하지 않으면, 검사를 새로 연 직후처럼 레일이 아직
    만들어지는 중일 때 클릭이 삼켜져 XIPL 버튼(1160)을 못 찾는다(2026-08-18
    실측: TC_06이 "Viewer XIPL tool (1160) not found"로 중단). 펼쳐졌는지
    확인하며 상한을 두고 재시도한다. 이미 펼쳐져 있으면 아무것도 하지 않으므로
    토글을 반대로 눌러 접을 위험은 없다.
    """
    for _ in range(attempts):
        if _visible(ui, POST_RECON) and _visible(ui, XIPL_TOOL):
            return True
        toggles = _visible(ui, EXPAND_TOOLS)
        if toggles:
            ui.click(toggles[0], settle=1)
        else:
            time.sleep(.8)
    return bool(_visible(ui, POST_RECON) and _visible(ui, XIPL_TOOL))


def select_2d(ui, index):
    flows.select_step(ui, index)
    time.sleep(1)


def select_3d_raw(ui, index):
    flows.select_step(ui, index)
    time.sleep(1)
    raw = _visible(ui, 2122)
    if raw:
        ui.click(raw[0], settle=1)


def open_process(ui):
    ui.click(_visible(ui, PROC)[0], settle=2)
    if not _visible(ui, PARAM_COMBO):
        raise RuntimeError("Viewer Image Processing window did not open")


def open_post_reconstruction(ui):
    expand_tools(ui)
    ui.click(_visible(ui, POST_RECON)[0], settle=3)
    if not _visible(ui, PARAM_COMBO) or not _visible(ui, 2043):
        raise RuntimeError("Viewer Post Reconstruction window did not open")


def _parameter_name_key(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _ocr_parameter_row(control):
    """Return OCR candidates for one visible Parameter dropdown row."""
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for Parameter selection") from exc
    if os.path.exists(TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    image = ImageGrab.grab(bbox=control.rect, all_screens=True).convert("RGB")
    gray = ImageOps.autocontrast(ImageOps.grayscale(image))
    variants = [gray]
    variants.extend(gray.point(lambda p, cut=cut: 255 if p >= cut else 0)
                    for cut in (120, 160, 200))
    out = []
    for variant in variants:
        scaled = variant.resize((variant.width * 5, variant.height * 5),
                                Image.Resampling.LANCZOS)
        text = pytesseract.image_to_string(
            scaled,
            config=("--psm 7 "
                    "-c tessedit_char_whitelist="
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"))
        text = text.strip()
        if text and text not in out:
            out.append(text)
    return out


def _parameter_popup_rows(ui, popup):
    """Only rows geometrically contained by the open ItemList popup."""
    pl, pt, pr, pb = popup.rect
    seen, rows = set(), []
    for c in children(popup.hwnd, 4):
        l, t, r, b = c.rect
        if (c.text == "TextButton" and c.visible and c.hwnd not in seen
                and l >= pl and r <= pr and t >= pt and b <= pb
                and r - l >= 80 and b - t >= 18):
            seen.add(c.hwnd)
            rows.append(c)
    return sorted(rows, key=lambda c: c.rect[1])


def _settle_parameter_panel(seconds=2.5):
    """Wait out the WPF relayout after a Parameter selection.

    Selecting a row reloads all 5 sliders at once; the last one to finish
    repainting (Noise reduction) has been observed to OCR as blank if read
    immediately after the click, even across several 1s OCR retries, while
    an unrelated later read of the same region succeeds instantly. This
    mirrors the WPF settle already required by XiplStudio.save_as() for the
    same underlying reason (see its comment) - a fixed pre-emptive sleep
    here, not just retries after failure.
    """
    time.sleep(seconds)


def select_test_parameter(ui, expected_name):
    """OCR the dropdown and click only the row matching *expected_name*.

    Additional parameter files can change both list length and ordering.  No
    row index is assumed: visible rows are read, the popup is scrolled when
    necessary, and a click occurs only for an unambiguous filename match.
    """
    ui.click(_visible(ui, REFRESH)[0], settle=1)
    expected_key = _parameter_name_key(expected_name)
    pages_seen = set()
    observations = []
    ui.click(_visible(ui, PARAM_COMBO)[0], settle=.5)
    # Stop on a repeated OCR page, not on a small fixed item count.  The high
    # ceiling only guards against a pathological custom list that never
    # reports the same page while refusing to reach its end.
    for _ in range(100):
        popups = [w for w in ui.windows() if w.text == "ItemList"]
        if not popups:
            raise RuntimeError("Parameter list did not open")
        popup = popups[0]
        rows = _parameter_popup_rows(ui, popup)
        if not rows:
            ui.key("ESC", settle=.2)
            raise RuntimeError("No Parameter rows were found inside ItemList")

        scored = []
        page_text = []
        for row in rows:
            texts = _ocr_parameter_row(row)
            page_text.extend(texts)
            for text in texts:
                key = _parameter_name_key(text)
                score = SequenceMatcher(None, expected_key, key).ratio()
                scored.append((score, key == expected_key, row, text))
        observations.append(page_text)
        exact = [x for x in scored if x[1]]
        if len({x[2].hwnd for x in exact}) == 1:
            target = exact[0][2]
            ui.click(target, settle=1)
            _settle_parameter_panel()
            return ui.combo_value(_visible(ui, PARAM_COMBO)[0]) or expected_name

        # OCR may confuse one character (e.g. D/0). Accept only one strong
        # candidate with a clear margin over every other row.
        ranked = sorted(scored, key=lambda x: x[0], reverse=True)
        if ranked and ranked[0][0] >= .88:
            runner_up = next((x for x in ranked[1:]
                              if x[2].hwnd != ranked[0][2].hwnd), None)
            if not runner_up or ranked[0][0] - runner_up[0] >= .08:
                ui.click(ranked[0][2], settle=1)
                _settle_parameter_panel()
                return ui.combo_value(_visible(ui, PARAM_COMBO)[0]) or expected_name

        signature = tuple(sorted(_parameter_name_key(x) for x in page_text))
        if signature in pages_seen:
            ui.key("ESC", settle=.2)
            break
        pages_seen.add(signature)
        # Keep the list open while scrolling; clicking the combo again at the
        # top of the next loop would close it, so scroll now and OCR directly.
        ui.wheel(((popup.rect[0] + popup.rect[2]) // 2,
                  (popup.rect[1] + popup.rect[3]) // 2), -5, settle=.7)
    raise RuntimeError(
        f"Parameter {expected_name!r} was not recognized in the dropdown; "
        f"OCR pages={observations}")


def increment_slider(ui, slider_id):
    slider = _visible(ui, slider_id)[0]
    plus = [c for c in children(slider.hwnd, 2) if c.ctrl_id == 2 and c.visible]
    if not plus:
        raise RuntimeError(f"Slider {slider_id} + button not found")
    ui.click(plus[0], settle=1)


def shift_slider(ui, slider_id, direction, clicks=8):
    """Move a parameter strongly using only its bounded +/- UI buttons."""
    slider = _visible(ui, slider_id)[0]
    button_id = 2 if direction == "+" else 1
    buttons = [c for c in children(slider.hwnd, 2)
               if c.ctrl_id == button_id and c.visible]
    if not buttons:
        raise RuntimeError(f"Slider {slider_id} {direction} button not found")
    for _ in range(clicks):
        ui.click(buttons[0], settle=.12)


def _slider_value_bbox(slider):
    """Locate the custom-drawn numeric value area from +/- geometry."""
    buttons = {c.ctrl_id: c for c in children(slider.hwnd, 2)
               if c.ctrl_id in (1, 2) and c.visible}
    if 1 not in buttons or 2 not in buttons:
        raise RuntimeError(f"Slider {slider.ctrl_id} +/- buttons not found")
    l, t, r, b = slider.rect
    minus, plus = buttons[1], buttons[2]
    left_gap = minus.rect[0] - l
    right_gap = r - plus.rect[2]
    if left_gap >= right_gap and left_gap >= 12:
        return (l, t, minus.rect[0], b)
    if right_gap >= 12:
        return (plus.rect[2], t, r, b)
    raise RuntimeError(
        f"Slider {slider.ctrl_id} numeric value area not found: rect={slider.rect}")


def _ocr_integer(image):
    """OCR a slider's numeric value robustly across Tesseract page modes.

    No single --psm mode reads every value correctly, and the two failure
    modes pull in opposite directions (verified live on the 2D sliders):
      * psm 7 (single text line) silently DROPS an isolated single digit -
        it returns '' for a legible "8" - but reads "10"/"20" fine.
      * psm 8 (single word) reads "8" fine but sometimes DOUBLES a trailing
        digit, turning "10" into "100".
    So instead of trusting one mode, every mode that yields exactly one
    in-range integer casts a vote over both a grayscale and a thresholded
    variant, and the majority value wins.  psm 6 is tried first so it also
    breaks ties (empirically it read all five sliders correctly on its own).
    """
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for XIPL value verification") from exc
    if os.path.exists(TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    elif not shutil.which("tesseract"):
        raise RuntimeError(f"Tesseract executable not found: {TESSERACT_EXE}")

    gray = ImageOps.autocontrast(ImageOps.grayscale(image))
    gray = gray.resize((max(1, gray.width * 6), max(1, gray.height * 6)),
                       Image.Resampling.LANCZOS)
    variants = (gray, gray.point(lambda p: 0 if p < 190 else 255))
    votes = Counter()
    texts = []
    for candidate in variants:
        for psm in (6, 7, 8):
            text = pytesseract.image_to_string(
                candidate,
                config=f"--psm {psm} -c tessedit_char_whitelist=0123456789").strip()
            texts.append(f"psm{psm}:{text}")
            hits = re.findall(r"\d+", text)
            if len(hits) == 1 and 0 <= int(hits[0]) <= 100:
                votes[int(hits[0])] += 1
    if votes:
        return votes.most_common(1)[0][0]
    raise RuntimeError(f"Slider value OCR failed: {texts}")


def read_slider_value(ui, slider_id, attempts=3, delay=0.6):
    """Read a slider's numeric value, trying every control matching slider_id.

    Bellalun's custom controls have shown duplicate/hidden hwnd instances for
    the same ctrl_id elsewhere in this codebase, so all visible candidates
    are tried, not just the first.  Each candidate is re-grabbed and re-OCR'd
    a few times as a guard against a mid-repaint frame; _ocr_integer itself
    votes across page-segmentation modes, so a correctly rendered value is
    read on the very first grab (this replaced an earlier, misdiagnosed
    "fresh subprocess" workaround - the real defect was psm choice, not
    process identity).
    """
    candidates = _visible(ui, slider_id)
    if not candidates:
        raise RuntimeError(f"Slider {slider_id} is not visible")
    errors = []
    for candidate in candidates:
        bbox = _slider_value_bbox(candidate)
        for attempt in range(attempts):
            try:
                image = ImageGrab.grab(bbox=bbox, all_screens=True)
                return _ocr_integer(image)
            except Exception as exc:
                errors.append(str(exc))
            if attempt < attempts - 1:
                time.sleep(delay)
    raise RuntimeError(
        f"Slider {slider_id} OCR failed for all {len(candidates)} visible "
        f"instance(s): {errors}")


def _pink_count(control):
    # Capture the absolute bbox directly. Cropping an all-screens composite is
    # wrong on multi-monitor desktops whose virtual origin is not (0, 0).
    crop = ImageGrab.grab(bbox=control.rect, all_screens=True).convert("RGB")
    return sum(1 for red, green, blue in crop.getdata()
               if red >= 175 and green <= 150 and blue <= 190
               and red >= green + 45)


def read_radio_choice(ui, use_id, not_use_id):
    use = _visible(ui, use_id)
    not_use = _visible(ui, not_use_id)
    if not use or not not_use:
        raise RuntimeError(f"Radio controls are not visible: {use_id}/{not_use_id}")
    counts = {"Use": _pink_count(use[0]),
              "Not use": _pink_count(not_use[0])}
    if counts["Use"] == counts["Not use"]:
        raise RuntimeError(f"Radio selection could not be distinguished: {counts}")
    return max(counts, key=counts.get)


def read_2d_parameter_state(ui):
    """Read every 2D value rendered in the Image Processing window."""
    return {name: read_slider_value(ui, slider_id)
            for slider_id, name in SLIDER_NAMES_2D.items()}


def read_3d_parameter_state(ui):
    """Read Background Masking plus every Recon/Syn numeric value."""
    state = {
        "Recon.Background Masking": read_radio_choice(ui, 2041, 2042),
        "Syn.Background Masking": read_radio_choice(ui, 2047, 2048),
    }
    state.update({name: read_slider_value(ui, slider_id)
                  for slider_id, name in SLIDER_NAMES_3D.items()})
    return state


def change_all_2d_parameters(ui):
    """Give every 2D parameter a conspicuous, non-default value."""
    changes = [(2057, "+", 8),   # Contrast
               (2058, "-", 8),   # Sharpness
               (2059, "+", 8),   # Brightness
               (2060, "-", 10),  # Tone type
               (2061, "+", 8)]   # Noise reduction
    for slider_id, direction, clicks in changes:
        shift_slider(ui, slider_id, direction, clicks)
    return changes


def change_all_3d_parameters(ui):
    """Change Background Masking and every Recon/Syn parameter strongly."""
    # Flip Background Masking to Not use for both output types.
    ui.click(_visible(ui, 2042)[0], settle=.4)
    ui.click(_visible(ui, 2048)[0], settle=.4)
    changes = [
        (2043, "+", 8), (2044, "-", 8),
        (2045, "+", 8), (2046, "-", 10),
        (2049, "-", 8), (2050, "+", 8),
        (2051, "-", 8), (2052, "-", 10),
    ]
    for slider_id, direction, clicks in changes:
        shift_slider(ui, slider_id, direction, clicks)
    return changes


def preview_and_apply(ui, preview_wait, apply_wait):
    ui.click(_visible(ui, PREVIEW)[0], settle=1)
    time.sleep(preview_wait)
    if not _visible(ui, APPLY):
        raise RuntimeError("Apply button unavailable after Preview")
    ui.click(_visible(ui, APPLY)[0], settle=1)
    time.sleep(apply_wait)
    return not _visible(ui, APPLY)


def cancel_window(ui):
    hits = _visible(ui, CANCEL)
    if hits:
        ui.click(hits[0], settle=1)
