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


#: 영상 위 Overlay OCR 의 전처리 변형과 psm 조합.
#  Overlay 는 **검은 배경에 흰 글자**로 찍힌다. Tesseract 는 밝은 배경/어두운
#  글자로 학습돼 있어 그대로 넣으면 얇은 획이 뭉개진다 — 2026-08-20 에
#  `DATA_FLOW_MWL_01` 의 `W` 가 배율 6/4/3 전부에서 `Y` 로 읽혔다(`DATA_FLOY_...`).
#  그래서 (1) 명암 반전과 (2) 임계값 이진화를 함께 시도하고, 확대는 획을 흐리는
#  LANCZOS 대신 **NEAREST** 도 함께 쓴다. 그리고 psm 을 하나로 고정하지 않는다
#  (psm 7 이 한 자리 숫자를 버리는 문제는 `viewer_processing._ocr_integer`
#   에서 이미 겪었다).
OVERLAY_VARIANTS = ("auto", "invert", "bin150", "bin110")
OVERLAY_PSMS = (6, 7)


def overlay_variants(crop, scales=(6, 4), variants=OVERLAY_VARIANTS):
    """Overlay 크롭 하나에서 OCR 전처리 변형 이미지들을 만든다.

    반환: {"이름": PIL.Image}
    """
    from PIL import Image, ImageOps

    gray = crop.convert("L")
    out = {}
    for scale in scales:
        size = (gray.width * scale, gray.height * scale)
        smooth = gray.resize(size, Image.Resampling.LANCZOS)
        sharp = gray.resize(size, Image.Resampling.NEAREST)
        for name in variants:
            if name == "auto":
                out[f"auto_x{scale}"] = ImageOps.autocontrast(smooth)
            elif name == "invert":
                out[f"invert_x{scale}"] = ImageOps.invert(
                    ImageOps.autocontrast(smooth))
            elif name.startswith("bin"):
                t = int(name[3:])
                # 흰 글자 -> 검은 글자 / 검은 배경 -> 흰 배경 으로 뒤집는다.
                out[f"{name}_x{scale}"] = sharp.point(
                    lambda v, t=t: 0 if v > t else 255)
    return out


def read_overlay_text(crop, tesseract_exe=None, scales=(6, 4),
                      psms=OVERLAY_PSMS, variants=OVERLAY_VARIANTS):
    """Overlay 크롭을 여러 전처리·psm 으로 읽어 **모든 결과**를 돌려준다.

    반환: {"invert_x6_psm6": "읽은 문구", ...}

    한 조합만 쓰지 않는 이유는 위 `OVERLAY_VARIANTS` 주석에 있다. 호출부는 기대
    문구가 **어느 조합에서든** 나오면 표시된 것으로 본다. 판정을 느슨하게 하는
    것이 아니라 **전처리 실패와 미표시를 구분**하는 것이다 — 모든 조합에서 안
    나오면 그때는 정말 안 찍힌 것이거나 이 글꼴을 못 읽는 것이고, 그 사실을
    그대로 보고한다.
    """
    import pytesseract

    if tesseract_exe:
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    reads = {}
    for name, image in overlay_variants(crop, scales=scales,
                                        variants=variants).items():
        for psm in psms:
            try:
                reads[f"{name}_psm{psm}"] = pytesseract.image_to_string(
                    image, config=f"--psm {psm}", lang="eng").strip()
            except Exception as exc:                   # noqa: BLE001
                reads[f"{name}_psm{psm}"] = f"<ocr err {exc}>"
    return reads


#: 버튼 문구 판독에 쓰는 psm 순서.
#  Film 창의 `Close`(1105)는 아이콘+글자가 섞여 있어 psm 6/7 이 **빈 문자열**을
#  돌려준다(2026-08-21 실측). psm 11(sparse text)과 8(single word)에서만 읽혔다.
#  하나로 고정하지 않는다 — `viewer_processing._ocr_integer` 에서 같은 교훈을 얻었다.
BUTTON_PSMS = (11, 8, 7, 6)

#: 버튼 전처리 변형. 이 제품의 확인 대화상자는 **분홍 배경 + 흰 글자**(Yes)와
#  **흰 배경 + 분홍 글자**(No)를 나란히 쓴다. `autocontrast` 하나로는 Yes 가
#  `ee`, No 가 `(me)` 로 읽혀 구분되지 않았고, 임계값 이진화에서만
#  `Yes`/`No` 가 읽혔다(2026-08-21 실측 — Film 창의 "Are you sure you want to
#  close?" 대화상자).
BUTTON_VARIANTS = ("auto", "invert", "bin150", "bin150i", "bin110i")


