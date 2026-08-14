# -*- coding: utf-8 -*-
"""Viewer 화면 조작 시나리오.

컨트롤 ID는 2026-08-10에 실측한 값이며 `config.json > viewer.control_ids` 와
같은 내용이다. 화면이 바뀌면 `python run.py ui-probe` 로 다시 뜬다.
"""

import time

from core.ui import ViewerUi, children


# --- 화면별 컨트롤 ID -------------------------------------------------
LOGIN = {"id_combo": 2001, "password": 2002, "login": 2003}
WELCOME = {"examine": 2007, "today_qc": 2008, "logout": 2004, "power": 2005}

PATIENT = {
    "tab_patient_list": 2284,
    "tab_new_patient": 2285,
    "mode_selector": 2132,
    # Patient List
    "search_field_combo": 2135,
    "search_text": 2138,
    "modality_combo": 2136,
    "station_combo": 2137,
    "auto_refresh": 2146,
    "range_today": 1106,
    "range_week": 1107,
    "range_month": 1108,
    "range_custom": 1109,
    "search": 2141,
    "refresh": 2142,
    "study_list": 2147,
    "edit": 2143,
    "delete": 2145,
    "examine_from_list": 2144,
    # New Patient
    "np_study_datetime": 2163,
    "np_patient_id": 2155,
    "np_patient_name": 2150,
    "np_accession": 2164,
    "np_birth_date": 2156,
    "np_birth_picker": 2149,
    "np_age": 2157,
    "np_sex_female": 2167,
    "np_sex_male": 2168,
    "np_sex_other": 2169,
    "np_study_description": 2165,
    "np_procedure_combo": 2170,
    "np_examine": 2148,
    "np_save": 1103,
    "close": 4,
}

# Patient List의 데이터 소스 드롭리스트(2139)와 항목 (2026-08-11 실측)
#   All(1191) / Local(1192) / MWL(1195)  — ID가 연속이 아니므로 값으로 지정한다.
PATIENT_SOURCE_DROPLIST = 2139
PATIENT_SOURCE_ITEMS = {"all": 1191, "local": 1192, "mwl": 1195}

# 검색 기준 콤보(2135) 팝업 항목 (컨트롤 ID = 표시 순서)
SEARCH_FIELD_ITEMS = {
    "patient_name": 1, "patient_id": 2, "accession": 3, "id_name_acc": 4,
}
SEARCH_FIELD_LABELS = {
    "patient_name": "Patient Name", "patient_id": "Patient ID",
    "accession": "Acc No.", "id_name_acc": "ID, Name, Acc No.",
}

EXAMINE = {
    "status_banner": 2202,        # 상단 우측 상태 배너 (Ready / 미준비)
    "step_thumbnails": 155,       # SystemThumbnail — 하위 SystemThumbnailItem 1..N = Step
    "edit_information": 2203,     # 헤더의 연필 아이콘 → Edit Information 대화상자
    "procedure_add": 2208,        # Procedure 패널 +
    "procedure_delete": 2207,     # Procedure 패널 휴지통
    "close": 2204,                # 검사 종료
    "retake": 2205,
    "tool_select": 1111,
    "tool_zoom": 1113,
    "tool_pan": 1114,
    "tool_fit": 1124,
    "tool_center": 1127,
    "tool_send": 1148,
    "tool_proc": 1151,
    "tool_reset": 1161,
    "layout_button": 1140,
}

STATUS_BAR = {"menu": 2015}

# 메인 메뉴(좌측 하단 ☰). 아이콘 레일과 메뉴 항목의 컨트롤 ID (2026-08-10 실측)
MAIN_MENU = {
    "examined": 58,     # 검사 목록
    "dicom": 59,        # DICOM 창
    "setting": 55,      # Setting
    "power": 1000,      # 종료
    "item_examine": 52,
    "item_view": 53,
    "item_account": 100,
}


def menu_is_open(ui):
    """메인 메뉴가 펼쳐져 있는지. 메뉴 항목 컨트롤의 표시 여부로 판단한다."""
    ids = {MAIN_MENU["item_examine"], MAIN_MENU["item_view"], MAIN_MENU["setting"]}
    return any(c.ctrl_id in ids and c.visible and c.rect[2] - c.rect[0] > 20
               for c in ui.controls(max_depth=6))


