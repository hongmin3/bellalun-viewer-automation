# -*- coding: utf-8 -*-
"""Bellalun DICOM Print Overlay configuration helpers.

The catalogue is custom-drawn, so Win32 exposes each row as ``ListItem``
without its label.  Selection therefore uses the stable list/control IDs and
verifies the row text with OCR before clicking it.
"""

from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

from PIL import ImageGrab, ImageOps

from . import flows
from .ui import children


OVERLAY_NAME = "TC_WF03_OVERLAY"

# Catalogue indexes observed in Bellalun 1.0.12.105.  OCR verification below
# deliberately fails closed if another build changes the order.
# Setting > DICOM > Print Overlay 의 세 영역 (2026-08-19 실측).
#
# 사양 근거: 사양서1 305쪽 SRS 04-20-10 "Overlay로 표시할 항목 설정
# (Header / Top / Bottom)".
#
# **Position 이 화면 순서와 다르다.** 화면은 위에서 Header / Top / Bottom 순인데
# `PRINT_OVERLAY_ITEM.Position` 은 각각 2 / 0 / 1 이다. Top=0, Bottom=1 은 Image
# Overlay(`OVERLAY_ITEM.Position`)와 같고 Header 가 나중에 2 를 받은 것으로 보인다.
# 추측하면 틀리는 부분이라 **항목을 넣어 보고 DB 로 확인**했고, 목록 라벨은 화면
# 캡처로 눈으로 확인했다.
PRINT_AREAS = ("header", "top", "bottom")
PRINT_AREA_POSITION = {"header": 2, "top": 0, "bottom": 1}
PRINT_AREA_LIST = {"header": 2486, "top": 2487, "bottom": 2488}
PRINT_AREA_ADD = {"header": 2501, "top": 2503, "bottom": 2505}
PRINT_AREA_REMOVE = {"header": 2502, "top": 2504, "bottom": 2506}

# 영역별 항목. 카탈로그 index 는 Bellalun 1.0.12.105 실측이며, 아래 OCR 검증이
# 다른 빌드에서 순서가 바뀌면 **통과하지 않고 실패**하도록 되어 있다.
#
# 개정본 `WF_03` Expected Result 의 시스템정보(compression / HVL / AGD / Thickness)와
# 환자정보(ID / birthdate)가 이 6개다. 세 영역에 나눠 두어 **Top 이외의 영역도 실제로
# 저장되는지** 검증한다(사용자 요청).
PRINT_ITEMS_BY_AREA = {
    "header": (("Patient ID", 0), ("Birth Date", 2)),
    "top": (("Thickness", 34), ("Compression Force", 35)),
    "bottom": (("HVL", 36), ("AGD", 37)),
}

# 영역 구분 없이 전체를 훑을 때 쓴다(개수·라벨 목록).
PRINT_ITEMS = tuple(item for area in PRINT_AREAS
                    for item in PRINT_ITEMS_BY_AREA[area])

# 라벨 -> FieldID (실측). 저장 결과를 영역별로 대조할 때 쓴다.
PRINT_FIELD_IDS = {
    "Patient ID": 1,
    "Birth Date": 15,
    "Thickness": 130,
    "Compression Force": 131,
    "HVL": 132,
    "AGD": 133,
}

# 기대하는 영역별 FieldID 집합.
PRINT_EXPECTED_BY_POSITION = {
    PRINT_AREA_POSITION[area]: {PRINT_FIELD_IDS[label]
                               for label, _ in PRINT_ITEMS_BY_AREA[area]}
    for area in PRINT_AREAS
}


