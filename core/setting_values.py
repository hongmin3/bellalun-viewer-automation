# -*- coding: utf-8 -*-
r"""Setting 화면의 **값**을 컨트롤 ID 기준으로 읽어 항목 단위로 비교한다.

`TC_Basic_WorkFlow_14`(Setting Export/Import) Expected 7 — "Export 시점의
설정값으로 복원되어 있다" — 를 **이미지 비교 없이** 판정하기 위한 모듈이다.

## 왜 이미지 비교를 주 판정으로 쓰지 않는가

사내에 같은 목적의 선행 도구(Setting 화면 캡처-비교 프로그램)가 있다. 그 도구는
`pyautogui` 절대좌표 + Calibration 으로 각 Setting 페이지를 캡처해 **이미지끼리**
비교한다(도구와 문서 위치는 사내 공유 폴더에 있다 — 이 저장소는 공개 저장소라
경로를 적지 않는다).
그 문서의 회고가 스스로 두 가지 오탐을 적어 두었다.

  - "텍스트 커서가 캡처가 되면 같은 Setting 값을 가지고 있지만 Fail 로 인식"
  - "Setting 창 로딩이 늦어진 Fail composite Image"

둘 다 **픽셀을 값의 대리물로 쓴 데서** 나온다. 값을 직접 읽으면 커서도 로딩도
판정에 섞이지 않는다.

## 이 모듈이 읽는 것 (2026-08-21 실측으로 확정)

| 대상 | 읽는 방법 | 정확도 |
|---|---|---|
| `Edit` (숫자/문자 입력) | `WM_GETTEXT` | **정확** (`2240` -> `'10'`) |
| 콤보 (커스텀) | `WM_GETTEXT` | 앞 8자로 잘리지만 **결정적** (`2241` -> `'Allow on'`). 값 대조에는 충분하고, 보고용 전체 문구는 OCR 로 보강 |
| `RadioButton` / `CheckBox` (커스텀) | `screen.radio_selected_in` — 패널을 한 번만 캡처해 그 안의 픽셀로 판독 | 3-state (True/False/None) |
| 목록(계정·SCP·Reject 사유 등) | 읽지 않음 | **DB 전수 대조가 담당** |

**커스텀 컨트롤은 `BM_GETCHECK`/`BM_GETSTATE` 에 응답하지 않는다** — 라디오 8개에
보내 보니 전부 `0` 을 돌려줬다(2026-08-21 실측). 그래서 라디오/체크박스의 *화면*
상태는 픽셀 말고는 읽을 방법이 없다. 대신 그 값들의 *저장된* 상태는
`CONFIGURATION`/`ACCOUNT`/`PROCEDURE` 테이블에 정확히 들어 있다.

## 판정에서의 위치 (중요)

- **주 판정 = DB 설정 테이블 전수 대조**(`snapshot.config_identical`).
  좌표도 픽셀도 OCR 도 개입하지 않는 결정적 근거다. 사양서1 "60. Setting
  Export/Import" 가 Export 대상을 "Study 정보를 제외한 모든 설정 정보
  (DB / sql file)" 로 정의하므로 이것이 사양에 가장 가깝다.
- **보조 판정 = 이 모듈의 화면 값 대조**. "DB 는 돌아왔는데 화면이 안 따라오는"
  경우를 잡고, 차이가 난 **페이지와 컨트롤 ID** 를 바로 알려 준다.
"""

from __future__ import annotations

import os
import time

from core import flows, screen, uitext

# 커스텀 컨트롤이 `WM_GETTEXT` 로 돌려주는 **일반 이름**들. 값이 아니라 종류다.
# 이 목록에 없는 문자열이 나오면 그 컨트롤은 "값을 표시하고 있다"는 뜻이다
# (콤보의 현재 값이 대표적 — `2227` -> 'Pure Whi', `2241` -> 'Allow on').
GENERIC_TEXTS = {
    "", "StaticText", "TextButton", "IconButton", "RadioButton", "CheckBox",
    "GroupBox", "Slider", "ItemList", "ItemWnd", "Scroll", "PngViewer",
    "PathView", "SystemThumbnail", "SystemThumbnailItem", "ListCtrl",
    "ListItem", "ExpandButton", "CircleButton", "TransparentBackIconButton",
    "MessageDisplayPanel", "SettingMenuItem", "SettingMenuGroupItem",
    "FrameTransparent", "ComboBoxEx32", "Static", "Button", "ToolbarWindow32",
    "SysListView32", "SysHeader32", "SHELLDLL_DefView", "FolderView",
}

