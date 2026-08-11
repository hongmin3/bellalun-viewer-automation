# -*- coding: utf-8 -*-
"""TC_Basic_WorkFlow_01: MWL 조회부터 Local 검사 생성까지 완전자동화."""
import os
import time
from datetime import date

from core import flows, screen
from core.dicom_settings import _exact_saved, _saved_rows, tcp_open
from core.mwl import MwlServer, make_mg_order
from core.result import TCResult, PASS, FAIL


MWL_PID = "DATA_FLOW_MWL_01"
LOCAL_PID = "DATA_FLOW_LOCAL_01"


def _wait_row(db, sql, params, timeout=40):
    end = time.time() + timeout
    row = None
    while time.time() < end:
        row = db.one("DATA", sql, params)
        if row:
            return row
        time.sleep(1)
    return row


def _compact(value):
    return "".join(ch for ch in str(value or "") if ch.isalnum()).upper()


def _name(value):
    return " ".join(str(value or "").replace("^", " ").split()).upper()


def _capture(ctx, ui, name, result):
    win = ui.main_window()
    if not win:
        return None
    path = os.path.join(ctx.evidence_root, "Flow", "01_Worklist", name)
    screen.grab(win.rect, path=path)
    result.attach(path)
    return path


def _prepare_mwl(ctx):
    cfg = ctx.cfg["dicom"]
    server = MwlServer(cfg["mwl_server_url"])
    spec = next(x for x in cfg["servers_to_register"] if x["kind"] == "MWL")
    server.delete_where(patient_id=MWL_PID)
    fields = make_mg_order(
        patient_id=MWL_PID, patient_name="AUTO^MWL^^^",
        accession_number="ACC_AUTO_001", sps_id="SPS_AUTO_001",
        station_ae="BELLALUN", sps_start_date=date.today().isoformat(),
        sps_start_time="09:00", procedure_id="RP_AUTO_001",
        procedure_description="Mammography", patient_sex="F",
        patient_birthdate="1980-01-01", station_name="MAMMO")
    item = server.create(**fields)
    if not server.scp_running()[0]:
        server.scp_start(spec["ae_title"], spec["port"])
    return item


def _latest_patient(ctx, patient_id):
    return ctx.db.one(
        "DATA", "SELECT TOP 1 PatientID,PatientName,PatientBirthDate,PatientSex "
        "FROM PATIENT WHERE PatientID=@pid ORDER BY [Key] DESC", {"pid": patient_id})


