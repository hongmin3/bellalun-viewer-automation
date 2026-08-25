# -*- coding: utf-8 -*-
r"""여러 Setting 메뉴의 값을 **바꾸고 되돌리는** 변경 세트.

`TC_Basic_WorkFlow_14`(Setting Export/Import) Step 3 — "Theme 또는 검증 대상
비파괴 설정 1개를 변경한다" — 를 **여러 메뉴로 넓히기 위한** 모듈이다.

## 왜 1개가 아니라 여러 개인가

Step 7 의 판정은 "Export 시점의 설정값으로 복원되어 있다" 이고, 이 저장소는 그것을
설정 테이블 **전수 대조**로 본다. 그런데 **바꾸지 않은 영역은 그 판정이 아무것도
증명하지 못한다** — Import 가 `TOOL_COMMON` 을 통째로 건너뛰어도, 그 테이블을
건드린 적이 없으면 Export 전후가 당연히 같아서 통과한다.

즉 **변경 범위가 곧 이 TC 의 실제 검증 범위**다. 한 테이블만 바꾸면 전수 대조라는
이름과 달리 실제로 검증되는 것은 그 한 테이블뿐이다.

그래서 서로 다른 **7개 메뉴 / 7개 설정 테이블**을 건드린다.

    System    > General       SYSTEM_COMMON.StorageWarning
    Patient   > Patient List  REGISTRATION_COMMON.AutoRefreshTime
    Display   > Overlay       OVERLAY.OverlayFontSize
    Procedure > General       PROCEDURE_COMMON.TargetExposureIndex
    Q.C.      > Setting 3D    QC_COMMON.TomoMTFThick
    DICOM     > General       DICOM_COMMON.AllowLongAcc
    Tool      > General       TOOL_COMMON.CopyImgCrop

## 일부러 **제외한** 것과 그 이유

바꿔서 되돌리지 못하면 뒤따르는 TC 가 연쇄로 무너지는 항목들이다. 판정력을 위해
위험을 지는 거래는 하지 않는다 — 위 7개로도 "Import 가 특정 설정 테이블을
건너뛴다" 는 결함은 잡힌다.

  - **Theme**(`system.general` 2227) — Viewer 전체 색이 바뀐다. 이 저장소의 판정
    다수가 브랜드 핑크 픽셀(`core/screen.radio_selected`)과 흰 배경/검은 글자 OCR
    에 의존하므로, 복원이 실패하면 무인 회귀 전체가 무너진다.
  - **Language / Date Format**(`system.region` 2243~2245) — 화면 문구가 통째로
    바뀌어 모든 OCR 판정이 죽는다.
  - **Security**(`system.security`) — 자동 로그오프·비밀번호 정책이다. 사용자
    지시가 보안 설정을 우회하지 말라고 했고, 자동 로그오프 시간을 건드리면 회귀
    중간에 로그아웃될 수 있다.
  - **DICOM Station Port / AE Title**(`dicom.general` 2435/2437) — MWL·Storage·
    Print 통신이 끊긴다. 복원 실패 시 DICOM 계열 TC 가 전부 FAIL 한다.
  - **Device > General 라디오**(2633~2640) — `DEVICE_COMMON` 의
    `GainCalPreventExposure` / `MagTablePreventExposure` 같은 **노출 인터록**이다.
    화면 문구만으로 어느 라디오가 어느 인터록인지 확정하지 못했고, 사양에 없는
    동작을 지어내지 않는다는 원칙에 따라 손대지 않는다.
  - **Study > Study Delete / Q.C. > Auto Delete** — 자동 삭제 조건이다. 되돌리지
    못한 채 조건이 맞으면 데이터가 지워진다.

## 값을 넣는 방법 (2026-08-25 실측)

숫자 Edit 에 **`ui.type_text` 는 먹지 않는다.** `Ctrl+A`+`Delete` 로 지워지기까지
하고 입력한 문자는 들어가지 않아 **빈 칸**이 된다. 네 가지를 실측 비교했다.

    A  type_text(SendInput KEYEVENTF_UNICODE)  ->  ''     실패
    B  클릭 후 raw_key(VK 0x30+숫자)             ->  '32'   성공
    C  WM_SETTEXT + Tab                        ->  '33'   화면은 바뀌나 미검증
    D  클릭 후 End+Backspace 다음 raw_key        ->  '34'   성공, DB 반영까지 확인

제품의 숫자 Edit 이 `WM_KEYDOWN` 의 가상키로 입력을 거르는 것으로 보인다.
`KEYEVENTF_UNICODE` 는 가상키 없이 `WM_CHAR` 만 만들어서 걸러진다. 그래서 이
모듈은 **VK 원시 키**로 숫자를 넣는다(`type_digits`).

## 대상 컨트롤을 고르는 방법 — ID 가 아니라 **DB 값**으로 찾는다

같은 페이지에 **같은 ctrl_id 를 가진 Edit 이 여러 개** 있다(`device.general` 의
2621/2622 가 두 줄에 반복된다). ID 만으로 `next(...)` 를 쓰면 조용히 다른 칸을
집는다 — 2026-08-25 첫 시도에서 실제로 그렇게 엉뚱한 칸을 잡아, 바꾸지도 않은
값을 바꿨다고 볼 뻔했다.

그래서 **먼저 DB 에서 현재 값을 읽고, 그 값을 표시하고 있는 Edit** 을 찾는다.
후보가 0개거나 2개 이상이면 **집지 않고 그 항목을 실패로 남긴다**(아무거나 집어
성공한 척하지 않는다).
"""

