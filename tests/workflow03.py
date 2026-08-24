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

단계 분담 (2026-08-21 갱신 — Step 5·6 을 자동화해 **전 단계 자동 판정**이 됐다)
  * Step 1~3 은 실제 UI 로 수행하고 DB 로 대조한다
    (CONFIGURATION.OVERLAY_ITEM / PRINT_OVERLAY_ITEM / DICOM_PRINT.Overlay).
  * Step 4 는 Examined 에서 대상 검사를 열고 DATA.STUDY/PATIENT 로 대조한다.
  * Step 5 는 Examine 화면 영상 패널(컨트롤 203)의 위·아래를 크롭해 OCR 하고,
    Step 1 이 추가한 항목의 **라벨이 표시되는지** 판정한다
    (`core/image_overlay.py`, `WF_15` 와 공용). 값이 아니라 항목으로 판정하는
    이유는 그 모듈 docstring 에 있다 — Demo(F8) 가상 촬영에서는 선량 값이
    `-- kVp` 로 찍히므로 값 대조를 요구하면 정상 동작을 실패로 판정한다.
  * Step 6 은 Film 창을 열어 Header/Top/Bottom **영역별로** Print Overlay 표시를
    OCR 로 대조한다(`core/print_overlay.py`, `WF_08` 과 공용).
    **`WF_08` 과 중복이 아니다** — 여기는 Film **창의 표시**를 보고, `WF_08` 은
    실제 DICOM Print 를 수행해 **Print SCP 가 수신한 출력물**을 본다.
    이 TC 는 Print 를 수행하지 않는다.

Print Overlay 6개 항목은 Expected Result의 시스템정보(compression, HVL, AGD,
Thickness)와 환자정보(ID, birthdate)에 대응한다 — Patient ID, Birth Date,
Thickness, Compression Force, HVL, AGD. Image Overlay 추가 항목은 Dose kVp,
Dose mAs다(사용자 확정, 2026-08-18).

