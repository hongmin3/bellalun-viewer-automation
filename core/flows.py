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
    # 2026-08-20 **툴팁으로 확정** — 이전 기록("procedure_add 2208 / 
    # procedure_delete 2207")은 **둘 다 틀렸다.** 아이콘 모양으로 추정한 결과였고,
    # 실제는 Implant 표시 버튼이다. 이 저장소의 아이콘 추정 오류 세 번째 사례
    # (앞선 둘: 2184 를 Send 로 추정했으나 Import Study, 2196 을 검사 내 검색으로
    # 추정했으나 Pre-send Preview).
    "implant_right": 2208,        # 툴팁 "Right Implant"
    "implant_left": 2207,         # 툴팁 "Left Implant"
    # Procedure 라벨 옆 두 버튼 (2026-08-20 툴팁으로 확정). WF_11 의 진입점이다.
    "reject_image": 1168,         # 툴팁 "Reject Image" — 휴지통 모양
    "multi_select": 1169,         # 툴팁 "Multi Select"
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


def setting_is_open(ui):
    """Setting 화면이 **이미 열려 있는가.**

    최상위 창 중 큰 `#32770` 을 찾아 **직계 자식**에 그룹 레일의 System(177)이
    있는지만 본다. `ui.by_id` 처럼 전체 트리를 훑지 않으므로 싸다(실측 0.1초).
    Export/Import 저장 대화상자도 `#32770` 이지만 작고 177 이 없어 걸리지 않는다.
    """
    from core.ui import children

    for w in ui.windows():
        if w.cls != "#32770" or not w.visible:
            continue
        if w.rect[2] - w.rect[0] < 800 or w.rect[3] - w.rect[1] < 500:
            continue
        for c in children(w.hwnd, 1):
            if c.ctrl_id == SETTING_GROUPS["system"] and c.visible:
                return True
    return False


def open_setting(ui, wait=4.0):
    """메인 메뉴 → Setting 화면으로 이동한다. **이미 열려 있으면 누르지 않는다.**

    2026-08-25 사용자 지적: 그룹을 옮길 때마다 좌측 하단 메뉴 버튼과 Setting 을
    다시 눌렀다. `setting_values.read_all` 은 9개 그룹을 도므로 한 회차에 9번,
    WF_14 은 두 회차라 **18번을 헛눌렀다**(회차당 약 1분). 이미 열린 창을 다시
    열려고 모달 뒤의 메뉴를 누르는 것이라 느릴 뿐 아니라 위험하다.

    `open_system_setting` / `open_dicom_setting` 등 8개 헬퍼가 모두 이 함수를
    무조건 부르므로, 여기서 한 번 막으면 전부 고쳐진다.
    """
    if setting_is_open(ui):
        return True
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
    # 화면 라벨을 캡처로 확인했다(2026-08-19,
    # `Evidence/ui/probe_setting_dicom_general.png`).
    "study_close_option": 2444,      # "Study close option on Examine mode" 콤보
    "urgent_auto_send_yes": 2446,    # "Send urgent patient automatically" Yes
    "urgent_auto_send_no": 2445,     # 같은 항목 No (제품 기본값)
    "validate_study_uid_yes": 2448,  # "Validate study instance UID" Yes (기본값)
    "validate_study_uid_no": 2447,
    "long_accession_no": 2449,       # "Allow long accession number" No (기본값)
    "ip_address": 2436,              # 읽기 전용
    "station_name": 2434,
    "station_ae_title": 2435,
    "station_port": 2437,
}


def _click_setting_control(ui, ctrl_id, what, wait=1.5, timeout=15):
    """Setting 화면의 컨트롤을 누른다. **나타날 때까지 상한을 두고 기다린다.**

    Setting 창을 막 열었거나 방금 닫았다 다시 연 직후에는 그룹/페이지 레일이
    아직 그려지지 않은 순간이 있다. 2026-08-25 실측: UPS 설정을 바꾸느라 Setting
    을 한 번 더 여닫은 뒤 `Setting > System > My Settings`(193)를 찾지 못해 TC 가
    Step 4 에서 중단됐다. 고정 대기를 늘리는 대신 **실제로 나타나는 것**을
    기다린다.

    상한을 8초에서 15초로 올렸다(2026-08-28). 짧은 시간에 Viewer 를 반복
    강제 재기동하며 여러 TC 를 돌리는 동안, 평소 잘 되던 Update 버튼(2226) 조차
    8초 안에 나타나지 않아 `WF_13` 이 중단됐다 — `_need()` 가 같은 이유로 이미
    8초에서 20초로 올린 전례와 같은 계열이다.
    """
    end = time.time() + timeout
    hits = []
    while time.time() < end:
        hits = [c for c in ui.controls(max_depth=7)
                if c.ctrl_id == ctrl_id and c.visible
                and c.rect[2] - c.rect[0] > 20]
        if hits:
            break
        time.sleep(0.4)
    if not hits:
        raise FlowError(f"{what}(ID {ctrl_id})을 {timeout}초 동안 찾지 "
                        f"못했습니다. 현재 화면을 ui-probe로 확인하십시오.")
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


# ---------------------------------------------------------------------------
# Study Reject / Restore (WF_12). 2026-08-20 실측 — 사용자가 캡처로 알려 주고
# hover 툴팁으로 확정했다.
#
# **2186 은 같은 버튼이 상태에 따라 토글된다.**
#   일반 검사 선택 -> 툴팁 "Reject Study"  (아이콘 휴지통)
#   Rejected 검사 선택 -> 툴팁 "Restore Study"  (아이콘 되돌리기 화살표)
#
# 내가 2026-08-19 에 이 버튼을 "휴지통(삭제) — **절대 누르지 말 것**" 으로 기록했다.
# 아이콘 추정 오류의 네 번째 사례다(2184 Import Study / 2196 Pre-send Preview /
# 2207 Left Implant 에 이어). 그래서 파괴적으로 보이는 아이콘도 `ui.hover` 로
# 툴팁을 먼저 읽는다.
EXAMINED_REJECT_STUDY = 2186        # = Restore Study (상태에 따라 토글)

# Examined 의 데이터 소스 드롭리스트(2200) 항목. Reject 된 검사는 기본 목록에서
# 빠지므로 `rejected` 로 바꿔야 보인다 — WF_12 Step 3 이 이걸 요구한다.
EXAMINED_SOURCE_DROPLIST = 2200
EXAMINED_SOURCE_ITEMS = {
    "all": 1184, "rejected": 1187, "no_rejected": 1188,
    "suspended": 1189, "locked": 1190,
}

# `STUDY.StudyStatus` 실측값. Study Reject 는 3 -> **5** 로 바꾸고
# RejectType / RejectReason / RejectUserID 를 기록한다(2026-08-20).
STUDY_STATUS_REJECTED = 5

# 검사가 **Examine 에 열려 있는 동안**의 값(2026-08-31 실측). `WF_07` 이
# Emergency 검사를 시작한 직후 1 이었고, Close 클릭이 삼켜져 열린 채 남았을 때도
# 1 이 유지됐다. 정상 종료된 같은 TC 의 검사들은 3 이었다(위 주석의 "Reject 는
# 3 -> 5" 와도 일관된다 — 3 이 종료된 검사의 값이다).
# `close_examine_confirmed` 가 "Close 가 실제로 먹혔는가" 판별에 쓴다.
STUDY_STATUS_EXAMINING = 1

# Study Reject 도 Image Reject 와 **같은 사유 팝업**(701~707)을 쓴다(실측).


def select_examined_source(ui, source, tesseract_exe=None):
    """Examined 의 데이터 소스를 바꾼다(all / rejected / ...).

    항목 문구를 OCR 로 확인해 고른다 — 순서로 고르면 조용히 틀어진다.
    """
    from core import uitext

    if source not in EXAMINED_SOURCE_ITEMS:
        raise FlowError(f"알 수 없는 Examined 데이터 소스: {source}")
    drop = [c for c in ui.by_id(EXAMINED_SOURCE_DROPLIST) if c.visible]
    if not drop:
        raise FlowError(
            f"Examined 데이터 소스 드롭리스트({EXAMINED_SOURCE_DROPLIST})를 "
            "찾지 못했습니다.")
    ui.click(drop[0], settle=1.2)
    ctrl_id = EXAMINED_SOURCE_ITEMS[source]
    hits = [c for c in ui.by_id(ctrl_id) if c.visible]
    if not hits:
        raise FlowError(
            f"데이터 소스 항목 {source}({ctrl_id})을 찾지 못했습니다.")
    text = uitext.ocr(hits[0], tesseract_exe)
    if source != "all" and uitext.norm(source.replace("_", "")) not in \
            uitext.norm(text):
        raise FlowError(
            f"데이터 소스 항목 {ctrl_id} 가 {source!r} 이 아닙니다"
            f"(읽은 값 {text!r}). 잘못된 필터를 고르지 않도록 중단합니다.")
    ui.click(hits[0], settle=2.0)
    return {"source": source, "ctrl_id": ctrl_id, "ocr": text}


