# -*- coding: utf-8 -*-
"""TC_Basic_WorkFlow_01 - MWL 조회부터 Local 검사 생성까지 완전자동화.

체크리스트 원문 (변경 금지):
  Step 1. RIS Server를 실행후 Patient List에서 MWL을 조회 및 촬영한다.
  Step 2. New Patient - Save후 Patient List에서 조회 및 촬영한다.
  Expected 1. MWL Study List가 조회되며 촬영가능하다.
  Expected 2. Local로 스터디가 저장되며 촬영가능하다.

판정 근거 (AGENTS.md 2항 - 매뉴얼/사양 우선):
  * Operation Manual 6.1 "Patient List 모드", 6.1.1 "Patient List 검색하기" -
    Patient List는 MWL SCU 조회 결과를 목록으로 표시하고, 목록의 검사를 선택해
    촬영에 진입한다. 그래서 이 TC는 "조회 버튼을 눌렀다"가 아니라 **보낸 처방의
    환자정보가 화면 목록과 DB에 그대로 들어왔는지**를 판정한다.
  * Operation Manual 6.2 "New Patient 모드" - 직접 입력한 환자를 Save하면 Local
    검사로 저장되고 Patient List에서 다시 조회된다. Step 2의 기대결과가 이것이라
    저장 후 **재조회와 DB 대조**까지 확인한다.
  * MWL 조회는 DICOM Conformance Statement의 Modality Worklist SCU 동작을 따른다
    (C-FIND). 그래서 검증용 RIS는 core/mwl.py의 최소 SCP로 대체한다.
"""
import os
import re
import time
from datetime import date, datetime

from core import flows, screen, uitext, watchdog
from core.dicom_settings import _exact_saved, _saved_rows, tcp_open
from core.mwl import MwlServer, make_mg_order
from core.result import TCResult, PASS, FAIL

# `_digits`는 workflow02 가 이미 만든 헬퍼를 재사용한다(순환 import 없음,
# workflow02 는 workflow01 을 import 하지 않는다).
from tests.workflow02 import _digits


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


