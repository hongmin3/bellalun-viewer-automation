# -*- coding: utf-8 -*-
"""UI를 직접 구동하는 TC (live 모드).

DICOM 서버 연동 없이 Viewer UI + Demo 가상 촬영만으로 수행 가능한 항목이다.
각 TC는 조작과 판정을 스스로 수행하므로 pre/post 스냅샷이 필요 없다.

TC_Basic_WorkFlow_01  Local 검사 생성            [Local 부분만. MWL은 연동 필요]
TC_Basic_WorkFlow_03  Demo 가상 촬영 및 검사 종료  [F8. 실물 팬텀 불필요]
"""

import time

from core import flows, preflight, statusbar, watchdog
from core.result import TCResult, PASS, FAIL, MANUAL
from core.ui import ViewerUi  # noqa: F401  (진단용)

# 촬영 결과가 DB에 반영될 때까지의 최대 대기 (초)
DB_SETTLE_TIMEOUT = 40


def _ensure_viewer(ctx, r, step=0):
    """Viewer가 꺼져 있는 상태를 전제로 기동 → 로그인 → DICOM 연결 확인."""
    import os

    ev = os.path.join(ctx.evidence_root, "ui")
    try:
        ui, log = flows.cold_start(ctx.cfg, ctx.db)
        r.add(step, "Viewer 기동 및 로그인 (cold start)", PASS,
              expected="기동 → 팝업 정리 → 로그인 → DB attach",
              actual=" / ".join(log))
    except Exception as exc:
        r.add(step, "Viewer 기동 및 로그인 (cold start)", FAIL, actual=str(exc))
        return None, None

    guard = watchdog.DialogGuard(ui, evidence_dir=ev)

    if not flows.ensure_patient_screen(ui):
        r.add(step, "Patient 화면 진입", FAIL,
              expected="Patient List/New Patient 탭", actual="화면 전환 실패")
        return None, None
    r.add(step, "Patient 화면 진입", PASS,
          expected="Patient List/New Patient 탭", actual="진입 완료")

    # DICOM 서버 연결 상태 — 상태바 아이콘 (Operation Manual 3.13 / 11.2.1)
    try:
        btn = ui.by_id(flows.WELCOME["examine"])
        if btn:
            ui.click(btn[0], settle=2.0)
            time.sleep(6)
            guard.sweep(tag="_patient")
        st = statusbar.read(ui, evidence_dir=ev, tag="_run")
        summary = statusbar.dicom_summary(st)
        for name in statusbar.DICOM_ICONS:
            v = st.get(name, {})
            r.add(step, f"[전제] DICOM {name.upper()} 서버 연결",
                  PASS if v.get("connected") else MANUAL,
                  expected="연결됨", actual=v.get("detail"),
                  note="미연결 시 Setting > DICOM 에서 서버 등록 후 Echo 필요. "
                       "판정 근거 캡처: " + str(v.get("evidence")))
        r.add(step, "[전제] 상태바 종합", PASS, expected="참고",
              actual=statusbar.describe(st))
        ctx.dicom_connected = all(summary.values())
    except Exception as exc:
        r.add(step, "[전제] DICOM 서버 연결 확인", MANUAL, actual=str(exc))
        ctx.dicom_connected = None

    return ui, guard


def _preflight(ctx, r):
    ok, items = preflight.check_all(ctx.cfg, ctx.db, require_viewer=False)
    for i in items:
        r.add(0, f"[전제] {i['name']}",
              PASS if i["ok"] else (FAIL if i["blocking"] else MANUAL),
              expected="충족", actual=i["detail"])
    return ok


def _wait_count(db, sql, target, timeout=DB_SETTLE_TIMEOUT, poll=2.0):
    """DB 건수가 target에 도달할 때까지 대기. 최종 건수를 반환."""
    end = time.time() + timeout
    n = db.scalar("DATA", sql)
    while time.time() < end and (n or 0) < target:
        time.sleep(poll)
        n = db.scalar("DATA", sql)
    return n or 0


