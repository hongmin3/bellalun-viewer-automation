# -*- coding: utf-8 -*-
r"""Setting 화면의 **목록**을 스크롤 아래 숨은 행까지 전수 열거하고, 행마다
선택했을 때 나타나는 상세값을 읽는다.

`TC_Basic_WorkFlow_14`(Setting Export/Import) Expected 7 — "Export 시점의
설정값으로 복원되어 있다" — 가운데 **목록 행의 상세값**을 판정하기 위한 모듈이다.

## 왜 새로 만들었는가 (2026-08-25 실패의 교훈)

2026-08-25 에 목록 스크롤을 붙였다가 **사용자 지시로 제거**했다. 이유:

> 스크롤 목록은 같은 가상 `ListItem` HWND/ID 를 재사용해, 조금 내린 뒤 일부 행만
> 읽고도 **끝으로 오인**했다.

핵심은 "행을 무엇으로 식별하는가" 였다. HWND 도 ctrl_id 도 재사용되므로 둘 다
식별자가 될 수 없다. 그래서 이 모듈은 **행에 실제로 찍힌 문구**로 식별한다.

## 끝까지 봤다는 것을 어떻게 증명하는가 — 세 겹

1. **정지 증명** — 스크롤해도 보이는 행 시퀀스가 더 이상 바뀌지 않는다.
   (`_screen_signatures` 가 같으면 바닥이다.)
2. **연속 증명** — 스크롤 전후 시퀀스가 **겹쳐야** 한다. 이전 화면의 꼬리와 새
   화면의 머리가 겹치지 않으면 한 화면 이상을 건너뛴 것이므로, 스크롤 폭을 줄여
   다시 시도하고 그래도 겹치지 않으면 **열거 실패로 보고한다**(빠뜨린 채
   "전수" 라고 말하지 않는다). 이것이 2026-08-25 오인의 직접적인 재발 방지다.
3. **개수 증명** — 열거한 행 수를 **DB 원천 테이블 행 수**와 대조한다. 화면과
   무관한 결정적 근거라 1·2 가 통과해도 이것이 어긋나면 실패다. 호출부가
   `expected_count` 로 넘긴다.

셋 중 하나라도 성립하지 않으면 `complete=False` 와 이유를 남긴다. **불완전한
열거를 판정 근거로 쓰지 않는다.**

## 행을 선택할 때의 안전

`ui.click(row)` 는 행 **중앙**을 누른다. 행 가운데에 버튼(⚙ 등)이 있는 목록에서는
의도와 다른 것이 눌린다 — 2026-08-20 에 Hospital Code 목록에서 실제로 그렇게
View Position 대화상자가 열렸고 그 팝업이 이후 클릭을 삼켰다(AGENTS.md 3절).
그래서 이 모듈은 **행 좌측 첫 열**의 좌표를 rect 에서 계산해 누른다.

행 선택은 조회 동작이지만 "누르지 않아도 즉시 저장되는" 화면이 있었으므로
(같은 3절), 호출부가 탐색 전후 DB 스냅샷을 대조하도록 설계했다
(`TC_Basic_WorkFlow_14` 가 `snapshot.config_identical` 로 확인한다).
"""

from __future__ import annotations

import time

from core import setting_values
from core.ui import children

#: 목록 행으로 볼 컨트롤의 `WM_GETTEXT` 이름. 값이 아니라 **종류**다
#  (`setting_values.GENERIC_TEXTS` 에 들어 있는 일반 이름).
ROW_TEXTS = {"ListItem"}

#: 행 좌측에서 이 비율만큼 들어간 x 를 누른다. 행 가운데의 버튼을 피하기 위한
#  것이고, 좌측 첫 열은 보통 이름/번호 셀이라 눌러도 안전하다.
ROW_CLICK_X_RATIO = 0.08

#: 한 번에 굴리는 휠 노치. 겹침이 생기지 않으면 이 값을 절반씩 줄인다.
DEFAULT_SCROLL_NOTCHES = 3

#: 스크롤 반복 상한. 목록이 이보다 길면 열거 실패로 보고한다(무한 루프 금지).
MAX_SCROLL_STEPS = 60


class ListWalkError(RuntimeError):
    pass