# Header 표시 위치와 Layout (Setting > DICOM > Print Overlay 우측 Option).
#
# 사양서1 297쪽: "Header가 표시될 수 있는 위치는 다음과 같다. None으로 설정한 경우
# 표시되지 않는다. None, Top, Bottom" / "Header Layout은 1x1에서 3x3까지 선택할 수
# 있다. **Layout 한 칸당 한 항목씩 표시한다.**"
#
# 값 매핑은 실측이다(선택해 보고 DB 확인). 콤보 팝업의 **항목 순서와 DB 값이
# 일치하지 않으므로**(index 1 을 눌렀더니 Bottom 이 됐다) 순서로 고르지 않고 항목을
# OCR 로 읽어 고른다.
HEADER_POSITION_CONTROL = 2497
HEADER_LAYOUT_CONTROL = 2498
HEADER_POSITION_VALUES = {"none": 0, "top": 1, "bottom": 2}
HEADER_LAYOUT_LABELS = ("1 X 1", "1 X 2", "1 X 3",
                        "2 X 1", "2 X 2", "2 X 3",
                        "3 X 1", "3 X 2", "3 X 3")
HEADER_LAYOUT_CELLS = {label: int(label[0]) * int(label[-1])
                       for label in HEADER_LAYOUT_LABELS}

# Header 를 어디에 둘지. Top 은 필름 상단이다.
HEADER_POSITION = "top"


def required_header_layout(item_count):
    """항목 수를 담을 수 있는 **가장 작은** Layout 을 고른다.

    사양서1 297쪽 "Layout 한 칸당 한 항목씩 표시한다" 가 근거다. 칸이 항목보다
    적으면 넘치는 항목이 표시되지 않는다.
    """
    for label in HEADER_LAYOUT_LABELS:
        if HEADER_LAYOUT_CELLS[label] >= item_count:
            return label
    raise RuntimeError(
        f"Header 항목 {item_count}개는 3x3(9칸)으로도 담을 수 없습니다.")


# ---------------------------------------------------------------------------
# 필름/프린트 프리뷰에서 각 영역이 차지하는 자리.
#
# 사양서1 **296쪽**: "Logo 영역의 높이는 전체 필름 높이의 3%, Header 영역은
# (전체 필름 높이의 3% x 선택한 Header Layout의 행수)이다."
# 그래서 Header 밴드 높이를 상수로 박지 않고 **행수에서 계산**한다.
#
# Top / Bottom 의 위치와 OCR 확대 배율은 2026-08-19 실측이다(필름 723x904, Print
# 서버 웹 프리뷰 1280x1600 양쪽에서 같은 비율로 읽힌다).
#   Header  y 0.009-0.025  전체 폭, 값만
#   Top     y 0.095-0.116  우측, 값만      -> Header 높이 + 0.05~0.10H
#   Bottom  y 0.959-0.981  우측, 라벨: 값
# Top 은 **Header 높이에 얹어** 잡는다. Header 표시를 끄면 아래 항목이 그만큼
# 올라오므로 고정 비율로 잡으면 엉뚱한 곳을 읽는다.
FILM_HEADER_ROW_RATIO = 0.03


def header_rows(layout_label=None):
    """Header Layout 라벨(`1 X 2`)의 행수. 없으면 현재 설정에서 계산한다."""
    label = layout_label or required_header_layout(
        len(PRINT_ITEMS_BY_AREA["header"]))
    return int(label[0])


# 한 배율로만 읽으면 판정이 흔들린다. 필름 Header 를 8배로 확대하면 `MWL` 이
# `MIWL` / `MIAL` 로 읽히고 12배에서는 제대로 읽힌다(2026-08-19 실측). 그래서 여러
# 배율로 읽고 **하나라도 기대값과 일치하면** 통과로 본다. 기대값이 DB 에서 온 값
# 이므로 느슨해지지 않는다 — 다른 환자의 필름은 어느 배율에서도 일치하지 않는다.
# 아래 세 배율이면 필름(723x904)과 Print 서버 웹 프리뷰(1280x1600) 양쪽에서 6개
# 항목이 모두 읽힌다.
FILM_OCR_SCALES = (12, 8, 5)


