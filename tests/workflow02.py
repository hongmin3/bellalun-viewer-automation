# -*- coding: utf-8 -*-
"""공통 2D/3D 촬영 및 Tool 적용 자동화.

**확인된 범위 불일치 (2026-08-18) — 제품 결함이 아니라 자동화 라벨 문제다.**

체크리스트(`(TC) R-23-2346_..._Checklist.xlsx` row 12)의 `TC_Basic_WorkFlow_02`
원문은 **External Device / Barcode / QR Code 설정**이다:

  1. Setting - Patient - External Device : Denso Wave AT20Q설정, Port설정한다.
  2. 뷰어를 재시작한다.
  3. Setting - Patient - External Device - External Input을 설정한다.
  4. Setting - Patient - Barcode를 설정한다.
  5. Setting - Patient - QR Code를 설정한다.
  6. 바코드/QR을 인식한다.
  Expected 2. 뷰어를 재시작시 External Device에 설정한 내용이 적용된다.
  Expected 6. 바코드/QR을 인식시 설정한 내용에 따라 동작한다.

이 모듈이 실제로 하는 일은 **MWL 보류 검사 재개 + 2D/3D-N Demo 촬영 + Tool 검증**
으로, 위 원문과 다르다. 촬영 자체는 `TC_Basic_WorkFlow_01`의 "MWL을 조회 및
**촬영**한다"에 해당하고, 이 흐름은 WF03/WF04/WF05/XIPL이 공유하는 **픽스처
생성기** 역할을 한다 — 즉 코드는 쓸모가 있으나 TC ID가 잘못 붙어 있다.

조치 방향(사용자 결정 필요, `NEXT_TASK.md` 참고): 이 흐름을 픽스처 단계로
재명명하고, 실제 WF02를 새로 구현한다. Step 1~5는 `CONFIGURATION.DEVICE_COMMON`
(`BarcodeReaderType`/`BarcodeReaderPort`/`ExternalInputUseTab`/
`BarcodeMappingField`/`QRCodeSearchField`)로 자동 판정 가능하고, Expected 2의
재기동 후 유지도 자동 검증 가능하다. Step 6은 실물 Denso Wave AT20Q 스캐너가
필요해 MANUAL이다(Service Manual 4.3.6/4.3.7/4.3.8, 6.1 근거).

그때까지 이 모듈은 **판정에 범위 불일치를 MANUAL로 명시**해 리포트가 거짓 주장을
하지 않게 한다.
"""

import os
import time

from core import flows, screen, viewer_processing, viewer_tools
from core.result import FAIL, PASS, TCResult
from core.ui import children


PATIENT_ID = "DATA_FLOW_MWL_01"
DB_TIMEOUT = 75


def _study(ctx):
    return ctx.db.one(
        "DATA",
        "SELECT TOP 1 s.[Key],s.StudyDate,s.StudyTime,s.StudyStatus,"
        "s.StudyInstanceUID,p.PatientID,p.PatientName,"
        "(SELECT COUNT(*) FROM INSTANCE i WHERE i.StudyKey=s.[Key]) AS Instances "
        "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid AND s.StudyStatus=4 "
        "AND NOT EXISTS (SELECT 1 FROM INSTANCE i WHERE i.StudyKey=s.[Key]) "
        "ORDER BY s.[Key] DESC", {"pid": PATIENT_ID})


def _study_card_number(ctx, target):
    rows = ctx.db.query(
        "DATA", "SELECT s.[Key] FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid "
        "ORDER BY s.StudyDate DESC,s.StudyTime DESC,s.[Key] DESC",
        {"pid": PATIENT_ID})
    keys = [int(row["Key"]) for row in rows]
    if int(target["Key"]) not in keys:
        raise RuntimeError(f"Target study disappeared: {target['Key']}")
    return keys.index(int(target["Key"])) + 1


def _digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _displayed_study_datetime(value):
    """Normalize Viewer 12-hour English display to DB YYYYMMDDHHMMSS."""
    import re
    text = " ".join(str(value or "").split())
    match = re.fullmatch(
        r"(\d{4})/(\d{2})/(\d{2})\s+(AM|PM)\s+(\d{2}):(\d{2}):(\d{2})",
        text, re.I)
    if not match:
        return _digits(text)
    year, month, day, meridiem, hour, minute, second = match.groups()
    hour = int(hour) % 12 + (12 if meridiem.upper() == "PM" else 0)
    return f"{year}{month}{day}{hour:02d}{minute}{second}"