from __future__ import annotations

import time

from core import flows, screen, setting_values as sv

# `PROCEDURE_COMMON` 만 PROCEDURE DB 에 있고 나머지는 CONFIGURATION 이다.
_DB_OF = {"PROCEDURE_COMMON": "PROCEDURE"}


class ChangeError(RuntimeError):
    pass


class ChangeItem:
    """변경 세트의 한 항목."""

    __slots__ = ("key", "group", "page", "kind", "ctrl_id", "table", "column",
                 "section", "delta", "label", "spec_note", "edit_id")

    def __init__(self, key, group, page, kind, ctrl_id, table, column, section,
                 label, delta=1, spec_note="", edit_id=None):
        self.key = key
        self.group = group
        self.page = page
        self.kind = kind                 # "digits" | "slider" | "toggle"
        self.ctrl_id = ctrl_id
        self.table = table
        self.column = column
        self.section = section           # snapshot 섹션 이름
        self.label = label               # 화면에 보이는 항목 이름
        self.delta = delta
        self.spec_note = spec_note
        #: 슬라이더가 값을 표시하는 Edit. 한 칸 움직일 때마다 **이 값이 실제로
        #: 바뀌었는지 확인**하는 데 쓴다(`_nudge_slider` 주석 참고).
        self.edit_id = edit_id

    def __repr__(self):                                # pragma: no cover
        return "<ChangeItem %s>" % self.key