def film_regions(width, height, layout_label=None):
    """영역별 crop box.

    Top 값은 필름에서 7px 정도로 작게 렌더링되므로 호출부가 `FILM_OCR_SCALES`
    로 확대해 읽는다.
    """
    band = int(height * FILM_HEADER_ROW_RATIO * header_rows(layout_label))
    return {
        # 사양 공식 그대로. 여유를 주면 Film 창의 빨간 선택 테두리가 들어와
        # OCR 잡음이 된다.
        "header": (0, 0, width, band),
        # Header 높이에 얹는다. Header 표시를 끄면 아래 항목이 그만큼 올라온다.
        "top": (int(width * .80), band + int(height * .05),
                width, band + int(height * .10)),
        "bottom": (int(width * .5), int(height * .93), width, height),
    }


def items_by_position(items):
    """저장된 항목을 {Position: {FieldID, ...}} 로 모은다."""
    grouped = {}
    for row in items:
        grouped.setdefault(int(row["Position"]), set()).add(int(row["FieldID"]))
    return grouped


def matches_expected_areas(items):
    """저장된 항목이 기대하는 영역 배치와 정확히 일치하는지."""
    return items_by_position(items) == PRINT_EXPECTED_BY_POSITION


def _visible(ui, control_id):
    return [c for c in ui.by_id(control_id) if c.visible]


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _ocr(control, tesseract_exe):
    import pytesseract

    if tesseract_exe:
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    image = ImageGrab.grab(bbox=control.rect, all_screens=True).convert("L")
    image = ImageOps.autocontrast(image).resize((image.width * 3, image.height * 3))
    return pytesseract.image_to_string(image, config="--psm 7", lang="eng").strip()


def _catalogue_row(ui, list_id, index, expected, tesseract_exe):
    lists = _visible(ui, list_id)
    if not lists:
        raise RuntimeError(f"Print Overlay catalogue control {list_id} not found")
    catalogue = lists[0]
    nested = children(catalogue.hwnd, 5)
    scrolls = [c for c in nested if c.text == "Scroll" and c.visible]
    if not scrolls:
        raise RuntimeError("Print Overlay catalogue scroll control not found")
    arrows = children(scrolls[0].hwnd, 2)
    up = [c for c in arrows if c.ctrl_id == 1 and c.visible]
    down = [c for c in arrows if c.ctrl_id == 2 and c.visible]
    if not up or not down:
        raise RuntimeError("Print Overlay catalogue scroll arrows not found")

    # Always return to a known origin.  A no-op click at the limit is safe.
    for _ in range(50):
        ui.click(up[0], settle=.015)

    rows = sorted({c.hwnd: c for c in children(catalogue.hwnd, 5)
                   if c.text == "ListItem" and c.visible}.values(),
                  key=lambda c: c.rect[1])
    if not rows:
        raise RuntimeError("Print Overlay catalogue has no visible rows")
    # Bellalun's custom scrollbar does not move exactly one row per arrow
    # click.  For lower catalogue entries, jump to the bottom through the
    # scroll track and identify the intended visible row by OCR.
    if index >= len(rows):
        l, t, r, b = catalogue.rect
        for _ in range(12):
            ui.click((r - 8, b - 25), settle=.08)
    rows = sorted({c.hwnd: c for c in children(catalogue.hwnd, 5)
                   if c.text == "ListItem" and c.visible}.values(),
                  key=lambda c: c.rect[1])
    candidates = []
    for row in rows:
        observed = _ocr(row, tesseract_exe)
        score = SequenceMatcher(None, _norm(expected), _norm(observed)).ratio()
        if _norm(expected) and _norm(expected) in _norm(observed):
            score = 1.0
        # At the native 35px row height Tesseract consistently reads the
        # leading H in HVL as A.  Keep this narrow and explicit; do not relax
        # the threshold for other catalogue labels.
        if _norm(expected) == "hvl" and _norm(observed).startswith("avl"):
            score = 1.0
        candidates.append((score, row, observed))
    score, row, observed = max(candidates, key=lambda item: item[0])
    if score < .72:
        raise RuntimeError(
            f"Print Overlay item not found: expected={expected!r}, "
            f"best OCR={observed!r}, score={score:.3f}")
    return row, observed


