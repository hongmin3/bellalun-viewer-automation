# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_03 - Image Overlay 및 Print Overlay 설정.

체크리스트 원문 (변경 금지) — `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`
시트 `개정 TC` row 13:

  Precondition
    TC_Basic_WorkFlow_03이 Pass이다.
    DATA_FLOW_MWL_01에 2D/3D 영상이 존재한다.
  Step 1. Setting > Display > Overlay에서 Image Overlay 항목을 추가한다.
  Step 2. Setting > DICOM > Print에서 Print Overlay를 추가한다.
  Step 3. Print 설정에서 추가한 Print Overlay를 선택한다.
  Step 4. Examined 창에서 DATA_FLOW_MWL_01 검사를 연다.
  Step 5. 2D 영상의 Image Overlay를 확인한다.
  Step 6. Film 창에 동일 영상을 추가하고 Print Overlay를 확인한다.
  Expected 1. 선택한 Image Overlay 항목이 저장된다.
  Expected 2. Print Overlay 구성이 저장된다.
  Expected 3. Print 설정에 선택한 Overlay가 적용된다.
  Expected 4. 동일 환자와 검사 영상이 열린다.
  Expected 5. 설정한 Image Overlay 항목이 표시된다.
  Expected 6. Film 창에 설정한 Print Overlay가 표시된다.

**2026-08-19 재라벨**: 이전에는 이 모듈이 `TC_Basic_WorkFlow_04 - Overlay`였다.
그때는 다른 체크리스트(`지식\(TC) R-23-2346...xlsx`)의 번호를 따랐는데, 이 저장소의
기준 문서는 **개정본**이다(`AGENTS.md` 0절). 개정본에서 이 내용은 `WF_03`이고,
`WF_04`는 "2D 수동 DICOM Send"(tests/workflow04.py)다.

단계 분담
  * Step 1~3은 이 모듈이 실제 UI로 수행하고 DB로 대조한다
    (CONFIGURATION.OVERLAY_ITEM / PRINT_OVERLAY_ITEM / DICOM_PRINT.Overlay).
  * Step 4~5(Examined에서 열어 Image Overlay 표시 확인)는 이 모듈이 검사를 열어
    확인한다.
  * **Step 6(Film 창의 Print Overlay 표시)은 `WF_08`(tests/workflow03.py)이**
    Film Layout 1x1 구성과 실제 DICOM Print, Print SCP가 수신한 Film의 Overlay
    실제값 OCR·raster 비교로 검증한다. 중복 출력하지 않고 그 결과를 참조한다.

Print Overlay 6개 항목은 Expected Result의 시스템정보(compression, HVL, AGD,
Thickness)와 환자정보(ID, birthdate)에 대응한다 — Patient ID, Birth Date,
Thickness, Compression Force, HVL, AGD. Image Overlay 추가 항목은 Dose kVp,
Dose mAs다(사용자 확정, 2026-08-18).

