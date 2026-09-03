# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_13 — 계정 추가·수정 및 로그인.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.

체크리스트 원문 (변경 금지)
  Precondition
    서비스 또는 관리자 계정으로 로그인되어 있다.
  Step
    1. Setting > System > Account에서 TEST_USER_FLOW 계정을 추가한다.
    2. 계정의 허용 권한을 설정한다.
    3. 계정 정보를 수정한다.
    4. 로그오프한다.
    5. TEST_USER_FLOW 계정으로 로그인한다.
    6. 설정한 권한에 따른 메뉴 접근 상태를 확인한다.
  Expected Result
    1. 계정이 저장된다.
    2. 권한 설정이 저장된다.
    3. 수정한 계정 정보가 저장된다.
    4. 로그인 화면이 표시되고 이전 사용자 정보가 남지 않는다.
    5. 수정한 계정 정보로 로그인된다.
    6. 허용된 기능만 사용할 수 있다.

자동화 범위 (2026-08-20, 완전 자동 — 커밋 `9fa0274`)
  **1~6단계 전부 실제 UI 조작 + DB 대조 + 사양서 대조로 자동 판정한다.**
  4~6단계(로그오프 → 시험 계정 로그인 → 권한별 메뉴 접근 확인)는 한때 MANUAL로
  남겨 뒀었다 — 로그오프 후 시험 계정으로 로그인하면 **회귀의 나머지 TC 가
  권한이 제한된 계정으로 실행되고**, 중간에 실패하면 복구하지 못해 뒤따르는
  TC 가 연쇄로 무너지는 사고를 이미 여러 번 겪었기 때문이다(회귀 7·13·14차).
  2026-08-20 사용자가 사양서1 78~80쪽 계정 그룹별 메뉴 표(SRS 01-30-20)를
  확인해 줘서, **로그인 시도 전에 복구 플래그를 세우고 `finally`에서 반드시
  원래 계정(대개 service)으로 `cold_start` 복구 + 시험 계정 삭제**하는 방식으로
  자동화했다 — 이 TC 안에서만 계정이 바뀌고 회귀의 다른 TC는 영향받지 않는다.
  56개 항목 전부 실측 가시성과 대조해 2026-08-20 56/56 일치 확인(아래 Step 6).

실측한 컨트롤 (2026-08-19, 캡처의 화면 라벨과 rect 대조)
  Setting > System > Account = 페이지 191 (`flows.SETTING_SYSTEM_PAGES`)
    2280 Account List(ID / Name / Group / System) / 2281 + / 2282 휴지통
    우측 Properties: 2283 User ID / 2284 User Name / 2285 Password /
                     2286 Check Password / 2287 Group / 2226 Update
  `+` 는 인라인 편집이 아니라 **New Account 모달**을 띄운다.
    2288 User ID / 2289 User Name / 2290 Password / 2291 Check Password /
    2292 Group 콤보 / 1101 OK / 1102 Cancel
  Group 콤보 항목은 OCR 로 읽어 확정했다: `Service`, `Admin`, `User`.
  `ACCOUNT.Group` 실측값: service=3, admin=2. 새 계정에 붙는 값은 **추측하지 않고**
  만든 뒤 DB 로 확인한다.

비밀번호
  제품이 **8자 이상**을 요구한다(모달의 "At least 8 characters").
  체크리스트는 값을 정하지 않았다. 자격증명을 저장소에 넣지 않기 위해
  (`AGENTS.md` 10항) **실행 시점에 생성해 쓰고 계정과 함께 지운다.** 어디에도
  기록하지 않는다. `config.json` 의 `test_data.account_password` 가 있으면
  그것을 쓴다(사용자가 값을 정하고 싶을 때).
