# -*- coding: utf-8 -*-
r"""커스텀 렌더 컨트롤의 텍스트를 읽고, 문구로 항목을 고르는 공용 기능.

Bellalun 의 MFC 커스텀 컨트롤(`TextButton`, `ListItem`, `IconButton` 등)은
`WM_GETTEXT` 로 빈 문자열을 돌려준다. 그래서 화면에 보이는 글자를 읽으려면 컨트롤
영역을 캡처해 OCR 해야 한다.

`core/print_overlay.py` 가 Print Overlay 카탈로그와 Header 콤보에 쓰던 코드를 옮겨
왔다(2026-08-19). 계정 권한 그룹 콤보(WF_13) 등 다른 화면에서도 같은 일이
필요해졌기 때문이다.

**항목 순서를 신뢰하지 않는다.** 2026-08-19 에 Print Overlay Header 표시 위치 콤보의
두 번째 항목을 눌렀더니 DB 값이 Top(1) 이 아니라 Bottom(2) 이 됐다. 그래서 순서로
고르지 않고 문구를 읽어 고르고, 원하는 문구가 없으면 **아무것도 누르지 않고**
읽은 값을 붙여 실패시킨다 — 엉뚱한 항목을 고르면 설정이 조용히 틀어진다.
"""

from __future__ import annotations

import re

from PIL import ImageGrab, ImageOps

from .ui import children


def norm(value):
    """비교용 정규화 — 영숫자만 남기고 소문자로."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def ocr(control, tesseract_exe=None, psm=7, scale=3):
    """컨트롤 영역을 캡처해 OCR 한다."""
    import pytesseract

    if tesseract_exe:
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    image = ImageGrab.grab(bbox=control.rect, all_screens=True).convert("L")
    image = ImageOps.autocontrast(image).resize(
        (image.width * scale, image.height * scale))
    return pytesseract.image_to_string(
        image, config=f"--psm {psm}", lang="eng").strip()


def visible(ui, control_id):
    return [c for c in ui.by_id(control_id) if c.visible]


def list_rows(ui, list_id, item_text="ListItem", depth=5):
    """목록 컨트롤의 보이는 행을 위에서 아래 순서로 돌려준다."""
    hits = visible(ui, list_id)
    if not hits:
        return []
    rows = {c.hwnd: c for c in children(hits[0].hwnd, depth)
            if c.visible and c.text == item_text}
    return sorted(rows.values(), key=lambda c: c.rect[1])


def find_row_by_text(ui, list_id, wanted, tesseract_exe=None,
                     item_text="ListItem", min_prefix=8):
    """목록에서 **OCR 로 읽은 문구**가 맞는 행을 찾는다.

    좁은 열은 값을 잘라서 표시한다. 2026-08-19 에 `TEST_USER_FLOW` 계정이 ID 열에서
    `testuserflo` 로 잘려 완전일치가 실패했다. 그래서 완전 포함으로 먼저 찾고,
    없으면 접두사를 한 글자씩 줄여 가며 찾는다.

    **접두사로 찾을 때 두 행 이상이 걸리면 아무것도 돌려주지 않는다.** 애매한 상태
    에서 하나를 고르면 엉뚱한 대상을 수정·삭제할 수 있다.

    반환: `(control, 읽은 문구 목록)`. 못 찾으면 `(None, 읽은 문구 목록)`.
    """
    rows = list_rows(ui, list_id, item_text=item_text)
    seen = [norm(ocr(row, tesseract_exe)) for row in rows]
    key = norm(wanted)

    exact = [row for row, text in zip(rows, seen) if key and key in text]
    if len(exact) == 1:
        return exact[0], seen
    if len(exact) > 1:
        return None, seen

    for length in range(len(key) - 1, min_prefix - 1, -1):
        prefix = key[:length]
        hits = [row for row, text in zip(rows, seen) if prefix in text]
        if len(hits) == 1:
            return hits[0], seen
        if len(hits) > 1:
            # 더 짧게 줄이면 후보가 늘 뿐이다. 애매하면 고르지 않는다.
            return None, seen
    return None, seen


def pick_combo_by_text(ui, control_id, wanted, tesseract_exe=None, what="콤보",
                       settle=1.0, match="exact"):
    """콤보를 열어 **OCR 로 읽은 항목 문구**가 맞는 것을 고른다.

    `match="exact"`(기본)는 정규화 후 완전일치, `"contains"` 는 부분일치다.
    부분일치는 항목이 `(0032,1064) Requested Procedure Code Sequence` 처럼 길고
    앞부분(태그 번호)만으로 특정되는 경우에 쓴다. **두 항목 이상이 걸리면 아무것도
    누르지 않는다** — 애매한 상태에서 하나를 고르면 설정이 조용히 틀어진다.

    반환: `{"wanted": str, "items_read": [str, ...]}`
    원하는 문구가 없으면 아무것도 누르지 않고 `RuntimeError` 를 던진다.
    """
    if match not in ("exact", "contains"):
        raise ValueError(f"알 수 없는 match: {match!r}")
    hits = visible(ui, control_id)
    if not hits:
        raise RuntimeError(f"{what} 콤보({control_id})를 찾지 못했습니다"
                           "(비활성일 수 있습니다).")
    ui.click(hits[0], settle=settle)
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    if not popups:
        raise RuntimeError(f"{what} 콤보({control_id}) 목록이 열리지 않았습니다.")
    items = sorted({c.hwnd: c for c in children(popups[0].hwnd, 4)
                    if c.visible and c.text == "TextButton"}.values(),
                   key=lambda c: c.rect[1])
    key = norm(wanted)
    seen = [norm(ocr(item, tesseract_exe)) for item in items]
    if match == "exact":
        hits = [item for item, text in zip(items, seen) if text == key]
    else:
        hits = [item for item, text in zip(items, seen) if key and key in text]
    if len(hits) != 1:
        raise RuntimeError(
            f"{what} 콤보에서 {wanted!r} 항목을 "
            f"{'찾지 못했습니다' if not hits else f'{len(hits)}개 찾았습니다'}"
            f"(match={match}). 읽은 항목={seen}. "
            "잘못된 항목을 고르지 않도록 중단합니다.")
    ui.click(hits[0], settle=settle)
    return {"wanted": wanted, "items_read": seen, "match": match}


def read_combo_items(ui, control_id, tesseract_exe=None, what="콤보"):
    """콤보를 열어 항목 문구만 읽고 **아무것도 고르지 않고 닫는다.**

    선택지를 모를 때 먼저 확인하는 용도다. 값을 추측해 넣지 않기 위한 도구다.
    """
    hits = visible(ui, control_id)
    if not hits:
        raise RuntimeError(f"{what} 콤보({control_id})를 찾지 못했습니다.")
    ui.click(hits[0], settle=1.0)
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    if not popups:
        raise RuntimeError(f"{what} 콤보({control_id}) 목록이 열리지 않았습니다.")
    items = sorted({c.hwnd: c for c in children(popups[0].hwnd, 4)
                    if c.visible and c.text == "TextButton"}.values(),
                   key=lambda c: c.rect[1])
    read = [ocr(item, tesseract_exe) for item in items]
    # 목록을 닫는다 — 같은 콤보를 다시 눌러 토글한다.
    ui.click(hits[0], settle=.8)
    return read
