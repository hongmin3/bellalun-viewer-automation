# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_10 — MWL Hospital Code와 Procedure 매핑.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.

체크리스트 원문 (변경 금지)
  Step
    1. Setting > Procedure > Hospital Code에서 HC를 추가한다.
    2. HC에 Procedure를 매핑한다.
    3. Setting > DICOM > MWL에서 Hospital Code Mapping을 추가한다.
    4. RIS/MWL 서버에 HC가 포함된 처방을 등록한다.
    5. Patient 창의 Patient List에서 MWL을 조회한다.
    6. 해당 처방을 선택한다.
    7. Examine 버튼을 클릭한다.
  Expected Result
    1. Hospital Code가 저장된다.
    2. Procedure 매핑이 저장된다.
    3. MWL Hospital Code Mapping이 저장된다.
    4. 검증용 처방이 MWL 서버에 등록된다.
    5. 해당 처방이 목록에 표시된다.
    6. 선택한 처방의 Hospital Code와 Procedure 단계가 표시된다.
    7. Examine 모드에 매핑된 Procedure Step이 등록되고 첫 Step/Preset이 선택된다.

**Test Data 를 2026-08-20 에 수정했다.** 원문은 코드 값을 `HC_FLOW_01` 로 두었는데
사용자 지시로 **`HC`** 로 바꿨다. Procedure 도 `PROC_FLOW_01` 을 새로 만들지 않고
제품에 이미 있는 것을 매핑한다(새로 만들면 촬영 Step 구성까지 필요해 TC 범위를
벗어난다). TC ID 는 건드리지 않았다.

실측한 흐름 (2026-08-20)
  Setting > Procedure > Hospital Code(215)
    `+`(2558) -> 인라인 행 추가. **이것만으로 DB 에 즉시 저장된다.**
    Code 셀 **진짜 더블클릭**(`ui.double_click`) -> 표준 Edit 열림 -> 값 입력
      `ui.click()` 두 번은 간격이 벌어져 더블클릭으로 인식되지 않는다.
    Procedure 열의 톱니바퀴(행 rect 에서 계산) -> `View Position` 대화상자
      탭 2086 `Procedure` -> 목록에서 Procedure 선택 -> 1101 OK
    Update(2226) -> 셀 편집 값이 확정된다(`+` 와 달리 편집은 Update 가 필요하다)
  Setting > DICOM > MWL 의 `Hospital Code Mapping` 콤보(2453)
    등록된 코드가 없으면 **목록이 아예 열리지 않는다.** 그래서 순서가 중요하다.
  MWL 처방 등록은 `core/mwl.py` 가 한다(`POST /worklist/new`,
    `make_mg_order(..., hospital_code=...)` -> Requested Procedure Code Value).

  DB: `PROCEDURE.HOSPITAL_CODE(Key, Code, Description, MappingKey, MappingType)`
      매핑은 `MappingKey` = `PROCEDURE_INFO.Key`.