def open_main_menu(ui, timeout=6):
    """메인 메뉴를 연다. 이미 열려 있으면 그대로 둔다.

    메뉴 버튼은 토글이라, 열린 상태에서 다시 누르면 닫힌다.
    상태 확인 없이 누르면 의도와 반대로 동작한다(실제로 발생).
    """
    if menu_is_open(ui):
        return True
    btn = ui.by_id(STATUS_BAR["menu"])
    if not btn:
        raise FlowError("메인 메뉴 버튼(2015)을 찾지 못했습니다. "
                        "상태바가 있는 화면인지 확인하십시오.")
    ui.click(btn[0], settle=1.0)
    end = time.time() + timeout
    while time.time() < end:
        if menu_is_open(ui):
            return True
        time.sleep(0.4)
    return False


def _click_menu(ui, key, wait=3.0):
    if not open_main_menu(ui):
        raise FlowError("메인 메뉴가 열리지 않았습니다.")
    target = [c for c in ui.controls(max_depth=6)
              if c.ctrl_id == MAIN_MENU[key] and c.visible
              and c.rect[2] - c.rect[0] > 20]
    if not target:
        raise FlowError(f"메뉴 항목 '{key}'(ID {MAIN_MENU[key]})을 찾지 못했습니다.")
    ui.click(target[0], settle=1.5)
    time.sleep(wait)
    return True


def open_setting(ui, wait=4.0):
    """메인 메뉴 → Setting 화면으로 이동한다."""
    return _click_menu(ui, "setting", wait)


def open_dicom_window(ui, wait=4.0):
    """메인 메뉴 → DICOM 창으로 이동한다 (Queue / SCP List)."""
    return _click_menu(ui, "dicom", wait)


# --- Setting 화면 -----------------------------------------------------
# 좌측 그룹 레일 (2026-08-10 실측, Bellalun 1.0.12.105)
SETTING_GROUPS = {
    "system": 177, "patient": 178, "display": 179, "tool": 180, "study": 181,
    "procedure": 182, "dicom": 183, "device": 184, "qc": 185,
}
# DICOM 그룹의 하위 페이지 (위 → 아래)
SETTING_DICOM_PAGES = {
    "general": 216, "mwl": 217, "mpps": 218, "storage": 219,
    "storage_group": 220, "storage_commitment": 221, "print": 222,
    "print_overlay": 223, "query_retrieve": 224, "tag_mapping": 225,
}
SETTING_UPDATE_BUTTON = 2226

# Setting > DICOM > General 페이지 컨트롤
SETTING_DICOM_GENERAL = {
    "study_close_option": 2444,      # 콤보 (None / Auto Send 등)
    "urgent_auto_send_yes": 2446,
    "urgent_auto_send_no": 2445,
    "ip_address": 2436,              # 읽기 전용
    "station_name": 2434,
    "station_ae_title": 2435,
    "station_port": 2437,
}


def _click_setting_control(ui, ctrl_id, what, wait=1.5):
    hits = [c for c in ui.controls(max_depth=7)
            if c.ctrl_id == ctrl_id and c.visible
            and c.rect[2] - c.rect[0] > 20]
    if not hits:
        raise FlowError(f"{what}(ID {ctrl_id})을 찾지 못했습니다. "
                        f"현재 화면을 ui-probe로 확인하십시오.")
    ui.click(hits[0], settle=1.0)
    time.sleep(wait)
    return hits[0]


def open_setting_group(ui, group, wait=2.0):
    if group not in SETTING_GROUPS:
        raise FlowError(f"알 수 없는 Setting 그룹: {group}")
    return _click_setting_control(ui, SETTING_GROUPS[group],
                                  f"Setting 그룹 '{group}'", wait)


def open_dicom_setting(ui, page, wait=2.5):
    """Setting > DICOM > <page> 로 이동한다.

    page: general | mwl | mpps | storage | storage_group |
          storage_commitment | print | print_overlay |
          query_retrieve | tag_mapping
    """
    if page not in SETTING_DICOM_PAGES:
        raise FlowError(f"알 수 없는 DICOM 설정 페이지: {page}")
    open_setting(ui, wait=3.0)
    open_setting_group(ui, "dicom", wait=2.0)
    return _click_setting_control(ui, SETTING_DICOM_PAGES[page],
                                  f"DICOM 설정 '{page}'", wait)


def setting_update(ui, wait=2.0):
    """Setting 화면의 Update(적용) 버튼을 누른다."""
    return _click_setting_control(ui, SETTING_UPDATE_BUTTON, "Update 버튼", wait)


class FlowError(RuntimeError):
    pass