def _saved(db, name=OVERLAY_NAME):
    overlay = db.one(
        "CONFIGURATION", "SELECT * FROM PRINT_OVERLAY WHERE Name=@name",
        {"name": name})
    if not overlay:
        return None
    items = db.query(
        "CONFIGURATION", "SELECT PrintOverlayKey,Position,FieldID,[Order] "
        "FROM PRINT_OVERLAY_ITEM WHERE PrintOverlayKey=@key "
        "ORDER BY Position,[Order]", {"key": overlay["Key"]})
    return {"overlay": overlay, "items": items}


def _pick_combo_by_text(ui, control_id, wanted, tesseract_exe, what):
    """콤보를 열어 **OCR 로 읽은 항목 문구**가 맞는 것을 고른다.

    팝업 항목 순서에 의존하지 않는다. 원하는 문구를 못 찾으면 아무것도 누르지 않고
    읽은 값을 붙여 실패시킨다 — 엉뚱한 항목을 고르면 설정이 조용히 틀어진다.
    """
    hits = _visible(ui, control_id)
    if not hits:
        raise RuntimeError(f"{what} 콤보({control_id})를 찾지 못했습니다"
                           "(비활성일 수 있습니다).")
    ui.click(hits[0], settle=1.0)
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    if not popups:
        raise RuntimeError(f"{what} 콤보({control_id}) 목록이 열리지 않았습니다.")
    items = sorted({c.hwnd: c for c in children(popups[0].hwnd, 4)
                    if c.visible and c.text == "TextButton"}.values(),
                   key=lambda c: c.rect[1])
    seen = []
    target = None
    for item in items:
        text = _norm(_ocr(item, tesseract_exe))
        seen.append(text)
        if text == _norm(wanted):
            target = item
            break
    if target is None:
        raise RuntimeError(
            f"{what} 콤보에서 {wanted!r} 항목을 찾지 못했습니다. "
            f"읽은 항목={seen}. 잘못된 항목을 고르지 않도록 중단합니다.")
    ui.click(target, settle=1.0)
    return {"wanted": wanted, "items_read": seen}


def header_targets(item_count, position=HEADER_POSITION):
    """기대하는 `(HeaderPosition, HeaderLayout, layout_label)`."""
    if position not in HEADER_POSITION_VALUES:
        raise RuntimeError(f"알 수 없는 Header 표시 위치: {position!r}")
    layout_label = required_header_layout(item_count)
    return (HEADER_POSITION_VALUES[position],
            HEADER_LAYOUT_LABELS.index(layout_label), layout_label)


def header_matches(overlay, item_count, position=HEADER_POSITION):
    """저장된 Overlay 행의 Header 설정이 기대와 맞는지."""
    want_position, want_layout, _ = header_targets(item_count, position)
    return (int((overlay or {}).get("HeaderPosition", -1)) == want_position
            and int((overlay or {}).get("HeaderLayout", -1)) == want_layout)


