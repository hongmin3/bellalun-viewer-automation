# -*- coding: utf-8 -*-
"""TC_Basic_WorkFlow_04 — Overlay.

체크리스트 원문 (변경 금지):
  Step 1. Setting - Display - Overlay - Image Overlay를 추가한다.
  Step 2. Setting - DICOM - Print - Print Overlay를 추가한뒤 Print의 Overlay항목에
          추가한 Print Overlay를 선택한다.
  Step 3. DICOM Send, Print, Export 확인한다.
  Expected: 3. Overlay 항목이 포함된채 Image가 전송된다.
            시스템정보: compression, HVL, AGD, Thickness 등
            환자정보: ID, birthdate

사용자 확정 사항 (2026-08-18):
  * 범위는 **Send + Print + Export 전부**.
  * Print Overlay는 WF03가 이미 등록하는 6개를 재사용한다 — Patient ID,
    Birth Date, Thickness, Compression Force, HVL, AGD. Expected Result의
    시스템정보/환자정보와 정확히 일치한다.
  * Image Overlay에 추가할 2개는 **Dose kVp + Dose mAs**.
  * Export 경로는 **제품 기본값**을 쓴다(폴더 선택 창은 뜨지 않고 경로 Edit에
    `<data_dir>\\Export`가 이미 채워져 있다 — 실측).

판정 근거(운영 지침 2절): 설정 저장은 DB로, 전송은 **실제 수신 객체의 UID를 DB와
대조**하고, Export는 **경로에 생긴 파일**로 판정한다. 버튼을 눌렀다는 사실만으로
판정하지 않는다.
"""

import os
import time

from core import dicomlite, export_manager as em, flows, print_overlay
from core import viewer_processing as vp
from core.dicom_settings import ensure_bunny
from core.result import TCResult, PASS, FAIL, MANUAL

IMAGE_OVERLAY_ADD = ["Dose kVp", "Dose mAs"]


def _received_uids(ctx):
    root = (ctx.cfg.get("dicom") or {}).get("received_root") or ""
    if not root or not os.path.isdir(root):
        return None, []
    objects = dicomlite.scan_dir(root)
    return objects, [o.get("SOPInstanceUID") for o in objects
                     if o.get("SOPInstanceUID")]


def _clear_received(ctx):
    root = (ctx.cfg.get("dicom") or {}).get("received_root") or ""
    if root and os.path.isdir(root):
        for dirpath, _, files in os.walk(root):
            for name in files:
                try:
                    os.remove(os.path.join(dirpath, name))
                except OSError:
                    pass


def _db_uids(ctx, patient_id):
    return {r["ImageInstanceUID"] for r in ctx.db.query(
        "DATA",
        "SELECT i.ImageInstanceUID FROM INSTANCE i "
        "JOIN STUDY s ON s.[Key]=i.StudyKey JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid AND i.ImageInstanceUID IS NOT NULL",
        {"pid": patient_id})}


def _open_examined(ui, wait=6):
    """메인 메뉴 > View 로 Examined 창을 열고 검색해 목록을 채운다.

    검색 버튼은 **2179**(돋보기)다. 2180은 새로고침이라 눌러도 목록이 채워지지
    않는다(2026-08-18 실측 — 이걸 혼동해 "목록이 비었다"고 오진한 적이 있다).
    """
    flows.open_main_menu(ui)
    view = [c for c in ui.by_id(flows.MAIN_MENU["item_view"])
            if c.visible and c.rect[2] - c.rect[0] > 20]
    if not view:
        raise flows.FlowError("View 메뉴 항목을 찾지 못했습니다.")
    ui.click(view[0], settle=wait)
    search = [c for c in ui.by_id(2179) if c.visible]
    if not search:
        raise flows.FlowError("Examined 검색 버튼(2179)을 찾지 못했습니다.")
    ui.click(search[0], settle=3)
    time.sleep(1.5)


