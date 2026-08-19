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

자동화 범위 (2026-08-19)
  **1~3단계는 실제 UI 조작 + DB 대조로 자동 판정한다.**
  4~6단계는 자동화하지 않고 MANUAL 로 남긴다 — 이유를 분명히 적는다.
    로그오프 후 시험 계정으로 로그인하면 **회귀의 나머지 TC 가 권한이 제한된
    계정으로 실행된다.** 중간에 실패하면 로그인 상태를 복구하지 못해 뒤따르는
    TC 가 연쇄로 무너진다. 이 저장소는 그런 연쇄 실패를 이미 여러 번 겪었고
    (회귀 7·13·14차), 그때마다 원인 추적에 오래 걸렸다. 그래서 로그인 계정을
    바꾸는 단계는 **복구 절차를 사용자와 합의한 뒤** 붙인다.
    `NEXT_TASK.md` 에 물어볼 것으로 남겼다.

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


def _account_rows(db):
    return {r["ID"]: r for r in db.query(
        "ACCOUNT", "SELECT [Key],System,[Group],ID,Name FROM ACCOUNT "
                   "ORDER BY [Key]")}


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

        path = os.path.join(evidence_dir, "01_account_added.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)

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

        path = os.path.join(evidence_dir, "02_account_edited.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)

        r.assert_equal(
            3, "수정한 계정 정보 저장", edited,
            (final.get(account_id) or {}).get("Name"),
            note=f"Expected 3. 수정한 계정 정보가 저장된다. User Name 을 "
                 f"{name!r} -> {edited!r} 로 바꾸고 ACCOUNT.Name 으로 대조. "
                 f"선택한 행은 OCR로 확인했다({picked['rows_read']}). "
                 f"Update 결과: {edit_msg!r}")

        # --- Step 4~6: 로그인 계정 변경 (의도적으로 수동) ---------------------
        r.manual(4, "로그오프 후 로그인 화면에 이전 사용자 정보가 남지 않음",
                 "자동화하지 않는다 — 로그인 계정을 바꾸면 회귀의 뒤따르는 TC가 "
                 "제한 권한으로 실행되고, 중간 실패 시 복구가 불가능하다. "
                 "복구 절차를 합의한 뒤 붙인다(NEXT_TASK.md).")
        r.manual(5, f"{account_id} 계정으로 로그인",
                 "위와 같은 이유로 수동. 계정과 권한이 저장된 것은 Step 1~3에서 "
                 "DB로 확인했다.")
        r.manual(6, "허용된 기능만 사용 가능",
                 "권한별 메뉴 노출 범위가 매뉴얼에 표로 정리돼 있지 않아 기대값을 "
                 "확정할 수 없다. 사양 확인이 필요하다(NEXT_TASK.md).")
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_13 실행", FAIL, actual=str(exc))
    finally:
        # 시험 계정을 남기지 않는다. 지우지 못하면 리포트에 남겨 사람이 알게 한다.
        if ui is not None and created:
            try:
                gone = _delete_account(ui, ctx, account_id, tess)
                r.add(0, "뒷정리: 시험 계정 삭제", PASS if gone else MANUAL,
                      expected=f"{account_id} 삭제됨",
                      actual="삭제 확인" if gone
                             else f"삭제되지 않았다 — 수동 삭제 필요: {account_id}")
            except Exception as exc:
                r.add(0, "뒷정리: 시험 계정 삭제", MANUAL,
                      actual=f"삭제 실패({exc}). 수동으로 {account_id} 를 지우십시오.")
    return r