def ensure_header_layout(ui, db, item_count, position=HEADER_POSITION,
                         name=OVERLAY_NAME, tesseract_exe=None, save=True):
    """Header 표시 위치와 Layout 을 설정한다.

    표시 위치가 `None` 이면 Header 항목을 아무리 넣어도 **필름에 나오지 않는다**
    (사양서1 297쪽). Layout 은 항목 수를 담을 수 있는 가장 작은 것을 고른다
    (같은 쪽, "Layout 한 칸당 한 항목씩 표시한다").

    `save=True` 면 Update 까지 하고 **DB 값으로 확인**한다(기존 Overlay 수정).
    `save=False` 면 콤보만 고른다 — 신규 생성 경로에서는 Overlay 행이 아직 없어
    DB 로 확인할 수 없으므로, 저장과 확인을 호출부가 한 번에 한다.

    반환: {"position", "layout", "before", "after", "picked", "changed", "saved"}
    """
    want_position, want_layout, layout_label = header_targets(item_count, position)

    def current():
        return db.one(
            "CONFIGURATION",
            "SELECT HeaderPosition,HeaderLayout FROM PRINT_OVERLAY "
            "WHERE Name=@name", {"name": name}) or {}

    before = current() if save else {}
    if save and header_matches(before, item_count, position):
        return {"position": position, "layout": layout_label,
                "before": before, "after": before, "picked": None,
                "changed": False, "saved": True}

    picked = {}
    picked["position"] = _pick_combo_by_text(
        ui, HEADER_POSITION_CONTROL, position.title(), tesseract_exe,
        "Header 표시 위치")
    # 표시 위치가 None 이 아니어야 Layout 콤보가 활성화된다(실측).
    picked["layout"] = _pick_combo_by_text(
        ui, HEADER_LAYOUT_CONTROL, layout_label, tesseract_exe, "Header Layout")

    if not save:
        return {"position": position, "layout": layout_label,
                "before": before, "after": None, "picked": picked,
                "changed": True, "saved": False}

    flows.setting_update(ui, wait=3)
    if ui.dialog():
        ui.dismiss_dialog(timeout=2)
    end = time.time() + 10
    after = current()
    while time.time() < end and not header_matches(after, item_count, position):
        time.sleep(1)
        after = current()
    if not header_matches(after, item_count, position):
        raise RuntimeError(
            f"Header 설정이 반영되지 않았습니다. "
            f"기대 HeaderPosition={want_position}({position}) / "
            f"HeaderLayout={want_layout}({layout_label}), 실제={after}, "
            f"읽은 항목={picked}")
    return {"position": position, "layout": layout_label,
            "before": before, "after": after, "picked": picked,
            "changed": True, "saved": True}