# --- Cold start -------------------------------------------------------
def cold_start(cfg, db, on_event=None, force_restart=None):
    """Viewer가 꺼져 있는 상태를 전제로 기동부터 수행한다.

    수행 순서
      1) 기존 Viewer 프로세스 정리 (이전 실행의 잔여 상태 제거)
      2) VIEWER.exe 실행
      3) Demo 모드 등 기동 팝업 정리
      4) 로그인
      5) BELLALUN DB attach 완료 대기
         (설치 직후에는 DATA/CONFIGURATION 등이 SQL 인스턴스에 붙어 있지 않다.
          Viewer/BellalunService가 기동하면서 attach 하므로 여기서 기다린다)

    반환: (ViewerUi, 진행 로그 리스트)
    """
    from core import watchdog

    log = []

    def say(msg):
        log.append(msg)
        if on_event:
            on_event(msg)

    ui = ViewerUi()

    # 기본은 '이미 떠 있고 로그인까지 되어 있으면 재사용'이다.
    # 매 실행마다 강제 재기동하면 검증자가 보기에 뷰어가 계속 꺼졌다 켜진다.
    # 깨끗한 상태가 꼭 필요한 TC만 config의 viewer.force_restart로 켠다.
    if force_restart is None:
        force_restart = bool(cfg["viewer"].get("force_restart", False))

    if ui.pid and not force_restart:
        healthy = not ui.at_login_screen() and db.ping()
        if healthy:
            say(f"실행 중인 Viewer(PID {ui.pid}) 재사용")
            guard = watchdog.DialogGuard(
                ui, evidence_dir=cfg.get("evidence_ui_dir", "Evidence/ui"))
            guard.sweep(tag="_reuse")
            return ui, log
        say("실행 중인 Viewer가 로그인 전 상태 — 로그인부터 수행")

    if force_restart and ui.pid:
        # 검사가 열린 채로 강제 종료하면 저장되지 않은 상태가 남을 수 있다.
        # 먼저 정상 경로(검사 종료 → 로그아웃)를 시도하고, 안 되면 그때 강제 종료한다.
        say(f"기존 Viewer(PID {ui.pid}) 정리")
        try:
            if ui.by_id(EXAMINE["close"]):
                say("  열린 검사가 있어 Suspend(보류 저장) 수행")
                # 0장 검사에서 ID 501은 Close가 아니라 Discard다. 재기동 정리는
                # 데이터를 잃지 않는 Suspend(502)를 항상 사용한다.
                close_examine(ui, option="suspend", wait=6)
        except Exception as exc:
            say(f"  검사 종료 시도 실패({exc}) — 강제 종료로 전환")
        _kill_viewer(ui.pid)
        time.sleep(3)
        ui._pid = None

    if not ui.pid:
        exe = cfg["viewer"]["exe"]
        say(f"Viewer 실행: {exe}")
        ui.launch(exe, wait=int(cfg["viewer"].get("launch_wait", 18)))
        if not ui.pid:
            raise FlowError("Viewer가 기동되지 않았습니다.")

    guard = watchdog.DialogGuard(ui, evidence_dir=cfg.get("evidence_ui_dir",
                                                         "Evidence/ui"))
    popped = guard.sweep(tag="_startup")
    if popped:
        say("기동 팝업 정리: " + "; ".join(p["message"] or p["title"] for p in popped))

    # 로그인 화면이 실제로 뜰 때까지 기다린다.
    # 기동 직후에는 컨트롤이 아직 없어서, 바로 로그인하면 '이미 로그인됨'으로
    # 오인하고 그냥 통과해 버린다(실제로 발생한 버그).
    say("로그인 또는 Viewer 준비 화면 대기")
    startup_timeout = int(cfg["viewer"].get("startup_timeout", 180))
    end = time.time() + startup_timeout
    ready_without_login = False
    while time.time() < end:
        guard.sweep(tag="_startup_wait")
        if ui.at_login_screen():
            break
        # 느린 PC에서는 로그인 화면이 잠깐 나타났다 사라질 수 있다. 명확한
        # Viewer 화면 컨트롤이 보일 때만 '이미 로그인됨'으로 판단한다.
        if (ui.by_id(WELCOME["examine"]) or
                ui.by_id(PATIENT["tab_new_patient"]) or
                ui.by_id(STATUS_BAR["menu"])):
            ready_without_login = True
            break
        time.sleep(1.0)
    if not ui.at_login_screen() and not ready_without_login:
        raise FlowError(
            f"Viewer가 {startup_timeout}초 안에 로그인/준비 화면을 표시하지 않았습니다. "
            "기동 실패를 로그인 완료로 간주하지 않고 안전하게 중단합니다.")

    login = cfg["viewer"]["login"]
    if ui.at_login_screen():
        say(f"로그인: {login['id']}")
        ok = ui.login(login["id"], login["password"])
        popped = guard.sweep()
        if popped:
            msgs = "; ".join(p["message"] or "(문구 미노출)" for p in popped)
            raise FlowError(f"로그인 중 팝업 발생: {msgs} "
                            f"(증적은 Evidence/ui 참조). 계정/비밀번호를 확인하십시오.")
        if not ok or ui.at_login_screen():
            raise FlowError("로그인에 실패했습니다. 계정/비밀번호를 확인하십시오.")
        say("로그인 완료")
    guard.sweep()

    say("BELLALUN DB attach 대기")
    watchdog.wait_until(db.ping, timeout=90, poll=2.0, desc="BELLALUN DB 접속")
    say("DB 접속 확인")

    return ui, log