def _child_signature(row):
    """자식 컨트롤의 텍스트만으로 구한 서명. 자식 텍스트가 없으면 `None`.

    `None` 은 "이 행은 owner-draw 라 자식 창이 없다"는 뜻이다(2026-08-31 실측 —
    `System > Account` 의 행은 `core.ui.children` 으로 자식이 0개인데, 같은
    rect 를 화면 OCR 하면 `service`/`admin` 계정이 실제로 그려져 있다).
    """
    parts = []
    for c in children(row.hwnd, 3):
        if not c.visible:
            continue
        text = (c.text or "").strip()
        if text and text not in setting_values.GENERIC_TEXTS:
            parts.append(text)
    return " | ".join(parts) if parts else None


def row_signature(row, tesseract_exe=None):
    """행 하나의 식별 문구. 자식 컨트롤의 텍스트를 이어 붙인다.

    자식 텍스트가 없을 때만 화면 픽셀을 OCR 로 읽는다 — 자식 텍스트가 있는
    (=이미 빠르고 확실한) 페이지는 OCR 을 타지 않는다. **OCR 로 읽은 서명은
    같은 화면을 다시 캡처해도 완전히 같다는 보장이 없다**(안티에일리어싱·
    하이라이트 등으로 캡처마다 미세하게 달라질 수 있음 — 2026-08-31 실측,
    `walk()` 가 스크롤이 필요 없는 목록에만 OCR 결과를 신뢰하는 이유다).

    빈 문자열이면 **그 행은 정말 식별할 수 없다**(OCR 도 실패했다). 호출부는
    그 목록을 열거 불가로 보고해야 한다 — 식별할 수 없는 행으로 겹침을
    계산하면 2026-08-25 과 같은 오인이 다시 난다.
    """
    sig = _child_signature(row)
    if sig is not None:
        return sig
    from core import uitext
    try:
        return uitext.ocr(row, tesseract_exe).strip()
    except Exception:                                      # noqa: BLE001
        return ""


def visible_rows(pane):
    """패널 안에 **현재 보이는** 목록 행(위->아래, 왼->오른쪽)."""
    rows, seen = [], set()
    for c in setting_values.pane_controls(pane, depth=6):
        if (c.text or "") in ROW_TEXTS and c.hwnd not in seen:
            seen.add(c.hwnd)
            rows.append(c)
    return sorted(rows, key=lambda c: (c.rect[1], c.rect[0]))


def _screen(pane, tesseract_exe=None):
    """현재 화면의 (행 컨트롤, 서명, OCR 로 읽은 행이 있는지) 목록."""
    rows = visible_rows(pane)
    sigs = [row_signature(r, tesseract_exe) for r in rows]
    used_ocr = any(_child_signature(r) is None for r in rows)
    return rows, sigs, used_ocr