RADIO_TEXTS = {"RadioButton", "CheckBox"}

# 콘텐츠 패널 후보의 최소 크기. Setting 창(실측 1766x978) 안의 콘텐츠 패널은
# 1458x820 이다(2026-08-21, 1920x1080/96DPI).
_PANE_MIN_W = 700
_PANE_MIN_H = 400


class SettingValueError(RuntimeError):
    pass


def content_pane(ui, rail_ctrl, controls=None):
    """Setting 콘텐츠 패널의 rect 를 **컨트롤에서** 구한다.

    좌측 페이지 레일(`rail_ctrl`) 오른쪽에 있는 `#32770` 자식 중 가장 큰 것이
    콘텐츠 패널이다(2026-08-21 실측: 레일 항목 rect x 168~375, 패널 rect
    382,85 ~ 1840,905). 절대 좌표를 박지 않으므로 창 위치가 바뀌어도 따라간다.

    `controls` 를 주면 그 목록을 쓴다 — `ui.controls()` 는 한 번에 약 0.57초
    걸리므로(2026-08-21 실측) 한 페이지에서 여러 번 부르면 그것만으로 수십 초가
    쌓인다. 호출부가 한 번 열거해 돌려 쓰게 한다.
    """
    rail_right = rail_ctrl.rect[2]
    best = None
    for c in (controls if controls is not None else ui.controls(max_depth=6)):
        if c.cls != "#32770" or not c.visible:
            continue
        l, t, r, b = c.rect
        if l < rail_right:
            continue
        w, h = r - l, b - t
        if w < _PANE_MIN_W or h < _PANE_MIN_H:
            continue
        if best is None or w * h > best[0]:
            best = (w * h, (l, t, r, b))
    if best is None:
        raise SettingValueError(
            "Setting 콘텐츠 패널(#32770)을 찾지 못했습니다. "
            f"레일 오른쪽(x>{rail_right})에 {_PANE_MIN_W}x{_PANE_MIN_H} 이상인 "
            "패널이 없습니다.")
    return best[1]


def read_page(ui, pane, ocr_combos=False, tesseract_exe=None, controls=None,
              pane_image=None):
    """한 페이지의 컨트롤 값을 읽는다.

    반환: {"<ctrl_id>@<x>,<y>": {"kind":.., "value":..}, ...}

    키에 좌표를 붙이는 이유: 같은 페이지에 **같은 ID 가 여러 개** 있다
    (`1001` StaticText 가 라벨마다 반복된다). ID 만으로는 구분이 안 되므로
    컨트롤의 좌상단을 **패널 기준 상대 좌표**로 붙여 구분한다. 절대 좌표가
    아니므로 창 위치가 바뀌어도 같은 키가 나온다.

    `ocr_combos` 기본값이 `False` 인 이유: 콤보의 `WM_GETTEXT` 는 앞 8자로
    잘리지만 **결정적**이라 값 대조에는 그것으로 충분하다(실측: `2227` ->
    'Pure Whi', `2241` -> 'Allow on'). OCR 은 호출당 약 0.27초라 56개 페이지
    두 회차에 붙이면 수 분이 더 든다. 사람이 볼 전체 문구는 같은 폴더에 남는
    페이지 캡처로 확인한다.
    """
    pl, pt, pr, pb = pane
    # 라디오/체크박스는 컨트롤마다 캡처하지 않고 **패널을 한 번 캡처해** 그 안에서
    # 읽는다. `screen.radio_selected` 는 호출마다 전체 화면을 뜨므로 페이지당
    # 라디오가 6개면 전체 화면 캡처가 6번 일어난다(56페이지 x 2회차면 수 분).
    if pane_image is None:
        pane_image = screen.grab(pane)
    out = {}
    for c in (controls if controls is not None else ui.controls(max_depth=8)):
        if not c.visible:
            continue
        l, t, r, b = c.rect
        if l < pl or t < pt or r > pr or b > pb:
            continue
        if r - l < 8 or b - t < 8:
            continue
        key = f"{c.ctrl_id}@{l - pl},{t - pt}"
        text = c.text or ""
        if c.cls == "Edit":
            out[key] = {"kind": "edit", "value": (ui.get_text(c) or "").strip()}
        elif text in RADIO_TEXTS:
            out[key] = {"kind": "radio",
                        "value": screen.radio_selected_in(
                            pane_image, (pl, pt), c)}
        elif text not in GENERIC_TEXTS:
            entry = {"kind": "value_text", "value": text}
            if ocr_combos:
                try:
                    entry["ocr"] = uitext.ocr(c, tesseract_exe)
                except Exception as exc:               # noqa: BLE001
                    entry["ocr"] = f"<ocr err {exc}>"
            out[key] = entry
    return out