def _button_images(control, scale=4, variants=BUTTON_VARIANTS):
    from PIL import ImageOps

    gray = ImageGrab.grab(bbox=control.rect, all_screens=True).convert("L")
    made = {}
    for name in variants:
        if name == "auto":
            image = ImageOps.autocontrast(gray)
        elif name == "invert":
            image = ImageOps.invert(ImageOps.autocontrast(gray))
        elif name == "bin150":
            image = gray.point(lambda v: 255 if v > 150 else 0)
        elif name == "bin150i":
            image = gray.point(lambda v: 0 if v > 150 else 255)
        elif name == "bin110i":
            image = gray.point(lambda v: 0 if v > 110 else 255)
        else:
            continue
        made[name] = image.resize((image.width * scale, image.height * scale))
    return made


def button_reads(control, tesseract_exe=None, scale=4, psms=BUTTON_PSMS,
                 variants=BUTTON_VARIANTS):
    """버튼 컨트롤에서 읽은 문구 전부. `{"변형_psm": 문구}`.

    판독본을 전부 남기는 이유: 어느 조합에서 읽혔는지를 판정 근거에 적을 수 있고,
    나중에 전처리를 손볼 때 무엇이 통했는지 되짚을 수 있다.
    """
    import pytesseract

    if tesseract_exe:
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    out = {}
    for name, image in _button_images(control, scale, variants).items():
        for psm in psms:
            text = pytesseract.image_to_string(
                image, config=f"--psm {psm}", lang="eng").strip()
            if text:
                out[f"{name}_psm{psm}"] = text
    return out


def button_label(control, tesseract_exe=None, scale=4, psms=BUTTON_PSMS):
    """버튼 컨트롤의 화면 문구(처음 읽힌 것). 못 읽으면 빈 문자열.

    **누르기 전에 문구를 확인하는 용도**다. 같은 화면에 파괴적인 버튼이 나란히
    있을 때(예: Film 창의 `Print`(1149) 옆 `Close`(1105)) ID 만 믿고 누르면
    의도치 않은 동작이 일어난다.
    """
    reads = button_reads(control, tesseract_exe, scale, psms, ("auto",))
    if reads:
        return next(iter(reads.values()))
    reads = button_reads(control, tesseract_exe, scale, psms)
    return next(iter(reads.values())) if reads else ""


def pick_button(buttons, wanted, tesseract_exe=None):
    """버튼 목록에서 **문구가 맞는 하나**를 고른다.

    `(control, {버튼 index: 읽은 문구들})` 을 돌려준다. 맞는 버튼이 없거나
    둘 이상이면 `control` 은 `None` 이다 — **애매하면 아무것도 누르지 않는다.**
    확인 대화상자의 Yes/No 를 위치나 ID 로 고르면 정반대를 누를 수 있다.
    """
    key = norm(wanted)
    reads, hits = {}, []
    for index, control in enumerate(buttons):
        got = button_reads(control, tesseract_exe)
        reads[index] = {"rect": control.rect, "reads": got}
        if any(key and key in norm(text) for text in got.values()):
            hits.append(control)
    return (hits[0] if len(hits) == 1 else None), reads


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

    `match="exact"`(기본)는 정규화 후 완전일치, `"contains"` 는 부분일치,
    `"prefix"` 는 UI가 긴 값을 잘라 표시하는 콤보에서 한쪽이 다른 쪽의
    접두사인 경우를 허용한다. 어느 방식이든 후보가 하나일 때만 선택한다.
    부분일치는 항목이 `(0032,1064) Requested Procedure Code Sequence` 처럼 길고
    앞부분(태그 번호)만으로 특정되는 경우에 쓴다. **두 항목 이상이 걸리면 아무것도
    누르지 않는다** — 애매한 상태에서 하나를 고르면 설정이 조용히 틀어진다.

    반환: `{"wanted": str, "items_read": [str, ...]}`
    원하는 문구가 없으면 아무것도 누르지 않고 `RuntimeError` 를 던진다.
    """
    if match not in ("exact", "contains", "prefix"):
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
    elif match == "contains":
        hits = [item for item, text in zip(items, seen) if key and key in text]
    else:
        # 로그인 ID 콤보는 `TEST_USER_FLOW`를 `TEST_USE`처럼 잘라 표시한다.
        # 너무 짧은 OCR 결과를 접두사로 인정하면 다른 계정을 고를 수 있으므로
        # 로그인 검증과 같은 최소 4자 조건을 둔다.
        hits = [item for item, text in zip(items, seen)
                if min(len(key), len(text)) >= 4
                and (key.startswith(text) or text.startswith(key))]
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