"""

from __future__ import annotations

import os
import time
from datetime import date

from core import flows, mwl, screen, uitext
from core.result import FAIL, MANUAL, PASS, TCResult
from core.ui import children

# 사용자 지시(2026-08-20): "HC_FLOW_01 로 입력하지 말고 HC 로 입력을 해주고"
DEFAULT_CODE = "HC"
# 제품에 이미 있는 Procedure 를 매핑한다. 첫 항목(Default=1)이 Routine Mammography 다.
PROCEDURE_NAME = "Routine Mammography"
PATIENT_ID = "MWL_HC_01"


def _codes(db):
    return {r["Code"]: r for r in db.query(
        "PROCEDURE",
        "SELECT [Key],Code,Description,MappingKey,MappingType "
        "FROM HOSPITAL_CODE ORDER BY [Key]")}


def _procedures(db):
    return {r["Name"]: r for r in db.query(
        "PROCEDURE", "SELECT [Key],Name,[Default] FROM PROCEDURE_INFO "
                     "ORDER BY [Key]")}


def _rows(ui):
    return uitext.list_rows(ui, flows.SETTING_HOSPITAL_CODE["list"])


def _wait_study(db, patient_id, after_key=0, timeout=40):
    """MWL 처방으로 만들어진 검사 행이 나타날 때까지 기다린다.

    Examine 진입은 검사 행을 만드는 비동기 동작이라 즉시 조회하면 없다. 고정
    대기를 쓰지 않고 **행이 생길 때까지** 기다린다.
    """
    end = time.time() + timeout
    row = None
    while time.time() < end:
        row = db.one(
            "DATA",
            "SELECT TOP 1 s.[Key],s.HospitalCode,s.ProcedureKey,"
            "s.RequestedProcedureID,s.StudyInstanceUID,p.PatientID "
            "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
            "WHERE p.PatientID=@pid AND s.[Key]>@k "
            "ORDER BY s.[Key] DESC", {"pid": patient_id, "k": after_key})
        if row:
            return row
        time.sleep(1)
    return row


def _clear_codes(ui, db, tesseract_exe=None, limit=10):
    """기존 Hospital Code 행을 지운다.

    행을 **선택**할 때 행 중앙을 누르면 톱니바퀴가 눌려 대화상자가 열리고, 그 팝업이
    이후 클릭을 삼킨다(2026-08-20 실측). 좌측 Code 셀을 누른다.
    """
    for _ in range(limit):
        rows = _rows(ui)
        if not rows:
            break
        ui.click(flows.hospital_code_cell(rows[0], "code"), settle=1.0)
        delete = [c for c in ui.by_id(flows.SETTING_HOSPITAL_CODE["delete"])
                  if c.visible]
        if not delete:
            break
        ui.click(delete[0], settle=1.2)
        if ui.dialog():
            if flows.confirm_study_delete(ui, accept=True, timeout=4) is None:
                ui.dismiss_dialog(timeout=2)
        time.sleep(.8)
    return _codes(db)


def _add_code(ui, code, tesseract_exe=None):
    """Hospital Code 행을 만들고 Code 값을 입력한다. 반환: 그 행."""
    add = [c for c in ui.by_id(flows.SETTING_HOSPITAL_CODE["add"]) if c.visible]
    if not add:
        raise RuntimeError(
            f"Hospital Code 추가 버튼({flows.SETTING_HOSPITAL_CODE['add']})을 "
            "찾지 못했습니다.")
    ui.click(add[0], settle=2.0)
    rows = _rows(ui)
    if not rows:
        raise RuntimeError("Hospital Code 행이 추가되지 않았습니다.")
    row = rows[-1]
    # **진짜 더블클릭**이어야 편집 모드가 열린다.
    ui.double_click(flows.hospital_code_cell(row, "code"), settle=1.4)
    edits = [c for c in ui.controls(max_depth=10)
             if c.visible and c.cls in ("Edit", "RichEdit20W")]
    if not edits:
        raise RuntimeError(
            "Code 셀 편집 모드가 열리지 않았습니다. ui.double_click 의 클릭 간격이 "
            "시스템 더블클릭 임계값을 넘었을 수 있습니다.")
    ui.type_text(edits[0], code, clear=True, settle=.8)
    import ctypes
    ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)
    time.sleep(1.0)
    return _rows(ui)[-1]


def _map_procedure(ui, row, name, tesseract_exe=None):
    """행의 톱니바퀴로 `View Position` 대화상자를 열어 Procedure 를 매핑한다."""
    ui.click(flows.hospital_code_cell(row, "gear"), settle=2.5)
    end = time.time() + 10
    dlg = None
    while time.time() < end:
        found = [w for w in ui.windows()
                 if 1000 < w.rect[2] - w.rect[0] < 1600
                 and 500 < w.rect[3] - w.rect[1] < 800]
        if found:
            dlg = found[0]
            break
        time.sleep(.5)
    if dlg is None:
        raise RuntimeError("View Position 대화상자가 열리지 않았습니다.")

    tab = [c for c in children(dlg.hwnd, 6) if c.visible
           and c.ctrl_id == flows.VIEW_POSITION_DIALOG["tab_procedure"]]
    if not tab:
        raise RuntimeError(
            f"Procedure 탭({flows.VIEW_POSITION_DIALOG['tab_procedure']})을 "
            "찾지 못했습니다.")
    ui.click(tab[0], settle=2.5)

    # 목록 행 ctrl_id 가 PROCEDURE_INFO.Key 와 일치하지만 **헤더도 id=1** 이라
    # 순서로 고르지 않는다. 문구를 OCR 로 읽어 고른다.
    items = sorted(
        {(c.ctrl_id, c.rect): c for c in children(dlg.hwnd, 6)
         if c.visible and c.rect[2] - c.rect[0] > 200
         and 20 < c.rect[3] - c.rect[1] < 60
         and dlg.rect[1] + 120 < c.rect[1] < dlg.rect[3] - 120}.values(),
        key=lambda c: c.rect[1])
    target, seen = None, []
    for item in items:
        text = uitext.ocr(item, tesseract_exe)
        seen.append(text)
        if uitext.norm(name) in uitext.norm(text):
            target = item
            break
    if target is None:
        raise RuntimeError(
            f"Procedure 탭에서 {name!r} 을 찾지 못했습니다. 읽은 항목={seen}. "
            "엉뚱한 Procedure 를 고르지 않도록 중단합니다.")
    ui.click(target, settle=1.2)
    ok = [c for c in children(dlg.hwnd, 6) if c.visible
          and c.ctrl_id == flows.VIEW_POSITION_DIALOG["ok"]]
    if not ok:
        raise RuntimeError("View Position 대화상자의 OK 를 찾지 못했습니다.")
    ui.click(ok[0], settle=2.0)
    return {"procedure": name, "items_read": seen}


def run(ctx):
    r = TCResult("TC_Basic_WorkFlow_10", "MWL Hospital Code와 Procedure 매핑")
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    code = (ctx.cfg.get("test_data") or {}).get("hospital_code") or DEFAULT_CODE
    if code.upper().startswith("HC_FLOW"):
        # 사용자 지시로 짧은 코드를 쓴다. 설정에 옛 값이 남아 있어도 따르지 않는다.
        code = DEFAULT_CODE
    evidence = os.path.join(ctx.evidence_root, "Flow", "10_HospitalCode")
    ui = None
    created_code = False
    examine_opened = False
    try:
        station = next((x for x in ctx.cfg["dicom"]["servers_to_register"]
                        if x["kind"] == "MWL"), {})
        procs = _procedures(ctx.db)
        if PROCEDURE_NAME not in procs:
            raise RuntimeError(
                f"PROCEDURE_INFO 에 {PROCEDURE_NAME!r} 이 없습니다: "
                f"{sorted(procs)[:6]}")
        want_proc = procs[PROCEDURE_NAME]

        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError("Patient 화면이 준비되지 않았습니다")

        # --- Step 1: Hospital Code 추가 ----------------------------------
        flows.open_group_page(ui, "procedure", "hospital_code", wait=3.0)
        before = _clear_codes(ui, ctx.db, tess)
        if before:
            raise RuntimeError(
                f"기존 Hospital Code 를 정리하지 못했습니다: {sorted(before)}. "
                "판정이 오염되므로 중단합니다.")
        row = _add_code(ui, code, tess)
        created_code = True

        # --- Step 2: Procedure 매핑 --------------------------------------
        mapped = _map_procedure(ui, row, PROCEDURE_NAME, tess)
        flows.setting_update(ui, wait=3)
        if ui.dialog():
            ui.dismiss_dialog(timeout=3)
        end = time.time() + 12
        saved = _codes(ctx.db)
        while time.time() < end and code not in saved:
            time.sleep(1)
            saved = _codes(ctx.db)
        path = os.path.join(evidence, "01_hospital_code.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)

        entry = saved.get(code)
        r.assert_true(
            1, f"[Setting > Procedure > Hospital Code] {code} 저장",
            entry is not None,
            expected={"Code": code},
            actual={"saved": saved, "codes": sorted(saved)},
            note="Expected 1. Hospital Code 가 저장된다. `+`(2558)는 인라인 행을 "
                 "만들고 **그것만으로 DB 에 즉시 저장된다**. Code 값은 진짜 "
                 "더블클릭(ui.double_click)으로 편집 모드를 열어 입력하고 "
                 "Update(2226)로 확정한다 — 조작마다 저장 시점이 다르다.")

        r.assert_true(
            2, f"{code} 에 Procedure({PROCEDURE_NAME}) 매핑",
            entry is not None
            and int(entry.get("MappingKey", -1)) == int(want_proc["Key"]),
            expected={"MappingKey": want_proc["Key"],
                      "Procedure": PROCEDURE_NAME},
            actual={"entry": entry, "picked": mapped},
            note="Expected 2. Procedure 매핑이 저장된다. 행의 톱니바퀴로 "
                 "`View Position` 대화상자를 열고 Procedure 탭(2086)에서 고른다. "
                 "매핑은 HOSPITAL_CODE.MappingKey = PROCEDURE_INFO.Key 로 기록된다. "
                 "탭 목록의 행 ctrl_id 가 Key 와 일치하지만 헤더도 id=1 이라 순서로 "
                 "고르지 않고 문구를 OCR 로 읽어 고른다.")

        # --- Step 3: Setting > DICOM > MWL 의 Hospital Code Mapping -------
        # 이 콤보의 항목은 **Hospital Code 값이 아니라 DICOM 태그 목록**이다.
        # `core/mwl.py` 가 Hospital Code 를 Requested Procedure Code Value 로
        # 넣으므로 (0032,1064) Requested Procedure Code Sequence 를 골라야 짝이 맞는다.
        flows.open_dicom_setting(ui, "mwl", wait=3.0)
        # **SCP 를 먼저 선택해야 우측 설정이 활성화된다**(선택 전에는 콤보 목록이
        # 아예 열리지 않는다).
        scp = flows.select_first_scp(ui, tess)
        want_tag = flows.MWL_CODE_MAPPING_TAGS[
            "requested_procedure_code_sequence"]
        combo_items = []
        picked_mapping = None
        try:
            # 항목은 `(0032,1064) Requested Procedure Code Sequence` 처럼 길다.
            # 태그 번호로 **부분일치**하되 두 개 이상 걸리면 실패한다.
            picked_mapping = uitext.pick_combo_by_text(
                ui, flows.MWL_HOSPITAL_CODE_MAPPING, want_tag, tess,
                what="Hospital Code Mapping", match="contains")
            combo_items = picked_mapping.get("items_read", [])
            flows.setting_update(ui, wait=3)
            if ui.dialog():
                ui.dismiss_dialog(timeout=3)
        except Exception as exc:
            picked_mapping = {"error": str(exc), "scp": scp}
        path = os.path.join(evidence, "02_mwl_mapping.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        mapping_row = ctx.db.one(
            "CONFIGURATION",
            "SELECT Name,CodeMappingTag FROM DICOM_MWL WHERE Name=@n",
            {"n": station.get("name", "MWL_TEST")}) if station else None
        r.assert_true(
            3, f"MWL 의 Hospital Code Mapping 을 {want_tag} 로 설정",
            bool(picked_mapping) and "error" not in picked_mapping,
            expected={"콤보": flows.MWL_HOSPITAL_CODE_MAPPING,
                      "선택": f"{want_tag} Requested Procedure Code Sequence"},
            actual={"picked": picked_mapping, "items": combo_items,
                    "scp": scp, "db": mapping_row},
            note="Expected 3. MWL Hospital Code Mapping 이 저장된다. 이 콤보의 항목은 "
                 "**Hospital Code 값이 아니라 DICOM 태그 목록**이다(None / "
                 "(0040,1001) Requested Procedure ID / (0032,1060) Requested "
                 "Procedure Description / (0032,1064) Requested Procedure Code "
                 "Sequence / (0040,0007) SPS Description / (0040,0009) SPS ID). "
                 "즉 Viewer 가 Hospital Code 를 어느 태그에서 읽을지 정하는 설정이다. "
                 "core/mwl.py 가 Hospital Code 를 Requested Procedure Code Value 로 "
                 "넣으므로 (0032,1064) 를 고른다. **SCP 목록에서 서버를 먼저 선택해야 "
                 "이 콤보가 활성화된다** — 선택 전에는 목록이 열리지 않는다.")

        # --- Step 4: MWL 서버에 처방 등록 ---------------------------------
        server = mwl.MwlServer(ctx.cfg["dicom"]["mwl_server_url"])
        today = date.today().strftime("%Y-%m-%d")
        server.delete_where(patient_id=PATIENT_ID)
        fields = mwl.make_mg_order(
            patient_id=PATIENT_ID, patient_name="MWL^HC",
            accession_number="ACC_HC_001", sps_id="SPS_HC_001",
            station_ae=ctx.cfg["viewer"].get("station_ae_title", "BELLALUN"),
            sps_start_date=today, procedure_description=PROCEDURE_NAME,
            hospital_code=code)
        created = server.create(**fields)
        listed = server.find(patient_id=PATIENT_ID)
        r.assert_true(
            4, f"MWL 서버에 {code} 가 포함된 처방 등록", bool(listed),
            expected={"PatientID": PATIENT_ID, "hospital_code": code},
            actual={"created": created, "listed": listed},
            note="Expected 4. 검증용 처방이 MWL 서버에 등록된다. core/mwl.py 가 "
                 "시험용 MWL SCP 를 HTTP 로 제어한다(POST /worklist/new). "
                 "Hospital Code 는 make_mg_order 가 Requested Procedure Code Value"
                 "(rp_code_value)로 넣는다.")

        # --- Step 5~7: MWL 조회 -> 처방 선택 -> Examine --------------------
        # 판정 기준을 2026-08-21 에 확정했다(그전에는 "화면 OCR 인지 DB 인지"가
        # 미결이라 MANUAL 이었다). 결론: **DB 가 주 판정, 화면이 보강**이다.
        #   Expected 6 "선택한 처방의 Hospital Code 와 Procedure 단계가 표시된다"
        #     -> `STUDY.HospitalCode` 와 `STUDY.ProcedureKey` 가 결정적이다.
        #        화면 OCR 로 코드 문자열을 읽는 것보다 직접적이고, Viewer 가
        #        MWL 태그(0032,1064)의 코드를 **매핑된 Procedure 로 해석했는지**를
        #        바로 보여 준다.
        #   Expected 7 "매핑된 Procedure Step 이 등록되고 첫 Step/Preset 이 선택된다"
        #     -> Step 개수는 `PROCEDURE_ITEMS` 의 그 Procedure 행 수와 대조한다
        #        (Routine Mammography = 4행). 선택·준비 상태는 Examine 상단 배너
        #        (`flows.examine_status`)가 Ready 인지로 본다.
        # **이 판정이 자기충족이 아닌 근거**: `TC_Basic_WorkFlow_01` 은 Procedure 가
        # 없는 MWL 처방으로 들어가 **Step 수 = 0** 을 확인한다. 같은 코드 경로가
        # 매핑이 있을 때만 Step 을 만든다는 대조군이 이미 있다.
        proc_key = int(want_proc["Key"])
        want_steps = ctx.db.scalar(
            "PROCEDURE",
            "SELECT COUNT(*) FROM PROCEDURE_ITEMS WHERE ProcedureKey=@k",
            {"k": proc_key}) or 0

        # **Step 1~4 는 Setting 화면에서 끝난다.** 거기서 곧바로 Patient List 탭을
        # 찾으면 없다(2026-08-21 실측: 랜드마크 `['status_bar','setting','examine']`
        # 상태에서 탭 2284 를 20초 동안 못 찾고 실패). `ensure_patient_screen` 이
        # Setting 모달을 닫고(잔여 변경 저장 확인 팝업까지 처리) Patient 화면으로
        # 옮겨 준다.
        if not flows.ensure_patient_screen(ui):
            raise flows.FlowError(
                "Setting 화면에서 Patient 화면으로 돌아가지 못했습니다: "
                f"랜드마크={flows.known_screen(ui)}")
        flows.open_patient_list_tab(ui)
        flows.select_patient_source(ui, "mwl")
        found = flows.search_patient(ui, PATIENT_ID, "patient_id")
        d = ui.dialog()
        if d:
            path = os.path.join(evidence, "05_mwl_search_error.png")
            try:
                ui.capture_dialog(d, path)
                r.attach(path)
            except Exception:                          # noqa: BLE001
                pass
            message = ui.dialog_text(d) or "MWL 조회 오류 팝업"
            ok = next((x for x in ui.dialog_buttons(d)
                       if x.ctrl_id == flows.SETTING_CONFIRM_OK), None)
            if ok:
                ui.click(ok, settle=.5)
            raise flows.FlowError(
                f"MWL 조회 오류 팝업을 닫고 중단했습니다: {message}")
        path = os.path.join(evidence, "05_mwl_list.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        r.assert_equal(
            5, "Patient List 의 MWL 조회에 해당 처방 표시", 1, found,
            note="Expected 5. 등록한 처방이 목록에 표시된다. 화면 행 수를 세는 것이 "
                 "아니라 `flows.search_patient` 가 돌려주는 실제 목록 행 수로 "
                 "판정한다.")
        if found != 1:
            raise flows.FlowError(
                f"MWL 조회 결과가 {found}건이라 Step 6~7 을 수행할 수 없습니다.")

        # --- Step 6 ---------------------------------------------------
        flows.select_study_row(ui, 1)
        before_key = ctx.db.scalar(
            "DATA", "SELECT ISNULL(MAX([Key]),0) FROM STUDY") or 0
        ui.click(flows._need(ui, flows.PATIENT["examine_from_list"], "Examine"),
                 settle=1.5)
        # 이전 실행이 남긴 같은 환자 검사가 있으면 중복 안내가 뜬다(WF_01 과 같다).
        dup = flows.handle_select_patient_information(ui, "use_existing",
                                                      timeout=5)
        if not flows.wait_controls(ui, [flows.EXAMINE["edit_information"]],
                                   timeout=15):
            raise flows.FlowError("Examine 화면에 진입하지 못했습니다.")
        examine_opened = True
        study = _wait_study(ctx.db, PATIENT_ID, before_key)
        path = os.path.join(evidence, "06_examine.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        r.assert_equal(
            6, f"선택한 처방의 Hospital Code 가 검사에 반영({code})",
            code, (study or {}).get("HospitalCode"),
            note="Expected 6. Viewer 가 MWL 처방의 "
                 f"{want_tag} Requested Procedure Code Sequence 에서 읽은 코드를 "
                 "검사에 기록했는지 `STUDY.HospitalCode` 로 확인한다. 화면 문자열 "
                 "OCR 보다 직접적이다(중복 검사 안내 처리: "
                 f"{dup}).")
        # `STUDY.ProcedureKey` 는 **판정에 쓰지 않는다.** 2026-08-21 실측에서
        # MWL 유래 검사는 Hospital Code 가 있든 없든 `-1` 이었고(이 검사도,
        # Hospital Code 없이 만든 `DATA_FLOW_MWL_01` 도), Local 생성 검사만 `1` 이었다.
        # 즉 이 컬럼은 MWL 경로에서 채워지지 않으며 매핑 동작의 지표가 아니다.
        # 처음에 이 값을 기대값으로 넣어 FAIL 이 났는데, **의미를 확인하지 않은
        # 대리 지표**를 판정에 쓴 내 잘못이었다(운영 지침 10절). 관측만 남긴다.
        r.add(6, "[관측] MWL 유래 검사의 STUDY.ProcedureKey", PASS,
              expected="참고 정보 (사양에 정의된 관찰 대상이 아니다)",
              actual={"ProcedureKey": (study or {}).get("ProcedureKey"),
                      "RequestedProcedureID": (study or {}).get(
                          "RequestedProcedureID"),
                      "HOSPITAL_CODE.MappingKey": proc_key},
              note="2026-08-21 실측: MWL 유래 검사는 Hospital Code 유무와 무관하게 "
                   "`-1` 이고 Local 생성 검사만 `1` 이다. 이 컬럼이 무엇을 뜻하는지 "
                   "문서로 확인되지 않았으므로 **기대값을 정하지 않고 기록만 한다.** "
                   "매핑이 실제로 적용됐는지는 아래 Expected 7 의 Step 수 대조가 "
                   "답한다 — 그것이 체크리스트가 요구하는 '**Procedure 단계가 "
                   "표시된다**' 에 직접 대응한다.")

        # --- Step 7 ---------------------------------------------------
        steps = flows.step_items(ui)
        r.assert_equal(
            7, "Examine 모드에 매핑된 Procedure Step 등록", want_steps, len(steps),
            note="Expected 7 이자 **Expected 6 의 'Procedure 단계가 표시된다' 근거**. "
                 "기대값을 코드에 박지 않고 "
                 f"`PROCEDURE_ITEMS(ProcedureKey={proc_key})` 행 수로 계산한다"
                 f"(실측 {want_steps}행). **이 판정이 매핑 동작의 결정적 근거인 이유**: "
                 "TC_Basic_WorkFlow_01 은 Hospital Code 가 없는 MWL 처방으로 Examine 에 "
                 "들어가 **Step 수 0** 을 확인한다. 같은 MWL 경로가 매핑이 있을 때만 "
                 "Step 을 만든다는 대조군이 이미 있으므로, 이 판정은 항상 참이 되는 "
                 "종류가 아니다.")
        status = flows.examine_status(ui)
        r.assert_true(
            7, "첫 Step/Preset 이 선택되어 촬영 준비 상태",
            bool(status.get("ready")),
            expected="Examine 상단 배너 Ready",
            actual=status,
            note="Expected 7. 'Preset 이 선택되었다'를 직접 읽을 수 있는 컨트롤이 "
                 "없어(커스텀 렌더) 상단 상태 배너로 판정한다 — View Position 이 "
                 "등록되지 않았거나 Step 이 선택되지 않으면 Ready 가 되지 않는다"
                 "(`core/flows.examine_status`, 녹색 비율로 판독). "
                 "**이 실행으로 말할 수 없는 것**: 선택된 Preset 의 이름 — "
                 "준비 상태까지만 확인했다.")
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_10 실행", exc)
    finally:
        # Examine 화면을 열어 둔 채 끝내면 다음 TC 가 Patient 화면을 못 찾는다.
        # 이 검사는 촬영하지 않으므로 `close` 를 고르면 제품이 "This study will
        # be deleted" 확인을 띄우고, `close_examine` 이 Yes 로 처리해 검사까지
        # 정리된다(영상이 있으면 그 확인은 뜨지 않으므로 데이터 유실 위험 없음).
        if examine_opened and ui is not None:
            try:
                closed = flows.close_examine(ui, option="close", wait=6)
                left = _wait_study(ctx.db, PATIENT_ID, timeout=3)
                r.add(0, "뒷정리: Examine 종료 및 시험 검사 삭제",
                      PASS if left is None else MANUAL,
                      expected="Examine 종료 + 시험 검사(MWL_HC_01) 삭제",
                      actual={"close": closed,
                              "남은 검사": left and dict(left)},
                      note="촬영하지 않은 검사라 Close 시 제품이 삭제 확인을 띄운다. "
                           "남아 있으면 다음 실행의 Step 5 조회가 중복 안내를 "
                           "만나므로 정리 여부를 판정으로 남긴다.")
            except Exception as exc:                   # noqa: BLE001
                r.add(0, "뒷정리: Examine 종료", MANUAL,
                      actual=f"종료 실패({type(exc).__name__}: {exc}). "
                             "Viewer 를 재시작하면 정리된다.")
        # 시험용 Hospital Code 와 처방을 남기지 않는다.
        if created_code and ui is not None:
            try:
                flows.open_group_page(ui, "procedure", "hospital_code", wait=3.0)
                left = _clear_codes(ui, ctx.db, tess)
                flows.setting_update(ui, wait=2)
                if ui.dialog():
                    ui.dismiss_dialog(timeout=2)
                r.add(0, "뒷정리: Hospital Code 삭제",
                      PASS if not left else MANUAL,
                      expected="HOSPITAL_CODE 0행",
                      actual=f"남은 {sorted(left)}" if left else "삭제 확인")
            except Exception as exc:
                r.add(0, "뒷정리: Hospital Code 삭제", MANUAL,
                      actual=f"삭제 실패({exc}). PROCEDURE.HOSPITAL_CODE 를 확인해 "
                             "수동으로 지우십시오.")
        try:
            mwl.MwlServer(ctx.cfg["dicom"]["mwl_server_url"]).delete_where(
                patient_id=PATIENT_ID)
        except Exception:
            pass
    return r