def read_all(ui, groups=None, ocr_combos=False, tesseract_exe=None,
             capture_dir=None, on_event=None):
    """Setting 전 그룹/페이지를 순회하며 컨트롤 값을 읽는다.

    `capture_dir` 를 주면 페이지 캡처도 함께 남긴다(사람이 눈으로 볼 증거).
    캡처는 **판정에 쓰지 않는다** — 판정은 값과 DB 다.

    반환: {"pages": {"system.general": {키: {...}}}, "missing": {...},
           "shots": {"system.general": png}, "pane": [l,t,r,b]}
    """
    pages, missing, shots = {}, {}, {}
    pane = None
    if capture_dir:
        os.makedirs(capture_dir, exist_ok=True)
    for group in (groups or list(flows.SETTING_GROUPS)):
        try:
            flows.open_setting(ui, wait=2.5)
            flows.open_setting_group(ui, group, wait=2.0)
        except Exception as exc:                       # noqa: BLE001
            for name in flows.setting_pages(group):
                missing[f"{group}.{name}"] = f"그룹 진입 실패: {exc}"
            continue
        for name, ctrl_id in flows.setting_pages(group).items():
            key = f"{group}.{name}"
            try:
                rail = _open_page(ui, ctrl_id, f"{group} 설정 '{name}'")
            except Exception as exc:                   # noqa: BLE001
                missing[key] = str(exc)
                continue
            # 페이지가 그려질 때까지 기다린 뒤 **그때 열거한 목록을 돌려 쓴다.**
            # `ui.controls()` 는 호출당 약 0.57초라(실측) 한 페이지에서 여러 번
            # 부르면 그것만으로 회귀가 수십 분 길어진다.
            controls = ui.controls(max_depth=8)
            try:
                pane = content_pane(ui, rail, controls=controls)
            except Exception as exc:                   # noqa: BLE001
                missing[key] = str(exc)
                continue
            controls, settled = _wait_page_settled(ui, pane, controls)
            pane_image = screen.grab(pane)
            pages[key] = read_page(ui, pane, ocr_combos=ocr_combos,
                                   tesseract_exe=tesseract_exe,
                                   controls=controls, pane_image=pane_image)
            if capture_dir:
                path = os.path.join(capture_dir, f"{key}.png")
                pane_image.save(path)
                shots[key] = path
            if on_event:
                on_event(f"{key}: {len(pages[key])}개 값 settled={settled}")
    return {"pages": pages, "missing": missing, "shots": shots,
            "pane": list(pane) if pane else None}


def _open_page(ui, ctrl_id, what):
    """페이지 레일 항목을 누른다. `flows._click_setting_control` 의 경량 판본.

    공용 헬퍼는 클릭 후 `settle=1.0` + `wait` 로 고정 대기를 한다. 56개 페이지를
    두 회차 도는 이 모듈에서는 그 고정 대기만으로 2분 이상이 쌓인다. 여기서는
    짧게 누르고 **`_wait_page_settled` 가 실제로 그려질 때까지 기다린다** —
    고정 대기를 상태 기반 대기로 바꾼 것이므로 판정 안전성은 떨어지지 않는다.
    """
    hits = [c for c in ui.controls(max_depth=7)
            if c.ctrl_id == ctrl_id and c.visible
            and c.rect[2] - c.rect[0] > 20]
    if not hits:
        raise SettingValueError(
            f"{what}(ID {ctrl_id})을 찾지 못했습니다. 현재 화면을 확인하십시오.")
    ui.click(hits[0], settle=0.3)
    return hits[0]


def _in_pane(controls, pane):
    pl, pt, pr, pb = pane
    return [c for c in controls
            if c.visible and c.rect[0] >= pl and c.rect[1] >= pt
            and c.rect[2] <= pr and c.rect[3] <= pb]