# ---------------------------------------------------------------------------
# Image Reject / Restore (WF_11). 2026-08-20 실측 — 사용자가 위치를 알려 주고
# 툴팁으로 확정했다.
#
# 흐름
#   Examined 에서 검사 선택 -> View(2182) -> 우측 Procedure 패널의 썸네일에서
#   대상 영상 선택 -> **1168 "Reject Image"** -> 사유 팝업에서 사유 선택
#   -> 영상에 빨간 `REJECTED` 스탬프가 찍히고 썸네일에 되돌리기 화살표(↺)가 겹친다
#   -> ↺ 를 누르면 "Do you want to restore the images?" -> 좌 Yes(501) 로 원복
#
# 사유 팝업 항목 (Setting > Study > Reject/Retake 목록에는 스크롤 때문에 5개만
# 보이지만 팝업에는 7개다).
REJECT_REASONS = {
    "artifacts": 701,
    "mispositioning": 702,
    "patient_movement": 703,
    "mechanical_failure": 704,
    "inappropriate_processing": 705,
    "double_exposure": 706,
    "others": 707,
}

# Reject 된 썸네일 안의 ↺(Restore) 는 **별도 컨트롤이 아니다** — 커스텀 렌더링이라
# `SystemThumbnailItem` 의 자식 윈도우가 없다. 그래서 썸네일 `rect` 에서 위치를
# 계산한다. 좌표 상수를 저장하지 않고 비율만 둔다(실측 (1615,238) / rect
# (1559,137,1890,312)).
RESTORE_ICON_RATIO = (0.17, 0.58)

# Restore 확인 팝업 — 문구 "Do you want to restore the images?" (OCR 확인).
# **좌 = Yes(501) / 우 = No(500)** 다. `ui.dismiss_dialog()` 는 No 를 눌러 원복이
# 되지 않았다(계정 삭제와 같은 함정). 좌우 순서와 ID 를 함께 확인해 Yes 를 누른다.
RESTORE_CONFIRM = {"yes": 501, "no": 500}
RESTORE_MARKERS = ("restore the image", "want to restore")

# 썸네일 목록 컨트롤과 항목 클래스.
THUMBNAIL_LIST = 155
THUMBNAIL_ITEM = "SystemThumbnailItem"


def restore_point(thumbnail):
    """Reject 된 썸네일 안 ↺ 아이콘의 클릭 좌표를 rect 에서 계산한다."""
    left, top, right, bottom = thumbnail.rect
    return (left + int((right - left) * RESTORE_ICON_RATIO[0]),
            top + int((bottom - top) * RESTORE_ICON_RATIO[1]))


# 검사를 **View 로 열었을 때** 하단의 3D 영상 종류 전환 버튼 (2026-08-20 실측,
# 캡처로 라벨 확인). Examine 모드의 Retake(2205)는 View 모드에 없다.
VIEW_INSTANCE_TYPE = {"raw": 2122, "recon": 2123, "syn": 2124}
VIEW_CLOSE = 2204          # View 모드의 닫기(366x64, Examine 의 2204 와 같은 ID)
EXAMINED_VIEW_BUTTON = 2182  # Examined 창 하단의 `View`


def close_view_study(ui, settle=3.0, dialog_timeout=3):
    """View 로 연 검사를 닫고 Examined 목록으로 돌아간다.

    **검사를 연 TC 는 반드시 이것으로 닫는다.** 열어 둔 채 끝나면 다음 TC 가
    Examined 화면을 찾지 못한다 — 2026-08-28 실측: `WF_04` 가 닫지 않고 끝나
    뒤따른 `WF_06` 이 `Examined 검색 컨트롤(2177/2178/2179)을 찾지 못했습니다`
    로 진입조차 못 했다.

    반환: 닫았으면 `{"closed": True, "dialog": bool}`, 닫기 버튼이 없으면 `None`
    (이미 Examined 이거나 다른 화면이라는 뜻이라 예외로 만들지 않는다).
    """
    from core import uitext

    btn = uitext.visible(ui, VIEW_CLOSE)
    if not btn:
        return None
    ui.click(btn[0], settle=settle)
    dialog = False
    if ui.dialog():
        ui.dismiss_dialog(timeout=dialog_timeout)
        dialog = True
    return {"closed": True, "dialog": dialog}

# Examined 창의 Pre-send Preview (WF_15). 2026-08-20 실측 — 사용자가 툴팁 캡처로
# 버튼을 지목해 줬다.
#
# **아이콘 추정이 또 틀린 사례다.** 2196 의 아이콘은 "목록 + 돋보기" 모양이라
# 2026-08-19 에 "검사 내 검색"으로 추정 기록했는데 실제는 `Pre-send Preview` 였다.
# 앞선 사례: 2184 를 Send 로 추정했으나 Import Study.
#
# 흐름
#   Examined 에서 검사 선택 -> 2196 -> 범위 선택 대화상자
#     "Do you want to send all images of the selected study?"
#     502 All Images / 501 Selected / 500 Cancel
#   -> `Pre-send Preview` 창(제목이 평문으로 읽힌다, 1766x978)
#
# 창 안에서 확인된 것
#   203  UIInstanceManager — Step 영상 패널. **보이는 개수 = 표시된 영상 수**
#   201  UIInstance — 실제 영상
#   2131 Storage 서버 선택 콤보 (`BUNNY_TEST (Use)`)
#   2128 Images 썸네일 목록
#   1148 **Send** — Examine 화면의 tool_send 와 같은 ID다(기능별로 ID 가 일관된다)
#   1105 Close
#   도구: 1111 Select / 1112 Select All / 1114 Pan / 1124 Fit / 1127 Center /
#         1115 W/L / 1173 Multi / 1183 Status
#   Layout: 1141 1x1 / 1142 1x2 / 1144 2x1 / 1143 2x2
EXAMINED_PRE_SEND_PREVIEW = 2196
PRE_SEND_SCOPE = {"all": 502, "selected": 501, "cancel": 500}
PRE_SEND_PREVIEW = {
    "title": "Pre-send Preview",
    "instance_panel": 203,
    "instance": 201,
    "storage_combo": 2131,
    "thumbnails": 2128,
    "send": 1148,
    "close": 1105,
    "layout_1x1": 1141,
    "layout_1x2": 1142,
    "layout_2x1": 1144,
    "layout_2x2": 1143,
}

# ---------------------------------------------------------------------------
# Film 창 (WF_03 Step 6 / WF_08). 2026-08-21 실측.
#
# 진입: Examined 에서 검사 선택 -> Print(2188) -> 범위 선택 Selected(501)
#       -> Film 다이얼로그. 필름 raster 는 `158`(`CWndFilmManager`)이다.
#
# 창 안에서 확인된 것 (컨트롤 열거 + 버튼 문구 OCR)
#   1141 1x1 / 1142 1x2 / 1143 2x2 / 1144 2x1   Layout
#   1149 **Print**  (OCR `Print`)
#   1105 **Close**  (OCR `Close`) — Pre-send Preview 창의 Close 와 같은 ID다
#                                   (이 제품은 기능별로 ID 가 일관된다)
#
# **Film 창을 열어 둔 채 TC 를 끝내지 않는다.** 뒤따르는 TC 가
# `cold_start(force_restart=True)` 로 시작하면 문제가 없지만, `WF_04` 처럼
# **재기동 없이 기존 Viewer 를 재사용**하는 TC 는 `ensure_patient_screen` 이
# 실패한다(2026-08-21 실측: 랜드마크가 `['status_bar','examine']` 로 남아 FAIL).
FILM = {
    "window": 158,
    "window_text": "CWndFilmManager",
    "layout_1x1": 1141,
    "layout_1x2": 1142,
    "layout_2x1": 1144,
    "layout_2x2": 1143,
    "print": 1149,
    "close": 1105,
}


def film_window(ui):
    """열려 있는 Film 창(`CWndFilmManager`). 없으면 None."""
    hits = [c for c in ui.by_id(FILM["window"])
            if c.visible and c.text == FILM["window_text"]]
    return hits[0] if hits else None


def close_film(ui, tesseract_exe=None, timeout=15):
    """Film 창을 닫는다. **버튼 문구를 OCR 로 확인한 뒤에만 누른다.**

    아이콘/위치 추정으로 버튼을 눌러 네 번 틀린 이력이 있다(2184 Import Study /
    2196 Pre-send Preview / 2186 Reject Study /
    2207 Left Implant). 같은 화면에 `Print`(1149)가 나란히 있어서, ID 만 믿고
    누르면 **의도치 않게 실제 출력을 보낼 수 있다.** 그래서 `close` 로 읽히는
    버튼만 누른다.

    **Close 를 누르면 확인 대화상자가 뜬다** — 실측 문구
    `"Are you sure you want to close?"` / `Yes`(501) / `No`(500).
    ID 나 위치로 고르지 않고 **문구를 OCR 로 읽어** Yes 를 누른다. 이 제품은
    같은 ID(501/500)를 Print 범위 선택(Selected/Cancel)에도 쓰므로 ID 만 믿으면
    정반대를 누를 수 있다.

    반환: {"was_open": bool, "closed": bool, "labels": [...],
           "confirm": {...}|None, "error": str|None}
    """
    from core import uitext

    out = {"was_open": False, "closed": True, "labels": [], "confirm": None,
           "error": None}
    if film_window(ui) is None:
        return out
    out["was_open"] = True
    out["closed"] = False

    picked = None
    for c in [x for x in ui.by_id(FILM["close"]) if x.visible]:
        label = uitext.button_label(c, tesseract_exe)
        out["labels"].append({"rect": c.rect, "label": label})
        if "close" in uitext.norm(label):
            picked = c
            break
    if picked is None:
        out["error"] = (f"Film 창의 Close 버튼({FILM['close']})을 문구로 확인하지 "
                        "못해 누르지 않았습니다.")
        return out
    ui.click(picked, settle=2.5)

    dialog = ui.dialog()
    if dialog is not None:
        yes, reads = uitext.pick_button(ui.dialog_buttons(dialog), "yes",
                                       tesseract_exe)
        out["confirm"] = {"rect": dialog.rect, "buttons": reads,
                          "picked": "yes" if yes is not None else None}
        if yes is None:
            out["error"] = ("Film 종료 확인 대화상자에서 Yes 를 문구로 특정하지 "
                            "못해 아무것도 누르지 않았습니다.")
            return out
        ui.click(yes, settle=2.5)

    end = time.time() + timeout
    while time.time() < end:
        if film_window(ui) is None:
            out["closed"] = True
            return out
        time.sleep(1)
    out["error"] = "Close/Yes 를 눌렀지만 Film 창이 닫히지 않았습니다."
    return out