판정 근거(운영 지침 2절): 설정 저장은 DB로 대조한다. 버튼을 눌렀다는 사실만으로
판정하지 않는다.
"""

import os
import time

from PIL import ImageGrab

from core import flows, image_overlay, print_overlay, screen
from core import viewer_processing as vp
from core.result import TCResult, FAIL, MANUAL, PASS
from core.ui import children

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


def _film_from_selected_study(ui, patient_id):
    """Examined 에서 대상 검사를 골라 Film 창을 열고 Layout 1x1 로 맞춘다.

    경로(2026-08-19 실측, `WF_08` 과 같다): Examined 툴바 Print(2188) ->
    범위 선택 Selected(501) -> Film 창(158 `CWndFilmManager`) -> Layout 1x1(1141).

    Layout 을 확인하지 않으면 여러 칸에 나뉜 상태로 OCR 해 영역 크롭이 어긋난다.
    그래서 **한 칸이 Film 면적의 85% 이상**인지 확인하고 아니면 실패시킨다.
    """
    # `_examined_search` 는 Examined 가 닫혀 있으면 스스로 메인 메뉴 > View 로
    # 열고, Patient ID 검색 옵션을 골라 조회까지 한다. 그래서 `_open_examined` 를
    # 먼저 부르지 않는다 — 두 번 열면 이미 열린 상태에서 메인 메뉴를 찾다 실패한다.
    from tests.workflow02 import _examined_search

    rows = _examined_search(ui, patient_id)
    if not rows:
        raise RuntimeError(f"Examined 목록이 비어 있습니다: {patient_id}")
    ui.click(rows[0], settle=1.2)

    buttons = [c for c in ui.by_id(2188) if c.visible]
    if not buttons:
        raise RuntimeError("Examined Print 버튼(2188)을 찾지 못했습니다.")
    ui.click(buttons[0], settle=1)
    selected = [c for c in ui.by_id(501) if c.visible]
    if not selected:
        raise RuntimeError("Print 범위 Selected 버튼(501)을 찾지 못했습니다.")
    ui.click(selected[0], settle=5)

    film = [c for c in ui.by_id(158) if c.visible and c.text == "CWndFilmManager"]
    if not film:
        raise RuntimeError("Film 창이 열리지 않았습니다.")
    one_by_one = [c for c in ui.by_id(1141) if c.visible and c.rect[0] > 1400]
    if not one_by_one:
        raise RuntimeError("Film Layout 1x1 버튼(1141)을 찾지 못했습니다.")
    ui.click(one_by_one[0], settle=2)

    managers = [c for c in children(film[0].hwnd, 4)
                if c.ctrl_id == 203 and c.visible]
    unique = {c.hwnd: c for c in managers}.values()
    largest = max(unique, key=lambda c: ((c.rect[2] - c.rect[0]) *
                                         (c.rect[3] - c.rect[1])), default=None)
    if not largest:
        raise RuntimeError("Film 1x1 영상 칸을 찾지 못했습니다.")
    film_area = ((film[0].rect[2] - film[0].rect[0]) *
                 (film[0].rect[3] - film[0].rect[1]))
    pane_area = ((largest.rect[2] - largest.rect[0]) *
                 (largest.rect[3] - largest.rect[1]))
    if pane_area < film_area * .85:
        raise RuntimeError(
            f"Film Layout 이 1x1 로 바뀌지 않았습니다: pane={largest.rect}, "
            f"film={film[0].rect}")
    return film[0], {"button_id": 1141, "pane": largest.rect,
                     "film": film[0].rect,
                     "pane_ratio": round(pane_area / film_area, 4)}


def _cleanup_film(ui, tesseract_exe=None):
    """Film 창을 닫고 Patient 화면으로 돌아온다.

    **왜 판정으로 남기는가**: 2026-08-21 에 Step 6 을 붙이면서 Film 창을 열어 둔
    채 TC 를 끝냈더니 **다음 TC(`WF_04`)가 FAIL** 했다. `WF_04` 는
    `cold_start(force_restart=True)` 가 아니라 **재기동 없이 기존 Viewer 를
    재사용**하므로 `ensure_patient_screen` 이 실패하고
    (`landmarks=['status_bar','examine']`) 전제 단계에서 멈춘다.
    "조작 후 확인 없음 금지"(AGENTS.md 2절) 와 같은 종류의 실수였다.

    닫기 경로는 실측했다: Film 창 `Close`(1105) -> 확인 대화상자
    `"Are you sure you want to close?"` -> `Yes`. 두 버튼 모두 **문구를 OCR 로
    읽어** 고른다(`core/flows.close_film`) — 같은 화면에 `Print`(1149)가 나란히
    있고, 확인 대화상자의 Yes/No 는 Print 범위 선택과 같은 ID(501/500)를 쓴다.

    **이 TC 는 Print 를 수행하지 않는다.** 개정본 Step 6 은 "Film 창에 동일 영상을
    추가하고 Print Overlay 를 확인한다" 이고, 실제 출력 검증은 `WF_08` 이다.
    """
    try:
        closed = flows.close_film(ui, tesseract_exe)
    except Exception as exc:                       # noqa: BLE001
        closed = {"was_open": None, "closed": False,
                  "error": f"{type(exc).__name__}: {exc}"}
    try:
        patient = flows.ensure_patient_screen(ui, wait=10)
        landmarks = flows.known_screen(ui)
    except Exception as exc:                       # noqa: BLE001
        patient, landmarks = False, f"{type(exc).__name__}: {exc}"
    return {"close_film": closed, "patient_screen": patient,
            "landmarks": landmarks}


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

        evidence = os.path.join(ctx.evidence_root, "Flow", "03_Overlay")
        os.makedirs(evidence, exist_ok=True)
        shot = os.path.join(evidence, "05_image_overlay.png")
        win = ui.main_window()
        if win:
            screen.grab(win.rect, path=shot)
            r.attach(shot)

        # --- Step 5: 2D 영상의 Image Overlay 표시 -------------------------
        #
        # **2026-08-21 자동화.** 그전에는 "Demo(F8) 가상 촬영에서는 실제 노출값이
        # 들어오지 않을 수 있다"는 이유로 MANUAL 이었다. 그런데 개정본 Expected 5
        # 가 요구하는 것은 **"설정한 Image Overlay 항목이 표시된다"** 이지 값이
        # 맞는지가 아니다. 그래서 판정 대상을 값이 아니라 **항목(라벨) 표시**로
        # 두고, 값을 읽었는지는 교차 확인으로 따로 남긴다. 값 대조까지 요구하면
        # Demo 환경의 정상 동작(`-- kVp`)을 실패로 판정하게 된다.
        #
        # 크롭·OCR 경로는 `core/image_overlay.py`(WF_15 와 공용)를 쓴다.
        birth = ctx.db.scalar(
            "DATA", "SELECT TOP 1 PatientBirthDate FROM PATIENT "
                    "WHERE PatientID=@pid", {"pid": patient_id})
        overlay_study = {"PatientID": patient_id, "PatientBirthDate": birth}
        marks, reads, seen_panels = image_overlay.read_all(
            ui, evidence, "05_panel", tess, study=overlay_study,
            attach=r.attach)
        want_labels = list(IMAGE_OVERLAY_ADD)
        label_seen = image_overlay.labels_seen(marks, want_labels)
        r.assert_true(
            5, "2D 영상에 추가한 Image Overlay 항목 표시",
            bool(seen_panels) and all(label_seen.values()),
            expected={"영상 패널(203)": ">=1",
                      f"{IMAGE_OVERLAY_POSITION} Overlay 라벨": want_labels},
            actual={"panels": len(seen_panels), "labels_seen": label_seen,
                    "by_panel": marks, "ocr": reads},
            note="개정본 Expected 5 = '설정한 Image Overlay 항목이 표시된다'. "
                 f"Step 1 이 {IMAGE_OVERLAY_ADD} 를 **{IMAGE_OVERLAY_POSITION}** "
                 "에 추가했고, 여기서는 Examine 화면 영상 패널(컨트롤 203)의 "
                 "아래·위를 크롭해 OCR 로 그 **라벨이 실제로 찍히는지** 확인한다. "
                 "**값이 아니라 항목으로 판정하는 이유**: 이 PC 는 Demo(F8) 가상 "
                 "촬영이라 선량 값이 `-- kVp` / `-- mAs` 로 찍힌다(실측). 값 "
                 "일치를 요구하면 정상 동작을 실패로 판정한다. 읽은 문구 전체와 "
                 "크롭 원본을 증거로 남겨 사람이 눈으로 감사할 수 있게 한다. "
                 "설정 저장 사실은 Step 1 이 CONFIGURATION.OVERLAY_ITEM 으로 "
                 "대조했다.")
        # 환자 정보 Overlay 는 **DB 값과 대조**해 교차 확인으로 남긴다(판정 대상은
        # Step 1 이 추가한 항목이다). 값 대조가 되면 Overlay 자체를 제품이
        # 렌더링하고 있다는 독립 증거가 된다.
        patient_seen = image_overlay.labels_seen(
            marks, list(image_overlay.PATIENT_MARKERS))
        r.add(5, "영상 Overlay 의 환자 정보 값이 DB 와 일치(교차 확인)",
              PASS if all(patient_seen.values()) else MANUAL,
              expected={"DB 대조": list(image_overlay.PATIENT_MARKERS),
                        "PatientID": patient_id, "PatientBirthDate": birth},
              actual={"seen": patient_seen,
                      "pid_match": {k: v.get("_pid_match")
                                    for k, v in marks.items()}},
              note="이 항목은 Expected 5 의 판정 대상이 아니라 **교차 확인**이다. "
                   "Overlay 렌더링 자체가 동작하는지를 DB 값(환자 ID·생년월일)과 "
                   "대조해 본다. 읽지 못하면 MANUAL 로 남기고 크롭 원본"
                   "(`Evidence/Flow/03_Overlay/05_panelN_top.png`)을 먼저 눈으로 "
                   "확인한다 — 판정을 약화시키지 않기 위해 접두사를 줄이지 않는다.")

        if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
            flows.close_examine(ui, option="suspend", wait=10)

        # --- Step 6: Film 창의 Print Overlay 표시 -------------------------
        #
        # **2026-08-21 자동화.** 그전에는 "WF_08 이 확인한다"며 MANUAL 로 두었다.
        # 그런데 개정본 WF_03 Step 6 은 **Film 창에 영상을 추가해 표시를 확인**
        # 하는 것이고, WF_08 이 검증하는 것은 그 뒤의 **실제 DICOM Print 출력물**
        # 이다. 대상이 다르므로 이 TC 가 직접 확인해야 한다(중복이 아니다).
        # 판독·판정은 `core/print_overlay.py`(WF_08 과 공용)를 쓴다.
        try:
            film, layout = _film_from_selected_study(ui, patient_id)
            film_path = os.path.join(evidence, "06_film_overlay.png")
            film_image = ImageGrab.grab(bbox=film.rect, all_screens=True)
            film_image.save(film_path)
            r.attach(film_path)
            expect = print_overlay.film_expectations(overlay_study)
            film_texts = print_overlay.ocr_film_areas(
                film_image, os.path.splitext(film_path)[0], tess,
                attach=r.attach)
            film_labels = print_overlay.judge_film_areas(film_texts, expect)
            r.assert_true(
                6, "Film 창에 설정한 Print Overlay 표시",
                print_overlay.film_all_ok(film_labels),
                expected={area: sorted(checks)
                          for area, checks in expect.items()},
                actual={"areas": film_labels, "layout": layout,
                        "ocr": film_texts,
                        "regions": print_overlay.film_regions(*film_image.size)},
                note="개정본 Expected 6 = 'Film 창에 설정한 Print Overlay 가 "
                     "표시된다'. Examined 에서 Print(2188) -> Selected(501) 로 "
                     "Film 창을 열고 Layout 1x1(1141)로 맞춘 뒤, Step 2 가 "
                     "Header/Top/Bottom 세 영역에 저장한 6개 항목이 **영역별로** "
                     "찍히는지 OCR 로 대조한다. 한 곳만 읽으면 6개가 전부 Top 에 "
                     "몰려 있어도 통과하므로 영역을 나눠 읽는다. 환자 정보 기대값은 "
                     "상수가 아니라 DATA.PATIENT 값에서 만든다. "
                     "**WF_08 과 중복이 아니다** — 여기는 Film **창의 표시**를, "
                     "WF_08 은 Print SCP 가 수신한 **출력물**을 본다.")
        except Exception as exc:                                # noqa: BLE001
            r.add(6, "Film 창에 설정한 Print Overlay 표시", FAIL,
                  expected="Film 창이 열리고 Header/Top/Bottom Overlay 표시",
                  actual={"error": f"{type(exc).__name__}: {exc}"},
                  note="Film 창을 열지 못했거나 Layout 을 1x1 로 맞추지 못했다. "
                       "Examined Print(2188) / Print 범위 Selected(501) / Layout "
                       "1x1(1141) 경로를 확인한다. 이 TC 는 Print 를 수행하지 "
                       "않는다 — 실제 출력물 검증은 WF_08 이다.")
        finally:
            cleanup = _cleanup_film(ui, tess)
            close_ok = (cleanup["close_film"].get("was_open") is False
                        or cleanup["close_film"].get("closed") is True)
            r.assert_true(
                6, "뒷정리: Film 창 종료 후 Patient 화면 복귀",
                close_ok and bool(cleanup["patient_screen"]),
                expected={"film_open": False, "patient_screen": True},
                actual=cleanup,
                note="이 TC 다음에 오는 `WF_04` 는 **Viewer 를 재기동하지 않고** "
                     "기존 세션을 재사용한다. Film 창을 열어 둔 채 끝내면 그 TC 가 "
                     "Patient 화면에 닿지 못해 전제 단계에서 FAIL 한다"
                     "(2026-08-21 실측). 그래서 정리 결과를 판정으로 남긴다. "
                     "Close(1105)와 확인 대화상자의 Yes 는 모두 **문구를 OCR 로 "
                     "읽어** 고른다 — 같은 화면의 Print(1149)와, Print 범위 선택과 "
                     "같은 ID(501/500)를 쓰는 Yes/No 를 ID 로 고르면 정반대를 누를 "
                     "수 있다(core/flows.close_film).")
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_03 실행", exc)
    return r


def run(ctx):
    return [workflow_03(ctx)]