def ensure_print_overlay(ui, db, tesseract_exe, name=OVERLAY_NAME):
    """Create the six-item TC overlay through Setting > DICOM > Print Overlay."""
    header_count = len(PRINT_ITEMS_BY_AREA["header"])

    current = _saved(db, name)
    # 개수만 보면 안 된다. 같은 6개가 전부 Top 에 있어도 통과해 버려서, 영역별로
    # 나눠 넣는 이번 요구사항을 검증하지 못한다. **영역 배치까지 일치**해야 재사용한다.
    #
    # Header 표시 설정도 함께 본다. 표시 위치가 None 이면 Header 항목이 저장돼 있어도
    # 필름에 나오지 않는다(사양서1 297쪽).
    if current and matches_expected_areas(current["items"]):
        if header_matches(current["overlay"], header_count):
            return current
        # 항목은 맞고 Header 표시 설정만 다르면 그것만 고친다.
        flows.open_dicom_setting(ui, "print_overlay", wait=3)
        rows = sorted({c.hwnd: c for c in children(_visible(ui, 2485)[0].hwnd, 4)
                       if c.text == "ListItem" and c.visible}.values(),
                      key=lambda c: c.rect[1])
        if not rows:
            raise RuntimeError(f"Saved Print Overlay is not selectable: {name}")
        ui.click(rows[0], settle=.8)
        header = ensure_header_layout(ui, db, header_count, name=name,
                                      tesseract_exe=tesseract_exe)
        refreshed = _saved(db, name)
        refreshed["header"] = header
        refreshed["by_position"] = {pos: sorted(fids) for pos, fids
                                    in items_by_position(refreshed["items"]).items()}
        refreshed["areas"] = {area: sorted(PRINT_FIELD_IDS[label]
                                          for label, _ in PRINT_ITEMS_BY_AREA[area])
                              for area in PRINT_AREAS}
        return refreshed

    flows.open_dicom_setting(ui, "print_overlay", wait=3)
    if current:
        rows = sorted({c.hwnd: c for c in children(_visible(ui, 2485)[0].hwnd, 4)
                       if c.text == "ListItem" and c.visible}.values(),
                      key=lambda c: c.rect[1])
        if not rows:
            raise RuntimeError(f"Saved Print Overlay is not selectable: {name}")
        ui.click(rows[0], settle=.5)
        # 배치가 다른 기존 Overlay를 자동으로 고치지 않는다.
        #
        # 삭제하고 다시 만드는 방법은 막혀 있다 — Print 서버가 참조 중인 Overlay는
        # 삭제 버튼(2432)을 눌러도 "This Overlay is in use and can not be deleted."로
        # 거부된다(2026-08-19 실측).
        #
        # 항목을 하나씩 옮기는 방법은 목록 행에서 FieldID를 화면으로 읽을 수 없어
        # 위험하다. Image Overlay에서 같은 상황에 "위에서부터 지운다"는 임의 규칙을
        # 만들어 Patient ID/Name을 잃은 적이 있다. 그래서 **사람이 확인하도록 중단**
        # 한다. 회귀는 DB를 기준 복원하므로 이 경로를 타지 않는다.
        raise RuntimeError(
            f"Print Overlay {name} 이 이미 있는데 영역 배치가 기대와 다릅니다. "
            f"기대={PRINT_EXPECTED_BY_POSITION} "
            f"실제={items_by_position(current['items'])} "
            "(Position: header=2 / top=0 / bottom=1). 덮어쓰지 않고 중단합니다 — "
            "Setting > DICOM > Print Overlay 에서 확인하십시오.")

    add = _visible(ui, 2431)
    name_edit = _visible(ui, 2490)
    if not add or not name_edit:
        raise RuntimeError("Print Overlay add/name controls not found")
    missing = [area for area in PRINT_AREAS
               if not _visible(ui, PRINT_AREA_ADD[area])]
    if missing:
        raise RuntimeError(
            f"Print Overlay 추가 버튼을 찾지 못했습니다: "
            f"{[(a, PRINT_AREA_ADD[a]) for a in missing]}")
    ui.click(add[0], settle=.8)
    ui.type_text(name_edit[0], name, clear=True, settle=.5)

    selected = []
    for area in PRINT_AREAS:
        add_button = _visible(ui, PRINT_AREA_ADD[area])[0]
        for label, index in PRINT_ITEMS_BY_AREA[area]:
            row, observed = _catalogue_row(ui, 2489, index, label, tesseract_exe)
            ui.click(row, settle=.2)
            ui.click(add_button, settle=.5)
            if ui.dialog():
                message = ui.dismiss_dialog(timeout=2)
                raise RuntimeError(
                    f"Failed to add Print Overlay item {label} to {area}: {message}")
            selected.append({"label": label, "area": area,
                             "position": PRINT_AREA_POSITION[area],
                             "catalogue_index": index, "ocr": observed})

    # 항목을 넣은 뒤 **Header 표시 설정**을 한다. 표시 위치가 None 이면 Header
    # 항목이 필름에 나오지 않는다(사양서1 297쪽). Layout 은 항목 수를 담을 수 있는
    # 가장 작은 것을 고른다("Layout 한 칸당 한 항목씩 표시한다").
    header = ensure_header_layout(
        ui, db, header_count, name=name, tesseract_exe=tesseract_exe,
        save=False) if header_count else None

    flows.setting_update(ui, wait=3)
    if ui.dialog():
        ui.dismiss_dialog(timeout=2)
    def complete(row):
        # 영역 배치와 Header 표시 설정을 **함께** 본다. Header 표시 위치가 None 이면
        # 항목이 저장돼 있어도 필름에 나오지 않는다(사양서1 297쪽).
        return bool(row) and matches_expected_areas(row["items"]) and (
            not header_count or header_matches(row["overlay"], header_count))

    end = time.time() + 10
    saved = _saved(db, name)
    while time.time() < end and not complete(saved):
        time.sleep(1)
        saved = _saved(db, name)
    if not complete(saved):
        want_position, want_layout, layout_label = header_targets(header_count or 1)
        raise RuntimeError(
            "Print Overlay 가 기대한 영역 배치/Header 설정으로 저장되지 않았습니다. "
            f"기대 영역={PRINT_EXPECTED_BY_POSITION} "
            f"실제 영역={items_by_position(saved['items']) if saved else None} / "
            f"기대 HeaderPosition={want_position}({HEADER_POSITION}) "
            f"HeaderLayout={want_layout}({layout_label}) "
            f"실제={{k: (saved or {{}}).get('overlay', {{}}).get(k) "
            f"for k in ('HeaderPosition', 'HeaderLayout')}}")
    saved["selected"] = selected
    saved["header"] = header
    saved["by_position"] = {pos: sorted(fids) for pos, fids
                            in items_by_position(saved["items"]).items()}
    saved["areas"] = {area: sorted(PRINT_FIELD_IDS[label]
                                   for label, _ in PRINT_ITEMS_BY_AREA[area])
                      for area in PRINT_AREAS}
    return saved