판정 근거(운영 지침 2절): 설정 저장은 DB로 대조한다. 버튼을 눌렀다는 사실만으로
판정하지 않는다.
"""

import os
import time

from core import flows, print_overlay, screen
from core import viewer_processing as vp
from core.result import TCResult, FAIL

IMAGE_OVERLAY_ADD = ["Dose kVp", "Dose mAs"]

# 추가 위치. **Bottom**이다(사용자 확정, 2026-08-19). Dose 정보는 촬영 조건이라
# 환자정보가 모인 상단과 분리해 영상 하단에 두는 것이 검증자가 보기 좋다.
# `CONFIGURATION.OVERLAY_ITEM.Position`은 0=Top / 1=Bottom (실측).
IMAGE_OVERLAY_POSITION = "bottom"


def _open_examined(ui, wait=6):
    """메인 메뉴 > View 로 Examined 창을 열고 검색해 목록을 채운다.

    검색 버튼은 **2179**(돋보기)다. 2180은 새로고침이라 눌러도 목록이 채워지지
    않는다(2026-08-18 실측 — 이걸 혼동해 "목록이 비었다"고 오진한 적이 있다).
    """
    # 반환값을 버리면 메뉴가 안 열렸을 때 "View 메뉴 항목을 못 찾았다"는
    # 엉뚱한 원인으로 보고된다. 실패 지점을 정확히 남긴다.
    if not flows.open_main_menu(ui):
        raise flows.FlowError("메인 메뉴가 열리지 않았습니다(Examined 진입 전).")
    view = [c for c in ui.by_id(flows.MAIN_MENU["item_view"])
            if c.visible and c.rect[2] - c.rect[0] > 20]
    if not view:
        raise flows.FlowError("View 메뉴 항목을 찾지 못했습니다.")
    ui.click(view[0], settle=wait)
    # 창이 그려지기를 기다린다(즉시 조회 금지).
    flows.wait_controls(ui, (2179,), timeout=20)
    search = [c for c in ui.by_id(2179) if c.visible]
    if not search:
        raise flows.FlowError("Examined 검색 버튼(2179)을 찾지 못했습니다.")
    ui.click(search[0], settle=3)
    time.sleep(1.5)


def workflow_03(ctx):
    r = TCResult("TC_Basic_WorkFlow_03", "Image Overlay 및 Print Overlay 설정")
    patient_id = (ctx.cfg.get("xipl") or {}).get(
        "test_patient_id", "DATA_FLOW_MWL_01")
    try:
        session = vp.open_test_study(ctx)
        ui = session["ui"]

        # --- Step 1: Image Overlay 추가 -------------------------------
        if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
            flows.close_examine(ui, option="suspend", wait=10)
        flows.ensure_patient_screen(ui, wait=3)
        added = vp.add_image_overlay_items(
            ui, ctx.db, IMAGE_OVERLAY_ADD, position=IMAGE_OVERLAY_POSITION)
        want_ids = {vp.OVERLAY_FIELD_IDS[x] for x in IMAGE_OVERLAY_ADD}
        want_position = vp.OVERLAY_POSITION[IMAGE_OVERLAY_POSITION]
        saved = added["after"]
        # 저장됐는지만 보지 않고 **어느 위치에 들어갔는지**까지 판정한다.
        # 위치를 확인하지 않으면 Top에 들어가도 PASS가 되어 요구사항을 놓친다.
        wrong = {fid: saved[fid] for fid in want_ids
                 if fid in saved and saved[fid][0] != want_position}
        r.assert_true(
            1, f"Setting > Display > Overlay의 {IMAGE_OVERLAY_POSITION.title()}에 "
               "Image Overlay 항목 추가",
            want_ids <= set(saved) and not wrong,
            expected={"labels": IMAGE_OVERLAY_ADD,
                      "field_ids": sorted(want_ids),
                      "position": f"{IMAGE_OVERLAY_POSITION}"
                                  f"(OVERLAY_ITEM.Position={want_position})"},
            actual={**added, "wrong_position": wrong},
            note="CONFIGURATION.OVERLAY_ITEM의 FieldID와 **Position**을 함께 대조한다. "
                 "FieldID(Dose kVp=115, Dose mAs=118)와 Position(0=Top, 1=Bottom)은 "
                 "모두 추가해 보고 실측한 값이다. 개정본 Expected 1은 '선택한 Image "
                 "Overlay 항목이 저장된다'이고, 표시 위치는 사용자 확정 사항이다.")

        # --- Step 2: Print Overlay 등록 및 Print에서 선택 --------------
        tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
        po = print_overlay.ensure_print_overlay(ui, ctx.db, tess)
        print_spec = next(x for x in ctx.cfg["dicom"]["servers_to_register"]
                          if x["kind"] == "Print")
        applied = print_overlay.apply_to_print_server(
            ui, ctx.db, print_spec["name"], po["overlay"]["Key"],
            tesseract_exe=tess)
        # 개정본은 "Print Overlay를 추가한다"(Step 2)와 "Print 설정에서 선택한다"
        # (Step 3)를 별개 단계로 둔다. 한 판정으로 묶으면 어느 쪽이 실패했는지
        # 리포트에서 구분되지 않으므로 나눠서 기록한다.
        # 개수만 보면 6개가 전부 Top에 있어도 통과한다. **영역별 배치까지** 대조해
        # Header / Top / Bottom 세 영역이 실제로 저장되는지 확인한다(사용자 요청).
        area_ok = print_overlay.matches_expected_areas(po["items"])
        r.assert_true(
            2, "Setting > DICOM > Print에서 Print Overlay를 Header/Top/Bottom에 추가",
            len(po["items"]) == len(print_overlay.PRINT_ITEMS) and area_ok,
            expected={"name": print_overlay.OVERLAY_NAME,
                      "areas": {area: [label for label, _ in items]
                                for area, items
                                in print_overlay.PRINT_ITEMS_BY_AREA.items()},
                      "position_map": print_overlay.PRINT_AREA_POSITION,
                      "expected_by_position": {
                          k: sorted(v) for k, v
                          in print_overlay.PRINT_EXPECTED_BY_POSITION.items()}},
            actual={"saved": po,
                    "by_position": print_overlay.items_by_position(po["items"])},
            note="Expected 2. Print Overlay 구성이 저장된다. "
                 "CONFIGURATION.PRINT_OVERLAY_ITEM의 FieldID와 **Position**을 함께 "
                 "대조한다. 근거: 사양서1 305쪽 SRS 04-20-10 'Overlay로 표시할 항목 "
                 "설정 (Header / Top / Bottom)'. Position은 header=2 / top=0 / "
                 "bottom=1로 실측했다(화면 순서와 다르다). Expected Result의 "
                 "시스템정보(compression/HVL/AGD/Thickness)와 환자정보"
                 "(ID/birthdate)가 이 6개 항목이며, 세 영역에 나눠 두어 Top 이외의 "
                 "영역도 저장되는지 검증한다.")
        # 항목만 저장돼 있으면 안 된다. Header 표시 위치가 `None` 이면 필름에
        # 나오지 않으므로(사양서1 297쪽) 표시 설정까지 이 TC 가 확인한다.
        header_count = len(print_overlay.PRINT_ITEMS_BY_AREA["header"])
        want_position, want_layout, layout_label = print_overlay.header_targets(
            header_count)
        r.assert_true(
            2, "Print Overlay Header 표시 위치와 Layout 설정",
            print_overlay.header_matches(po["overlay"], header_count),
            expected={"HeaderPosition": f"{want_position}"
                                        f"({print_overlay.HEADER_POSITION})",
                      "HeaderLayout": f"{want_layout}({layout_label})",
                      "cells_needed": header_count},
            actual={"HeaderPosition": po["overlay"]["HeaderPosition"],
                    "HeaderLayout": po["overlay"]["HeaderLayout"],
                    "header": po.get("header")},
            note="사양서1 297쪽 - 'Header가 표시될 수 있는 위치는 다음과 같다. "
                 "None으로 설정한 경우 표시되지 않는다. None, Top, Bottom' / "
                 "'Header Layout은 1x1에서 3x3까지 선택할 수 있다. Layout 한 칸당 "
                 "한 항목씩 표시한다.' Header 항목이 "
                 f"{header_count}개이므로 {header_count}칸 이상이 필요해 "
                 f"{layout_label}을 고른다. 값 매핑(0=None/1=Top/2=Bottom)은 실측이며 "
                 "PRINT_OVERLAY.HeaderPosition/HeaderLayout으로 대조한다.")
        r.assert_equal(
            3, "Print 설정에서 추가한 Print Overlay 선택",
            po["overlay"]["Key"], applied.get("Overlay"),
            note="Expected 3. Print 설정에 선택한 Overlay가 적용된다. "
                 f"DICOM_PRINT({print_spec['name']}).Overlay를 DB로 대조.")

        # --- Step 4~5: Examined에서 검사를 열어 Image Overlay 표시 확인 ----
        session = vp.open_test_study(ctx)
        ui = session["ui"]
        flows.select_step(ui, session["step_2d"])
        study = ctx.db.one(
            "DATA",
            "SELECT TOP 1 s.[Key], s.StudyInstanceUID, p.PatientID, p.PatientName "
            "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
            "WHERE p.PatientID=@pid ORDER BY s.[Key] DESC", {"pid": patient_id})
        r.assert_true(
            4, "Examined에서 대상 검사 열기",
            bool(study) and str(study.get("PatientID")) == patient_id,
            expected=f"PatientID={patient_id} 검사가 열린다",
            actual=study,
            note="DATA.STUDY/PATIENT로 대조. 열린 검사의 환자정보가 Expected 4다.")

        shot = os.path.join(ctx.evidence_root, "Flow", "03_Overlay",
                            "05_image_overlay.png")
        os.makedirs(os.path.dirname(shot), exist_ok=True)
        win = ui.main_window()
        if win:
            screen.grab(win.rect, path=shot)
            r.attach(shot)
        r.manual(
            5, "2D 영상에 추가한 Image Overlay 항목 표시 확인",
            f"Step 1에서 추가한 {IMAGE_OVERLAY_ADD} 가 영상 "
            f"**{IMAGE_OVERLAY_POSITION}**의 Overlay에 표시되는지 "
            "캡처로 확인한다. 이 항목들은 촬영 조건 값이라 Demo(F8) 가상 촬영에서는 "
            "실제 노출값이 들어오지 않을 수 있어 자동 판정 대상으로 두지 않는다. "
            "설정이 저장된 사실은 Step 1이 CONFIGURATION.OVERLAY_ITEM으로 대조했다.",
            expected=f"영상 Overlay에 {IMAGE_OVERLAY_ADD} 표시",
            actual=f"증적 캡처: {shot}")

        # --- Step 6: Film 창의 Print Overlay 표시 -------------------------
        r.manual(
            6, "Film 창에 설정한 Print Overlay 표시 확인",
            "TC_Basic_WorkFlow_08(run-wf08)이 Film Layout 1x1 구성과 실제 DICOM "
            "Print를 수행하고, Print SCP가 수신한 Film의 Overlay 실제값을 OCR로 "
            "읽어 raster까지 대조한다. 중복 출력하지 않고 그 결과를 참조한다.",
            expected="Film에 Patient ID/Birth Date/Thickness/Compression Force/"
                     "HVL/AGD 표시",
            actual="WF_08에서 자동 검증")

        if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
            flows.close_examine(ui, option="suspend", wait=10)
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_03 실행", FAIL, actual=str(exc))
    return r


def run(ctx):
    return [workflow_03(ctx)]