def _wait_page_settled(ui, pane, controls, tries=4, gap=0.25):
    """**콘텐츠 패널 안의** 컨트롤 수가 두 번 연속 같아질 때까지 기다린다.

    반환: (마지막으로 열거한 컨트롤 목록, 안정화 여부).

    패널 밖을 세면 안정화되지 않는다 — 상태바의 `MessageDisplayPanel` 과 시계가
    계속 바뀌기 때문이다. 2026-08-21 첫 실행에서 이것 때문에 매 페이지가 최대
    시도(4회)를 다 소모해 페이지당 약 3초를 더 썼다. 고정 대기를 쓰지 않되,
    **판정에 쓰는 영역만** 안정화 기준으로 삼는다.
    """
    prev_n = len(_in_pane(controls, pane))
    prev = controls
    for _ in range(tries):
        time.sleep(gap)
        cs = ui.controls(max_depth=8)
        n = len(_in_pane(cs, pane))
        if n == prev_n and n > 0:
            return cs, True
        prev_n, prev = n, cs
    return prev, False


#: 컨트롤 위치가 회차 사이에 이만큼(px)까지 흔들려도 같은 컨트롤로 본다.
#  2026-08-21 WF_14 실측: `patient.general` 의 `2303` 이 x=595 -> 594 로 **1px**
#  움직여, 좌표를 넣은 키가 서로 안 맞아 "한쪽에만 있음" 두 건으로 잡혔다.
#  1px 배치 흔들림을 설정 차이로 보고하면 안 된다.
POSITION_TOLERANCE = 8


def _pair_keys(before_page, after_page):
    """두 회차의 컨트롤 키를 짝짓는다.

    1) 키가 정확히 같으면 그대로 짝짓는다.
    2) 남은 것끼리는 **같은 컨트롤 ID + 가장 가까운 위치**(허용 오차
       `POSITION_TOLERANCE`)로 짝짓는다.
    3) 그래도 남으면 진짜로 한쪽에만 있는 것이다.

    반환: (짝지은 [(b_key, a_key)], b 에만 남은 키, a 에만 남은 키)
    """
    def parse(key):
        cid, _, pos = key.partition("@")
        try:
            x, _, y = pos.partition(",")
            return int(cid), (int(x), int(y))
        except ValueError:
            return int(cid) if cid.isdigit() else cid, (0, 0)

    pairs = []
    left = [k for k in before_page if k not in after_page]
    right = [k for k in after_page if k not in before_page]
    for k in before_page:
        if k in after_page:
            pairs.append((k, k))

    for bk in list(left):
        bcid, (bx, by) = parse(bk)
        best, best_d = None, None
        for ak in right:
            acid, (ax, ay) = parse(ak)
            if acid != bcid:
                continue
            d = abs(ax - bx) + abs(ay - by)
            if d <= POSITION_TOLERANCE and (best_d is None or d < best_d):
                best, best_d = ak, d
        if best is not None:
            pairs.append((bk, best))
            left.remove(bk)
            right.remove(best)
    return pairs, left, right


def compare(before, after):
    """두 회차의 값을 항목 단위로 비교한다.

    반환:
      {
        "compared_pages": int, "compared_items": int,
        "changed": [{"page":.., "control":.., "kind":.., "pre":.., "post":..}],
        "only_before": [...], "only_after": [...],
        "unreadable": [...],        # radio 판독이 None 이라 비교 못 한 항목
        "jitter_matched": int,      # 1px 배치 흔들림을 흡수해 짝지은 항목 수
        "missing_pages": {...},
      }
    """
    bp, ap = before["pages"], after["pages"]
    changed, only_b, only_a, unreadable = [], [], [], []
    items = jitter = 0
    common = sorted(set(bp) & set(ap))
    for page in common:
        b, a = bp[page], ap[page]
        pairs, left, right = _pair_keys(b, a)
        only_b.extend(f"{page}:{k}" for k in left)
        only_a.extend(f"{page}:{k}" for k in right)
        for key, akey in sorted(pairs):
            if key != akey:
                jitter += 1
            items += 1
            bv, av = b[key], a[akey]
            if bv["kind"] == "radio" and (bv["value"] is None
                                          or av["value"] is None):
                unreadable.append(f"{page}:{key}")
                continue
            if bv["value"] != av["value"]:
                changed.append({"page": page, "control": key,
                                "kind": bv["kind"], "pre": bv["value"],
                                "post": av["value"],
                                "pre_ocr": bv.get("ocr"),
                                "post_ocr": av.get("ocr")})
    return {"compared_pages": len(common), "compared_items": items,
            "changed": changed, "only_before": only_b, "only_after": only_a,
            "unreadable": unreadable, "jitter_matched": jitter,
            "missing_pages": {**before.get("missing", {}),
                              **after.get("missing", {})}}