#: 실제 변경 세트. 위 docstring 의 표와 같은 순서다.
#: `ctrl_id` 와 DB 컬럼 대응은 2026-08-25 실측으로 확정했다
#: (`work/probe_radio.log`, `work/probe_typing.py` 실행 결과).
CHANGE_PLAN = (
    ChangeItem("system.general", "system", "general", "slider", 2230,
               "SYSTEM_COMMON", "StorageWarning", "system_common",
               "Storage Free Space Alarm > Warning", edit_id=2232,
               spec_note="슬라이더 2230 의 자식 2(증가)를 눌러 1 올린다. "
                         "값은 같은 줄의 Edit 2232 에 표시되고, 한 칸마다 그 "
                         "값이 실제로 바뀌었는지 확인한다."),
    ChangeItem("patient.patient_list", "patient", "patient_list", "digits",
               2331, "REGISTRATION_COMMON", "AutoRefreshTime",
               "registration_common", "Patient List > Auto refresh time",
               spec_note="2026-08-25 실측으로 30 -> 34 변경이 "
                         "REGISTRATION_COMMON.AutoRefreshTime 에 반영되는 것을 "
                         "확인했다."),
    ChangeItem("display.overlay", "display", "overlay", "digits", 2393,
               "OVERLAY", "OverlayFontSize", "overlay",
               "Overlay > Overlay font size"),
    ChangeItem("procedure.general", "procedure", "general", "digits", 2546,
               "PROCEDURE_COMMON", "TargetExposureIndex", "procedure_common",
               "Procedure General > Target Exposure Index (2D)",
               spec_note="2026-08-25 실측으로 100 -> 101 변경이 "
                         "PROCEDURE_COMMON.TargetExposureIndex 에 반영되는 것을 "
                         "확인했다."),
    ChangeItem("qc.setting_3d", "qc", "setting_3d", "digits", 2712,
               "QC_COMMON", "TomoMTFThick", "qc_common",
               "Q.C. Setting 3D > MTF thickness"),
    ChangeItem("dicom.general", "dicom", "general", "toggle", 2450,
               "DICOM_COMMON", "AllowLongAcc", "dicom_common",
               "DICOM General > Allow long accession number",
               spec_note="같은 줄의 라디오 쌍은 2450=Yes / 2449=No 다"
                         "(실측: 기본값 No 선택). 0 -> 1 로 바꾼다."),
    ChangeItem("tool.general", "tool", "general", "toggle", 2354,
               "TOOL_COMMON", "CopyImgCrop", "tool_common",
               "Tool General > Copy image with crop",
               spec_note="체크박스라 같은 컨트롤을 눌러 켜고 끈다."),
)

#: 토글 항목이 값을 되돌릴 때 눌러야 하는 **짝 컨트롤**.
#: 라디오는 같은 것을 다시 눌러도 해제되지 않으므로 짝을 눌러야 한다.
#: 체크박스는 짝이 없다(같은 컨트롤을 다시 누른다).
TOGGLE_PARTNER = {2450: 2449}


# --- 저수준 조작 -------------------------------------------------------
def type_digits(ui, ctrl, text, settle=0.25):
    """숫자 Edit 에 **VK 원시 키**로 값을 넣는다.

    `ui.type_text` 는 이 컨트롤들에서 실패한다(모듈 docstring 의 실측표 참고).

    `keybd_event` 는 창을 지정할 수 없고 **그 순간 최전면인 창**으로 들어가므로,
    보내기 전에 Viewer 가 앞에 있는지 확인한다. `ui.type_text` 를 우회하는
    경로라 그쪽 가드를 물려받지 못한다.
    """
    if not str(text).isdigit():
        raise ChangeError("숫자만 넣을 수 있습니다: %r" % (text,))
    ui.require_front("설정값 입력")
    ui.click(ctrl, settle=0.25)
    ui.key_combo(0x11, 0x41)                 # Ctrl+A
    ui.raw_key(0x2E)                         # Delete
    for ch in str(text):
        ui.raw_key(0x30 + int(ch), settle=0.06)
    time.sleep(settle)


def goto(ui, group, page):
    """Setting > <group> > <page> 로 이동하고 (패널, 패널하위 컨트롤)을 준다.

    `flows.open_setting` 은 이미 열려 있으면 누르지 않는다(멱등).
    """
    flows.open_setting(ui, wait=2.5)
    flows.open_setting_group(ui, group, wait=1.2)
    rail = sv._open_page(ui, flows.setting_pages(group)[page],
                         "%s 설정 '%s'" % (group, page))
    pane = sv.pane_control(ui, rail, window=sv.setting_window(ui))
    if pane is None:
        raise ChangeError("%s.%s 의 콘텐츠 패널을 찾지 못했습니다." % (group, page))
    controls, _ = sv._wait_page_settled(ui, pane, sv.pane_controls(pane))
    return pane, controls


