# -*- coding: utf-8 -*-
"""TC_Basic_WorkFlow_02: 공통 2D/3D 촬영 및 Tool 적용 자동화."""

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


def _instance_counts(ctx, study_key):
    rows = ctx.db.query(
        "DATA", "SELECT InstanceType,COUNT(*) AS Cnt FROM INSTANCE "
        "WHERE StudyKey=@study GROUP BY InstanceType ORDER BY InstanceType",
        {"study": study_key})
    return {int(row["InstanceType"]): int(row["Cnt"]) for row in rows}


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
        if not flows.ensure_patient_screen(ui):
            raise flows.FlowError("Patient 화면에 진입하지 못했습니다.")
        card_number = _study_card_number(ctx, target)
        visible = _open_suspended(ui, PATIENT_ID, card_number)
        info = flows.read_edit_information(ui)
        result.assert_equal(1, "선택 검사 Patient ID", PATIENT_ID, info["patient_id"])
        expected_datetime = _digits(target["StudyDate"]) + _digits(target["StudyTime"])
        result.assert_true(
            1, "선택 검사 Study Date/Time",
            _digits(info.get("study_datetime")).endswith(expected_datetime),
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
            ui, 1, settle=int(ctx.cfg.get("demo", {}).get("settle_seconds", 14)))
        counts = _wait_types(ctx, target["Key"], {0: 1})
        result.assert_true(3, "2D 영상 생성", counts.get(0, 0) >= 1,
                           expected="InstanceType 0 >= 1",
                           actual={"capture": shot_2d, "instance_types": counts})
        _capture(ctx, ui, "03_acquired_2d.png", result)

        viewer_processing.add_view_position(ui, "3d")
        result.assert_equal(4, "3D-N View Position 등록", 2, len(flows.step_items(ui)),
                            note="Procedure + / 3D-N Preset / LCC / OK")
        _capture(ctx, ui, "04_registered_3dn.png", result)

        shot_3d = flows.demo_acquire_step(
            ui, 2, settle=int(ctx.cfg.get("demo", {}).get("settle_seconds", 14)))
        counts = _wait_types(ctx, target["Key"], {0: 1, 1: 1, 2: 1, 3: 1})
        expected_types = {0, 1, 2, 3}
        result.assert_true(5, "3D Raw/Recon/Syn 영상 생성",
                           expected_types.issubset(set(counts)),
                           expected="InstanceType 0/1/2/3",
                           actual={"capture": shot_3d, "instance_types": counts})
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
        _capture(ctx, ui, "08_examined_result.png", result)
        result.assert_true(8, "검사 종료 후 상태 전환",
                           after.get("StudyStatus") != before_status,
                           expected=f"StudyStatus != {before_status}", actual=after)
        result.assert_true(8, "검사 종료 후 Examined 재조회",
                           bool(rows) and int(after.get("Instances") or 0) >= 4,
                           expected=f"{PATIENT_ID} 카드 표시 및 영상 >= 4",
                           actual={"visible_rows": len(rows), "db": after, "close": closed})
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
    return result
