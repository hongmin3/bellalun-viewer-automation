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
        r.manual(
            5, "Patient List 에서 MWL 조회 / 처방 선택 / Examine",
            "Step 1~4 까지 자동화했다. 5~7 단계는 아직 붙이지 않았다 — "
            "**해제 조건**: WF_01 이 이미 MWL 조회와 Examine 진입을 자동화하고 있어"
            "(tests/workflow01.py) 그 절차를 재사용하면 된다. 다만 Expected 6 의 "
            "'선택한 처방의 Hospital Code 와 Procedure 단계가 표시된다'와 Expected 7 의 "
            "'첫 Step/Preset 이 선택된다'를 무엇으로 판정할지(화면 OCR 인지 DB 인지) "
            "확정이 필요하다. "
            "**이 실행으로 말할 수 없는 것**: 등록한 Hospital Code 가 실제로 Viewer 의 "
            "Examine 모드에 Procedure Step 으로 반영되는지 — Step 1~4 는 설정과 처방이 "
            "저장된 것까지만 확인했다.")
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_10 실행", FAIL, actual=str(exc))
    finally:
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