def db_value(db, item):
    """항목이 가리키는 DB 컬럼의 현재 값."""
    which = _DB_OF.get(item.table, "CONFIGURATION")
    row = db.one(which, "SELECT [%s] FROM %s" % (item.column, item.table))
    if not row or row.get(item.column) is None:
        raise ChangeError("%s.%s 을 읽지 못했습니다(행 없음)."
                          % (item.table, item.column))
    return row[item.column]


def find_edit_by_value(ui, controls, value):
    """**표시된 값**으로 Edit 을 찾는다. 후보가 하나가 아니면 예외.

    같은 ctrl_id 를 가진 Edit 이 한 페이지에 여러 개 있으므로 ID 로 고르면
    조용히 다른 칸을 집는다(모듈 docstring 참고).
    """
    want = str(value).strip()
    hits = [c for c in controls
            if c.cls == "Edit" and c.visible
            and (ui.get_text(c) or "").strip() == want]
    if len(hits) != 1:
        raise ChangeError(
            "값 %r 을 표시하는 Edit 이 %d개입니다(1개여야 고를 수 있습니다)."
            % (want, len(hits)))
    return hits[0]


def _commit(ui):
    flows.setting_update(ui, wait=1.8)
    flows.confirm_setting_dialog(ui)


def _wait_db(db, item, want, timeout=15):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = db_value(db, item)
        except ChangeError:
            last = None
        if last is not None and str(last) == str(want):
            return True, last
        time.sleep(0.8)
    return False, last


def _slider_shown(ui, pane, edit_id):
    """슬라이더가 값을 표시하는 Edit 의 현재 숫자. 못 읽으면 None."""
    hits = [c for c in sv.pane_controls(pane)
            if c.ctrl_id == edit_id and c.visible and c.cls == "Edit"]
    if len(hits) != 1:
        return None
    text = (ui.get_text(hits[0]) or "").strip()
    return int(text) if text.isdigit() else None


def _nudge_slider(ui, pane, controls, item, before, target, attempts=4,
                  timeout=6):
    """슬라이더의 감소/증가 버튼을 눌러 목표값까지 옮긴다(자식 1=감소 / 2=증가).

    **한 칸 누를 때마다 화면 값이 실제로 바뀌었는지 확인하고, 안 바뀌면 다시
    누른다.** 이 제품은 화면 전환 직후 첫 클릭을 삼키는 일이 있다(같은 이유로
    `viewer_processing.add_view_position` 도 `+` 를 최대 3번 누른다).

    2026-08-25 실측: 확인 없이 한 번만 누르는 판본으로 WF_14 를 돌렸더니, 다른
    6개 항목은 다 바뀌었는데 **Export 직후 첫 항목인 이것만 안 바뀌었다.**
    조작 후 확인 없는 코드를 만들지 않는다는 운영 지침 11절 그대로다.
    """
    from core.ui import children

    slider = next((c for c in controls
                   if c.ctrl_id == item.ctrl_id and c.visible), None)
    if slider is None:
        raise ChangeError("슬라이더 %d 를 찾지 못했습니다." % item.ctrl_id)
    want_id = 2 if int(target) > int(before) else 1
    btn = next((c for c in children(slider.hwnd, 3)
                if c.ctrl_id == want_id and c.visible
                and c.rect[2] - c.rect[0] > 10), None)
    if btn is None:
        raise ChangeError(
            "슬라이더 %d 의 %s 버튼(%d)을 찾지 못했습니다."
            % (item.ctrl_id, "증가" if want_id == 2 else "감소", want_id))
    for _ in range(abs(int(target) - int(before))):
        shown = _slider_shown(ui, pane, item.edit_id) if item.edit_id else None
        if shown is None:
            # 표시 Edit 을 못 읽으면 확인할 방법이 없다. 한 번만 누르고
            # 최종 판정은 `_wait_db` 에 맡긴다(성공한 척하지는 않는다).
            ui.click(btn, settle=0.5)
            continue
        for attempt in range(attempts):
            ui.click(btn, settle=0.4)
            end = time.time() + timeout
            while time.time() < end:
                now = _slider_shown(ui, pane, item.edit_id)
                if now is not None and now != shown:
                    break
                time.sleep(0.3)
            else:
                continue
            break
        else:
            raise ChangeError(
                "슬라이더 %d 를 %d번 눌렀는데 표시값이 %s 에서 바뀌지 "
                "않았습니다." % (item.ctrl_id, attempts, shown))