def _instance_counts(ctx, study_key):
    rows = ctx.db.query(
        "DATA", "SELECT InstanceType,COUNT(*) AS Cnt FROM INSTANCE "
        "WHERE StudyKey=@study GROUP BY InstanceType ORDER BY InstanceType",
        {"study": study_key})
    return {int(row["InstanceType"]): int(row["Cnt"]) for row in rows}


def _image_structure(ctx, study_key):
    instances = ctx.db.query(
        "DATA", "SELECT [Key],SeriesKey,GroupKey,InstanceType,InstanceNumber,"
        "ImageInstanceUID FROM INSTANCE WHERE StudyKey=@study ORDER BY [Key]",
        {"study": study_key})
    series = ctx.db.query(
        "DATA", "SELECT [Key],SeriesInstanceUID FROM SERIES "
        "WHERE StudyKey=@study ORDER BY [Key]", {"study": study_key})
    groups = ctx.db.query(
        "DATA", "SELECT [Key],SeriesKey,Type,ExposureMode FROM INSTANCE_GROUP "
        "WHERE StudyKey=@study ORDER BY [Key]", {"study": study_key})
    return {"instances": instances, "series": series, "groups": groups}


def _valid_image_structure(structure, expected_types, expected_series, expected_groups):
    instances = structure["instances"]
    types = [int(row["InstanceType"]) for row in instances]
    image_uids = [str(row.get("ImageInstanceUID") or "") for row in instances]
    series_uids = [str(row.get("SeriesInstanceUID") or "")
                   for row in structure["series"]]
    return (sorted(types) == sorted(expected_types)
            and len(structure["series"]) == expected_series
            and len(structure["groups"]) == expected_groups
            and all(image_uids) and len(set(image_uids)) == len(image_uids)
            and all(series_uids) and len(set(series_uids)) == len(series_uids))


def _wait_types(ctx, study_key, required, timeout=DB_TIMEOUT):
    end = time.time() + timeout
    counts = _instance_counts(ctx, study_key)
    while time.time() < end and any(counts.get(t, 0) < n for t, n in required.items()):
        time.sleep(2)
        counts = _instance_counts(ctx, study_key)
    return counts


def _capture(ctx, ui, name, result):
    path = os.path.join(ctx.evidence_root, "Flow", "02_WorkFlow", name)
    screen.grab(ui.main_window().rect, path=path)
    result.attach(path)
    return path


def _examined_search(ui, patient_id, wait=3):
    """Examined 화면에서 Patient ID로 월 범위 검색한다."""
    if not [c for c in ui.by_id(2177) if c.visible]:
        if not flows.open_main_menu(ui):
            raise flows.FlowError("메인 메뉴가 열리지 않았습니다.")
        view = [c for c in ui.by_id(flows.MAIN_MENU["item_view"])
                if c.visible and c.rect[2] - c.rect[0] > 20]
        if not view:
            raise flows.FlowError("VIEW 메뉴 항목(53)을 찾지 못했습니다.")
        ui.click(view[0], settle=4)

    month = [c for c in ui.by_id(1108) if c.visible]
    if month:
        ui.click(month[0], settle=1)
    field = [c for c in ui.by_id(2177) if c.visible]
    edit = [c for c in ui.by_id(2178) if c.visible]
    search = [c for c in ui.by_id(2179) if c.visible]
    if not field or not edit or not search:
        raise flows.FlowError("Examined 검색 컨트롤(2177/2178/2179)을 찾지 못했습니다.")
    ui.click(field[0], settle=.5)
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    options, seen = [], set()
    for c in children(popups[0].hwnd, 3) if popups else []:
        if c.text == "TextButton" and c.visible and c.hwnd not in seen:
            seen.add(c.hwnd)
            options.append(c)
    patient_id_option = [c for c in options if c.ctrl_id == 2]
    if not patient_id_option:
        raise flows.FlowError("Patient ID 검색 옵션을 찾지 못했습니다.")
    ui.click(patient_id_option[0], settle=.5)
    ui.set_text(edit[0], patient_id)
    ui.click(search[0], settle=wait)

    study_list = [c for c in ui.by_id(2199) if c.visible]
    rows, seen = [], set()
    for c in children(study_list[0].hwnd, 4) if study_list else []:
        if c.text == "StudyListItem" and c.visible and c.hwnd not in seen:
            seen.add(c.hwnd)
            rows.append(c)
    return sorted(rows, key=lambda c: (c.rect[1], c.rect[0]))