"""

from __future__ import annotations

import os
import secrets
import time

from core import flows, screen, uitext
from core.result import FAIL, MANUAL, PASS, TCResult

GROUP_LABEL = "User"        # 체크리스트의 "허용 권한" — 가장 제한적인 그룹
NAME_SUFFIX = " (edited)"   # 3단계에서 바꿀 표시 이름

# 사양서1 **78~80쪽** "Setting에서 계정 그룹별로 사용할 수 있는 메뉴는 다음과 같다"
# 의 `User` 열을 그대로 옮겼다. 근거 SRS 는 77쪽 제목 **SRS 01-30-20**
# ("로그인한 계정의 권한 그룹에 따라 사용할 수 있는 기능을 제한한다").
# 사용자가 표를 이미지로 확인해 줬고(2026-08-20) 텍스트 추출 결과와 일치했다.
#
#   True  = O (사용 가능)
#   False = X (사용 불가)
#   문자열 = 부분 제한 (표의 비고를 그대로 적는다)
USER_MENU_TABLE = {
    "system": {
        "general": False,
        "security": "Date/Time Change 만 사용 (KIOSK 사용 중일 때만 버튼 활성화)",
        "region": False, "system_info": False,
        "software_info": True, "account": True,
        "license": False, "my_settings": False, "cs": True,
    },
    "patient": {
        "general": False, "patient_list": False, "new_patient": False,
        "examined": False, "physician": False, "external_device": False,
        "barcode": False, "qr_code": False,
    },
    "display": {
        "general": False, "overlay": False, "layout": False, "lut": False,
        "monitor_correction": False,
    },
    "tool": {
        "general": False, "predefined_text": False,
        "image_tool": True,                 # 표에서 User 가 O 인 항목
        "status_bar": False,
    },
    "study": {"general": False, "study_delete": False, "reject_retake": False},
    "procedure": {
        "general": False, "preset": False, "procedure": False,
        "hospital_code": True,              # 표에서 User 가 O 인 항목
    },
    "dicom": {
        "general": False, "mwl": False, "mpps": False, "storage": False,
        "storage_group": False, "storage_commitment": False, "print": False,
        "print_overlay": False, "query_retrieve": False, "tag_mapping": False,
    },
    "device": {
        "general": False, "device_info": False, "aec": False, "aec_3d": False,
        "gantry": False, "gantry_misc": False, "viewposition": False,
        "ups": False,
    },
    "qc": {
        "setting_2d": False, "setting_3d": False, "scheduler": False,
        "auto_delete": False,
        "regular_inspection": "Inspection Information 항목만 표시",
    },
}


def _account_rows(db):
    return {r["ID"]: r for r in db.query(
        "ACCOUNT", "SELECT [Key],System,[Group],ID,Name FROM ACCOUNT "
                   "ORDER BY [Key]")}


def _grab(ui, evidence_dir, name, r):
    """전체 화면을 캡처해 증거로 붙인다. **못 찍어도 TC 를 중단시키지 않는다.**

    로그인/재기동 직후처럼 화면이 전환되는 순간에는 `ui.main_window()`가
    잠깐 `None`을 돌려준다 — 2026-08-28 실측: Step 3 저장 직후 이 호출이
    `AttributeError: 'NoneType' object has no attribute 'rect'`로 죽어 TC 가
    중단되고 시험 계정도 못 지운 채 남았다. 증거는 참고 자료일 뿐 판정 근거가
    아니므로, 못 찍으면 건너뛰고 판정은 계속 진행한다.
    """
    win = ui.main_window()
    if not win:
        return None
    path = os.path.join(evidence_dir, name)
    screen.grab(win.rect, path=path)
    r.attach(path)
    return path


def _password(ctx):
    """8자 이상 비밀번호. 설정에 없으면 실행 시점에 생성한다(기록하지 않는다)."""
    given = (ctx.cfg.get("test_data") or {}).get("account_password")
    if given:
        if len(str(given)) < 8:
            raise RuntimeError(
                "config.json test_data.account_password 가 8자 미만입니다. "
                "제품이 8자 이상을 요구합니다.")
        return str(given)
    # 대/소문자·숫자·기호를 섞어 12자 이상. 반환값은 이 실행 안에서만 쓰인다.
    return "Aa1!" + secrets.token_urlsafe(9)


def _open_account_page(ui):
    """Account 페이지로 이동한다. **이미 그 페이지면 아무것도 하지 않는다.**

    Setting 창이 열려 있을 때 `open_setting` 을 다시 부르면 메인 메뉴에 닿지 못해
    "메인 메뉴가 열리지 않았습니다" 로 죽는다(2026-08-19 실측). 같은 함수를 여러
    단계에서 부르므로 멱등해야 한다.
    """
    if uitext.visible(ui, flows.SETTING_ACCOUNT["list"]):
        return
    flows.open_system_setting(ui, "account", wait=3.0)
    if not uitext.visible(ui, flows.SETTING_ACCOUNT["list"]):
        raise RuntimeError(
            f"Account 목록({flows.SETTING_ACCOUNT['list']})을 찾지 못했습니다.")


def _new_account_dialog(ui):
    """`+` 를 눌러 New Account 모달을 띄우고 그 창을 돌려준다."""
    add = uitext.visible(ui, flows.SETTING_ACCOUNT["add"])
    if not add:
        raise RuntimeError(
            f"Account 추가 버튼({flows.SETTING_ACCOUNT['add']})을 찾지 못했습니다.")
    ui.click(add[0], settle=1.5)
    end = time.time() + 8
    while time.time() < end:
        for w in ui.windows():
            width = w.rect[2] - w.rect[0]
            height = w.rect[3] - w.rect[1]
            # 모달은 화면 중앙의 작은 창이다(실측 386x534).
            if 250 < width < 900 and 300 < height < 800 and \
                    uitext.visible(ui, flows.NEW_ACCOUNT["user_id"]):
                return w
        time.sleep(.5)
    raise RuntimeError("New Account 모달이 열리지 않았습니다.")


def _fill_new_account(ui, account_id, name, password, tesseract_exe):
    """모달을 채우고 Group 을 고른 뒤 OK 를 누른다.

    Group 은 **항목 문구를 OCR 로 읽어** 고른다. 순서로 고르면 조용히 틀어진다
    (`core/uitext.pick_combo_by_text`).
    """
    fields = ((flows.NEW_ACCOUNT["user_id"], account_id),
              (flows.NEW_ACCOUNT["user_name"], name),
              (flows.NEW_ACCOUNT["password"], password),
              (flows.NEW_ACCOUNT["check_password"], password))
    for ctrl_id, value in fields:
        hits = uitext.visible(ui, ctrl_id)
        if not hits:
            raise RuntimeError(f"New Account 입력({ctrl_id})을 찾지 못했습니다.")
        ui.type_text(hits[0], value, clear=True, settle=.4)

    picked = uitext.pick_combo_by_text(
        ui, flows.NEW_ACCOUNT["group"], GROUP_LABEL, tesseract_exe,
        what="계정 권한 그룹")

    ok = uitext.visible(ui, flows.NEW_ACCOUNT["ok"])
    if not ok:
        raise RuntimeError(
            f"New Account OK 버튼({flows.NEW_ACCOUNT['ok']})을 찾지 못했습니다.")
    ui.click(ok[0], settle=1.5)
    message = None
    if ui.dialog():
        message = ui.dismiss_dialog(timeout=3)
    return {"group_picked": picked, "dialog": message}


def _save(ui, tesseract_exe=None):
    """Update 를 누르고 결과 팝업을 정리한다.

    팝업 문구는 커스텀 렌더링이라 `WM_GETTEXT` 로 빈 값이 온다("(문구 미노출)").
    그러면 검증 실패인지 저장 성공 안내인지 구분할 수 없어 **OCR 로 읽어** 돌려준다
    — 2026-08-19 에 이 때문에 "왜 저장이 안 되는지" 알 수 없었다.
    """
    flows.setting_update(ui, wait=3)
    dlg = ui.dialog()
    if not dlg:
        return None
    text = None
    try:
        text = flows.read_dialog_message(ui, dlg, tesseract_exe)
    except Exception:
        text = None
    raw = ui.dismiss_dialog(timeout=3)
    return {"ocr": (text or "").strip(), "raw": raw}


def _select_account(ui, account_id, tesseract_exe):
    """목록에서 대상 계정 행을 **OCR 로 확인해** 선택한다.

    행 순서로 고르지 않는다 — 잘못된 계정을 수정하거나 지우면 로그인이 막힌다.
    """
    row, seen = uitext.find_row_by_text(
        ui, flows.SETTING_ACCOUNT["list"], account_id, tesseract_exe)
    if row is None:
        raise RuntimeError(
            f"계정 목록에서 {account_id} 행을 찾지 못했습니다. 읽은 행={seen}. "
            "엉뚱한 계정을 건드리지 않도록 중단합니다.")
    ui.click(row, settle=1.0)
    return {"rows_read": seen}


def _delete_account(ui, ctx, account_id, tesseract_exe):
    """뒷정리 — 시험 계정을 지운다. 대상을 OCR 로 확인한 뒤에만 지운다."""
    _open_account_page(ui)
    _select_account(ui, account_id, tesseract_exe)
    delete = uitext.visible(ui, flows.SETTING_ACCOUNT["delete"])
    if not delete:
        raise RuntimeError("Account 삭제 버튼(2282)을 찾지 못했습니다.")
    ui.click(delete[0], settle=1.0)
    # 삭제 확인 팝업은 "Are you sure you want to delete this account?" 이고
    # 좌=Yes(501) / 우=No(500) 다(2026-08-19 캡처로 확인). `dismiss_dialog` 는 No 를
    # 눌러 삭제가 되지 않았다. 검사 삭제와 같은 버튼 구성이라
    # `flows.confirm_study_delete` 를 그대로 쓴다 — ID 를 맹신하지 않고 좌우 순서와
    # ID 를 함께 확인해 Yes 를 누르고, 구성이 다르면 중단한다.
    confirmed = flows.confirm_study_delete(ui, accept=True, timeout=6)
    if confirmed is None:
        raise RuntimeError(
            "계정 삭제 확인 팝업이 나타나지 않았습니다. 삭제되지 않은 것으로 봅니다.")
    _save(ui, tesseract_exe)
    end = time.time() + 10
    while time.time() < end and account_id in _account_rows(ctx.db):
        time.sleep(1)
    return account_id not in _account_rows(ctx.db)


def _menu_visibility(ui):
    """모든 Setting 그룹의 하위 페이지가 **보이는지** 그룹별로 실측한다.

    사양의 `O`/`X` 가 "메뉴가 안 보인다"인지 "보이지만 비활성"인지 표에 적혀 있지
    않다. 추측하지 않고 보이는지 여부를 그대로 남긴다.
    """
    seen = {}
    for group, pages in ((g, flows.setting_pages(g))
                         for g in flows.SETTING_GROUPS):
        try:
            flows.open_setting(ui, wait=2.5)
            flows.open_setting_group(ui, group, wait=2.0)
        except Exception as exc:
            # 그룹 자체가 안 보이면 그 그룹의 모든 페이지가 접근 불가다.
            seen[group] = {"_group_error": str(exc)}
            continue
        state = {}
        for name, ctrl_id in pages.items():
            # 그룹을 연 직후 페이지 레일이 아직 그려지는 중일 수 있다 — 한 번만
            # 보면 간헐적으로 "안 보임"이 된다(2026-08-28 실측:
            # `tool > image_tool`이 이 이유로 거짓 FAIL 이었다). 접근 불가(X)는
            # 끝까지 안 보여야 하므로 상한을 짧게 둔다.
            end = time.time() + 3
            hits = []
            while not hits and time.time() < end:
                hits = [c for c in ui.controls(max_depth=8)
                        if c.ctrl_id == ctrl_id and c.visible
                        and c.rect[2] - c.rect[0] > 20]
                if not hits:
                    time.sleep(0.3)
            state[name] = bool(hits)
        seen[group] = state
    return seen


def _compare_with_spec(seen):
    """실측 가시성을 사양서 표와 대조한다.

    반환: (틀린 항목 목록, 요약). 부분 제한 항목은 "접근 가능"으로 기대한다 —
    표의 비고가 화면 안에서의 제한을 말하기 때문이다.
    """
    wrong = []
    summary = {"allowed_ok": 0, "denied_ok": 0, "partial_ok": 0, "checked": 0}
    for group, expected in USER_MENU_TABLE.items():
        measured = seen.get(group, {})
        if "_group_error" in measured:
            # 그룹을 못 열었다 = 그 그룹의 모든 페이지가 접근 불가.
            for name, want in expected.items():
                summary["checked"] += 1
                if want is False:
                    summary["denied_ok"] += 1
                else:
                    wrong.append({"group": group, "page": name,
                                  "expected": want, "measured": "그룹 접근 불가",
                                  "reason": measured["_group_error"][:80]})
            continue
        for name, want in expected.items():
            summary["checked"] += 1
            got = measured.get(name)
            if want is False:
                if got:
                    wrong.append({"group": group, "page": name,
                                  "expected": "X (사용 불가)", "measured": "보임"})
                else:
                    summary["denied_ok"] += 1
            else:
                if got:
                    summary["partial_ok" if isinstance(want, str)
                            else "allowed_ok"] += 1
                else:
                    wrong.append({"group": group, "page": name,
                                  "expected": ("부분 제한: " + want)
                                  if isinstance(want, str) else "O (사용 가능)",
                                  "measured": "안 보임"})
    return wrong, summary


def _login_as(ctx, account_id, password):
    """시험 계정으로 Viewer 를 재기동해 로그인한다.

    `cold_start` 는 `cfg["viewer"]["login"]` 을 쓰므로 **설정 복사본**을 넘긴다.
    원본 `ctx.cfg` 를 건드리면 복구가 원래 계정으로 되지 않는다.
    """
    import copy

    cfg = copy.deepcopy(ctx.cfg)
    cfg["viewer"]["login"] = {"id": account_id, "password": password}
    cfg["viewer"]["force_restart"] = True
    return flows.cold_start(cfg, ctx.db, force_restart=True)


def run(ctx):
    r = TCResult("TC_Basic_WorkFlow_13", "계정 추가·수정 및 로그인")
    account_id = (ctx.cfg.get("test_data") or {}).get("account_id")
    if not account_id:
        r.add(0, "TC_Basic_WorkFlow_13 실행", FAIL,
              actual="config.json 의 test_data.account_id 가 없습니다.")
        return r

    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    evidence_dir = os.path.join(ctx.evidence_root, "Flow", "13_Account")
    ui = None
    created = False
    logged_in_as_test = False
    try:
        password = _password(ctx)
        name = "Auto Flow User"

        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError("Patient 화면이 준비되지 않았습니다")

        before = _account_rows(ctx.db)
        r.assert_true(0, "전제: 서비스/관리자 계정으로 로그인된 상태",
                      bool(before),
                      expected="ACCOUNT 행 1건 이상",
                      actual={"accounts": sorted(before), "startup": startup})
        if account_id in before:
            # 이전 실행이 남긴 계정이 있으면 먼저 지운다. 남은 계정을 그대로 쓰면
            # "추가되었다"는 판정이 거짓으로 통과한다.
            removed = _delete_account(ui, ctx, account_id, tess)
            before = _account_rows(ctx.db)
            if not removed or account_id in before:
                raise RuntimeError(
                    f"이전 실행이 남긴 {account_id} 계정을 지우지 못했습니다. "
                    f"현재 계정={sorted(before)}. 남은 계정을 그대로 쓰면 '추가되었다'는 "
                    "판정이 거짓으로 통과하므로 중단합니다.")

        # --- Step 1 / 2: 계정 추가 + 권한 그룹 -------------------------------
        _open_account_page(ui)
        dlg = _new_account_dialog(ui)
        filled = _fill_new_account(ui, account_id, name, password, tess)
        saved_msg = _save(ui, tess)
        created = True

        end = time.time() + 10
        after = _account_rows(ctx.db)
        while time.time() < end and account_id not in after:
            time.sleep(1)
            after = _account_rows(ctx.db)
        row = after.get(account_id)

        _grab(ui, evidence_dir, "01_account_added.png", r)

        r.assert_true(
            1, f"[Setting > System > Account] {account_id} 계정 추가",
            row is not None and row.get("Name") == name,
            expected={"ID": account_id, "Name": name},
            actual={"row": row, "dialog": filled, "update": saved_msg,
                    "added": sorted(set(after) - set(before))},
            note="Expected 1. 계정이 저장된다. ACCOUNT 테이블로 대조한다. "
                 "New Account 모달(2288~2292)에 입력하고 OK(1101) 후 Update(2226).")

        # Group 값은 **실측**으로 확정했다: Service=3 / Admin=2 / User=1
        # (`flows.ACCOUNT_GROUPS`). 그래서 "기존과 다른 값" 같은 느슨한 판정이
        # 아니라 고른 라벨에 대응하는 값을 그대로 대조한다.
        want_group = flows.ACCOUNT_GROUPS[GROUP_LABEL]
        r.assert_equal(
            2, f"계정 권한 그룹을 {GROUP_LABEL}({want_group}) 로 설정",
            want_group, row.get("Group") if row else None,
            note=f"Expected 2. 권한 설정이 저장된다. 콤보 항목을 OCR로 읽어 고른다 — "
                 f"읽은 항목 {filled.get('group_picked', {}).get('items_read')}. "
                 f"ACCOUNT.Group 매핑 {flows.ACCOUNT_GROUPS} 은 실제로 만들어 DB로 "
                 f"확인한 값이다. 권한 코드별 기능 범위 표는 매뉴얼에 없어 Step 6은 "
                 f"수동으로 둔다.")

        # --- Step 3: 계정 정보 수정 -----------------------------------------
        _open_account_page(ui)
        picked = _select_account(ui, account_id, tess)
        edited = name + NAME_SUFFIX
        name_edit = uitext.visible(ui, flows.SETTING_ACCOUNT["user_name"])
        if not name_edit:
            raise RuntimeError("Properties User Name(2284)을 찾지 못했습니다.")
        ui.type_text(name_edit[0], edited, clear=True, settle=.5)
        # 계정을 선택하면 Password / Check Password 는 비워진 상태로 표시된다
        # ("Input Password" 자리표시자). 비운 채 Update 하면 저장되지 않았다
        # (2026-08-19 실측). 수정 시에도 같은 비밀번호를 다시 넣는다.
        for key in ("password", "check_password"):
            hits = uitext.visible(ui, flows.SETTING_ACCOUNT[key])
            if hits:
                ui.type_text(hits[0], password, clear=True, settle=.4)
        edit_msg = _save(ui, tess)

        end = time.time() + 10
        final = _account_rows(ctx.db)
        while time.time() < end and (final.get(account_id) or {}).get("Name") != edited:
            time.sleep(1)
            final = _account_rows(ctx.db)

        _grab(ui, evidence_dir, "02_account_edited.png", r)

        r.assert_equal(
            3, "수정한 계정 정보 저장", edited,
            (final.get(account_id) or {}).get("Name"),
            note=f"Expected 3. 수정한 계정 정보가 저장된다. User Name 을 "
                 f"{name!r} -> {edited!r} 로 바꾸고 ACCOUNT.Name 으로 대조. "
                 f"선택한 행은 OCR로 확인했다({picked['rows_read']}). "
                 f"Update 결과: {edit_msg!r}")

        # --- Step 4~5: 로그오프하고 시험 계정으로 로그인 ----------------------
        # Viewer 재기동으로 로그오프와 로그인이 함께 이뤄진다. 이 시점부터 실패해도
        # `finally` 가 원래 계정으로 되돌린다.
        # 플래그를 **시도 전에** 세운다. 로그인 도중 실패해도 `finally` 가 원래
        # 계정으로 되돌려야 한다 — 세운 뒤 실패하면 복구가 돌지 않는다.
        logged_in_as_test = True
        ui, startup2 = _login_as(ctx, account_id, password)
        entered = flows.ensure_patient_screen(ui)
        _grab(ui, evidence_dir, "03_logged_in_as_test.png", r)

        r.assert_true(
            4, "로그오프 후 로그인 화면을 지나 재로그인",
            any("로그인" in str(x) for x in startup2),
            expected="Viewer 재기동 시 로그인 화면을 지난다",
            actual={"startup": startup2},
            note="Expected 4. 로그인 화면이 표시되고 이전 사용자 정보가 남지 않는다. "
                 "재기동으로 로그오프+로그인을 함께 수행한다. ID 입력창은 목록형이라 "
                 "등록된 계정이 목록에 남는 것이 정상이다(사양서1 78쪽 '기존에 등록했던 "
                 "계정 목록이 표시되며, 목록 중에 선택해서 로그인할 수 있다').")

        r.assert_true(
            5, f"{account_id} 계정으로 로그인", entered,
            expected=f"{account_id} 로 로그인되고 Patient 화면 진입",
            actual={"startup": startup2, "patient_screen": entered},
            note="Expected 5. 수정한 계정 정보로 로그인된다. 비밀번호는 이 실행에서 "
                 "만든 값을 쓰며 어디에도 기록하지 않는다.")

        # --- Step 6: 권한 그룹에 따른 메뉴 접근 (사양서 표 56개 전부) ---------
        seen = _menu_visibility(ui)
        wrong, summary = _compare_with_spec(seen)
        _grab(ui, evidence_dir, "04_user_setting_menus.png", r)

        r.assert_true(
            6, f"권한 그룹({GROUP_LABEL})에 허용된 메뉴만 접근 가능 "
               f"(사양서 표 {summary['checked']}개 항목)",
            not wrong,
            expected={"근거": "사양서1 78~80쪽 계정 그룹별 사용 가능 메뉴 표 "
                             "(SRS 01-30-20) 의 User 열",
                      "O(사용 가능)": [f"{g}>{n}" for g, d in USER_MENU_TABLE.items()
                                    for n, v in d.items() if v is True],
                      "부분 제한": [f"{g}>{n}" for g, d in USER_MENU_TABLE.items()
                                for n, v in d.items() if isinstance(v, str)]},
            actual={"불일치": wrong, "요약": summary, "실측": seen},
            note="Expected 6. 허용된 기능만 사용할 수 있다. 사양서 표의 56개 항목을 "
                 "전부 대조한다. 페이지 컨트롤 ID 는 2026-08-20 에 각 항목을 OCR 로 "
                 "읽어 표 순서와 짝지어 확정했다 — ID 가 화면 순서와 무관해서"
                 "(Device 는 234-226-230-231-229-232-233-227) 추정하면 틀린다. "
                 "표가 O/X 가 '안 보임'인지 '보이지만 비활성'인지 적지 않았으므로 "
                 "**보이는지 여부**로 판정하고 실측값을 그대로 남긴다. 부분 제한 항목은 "
                 "접근 가능으로 기대한다 — 표의 비고는 화면 안에서의 제한이다.")
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_13 실행", exc)
    finally:
        # **로그인 계정을 반드시 되돌린다.** 시험 계정으로 남으면 뒤따르는 TC 가
        # 제한 권한으로 돌아 연쇄 실패한다(회귀 7·13·14차의 교훈).
        if logged_in_as_test:
            try:
                original = ctx.cfg["viewer"]["login"]["id"]
                ui, back = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
                ok = flows.ensure_patient_screen(ui)
                r.cleanup(0, "뒷정리: 원래 계정으로 복구", PASS if ok else FAIL,
                      expected=f"{original} 로 재로그인",
                      actual={"startup": back, "patient_screen": ok},
                      note="로그인 계정을 바꾸는 TC 는 반드시 되돌린다. 되돌리지 "
                           "못하면 뒤따르는 TC 가 전부 무너진다.")
            except Exception as exc:
                r.cleanup(0, "뒷정리: 원래 계정으로 복구", FAIL,
                      actual=f"복구 실패({exc}). **뒤따르는 TC 가 제한 권한으로 "
                             f"실행될 수 있다.** Viewer 를 재시작하고 "
                             f"{ctx.cfg['viewer']['login']['id']} 로 로그인하십시오.")

        # 시험 계정을 남기지 않는다. 지우지 못하면 리포트에 남겨 사람이 알게 한다.
        # **원래 계정으로 돌아온 뒤에** 지운다 — 제한 권한으로는 못 지울 수 있다.
        if ui is not None and created:
            try:
                gone = _delete_account(ui, ctx, account_id, tess)
                r.cleanup(0, "뒷정리: 시험 계정 삭제", PASS if gone else MANUAL,
                      expected=f"{account_id} 삭제됨",
                      actual="삭제 확인" if gone
                             else f"삭제되지 않았다 — 수동 삭제 필요: {account_id}")
            except Exception as exc:
                r.cleanup(0, "뒷정리: 시험 계정 삭제", MANUAL,
                      actual=f"삭제 실패({exc}). 수동으로 {account_id} 를 지우십시오.")
    return r