def _dicom_age_years(birth_iso, ref_iso):
    """생년월일 대비 기준일의 만 나이(년). DICOM AS(Age String) 계산 관례.

    MWL 서버는 Age 태그를 직접 보내지 않는다(`core/mwl.make_mg_order` 참고) —
    뷰어가 Patient Birth Date와 조회 시점(Scheduled Date)으로 계산해 표시한다.
    그래서 기대값도 화면에서 역산하지 않고 **독립적으로 계산**한다
    (AGENTS.md "관찰한 동작으로 정상 기준을 역산하지 않는다").
    """
    from datetime import date
    b = date.fromisoformat(birth_iso)
    ref = date.fromisoformat(ref_iso)
    return ref.year - b.year - ((ref.month, ref.day) < (b.month, b.day))


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
        expected_order = {
            "patient_id": MWL_PID, "patient_name": "AUTO^MWL^^^",
            "accession_number": "ACC_AUTO_001", "patient_sex": "F",
            "patient_birthdate": "1980-01-01",
            "requested_procedure_description": "Mammography"}
        actual_order = {key: order.get(key) for key in expected_order}
        r.assert_true(
            0, "MWL 시험 처방 원본 데이터 준비",
            all(_compact(actual_order[key]) == _compact(value)
                for key, value in expected_order.items())
            and bool(order.get("study_instance_uid")),
            expected={**expected_order, "study_instance_uid": "발급됨"},
            actual={**actual_order,
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
        r.abort(0, "Viewer 기동 및 Patient 화면", exc)
        return r

    try:
        # TC_WindowsUpdate_02(Windows Update 체크리스트) Expected 2 가 요구하는
        # Scheduled Date/Time 대조 전제. 기본값은 꺼져 있어 켜 둔다(멱등 —
        # 이미 켜져 있으면 아무것도 안 바꾼다). 2026-09-08 사용자 지시.
        column = flows.ensure_scheduled_datetime_column(ui)
        r.add(0, "Patient List에 Scheduled Study DateTime 열 표시",
              PASS if column["now_on"] else FAIL,
              expected="List Show Item에 Scheduled Study DateTime 켜짐",
              actual=column,
              note="Setting > Patient > Patient List > List Show Item. "
                   "사용자 지시로 2026-09-08 추가. owner-draw 픽셀 판독이라 "
                   "간헐적으로 오탐할 수 있어 stop=False.",
              stop=False)
        if not flows.ensure_patient_screen(ui):
            raise flows.FlowError("Setting 종료 후 Patient 화면으로 돌아오지 못했습니다.")
    except Exception as exc:
        r.abort(0, "Scheduled Study DateTime 열 표시 설정", exc)
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

        # Scheduled Date/Time 대조 — Patient List 카드에서 읽는다(Edit
        # Information 의 study_datetime 은 Scheduled 가 아니라 실제 Study
        # 일시임을 실측 확인했다 — 2026-09-08 이전 세션 기록 참고). 카드 열이
        # 화면 폭보다 넓어져(Scheduled Study DateTime 열을 켠 뒤) 오른쪽으로
        # 스크롤해야 보인다.
        # 카드 열 전체 폭이 화면보다 훨씬 넓어(실측 약 2600px) 스크롤 버튼
        # 클릭 수 : 실제 이동 폭이 일정하지 않다. 고정 클릭 수 대신 **조금씩
        # 스크롤하며 매번 OCR로 기대 날짜가 보이는지 직접 확인**하고, 보이면
        # 즉시 멈춘다(상한만 둔다) — 스크롤 폭을 추측하지 않는다.
        win = ui.main_window()
        expected_sched_date = _digits(order.get("sps_start_date"))
        card_text, dates, actual_sched_date = "", [], ""
        for _ in range(8):
            rows_now = flows._study_items(ui)
            if not rows_now:
                break
            rl, rt, rr, rb = rows_now[0].rect
            clipped = (max(rl, win.rect[0]), rt, min(rr, win.rect[2]), rb)
            card_text = screen.ocr(clipped, scale=3, path=None)
            dates = re.findall(r"(\d{4}/\d{2}/\d{2})", card_text)
            if dates and _digits(dates[-1]) == expected_sched_date:
                actual_sched_date = _digits(dates[-1])
                break
            flows.scroll_study_list_right(ui, clicks=8)
            time.sleep(.4)
        else:
            actual_sched_date = _digits(dates[-1]) if dates else ""
        sched_ok = bool(actual_sched_date) and actual_sched_date == expected_sched_date
        # stop=False — 이 대조는 owner-draw 카드의 가로 스크롤+OCR 에 의존해
        # 아직 안정성이 낮다(2026-09-08 라이브 실행에서 간헐 실패 관찰). 이
        # 한 항목 때문에 TC 전체가 중단되지 않게 한다 — 나머지 Step 은
        # 이 항목과 독립적으로 그 자체로 의미가 있다.
        r.add(1, "MWL Scheduled Date", PASS if sched_ok else FAIL,
              expected=expected_sched_date,
              actual={"card_ocr": card_text, "parsed_date": actual_sched_date},
              note="Patient List 카드의 Scheduled Study DateTime 열(우측, 가로 "
                   "스크롤 필요)을 OCR로 읽는다. 시:분까지는 OCR 안정성이 "
                   "낮아 날짜만 비교한다. 간헐적으로 카드 재렌더링 타이밍 "
                   "때문에 OCR이 비거나 스크롤이 반영 안 될 수 있다(조사 중).",
              stop=False)

        flows.select_study_row(ui, 1)
        _capture(ctx, ui, "01_mwl_selected.png", r)
        r.assert_true(2, "유일한 MWL 처방 선택",
                      count == 1 and os.path.isfile(os.path.join(
                          ctx.evidence_root, "Flow", "01_Worklist",
                          "01_mwl_selected.png")),
                      expected=f"{MWL_PID} 단일 결과와 선택 증거",
                      actual={"result_count": count, "patient_id": MWL_PID})

        before_key = ctx.db.scalar("DATA", "SELECT ISNULL(MAX([Key]),0) FROM STUDY") or 0
        ui.click(flows._need(ui, flows.PATIENT["examine_from_list"], "Examine"), settle=1)
        dup = flows.handle_select_patient_information(ui, "use_existing", timeout=5)
        wait_started_wall, wait_started = datetime.now(), time.perf_counter()
        entered = watchdog.wait_until(
            lambda: bool(ui.by_id(flows.EXAMINE["edit_information"])),
            timeout=7, poll=.25, desc="MWL Examine 화면")
        r.record_timing("MWL Examine 화면 진입", wait_started_wall, wait_started,
                        "control appeared" if entered else "timeout",
                        "Edit Information control ID 2003")
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
        # TC_WindowsUpdate_02(Windows Update 체크리스트) Expected 2 가 명시하는
        # 대조 항목 중 개정본 WF_01 이 아직 안 보던 두 가지 — Age 와 Scheduled
        # Date/Time. 2026-09-07 추가(기본기능 TC 자체를 고도화, 사용자 승인).
        expected_age = _dicom_age_years(
            order.get("patient_birthdate"), order.get("sps_start_date"))
        actual_age_digits = _digits(info.get("age"))
        r.assert_true(
            4, "MWL Age",
            bool(actual_age_digits) and int(actual_age_digits) == expected_age,
            expected=f"{expected_age}(생년월일·Scheduled Date 기준 계산)",
            actual=info.get("age"),
            note="MWL 서버는 Age 태그를 보내지 않는다 — Patient Birth Date 와 "
                 "Scheduled Date 로 독립 계산한 값과 대조한다.")
        # Scheduled Date/Time 대조는 Step 1 에서 이미 Patient List 카드로
        # 했다(Edit Information 의 `np_study_datetime`은 Scheduled 이 아니라
        # 실제 Study 일시임을 실측 확인해 여기서는 쓰지 않는다 — 2026-09-07
        # 조사, 2026-09-08 Patient List List Show Item 으로 해결).
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
        r.abort(1, "MWL UI 흐름", exc)
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
        wait_started_wall, wait_started = datetime.now(), time.perf_counter()
        entered = watchdog.wait_until(
            lambda: bool(ui.by_id(flows.EXAMINE["edit_information"])),
            timeout=7, poll=.25, desc="Local Examine 화면")
        r.record_timing("Local Examine 화면 진입", wait_started_wall, wait_started,
                        "control appeared" if entered else "timeout",
                        "Edit Information control ID 2003")
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
        close = flows.close_examine(ui, option="suspend", wait=6)
        local_final = ctx.db.one(
            "DATA", "SELECT s.[Key],s.StudyStatus,s.AccessionNumber,s.[Lock],"
            "(SELECT COUNT(*) FROM INSTANCE i WHERE i.StudyKey=s.[Key]) AS Inst "
            "FROM STUDY s WHERE s.[Key]=@study",
            {"study": local_study["Key"]}) if local_study else None
        r.assert_true(
            9, "Local 검사 보류 후 실제 DB 상태",
            bool(local_final)
            and int(local_final.get("StudyStatus") or -1) == 4
            and str(local_final.get("AccessionNumber")) == "ACC_LOCAL_001"
            and int(local_final.get("Lock") or 0) == 0
            and int(local_final.get("Inst") or 0) == 0,
            expected=("StudyStatus=4, Accession=ACC_LOCAL_001, "
                      "Lock=0, INSTANCE=0"),
            actual={"db": local_final, "close": close})
    except Exception as exc:
        r.abort(6, "Local UI 흐름", exc)
    return r