# ---------------------------------------------------------------------
def workflow_01_local(ctx):
    """New Patient로 Local 검사를 생성하고 DB로 판정한다."""
    r = TCResult("TC_Basic_WorkFlow_01", "Local 검사 생성 (UI 자동 수행)")

    if not _preflight(ctx, r):
        r.add(0, "전제 조건 미충족", FAIL,
              note="XIPL.SERVER / 관리자 권한 / DB 중 하나가 준비되지 않아 수행하지 않음")
        return r, None

    ui, guard = _ensure_viewer(ctx, r, step=0)
    if not ui:
        return r, None

    # Step 6~7. New Patient 입력
    pid = flows.unique_patient_id()
    name = "AUTO^LOCAL^^^"
    birth = "1980/01/01"
    desc = "AUTO Local Study"
    got = None
    with watchdog.guarded("New Patient 입력", r, 6, guard) as g:
        got = flows.fill_new_patient(ui, patient_id=pid, patient_name=name,
                                     birth_date=birth, sex="F",
                                     study_description=desc)
    if not g.ok or not got:
        return r, None

    r.assert_true(6, "New Patient 입력 화면 데이터 표시",
                  bool(got.get("patient_id")) and bool(got.get("procedure")),
                  expected="환자 입력값과 기본 Procedure 표시", actual=got)
    r.assert_equal(7, "입력한 Patient ID가 폼에 반영", pid, got["patient_id"])
    r.assert_equal(7, "입력한 Patient Name이 폼에 반영", name, got["patient_name"])
    r.assert_equal(7, "입력한 Birth Date가 폼에 반영", birth, got["birth_date"])
    r.assert_true(7, "Birth Date 입력 시 Age 자동 계산",
                  bool((got["age"] or "").strip()),
                  expected="Age 값 표시", actual=got["age"])
    default_procedure = ctx.db.one(
        "PROCEDURE", "SELECT TOP 1 [Key],Name FROM PROCEDURE_INFO "
        "WHERE [Default]=1 ORDER BY [Key]") or {}
    r.assert_equal(7, "Procedure 기본값 DB 일치",
                   default_procedure.get("Name"), got["procedure"],
                   note="UI 표시값을 PROCEDURE_INFO.Default=1 행과 직접 비교")

    # Step 8. Examine 진입
    before = ctx.db.scalar("DATA", "SELECT COUNT(*) FROM STUDY") or 0
    try:
        dup = flows.start_examine_from_new_patient(ui, wait=10, on_duplicate="fail")
    except flows.FlowError as exc:
        r.add(8, "Examine 진입", FAIL, actual=str(exc),
              note="동일 Patient ID 경고. 고유 ID 생성 로직 확인 필요")
        return r, None
    if dup:
        r.add(8, "동일 Patient ID 경고 미발생", MANUAL, actual=str(dup))

    after = _wait_count(ctx.db, "SELECT COUNT(*) FROM STUDY", before + 1)
    r.assert_true(8, "Local 검사로 Examine 모드 전환 및 검사 생성", after == before + 1,
                  expected=f"STUDY {before + 1}건", actual=f"{after}건")

    # Step 9. 입력 정보와 저장 정보 대조
    row = ctx.db.one(
        "DATA",
        "SELECT TOP 1 s.[Key],s.StudyDate,s.StudyStatus,s.AccessionNumber,"
        "s.StudyDescription,p.PatientID,p.PatientName,p.PatientBirthDate,p.PatientSex "
        "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid ORDER BY s.[Key] DESC", {"pid": pid})
    if not row:
        r.add(9, "생성된 검사의 환자 정보 일치", FAIL,
              expected=f"PatientID={pid}", actual="해당 검사 없음")
        return r, None

    r.assert_equal(9, "저장된 Patient ID", pid, row["PatientID"])
    normalize_name = lambda value: " ".join(
        str(value or "").replace("^", " ").split()).upper()
    r.assert_true(9, "저장된 Patient Name",
                  normalize_name(row["PatientName"]) == normalize_name(name),
                  expected=name, actual=row["PatientName"],
                  note="DICOM PN은 구성요소 구분자(^)가 정규화되어 저장됨")
    r.assert_equal(9, "저장된 Birth Date", birth.replace("/", ""),
                   row["PatientBirthDate"])
    r.assert_equal(9, "저장된 Sex", "F", row["PatientSex"])
    r.manual(9, "검사 생성 직후 상태 코드 (참고)",
             "StudyStatus 코드 의미는 문서상 확정되지 않아 PASS 근거로 사용하지 않음",
             expected="Examine 진행 상태 코드 사양",
             actual=f"StudyStatus={row['StudyStatus']}, StudyDate={row['StudyDate']}")

    return r, {"ui": ui, "guard": guard, "study_key": row["Key"], "patient_id": pid}