def _click_toggle(ui, controls, item, before, target):
    """라디오/체크박스를 눌러 값을 바꾼다.

    라디오는 **짝 컨트롤**을 눌러야 한다 — 이미 선택된 라디오를 다시 눌러도
    해제되지 않는다. 체크박스는 짝이 없어 같은 컨트롤을 다시 누른다.
    """
    del before
    ctrl_id = item.ctrl_id
    partner = TOGGLE_PARTNER.get(item.ctrl_id)
    if partner is not None and int(target) == 0:
        ctrl_id = partner
    hits = [c for c in controls if c.ctrl_id == ctrl_id and c.visible]
    if len(hits) != 1:
        raise ChangeError("토글 컨트롤 %d 가 %d개입니다." % (ctrl_id, len(hits)))
    ui.click(hits[0], settle=0.5)


# --- 항목 단위 적용 / 복원 ---------------------------------------------
def set_value(ui, db, item, target):
    """항목을 `target` 으로 맞추고 **DB 로 확인**한다.

    반환: {"ok":bool, "before":.., "target":.., "actual":.., "how":..}
    """
    before = db_value(db, item)
    if str(before) == str(target):
        return {"ok": True, "before": before, "target": target,
                "actual": before, "how": "이미 목표값"}
    pane, controls = goto(ui, item.group, item.page)
    how = item.kind
    if item.kind == "digits":
        ctrl = find_edit_by_value(ui, controls, before)
        type_digits(ui, ctrl, str(target))
    elif item.kind == "slider":
        _nudge_slider(ui, pane, controls, item, before, target)
        how = "슬라이더 감소/증가"
    elif item.kind == "toggle":
        _click_toggle(ui, controls, item, before, target)
        how = "라디오/체크박스"
    else:
        raise ChangeError("알 수 없는 변경 방식: %s" % item.kind)
    _commit(ui)
    ok, actual = _wait_db(db, item, target)
    return {"ok": ok, "before": before, "target": target, "actual": actual,
            "how": how}


def toggled_target(current):
    """토글 항목의 반대값."""
    return 0 if int(current) else 1


def plan_targets(db, plan=CHANGE_PLAN):
    """각 항목의 현재값과 바꿀 목표값을 계산한다(조작 없음)."""
    out = []
    for item in plan:
        try:
            before = db_value(db, item)
        except ChangeError as exc:
            out.append({"item": item, "error": str(exc)})
            continue
        if item.kind == "toggle":
            target = toggled_target(before)
        else:
            target = int(before) + item.delta
        out.append({"item": item, "before": before, "target": target})
    return out


def apply_all(ui, db, plan=CHANGE_PLAN, on_event=None):
    """변경 세트를 적용한다. **한 항목이 실패해도 나머지를 계속한다.**

    한 항목이 안 되면 거기서 멈추는 게 아니라, 되는 만큼 바꾸고 무엇이 안 됐는지
    남기는 편이 낫다 — 이 TC 의 목적은 "여러 테이블을 건드린 뒤 Import 가 전부
    되돌리는가" 이고, 7개 중 6개만 바뀌어도 그 판정은 여전히 성립한다. 대신
    **몇 개가 실제로 바뀌었는지**를 판정에 남겨, 0개가 바뀐 채 통과하는 일은
    없게 한다.

    반환: [{"key":.., "label":.., "section":.., "column":.., "before":..,
            "target":.., "actual":.., "ok":bool, "error":str|None}, ...]
    """
    results = []
    for entry in plan_targets(db, plan):
        item = entry["item"]
        rec = {"key": item.key, "label": item.label, "section": item.section,
               "column": "%s.%s" % (item.table, item.column), "ok": False,
               "error": entry.get("error")}
        if rec["error"]:
            results.append(rec)
            if on_event:
                on_event("%s: 준비 실패 %s" % (item.key, rec["error"]))
            continue
        rec["before"] = entry["before"]
        rec["target"] = entry["target"]
        try:
            res = set_value(ui, db, item, entry["target"])
        except Exception as exc:                       # noqa: BLE001
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        else:
            rec.update(ok=res["ok"], actual=res["actual"], how=res["how"])
            if not res["ok"]:
                rec["error"] = ("DB 반영 안 됨(기대 %s, 실제 %s)"
                                % (res["target"], res["actual"]))
        results.append(rec)
        if on_event:
            on_event("%s: %s -> %s ok=%s"
                     % (item.key, rec.get("before"), rec.get("actual"),
                        rec["ok"]))
    return results