def run(ctx):
    r = TCResult("TC_Basic_WorkFlow_01", "MWL 조회 및 Local 검사 생성")
    mwl_spec = next(x for x in ctx.cfg["dicom"]["servers_to_register"]
                    if x["kind"] == "MWL")
    try:
        saved_rows = _saved_rows(ctx.db, "MWL", mwl_spec)
        configured = (_exact_saved(saved_rows, mwl_spec) and
                      any(int(x.get("Use") or 0) == 1 for x in saved_rows))
        connected = tcp_open(mwl_spec["ip"], mwl_spec["port"])
        if not configured or not connected:
            raise RuntimeError(
                "MWL 서버가 미등록/비활성/불일치 상태입니다. "
                "먼저 'python run.py setup-dicom'을 실행하십시오. "
                f"DB={saved_rows}, TCP={connected}")
        r.add(0, "MWL 서버 사전 연결 확인", PASS,
              expected=(f"{mwl_spec['name']} Use=1 / "
                        f"{mwl_spec['ip']}:{mwl_spec['port']}"),
              actual={"db": saved_rows, "tcp": connected})
    except Exception as exc:
        r.add(0, "MWL 서버 사전 연결 확인", FAIL,
              expected="Setting > DICOM > MWL 등록·활성 및 TCP 연결",
              actual=str(exc),
              note="미연결 상태에서 MWL 검색을 진행해 'No search items'로 오판하지 않음")
        return r
    try:
        order = _prepare_mwl(ctx)
        r.add(0, "MWL 시험 처방 준비", PASS, expected=MWL_PID,
              actual={"patient_id": order.get("patient_id"),
                      "study_instance_uid": order.get("study_instance_uid")})
    except Exception as exc:
        r.add(0, "MWL 시험 처방 준비", FAIL, expected="시험 MWL 등록 및 SCP 실행",
              actual=str(exc))
        return r

    try:
        ui, startup = flows.cold_start(ctx.cfg, ctx.db)
        if not flows.ensure_patient_screen(ui):
            raise flows.FlowError("Patient 화면에 진입하지 못했습니다.")
        r.add(0, "Viewer 기동 및 Patient 화면", PASS, actual=" / ".join(startup))
    except Exception as exc:
        r.add(0, "Viewer 기동 및 Patient 화면", FAIL, actual=str(exc))
        return r

    try:
        flows.open_patient_list_tab(ui)
        flows.select_patient_source(ui, "mwl")
        count = flows.search_patient(ui, MWL_PID, "patient_id")
        d = ui.dialog()
        if d:
            popup_path = os.path.join(ctx.evidence_root, "Flow", "01_Worklist",
                                      "01_mwl_search_error.png")
            try:
                ui.capture_dialog(d, popup_path)
                r.attach(popup_path)
            except Exception:
                pass
            message = ui.dialog_text(d) or "커스텀 MWL 연결/검색 오류 팝업"
            buttons = ui.dialog_buttons(d)
            ok = next((x for x in buttons if x.ctrl_id == 500), None)
            if ok:
                ui.click(ok, settle=.5)
            raise flows.FlowError(
                f"MWL 검색 오류 팝업을 닫고 중단했습니다: {message}. "
                "Setting > DICOM > MWL Echo 및 Viewer 설정 재적용을 확인하십시오.")
        r.assert_equal(1, "MWL 조회 결과 1건 표시", 1, count)
        if count != 1:
            return r
        flows.select_study_row(ui, 1)
        _capture(ctx, ui, "01_mwl_selected.png", r)
        r.add(2, "MWL 처방 선택", PASS, expected=MWL_PID,
              actual="첫 번째(유일) 검색 결과 선택; 화면 증적 저장")

        before_key = ctx.db.scalar("DATA", "SELECT ISNULL(MAX([Key]),0) FROM STUDY") or 0
        ui.click(flows._need(ui, flows.PATIENT["examine_from_list"], "Examine"), settle=1)
        dup = flows.handle_select_patient_information(ui, "use_existing", timeout=5)
        time.sleep(7)
        if not ui.by_id(flows.EXAMINE["edit_information"]):
            raise flows.FlowError("MWL 검사 Examine 화면에 진입하지 못했습니다.")
        r.add(3, "선택 MWL 처방으로 Examine 진입", PASS,
              expected="Edit Information/Close 컨트롤 표시", actual={"duplicate": dup})

        info = flows.read_edit_information(ui)
        r.assert_equal(4, "MWL Patient ID", MWL_PID, info["patient_id"])
        r.assert_true(4, "MWL Patient Name",
                      _name(info["patient_name"]) == _name(order.get("patient_name")),
                      expected=order.get("patient_name"), actual=info["patient_name"])
        r.assert_equal(4, "MWL Accession Number", order.get("accession_number"),
                       info["accession"])
        r.assert_equal(4, "MWL Birth Date", _compact(order.get("patient_birthdate")),
                       _compact(info["birth_date"]))
        r.assert_equal(4, "MWL Sex", order.get("patient_sex"), info["sex"])
        r.assert_equal(4, "MWL Study Description",
                       order.get("requested_procedure_description"),
                       info["study_description"])
        r.assert_equal(4, "Procedure 없는 MWL의 Step 수", 0,
                       len(flows.step_items(ui)))
        _capture(ctx, ui, "04_mwl_examine.png", r)

        flows.close_examine(ui, option="suspend", wait=6,
                            evidence_path=os.path.join(
                                ctx.evidence_root, "Flow", "01_Worklist",
                                "05_mwl_suspend.png"))
        uid = order.get("study_instance_uid")
        mwl_study = _wait_row(
            ctx.db,
            "SELECT TOP 1 s.[Key],s.StudyStatus,s.StudyInstanceUID," 
            "(SELECT COUNT(*) FROM INSTANCE i WHERE i.StudyKey=s.[Key]) AS Inst "
            "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
            "WHERE s.[Key]>@before AND p.PatientID=@pid "
            "ORDER BY s.[Key] DESC",
            {"before": before_key, "pid": MWL_PID})
        r.assert_true(5, "MWL 검사 보류 상태로 저장",
                      bool(mwl_study) and int(mwl_study.get("StudyStatus") or -1) == 4,
                      expected="StudyStatus=4", actual=mwl_study)
        r.assert_equal(5, "MWL Study Instance UID 유지", uid,
                       (mwl_study or {}).get("StudyInstanceUID"))
    except Exception as exc:
        r.add(1, "MWL UI 흐름", FAIL, actual=str(exc))
        return r

    try:
        if not flows.ensure_patient_screen(ui):
            raise flows.FlowError("MWL 보류 후 Patient 화면으로 돌아오지 못했습니다.")
        existing = _latest_patient(ctx, LOCAL_PID)
        local_name = (existing or {}).get("PatientName") or "AUTO^LOCAL^^^"
        local_birth = (existing or {}).get("PatientBirthDate") or "19800101"
        local_sex = (existing or {}).get("PatientSex") or "F"
        got = flows.fill_new_patient(
            ui, patient_id=LOCAL_PID, patient_name=local_name,
            accession="ACC_LOCAL_001", birth_date=str(local_birth), sex=local_sex,
            study_description="AUTO Local Study")
        r.add(6, "New Patient 화면 표시", PASS, expected="입력 폼", actual="표시됨")
        r.assert_equal(7, "Local Patient ID 입력", LOCAL_PID, got["patient_id"])
        r.assert_true(7, "Local Patient Name 입력",
                      _name(local_name) == _name(got["patient_name"]),
                      expected=local_name, actual=got["patient_name"])
        r.assert_equal(7, "Local Birth Date 입력", _compact(local_birth),
                       _compact(got["birth_date"]))

        before_key = ctx.db.scalar("DATA", "SELECT ISNULL(MAX([Key]),0) FROM STUDY") or 0
        ui.click(flows._need(ui, flows.PATIENT["np_examine"], "Examine"), settle=1)
        dup = flows.handle_select_patient_information(ui, "use_existing", timeout=5)
        time.sleep(7)
        if not ui.by_id(flows.EXAMINE["edit_information"]):
            raise flows.FlowError("Local 검사 Examine 화면에 진입하지 못했습니다.")
        r.add(8, "Local 검사 Examine 진입", PASS, actual={"duplicate": dup})
        local_info = flows.read_edit_information(ui)
        local_study = _wait_row(
            ctx.db,
            "SELECT TOP 1 s.[Key],s.StudyStatus,s.AccessionNumber," 
            "p.PatientID,p.PatientName,p.PatientBirthDate,p.PatientSex "
            "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
            "WHERE s.[Key]>@before AND p.PatientID=@pid ORDER BY s.[Key] DESC",
            {"before": before_key, "pid": LOCAL_PID})
        r.assert_true(9, "Local 검사 DB 생성", bool(local_study),
                      expected=f"Key>{before_key}", actual=local_study)
        r.assert_equal(9, "Local Patient ID 일치", LOCAL_PID,
                       local_info["patient_id"])
        r.assert_true(9, "Local Patient Name 일치",
                      _name(local_name) == _name(local_info["patient_name"]),
                      expected=local_name, actual=local_info["patient_name"])
        r.assert_equal(9, "Local Birth Date 일치", _compact(local_birth),
                       _compact(local_info["birth_date"]))
        r.assert_equal(9, "Local Sex 일치", str(local_sex)[:1].upper(),
                       local_info["sex"])
        _capture(ctx, ui, "09_local_examine.png", r)
        # 촬영 없는 시험 데이터를 폐기하지 않고 보류해 재검증 가능한 상태로 둔다.
        flows.close_examine(ui, option="suspend", wait=6)
    except Exception as exc:
        r.add(6, "Local UI 흐름", FAIL, actual=str(exc))
    return r