def workflow_04(ctx):
    r = TCResult("TC_Basic_WorkFlow_04", "Overlay")
    patient_id = (ctx.cfg.get("xipl") or {}).get(
        "test_patient_id", "DATA_FLOW_MWL_01")
    try:
        if not ensure_bunny(ctx.cfg):
            r.add(0, "Storage SCP(Bunny) 기동", FAIL,
                  expected="Bunny 실행 및 수신 포트 대기", actual="확인 실패")
            return r

        session = vp.open_test_study(ctx)
        ui = session["ui"]

        # --- Step 1: Image Overlay 추가 -------------------------------
        if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
            flows.close_examine(ui, option="suspend", wait=10)
        flows.ensure_patient_screen(ui, wait=3)
        added = vp.add_image_overlay_items(ui, ctx.db, IMAGE_OVERLAY_ADD)
        want_ids = {vp.OVERLAY_FIELD_IDS[x] for x in IMAGE_OVERLAY_ADD}
        saved_ids = set(added["after"])
        r.assert_true(
            1, "Setting > Display > Overlay에 Image Overlay 항목 추가",
            want_ids <= saved_ids,
            expected={"labels": IMAGE_OVERLAY_ADD, "field_ids": sorted(want_ids)},
            actual=added,
            note="CONFIGURATION.OVERLAY_ITEM으로 대조. FieldID는 추가해 보고 실측한 값"
                 "(Dose kVp=115, Dose mAs=118).")

        # --- Step 2: Print Overlay 등록 및 Print에서 선택 --------------
        tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
        po = print_overlay.ensure_print_overlay(ui, ctx.db, tess)
        print_spec = next(x for x in ctx.cfg["dicom"]["servers_to_register"]
                          if x["kind"] == "Print")
        applied = print_overlay.apply_to_print_server(
            ui, ctx.db, print_spec["name"], po["overlay"]["Key"],
            tesseract_exe=tess)
        r.assert_true(
            2, "Setting > DICOM > Print Overlay 추가 및 Print에서 선택",
            len(po["items"]) == len(print_overlay.PRINT_ITEMS)
            and applied.get("Overlay") == po["overlay"]["Key"],
            expected={"name": print_overlay.OVERLAY_NAME,
                      "items": [x[0] for x in print_overlay.PRINT_ITEMS],
                      "print_server_overlay_key": po["overlay"]["Key"]},
            actual={"saved": po, "applied": applied},
            note="Expected Result의 시스템정보(compression/HVL/AGD/Thickness)와 "
                 "환자정보(ID/birthdate)가 이 6개 항목이다. "
                 "PRINT_OVERLAY_ITEM 저장과 DICOM_PRINT.Overlay 선택을 DB로 대조.")

        # --- Step 3-a: DICOM Send -------------------------------------
        session = vp.open_test_study(ctx)
        ui = session["ui"]
        flows.select_step(ui, session["step_2d"])
        vp.expand_tools(ui)
        _clear_received(ctx)
        sent = flows.send_current_study(ui, scope="all")
        end = time.time() + 60
        objects, uids = [], []
        while time.time() < end:
            objects, uids = _received_uids(ctx)
            if uids:
                break
            time.sleep(2)
        expected = _db_uids(ctx, patient_id)
        unknown = set(uids) - expected
        r.assert_true(
            3, "DICOM Send — Overlay 설정 상태에서 영상 전송",
            bool(uids) and not unknown,
            expected=f"수신 객체의 모든 SOP Instance UID가 {patient_id}의 DB와 일치",
            actual={"send": sent, "received": len(objects),
                    "modalities": sorted({o.get("Modality") for o in objects}),
                    "sop_classes": sorted({o.get("SOPClassUID") for o in objects}),
                    "uids_matched": len(set(uids) & expected),
                    "uids_not_in_db": sorted(unknown)},
            note="Queue 상태가 아니라 실제 수신 객체의 UID를 DB와 대조한다.")

        # --- Step 3-b: Export -----------------------------------------
        if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
            flows.close_examine(ui, option="suspend", wait=10)
        flows.ensure_patient_screen(ui, wait=3)
        _open_examined(ui)
        picked = vp.click_viewer_text(ui, "MWL", settle=1.5)
        export_button = [c for c in ui.by_id(2191) if c.visible]
        if not picked or not export_button:
            r.add(3, "Export — Overlay 설정 상태에서 파일 내보내기", FAIL,
                  expected="Examined에서 검사 선택 후 Export(2191)",
                  actual={"card_selected": picked,
                          "export_button": bool(export_button)})
        else:
            ui.click(export_button[0], settle=3)
            manager = em.attach()
            outcome = em.export(manager, wait=120)
            r.assert_true(
                3, "Export — Overlay 설정 상태에서 파일 내보내기",
                bool(outcome["files"]),
                expected="제품 기본 Export 경로에 파일 생성",
                actual=outcome,
                note="경로는 제품 기본값을 그대로 쓴다(폴더 선택 창 없음). "
                     "버튼 클릭이 아니라 경로에 생긴 파일로 판정한다.")

        # --- Step 3-c: Print -------------------------------------------
        r.manual(3, "Print — Overlay 항목이 포함된 출력물 확인",
                 "실제 Film 출력과 출력물의 Overlay 표시 검증은 "
                 "TC_Basic_WorkFlow_03(run-wf03)이 Print 서버 웹 프리뷰 OCR로 "
                 "이미 수행한다. WF04에서 중복 출력하지 않고 그 결과를 참조한다.",
                 expected="Film에 Patient ID/Birth Date/Thickness/Compression/HVL/AGD 표시",
                 actual="WF03에서 자동 검증됨")
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_04 실행", FAIL, actual=str(exc))
    return r


def run(ctx):
    return [workflow_04(ctx)]