def apply_to_print_server(ui, db, print_name, overlay_key,
                          overlay_name=OVERLAY_NAME, tesseract_exe=None):
    """Select the saved overlay on the named DICOM Print server and persist it."""
    flows.open_dicom_setting(ui, "print", wait=2)
    server_list = _visible(ui, 2429)
    if not server_list:
        raise RuntimeError("DICOM Print SCP list not found")
    rows = sorted({c.hwnd: c for c in children(server_list[0].hwnd, 5)
                   if c.text == "ListItem" and c.visible}.values(),
                  key=lambda c: c.rect[1])
    if not rows:
        raise RuntimeError(f"DICOM Print server is not visible: {print_name}")
    ui.click(rows[0], settle=.6)
    combo = _visible(ui, 2474)
    if not combo:
        raise RuntimeError("DICOM Print Overlay selector (2474) not found")
    ui.click(combo[0], settle=.4)
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    options = []
    for c in children(popups[-1].hwnd, 4) if popups else []:
        if c.text == "TextButton" and c.visible:
            options.append(c)
    options = sorted({c.hwnd: c for c in options}.values(), key=lambda c: c.rect[1])
    # TextButton IDs are the current dropdown ordinal, not PRINT_OVERLAY.Key.
    # Read the rendered labels and select the configured overlay by name.
    observed = [(c, _ocr(c, tesseract_exe)) for c in options]
    scored = [(SequenceMatcher(None, _norm(overlay_name), _norm(label)).ratio(),
               c, label) for c, label in observed]
    best = max(scored, default=(0.0, None, ""), key=lambda item: item[0])
    exact = [best[1]] if best[0] >= .85 else []
    if not exact:
        raise RuntimeError(
            f"Print Overlay dropdown has no named item {overlay_name!r}; "
            f"available={[(c.ctrl_id, label) for c, label in observed]}, "
            f"best_score={best[0]:.3f}")
    ui.click(exact[0], settle=.5)
    flows.setting_update(ui, wait=3)
    if ui.dialog():
        ui.dismiss_dialog(timeout=2)
    row = db.one(
        "CONFIGURATION", "SELECT p.[Key],p.Name,d.Overlay FROM DICOM_PRINT p "
        "JOIN DICOM_PRINT_DICOM d ON d.PrintKey=p.[Key] WHERE p.Name=@name",
        {"name": print_name}) or {}
    if int(row.get("Overlay", -1)) != int(overlay_key):
        raise RuntimeError(
            f"Print server overlay was not applied: expected={overlay_key}, actual={row}")
    return row
