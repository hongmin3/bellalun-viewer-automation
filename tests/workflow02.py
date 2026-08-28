# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_02 - 공통 2D/3D 검사 촬영 및 Tool 적용.

체크리스트 원문 (변경 금지) — `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`
시트 `개정 TC` row 12:

  Precondition
    TC_Basic_WorkFlow_01이 Pass이다.
    DATA_FLOW_MWL_01 검사가 보류 상태이다.
    2D/3D 라이선스 등록상태
  Step 1. Examined 창에서 DATA_FLOW_MWL_01 검사를 선택하고 View 또는 추가 촬영 모드로 연다.
  Step 2. 2D View Position을 촬영 등록한다.
  Step 3. 2D 영상을 1회 촬영한다.
  Step 4. 3D-N View Position을 촬영 등록한다.
  Step 5. 3D 영상을 1회 촬영한다.
  Step 6. 2D 영상에 Window Level, Zoom, Pan, Annotation 중 검증 대상 Tool을 각각 적용한다.
  Step 7. 3D Recon 영상에 지원되는 검증 대상 Tool을 적용한다.
  Step 8. 검사를 종료한다.
  Expected 1. 선택한 검사가 올바른 환자 정보로 열린다.
  Expected 2. 2D View Position이 촬영 목록에 등록된다.
  Expected 3. 2D 영상이 해당 검사에 생성된다.
  Expected 4. 3D-N View Position이 촬영 목록에 등록된다.
  Expected 5. 3D Raw 및 지원되는 결과 영상이 해당 검사에 생성된다.
  Expected 6. 선택한 2D 영상에 각 Tool 결과가 표시된다.
  Expected 7. 선택한 3D Recon 영상에 지원되는 Tool 결과가 표시된다.
  Expected 8. 검사 종료 후 Examined 창에서 동일 검사가 조회된다.
  Test Data: 공통 재사용 검사 DATA_FLOW_MWL_01 / 2D IMG_FLOW_2D_01 /
             3D Raw·Recon·Syn IMG_FLOW_3D_01

**근거 문서 주의 (2026-08-19)**: 이 저장소의 기준 체크리스트는 위 **개정본**이다.
`..\지식\(TC) R-23-2346_BellalunViewer_기본기능_Checklist.xlsx`는 **다른 문서**이고
TC 번호 매핑이 다르다(그 문서의 WF02는 External Device/Barcode/QR이다). 2026-08-19에
그 문서를 근거로 삼아 이 TC를 "범위 불일치"로 잘못 강등한 적이 있다.
**판정 근거는 개정본에서 확인한다** — `core/checklist.py`가 결과를 기록하는 원본도
개정본이다.
"""

import os
import time

from core import flows, screen, viewer_processing, viewer_tools
from core.result import FAIL, PASS, TCResult


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
    """Examined 화면에서 Patient ID로 월 범위 검색한다.

    구현은 2026-08-27 에 `core/flows.examined_search` 로 옮겼다 — `WF_04` 가
    개정본 Step 1("Examined 창에서 검사를 선택한다")의 UI 경로를 **직접** 밟게
    하려면 tests 모듈이 아니라 공용 흐름에 있어야 하기 때문이다. 기존 호출부
    (WF_02 / WF_06 / WF_15)가 그대로 동작하도록 이름은 남긴다.
    """
    return flows.examined_search(ui, patient_id, wait=wait)


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

        # --- 3D-W 스텝 (픽스처 확장, 2026-08-26 사용자 요청) ----------------
        #
        # 개정본 `WF_02` 의 범위는 2D + 3D-N 까지이고, 그 판정(Step 2~5)은 위에서
        # 이미 끝났다. 여기서 3D-W 를 하나 더 만드는 이유는 **Send TC 가 2D /
        # 3D-N / 3D-W 세 종류를 모두 수신 검증**할 수 있게 하기 위해서다
        # (`open_test_study` 가 3 스텝을 받도록 함께 넓혔다).
        #
        # 개정본에 없는 확장이므로 판정 제목에 그렇게 적고,
        # `config.json > test_data.include_3d_wide` 로 끌 수 있게 둔다 — 이 픽스처를
        # 쓰는 다른 TC 가 InstanceType 개수를 보고 있다면 되돌릴 수 있어야 한다.
        if (ctx.cfg.get("test_data") or {}).get("include_3d_wide", True):
            viewer_processing.add_view_position(ui, "3d-w")
            result.assert_equal(
                5, "3D-W View Position 등록 (픽스처 확장)",
                3, len(flows.step_items(ui)),
                note="Procedure + / 3D-W Preset / LCC / OK. 개정본 범위 밖의 "
                     "확장이다 — Send TC 의 3D-W 수신 검증에 필요하다.")
            _capture(ctx, ui, "05a_registered_3dw.png", result)

            shot_3dw = flows.demo_acquire_step(ui, 3, settle=0)
            counts_w = _wait_types(ctx, target["Key"], {0: 1, 1: 2, 2: 2, 3: 2})
            result.assert_true(
                5, "3D-W 영상 데이터 생성 (픽스처 확장)",
                counts_w == {0: 1, 1: 2, 2: 2, 3: 2},
                expected="3D-W 촬영으로 Raw/Recon/Syn 이 각 1건씩 더 생긴다 "
                         "(InstanceType {0:1, 1:2, 2:2, 3:2})",
                actual={"capture": shot_3dw, "instance_types": counts_w},
                note="전송 대상은 Recon 이므로(`send_verify.SENDABLE_3D_TYPES`) "
                     "이후 All Images 전송에서 DBT 객체가 2건이 된다.")
            _capture(ctx, ui, "05b_acquired_3dw.png", result)

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
        # 기대 영상 수는 **픽스처 구성에서 계산한다.** 예전에는 4 로 박아 두었는데
        # (2D 1 + 3D-N 의 Raw/Recon/Syn 3), 2026-08-26 에 3D-W 스텝을 추가하자
        # 7 건이 되어 이 판정만 깨졌다 — 촬영은 정상이었다. 픽스처를 넓힐 때
        # 같이 넓혀야 하는 자리다.
        include_wide = (ctx.cfg.get("test_data") or {}).get("include_3d_wide", True)
        expected_instances = 4 + (3 if include_wide else 0)
        result.assert_true(8, "검사 종료 후 Examined 재조회",
                           target_rank <= len(rows)
                           and int(after.get("Instances") or 0) == expected_instances,
                           expected=(f"{PATIENT_ID} 대상 Study 카드 표시 및 "
                                     f"동일 Study 영상 {expected_instances}건"
                                     f"(2D 1 + 3D-N 3"
                                     + (" + 3D-W 3" if include_wide else "") + ")"),
                           actual={"visible_rows": len(rows),
                                   "target_card_rank": target_rank,
                                   "target_study_key": target["Key"],
                                   "db": after, "close": closed})
        completed = True
    except Exception as exc:
        result.abort(0, "TC_Basic_WorkFlow_02 실행", exc)
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
    return result