# ---------------------------------------------------------------------------
# "Select Images" 창 (WF_08 3D Print). 2026-09-02 실측.
#
# Print(2188) -> Selected(501) 이후, 검사에 3D(Narrow/Wide) 영상이 있으면
# Film 창 대신 이 창이 먼저 뜬다. 2D 는 프레임이 하나뿐이라 이 창 자체가
# 뜨지 않고 바로 Film 으로 간다 - 예전 코드가 이 창을 전혀 다루지 않아
# 3D Print 가 "Film window did not open"(25초 타임아웃)으로 항상 실패했다.
#
# 네이티브 타이틀이 없는 커스텀 창(자식 ctrl_id로만 식별). 실측한 구성:
#   좌 = View Position 목록(현재 선택한 검사의 썸네일 하나)
#   중 = 좌에서 고른 View Position 의 프레임. 3D 는 위에 Raw/Recon/Syn
#        라디오(2112/2113/2114)가 있어 Type 을 바꾸면 프레임 목록이 바뀐다.
#   우 = 전송(=인쇄) 목록. 중앙에서 프레임을 고르고 `+`(2116)를 누르면
#        `<View Position>: <Type>` 라벨(예: `LCC (3D-N): Recon`)로 여기 담긴다.
#        `Add All`(2117, 아이콘만이라 OCR 불가)은 현재 Type 프레임을 한 번에
#        전부 담고, 휴지통(2115)은 우측에서 고른 항목을 뺀다.
#   하단 OK(1101)/Cancel(1102).
#
# 좌/중/우 경계는 해상도에 따라 달라질 수 있어 픽셀 값을 박지 않는다 -
# 우측 목록 컨테이너(2111)의 실측 rect 를 매번 다시 읽어 그 왼쪽 끝을
# 경계로 삼는다(AGENTS.md 5절, B.14 와 같은 이유).
SELECT_IMAGES = {
    "raw": 2112, "recon": 2113, "syn": 2114,
    "add": 2116, "add_all": 2117, "delete": 2115,
    "ok": 1101, "cancel": 1102, "dest_list": 2111,
}


def select_images_window(ui, timeout=5):
    """`Select Images` 창을 찾는다. 2D 처럼 뜨지 않으면 `None`을 돌려준다."""
    end = time.time() + timeout
    while time.time() < end:
        for w in ui.windows():
            ids = {c.ctrl_id for c in children(w.hwnd, 6)}
            if SELECT_IMAGES["ok"] in ids and SELECT_IMAGES["add"] in ids:
                return w
        time.sleep(.3)
    return None


def _si_children(win):
    return list({c.hwnd: c for c in children(win.hwnd, 8)}.values())


def _si_dest_boundary(win):
    dest = [c for c in _si_children(win) if c.ctrl_id == SELECT_IMAGES["dest_list"]]
    return min((c.rect[0] for c in dest), default=None)


def select_images_dest_count(win):
    """전송(우측) 목록에 담긴 프레임 수."""
    boundary = _si_dest_boundary(win)
    if boundary is None:
        return 0
    return len([c for c in _si_children(win)
                if c.text == "FrameItem" and c.rect[0] >= boundary])


def select_images_clear(ui, win, max_rounds=20):
    """전송(우측) 목록을 비운다.

    Print > Selected 로 같은 View Position 을 다시 열면 **이전에 담아 뒀던
    항목이 그대로 남아 있을 수 있다**(2026-09-02 실측 - 이전 세션이 끝까지
    확인/취소되지 않은 채 남긴 선택이 다음에도 보였다). 이미 담긴 프레임을
    다시 고르면 제품이 "This item already exists."로 막으므로, 새로 담기
    전에 항상 먼저 비워서 시작 상태를 결정적으로 만든다."""
    for _ in range(max_rounds):
        if select_images_dest_count(win) == 0:
            return
        select_images_delete_last(ui, win)
    if select_images_dest_count(win) != 0:
        raise FlowError("Select Images 전송 목록을 비우지 못했습니다.")


def select_images_add(ui, win, kind=None, frame_index=0, max_attempts=20):
    """`kind`(raw/recon/syn)가 있으면 그 라디오를 먼저 고르고, 중앙 목록에서
    `frame_index` 번째부터 시작해 담을 수 있는 프레임을 전송 목록에 추가한다.

    **이미 담긴 프레임을 다시 고르면** 제품이 "This item already exists."
    경고로 막는다(2026-09-02 실측). **`ui.dialog()`로 이 경고를 구분할 수
    없다** - Select Images 창 자체도 작은 `#32770`이라 창이 열려 있기만
    해도 `ui.dialog()`가 그 창 자체를 "떠 있는 대화상자"로 오탐지한다(같은
    rect). 그래서 경고 여부는 **전송 목록 개수가 실제로 늘었는지**로만
    판정하고, 늘지 않았을 때만 - 그리고 그 "대화상자"의 rect 가 Select
    Images 창 rect 와 다를 때만 - 진짜 경고로 보고 닫은 뒤 다음 프레임으로
    재시도한다.

    반환: `{"kind", "before", "after", "frame_index"}`."""
    if kind is not None:
        radios = [c for c in _si_children(win) if c.ctrl_id == SELECT_IMAGES[kind]]
        if not radios:
            raise FlowError(f"Select Images '{kind}' 라디오를 찾지 못했습니다.")
        ui.click(radios[0], settle=1.0)
    before = select_images_dest_count(win)
    boundary = _si_dest_boundary(win)
    frames = sorted(
        (c for c in _si_children(win)
         if c.text == "FrameItem" and (boundary is None or c.rect[0] < boundary)),
        key=lambda c: (c.rect[1], c.rect[0]))
    add_btn = [c for c in _si_children(win) if c.ctrl_id == SELECT_IMAGES["add"]]
    if not add_btn:
        raise FlowError("Select Images '+' 버튼을 찾지 못했습니다.")
    idx = frame_index
    tried = 0
    while tried < max_attempts:
        if idx >= len(frames):
            break
        ui.click(frames[idx], settle=.8)
        ui.click(add_btn[0], settle=1.0)
        after = select_images_dest_count(win)
        if after == before + 1:
            return {"kind": kind, "before": before, "after": after, "frame_index": idx}
        dup = ui.dialog()
        if dup is not None and dup.rect != win.rect:
            buttons = ui.dialog_buttons(dup)
            if len(buttons) == 1:
                ui.click(buttons[0], settle=1.0)
        idx += 1
        tried += 1
    raise FlowError(
        f"Select Images '{kind or '현재 Type'}' 프레임을 추가하지 못했습니다"
        f"(index {frame_index}~{idx - 1} 모두 실패, 프레임 {len(frames)}개).")


def select_images_delete_last(ui, win):
    """전송 목록에서 가장 최근에 추가된 항목을 눌러 휴지통으로 뺀다.

    새 항목은 전송 목록 **아래쪽에 이어 붙는다**(2026-09-02 실측 - 먼저 넣은
    항목이 위로 밀려 스크롤된다). 그래서 y 오름차순으로 정렬했을 때
    **마지막(가장 아래)** 이 최근 항목이다.

    반환: `{"before", "after"}`."""
    boundary = _si_dest_boundary(win)
    dest_items = sorted(
        (c for c in _si_children(win)
         if c.text == "FrameItem" and boundary is not None and c.rect[0] >= boundary),
        key=lambda c: (c.rect[1], c.rect[0]))
    if not dest_items:
        raise FlowError("Select Images 전송 목록이 비어 있어 삭제할 항목이 없습니다.")
    ui.click(dest_items[-1], settle=.8)
    del_btn = [c for c in _si_children(win) if c.ctrl_id == SELECT_IMAGES["delete"]]
    if not del_btn:
        raise FlowError("Select Images 휴지통(삭제) 버튼을 찾지 못했습니다.")
    before = select_images_dest_count(win)
    ui.click(del_btn[0], settle=1.0)
    return {"before": before, "after": select_images_dest_count(win)}


def select_images_confirm(ui, win):
    """OK 를 눌러 전송 목록을 확정하고 Film 창으로 넘어간다."""
    ok = [c for c in _si_children(win) if c.ctrl_id == SELECT_IMAGES["ok"]]
    if not ok:
        raise FlowError("Select Images OK 버튼을 찾지 못했습니다.")
    ui.click(ok[0], settle=2.0)


