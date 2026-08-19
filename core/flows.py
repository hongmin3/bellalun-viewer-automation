# -*- coding: utf-8 -*-
"""Viewer 화면 조작 시나리오.

컨트롤 ID는 2026-08-10에 실측한 값이며 `config.json > viewer.control_ids` 와
같은 내용이다. 화면이 바뀌면 `python run.py ui-probe` 로 다시 뜬다.
"""

import os
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

# 메인 메뉴(좌측 하단 ☰). 아이콘 레일과 메뉴 항목의 컨트롤 ID (2026-08-10 실측,
# "qc"는 2026-08-14 사용자 확인으로 수정 - 이전에 "examined"로 잘못 표기돼
# 있었고 실제로는 어디서도 사용되지 않았다. 아이콘 순서는 위에서부터 QC/DICOM/
# Setting/전원이다).
MAIN_MENU = {
    "qc": 58,           # Q.C. 창 (Q.C. Test / Q.C. Results)
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


def open_main_menu(ui, timeout=6, button_timeout=15, attempts=3):
    """메인 메뉴를 연다. 이미 열려 있으면 그대로 둔다.

    메뉴 버튼은 토글이라, 열린 상태에서 다시 누르면 닫힌다.
    상태 확인 없이 누르면 의도와 반대로 동작한다(실제로 발생).

    버튼이 "지금" 없다고 바로 실패하지 않고 `button_timeout`까지 기다린다.
    Setting 창을 닫은 직후 Viewer는 상태 전환 중이어서(실측: 로그에
    `System State Change(110)` 후 `Select Mode` 두 번) 상태바가 아직
    안 그려진 순간이 있다. 2026-08-18 회귀에서 이 때문에 `_prepare()`가
    죽어 XIPL 4건이 연쇄 실패했고, TC_05 단독 실행도 같은 지점에서
    `메인 메뉴 버튼(2015)을 찾지 못했습니다`로 실패했다. 화면이 정말로
    상태바 없는 화면이면 대기 후 동일한 오류로 중단된다.
    """
    if menu_is_open(ui):
        return True
    btn = ui.by_id(STATUS_BAR["menu"])
    end = time.time() + button_timeout
    while not btn and time.time() < end:
        time.sleep(0.5)
        if menu_is_open(ui):
            return True
        btn = ui.by_id(STATUS_BAR["menu"])
    if not btn:
        raise FlowError(
            f"메인 메뉴 버튼(2015)을 {button_timeout}초 동안 찾지 못했습니다. "
            "상태바가 있는 화면인지 확인하십시오.")
    # 토글 클릭이 삼켜지는 경우가 있어(실측: 2026-08-18 회귀에서 버튼은 찾았는데
    # 6초 안에 메뉴가 열리지 않아 XIPL 4건이 `Viewer main menu did not open`으로
    # 연쇄 실패) 한 번 더 눌러 본다. Viewer가 Setting 종료 직후 상태 전환
    # (`System State Change` → `Select Mode`)을 하는 동안 입력을 놓치는 것으로
    # 보인다. 이미 열렸는지 매번 확인하므로 토글을 반대로 눌러 닫을 위험은 없다.
    for attempt in range(attempts):
        if menu_is_open(ui):
            return True
        hits = ui.by_id(STATUS_BAR["menu"])
        if not hits:
            continue
        ui.click(hits[0], settle=1.0)
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


# Setting > Procedure 하위 페이지 (2026-08-14 실측, Bellalun 1.0.12.105)
SETTING_PROCEDURE_PAGES = {"general": 212, "preset": 213, "procedure": 214,
                           "hospital_code": 215}

# Setting > Procedure > General 페이지 Default Parameter 콤보
PROCEDURE_GENERAL_PARAM_2D = 2542
PROCEDURE_GENERAL_PARAM_3D_N = 2543
PROCEDURE_GENERAL_PARAM_3D_W = 2544

# Setting > Procedure > Preset 페이지 (2D 열만 사용)
PRESET_2D_LIST = 2554
PRESET_2D_ADD = 2548
PRESET_2D_DELETE = 2549

# Update 후 뜨는 결과 팝업(성공/오류 공통)의 OK 버튼
SETTING_CONFIRM_OK = 500


def open_procedure_setting(ui, page, wait=1.5):
    """Setting > Procedure > <page> 로 이동한다.

    page: general | preset | procedure | hospital_code
    """
    if page not in SETTING_PROCEDURE_PAGES:
        raise FlowError(f"알 수 없는 Procedure 설정 페이지: {page}")
    open_setting(ui, wait=3.0)
    open_setting_group(ui, "procedure", wait=2.0)
    return _click_setting_control(ui, SETTING_PROCEDURE_PAGES[page],
                                  f"Procedure 설정 '{page}'", wait)


# Setting > Q.C 하위 페이지 (2026-08-14 실측, Bellalun 1.0.12.105)
SETTING_QC_PAGES = {"setting_2d": 238, "setting_3d": 239, "scheduler": 240,
                    "auto_delete": 241, "regular_inspection": 242}

# Setting > Q.C > Setting / Setting (3D) 페이지의 Default Image Process
# Parameter 콤보
QC_PARAM_2D = 2704
QC_PARAM_3D = 2707


def open_qc_setting(ui, page, wait=1.5):
    """Setting > Q.C > <page> 로 이동한다.

    page: setting_2d | setting_3d | scheduler | auto_delete | regular_inspection
    """
    if page not in SETTING_QC_PAGES:
        raise FlowError(f"알 수 없는 Q.C 설정 페이지: {page}")
    open_setting(ui, wait=3.0)
    open_setting_group(ui, "qc", wait=2.0)
    return _click_setting_control(ui, SETTING_QC_PAGES[page],
                                  f"Q.C 설정 '{page}'", wait)


def open_qc_tool(ui, wait=2.0):
    """메인 메뉴 → Q.C. 창(Q.C. Test / Q.C. Results)을 연다.

    Welcome 화면의 'Today Q.C.'는 예정된 검사 일정만 보여주는 별도 화면이다.
    실제 ACR Phantom 등 개별 Q.C. Test를 실행하는 창은 이 메인 메뉴 경로로만
    들어갈 수 있다(2026-08-14 사용자 확인).
    """
    return _click_menu(ui, "qc", wait)


def confirm_setting_dialog(ui, wait=1.5, timeout=6):
    """Update 후 뜨는 결과 팝업의 OK를 누른다. 팝업이 없으면 조용히 넘어간다."""
    end = time.time() + timeout
    while time.time() < end:
        ok = [c for c in ui.by_id(SETTING_CONFIRM_OK) if c.visible]
        if ok:
            ui.click(ok[0], settle=wait)
            return True
        time.sleep(.3)
    return False


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
        # 비밀번호는 물리 키 입력으로 넣기 때문에(ui.type_text 주석 참고), Viewer
        # 기동 직후 포커스가 완전히 잡히기 전에는 일부 문자가 유실돼 "Wrong ID or
        # password" 팝업이 뜨는 일이 있다(2026-08-14 회귀에서 실제 발생, 같은
        # 자격증명으로 직전/직후 로그인은 성공). 한 번의 유실로 회귀 전체가
        # 무너지지 않게 다시 타이핑해서 재시도한다.
        #
        # ACCOUNT 테이블에는 실패 횟수/잠금 컬럼이 없어(Key/System/Group/ID/
        # Password/Name) 재시도로 계정이 잠길 위험은 없다. 그래도 진짜 잘못된
        # 자격증명을 무한히 덮지 않도록 횟수를 제한하고, 소진되면 기존과 똑같이
        # 명확한 FlowError로 중단한다.
        # 성공 판정은 "실제로 로그인 화면을 벗어났는가"로 한다. 팝업이 떴다는
        # 사실만으로 실패로 단정하면, 늦게 뜬 Demo 모드 안내 같은 무해한 팝업에도
        # 회귀 전체가 중단된다. 대신 걷어낸 팝업 문구는 로그로 남겨 추적 가능하게
        # 하고, 로그인하지 못한 경우에만 재시도/중단한다.
        attempts = int((cfg["viewer"].get("login_attempts") or 3))
        for attempt in range(1, attempts + 1):
            # Viewer를 최전면으로 올린다. 비밀번호는 물리 키 입력이라 포커스가
            # 다른 창에 있으면 키가 그 창으로 들어간다.
            #
            # **실패해도 중단하지 않는다.** 기동 직후에는 최전면이 데스크톱인
            # 정상 순간이 있고, 여기서 중단하면 멀쩡한 실행을 막는다(2026-08-19
            # 회귀에서 `Program Manager`를 가림으로 오판해 14개 TC가 연쇄 FAIL).
            # 결과만 기동 로그에 남기고, 로그인이 **최종 실패했을 때** 그 정보를
            # 오류 메시지에 실어 "가려져서 실패했는지"를 알 수 있게 한다.
            front = ui.bring_to_front()
            if not front["ok"]:
                blocking = front.get("blocking")
                say("Viewer가 최전면이 아닙니다" +
                    (f" — 가리고 있는 창: {blocking['title']!r} "
                     f"(PID {blocking['pid']})" if blocking else
                     " (셸/미확인 창이 전면)"))
            say(f"로그인: {login['id']}" + (f" (재시도 {attempt - 1})" if attempt > 1 else ""))
            ok = ui.login(login["id"], login["password"])
            popped = guard.sweep()
            msgs = "; ".join(p["message"] or "(문구 미노출)" for p in popped)
            if ok and not ui.at_login_screen():
                if popped:
                    say(f"로그인 중 팝업을 닫았습니다(로그인은 성공): {msgs}")
                break
            if attempt >= attempts:
                detail = f"마지막 팝업: {msgs} " if popped else ""
                # 가려져서 실패한 것인지 바로 알 수 있게 최전면 창을 함께 남긴다.
                front_now = ui.foreground_window()
                occluded = ""
                if front_now and front_now["pid"] != ui.pid:
                    occluded = (f" 최전면 창이 Viewer가 아닙니다: "
                                f"{front_now['title']!r} (PID {front_now['pid']}). "
                                "비밀번호는 물리 키 입력이라 다른 창이 포커스를 쥐고 "
                                "있으면 키가 그 창으로 들어갑니다 — 그 창을 닫거나 "
                                "최소화한 뒤 다시 실행하십시오.")
                raise FlowError(
                    f"로그인에 {attempts}회 실패했습니다. {detail}"
                    f"(증적은 Evidence/ui 참조). 계정/비밀번호를 확인하십시오.{occluded}")
            say(f"로그인 재시도 예정 (원인: {msgs or '로그인 화면 유지'})")
            time.sleep(1.5)
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


def _need(ui, ctrl_id, what, timeout=20):
    """컨트롤을 찾는다. 없으면 `timeout`까지 기다린 뒤에야 실패로 본다.

    Viewer는 화면 전환 중(특히 Setting 창을 닫은 직후) 목표 화면의 컨트롤이
    아직 붙지 않은 순간이 있다. 한 번만 조회하고 실패하면 화면 자체가 잘못된
    것과 구분되지 않는다(2026-08-18 실측: Overlay 설정 후 New Patient 탭
    (2285)을 못 찾아 TC_04가 중단됐다). 화면이 정말 다르면 대기 후 같은
    오류로 중단된다.

    기본 상한을 8초에서 20초로 올렸다. 8초로는 부족했다 — 2026-08-18 8차 회귀에서
    `TC_XIPL_compatibility_04`가 `setting_update` + `confirm_setting_dialog` 직후
    2285를 8초 안에 못 찾아 중단됐다(같은 TC가 7차에서는 통과했으므로 화면이
    잘못된 게 아니라 **전환이 8초보다 느렸던 것**이다).

    실패 메시지에는 **지금 어떤 화면인지**를 함께 남긴다. 컨트롤 ID만 알려주면
    "화면이 다른 것"과 "아직 안 그려진 것"을 구분하러 매번 사람이 다시 재현해야
    한다.
    """
    hits = ui.by_id(ctrl_id)
    end = time.time() + timeout
    while not hits and time.time() < end:
        time.sleep(.4)
        hits = ui.by_id(ctrl_id)
    if not hits:
        raise FlowError(
            f"{what} 컨트롤(ID {ctrl_id})을 {timeout}초 동안 찾지 못했습니다. "
            + _screen_context(ui))
    return hits[0]


def _screen_context(ui):
    """실패 시점의 화면 상태를 한 줄로 만든다(랜드마크 + 열린 대화상자 + 캡처).

    랜드마크만으로는 부족했다. 2026-08-19 회귀에서 `TC_XIPL_compatibility_04`가
    `랜드마크=['status_bar','examine']`로 실패했는데, 같은 상태를 직접 만들어
    재현하니 정상 동작했다. 남은 차이가 **모달 대화상자**일 가능성이 크지만
    실패 시점 증적이 없어 확인할 수 없었다(이 저장소에서 모달이 클릭을 삼키는
    문제는 반복 확인됐다 - 운영 지침 11절).

    그래서 실패 순간에 (1) 랜드마크, (2) 열려 있는 대화상자 문구, (3) 전체 화면
    캡처를 남긴다. 다음 발생 때는 한 번에 원인을 지목할 수 있어야 한다.
    """
    parts = [f"화면 랜드마크={known_screen(ui) or '없음'}"]
    try:
        dialog = ui.dialog()
    except Exception:
        dialog = None
    if dialog:
        message = ""
        try:
            from core.ui import children
            texts = [c.text for c in children(dialog.hwnd, 3)
                     if c.visible and c.text and len(c.text) > 3]
            message = " | ".join(texts[:4])
        except Exception:
            pass
        parts.append(f"열린 대화상자={dialog.text!r} {message!r}"
                     " <- 모달이 클릭을 삼켰을 수 있다")
    else:
        parts.append("열린 대화상자=없음")
    try:
        from core import screen
        from PIL import ImageGrab
        path = os.path.join("Evidence", "ui", "need_failed.png")
        screen.grab(ImageGrab.grab(all_screens=True).getbbox(), path=path)
        parts.append(f"캡처={path}")
    except Exception as exc:
        parts.append(f"캡처 실패={exc}")
    return ". ".join(parts) + "."


# --- Patient 화면 -----------------------------------------------------
def open_new_patient_tab(ui, timeout=8):
    ui.activate()
    # **탭을 찾기 전에 Patient 화면으로 이동한다.** 이전에는 곧바로 2285를 찾아서,
    # 검사가 열린 Examine 화면에서 부르면 "탭을 못 찾았다"로 죽었다
    # (2026-08-19 10차 회귀에서 `TC_XIPL_compatibility_04`가 이렇게 실패했고,
    #  실패 메시지의 랜드마크가 `['status_bar', 'examine']`이었다).
    #
    # 대기 부족이 아니었다 — 상한을 20초로 늘려도 같은 실패였다. 화면 이동을
    # 시도하지 않은 것이 원인이고, `ensure_patient_screen`이 메인 메뉴로 이동해
    # 해결한다(그 화면에서 실제로 2285가 나타나는 것을 실측 확인).
    ensure_patient_screen(ui)
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


def known_screen(ui):
    """지금 화면에서 알아볼 수 있는 랜드마크를 돌려준다(없으면 빈 리스트).

    "어느 화면인지 판별 가능한가"를 재는 용도다. 하나도 없으면 아직 화면이
    그려지지 않은 것이므로 어떤 조작도 하면 안 된다.
    """
    found = []
    for name, ctrl_id in (("patient", PATIENT["tab_new_patient"]),
                          ("welcome", WELCOME["examine"]),
                          ("status_bar", STATUS_BAR["menu"]),
                          ("setting", SETTING_UPDATE_BUTTON),
                          ("examine", EXAMINE["close"])):
        if ui.by_id(ctrl_id):
            found.append(name)
    return found


def wait_known_screen(ui, timeout=60, poll=1.0):
    """알아볼 수 있는 화면이 나타날 때까지 기다린다. 반환: 랜드마크 목록."""
    end = time.time() + timeout
    while True:
        found = known_screen(ui)
        if found or time.time() >= end:
            return found
        time.sleep(poll)


def wait_controls(ui, ctrl_ids, timeout=15, poll=0.5):
    """지정한 컨트롤이 **모두** 보일 때까지 기다린다.

    화면을 연 직후 컨트롤을 즉시 조회해 "없다"고 판정하면, 아직 그려지지
    않았을 뿐인데 실패로 찍힌다. 이 저장소에서 반복된 결함 형태다.

    반환: {ctrl_id: 보이는 컨트롤 수} — 하나라도 0이면 시간 안에 못 나온 것.
    """
    end = time.time() + timeout
    while True:
        found = {cid: len([c for c in ui.by_id(cid) if c.visible])
                 for cid in ctrl_ids}
        if all(found.values()) or time.time() >= end:
            return found
        time.sleep(poll)


def ensure_patient_screen(ui, wait=5, settle_timeout=60):
    """Welcome/Setting/Examine 어느 화면에서 시작해도 Patient 화면으로 이동.

    **먼저 화면이 그려지기를 기다린다.** 로그인 직후에는 랜드마크 컨트롤이 아직
    하나도 없을 수 있는데, 그 순간에 곧바로 네비게이션을 시작하면
    `open_main_menu`가 상태바를 못 찾아 15초 뒤 실패한다. 2026-08-18 회귀에서
    실제로 이 지점이 무너졌다 - DB 복원 직후 강제 재기동한 Viewer가 화면을
    그리기 전에 이 함수가 판단을 내려 DICOM 등록이 실패하고, 그 결과 MWL 서버가
    미등록 상태로 남아 **8개 TC가 연쇄 FAIL**했다(PASS 121 -> 30). 정작 Viewer는
    잠시 뒤 정상이어서 뒤이은 TC_XIPL_04/05는 통과했다.

    고정 sleep이 아니라 **랜드마크 출현이라는 실제 신호**를 상한을 두고 기다린다.

    반환값은 기존과 같은 bool을 유지한다(예외를 던지면 `tests/ui_flows.py`처럼
    try 밖에서 부르는 호출부가 깨진다). 실패 원인이 필요하면 호출부에서
    `known_screen(ui)`를 함께 보고하면 된다 - `core/dicom_settings.py`가 그렇게 한다.
    """
    if not wait_known_screen(ui, timeout=settle_timeout):
        return False
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
        # Setting을 벗어날 때 잔여 변경이 있으면 저장 확인 팝업이 뜬다. 방치하면
        # 모달이 이후 모든 클릭을 삼킨다(2026-08-19 실측).
        confirm_config_save(ui, save=False, timeout=3)
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
    kids = children(d.hwnd, 3)
    texts = [c.text for c in kids if c.text]
    info = {"title": d.text, "texts": texts}
    if action == "report":
        return info
    if action == "use_existing":
        # 이 팝업의 버튼("Use existing data" / "Change current ID")은 표준
        # Button이 아니라 커스텀 렌더링 컨트롤이다. 예전 구현은 cls=="Button"만
        # 찾다가 **아무것도 클릭하지 못하고 조용히 반환**했고, 모달이 남아 이후
        # 모든 클릭이 막혔다(2026-08-18 실측: TC_04 재실행에서 Step 6이
        # "Step 등록 실패: 0->4"로 깨진 진짜 원인).
        #
        # ID를 하드코딩하지 않고 기하로 고른다. 제목줄의 X를 누르면 의도(기존
        # 데이터 사용)와 다르게 취소되므로 **대화상자 아래쪽 절반**만 후보로 삼고,
        # 위→아래·좌→우로 정렬해 왼쪽 버튼(=Use existing data)을 먼저 누른다.
        # 그리고 **모달이 실제로 닫혔는지 확인**한다.
        dl, dt, dr, db = d.rect
        midline = dt + (db - dt) // 2
        cands = [c for c in kids
                 if c.visible and c.rect[1] >= midline
                 and (c.rect[2] - c.rect[0]) >= 60
                 and 20 <= (c.rect[3] - c.rect[1]) <= 90]
        cands.sort(key=lambda c: (c.rect[1], c.rect[0]))
        for c in cands:
            ui.click(c, settle=1.0)
            if not ui.dialog():
                info["clicked"] = {"ctrl_id": c.ctrl_id, "rect": c.rect,
                                   "text": c.text}
                return info
        raise FlowError(
            f"동일 Patient ID 팝업을 닫지 못했습니다(후보 {len(cands)}개): {info}")
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


def confirm_study_delete(ui, accept=True, timeout=4):
    """"This study will be deleted. Are you sure?" 확인 팝업을 처리한다.

    영상이 없는 검사를 Close할 때만 나타난다(영상이 있으면 나타나지 않는다).
    버튼은 커스텀 렌더링이라 좌=Yes(501), 우=Cancel(500)로 실측됐다. ID를
    맹신하지 않고 좌우 순서와 ID를 함께 확인해 Yes를 누른다.

    accept=False면 Cancel을 눌러 삭제하지 않는다. 팝업이 없으면 None.
    """
    end = time.time() + timeout
    buttons = []
    while time.time() < end:
        buttons = _visible_close_buttons(ui)
        if ui.dialog() and len(buttons) == 2:
            break
        time.sleep(.3)
    if not (ui.dialog() and len(buttons) == 2):
        return None
    yes, cancel = buttons[0], buttons[1]
    target = yes if accept else cancel
    expected = 501 if accept else 500
    if target.ctrl_id != expected:
        raise FlowError(
            f"검사 삭제 확인 버튼 구성이 예상과 다릅니다 "
            f"(기대 {expected}, 실제 {target.ctrl_id}, "
            f"버튼={[(b.ctrl_id, b.rect[0]) for b in buttons]}). "
            f"잘못된 버튼을 누르지 않도록 중단합니다.")
    ui.click(target, settle=1.5)
    return {"accepted": bool(accept), "ctrl_id": target.ctrl_id}


UNSAVED_CHANGES_MARKERS = ("there are changes", "do you like to save")
CONFIG_SAVE_MARKERS = ("save changed configuration", "changed configuration")
CONFIG_SAVE_IDS = {"yes": 502, "no": 501, "cancel": 500}
STUDY_DELETE_MARKERS = ("will be deleted", "are you sure")


def read_dialog_message(ui, dialog, tesseract_exe=None):
    """대화상자 문구를 **OCR로** 읽는다.

    `ui.dialog_text()`(WM_GETTEXT)는 이 제품의 커스텀 팝업에서 **빈 문자열만**
    돌려준다(2026-08-19 실측: `dialog.text=''`, `dialog_text=''`, 하위 컨트롤은
    `AfxWnd140u`/`TextButton`뿐). 그래서 문구로 팝업을 구분하려면 화면을 읽어야
    한다.

    문구는 팝업 높이의 대략 30~70% 구간에 있다(버튼은 그 아래). 창 위치·크기가
    달라져도 되도록 **팝업 rect에 대한 비율**로 잘라낸다.
    """
    if not dialog:
        return ""
    if tesseract_exe:
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_exe
        except Exception:
            pass
    left, top, right, bottom = dialog.rect
    height = bottom - top
    if height <= 0:
        return ""
    box = (left + 10, top + int(height * 0.30),
           right - 10, top + int(height * 0.70))
    try:
        from core import screen
        return (screen.ocr(box, scale=3, psm=6) or "").strip()
    except Exception:
        return ""


def confirm_config_save(ui, save=False, timeout=6, tesseract_exe=None):
    """"Do you want to save changed configuration?" 팝업을 처리한다.

    Setting 화면을 벗어날 때 변경이 남아 있으면 뜬다. 방치하면 **모달이 이후 모든
    클릭을 삼켜** "메인 메뉴가 열리지 않았습니다" 같은 엉뚱한 증상으로 죽는다
    (2026-08-19 실측).

    버튼은 좌 502(Yes) / 중 501(No) / 우 500(Cancel)로 실측됐다. 이 저장소의 3버튼
    순서 규약(`CLOSE_OPTION_IDS`)과 같다.

    `save=False`(기본)는 **No** — 저장하지 않는다. 자동화가 의도한 설정 변경은 항상
    `setting_update()`로 **명시적으로** 저장한다. 이 팝업이 뜨는 상황은 그 경로를
    타지 않은 잔여 변경이라는 뜻이므로, 저장하면 의도하지 않은 설정이 남는다.

    문구는 OCR로 읽는다(이 제품의 커스텀 팝업은 WM_GETTEXT로 빈 문자열만 준다).
    문구를 확정하지 못하면 **누르지 않고** None을 돌려준다 — 3버튼 팝업은 검사 종료
    옵션(Suspend/Close/Cancel)과 구성이 같아서, 잘못 누르면 검사 상태를 바꾼다.

    반환: {"saved": bool, "ctrl_id": int, "message": str} / 해당 팝업이 없으면 None.
    """
    end = time.time() + timeout
    dialog, buttons = None, []
    while time.time() < end:
        dialog = ui.dialog()
        buttons = _visible_close_buttons(ui)
        if dialog and len(buttons) == 3:
            break
        time.sleep(.3)
    if not (dialog and len(buttons) == 3):
        return None

    message = read_dialog_message(ui, dialog, tesseract_exe)
    if not any(m in message.lower() for m in CONFIG_SAVE_MARKERS):
        # 다른 3버튼 팝업(예: 검사 종료 옵션)이다. 건드리지 않는다.
        return None

    key = "yes" if save else "no"
    expected = CONFIG_SAVE_IDS[key]
    target = next((b for b in buttons if b.ctrl_id == expected), None)
    if target is None:
        raise FlowError(
            f"설정 저장 확인 팝업에서 '{key}' 버튼(ID {expected})을 찾지 못했습니다"
            f"(버튼={[(b.ctrl_id, b.rect[0]) for b in buttons]}, 문구={message!r}). "
            "잘못된 버튼을 누르지 않도록 중단합니다.")
    ui.click(target, settle=1.5)
    return {"saved": bool(save), "ctrl_id": target.ctrl_id, "message": message}


def confirm_unsaved_changes(ui, save=True, timeout=6, tesseract_exe=None):
    """"There are changes. Do you like to save them?" 저장 확인 팝업을 처리한다.

    **발견 경위 (2026-08-19)**: `TC_XIPL_compatibility_04`가 회귀에서만 3회 연속
    같은 지점에서 실패했다. 두 번 잘못 짚은 뒤(대기 시간, 열린 검사) 실패 시점
    캡처를 남기게 하고서야 원인이 보였다 — Close를 누르면 제품이 이 팝업을 띄우는데
    아무도 답하지 않아 **모달이 이후 모든 클릭을 삼켰다.**

    `close_examine`은 종료 옵션 팝업(Close/Suspend/Cancel, 버튼 3개)만 알고 있어서
    버튼이 3개 미만이면 그냥 반환했다. 이 팝업은 Yes/No 2개다.

    **2버튼 팝업이 두 종류라 문구로 구분한다.** 같은 상황에서
    "This study will be deleted. Are you sure?"(`confirm_study_delete`)도 2버튼으로
    뜬다. 문구를 확인하지 않고 누르면 엉뚱한 팝업의 버튼을 누른다.

    `save=True`(기본)는 **Yes** — 변경을 저장한다. 이 저장소의 기존 판단과 같은
    방향이다(`close_examine`이 데이터를 잃지 않는 Suspend를 택하는 이유와 동일).
    공용 픽스처의 영상 조정 상태는 `WF_02` Expected 6/7과 `WF_08` Film 출력 비교가
    쓰므로, 버리면 뒤 TC의 근거가 흔들린다.

    버튼은 커스텀 렌더링이고 **좌=Yes(501), 우=No(500)** 로 실측됐다
    (2026-08-19: 팝업 rect (728,440,1192,641), Yes x=835, No x=965).
    `confirm_study_delete`와 같은 방식으로 **좌우 순서와 컨트롤 ID를 함께 확인**하고,
    다르면 클릭하지 않고 중단한다.

    **문구는 OCR로 읽는다.** `ui.dialog_text()`는 이 팝업에서 빈 문자열만 준다
    (실측). 처음 구현할 때 이걸 몰라서 문구 검사가 항상 실패했고, 핸들러가
    발동하지 않아 같은 실패가 한 번 더 났다.

    반환: {"saved": bool, "ctrl_id": int, "message": str} / 팝업 없으면 None.
    """
    end = time.time() + timeout
    dialog, buttons = None, []
    while time.time() < end:
        dialog = ui.dialog()
        buttons = _visible_close_buttons(ui)
        if dialog and len(buttons) == 2:
            break
        time.sleep(.3)
    if not (dialog and len(buttons) == 2):
        return None

    message = read_dialog_message(ui, dialog, tesseract_exe)
    low = message.lower()
    if any(m in low for m in STUDY_DELETE_MARKERS):
        # "This study will be deleted. Are you sure?" 다. 여기서 좌측(501)을
        # 누르면 **검사가 삭제된다.** 저장 확인과 버튼 구성이 같으므로 문구로
        # 구분하지 못하면 절대 누르지 않는다. 처리는 confirm_study_delete가 한다.
        return None
    if not any(m in low for m in UNSAVED_CHANGES_MARKERS):
        raise FlowError(
            "Close 직후 2버튼 팝업이 떴지만 문구를 확정하지 못했습니다"
            f"(OCR={message!r}, 버튼={[(b.ctrl_id, b.rect[0]) for b in buttons]}). "
            "저장 확인 팝업과 검사 삭제 확인 팝업은 버튼 구성이 같아서, 문구를 "
            "읽지 못한 상태로 누르면 검사를 삭제할 수 있습니다. 안전하게 중단합니다.")

    yes, no = buttons[0], buttons[1]
    target = yes if save else no
    expected = 501 if save else 500
    if target.ctrl_id != expected:
        raise FlowError(
            f"저장 확인 팝업의 버튼 구성이 예상과 다릅니다 "
            f"(기대 {expected}, 실제 {target.ctrl_id}, "
            f"버튼={[(b.ctrl_id, b.rect[0]) for b in buttons]}, 문구={message!r}). "
            f"잘못된 버튼을 누르지 않도록 중단합니다.")
    ui.click(target, settle=1.5)
    return {"saved": bool(save), "ctrl_id": target.ctrl_id, "message": message}


def close_examine(ui, option="close", wait=8, evidence_path=None,
                  save_changes=True, tesseract_exe=None):
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

    # Close를 누르면 영상 변경사항이 있을 때 "There are changes. Do you like to
    # save them?"이 **먼저** 뜬다. 이 팝업은 버튼이 2개라 아래 종료 옵션 판별
    # (3개 필요)에 걸리지 않고, 방치하면 모달이 이후 모든 클릭을 삼킨다
    # (2026-08-19 회귀에서 TC_XIPL_04가 이 때문에 3회 연속 실패했다).
    unsaved = confirm_unsaved_changes(ui, save=save_changes,
                                     tesseract_exe=tesseract_exe)

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
        return {"dialog": False, "option": None, "evidence": None,
                "unsaved_changes": unsaved}

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
    # 촬영 영상이 없는 검사를 Close하면 "This study will be deleted. Are you
    # sure?"(Yes/Cancel) 확인이 한 번 더 뜬다(2026-08-18 실측). 이걸 처리하지
    # 않으면 "팝업이 남아 있습니다"로 실패하고 화면도 막힌다.
    # 사용자 승인(2026-08-18): 영상이 없는 검사는 삭제해도 된다 — 영상이 있으면
    # 이 확인 자체가 뜨지 않으므로, 여기서 Yes를 누르는 것은 빈 검사에만 해당한다.
    confirm = confirm_study_delete(ui, accept=(option in ("close", "discard")))
    if confirm:
        time.sleep(1.5)
    if ui.dialog() or len(_visible_close_buttons(ui)) >= 3:
        raise FlowError(
            f"종료 옵션 '{option}' 선택 후에도 팝업이 남아 있습니다."
            + (f" (검사 삭제 확인 처리: {confirm})" if confirm else ""))
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


def select_step(ui, index, scroll_tries=8):
    """index번째(1부터) Step을 선택한다.

    썸네일 패널은 스크롤되며, 스텝이 4개를 넘으면 아래쪽 카드는 패널 밖으로
    잘린다. Win32 IsWindowVisible은 잘린 카드도 visible로 보고하므로
    step_items()에는 잡히지만, 그 카드의 center를 클릭하면 좌표가 패널 밖이라
    선택이 바뀌지 않는다. 실측(5스텝, 3D-W)에서 이 상태로 F8을 누르면 의도한
    Step이 아니라 기존 선택 Step이 촬영돼 조용히 오판정됐다. 그래서 대상
    카드의 center가 패널 안에 들어올 때까지 스크롤한 뒤에 클릭한다.
    """
    items = step_items(ui)
    if len(items) < index:
        raise FlowError(f"Step이 {len(items)}개라 {index}번째를 선택할 수 없습니다.")
    panel = ui.by_id(EXAMINE["step_thumbnails"])
    if panel:
        seen = None
        for attempt in range(scroll_tries):
            panel = ui.by_id(EXAMINE["step_thumbnails"]) or panel
            pl, pt, pr, pb = panel[0].rect
            current = step_items(ui)
            if len(current) >= index:
                target = current[index - 1]
                _, cy = target.center
                seen = (target.rect, panel[0].rect)
                if pt <= cy <= pb:
                    ui.click(target, settle=0.8)
                    return target
                # 패널 밖이면 두 가지 경우가 있다. (1) 정말 스크롤로 잘린 경우
                # (스텝 5개 이상) → 해당 방향으로 굴리면 들어온다. (2) Examine
                # 화면이 막 만들어져 카드 좌표가 아직 배치되지 않은 경우 →
                # 실측(2스텝 픽스처)에서 첫 카드가 panel(y 135~923)보다 위인
                # y -221~-46으로 보고된 적이 있다. 2스텝은 패널에 다 들어가므로
                # 스크롤 문제가 아니라 과도 상태다. 그래서 굴리기만 반복하지
                # 않고 매 회 **실제로 기다렸다가 다시 읽는다.**
                ui.wheel(((pl + pr) // 2, (pt + pb) // 2),
                         -3 if cy > pb else 3, settle=.3)
            time.sleep(.6)
        raise FlowError(
            f"{index}번째 Step 카드가 {scroll_tries}회 시도 후에도 패널 안에 "
            f"들어오지 않았습니다: card/panel={seen}")
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


# --- DICOM Send -------------------------------------------------------
# "전송할 영상을 선택합니다. 메시지 박스에서 All Image, Selected 또는 Cancel
# 버튼을 클릭하십시오." (Operation Manual 8.19 영상 전송하기)
# 실측 컨트롤 ID (2026-08-18, Bellalun 1.0.12.105) — 종료 옵션 팝업과 같은
# 좌→우 체계를 쓴다.
SEND_SCOPE_IDS = {"all": 502, "selected": 501, "cancel": 500}


def send_current_study(ui, scope="all", attempts=4, dialog_timeout=5):
    """Examine 화면에서 선택한 검사/영상을 DICOM Storage로 전송한다.

    사양(Operation Manual 8.19)이 요구하는 전제와 실측으로 확인한 함정을 모두
    반영한다.

    * **영상을 먼저 선택해야 한다.** 선택 전에는 Send 버튼(1148)이 비활성이라
      눌러도 아무 일도 일어나지 않는다(실측: 아이콘이 연한 분홍으로 표시됨).
      호출 전에 `select_step()` 등으로 대상을 선택해 둘 것.
    * **첫 클릭이 삼켜지는 일이 있다.** 그래서 "All Images/Selected" 메시지
      박스가 뜨는지 확인하며 상한을 두고 재시도한다(실측: 1회차 무반응,
      2회차에 등장). 이 저장소에서 반복 확인된 패턴이다.

    반환: {"scope": ..., "clicked": ctrl_id} / 메시지 박스가 안 뜨면 FlowError.
    """
    if scope not in SEND_SCOPE_IDS:
        raise FlowError(f"알 수 없는 전송 범위: {scope}")
    target_id = SEND_SCOPE_IDS[scope]

    for _ in range(attempts):
        buttons = [c for c in ui.by_id(EXAMINE["tool_send"]) if c.visible]
        if not buttons:
            raise FlowError(
                f"Send 버튼({EXAMINE['tool_send']})을 찾지 못했습니다. "
                "Tool 레일이 펼쳐져 있는지 확인하십시오.")
        ui.click(buttons[0], settle=2.0)
        end = time.time() + dialog_timeout
        while time.time() < end:
            hits = [c for c in ui.by_id(target_id) if c.visible]
            if hits:
                ui.click(hits[0], settle=2.5)
                return {"scope": scope, "clicked": target_id}
            time.sleep(.5)
    raise FlowError(
        f"Send 후 전송 범위 선택 메시지 박스가 {attempts}회 시도에도 "
        f"나타나지 않았습니다. 전송할 영상이 선택돼 있는지 확인하십시오"
        f"(선택 전에는 Send 버튼이 비활성입니다).")
