# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_06 — All Images 및 Dose SR 전송.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.
공용 판정 헬퍼는 `core/send_verify.py`.
"""

from core import dicom_settings as ds
from core import flows
from core import send_verify as sv
from core.dicom_settings import ensure_storage_reachable
from core.result import TCResult, FAIL

def workflow_06(ctx):
    r"""TC_Basic_WorkFlow_06 - All Images 및 Dose SR 전송.

    체크리스트 원문 (변경 금지) - 개정본 시트 `개정 TC` row 16:
      Precondition
        TC_Basic_WorkFlow_03이 Pass이다.
        검사가 종료되어 RDSR 생성 조건을 충족한다.
        Storage 설정에서 Dose SR 전송이 활성화되어 있다.
      Step 1. Examined 창에서 DATA_FLOW_MWL_01 검사를 선택한다.
      Step 2. Send 기능에서 All Images를 선택하여 전송한다.
      Step 3. Queue에서 Image와 DSR Type 항목을 확인한다.
      Step 4. Storage SCP에서 영상 객체와 RDSR 객체 수를 확인한다.
      Step 5. RDSR의 Patient ID와 Study Instance UID를 원본 검사와 비교한다.
      Test Data: RDSR SOP Class UID = 1.2.840.10008.5.1.4.1.1.88.67

    판정 근거

    * Queue의 Image / DSR 구분은 `DATA.DICOM_STORAGE_QUEUE.DataType`으로 본다
      (0=영상, 1=Dose SR). 2026-08-27 실측에서 제품이 Queue 행의 `ClassUID`를
      **채우지 않는 것**(전부 `None`)을 확인했다 — 그 값으로 세면 RDSR이 큐에
      분명히 있는데도 0건이 된다. **수신 객체** 쪽은 파일을 파싱하므로 SOP Class
      UID로 구분한다(체크리스트 Test Data가 RDSR의 UID를 명시하고, DICOM
      Conformance Statement V1.3W1이 X-Ray Radiation Dose SR Storage를 선언한다).
    * **RDSR 미수신은 2026-08-27 부터 FAIL 로 본다.** 그전에는 "Demo(F8) 가상
      촬영이라 Precondition('RDSR 생성 조건 충족')이 성립하지 않는다" 며 BLOCKED
      로 남겼는데, **그 전제가 틀렸다.** 오지 않은 진짜 이유는 이 TC 가 검사를
      `open_test_study` 로 **View 모드에 열고** Send 했기 때문이고, 사양서1
      173쪽 SRS 03-10-50 이 그 경로를 명시적으로 제외한다 — "Examine/View 모드에서
      Send/Multi-Send 버튼을 클릭했을 때는 Dose SR 을 전송하지 않는다".
      Examined 목록에서 전송하도록 고치자(2026-08-27) 같은 Demo 촬영 환경에서
      RDSR 이 정상 수신됐다. 즉 **Demo 촬영에서도 RDSR 은 생성된다.**
      사양이 요구하는 경로를 지키고 `SendDoseSR=1` 인데도 오지 않으면 그것은
      전제 미충족이 아니라 사양 위반이므로 그대로 FAIL 로 보고한다.
    """
    r = TCResult("TC_Basic_WorkFlow_06", "All Images 및 Dose SR 전송")
    patient_id = (ctx.cfg.get("xipl") or {}).get(
        "test_patient_id", "DATA_FLOW_MWL_01")
    try:
        reachable, storage = ensure_storage_reachable(ctx.cfg)
        if not reachable:
            r.add(0, "Storage SCP 도달 확인", FAIL,
                  expected="SCP running + DICOM 포트 연결", actual=storage,
                  note="2026-08-26 Bunny 대신 원격 Storage SCP 웹 서버를 쓴다.")
            return r

        # **깨끗한 화면에서 시작한다.** 이 TC 는 Examined 목록에서 검사를
        # 선택하는데, 앞 TC 가 Examine/View 화면을 남기면 그 목록에 닿지도
        # 못한다 — 2026-08-28 실측: 앞 실행이 남긴 Examine 화면 때문에
        # `Patient 화면 진입` 이 `landmarks=['status_bar','examine']` 로 FAIL 했다.
        # WF_04 / WF_15 는 이미 `force_restart=True` 로 같은 문제를 피하고 있었다.
        ui = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)[0]
        if not flows.ensure_patient_screen(ui):
            r.add(0, "Patient 화면 진입", FAIL,
                  expected="Setting 진입 가능한 Patient 화면",
                  actual={"landmarks": flows.known_screen(ui)})
            return r

        # `SCPUseType=0`(설정 행)만 본다 — 전송 작업 사본 행도 `Use=1` 이라 그것을
        # 집으면 엉뚱한 행의 `SendDoseSR` 을 판정한다
        # (`core/dicom_settings.STORAGE_SCP_USE_TYPE` 주석의 실측 근거 참고).
        storage = ctx.db.one(
            "CONFIGURATION",
            "SELECT TOP 1 [Key],Name,SendDoseSR,SCPUseType FROM DICOM_STORAGE "
            "WHERE [Use]=1 AND SCPUseType=@t ORDER BY [Key]",
            {"t": ds.STORAGE_SCP_USE_TYPE}) or {}
        r.assert_true(
            0, "[전제] Storage 설정의 Dose SR 전송 활성화",
            int(storage.get("SendDoseSR") or 0) == 1,
            expected="CONFIGURATION.DICOM_STORAGE.SendDoseSR = 1",
            actual=storage,
            note="개정본 Precondition. 0이면 RDSR이 Queue에 등록되지 않는다.")
        if not sv.ensure_transfer_syntax(ctx, ui, r):
            return r

        # **검사를 열지 않는다.** 개정본 Step 1 은 "Examined 창에서 검사를
        # 선택한다" 이고, 사양서1 이 그 구분에 결과를 건다 —
        #   "Send Dose SR 이 활성화되어 있을 때 ... ② **Examined 모드에서 모든
        #    영상을 전송할 때** Dose SR 을 전송한다"
        #   "Dose SR 은 검사가 종료될 때만 전송이 된다. (**Examine/View 모드에서
        #    Send/Multi-Send 버튼을 클릭했을 때는 Dose SR 을 전송하지 않는다**)"
        # 2026-08-26 까지 이 TC 는 `open_test_study` 로 검사를 **View 모드로 열어**
        # Send 했다. 그래서 Dose SR 이 오지 않았고, 그것을 제품 결함으로 오판해
        # 보고까지 했다. 사용자 지적으로 사양을 확인해 바로잡았다.
        from tests.workflow02 import _examined_search
        rows = _examined_search(ui, patient_id)
        if rows:
            ui.click(rows[0], settle=1.5)
        r.assert_true(
            1, "Examined 창에서 대상 검사 선택",
            bool(rows),
            expected=f"Examined 목록에서 {patient_id} 검사 카드 선택",
            actual={"visible_cards": len(rows)},
            note="개정본 Expected 1. **검사를 열지 않는다** — Examined 모드에서 "
                 "전송해야 Dose SR 이 함께 나간다(사양서1).")

        identity = sv.db_identity(ctx, patient_id)
        outcome = sv.send_and_verify(
            ctx, ui, r, patient_id, scope="all", expect_count=None, wait=120,
            sender=lambda s: flows.send_examined_study(ui, scope=s))
        if outcome is None:
            return r
        r.assert_true(
            2, "Send 기능에서 All Images 선택 후 전송",
            bool(outcome.get("queue_added")),
            expected="전체 영상과 RDSR이 Queue에 등록된다",
            actual=outcome,
            note="개정본 Expected 2.")

        queue = ctx.db.query(
            "DATA",
            "SELECT [Key],State,DataType,ClassUID,InstanceUID "
            "FROM DICOM_STORAGE_QUEUE ORDER BY [Key]")
        wanted = set(outcome.get("queue_added") or [])
        added = [row for row in queue if int(row["Key"]) in wanted]
        # **`ClassUID` 로 구분하지 않는다.** 제품은 Queue 행에 그 값을 채우지 않아
        # 실측이 전부 `None` 이었고, 그러면 RDSR 이 실제로 큐에 있는데도
        # `rdsr_rows=0` 이 되어 BLOCKED 로 빠진다(2026-08-27 실측:
        # `DataType=1` 행이 분명히 있는데 ClassUID 는 None).
        # 구분자는 `DataType` 이다 — 0=영상, 1=Dose SR(`sv.QUEUE_DATATYPE_DOSE_SR`).
        rdsr_queued = [row for row in added if sv.is_dose_sr_row(row)]
        image_queued = [row for row in added if not sv.is_dose_sr_row(row)]
        detail_queue = {
            "queue_rows": added,
            "image_rows": len(image_queued),
            "rdsr_rows": len(rdsr_queued),
            "class_uids": sorted({str(row.get("ClassUID")) for row in added}),
        }
        r.assert_true(
            3, "Queue에서 Image와 DSR Type 항목 확인",
            bool(image_queued) and bool(rdsr_queued),
            expected="Image 행과 Dose SR 행(DataType=1)이 모두 Queue에 등록",
            actual=detail_queue,
            note="개정본 Expected 2·3. Queue 는 `DataType` 으로 구분한다(0=영상, "
                 "1=Dose SR). 제품이 `ClassUID` 를 채우지 않아 그 값으로는 셀 수 "
                 "없다(실측 전부 None). 수신 객체 쪽은 SOP Class UID "
                 f"{sv.SOP_CLASS_RDSR}(체크리스트 Test Data)로 Step 4 에서 "
                 "확인한다. **Dose SR 이 없으면 FAIL 이다** — 사양서1 125쪽 "
                 "SRS 06-30-30 이 'Send Dose SR 옵션이 활성화되어 있을 때 ... "
                 "Examined 모드에서 모든 영상을 전송할 때' Dose SR 을 전송한다고 "
                 "정하고, 이 TC 는 그 경로를 지키며(Step 1 에서 검사를 열지 않는다) "
                 "위 전제 판정으로 SendDoseSR=1 을 확인했기 때문이다. "
                 "2026-08-27 이전에는 Demo 촬영을 이유로 BLOCKED 로 남겼는데, "
                 "경로를 사양대로 고치자 같은 Demo 환경에서 RDSR 이 수신됐다 — "
                 "전제 미충족이 아니라 자동화가 사양이 제외한 경로로 시험한 "
                 "것이었다(사양서1 173쪽 SRS 03-10-50).")

        # 지역 변수다. `sv.received` 에 대입하면 모듈 함수를 리스트로 덮어써서
        # 다음 TC 가 `'list' object is not callable` 로 죽는다(2026-08-19 회귀 16차).
        received = sv.received(ctx, patient_id) or []
        rdsr = [o for o in received
                if str(o.get("SOPClassUID") or "") == sv.SOP_CLASS_RDSR]
        images = [o for o in received
                  if str(o.get("SOPClassUID") or "")
                  in (sv.SOP_CLASS_MG, sv.SOP_CLASS_DBT)]
        r.assert_true(
            4, "Storage SCP에서 영상 객체와 RDSR 객체 수 확인",
            bool(images) and bool(rdsr),
            expected="전송 대상 영상과 RDSR이 누락 없이 수신",
            actual={"received_total": len(received),
                    "image_objects": len(images),
                    "rdsr_objects": len(rdsr),
                    "db_instances_by_type": {
                        k: len(v)
                        for k, v in sorted(identity["by_type"].items())}},
            note="개정본 Expected 4. 수신 파일을 파싱해 SOP Class로 구분한다"
                 f"(RDSR = {sv.SOP_CLASS_RDSR}, 체크리스트 Test Data). Queue "
                 "상태가 아니라 실제 수신 객체로 판정한다.")
        bad = [o for o in rdsr
               if o.get("PatientID") != patient_id
               or o.get("StudyInstanceUID") not in identity["study_uids"]]
        r.assert_true(
            5, "RDSR의 Patient ID와 Study Instance UID 비교",
            bool(rdsr) and not bad,
            expected=f"RDSR의 Patient ID={patient_id}, Study Instance UID가 "
                     "원본 검사와 일치",
            actual={"rdsr": [{k: o.get(k) for k in
                              ("PatientID", "StudyInstanceUID")}
                             for o in rdsr],
                    "mismatch": bad},
            note="개정본 Expected 5. DATA.PATIENT/STUDY와 대조. RDSR 은 영상이 "
                 "아니라 검사 단위 보고서라 `INSTANCE` 에 행이 없으므로 SOP "
                 "Instance UID 는 대조하지 않는다 — 사양서1 이 \"Dose SR 에서 "
                 "사용 시, 내부적으로 영상의 Instance UID 마지막에 '.1.1' 을 "
                 "붙인다\" 고 한다.")
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_06 실행", exc)
    return r


def run(ctx):
    return [workflow_06(ctx)]