# ---------------------------------------------------------------------------
# Setting > Procedure > Hospital Code (WF_10 Step 1~2). 2026-08-20 실측.
#
# 목록 컬럼이 `Code / Procedure·View Position / Type / Description` 이라서
# **코드 추가(Step 1)와 Procedure 매핑(Step 2)이 같은 화면**에서 이뤄진다.
#
# `+`(2558)는 모달이 아니라 **인라인 행**을 추가한다. 새 행은
# `Code / Unknown / (빈 Type) / (빈 Description)` 으로 시작하고, Procedure 열의
# **톱니바퀴(⚙)** 를 누르면 `View Position` 대화상자가 열린다. ⚙ 는 별도 컨트롤이
# 아니라 셀에 그려져 있어 행 rect 에서 위치를 계산한다(상대 x≈0.50).
# **주의 1 — 즉시 저장.** `+`(2558)는 Update 없이도 `PROCEDURE.HOSPITAL_CODE` 에
#   행을 **바로 만든다**(2026-08-20 실측, 프로브를 다섯 번 돌려 DB 에 5행을 남긴
#   사고로 확인했다). Print Overlay / Account 는 Update 까지 눌러야 저장되는데 이
#   화면은 다르다 — 화면마다 다르다고 봐야 한다.
# **주의 2 — 행 중앙에 ⚙ 가 있다.** `ui.click(row)` 는 행 중앙을 누르는데 이 목록은
#   중앙 x 가 정확히 ⚙ 위치다. 행을 **선택**하려면 좌측 Code 셀을 눌러야 한다
#   (`hospital_code_cell(row, "code")`). 중앙을 누르면 View Position 대화상자가
#   열리고, 그 위에 뜨는 "Please select item to add." 팝업이 이후 클릭을 삼킨다.
# **주의 1 - 즉시 저장.** `+`(2558)는 Update 없이도 `PROCEDURE.HOSPITAL_CODE` 에
#   행을 **바로 만든다**(2026-08-20 실측 — 프로브를 다섯 번 돌려 DB 에 5행을 남긴
#   사고로 확인했다). Print Overlay / Account 는 Update 까지 눌러야 저장되는데 이
#   화면은 다르다. 화면마다 다르다고 봐야 한다.
# **주의 1-1 - 셀 편집은 Update 가 필요하다.** `+` 로 만든 행은 즉시 DB 에 들어가지만
#   Code 셀을 고친 값은 Update 를 눌러야 반영된다. 같은 화면에서도 **조작마다 다르다.**
# **주의 1-2 - Code 셀은 진짜 더블클릭으로만 편집 모드가 열린다.** `ui.click()` 을 두 번
#   부르면 settle 때문에 간격이 400~900ms 로 벌어져 Windows 가 더블클릭으로 인식하지
#   않는다(임계값 기본 500ms). `ui.double_click()` 을 쓴다 — 그렇게 하면 Code 열에
#   표준 `Edit` 컨트롤(rect 는 Code 열 폭)이 열린다.
# **주의 2 - 행 중앙에 톱니바퀴 버튼이 있다.** `ui.click(row)` 는 행 중앙을 누르는데
#   이 목록은 중앙 x 가 정확히 그 버튼 위치다. 행을 **선택**하려면 좌측 Code 셀을
#   눌러야 한다(`hospital_code_cell(row, "code")`). 중앙을 누르면 View Position
#   대화상자가 열리고, 그 위에 뜨는 "Please select item to add." 팝업이 이후 클릭을
#   전부 삼킨다.
SETTING_HOSPITAL_CODE = {
    "list": 2557,
    "add": 2558,
    "delete": 2559,
    # 행 안에서의 상대 위치. 좌표 상수를 저장하지 않고 비율만 둔다.
    "code_cell_ratio": 0.08,
    "gear_ratio": 0.50,
}

# ⚙ 가 띄우는 `View Position` 대화상자. 탭 4개와 OK/Cancel (실측).
#   Procedure 탭의 목록 **행 ctrl_id 가 `PROCEDURE.PROCEDURE_INFO.Key` 와 일치**한다
#   (1 = Routine Mammography, 2 = Mammography (Rt), ...). 다만 헤더 행도 id=1 이라
#   y 좌표로 구분해야 한다 — 그래서 항목은 문구를 OCR 로 읽어 고른다.
VIEW_POSITION_DIALOG = {
    "tab_preset_2d": 2082,
    "tab_preset_3dn": 2083,
    "tab_preset_3dw": 2084,
    "tab_procedure": 2086,
    "ok": 1101,
    "cancel": 1102,
}