# ---------------------------------------------------------------------
def workflow_03_demo_acquire(ctx, session):
    """Demo 가상 촬영(F8)으로 영상을 획득하고 검사를 종료한다."""
    r = TCResult("TC_Basic_WorkFlow_03", "Demo 가상 촬영 및 검사 종료 (UI 자동 수행)")

    if not session:
        r.skip(0, "선행 TC", "TC_Basic_WorkFlow_01이 검사를 생성하지 못해 수행 불가")
        return r

    ui, guard, study_key = session["ui"], session["guard"], session["study_key"]
    want = int(ctx.cfg.get("demo", {}).get("acquire_count", 2))

    # Step 1. Examine 모드 및 촬영 목록
    steps = flows.step_items(ui)
    r.assert_true(1, "Procedure의 View Position이 촬영 목록에 등록", bool(steps),
                  expected=">= 1개 Step", actual=f"{len(steps)}개")
    if not steps:
        return r

    want = min(want, len(steps))
    q_inst = f"SELECT COUNT(*) FROM INSTANCE WHERE StudyKey={study_key}"
    q_grp = f"SELECT COUNT(*) FROM INSTANCE_GROUP WHERE StudyKey={study_key}"

    # Step 2~3. 가상 촬영
    acq = []
    with watchdog.guarded("Demo 가상 촬영", r, 3, guard) as g:
        acq = flows.demo_acquire(ui, count=want,
                                 settle=int(ctx.cfg.get("demo", {})
                                            .get("settle_seconds", 14)))
    if not g.ok:
        return r

    shot = [a for a in acq if not a.get("skipped")]
    r.assert_true(2, "촬영 준비(Ready) 상태 확인",
                  len(shot) == want and all(a.get("ready") for a in shot),
                  expected=f"선택한 {want}개 Step 모두 Ready",
                  actual=acq,
                  note="상태 배너 색으로 판독. Ready가 아닌 Step은 촬영하지 않음")

    n_inst = _wait_count(ctx.db, q_inst, want)
    n_grp = ctx.db.scalar("DATA", q_grp) or 0

    r.assert_equal(3, "F8 가상 촬영으로 영상 생성", want, n_inst,
                   note=f"Service Manual 5.2.3 근거. 실제 촬영 Step {len(shot)}회")
    r.assert_equal(3, "촬영 횟수만큼 영상 그룹 생성", want, n_grp)

    # SOP Instance UID 발급 및 중복 없음 (P0)
    inst = ctx.db.query("DATA",
                        "SELECT [Key],SeriesKey,GroupKey,InstanceType,InstanceNumber,ImageInstanceUID,"
                        "ContentDate,ContentTime FROM INSTANCE "
                        f"WHERE StudyKey={study_key} ORDER BY [Key]")
    uids = [i["ImageInstanceUID"] for i in inst]
    r.assert_true(3, "각 영상에 SOP Instance UID 발급", all(uids),
                  expected="전건 발급", actual=f"{sum(1 for u in uids if u)}/{len(uids)}")
    r.assert_true(3, "SOP Instance UID 중복 없음", len(set(uids)) == len(uids),
                  expected="중복 0건", actual=f"고유 {len(set(uids))} / 전체 {len(uids)}")
    r.assert_true(3, "2D 획득 데이터 구조",
                  len(inst) == want
                  and all(int(item["InstanceType"]) == 0 for item in inst)
                  and len({item["GroupKey"] for item in inst}) == want
                  and len({item["SeriesKey"] for item in inst}) == want,
                  expected=f"2D Instance {want}건, Series/Group 각각 {want}건",
                  actual=inst)

    series = ctx.db.query("DATA", f"SELECT [Key],SeriesInstanceUID FROM SERIES "
                                  f"WHERE StudyKey={study_key}")
    r.assert_true(3, "Series Instance UID 발급", bool(series) and
                  all(s["SeriesInstanceUID"] for s in series),
                  expected="발급됨", actual=[s["SeriesInstanceUID"] for s in series])

    # Dose 정보
    dose = ctx.db.query("DATA",
                        "SELECT GroupKey,DoseKVP,DoseMA,DoseMS,DoseMAS FROM DOSE_INFO "
                        f"WHERE GroupKey IN (SELECT [Key] FROM INSTANCE_GROUP "
                        f"WHERE StudyKey={study_key})")
    r.assert_true(3, "촬영 Dose 정보 기록", len(dose) >= n_grp,
                  expected=f">= {n_grp}건", actual=f"{len(dose)}건")

    r.manual(3, "획득 영상의 View Position / 화질",
             "Service Manual 5.2.3: Demo의 가상 획득 영상은 선택한 Step 정보와 "
             "연관이 없음. 영상 내용 기반 판정은 정식 라이선스 환경에서 수행")

    # Step 8. 검사 종료
    import os

    option = ctx.cfg.get("demo", {}).get("close_option", "close")
    status_before = ctx.db.one("DATA", f"SELECT StudyStatus FROM STUDY "
                                       f"WHERE [Key]={study_key}") or {}
    q_susp = f"SELECT COUNT(*) FROM SUSPEND_STEP WHERE StudyKey={study_key}"
    try:
        susp_before = ctx.db.scalar("DATA", q_susp)
    except Exception:
        susp_before = None

    closed_info = None
    with watchdog.guarded("검사 종료", r, 8, guard) as g:
        closed_info = flows.close_examine(
            ui, option=option, wait=8,
            evidence_path=os.path.join(ctx.evidence_root, "ui",
                                       "dialog_close_option.png"))
    if not g.ok:
        return r

    r.assert_true(
        8, "검사 종료 옵션 처리 결과",
        bool(closed_info), expected=f"'{option}' 처리 결과 반환",
        actual=closed_info,
        note="Operation Manual 8.32/9.19: 미촬영 View Position이 남으면 "
             "Suspend(보류)/Close(종료)/Cancel 중 선택")
    if closed_info and closed_info.get("evidence"):
        r.attach(closed_info["evidence"])

    after = ctx.db.one("DATA", f"SELECT StudyStatus,[Lock] FROM STUDY "
                               f"WHERE [Key]={study_key}") or {}
    r.assert_true(8, "검사 종료로 검사 상태 전환",
                  after.get("StudyStatus") != status_before.get("StudyStatus"),
                  expected=f"StudyStatus 변화 (종료 전 {status_before.get('StudyStatus')})",
                  actual=f"StudyStatus={after.get('StudyStatus')}, Lock={after.get('Lock')}",
                  note="상태 코드 의미는 문서상 미확정이므로 값 변화로 판정")

    n_after = ctx.db.scalar("DATA", q_inst) or 0
    r.assert_equal(8, "검사 종료 후 영상 손실 없음", n_inst, n_after)

    # 미촬영 Step 처리 방식 — 사양에 명시되어 있지 않아 실측값으로 기록한다
    try:
        susp_after = ctx.db.scalar("DATA", q_susp)
    except Exception as exc:
        susp_after = f"조회 실패: {exc}"
    remaining = len(steps) - n_after
    r.add(8, f"'{option}' 선택 시 미촬영 View Position 처리", MANUAL,
          expected="매뉴얼에 명시되지 않음 (사양 확인 필요)",
          actual=f"미촬영 Step {remaining}개 / SUSPEND_STEP 행 "
                 f"{susp_before} → {susp_after}",
          note="Suspend는 '촬영 예정이던 View Position도 함께 보류'가 명시되어 "
               "있으나, Close가 남은 Step을 삭제하는지는 문서상 확인되지 않음. "
               "위 실측값을 근거로 사양 확인 요청 권장")

    return r


# ---------------------------------------------------------------------
def run_local_workflow(ctx):
    """WorkFlow_01 → 03 을 이어서 수행한다."""
    r1, session = workflow_01_local(ctx)
    r2 = workflow_03_demo_acquire(ctx, session)
    return [r1, r2]


# 러너 등록 ID는 pre/post 판정용 TC와 구분한다.
# 판정 결과의 tc_id는 체크리스트의 TC ID를 그대로 쓴다.
REGISTRY = [
    {"id": "UI_Local_Workflow", "title": "Local 검사 생성 + Demo 촬영 (UI 자동 수행)",
     "mode": "live", "run_many": run_local_workflow,
     "covers": ["TC_Basic_WorkFlow_01", "TC_Basic_WorkFlow_03"],
     "note": "Viewer를 실제로 구동합니다. 수행 중 마우스/키보드를 사용하지 마십시오."},
]