def _kill_viewer(pid):
    import subprocess
    subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                   capture_output=True)


def _need(ui, ctrl_id, what):
    hits = ui.by_id(ctrl_id)
    if not hits:
        raise FlowError(f"{what} 컨트롤(ID {ctrl_id})을 찾지 못했습니다. "
                        f"현재 화면을 ui-probe로 확인하십시오.")
    return hits[0]


# --- Patient 화면 -----------------------------------------------------
def open_new_patient_tab(ui, timeout=8):
    ui.activate()
    ui.click(_need(ui, PATIENT["tab_new_patient"], "New Patient 탭"), settle=.2)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        controls = [c for c in ui.by_id(PATIENT["np_patient_id"]) if c.visible]
        if controls:
            return controls[0]
        time.sleep(.25)
    raise FlowError(
        f"New Patient 입력 화면이 {timeout}초 안에 준비되지 않았습니다 "
        f"(Patient ID control {PATIENT['np_patient_id']}).")


def open_patient_list_tab(ui):
    ui.activate()
    ui.click(_need(ui, PATIENT["tab_patient_list"], "Patient List 탭"), settle=1.2)


def _open_combo_and_choose(ui, combo_id, item_id, what):
    combo = _need(ui, combo_id, what)
    l, t, rr, bb = combo.rect
    # 이 커스텀 콤보는 가운데를 누르면 tooltip만 보일 수 있다.
    ui.click((rr - min(12, max(4, (rr - l) // 8)), (t + bb) // 2), settle=.5)
    end = time.time() + 5
    while time.time() < end:
        items = [c for c in ui.by_id(item_id) if c.visible]
        if items:
            ui.click(items[0], settle=.8)
            return True
        time.sleep(.2)
    raise FlowError(f"{what} 목록 항목(ID {item_id})을 찾지 못했습니다.")


def select_patient_source(ui, source):
    key = str(source).lower()
    if key not in PATIENT_SOURCE_ITEMS:
        raise FlowError(f"알 수 없는 Patient source: {source}")
    return _open_combo_and_choose(ui, PATIENT_SOURCE_DROPLIST,
                                  PATIENT_SOURCE_ITEMS[key], "Patient source")


def select_search_field(ui, field):
    key = str(field).lower()
    if key not in SEARCH_FIELD_ITEMS:
        raise FlowError(f"알 수 없는 search field: {field}")
    combo = _need(ui, PATIENT["search_field_combo"], "Search field")
    expected = SEARCH_FIELD_LABELS[key]
    if ui.combo_value(combo).strip().lower() == expected.lower():
        return True
    # 팝업 항목 ID 1~4는 Viewer의 다른 버튼 ID와 중복되고 팝업 행은 커스텀
    # 렌더링이라 Win32 자식으로 열거되지 않는다. 콤보 화살표로 연 뒤 콤보
    # rect/행 높이에 상대적인 위치를 누르고 표시 문자열로 최종 검증한다.
    icons = [c for c in children(combo.hwnd, 1)
             if c.ctrl_id == 1 and c.visible]
    ui.click(icons[0] if icons else combo, settle=.3)
    index = {"patient_name": 0, "patient_id": 1,
             "accession": 2, "id_name_acc": 3}[key]
    l, t, rr, bb = combo.rect
    row_h = bb - t
    ui.click(((l + rr) // 2, bb + index * row_h + row_h // 2), settle=.6)
    actual = ui.combo_value(combo)
    if actual.strip().lower() != expected.lower():
        raise FlowError(f"Search field 선택 실패: expected={expected}, actual={actual}")
    return True


def search_patient(ui, text, field="patient_id", wait=3):
    select_search_field(ui, field)
    ui.type_text(_need(ui, PATIENT["search_text"], "Search text"), str(text))
    ui.click(_need(ui, PATIENT["search"], "Search"), settle=1)
    time.sleep(wait)
    return visible_row_count(ui)


def select_patient_information_visible(ui):
    return bool([c for c in ui.by_id(2108) if c.visible] and
                [c for c in ui.by_id(1101) if c.visible] and
                [c for c in ui.by_id(1102) if c.visible])


def handle_select_patient_information(ui, action="use_existing", timeout=6):
    """커스텀 Select Patient Information 창을 컨트롤 ID로 처리한다."""
    end = time.time() + timeout
    while time.time() < end and not select_patient_information_visible(ui):
        time.sleep(.25)
    if not select_patient_information_visible(ui):
        return None
    ids = {"use_existing": 1101, "use_mwl": 1102, "cancel": 1102}
    if action not in ids:
        raise FlowError(f"알 수 없는 patient information action: {action}")
    target = [c for c in ui.by_id(ids[action]) if c.visible]
    if not target:
        raise FlowError("Select Patient Information 버튼을 찾지 못했습니다.")
    ui.click(target[0], settle=1)
    return {"popup": True, "action": action, "control_id": ids[action]}


def read_edit_information(ui, close=True):
    """Examine의 Edit Information을 읽고, 기본적으로 Cancel로 닫는다."""
    from core import screen
    ui.click(_need(ui, EXAMINE["edit_information"], "Edit Information"), settle=1)
    end = time.time() + 5
    while time.time() < end and not ui.by_id(PATIENT["np_patient_id"]):
        time.sleep(.2)
    values = read_new_patient(ui)
    selected = []
    for sex, key in (("F", "np_sex_female"), ("M", "np_sex_male"),
                     ("O", "np_sex_other")):
        hits = [c for c in ui.by_id(PATIENT[key]) if c.visible]
        if hits and screen.radio_selected(hits[0]) is True:
            selected.append(sex)
    values["sex"] = selected[0] if len(selected) == 1 else None
    if close:
        cancel = [c for c in ui.by_id(1102) if c.visible]
        if not cancel:
            raise FlowError("Edit Information Cancel 버튼(1102)을 찾지 못했습니다.")
        ui.click(cancel[0], settle=1)
    return values


def ensure_patient_screen(ui, wait=5):
    """Welcome/Setting/Examine 어느 화면에서 시작해도 Patient 화면으로 이동."""
    if ui.by_id(PATIENT["tab_new_patient"]):
        return True
    # Setting 모달을 먼저 닫는다.
    if ui.by_id(SETTING_UPDATE_BUTTON) or ui.by_id(SETTING_GROUPS["system"]):
        win = ui.main_window()
        top = win.rect[1] if win else 0
        close = [c for c in ui.by_id(4)
                 if c.visible and c.rect[1] < top + 100]
        if close:
            ui.click(close[0], settle=1)
    if ui.by_id(WELCOME["examine"]):
        ui.click(ui.by_id(WELCOME["examine"])[0], settle=2)
    if ui.by_id(PATIENT["tab_new_patient"]):
        return True
    # Examine 화면에서는 메인 메뉴의 Examine 항목으로 Patient 화면을 연다.
    if open_main_menu(ui):
        target = [c for c in ui.by_id(MAIN_MENU["item_examine"])
                  if c.visible and c.rect[2] - c.rect[0] > 20]
        if target:
            ui.click(target[0], settle=2)
    end = time.time() + wait
    while time.time() < end:
        if ui.by_id(PATIENT["tab_new_patient"]):
            return True
        time.sleep(.5)
    return False


def fill_new_patient(ui, patient_id, patient_name, accession=None,
                     birth_date=None, sex="F", study_description=None):
    """New Patient 폼을 채운다. 채운 값을 되읽어 반환한다(입력 검증용)."""
    open_new_patient_tab(ui)

    ui.set_text(_need(ui, PATIENT["np_patient_id"], "Patient ID"), patient_id)
    ui.set_text(_need(ui, PATIENT["np_patient_name"], "Patient Name"), patient_name)
    if accession is not None:
        ui.set_text(_need(ui, PATIENT["np_accession"], "Accession Number"), accession)
    if birth_date:
        ui.set_text(_need(ui, PATIENT["np_birth_date"], "Birth Date"), birth_date)
    if study_description:
        ui.set_text(_need(ui, PATIENT["np_study_description"], "Study Description"),
                    study_description)

    key = {"F": "np_sex_female", "M": "np_sex_male", "O": "np_sex_other"}.get(
        (sex or "F").upper()[:1])
    if key:
        ui.click(_need(ui, PATIENT[key], "Sex"), settle=0.3)

    return read_new_patient(ui)


def read_new_patient(ui):
    """폼에 실제로 들어간 값을 되읽는다."""
    def txt(name):
        hits = ui.by_id(PATIENT[name])
        return ui.get_text(hits[0]) if hits else None

    proc = ui.by_id(PATIENT["np_procedure_combo"])
    return {
        "study_datetime": txt("np_study_datetime"),
        "patient_id": txt("np_patient_id"),
        "patient_name": txt("np_patient_name"),
        "accession": txt("np_accession"),
        "birth_date": txt("np_birth_date"),
        "age": txt("np_age"),
        "study_description": txt("np_study_description"),
        "procedure": ui.combo_value(proc[0]) if proc else None,
    }


def unique_patient_id(prefix="BF_AUTO"):
    """실행마다 고유한 Patient ID.

    Operation Manual: 이미 등록된 검사에 동일한 Patient ID가 있으면 경고
    메시지가 뜨고, 기존 정보를 쓰거나 ID를 바꿔야 진행할 수 있다.
    자동화는 테스트 간 독립성이 우선이므로 매번 고유 ID를 만들어 경고 자체를
    회피하는 것을 기본으로 한다. 경고 동작 자체를 검증하려면
    handle_duplicate_patient()를 쓴다.
    """
    from datetime import datetime
    return f"{prefix}_{datetime.now():%y%m%d_%H%M%S}"


def handle_duplicate_patient(ui, action="fail", timeout=5):
    """동일 Patient ID 경고 팝업 처리.

    action:
      'fail'         - 팝업 문구를 증적으로 남기고 예외 (기본. 의도치 않은 중복 검출)
      'use_existing' - 기존 검사 정보 사용 (첫 번째 버튼)
      'report'       - 문구만 반환하고 닫지 않음

    버튼 구성이 문서에 명시되어 있지 않으므로, 버튼 텍스트를 그대로 반환해
    호출부가 판단할 수 있게 한다.
    """
    d = ui.wait_dialog(timeout=timeout)
    if not d:
        return None
    texts = [c.text for c in children(d.hwnd, 2) if c.text]
    info = {"title": d.text, "texts": texts}
    if action == "report":
        return info
    if action == "use_existing":
        for c in children(d.hwnd, 2):
            if c.cls == "Button":
                ui.click_button(c.hwnd)
                info["clicked"] = c.text
                return info
        return info
    raise FlowError(f"동일 Patient ID 경고 팝업이 표시되었습니다: {info}")


def start_examine_from_new_patient(ui, wait=8, on_duplicate="fail"):
    """New Patient 화면에서 Examine을 눌러 촬영 모드로 진입한다.

    동일 Patient ID 경고가 뜨면 on_duplicate 정책에 따라 처리한다.
    """
    ui.click(_need(ui, PATIENT["np_examine"], "Examine"), settle=1.5)
    dup = handle_duplicate_patient(ui, action=on_duplicate, timeout=4)
    time.sleep(wait)
    return dup


# 미촬영 View Position이 남은 채 Close를 누르면 나오는 종료 옵션 팝업.
# 문구: "Some View Positions remain uncaptured. Please select a closing option."
# 버튼 문구가 커스텀 렌더링이라 텍스트로 식별할 수 없다.
# 실측 컨트롤 ID (2026-08-10, Bellalun 1.0.12.105):
#   502 = Suspend (좌)   501 = Close (중)   500 = Cancel (우)
# ID가 팝업 종류마다 다를 수 있어 좌→우 순서를 기준으로 하되, ID도 함께 검증한다.
CLOSE_OPTIONS = ("suspend", "close", "discard", "cancel")
CLOSE_OPTION_IDS = {"suspend": 502, "close": 501, "discard": 501, "cancel": 500}


def _visible_close_buttons(ui):
    seen, out = set(), []
    for ctrl_id in (500, 501, 502):
        for c in ui.by_id(ctrl_id):
            l, t, rr, bb = c.rect
            if c.visible and rr - l >= 12 and bb - t >= 12 and c.hwnd not in seen:
                seen.add(c.hwnd)
                out.append(c)
    return sorted(out, key=lambda c: c.rect[0])


def close_examine(ui, option="close", wait=8, evidence_path=None):
    """Examine 모드에서 검사를 종료한다.

    Close 버튼은 강제 종료가 아니라 열려 있는 검사를 닫는 정상 동작이다.
    미촬영 View Position이 남아 있으면 종료 옵션 팝업이 뜨고, 무엇을 고르느냐가
    검사 상태를 바꾸므로 반드시 의도적으로 선택해야 한다.

    사양 근거 (Operation Manual 8.32 검사 보류하기 / 9.19 검사 닫기·보류하기)
      option='suspend' : 검사를 보류한다.
                         "검사를 보류할 경우 촬영 예정이었던 View Position도
                          함께 보류됩니다." 보류 검사는 이후 추가 촬영이나
                          촬영 종료를 위해 다시 열 수 있다.
                         단, Suspend 상태 검사는 Export 할 수 없고
                         DICOM 서버에서는 촬영 중인 검사로 분류된다.
      option='close'   : 검사를 종료한다. Patient 창으로 이동한다.
                         ※ 남은 미촬영 Step을 삭제하는지는 매뉴얼에 명시되어
                           있지 않다. 단정하지 말 것. DATA.SUSPEND_STEP 행 유무로
                           실측해 기록한다.
      option='cancel'  : 종료를 취소하고 Examine 모드에 남는다.

    반환: {"dialog": bool, "option": str|None, "evidence": path|None}
    """
    if option not in CLOSE_OPTIONS:
        raise FlowError(f"알 수 없는 종료 옵션: {option}")

    btn = ui.by_id(EXAMINE["close"])
    if not btn:
        raise FlowError("Close 버튼(2204)을 찾지 못했습니다.")
    ui.click(btn[0], settle=1.5)

    end = time.time() + 6
    d, buttons = None, []
    while time.time() < end:
        d = ui.dialog()
        buttons = _visible_close_buttons(ui)
        if len(buttons) >= 3:
            break
        time.sleep(.25)
    if len(buttons) < 3:
        time.sleep(wait)
        return {"dialog": False, "option": None, "evidence": None}

    if evidence_path and d:
        try:
            ui.capture_dialog(d, evidence_path)
        except Exception:
            evidence_path = None

    target = next((b for b in buttons if b.ctrl_id == CLOSE_OPTION_IDS[option]), None)
    if target is None:
        raise FlowError(f"종료 옵션 '{option}' 버튼을 찾지 못했습니다: "
                        f"{[(b.ctrl_id, b.rect) for b in buttons]}")
    expected_id = CLOSE_OPTION_IDS[option]
    if target.ctrl_id != expected_id:
        raise FlowError(
            f"종료 옵션 '{option}' 버튼의 컨트롤 ID가 예상과 다릅니다 "
            f"(기대 {expected_id}, 실제 {target.ctrl_id}). "
            f"버튼 구성: {[(b.ctrl_id, b.rect[0]) for b in buttons]}. "
            f"잘못된 버튼을 누르지 않도록 중단합니다.")

    ui.click(target, settle=1.5)
    time.sleep(wait)
    if ui.dialog() or len(_visible_close_buttons(ui)) >= 3:
        raise FlowError(f"종료 옵션 '{option}' 선택 후에도 팝업이 남아 있습니다.")
    return {"dialog": True, "option": option, "evidence": evidence_path}


def save_new_patient(ui, wait=3):
    ui.click(_need(ui, PATIENT["np_save"], "Save"), settle=1.5)
    time.sleep(wait)
    return ui.dialog()


def _study_items(ui):
    """StudyListItem을 hwnd 기준으로 중복 제거하고 화면 순서로 반환한다."""
    lists = ui.by_id(PATIENT["study_list"])
    if not lists:
        return []
    seen, items = set(), []
    for c in children(lists[0].hwnd, 3):
        if c.text != "StudyListItem" or not c.visible or c.hwnd in seen:
            continue
        seen.add(c.hwnd)
        items.append(c)
    return sorted(items, key=lambda c: (c.rect[1], c.rect[0]))


def select_study_row(ui, row=1):
    """Patient List / Examined 목록의 N번째 행을 선택한다.

    목록 행은 StudyList(2147) 하위에 StudyListItem 컨트롤 ID 1..9로 존재하며,
    데이터가 없으면 숨김 상태다.
    """
    items = _study_items(ui)
    if not ui.by_id(PATIENT["study_list"]):
        raise FlowError("StudyList 컨트롤을 찾지 못했습니다.")
    if len(items) < row:
        raise FlowError(f"목록에 표시된 행이 {len(items)}개라 {row}번째를 선택할 수 없습니다.")
    ui.click(items[row - 1], settle=0.6)
    return items[row - 1]


def visible_row_count(ui):
    return len(_study_items(ui))


# --- Demo 가상 촬영 ---------------------------------------------------
def step_items(ui):
    """Examine 화면의 촬영 Step(View Position) 썸네일 목록.

    썸네일 패널은 ItemList → ItemWnd → item 으로 중첩돼 있어 트리를 그냥 훑으면
    같은 창이 여러 번 잡힌다. hwnd로 중복을 제거해야 실제 Step 개수가 나온다.
    (중복 제거 전에는 4개 Step이 16개로 보여 두 번째 Step 선택이 첫 번째를
     다시 클릭하는 문제가 있었다)
    """
    panel = ui.by_id(EXAMINE["step_thumbnails"])
    if not panel:
        return []
    seen, items = set(), []
    for c in children(panel[0].hwnd, 3):
        if c.text != "SystemThumbnailItem" or not c.visible:
            continue
        if c.hwnd in seen:
            continue
        seen.add(c.hwnd)
        items.append(c)
    return sorted(items, key=lambda c: c.rect[1])


# Examine 상단 상태 배너(2202). 'Ready'는 녹색, 미준비는 적색으로 표시된다.
READY_GREEN_RATIO = 0.25


def examine_status(ui):
    """촬영 준비 상태 배너를 색으로 판독한다.

    배너 문구는 커스텀 렌더링이라 텍스트로 읽을 수 없다.
    녹색 비율이 높으면 Ready, 아니면 미준비(View Position Not Registered 등).
    """
    from PIL import ImageGrab
    hits = [c for c in ui.by_id(EXAMINE["status_banner"]) if c.visible]
    if not hits:
        return {"ready": None, "green_ratio": None, "detail": "상태 배너 없음"}
    img = ImageGrab.grab(bbox=hits[0].rect, all_screens=True).convert("RGB")
    px = img.load()
    wd, ht = img.size
    green = 0
    for y in range(ht):
        for x in range(wd):
            rr, gg, bb = px[x, y]
            if gg > 110 and gg - rr > 40 and gg - bb > 40:
                green += 1
    ratio = green / float(max(1, wd * ht))
    ready = ratio >= READY_GREEN_RATIO
    return {"ready": ready, "green_ratio": round(ratio, 4),
            "detail": "Ready" if ready else "촬영 준비 안 됨"}


def wait_ready(ui, timeout=20, poll=1.0):
    """촬영 Ready 상태가 될 때까지 대기."""
    end = time.time() + timeout
    st = examine_status(ui)
    while time.time() < end and st.get("ready") is False:
        time.sleep(poll)
        st = examine_status(ui)
    return st


def select_step(ui, index):
    """index번째(1부터) Step을 선택한다."""
    items = step_items(ui)
    if len(items) < index:
        raise FlowError(f"Step이 {len(items)}개라 {index}번째를 선택할 수 없습니다.")
    ui.click(items[index - 1], settle=0.8)
    return items[index - 1]


def demo_acquire_step(ui, index, settle=14, ready_timeout=20):
    """index번째 Step을 선택하고 Ready를 확인한 뒤 1회 가상 촬영한다.

    반환: {"step": index, "ready": bool|None, "green_ratio": float}
    Ready가 아니면 촬영하지 않는다 (미등록 상태에서 F8을 눌러도 영상이
    생기지 않아 '촬영했는데 실패'로 오판정되는 것을 막는다).
    """
    select_step(ui, index)
    st = wait_ready(ui, timeout=ready_timeout)
    info = {"step": index, "ready": st.get("ready"),
            "green_ratio": st.get("green_ratio"), "detail": st.get("detail")}
    if st.get("ready") is False:
        info["skipped"] = True
        return info
    ui.activate()
    ui.key("F8", settle=0.5)
    time.sleep(settle)
    info["skipped"] = False
    return info


def demo_acquire(ui, count=1, settle=14):
    """Demo 모드 가상 촬영 (F8)을 count회 수행한다.

    근거: Service Manual 5.2.3. 실제 X-ray·팬텀 없이 영상이 획득된다.
    주의: 획득 영상의 내용은 선택한 Step과 무관하므로 영상 내용 기반 판정 금지.

    동작 (실측 기준)
      - F8은 현재 선택된 Step 하나만 촬영하고 다음 Step으로 자동 진행하지 않는다.
      - 이미 촬영된 Step은 상태 배너가 Ready가 되지 않으므로 건너뛴다.
      따라서 Step을 순회하며 Ready인 것만 촬영한다.

    반환: 시도한 Step별 결과 리스트.
    """
    ui.activate()
    results = []
    shot = 0
    for idx in range(1, len(step_items(ui)) + 1):
        if shot >= count:
            break
        info = demo_acquire_step(ui, idx, settle=settle)
        results.append(info)
        if not info.get("skipped"):
            shot += 1
    return results