def _open_suspended(ui, patient_id, card_number):
    rows = _examined_search(ui, patient_id)
    if not rows:
        raise flows.FlowError(f"Examined 검색 결과가 없습니다: {patient_id}")
    # Examined Card는 StudyDate/Time 내림차순, 같은 행에서는 좌→우 순서다.
    if len(rows) < card_number:
        raise flows.FlowError(
            f"대상 카드 순번 {card_number}, 화면 카드 {len(rows)}건")
    ui.click(rows[card_number - 1], settle=1)
    button = [c for c in ui.by_id(2182) if c.visible]
    if not button:
        raise flows.FlowError("View/추가 촬영 버튼(2182)을 찾지 못했습니다.")
    ui.click(button[0], settle=8)
    if not ui.by_id(flows.EXAMINE["edit_information"]):
        raise flows.FlowError("선택한 보류 검사가 Examine 모드로 열리지 않았습니다.")
    return len(rows)


def _record_tools(result, step, records):
    for record in records:
        if record.get("evidence"):
            result.attach(record["evidence"])
        result.add(
            step, record["name"],
            PASS if record.get("supported") and record.get("passed") else FAIL,
            expected=(f"Control ID {record['control_id']} 지원 및 화면 변화율 >= "
                      f"{record.get('minimum_changed_ratio', 0):.5f}"),
            actual=record,
            note="Viewer 창 상대 영상 pane에서 조작하고 단계별 PNG 차이로 표시 결과 판정")


