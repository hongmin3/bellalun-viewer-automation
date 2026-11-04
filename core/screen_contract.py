# -*- coding: utf-8 -*-
"""로그인 직후 Patient 화면의 화면 계약(screen contract).

Viewer 판이 바뀌어 핵심 Control ID가 사라지거나 바뀌면, 이어지는 TC는 버튼을
찾지 못해 줄줄이 FAIL로 찍힌다. 그 FAIL은 해당 기능의 결함이 아니라 "화면 구조가
자동화가 아는 것과 다르다"는 한 가지 사실이다. 그래서 로그인해 Patient 화면에
도착한 직후 핵심 컨트롤이 모두 보이는지 먼저 확인하고, 하나라도 없으면 호출부가
이후 TC를 BLOCKED로 기록한다.

ID는 새로 정하지 않고 `core.flows`의 실측 상수만 쓴다.
- Patient 화면 랜드마크: `flows.known_screen`/`ensure_patient_screen`이 Patient
  화면 판별에 쓰는 New Patient 탭과, 그 옆 Patient List 탭.
- 상태바 메인 메뉴 버튼(2015): Setting·DICOM·Examine 진입이 모두 이 버튼에서 시작한다.

넣지 않은 것: Setting 아이콘(`MAIN_MENU["setting"]`)은 메인 메뉴를 펼쳐야 보이고,
`EXAMINE` 컨트롤은 Examine 화면에서만 보이므로 로그인 직후 계약이 아니다.
"""

from __future__ import annotations

from core import flows

CORE_CONTROLS = (
    flows.PATIENT["tab_patient_list"],   # 2284
    flows.PATIENT["tab_new_patient"],    # 2285
    flows.STATUS_BAR["menu"],            # 2015
)

CONTROL_LABELS = {
    flows.PATIENT["tab_patient_list"]: "Patient List 탭",
    flows.PATIENT["tab_new_patient"]: "New Patient 탭",
    flows.STATUS_BAR["menu"]: "메인 메뉴 버튼",
}


def check(ui, required=CORE_CONTROLS):
    """`required`의 Control ID가 모두 보이는지. UI는 읽기만 한다(클릭 없음).

    반환: `{"ok": bool, "missing": [id...], "checked": [id...]}`.
    """
    checked, missing = [], []
    for cid in required:
        checked.append(cid)
        try:
            hits = ui.by_id(cid) or []
        except Exception:
            hits = []
        if not any(getattr(c, "visible", False) for c in hits):
            missing.append(cid)
    return {"ok": not missing, "missing": missing, "checked": checked}


def describe(result):
    if result.get("ok"):
        return f"핵심 컨트롤 {len(result.get('checked') or [])}개 모두 표시"
    names = [f"{cid}({CONTROL_LABELS.get(cid, '?')})" for cid in result.get("missing") or []]
    return "화면 계약 불일치 — 보이지 않는 컨트롤: " + ", ".join(names)


def to_item(result):
    """사전 점검 항목 형식(`core.env_preflight`)으로 바꾼다. 불일치는 BLOCK."""
    return {
        "key": "screen_contract",
        "label": "화면 계약(로그인 직후 Patient 화면)",
        "level": "OK" if result.get("ok") else "BLOCK",
        "actual": describe(result),
        "expected": "표시: " + ", ".join(str(c) for c in result.get("checked") or []),
        "blocks_run": not result.get("ok"),
        "hint": ("" if result.get("ok") else
                 "Viewer 판이 바뀌었거나 로그인 뒤 다른 화면에 있습니다. 이후 TC는 BLOCKED로 "
                 "기록하고 Control ID를 다시 실측하세요."),
    }