def hospital_code_cell(row, which="code"):
    """Hospital Code 행에서 셀(또는 ⚙)의 클릭 좌표를 rect 에서 계산한다."""
    ratio = SETTING_HOSPITAL_CODE[
        "code_cell_ratio" if which == "code" else "gear_ratio"]
    left, top, right, bottom = row.rect
    return (left + int((right - left) * ratio), (top + bottom) // 2)


# Setting > DICOM > MWL 의 `Hospital Code Mapping` 콤보 (WF_10, 2026-08-20 실측).
#
# 사용자가 알려 준 절차: "mwl 서버에 임의의 코드에 커스텀 태그를 만들고 값을 넣은
# 다음에 Setting > DICOM > MWL 에서 hospital code 토글을 설정하면 된다. 토글을 넣은
# 다음에 **리스트를 확인**한 다음 그 리스트에 있는 항목으로 MWL 서버 커스텀 태그를
# 넣으면 될 듯."
#
# 즉 순서가 있다 — Setting > Procedure > Hospital Code(페이지 215)에서 코드를 먼저
# 만들어야 이 콤보에 항목이 생긴다. 코드가 없을 때 콤보를 누르면 **목록이 아예 열리지
# 않는다**(실측). 그래서 "콤보가 안 열림"을 실패로 보지 말고 "등록된 코드가 없다"로
# 읽어야 한다.
MWL_HOSPITAL_CODE_MAPPING = 2453

# 그 콤보의 항목은 **Hospital Code 값이 아니라 DICOM 태그 목록**이다(2026-08-20 실측).
# 즉 "Viewer 가 Hospital Code 를 어느 태그에서 읽을지" 를 정하는 설정이다.
#
# `core/mwl.py` 의 `make_mg_order(..., hospital_code=...)` 는 그 값을
# `rp_code_value`(Requested Procedure Code Value)로 넣으므로
# **(0032,1064) Requested Procedure Code Sequence** 와 짝이 맞는다.
#
# **SCP 목록에서 서버를 먼저 선택해야 이 콤보가 활성화된다.** 선택하지 않으면 눌러도
# 목록이 열리지 않는다(Print Overlay 와 같은 패턴).
MWL_CODE_MAPPING_TAGS = {
    "none": "None",
    "requested_procedure_id": "(0040,1001)",
    "requested_procedure_description": "(0032,1060)",
    "requested_procedure_code_sequence": "(0032,1064)",
    "sps_description": "(0040,0007)",
    "sps_id": "(0040,0009)",
}


def select_first_scp(ui, tesseract_exe=None):
    """Setting > DICOM 의 SCP 목록에서 첫 항목을 선택한다.

    우측 설정은 목록에서 서버를 고른 뒤에야 활성화된다.
    반환: 선택한 행의 OCR 문구(없으면 None).
    """
    from core import uitext
    from core.ui import children

    lists = [c for c in ui.controls(max_depth=8)
             if c.visible and c.text == "ListCtrl" and c.rect[0] > 380]
    for lc in lists:
        rows = sorted({x.hwnd: x for x in children(lc.hwnd, 5)
                       if x.visible and x.text == "ListItem"}.values(),
                      key=lambda x: x.rect[1])
        if rows:
            ui.click(rows[0], settle=1.5)
            return uitext.ocr(rows[0], tesseract_exe)
    return None

# Setting > System 하위 페이지 (2026-08-19 실측 — 캡처 라벨과 rect 대조).
#   화면 순서: General / Security / Region / System Info. / Software Info. /
#   Account / License / My Settings / CS
SETTING_SYSTEM_PAGES = {
    "general": 186, "security": 187, "region": 188, "system_info": 189,
    "software_info": 190, "account": 191, "license": 192,
    "my_settings": 193, "cs": 194,
}

# Setting > System > Account (WF_13). 목록 컬럼은 ID / Name / Group / System.
SETTING_ACCOUNT = {
    "list": 2280,            # ListCtrl — 하위 ListItem 이 계정 행
    "add": 2281,             # +
    "delete": 2282,          # 휴지통
    "user_id": 2283,
    "user_name": 2284,
    "password": 2285,
    "check_password": 2286,
    "group": 2287,           # 콤보 (Service / Admin / User ...)
}

# Account 페이지의 `+`(2281)가 띄우는 **New Account 모달** (2026-08-19 실측).
#   인라인 편집이 아니다 — 우측 Properties(2283~2287)는 선택된 계정의 표시용이고,
#   추가는 이 모달에서 한다. Password 는 제품이 8자 이상을 요구한다
#   (모달의 "At least 8 characters").
#   Group 콤보(2292) 항목은 OCR 로 읽어 확정했다: Service / Admin / User.
#   `ACCOUNT.Group` 실측값 (2026-08-19): Service=3 / Admin=2 / **User=1**.
#   콤보 라벨과 DB 값을 실제로 만들어 대조해 확정했다(추측 아님).
ACCOUNT_GROUPS = {"Service": 3, "Admin": 2, "User": 1}

NEW_ACCOUNT = {
    "user_id": 2288,
    "user_name": 2289,
    "password": 2290,
    "check_password": 2291,
    "group": 2292,
    "ok": 1101,
    "cancel": 1102,
}

# Setting > System > My Settings (WF_14). 버튼 두 개뿐이다.
SETTING_MY_SETTINGS = {"export": 2293, "import": 2294}

# Setting > Patient / Display / Tool / Device 하위 페이지 (2026-08-20 실측).
#
# 각 항목을 OCR 로 읽어 사양서1 78~80쪽 권한 표의 순서와 대조했다(56개 전부 일치).
# **ID 가 화면 순서와 무관하다.** Patient 의 External Device/Barcode/QR Code 는
# 228/235/236 으로 멀리 떨어져 있고, Device 는 234-226-230-231-229-232-233-227 로
# 순서가 완전히 뒤섞였다. 연속이라고 추정했으면 전부 틀렸다.
SETTING_PATIENT_PAGES = {
    "general": 195, "patient_list": 196, "new_patient": 197, "examined": 198,
    "physician": 199, "external_device": 228, "barcode": 235, "qr_code": 236,
}
SETTING_DISPLAY_PAGES = {
    "general": 200, "overlay": 201, "layout": 202, "lut": 203,
    "monitor_correction": 204,
}
SETTING_TOOL_PAGES = {
    "general": 205, "predefined_text": 206, "image_tool": 207, "status_bar": 208,
}
SETTING_DEVICE_PAGES = {
    "general": 234, "device_info": 226, "aec": 230, "aec_3d": 231,
    "gantry": 229, "gantry_misc": 232, "viewposition": 233, "ups": 227,
}


def setting_pages(group):
    """그룹 이름 -> {페이지 이름: 컨트롤 ID}. 실측된 그룹만 돌려준다."""
    return {
        "system": SETTING_SYSTEM_PAGES,
        "patient": SETTING_PATIENT_PAGES,
        "display": SETTING_DISPLAY_PAGES,
        "tool": SETTING_TOOL_PAGES,
        "study": SETTING_STUDY_PAGES,
        "procedure": SETTING_PROCEDURE_PAGES,
        "dicom": SETTING_DICOM_PAGES,
        "device": SETTING_DEVICE_PAGES,
        "qc": SETTING_QC_PAGES,
    }[group]


def open_group_page(ui, group, page, wait=2.5):
    """Setting > <group> > <page> 로 이동한다(그룹 무관 공용)."""
    pages = setting_pages(group)
    if page not in pages:
        raise FlowError(f"알 수 없는 {group} 설정 페이지: {page}")
    open_setting(ui, wait=3.0)
    open_setting_group(ui, group, wait=2.0)
    return _click_setting_control(ui, pages[page],
                                  f"{group} 설정 '{page}'", wait)


# Setting > Study 하위 페이지 (2026-08-19 실측)
SETTING_STUDY_PAGES = {"general": 209, "study_delete": 210, "reject_retake": 211}

# Setting > Study > Reject/Retake (WF_11 / WF_12 의 전제조건 확인용).
#   2026-08-19 기준 제품 기본값: reject_on_retake=No, 나머지 세 옵션은 모두 체크,
#   Reasons 5건(Artifacts / Mispositioning / Patient Movement / Mechanical
#   Failure / Inappropriate Processing). 자동화는 이 전제를 **바꾸지 않고 확인**한다.
SETTING_REJECT_RETAKE = {
    "reject_on_retake_yes": 2421,
    "reject_on_retake_no": 2422,
    "use_reject_reason": 2423,
    "use_retake_reason": 2424,
    "always_display_rejected": 2425,
    "reason_list": 2426,
    "reason_add": 2427,
    "reason_delete": 2428,
}

# Patient 화면 우상단의 빨간 원형 버튼 = Emergency (WF_07).
#   사이렌 아이콘을 캡처로 확인했다(`Evidence/ui/zoom_circle.png`).
PATIENT_EMERGENCY = 1100


def open_system_setting(ui, page, wait=2.5):
    """Setting > System > <page> 로 이동한다.

    page: general | security | region | system_info | software_info |
          account | license | my_settings | cs
    """
    if page not in SETTING_SYSTEM_PAGES:
        raise FlowError(f"알 수 없는 System 설정 페이지: {page}")
    open_setting(ui, wait=3.0)
    open_setting_group(ui, "system", wait=2.0)
    return _click_setting_control(ui, SETTING_SYSTEM_PAGES[page],
                                  f"System 설정 '{page}'", wait)


def open_study_setting(ui, page, wait=2.5):
    """Setting > Study > <page> 로 이동한다.

    page: general | study_delete | reject_retake
    """
    if page not in SETTING_STUDY_PAGES:
        raise FlowError(f"알 수 없는 Study 설정 페이지: {page}")
    open_setting(ui, wait=3.0)
    open_setting_group(ui, "study", wait=2.0)
    return _click_setting_control(ui, SETTING_STUDY_PAGES[page],
                                  f"Study 설정 '{page}'", wait)


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


def _setting_result_text(text):
    """Setting Update 결과 팝업으로 확정할 수 있는 OCR 문구인가."""
    compact = "".join(ch for ch in str(text or "").lower()
                      if ch.isalnum())
    return ("restarttheprogramtoapply" in compact
            or "updatesuccessfully" in compact
            or "updatedsuccessfully" in compact)


def _pink_button_point(image):
    """Setting 중앙 영역의 채워진 분홍 버튼 중심(이미지 상대좌표).

    1px 팝업 테두리보다 채워진 버튼 행의 분홍 픽셀이 훨씬 많다는 점을 이용한다.
    Update 버튼과 좌측 선택 레일은 중앙/중간 높이 범위 밖이라 후보가 아니다.
    """
    from core import screen

    width, height = image.size
    x0, x1 = int(width * .28), int(width * .72)
    y0, y1 = int(height * .30), int(height * .72)
    pixels = image.load()
    pink = {(x, y) for y in range(y0, y1) for x in range(x0, x1)
            if screen.is_pink(pixels[x, y])}
    components = []
    while pink:
        seed = pink.pop()
        stack = [seed]
        component = [seed]
        while stack:
            x, y = stack.pop()
            for point in ((x - 1, y), (x + 1, y),
                          (x, y - 1), (x, y + 1)):
                if point in pink:
                    pink.remove(point)
                    stack.append(point)
                    component.append(point)
        xs = [point[0] for point in component]
        ys = [point[1] for point in component]
        box_width = max(xs) - min(xs) + 1
        box_height = max(ys) - min(ys) + 1
        density = len(component) / float(box_width * box_height)
        # OK는 가로로 긴 채움 버튼이다. 팝업의 1px 테두리나 라디오 표시처럼
        # 서로 떨어진 분홍 요소를 같은 y행이라는 이유로 합치지 않는다.
        if (len(component) >= 300 and box_width >= 40 and box_height >= 10
                and box_width > box_height * 1.3 and density >= .35):
            components.append((len(component), min(xs), max(xs),
                               min(ys), max(ys)))
    if not components:
        return None
    _area, left, right, top, bottom = max(components)
    return ((left + right) // 2, (top + bottom) // 2)


def _setting_inline_result(ui):
    """UPS처럼 Setting 창 안에 그려지는 결과 팝업을 찾는다.

    이 팝업은 별도 Win32 버튼이 아니다. 실측상 OK가 자식 컨트롤로 열거되지 않아
    팝업 문구 OCR + 채워진 분홍 버튼을 함께 확인해야 한다. 좌표는 Setting 창에
    상대적이며, 둘 중 하나라도 확인되지 않으면 클릭하지 않는다.
    """
    if not hasattr(ui, "windows"):
        return None
    from core import screen

    updates = [c for c in ui.by_id(SETTING_UPDATE_BUTTON)
               if c.visible and c.rect[2] > c.rect[0]]
    if len({c.hwnd: c for c in updates}) != 1:
        return None
    update = next(iter({c.hwnd: c for c in updates}.values()))
    containers = []
    for top in ui.windows():
        nodes = [top] + list(children(top.hwnd, 3))
        for node in nodes:
            if node.cls != "#32770" or not node.visible:
                continue
            l, t, r, b = node.rect
            ul, ut, ur, ub = update.rect
            if l <= ul and t <= ut and ur <= r and ub <= b:
                containers.append(node)
    if not containers:
        return None
    dialog = min({c.hwnd: c for c in containers}.values(),
                 key=lambda c: ((c.rect[2] - c.rect[0])
                                * (c.rect[3] - c.rect[1])))
    image = screen.grab(dialog.rect)
    point = _pink_button_point(image)
    if point is None:
        return None
    l, t, r, b = dialog.rect
    text_box = (l + int((r - l) * .28), t + int((b - t) * .30),
                l + int((r - l) * .72), t + int((b - t) * .72))
    text = screen.ocr(text_box, scale=3, psm=6)
    if not _setting_result_text(text):
        return None
    return {"dialog": dialog, "text": text,
            "point": (l + point[0], t + point[1])}


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


def confirm_setting_dialog(ui, wait=1.5, timeout=6, required=False):
    """Update 결과 팝업 **안의** OK를 누르고 실제로 닫힐 때까지 확인한다.

    예전 구현은 ``ui.by_id(500)`` 으로 Viewer 전체 트리를 훑어 첫 항목을 눌렀다.
    Setting 본문이나 다른 창에도 같은 ID가 있을 수 있어 엉뚱한 컨트롤을 누른 뒤
    성공 팝업을 남길 수 있었고, 그러면 모달이 뒤이은 메뉴 클릭을 전부 삼킨다.
    2026-08-25 사용자가 WF_14의 UPS Update 직후 그 상태를 직접 확인했다.

    표준 ``#32770`` 외에 UPS처럼 Setting 안에 그려지는 인라인 팝업도 처리한다.
    UPS Update는 "재시작 필요"와 "Update 성공" 팝업이 **연속 두 개** 뜨므로,
    하나를 닫았다고 성공하지 않고 결과 팝업이 더 없을 때까지 반복한다.
    ``required=True`` 는 Update 직후처럼 팝업이 반드시 떠야 하는 경로다.
    """
    end = time.time() + timeout
    handled = False
    handled_count = 0
    while time.time() < end:
        inline = _setting_inline_result(ui)
        if inline:
            ui.click(inline["point"], settle=.2)
            close_end = time.time() + max(wait, 1.0)
            while time.time() < close_end:
                current = _setting_inline_result(ui)
                if current is None or current["text"] != inline["text"]:
                    handled = True
                    handled_count += 1
                    break
                time.sleep(.2)
            else:
                raise FlowError(
                    "Setting 인라인 결과 팝업의 OK를 눌렀지만 같은 팝업이 "
                    f"남았습니다(OCR={inline['text']!r}). 이후 메뉴를 누르지 않습니다.")
            # 다음 결과 팝업이 연달아 나타날 수 있으므로 처음부터 다시 확인한다.
            if handled_count >= 4:
                raise FlowError("Setting 결과 팝업이 4개를 초과해 연속으로 나타났습니다.")
            # OCR 한 번이 수 초 걸릴 수 있다. 이미 닫은 팝업의 OCR 시간 때문에
            # 전체 제한이 끝나 성공을 '팝업 없음'으로 덮어쓰지 않도록 갱신한다.
            end = time.time() + timeout
            continue
        dialog = ui.dialog()
        if dialog:
            buttons = ui.dialog_buttons(dialog)
            ok = [c for c in buttons
                  if c.ctrl_id == SETTING_CONFIRM_OK and c.visible]
            if len(ok) != 1:
                raise FlowError(
                    "Setting 결과 팝업의 OK 버튼 구성이 예상과 다릅니다"
                    f"(기대 ID {SETTING_CONFIRM_OK} 1개, "
                    f"실제={[(b.ctrl_id, b.rect[0]) for b in buttons]}). "
                    "잘못된 버튼을 누르지 않도록 중단합니다.")
            dialog_hwnd = dialog.hwnd
            ui.click(ok[0], settle=.2)
            close_end = time.time() + max(wait, 1.0)
            while time.time() < close_end:
                current = ui.dialog()
                if current is None or current.hwnd != dialog_hwnd:
                    handled = True
                    handled_count += 1
                    break
                time.sleep(.2)
            else:
                raise FlowError(
                    "Setting 결과 팝업의 OK를 눌렀지만 팝업이 닫히지 않았습니다"
                    f"(dialog hwnd={dialog_hwnd}). 이후 메뉴를 누르지 않고 중단합니다.")
            if handled_count >= 4:
                raise FlowError("Setting 결과 팝업이 4개를 초과해 연속으로 나타났습니다.")
            end = time.time() + timeout
            continue
        if handled:
            return True
        time.sleep(.3)
    if handled:
        return True
    if required:
        raise FlowError(
            f"Setting Update 후 {timeout}초 동안 결과 팝업이 나타나지 않았습니다. "
            "저장 성공을 확인할 수 없으므로 이후 메뉴를 누르지 않습니다.")
    return False


class FlowError(RuntimeError):
    pass


# --- Cold start -------------------------------------------------------
def select_login_id(ui, user_id, tesseract_exe=None):
    """로그인 화면의 ID 콤보에서 `user_id` 를 고른다.

    사양서1 78쪽: ID 입력창은 **등록된 계정 목록**이고 직접 입력이 아니라 선택하는
    방식이다. 이미 그 계정이 선택돼 있으면 아무것도 하지 않는다.

    반환: {"already": bool, "picked": {...}} / 고르지 못하면 예외.
    """
    from core import uitext

    # 콤보는 긴 ID를 잘라서 보여준다(`TEST_USER_FLOW` -> `TEST_USE`). 접두사로 본다.
    def matches(shown):
        shown = (shown or "").strip().lower()
        want = user_id.strip().lower()
        return bool(shown) and (shown == want
                                or (len(shown) >= 4 and want.startswith(shown)))

    current = (ui.current_login_id() or "").strip()
    if matches(current):
        return {"already": True, "current": current}

    # 1차: OCR 로 항목 문구를 읽어 고른다.
    picked, ocr_error = None, None
    try:
        picked = uitext.pick_combo_by_text(
            ui, ui.LOGIN_ID_COMBO, user_id, tesseract_exe, what="로그인 ID",
            match="prefix")
        after = (ui.current_login_id() or "").strip()
        if matches(after):
            return {"already": False, "current": after, "picked": picked}
    except Exception as exc:                           # noqa: BLE001
        ocr_error = f"{type(exc).__name__}: {exc}"

    # 2차: **고른 뒤 확인하고, 틀리면 다음 후보로 재시도**한다.
    #
    # OCR 이 항목을 잘못 읽으면 1차는 "후보가 하나가 아니다" 로 실패한다
    # (`pick_combo_by_text` 는 애매하면 아무것도 누르지 않는다 — 옳은 동작이다).
    # 그런데 이 콤보는 **고른 결과를 `ui.current_login_id()` 로 확인할 수 있으므로**
    # 후보를 하나씩 눌러 보고 확인하는 편이 안전하고 확실하다. 엉뚱한 계정이
    # 골라져도 즉시 알아채고 다음 후보로 넘어가며, 끝내 못 찾으면 예외를 던진다.
    # (`tests/xipl_flows._click_general_param_combo` 와 같은 방식이다.)
    tried = []
    for index in range(_LOGIN_ID_MAX_CANDIDATES):
        items = _login_id_items(ui)
        if index >= len(items):
            break
        ui.click(items[index], settle=0.8)
        after = (ui.current_login_id() or "").strip()
        tried.append(after)
        if matches(after):
            return {"already": False, "current": after,
                    "picked": {"wanted": user_id, "by": "확인 후 재시도",
                               "attempt": index + 1, "tried": tried,
                               "ocr_error": ocr_error}}
    raise FlowError(
        f"로그인 ID 를 {user_id!r} 로 바꾸지 못했습니다. "
        f"OCR 선택={ocr_error or (picked and picked.get('items_read'))}, "
        f"후보를 눌러 확인한 결과={tried}. 엉뚱한 계정으로 로그인하지 "
        "않도록 중단합니다.")


#: 로그인 ID 콤보에서 눌러 볼 후보 수 상한. 계정이 이보다 많으면 그 사실이
#  예외에 남는다 — 조용히 일부만 보고 "없다" 고 하지 않기 위한 상한이다.
_LOGIN_ID_MAX_CANDIDATES = 12


def _login_id_items(ui):
    """로그인 ID 콤보를 열고 항목 컨트롤을 위에서부터 돌려준다."""
    from core.ui import children

    hits = [c for c in ui.by_id(ui.LOGIN_ID_COMBO) if c.visible]
    if not hits:
        return []
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    if not popups:
        ui.click(hits[0], settle=0.8)
        popups = [w for w in ui.windows() if w.text == "ItemList"]
    if not popups:
        return []
    return sorted({c.hwnd: c for c in children(popups[0].hwnd, 4)
                   if c.visible and c.text == "TextButton"}.values(),
                  key=lambda c: c.rect[1])


def require_primary_monitor(ui):
    """Viewer 창이 주 모니터 밖에 있으면 **옮기지 않고** 중단한다.

    좌표 기반 자동화는 주 모니터 해상도를 전제하므로, 다른 모니터(특히 세로로
    긴 모니터)에서 열리면 이후 모든 클릭 좌표가 어긋난다. 2026-08-28 사용자
    지적: 자동화가 창을 강제로 옮기려 했다가(멀티 모니터 DPI 가상화 탓으로
    보임) 오히려 세로 모니터로 옮겨버렸다 — **강제로 옮기지 않고, 어긋나 있으면
    그 사실을 그대로 알리고 멈춘다.**

    2026-08-31 실측: 이 검사가 `cold_start` 안에서 **기동/로그인 경로에만** 있어서,
    이미 떠 있는 Viewer 를 재사용하는 경로(`force_restart=False`, `config.json`
    기본값)에서는 아예 평가되지 않았다. 창을 (-600, 100)으로 옮긴 뒤
    `cold_start(force_restart=False)` 를 호출하니 중단 없이 정상 반환했다.
    재사용 경로를 쓰는 TC(`WF_01`/`WF_05`/`run-ui` 등)는 창이 어긋나 있어도
    그대로 진행했다는 뜻이라, 두 경로가 같은 검사를 쓰도록 함수로 뽑았다.
    """
    win = ui.main_window()
    if not win:
        return
    from core.display import screen_size

    left, top, _r, _b = win.rect
    max_w, max_h = screen_size()
    if not (0 <= left < max_w and 0 <= top < max_h):
        raise FlowError(
            f"Viewer 창이 주 모니터(1920x1080, 좌표 0,0~{max_w}x{max_h}) 밖에 "
            f"있습니다(현재 rect={win.rect}). 자동화가 임의로 창을 옮기지 "
            "않습니다 — 실제 모니터 배치/Windows 주 모니터 설정을 1920x1080 "
            "모니터로 맞춘 뒤 다시 실행하십시오.")


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
            # 재사용 경로도 기동 경로와 **같은 창 위치 검사**를 거친다.
            # `guard.sweep` 이 팝업을 클릭하므로 클릭 전에 확인해야 한다.
            require_primary_monitor(ui)
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

    require_primary_monitor(ui)

    login = cfg["viewer"]["login"]
    if ui.at_login_screen():
        # ID 입력창은 등록된 계정 목록이다(사양서1 78쪽). 요청한 계정이 선택돼
        # 있지 않으면 목록에서 고른다 — 고르지 못하면 `ui.login` 의 가드가 잡는다.
        try:
            chosen = select_login_id(
                ui, login["id"], (cfg.get("xipl") or {}).get("tesseract_exe"))
            if not chosen.get("already"):
                say(f"로그인 ID 선택: {login['id']}")
        except Exception as exc:
            say(f"로그인 ID 선택 실패(계속 진행): {exc}")
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
                    f"(증거는 Evidence/ui 참조). 계정/비밀번호를 확인하십시오.{occluded}")
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
    실패 시점 증거가 없어 확인할 수 없었다(이 저장소에서 모달이 클릭을 삼키는
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
    # Patient 화면 위에 큰 `Examined` 창이 떠 있어도 뒤쪽 Patient 컨트롤은
    # `visible=True`로 열거된다. 예전 코드는 아래 `tab_new_patient`만 보고 True를
    # 돌려 Setting 메뉴를 Examined 창 뒤에서 누르려 했다(WF14 복구 중 재현).
    # Examined는 조회 창이므로 우상단 X를 눌러 닫고 실제 Patient 화면을 확인한다.
    examined = next((w for w in ui.windows()
                     if w.visible and w.text == "Examined"), None)
    if examined is not None:
        from core.ui import children

        _l, top, right, _b = examined.rect
        closes = [c for c in children(examined.hwnd, 4)
                  if c.visible and c.ctrl_id == 4
                  and c.rect[1] < top + 90 and c.rect[0] > right - 130]
        if len({c.hwnd: c for c in closes}) == 1:
            ui.click(next(iter({c.hwnd: c for c in closes}.values())), settle=1.0)
        else:
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
    #
    # `open_main_menu` 는 상태바를 못 찾으면 `FlowError` 를 **던진다.** 이 함수는
    # bool 만 돌려주기로 한 계약이므로(위 docstring) 여기서 삼키고 False 로
    # 떨어뜨린다. 2026-08-25 WF_14 에서 정리(finally) 블록이 이 함수를 부르다
    # 예외를 맞아, **본 시험을 다 통과한 실행이 리포트조차 남기지 못했다.**
    try:
        opened = open_main_menu(ui)
    except FlowError:
        opened = False
    if opened:
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
      'fail'         - 팝업 문구를 증거로 남기고 예외 (기본. 의도치 않은 중복 검출)
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

# Emergency 검사를 닫을 때 뜨는 팝업 (2026-08-20 실측, OCR):
#   "This study is registered as Emergency study.
#    Do you want to modify study information?"
# 환자 정보를 제품이 자동 생성하므로 닫기 전에 수정 기회를 준다. 자동화는 정보를
# 수정하지 않으므로 **No** 를 누른다.
EMERGENCY_MODIFY_MARKERS = ("registered as emergency", "modify study information")


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
    if any(m in low for m in EMERGENCY_MODIFY_MARKERS):
        # "This study is registered as Emergency study. Do you want to modify
        #  study information?" — 정보를 수정하지 않으므로 **No**(우측)를 누른다.
        no = buttons[-1]
        ui.click(no, settle=1.5)
        return {"saved": False, "ctrl_id": no.ctrl_id, "message": message,
                "kind": "emergency_modify"}
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


def study_status(db, study_key):
    """`STUDY.StudyStatus` 를 읽는다(없으면 None)."""
    row = db.one("DATA", "SELECT StudyStatus FROM STUDY WHERE [Key]=@k",
                 {"k": int(study_key)})
    if not row or row.get("StudyStatus") is None:
        return None
    return int(row["StudyStatus"])


def wait_study_closed(db, study_key, timeout=20, poll=1.0):
    """검사가 Examine 에서 실제로 빠져나갔는지 DB 로 기다린다.

    반환: {"status": 마지막으로 읽은 StudyStatus, "closed": bool, "waited": 초}
    """
    end = time.time() + timeout
    started = time.time()
    status = None
    while True:
        status = study_status(db, study_key)
        closed = status is not None and status != STUDY_STATUS_EXAMINING
        if closed or time.time() >= end:
            return {"status": status, "closed": bool(closed),
                    "waited": round(time.time() - started, 1)}
        time.sleep(poll)


def close_examine_confirmed(ui, db, study_key, option="close", attempts=3,
                            verify_timeout=20, **kwargs):
    r"""`close_examine` 을 부르고 **DB 로 실제 종료를 확인**한다.

    Close 클릭이 삼켜져 검사가 열린 채 남는 경우가 있다 — `+` 클릭이 삼켜지는 것과
    같은 계열이다(근거: `core/viewer_processing.open_view_position_dialog`
    docstring). 2026-08-31 `WF_07` Step 5 에서 실측했다: Close 버튼 위에 툴팁
    ("Send & Close")만 뜨고 검사는 Examine 에 남아 `StudyStatus=1` 이 유지됐으며,
    같은 코드의 재실행 2회는 정상이었다(재현율 1/3).

    **화면만 보고는 판별할 수 없다는 것을 실측으로 확인했다(2026-08-31).**

    - 상태 배너(2202)는 커스텀 드로잉이라 텍스트가 `'TextButton'` 으로만 잡히고,
      픽셀 OCR 은 종료 직후 다른 창이 배너를 가려 `'icine —'` 같은 쓰레기를 읽었다.
      문구도 `Ready` / `Xray Block` / `Not Examine Mode` 로 여러 가지다.
    - Close 버튼(2204)은 **Examine 이 아닌 화면에서도 `visible=True`** 였다.

    그래서 제품 상태 변경은 UI(Close 클릭)로 하고 **성공 판별만 DB 로** 한다
    (이 저장소 규칙: DB 로 제품 동작을 모사하지 않고 검증에 쓴다).

    **삼켜졌을 때만 다시 누른다.** 재시도 조건은 두 가지를 모두 만족할 때다 —
    종료 옵션 팝업이 안 떴고(`dialog` 가 False), `verify_timeout` 안에
    `StudyStatus` 가 `STUDY_STATUS_EXAMINING` 에서 벗어나지 않았을 때. 팝업 없이
    정상 종료되는 경로(미촬영 Step 이 없을 때)가 따로 있어 무조건 다시 누르면
    다음 검사를 건드릴 수 있기 때문에, 이 두 조건을 함께 본다.

    반환: `close_examine` 의 반환값 + `{"attempts": n, "verify": {...}}`
    """
    closed, verify = None, None
    for attempt in range(1, attempts + 1):
        closed = close_examine(ui, option=option, **kwargs)
        verify = wait_study_closed(db, study_key, timeout=verify_timeout)
        if verify["closed"] or closed.get("dialog"):
            break
    result = dict(closed or {})
    result["attempts"] = attempt
    result["verify"] = verify
    return result


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


def instance_type_counts(db, study_key):
    """StudyKey의 INSTANCE를 InstanceType별 건수로 집계한다.

    `tests/workflow02.py`(WF_02)와 `tests/system_compat.py`(run-sys3d)가 각자
    들고 있던 동일한 조회를 공용화한 것이다 — 두 콜사이트 모두 이 SQL 그대로
    회귀에서 실측 확인됐다(2026-08-26 26차 회귀 WF_02 PASS).
    """
    rows = db.query(
        "DATA", "SELECT InstanceType,COUNT(*) AS Cnt FROM INSTANCE "
        "WHERE StudyKey=@study GROUP BY InstanceType ORDER BY InstanceType",
        {"study": study_key})
    return {int(row["InstanceType"]): int(row["Cnt"]) for row in rows}


def wait_instance_types(db, study_key, required, timeout=90, poll=2.0):
    """`required`(InstanceType -> 최소 건수)를 모두 만족할 때까지 DB를 폴링한다.

    F8 가상 촬영 후 실제 영상 생성 완료를 기다리는 상태 신호 기반 대기다.
    고정 sleep과 달리 조건이 이미 충족돼 있으면 즉시 반환하고, 느린 정상
    환경에서도 timeout까지는 실패로 감추지 않는다.
    """
    end = time.time() + timeout
    counts = instance_type_counts(db, study_key)
    while time.time() < end and any(counts.get(t, 0) < n
                                     for t, n in required.items()):
        time.sleep(poll)
        counts = instance_type_counts(db, study_key)
    return counts


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


#: Examined(View) 검색 화면의 컨트롤. `tests/workflow02._examined_search` 가
#  2026-08-19 에 실측한 값이고, 2026-08-27 에 여러 TC 가 같은 경로를 직접 밟을 수
#  있도록 여기로 올렸다(그 함수는 이제 이 구현을 부르는 얇은 래퍼다).
EXAMINED_SEARCH = {
    "field_combo": 2177,      # 검색 항목 콤보 (팝업 'ItemList' 의 ctrl_id 2 = Patient ID)
    "text": 2178,
    "button": 2179,
    "study_list": 2199,       # 카드 목록 컨테이너. 자식 중 text=='StudyListItem' 이 카드
    "row_text": "StudyListItem",
    "patient_id_option": 2,
}


def examined_search(ui, patient_id, wait=3):
    """Examined(View) 화면에서 **Patient ID 로 월 범위 검색**하고 카드를 돌려준다.

    반환: 화면에 보이는 검사 카드 컨트롤 목록 (위->아래, 왼->오른쪽 순).

    카드 순서는 제품이 **StudyDate/Time 내림차순**으로 배열한다(실측). 따라서
    `[0]` 이 가장 새 검사, `[-1]` 이 가장 오래된 검사다. 재사용 픽스처는 한 번
    만들어 계속 쓰므로 보통 마지막 카드다.

    기본 조회 범위가 "Today" 라 **Month 로 넓히고** 검색한다 — 픽스처가 다른 날
    만들어졌으면 Today 범위로는 0건이 나온다.
    """
    if not [c for c in ui.by_id(EXAMINED_SEARCH["field_combo"]) if c.visible]:
        if not open_main_menu(ui):
            raise FlowError("메인 메뉴가 열리지 않았습니다.")
        view = [c for c in ui.by_id(MAIN_MENU["item_view"])
                if c.visible and c.rect[2] - c.rect[0] > 20]
        if not view:
            raise FlowError(f"VIEW 메뉴 항목({MAIN_MENU['item_view']})을 찾지 못했습니다.")
        ui.click(view[0], settle=4)

    month = [c for c in ui.by_id(PATIENT["range_month"]) if c.visible]
    if month:
        ui.click(month[0], settle=1)
    field = [c for c in ui.by_id(EXAMINED_SEARCH["field_combo"]) if c.visible]
    edit = [c for c in ui.by_id(EXAMINED_SEARCH["text"]) if c.visible]
    search = [c for c in ui.by_id(EXAMINED_SEARCH["button"]) if c.visible]
    if not field or not edit or not search:
        raise FlowError(
            f"Examined 검색 컨트롤({EXAMINED_SEARCH['field_combo']}/"
            f"{EXAMINED_SEARCH['text']}/{EXAMINED_SEARCH['button']})을 "
            "찾지 못했습니다.")
    ui.click(field[0], settle=.5)
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    options, seen = [], set()
    for c in children(popups[0].hwnd, 3) if popups else []:
        if c.text == "TextButton" and c.visible and c.hwnd not in seen:
            seen.add(c.hwnd)
            options.append(c)
    option = [c for c in options
              if c.ctrl_id == EXAMINED_SEARCH["patient_id_option"]]
    if not option:
        raise FlowError("Patient ID 검색 옵션을 찾지 못했습니다.")
    ui.click(option[0], settle=.5)
    ui.set_text(edit[0], patient_id)
    ui.click(search[0], settle=wait)
    return examined_cards(ui)


def examined_cards(ui):
    """현재 Examined 목록에 보이는 검사 카드(위->아래, 왼->오른쪽)."""
    study_list = [c for c in ui.by_id(EXAMINED_SEARCH["study_list"]) if c.visible]
    rows, seen = [], set()
    for c in children(study_list[0].hwnd, 4) if study_list else []:
        if (c.text == EXAMINED_SEARCH["row_text"] and c.visible
                and c.hwnd not in seen):
            seen.add(c.hwnd)
            rows.append(c)
    return sorted(rows, key=lambda c: (c.rect[1], c.rect[0]))


def open_examined_study(ui, patient_id, card="oldest", settle=8.0, wait=3):
    """**Examined 목록에서 카드를 직접 골라** 검사를 View 로 연다.

    반환: `{"cards": 카드수, "picked": 0-based 순번, "picked_rect": rect,
            "steps": Step 수, "patient_id": 검색어}`

    왜 별도 함수인가 — `viewer_processing.open_test_study` 도 같은 UI 경로를
    지나지만 그 함수는 **XIPL 픽스처 준비**(Overlay 항목 보장, InstanceType
    0/1/2/3 무결성 검사, 세션 dict 구성)까지 하는 공용 준비 흐름이다. 개정본
    Step 1 이 *"Examined 창에서 검사를 선택한다"* 인 TC 들이 그 준비 흐름에
    얹혀 가면 **그 TC 가 Step 1 의 UI 경로를 직접 밟지 않게 된다** — 자동화
    범위표에서 `WF_04` 가 2026-08-26 까지 그 이유로 부분 자동이었다.
    이 함수는 검사를 고르고 여는 **그 동작만** 하고 근거를 돌려준다.

    `card` 는 `"oldest"`(기본) / `"newest"` / 0-based 정수.
    카드는 StudyDate/Time 내림차순이라 재사용 픽스처는 보통 가장 오래된 카드다
    (`open_test_study` 도 같은 규칙을 쓴다 — 나중에 생긴 빈 중복 카드를 피한다).
    """
    cards = examined_search(ui, patient_id, wait=wait)
    if not cards:
        raise FlowError(f"Examined 검색 결과가 없습니다: {patient_id}")
    if card == "oldest":
        index = len(cards) - 1
    elif card == "newest":
        index = 0
    else:
        index = int(card)
    if not 0 <= index < len(cards):
        raise FlowError(f"대상 카드 순번 {index}, 화면 카드 {len(cards)}건")
    target = cards[index]
    ui.click(target, settle=1.2)
    button = [c for c in ui.by_id(EXAMINED_VIEW_BUTTON) if c.visible]
    if not button:
        raise FlowError(
            f"Examined 의 View 버튼({EXAMINED_VIEW_BUTTON})을 찾지 못했습니다. "
            "카드가 선택되지 않았을 수 있습니다.")
    ui.click(button[0], settle=settle)
    return {"cards": len(cards), "picked": index, "picked_rect": target.rect,
            "steps": len(step_items(ui)), "patient_id": patient_id}


# Examined 툴바. **툴팁으로 확정했다**(2026-08-26) — 아이콘만으로는 구분되지
# 않는다(2196 을 '검사 내 검색' 으로 오인한 전례가 있다).
EXAMINED_SEND = 2189          # 툴팁 'Send'
EXAMINED_MULTI_SEND = 2190    # 툴팁 'Multi Send'
EXAMINED_PRINT = 2188         # 툴팁 'Print'
EXAMINED_EXPORT = 2191        # 툴팁 'Export'
EXAMINED_MOVE_IMAGE = 2197    # 툴팁 'Move Image'


def send_examined_study(ui, scope="all", attempts=4, dialog_timeout=6):
    """**Examined 목록**에서 선택한 검사를 전송한다.

    `send_current_study`(Examine 화면의 Send)와 **경로가 다르고, 결과도 다르다.**
    사양서1 이 둘을 명확히 구분한다.

      - Storage 옵션에 Send Dose SR 이 켜져 있을 때 Dose SR 을 전송하는 경우:
        **① Examine Mode 에서 자동 전송 옵션이 활성화되어 있을 때,
        ② Examined 모드에서 모든 영상을 전송할 때.**
      - 그리고 못박는다: *"Dose SR 은 검사가 종료될 때만 전송이 된다.
        (**Examine/View 모드에서 Send/Multi-Send 버튼을 클릭했을 때는 Dose SR 을
        전송하지 않는다**)"*

    그래서 **Dose SR 을 보는 TC(WF_06)는 반드시 이 함수를 써야 한다.** 검사를
    `open_test_study` 로 열어(View 모드) `send_current_study` 를 부르면 Dose SR 이
    오지 않는 것이 **정상**이라, 제품 결함으로 오판하게 된다(2026-08-26 실제로
    그렇게 보고했다가 사용자 지적으로 바로잡았다).

    호출 전에 Examined 목록에서 **대상 검사 카드를 선택**해 두어야 한다.
    """
    if scope not in SEND_SCOPE_IDS:
        raise FlowError(f"알 수 없는 전송 범위: {scope}")
    target_id = SEND_SCOPE_IDS[scope]

    for _ in range(attempts):
        buttons = [c for c in ui.by_id(EXAMINED_SEND)
                   if c.visible and (c.rect[2] - c.rect[0]) >= 30]
        if not buttons:
            raise FlowError(
                f"Examined 의 Send 버튼({EXAMINED_SEND})을 찾지 못했습니다. "
                "Examined 화면인지 확인하십시오.")
        ui.click(buttons[0], settle=2.0)
        end = time.time() + dialog_timeout
        while time.time() < end:
            hits = [c for c in ui.by_id(target_id) if c.visible]
            if hits:
                ui.click(hits[0], settle=2.5)
                return {"scope": scope, "clicked": target_id,
                        "via": "Examined Send"}
            time.sleep(.5)
    raise FlowError(
        f"Examined Send 후 전송 범위 선택 메시지 박스가 {attempts}회 시도에도 "
        f"나타나지 않았습니다. 대상 검사 카드가 선택돼 있는지 확인하십시오.")