def run(ctx):
    result = TCResult("TC_Basic_WorkFlow_02", "공통 2D/3D 검사 촬영 및 Tool 적용")
    ui = None
    completed = False

    if ctx.cfg.get("viewer", {}).get("demo_mode") is not True:
        result.add(0, "Demo 가상 촬영 안전 게이트", FAIL,
                   expected="viewer.demo_mode=true", actual="false 또는 미설정",
                   note="실제 X-ray 노출은 자동 실행하지 않습니다.")
        return result
    target = _study(ctx)
    if not target:
        result.add(0, "선행 보류 검사", FAIL,
                   expected=f"{PATIENT_ID}, StudyStatus=4, INSTANCE=0",
                   actual="조건에 맞는 검사 없음",
                   note="먼저 python run.py run-wf01을 성공시켜야 합니다.")
        return result
    result.add(0, "선행 보류 검사 및 Demo 모드", PASS,
               expected=f"{PATIENT_ID}, StudyStatus=4, INSTANCE=0, Demo",
               actual=target)

    try:
        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        patient_ready = False
        # Immediately after a workflow boundary the Viewer frame can exist
        # before its status bar/menu children are attached.  Wait for the
        # actual Patient screen instead of failing on that transient frame.
        for _ in range(12):
            try:
                patient_ready = flows.ensure_patient_screen(ui, wait=2)
            except Exception:
                pass
            if patient_ready:
                break
            time.sleep(1)
        if not patient_ready:
            raise flows.FlowError("Patient 화면에 진입하지 못했습니다.")

        # Window Level 판정의 사양상 근거는 "W/L 드래그로 W1/W2 값이 증가/감소"다
        # (Service Manual "Window Level Option", Operation Manual "W/L 사용하기").
        # 그 값은 영상 Overlay로만 화면에 나오므로 Overlay(Histogram + W1/W2)가
        # 꺼져 있으면 판정 근거 자체가 사라진다. 예전에는 XIPL 흐름이 먼저 켜 둔
        # 설정에 얹혀 있었는데, 회귀가 DB를 기준 스냅샷으로 복원하기 시작하자
        # 초기화되어 이 검사만 근거를 잃었다(실측: 복원을 건너뛴 08-14 회귀는
        # 통과, 복원한 08-18은 실패). 그래서 WF02가 직접 보장한다.
        #
        # **반드시 검사를 열기 전(Patient 화면)에 호출한다.** 이 함수는 메인
        # 메뉴로 Setting에 들어갔다 나오므로, 검사 진행 중에 부르면 Examine
        # 화면이 원래대로 복구되지 않는다(실측: Tool 컨트롤과 Recon 타입
        # 버튼(2123)을 못 찾아 WF02가 중단됐다).
        viewer_processing.ensure_tc01_overlay(ui, ctx.db)
        # Setting 창을 닫은 직후에는 Patient 화면 컨트롤(2285)이 아직 붙지 않아
        # 한 번의 확인으로는 실패한다. 위 로그인 직후와 똑같이 상한을 둔 재시도로
        # 기다린다(2026-08-18 회귀 실측: 단발 확인이 "Patient 화면으로 돌아오지
        # 못했습니다"로 WF02를 죽여 이후 WF03/XIPL이 픽스처 없음으로 연쇄 실패).
        back_on_patient = False
        for _ in range(12):
            try:
                back_on_patient = flows.ensure_patient_screen(ui, wait=2)
            except Exception:
                pass
            if back_on_patient:
                break
            time.sleep(1)
        if not back_on_patient:
            raise flows.FlowError("Overlay 설정 후 Patient 화면으로 돌아오지 못했습니다.")

        card_number = _study_card_number(ctx, target)
        visible = _open_suspended(ui, PATIENT_ID, card_number)
        info = flows.read_edit_information(ui)
        result.assert_equal(1, "선택 검사 Patient ID", PATIENT_ID, info["patient_id"])
        expected_datetime = _digits(target["StudyDate"]) + _digits(target["StudyTime"])
        result.assert_true(
            1, "선택 검사 Study Date/Time",
            _displayed_study_datetime(info.get("study_datetime")) == expected_datetime,
            expected=expected_datetime, actual=info.get("study_datetime"))
        result.assert_true(1, "선택 검사 환자 정보 표시", bool(info.get("patient_name")),
                           expected="Patient Name 표시", actual=info)
        result.assert_equal(1, "보류 검사 초기 촬영 목록", 0, len(flows.step_items(ui)),
                            note=(f"Examined 동일 PID 카드 {visible}건 중 DB StudyDate/Time "
                                  f"순위 {card_number}번 선택"))
        _capture(ctx, ui, "01_opened_suspended.png", result)

        viewer_processing.add_view_position(ui, "2d")
        result.assert_equal(2, "2D View Position 등록", 1, len(flows.step_items(ui)),
                            note="Procedure + / 2D Preset / LCC / OK")
        _capture(ctx, ui, "02_registered_2d.png", result)

        shot_2d = flows.demo_acquire_step(
            ui, 1, settle=0)
        counts = _wait_types(ctx, target["Key"], {0: 1})
        structure_2d = _image_structure(ctx, target["Key"])
        result.assert_true(
            3, "2D 영상 데이터 생성",
            counts == {0: 1}
            and _valid_image_structure(structure_2d, [0], 1, 1),
            expected=("InstanceType {0:1}, Series/Group 각 1건, "
                      "Image/Series UID 발급·유일"),
            actual={"capture": shot_2d, "instance_types": counts,
                    "structure": structure_2d})
        _capture(ctx, ui, "03_acquired_2d.png", result)

        viewer_processing.add_view_position(ui, "3d")
        result.assert_equal(4, "3D-N View Position 등록", 2, len(flows.step_items(ui)),
                            note="Procedure + / 3D-N Preset / LCC / OK")
        _capture(ctx, ui, "04_registered_3dn.png", result)

        shot_3d = flows.demo_acquire_step(
            ui, 2, settle=0)
        counts = _wait_types(ctx, target["Key"], {0: 1, 1: 1, 2: 1, 3: 1})
        structure_3d = _image_structure(ctx, target["Key"])
        three_d = [row for row in structure_3d["instances"]
                   if int(row["InstanceType"]) in (1, 2, 3)]
        same_3d_series_group = (len(three_d) == 3
                                and len({row["SeriesKey"] for row in three_d}) == 1
                                and len({row["GroupKey"] for row in three_d}) == 1)
        result.assert_true(
            5, "3D Raw/Recon/Syn 영상 데이터 생성",
            counts == {0: 1, 1: 1, 2: 1, 3: 1}
            and _valid_image_structure(structure_3d, [0, 1, 2, 3], 2, 2)
            and same_3d_series_group,
            expected=("InstanceType 0/1/2/3 각 1건, Series/Group 각 2건, "
                      "3D 3종 동일 Series/Group, UID 발급·유일"),
            actual={"capture": shot_3d, "instance_types": counts,
                    "same_3d_series_group": same_3d_series_group,
                    "structure": structure_3d})
        _capture(ctx, ui, "05_acquired_3d.png", result)

        flows.select_step(ui, 1)
        evidence_dir = os.path.join(ctx.evidence_root, "Flow", "02_WorkFlow")
        tools_2d = viewer_tools.apply_tool_sequence(
            ui, evidence_dir, "06_2d", pane="left")
        _record_tools(result, 6, tools_2d)

        flows.select_step(ui, 2)
        viewer_tools.select_recon(ui)
        tools_3d = viewer_tools.apply_tool_sequence(
            ui, evidence_dir, "07_3d_recon", pane="right")
        _record_tools(result, 7, tools_3d)

        before_status = target["StudyStatus"]
        closed = flows.close_examine(
            ui, option="close", wait=8,
            evidence_path=os.path.join(evidence_dir, "08_close_dialog.png"))
        after = ctx.db.one(
            "DATA", "SELECT StudyStatus,[Lock],"
            "(SELECT COUNT(*) FROM INSTANCE i WHERE i.StudyKey=s.[Key]) AS Instances "
            "FROM STUDY s WHERE s.[Key]=@study", {"study": target["Key"]}) or {}
        rows = _examined_search(ui, PATIENT_ID)
        target_rank = _study_card_number(ctx, target)
        _capture(ctx, ui, "08_examined_result.png", result)
        result.assert_true(8, "검사 종료 후 상태 전환",
                           after.get("StudyStatus") != before_status,
                           expected=f"StudyStatus != {before_status}", actual=after)
        result.assert_true(8, "검사 종료 후 Examined 재조회",
                           target_rank <= len(rows)
                           and int(after.get("Instances") or 0) == 4,
                           expected=(f"{PATIENT_ID} 대상 Study 카드 표시 및 "
                                     "동일 Study 영상 4건"),
                           actual={"visible_rows": len(rows),
                                   "target_card_rank": target_rank,
                                   "target_study_key": target["Key"],
                                   "db": after, "close": closed})
        completed = True
    except Exception as exc:
        result.add(0, "TC_Basic_WorkFlow_02 실행", FAIL, actual=str(exc))
    finally:
        if ui is not None and not completed:
            try:
                cancel = [c for c in ui.by_id(1102) if c.visible
                          and c.rect[2] - c.rect[0] >= 80]
                if cancel:
                    ui.click(cancel[0], settle=1)
                if ui.by_id(flows.EXAMINE["close"]):
                    flows.close_examine(ui, option="suspend", wait=5)
            except Exception:
                pass
    # 리포트가 "WF02를 검증했다"고 잘못 읽히지 않게 범위를 명시한다.
    # 체크리스트 결과 xlsx는 TC ID로 행을 매칭하므로, 이 표시가 없으면 Barcode/QR
    # 행에 PASS가 찍힌다.
    result.manual(
        0, "[범위] 체크리스트 원문(External Device/Barcode/QR) 미검증",
        "이 TC의 체크리스트 원문은 External Device(Denso Wave AT20Q)·Barcode·"
        "QR Code 설정과 인식이다. 현재 자동화가 수행하는 2D/3D 촬영·Tool 검증은 "
        "그 범위가 아니다(모듈 docstring 참고). Step 1~5는 DEVICE_COMMON으로 "
        "자동 판정 가능하고 Step 6은 실물 스캐너가 필요하다.",
        expected="Step 1~5 설정 저장·재기동 유지, Step 6 바코드/QR 인식",
        actual="미구현 — 현재 자동화는 촬영 픽스처 생성과 Tool 검증을 수행")
    return result