def scroll_point(pane, rows):
    """휠을 굴릴 좌표. **목록 위**여야 한다.

    패널 중앙에서 굴리면 목록이 패널의 한쪽에만 있는 페이지에서 아무 일도
    일어나지 않는다(휠은 커서 아래 컨트롤로 간다). 보이는 행들의 중앙을 쓰고,
    행이 없을 때만 패널 중앙으로 물러선다.
    """
    if not rows:
        return pane.center
    left = min(r.rect[0] for r in rows)
    right = max(r.rect[2] for r in rows)
    top = min(r.rect[1] for r in rows)
    bottom = max(r.rect[3] for r in rows)
    return ((left + right) // 2, (top + bottom) // 2)


def overlap(previous, current):
    """`previous` 의 꼬리와 `current` 의 머리가 겹치는 **최대 길이**.

    스크롤은 목록을 위로 밀어 올리므로, 새 화면의 첫 몇 행은 직전 화면의 마지막
    몇 행과 같아야 한다. 그 길이가 0 이면 한 화면 이상을 건너뛴 것이다.

    가장 긴 겹침을 고른다. 반복 문구가 있는 목록에서 짧은 겹침이 우연히 맞는
    것보다, 긴 쪽이 실제 이동을 반영할 가능성이 높다.
    """
    limit = min(len(previous), len(current))
    for k in range(limit, 0, -1):
        if previous[-k:] == current[:k]:
            return k
    return 0


def walk(ui, pane, on_row=None, expected_count=None,
         notches=DEFAULT_SCROLL_NOTCHES, settle=0.6,
         max_steps=MAX_SCROLL_STEPS, tesseract_exe=None):
    r"""목록을 위에서 아래까지 훑는다.

    `on_row(row_control, signature, index)` 를 **새로 등장한 행마다 한 번씩**
    부른다. 같은 행을 두 번 부르지 않는다(겹침으로 걸러낸다).

    반환::

        {"signatures": [...],        # 열거한 행 서명(등장 순서)
         "screens": [[...], ...],    # 화면 단위 시퀀스(감사용)
         "steps": 3,                 # 실제 스크롤 횟수
         "complete": True/False,     # 세 증명을 모두 통과했는가
         "reasons": [...],           # 통과하지 못한 이유
         "expected_count": n or None,
         "unreadable_rows": 0}

    **완주하지 못하면 예외를 던지지 않는다.** 판정은 호출부(TC)가 하고, 이
    함수는 무엇을 보았고 무엇을 증명하지 못했는지만 돌려준다.
    """
    rows, sigs, used_ocr = _screen(pane, tesseract_exe)
    if not rows:
        return {"signatures": [], "screens": [], "steps": 0, "complete": False,
                "reasons": ["목록 행이 보이지 않는다"],
                "expected_count": expected_count, "unreadable_rows": 0}

    unreadable = sum(1 for s in sigs if not s)
    collected = list(sigs)
    screens = [list(sigs)]
    reasons = []
    if on_row is not None:
        for offset, (row, sig) in enumerate(zip(rows, sigs)):
            on_row(row, sig, offset)

    # OCR 로 읽은 서명은 같은 화면을 다시 캡처해도 완전히 같다는 보장이 없다
    # (2026-08-31 실측 — `System > Account` 를 두 번 읽으니 'service ... O' 가
    # 'service ... O | ea' 로 잡음이 붙었다). 그런데 정지/연속 증명은 **완전
    # 일치**를 요구하므로, 이런 목록에 스크롤 재확인을 시키면 잡음을 "행을
    # 건너뛰었다"로 오판한다(2026-08-25 재발 방지 설계와 정면으로 부딪힌다).
    # 이미 첫 화면에서 DB 원천 행 수와 정확히 같은 개수를 다 봤다면(=스크롤이
    # 필요 없다는 뜻) 잡음투성이 재확인 스크롤을 하지 않는다. 그 외(개수가
    # 안 맞거나 자식 텍스트로 읽어 잡음이 없는 목록)는 아래 3중 증명을 그대로
    # 다 거친다.
    if (used_ocr and not unreadable and expected_count is not None
            and len(rows) == expected_count):
        return {"signatures": collected, "screens": screens, "steps": 0,
                "complete": True, "reasons": [],
                "expected_count": expected_count, "unreadable_rows": 0}

    step = 0
    bottom = False
    gap = False
    current_notches = max(1, int(notches))
    wheel_at = scroll_point(pane, rows)
    while step < max_steps:
        step += 1
        ui.wheel(wheel_at, -current_notches, settle=settle)
        rows, sigs, _used_ocr = _screen(pane, tesseract_exe)
        unreadable += sum(1 for s in sigs if not s)
        if sigs == screens[-1]:
            bottom = True
            break
        k = overlap(screens[-1], sigs)
        if k == 0:
            if current_notches > 1:
                # 한 번에 너무 많이 굴렸다. 되돌리고 폭을 줄여 다시 시도한다.
                ui.wheel(wheel_at, current_notches, settle=settle)
                current_notches = max(1, current_notches // 2)
                step -= 1                       # 재시도는 진행으로 세지 않는다
                continue
            gap = True
            reasons.append(
                f"스크롤 {step}회째에 이전 화면과 겹치는 행이 없다 — 행을 "
                f"건너뛰었을 수 있어 전수 열거로 인정하지 않는다 "
                f"(이전 꼬리={screens[-1][-2:]}, 새 머리={sigs[:2]})")
            break
        screens.append(list(sigs))
        fresh = sigs[k:]
        if on_row is not None:
            for offset, sig in enumerate(fresh):
                on_row(rows[k + offset], sig, len(collected) + offset)
        collected.extend(fresh)

    if step >= max_steps and not bottom:
        reasons.append(
            f"스크롤 상한 {max_steps}회에 도달했는데 목록 끝에 닿지 않았다")
    if not bottom:
        reasons.append("스크롤해도 화면이 더 이상 바뀌지 않는 상태를 확인하지 못했다")
    if unreadable:
        reasons.append(
            f"문구를 읽지 못한 행 {unreadable}개 — 행을 식별할 수 없으면 "
            "겹침 계산을 믿을 수 없다")
    if expected_count is not None and len(collected) != expected_count:
        reasons.append(
            f"열거한 행 {len(collected)}개가 DB 원천 행 {expected_count}개와 "
            "다르다")
    return {"signatures": collected, "screens": screens, "steps": step,
            "complete": bool(bottom) and not gap and not unreadable
                        and not reasons,
            "reasons": reasons, "expected_count": expected_count,
            "unreadable_rows": unreadable}


def row_click_point(row):
    """행을 **선택**하기 위해 누를 좌표. 행 중앙의 버튼을 피한다."""
    left, top, right, bottom = row.rect
    return (left + max(6, int((right - left) * ROW_CLICK_X_RATIO)),
            (top + bottom) // 2)


def read_details(ui, pane, row, exclude_ids=(), settle=0.6):
    """행을 선택하고 **패널의 값**을 읽어 돌려준다.

    목록 행 자체의 값은 빼고(그건 서명으로 이미 갖고 있다) 상세 영역만 남긴다.
    반환 형태는 `setting_values.read_page` 와 같은 `{키: {kind, value}}` 다.
    """
    ui.click(row_click_point(row), settle=settle)
    controls = setting_values.pane_controls(pane, depth=6)
    values = setting_values.read_page(ui, pane.rect, controls=controls)
    if not exclude_ids:
        return values
    drop = {str(i) for i in exclude_ids}
    return {k: v for k, v in values.items() if k.split("@")[0] not in drop}


def collect(ui, pane, expected_count=None, exclude_ids=(),
            notches=DEFAULT_SCROLL_NOTCHES, settle=0.6, tesseract_exe=None):
    """목록을 훑으며 **행마다 상세값까지** 모은다.

    반환: `walk()` 의 결과에 `"details": {서명 또는 위치: {키: {...}}}` 를
    더한 것.

    같은 서명이 두 번 나오면 뒤엣것에 `#2` 를 붙인다 — 값을 덮어써 한 행이
    조용히 사라지는 것보다 낫다. 그런 목록은 서명만으로 행을 가릴 수 없다는
    뜻이므로 `duplicate_signatures` 에 남겨 호출부가 알 수 있게 한다.

    **OCR 로 읽은 행은 서명 대신 위치(`<OCR 행 #N>`)를 키로 쓴다.** OCR 은
    같은 화면을 다시 캡처해도 완전히 같은 문구를 준다는 보장이 없어서
    (2026-08-31 실측), 서명을 키로 쓰면 Export 전/후 두 번의 `collect()` 호출
    사이에서 **값이 안 바뀐 행도 문구가 미세하게 달라 서로 다른 행으로
    보여 짝이 안 맞을 수 있다** — 조용히 대조 대상에서 빠지는 것이지 FAIL 로
    드러나지도 않는다. 식별 컬럼이 없는 행을 행 순서로 짝짓는 기존 관례
    (`../프로젝트_상세.md` B.14)와 같은 해법이다 — 목록 순서가 Export/Import
    사이에 바뀌지 않는다는 전제이고, 이 전제가 깨지면(행이 늘거나 줄면) 위
    "목록 전 행 열거 완주" 서브체크가 별도로 잡는다.
    """
    details = {}
    duplicates = []
    stale = []

    def on_row(row, signature, index):
        ocr_based = _child_signature(row) is None
        if ocr_based:
            # 위치가 곧 식별자다 — 노이즈가 낀 문구를 키로 쓰지 않는다.
            key = f"<OCR 행 #{index}>"
            try:
                details[key] = read_details(ui, pane, row,
                                            exclude_ids=exclude_ids,
                                            settle=settle)
            except Exception as exc:                       # noqa: BLE001
                details[key] = {"<읽기 실패>": {
                    "kind": "error", "value": f"{type(exc).__name__}: {exc}"}}
            return
        key = signature or f"<빈 문구 #{index}>"
        if key in details:
            duplicates.append(key)
            suffix = 2
            while f"{key}#{suffix}" in details:
                suffix += 1
            key = f"{key}#{suffix}"
        # 앞 행을 선택하면서 목록이 움직였을 수 있다. 그러면 들고 있는 행
        # 컨트롤이 **다른 행을 가리킨다.** 누르기 직전에 문구를 다시 읽어
        # 확인한다 — 엉뚱한 행의 상세값을 그 행의 것으로 기록하면 대조가
        # 조용히 거짓이 된다. (OCR 기반 행은 문구 자체가 불안정해 이 재확인이
        # 안 통하므로 위에서 걸러진다 — 결정은 위치만으로 한다.)
        fresh = row_signature(row, tesseract_exe)
        if fresh != signature:
            stale.append({"expected": signature, "actual": fresh,
                          "index": index})
            return
        try:
            details[key] = read_details(ui, pane, row, exclude_ids=exclude_ids,
                                        settle=settle)
        except Exception as exc:                           # noqa: BLE001
            details[key] = {"<읽기 실패>": {"kind": "error",
                                        "value": f"{type(exc).__name__}: {exc}"}}

    result = walk(ui, pane, on_row=on_row, expected_count=expected_count,
                  notches=notches, settle=settle, tesseract_exe=tesseract_exe)
    result["details"] = details
    result["duplicate_signatures"] = duplicates
    result["stale_rows"] = stale
    if duplicates:
        result["complete"] = False
        result["reasons"].append(
            f"같은 문구의 행이 {len(duplicates)}개 있다 — 문구만으로 행을 "
            "구분할 수 없어 전수 열거를 보증할 수 없다")
    if stale:
        result["complete"] = False
        result["reasons"].append(
            f"선택 직전에 문구가 달라진 행 {len(stale)}개 — 앞 행을 누르면서 "
            "목록이 움직인 것이라 그 행의 상세값을 읽지 않았다: "
            f"{stale[:3]}")
    return result


def compare(before, after):
    """두 `collect()` 결과의 상세값을 항목 단위로 대조한다.

    반환: `{"changed": [...], "only_before": [...], "only_after": [...],
            "compared_rows": n, "compared_items": n}`

    `setting_values.compare` 와 같은 형식이지만 대상이 **행 -> 상세값** 2단이다.
    """
    b_rows = before.get("details") or {}
    a_rows = after.get("details") or {}
    changed, only_b, only_a = [], [], []
    items = 0
    for key in sorted(set(b_rows) | set(a_rows)):
        if key not in a_rows:
            only_b.append(key)
            continue
        if key not in b_rows:
            only_a.append(key)
            continue
        bv, av = b_rows[key], a_rows[key]
        for item in sorted(set(bv) | set(av)):
            if item not in av:
                only_b.append(f"{key}:{item}")
            elif item not in bv:
                only_a.append(f"{key}:{item}")
            else:
                items += 1
                if bv[item].get("value") != av[item].get("value"):
                    changed.append({"row": key, "item": item,
                                    "before": bv[item].get("value"),
                                    "after": av[item].get("value")})
    return {"changed": changed, "only_before": only_b, "only_after": only_a,
            "compared_rows": len(set(b_rows) & set(a_rows)),
            "compared_items": items}


#: 목록 페이지 -> 그 목록의 **원천 DB 행 수** 쿼리.
#
#  "개수 증명"(모듈 docstring 3번)에 쓴다. 화면과 무관한 결정적 근거이므로,
#  스크롤이 끝까지 갔다는 주장을 여기서 검산한다. 2026-08-27 실측 행 수를 주석에
#  남긴다 — 값이 아니라 **매핑이 맞는지** 확인하는 기준이다.
#
#  매핑이 없는 페이지도 탐색은 한다(정지·연속 증명만 하고 개수 증명은 생략).
#  없는 매핑을 추측해 넣지 않는다 — 틀린 기대값은 정상을 FAIL 로 만든다.
ROW_COUNT_QUERIES = {
    # Setting > System > Account — 계정 목록 (실측 2)
    "system.account": ("ACCOUNT", "SELECT COUNT(*) AS n FROM ACCOUNT"),
    # Setting > Display > Overlay — Image Overlay 항목 (실측 8)
    "display.overlay": ("CONFIGURATION",
                        "SELECT COUNT(*) AS n FROM OVERLAY_ITEM"),
    # Setting > Display > LUT — LUT **개수**(실측 3: ScreenLUT/StorageLUT/
    # ProcessLUT). `LUT_ITEM`은 LUT 하나가 아니라 **LUT 곡선의 제어점**을
    # 저장한다(`LUTKey`+`Order`+`X`+`Y`, 2026-08-31 실측 — LUT 3개 x 곡선점
    # 4개 = 12행). `COUNT(*)`는 화면의 LUT 행 수가 아니라 곡선점 수를 세는
    # 것이었다 — `COUNT(DISTINCT LUTKey)`로 고친다.
    "display.lut": ("CONFIGURATION",
                    "SELECT COUNT(DISTINCT LUTKey) AS n FROM LUT_ITEM"),
    # Setting > Tool > Predefined Text (실측 7)
    "tool.predefined_text": ("CONFIGURATION",
                             "SELECT COUNT(*) AS n FROM PREDEFINED_TEXT_ITEM"),
    # Setting > Study > Reject/Retake — Reject 사유 (실측 7)
    "study.reject_retake": ("CONFIGURATION",
                            "SELECT COUNT(*) AS n FROM REJECT_REASON"),
    # Setting > Procedure > Procedure (실측 15)
    "procedure.procedure": ("PROCEDURE",
                            "SELECT COUNT(*) AS n FROM PROCEDURE_INFO"),
    # Setting > Procedure > Hospital Code (실측 0)
    "procedure.hospital_code": ("PROCEDURE",
                                "SELECT COUNT(*) AS n FROM HOSPITAL_CODE"),
    # Setting > DICOM > * — SCP 목록. `SCPUseType=0` 만 설정 행이고 나머지는
    #   전송 작업 사본이라 화면에 나오지 않는다
    #   (`core/dicom_settings.STORAGE_SCP_USE_TYPE` 주석의 실측 근거).
    "dicom.storage": ("CONFIGURATION",
                      "SELECT COUNT(*) AS n FROM DICOM_STORAGE "
                      "WHERE SCPUseType=0"),
    "dicom.mwl": ("CONFIGURATION", "SELECT COUNT(*) AS n FROM DICOM_MWL"),
    "dicom.mpps": ("CONFIGURATION", "SELECT COUNT(*) AS n FROM DICOM_MPPS"),
    "dicom.print": ("CONFIGURATION", "SELECT COUNT(*) AS n FROM DICOM_PRINT"),
    "dicom.storage_group": ("CONFIGURATION",
                            "SELECT COUNT(*) AS n FROM DICOM_STORAGE_GROUP"),
    "dicom.storage_commitment": (
        "CONFIGURATION",
        "SELECT COUNT(*) AS n FROM DICOM_STORAGE_COMMITMENT"),
    "dicom.query_retrieve": ("CONFIGURATION",
                             "SELECT COUNT(*) AS n FROM DICOM_QR"),
    # Setting > DICOM > Print Overlay — 항목 목록 (실측 6)
    "dicom.print_overlay": ("CONFIGURATION",
                            "SELECT COUNT(*) AS n FROM PRINT_OVERLAY_ITEM"),
    # Setting > DICOM > Tag Mapping (실측 17)
    "dicom.tag_mapping": ("CONFIGURATION",
                          "SELECT COUNT(*) AS n FROM DICOM_MAPPING"),
    # Setting > Q.C. > Scheduler (실측 23 — 화면 한 장에 다 들어가지 않는다)
    "qc.scheduler": ("CONFIGURATION", "SELECT COUNT(*) AS n FROM QC_SCHEDULE"),
    # Setting > Patient > Physician (실측 0)
    "patient.physician": ("CONFIGURATION",
                          "SELECT COUNT(*) AS n FROM PHYSICIAN"),
}


def expected_row_count(db, page_key):
    """`ROW_COUNT_QUERIES` 로 그 페이지 목록의 DB 행 수를 구한다.

    매핑이 없거나 조회에 실패하면 `None` — 개수 증명을 생략한다는 뜻이다.
    추측한 값을 돌려주지 않는다.
    """
    spec = ROW_COUNT_QUERIES.get(page_key)
    if not spec:
        return None
    database, query = spec
    try:
        row = db.one(database, query)
    except Exception:                                      # noqa: BLE001
        return None
    return None if not row else int(row["n"])


def find_lists(ui, pages, min_rows=1, on_event=None):
    """주어진 `(group, page)` 목록을 돌며 **목록이 있는 페이지**를 찾는다.

    반환: `[{"key": "system.account", "rows": 3, "rail": ctrl, "pane": ctrl}]`

    전 페이지를 도는 비용을 피하려고 호출부가 후보 페이지만 넘기게 했다.
    """
    from core import flows

    found = []
    for group, page in pages:
        key = f"{group}.{page}"
        try:
            rail = flows.open_group_page(ui, group, page, wait=1.2)
            window = setting_values.setting_window(ui)
            pane = setting_values.pane_control(ui, rail, window=window)
            if pane is None:
                continue
            time.sleep(0.3)
            rows = visible_rows(pane)
        except Exception as exc:                           # noqa: BLE001
            if on_event:
                on_event(key, f"진입 실패: {type(exc).__name__}: {exc}")
            continue
        if len(rows) >= min_rows:
            found.append({"key": key, "rows": len(rows), "rail": rail,
                          "pane": pane})
    return found


def sweep(ui, db, pages, notches=DEFAULT_SCROLL_NOTCHES,
          settle=0.6, on_event=None, tesseract_exe=None):
    """후보 페이지들의 목록을 **행마다 상세값까지** 모아 한 번에 돌려준다.

    반환: `{"pages": {"dicom.storage": collect결과, ...},
            "skipped": {"system.general": "목록 없음"},
            "incomplete": ["qc.scheduler", ...]}`

    페이지마다 그 자리에서 열거·상세 판독까지 끝낸다. 목록을 먼저 다 찾아 두고
    나중에 다시 들어가면 **패널 컨트롤이 새로 만들어져**(2026-08-25 실측 — 같은
    rect, 다른 hwnd) 들고 있던 참조가 낡는다.
    """
    from core import flows

    out, skipped, incomplete = {}, {}, []
    for group, page in pages:
        key = f"{group}.{page}"
        try:
            rail = flows.open_group_page(ui, group, page, wait=1.2)
            window = setting_values.setting_window(ui)
            pane = setting_values.pane_control(ui, rail, window=window)
        except Exception as exc:                           # noqa: BLE001
            skipped[key] = f"진입 실패: {type(exc).__name__}: {exc}"
            continue
        if pane is None:
            skipped[key] = "콘텐츠 패널을 찾지 못했다"
            continue
        time.sleep(0.3)
        if not visible_rows(pane):
            skipped[key] = "목록 없음"
            continue
        # 장치 상태 칸은 설정이 아니라 실시간 값이라 뺀다 — 페이지별로 다르므로
        # 그 페이지의 것만 넘긴다(`setting_values.VOLATILE_CONTROLS` 주석 참고).
        result = collect(ui, pane, expected_count=expected_row_count(db, key),
                         exclude_ids=setting_values.VOLATILE_CONTROLS.get(
                             key, ()),
                         notches=notches, settle=settle,
                         tesseract_exe=tesseract_exe)
        out[key] = result
        if not result["complete"]:
            incomplete.append(key)
        if on_event:
            on_event(key, result)
    return {"pages": out, "skipped": skipped, "incomplete": incomplete}


def compare_sweep(before, after):
    """두 `sweep()` 결과를 페이지별로 대조한다.

    반환: `{"pages": {키: compare결과}, "changed_total": n,
            "only_before_pages": [...], "only_after_pages": [...],
            "compared_rows": n, "compared_items": n}`
    """
    b_pages = before.get("pages") or {}
    a_pages = after.get("pages") or {}
    pages, changed, rows, items = {}, 0, 0, 0
    for key in sorted(set(b_pages) & set(a_pages)):
        result = compare(b_pages[key], a_pages[key])
        pages[key] = result
        changed += len(result["changed"])
        rows += result["compared_rows"]
        items += result["compared_items"]
    return {"pages": pages, "changed_total": changed,
            "only_before_pages": sorted(set(b_pages) - set(a_pages)),
            "only_after_pages": sorted(set(a_pages) - set(b_pages)),
            "compared_rows": rows, "compared_items": items}