def restore_all(ui, db, applied, plan=CHANGE_PLAN, on_event=None):
    """`apply_all` 이 바꾼 값을 **원래 값으로 되돌린다.**

    Import 가 정상이면 이미 원래 값이므로 대부분 "이미 원래 값" 으로 끝난다.
    Import 전에 중단됐을 때를 위한 안전망이다 — 2026-08-25 에 조사 스크립트가
    강제 종료되면서 `TargetExposureIndex` 가 101 로 남았고, 그 상태로 다음 실행이
    시작돼 값을 잘못 읽었다. 그런 잔여물을 남기지 않는다.

    반환: [{"key":.., "ok":bool, "want":.., "actual":.., "error":..}, ...]
    """
    by_key = {i.key: i for i in plan}
    out = []
    for rec in applied:
        item = by_key.get(rec["key"])
        if item is None or "before" not in rec:
            continue
        want = rec["before"]
        entry = {"key": rec["key"], "want": want}
        try:
            now = db_value(db, item)
            if str(now) == str(want):
                entry.update(ok=True, actual=now, note="이미 원래 값")
            else:
                res = set_value(ui, db, item, want)
                entry.update(ok=res["ok"], actual=res["actual"])
                if not res["ok"]:
                    entry["error"] = ("원복 실패(기대 %s, 실제 %s)"
                                      % (want, res["actual"]))
        except Exception as exc:                       # noqa: BLE001
            entry.update(ok=False, error="%s: %s" % (type(exc).__name__, exc))
        out.append(entry)
        if on_event:
            on_event("원복 %s: ok=%s %s"
                     % (rec["key"], entry["ok"], entry.get("actual")))
    return out


def summarize(applied):
    """판정에 쓸 요약. 몇 개가 실제로 바뀌었고 어떤 섹션을 덮었는가."""
    ok = [r for r in applied if r.get("ok")]
    return {
        "요청": len(applied),
        "적용됨": len(ok),
        "덮은 설정테이블": sorted({r["section"] for r in ok}),
        "실패": [{"항목": r["key"], "사유": r.get("error")}
               for r in applied if not r.get("ok")],
        "변경 내역": [{"메뉴": r["key"], "항목": r["label"],
                   "컬럼": r["column"],
                   "값": "%s -> %s" % (r.get("before"), r.get("actual"))}
                  for r in ok],
    }


def close_setting(ui):
    """Setting 창을 닫는다(변경 저장 확인 팝업이 뜨면 저장하지 않음)."""
    if not flows.setting_is_open(ui):
        return True
    win = ui.main_window()
    top = win.rect[1] if win else 0
    close = [c for c in ui.by_id(4) if c.visible and c.rect[1] < top + 100]
    if close:
        ui.click(close[0], settle=1.0)
    flows.confirm_config_save(ui, save=False, timeout=3)
    return not flows.setting_is_open(ui)


def evidence_shot(ui, path):
    """현재 Setting 화면을 증거로 남긴다(판정에는 쓰지 않는다)."""
    win = sv.setting_window(ui) or ui.main_window()
    if win is None:
        return None
    screen.grab(win.rect, path=path)
    return path
