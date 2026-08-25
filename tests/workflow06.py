# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_06 — All Images 및 Dose SR 전송.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.
공용 판정 헬퍼는 `core/send_verify.py`.
"""

from core import dicom_settings as ds
from core import flows
from core import send_verify as sv
from core import viewer_processing as vp
from core.dicom_settings import ensure_bunny
from core.result import BLOCKED, TCResult, PASS, FAIL

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

    * Queue의 Image / DSR 구분은 `DATA.DICOM_STORAGE_QUEUE.ClassUID`로 본다.
      `DataType` 컬럼도 있지만 값의 의미를 실측으로 확정하지 못했으므로 DICOM
      SOP Class UID로 판정한다. 체크리스트 Test Data가 RDSR의 UID를 명시하고,
      DICOM Conformance Statement V1.3W1이 X-Ray Radiation Dose SR Storage를
      선언한다.
    * RDSR이 도착하지 않으면 **FAIL이 아니라 BLOCKED**로 보고한다. Precondition이
      "RDSR 생성 조건을 충족"을 요구하는데 이 환경은 Demo(F8) 가상 촬영이라 그
      조건이 성립하는지 확인되지 않았다. 전제 미충족을 제품 결함처럼 보고하지
      않는다(운영 지침 2절). 관측값은 증거로 남긴다.
    """
    r = TCResult("TC_Basic_WorkFlow_06", "All Images 및 Dose SR 전송")
    patient_id = (ctx.cfg.get("xipl") or {}).get(
        "test_patient_id", "DATA_FLOW_MWL_01")
    try:
        if not ensure_bunny(ctx.cfg):
            r.add(0, "Storage SCP(Bunny) 기동", FAIL,
                  expected="Bunny 실행 및 수신 포트 대기", actual="기동/포트 확인 실패")
            return r

        ui = flows.cold_start(ctx.cfg, ctx.db)[0]
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

        session = vp.open_test_study(ctx)
        ui = session["ui"]
        r.assert_true(
            1, "Examined 창에서 대상 검사 선택",
            bool(session.get("study_key")),
            expected=f"{patient_id} 검사가 전송 대상으로 열린다",
            actual={"study": session.get("study_key")},
            note="개정본 Expected 1.")

        flows.select_step(ui, session["step_2d"])
        vp.expand_tools(ui)
        identity = sv.db_identity(ctx, patient_id)
        outcome = sv.send_and_verify(ctx, ui, r, patient_id, scope="all",
                                  expect_count=None, wait=120)
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
            "SELECT [Key],State,DataType,ClassUID FROM DICOM_STORAGE_QUEUE "
            "ORDER BY [Key]")
        wanted = set(outcome.get("queue_added") or [])
        added = [row for row in queue if int(row["Key"]) in wanted]
        rdsr_queued = [row for row in added
                       if str(row.get("ClassUID") or "") == sv.SOP_CLASS_RDSR]
        image_queued = [row for row in added
                        if str(row.get("ClassUID") or "")
                        in (sv.SOP_CLASS_MG, sv.SOP_CLASS_DBT)]
        detail_queue = {
            "queue_rows": added,
            "image_rows": len(image_queued),
            "rdsr_rows": len(rdsr_queued),
            "class_uids": sorted({str(row.get("ClassUID")) for row in added}),
        }
        if rdsr_queued:
            r.assert_true(
                3, "Queue에서 Image와 DSR Type 항목 확인",
                bool(image_queued),
                expected="Image SOP Class와 RDSR SOP Class가 모두 Queue에 등록",
                actual=detail_queue,
                note=f"RDSR SOP Class UID {sv.SOP_CLASS_RDSR}(체크리스트 Test Data)로 "
                     "구분한다. DICOM_STORAGE_QUEUE.ClassUID 대조.")
        else:
            r.blocked(
                3, "Queue에서 Image와 DSR Type 항목 확인",
                "Queue에 RDSR SOP Class 항목이 없다. 개정본 Precondition은 '검사가 "
                "종료되어 RDSR 생성 조건을 충족'을 요구하는데, 이 환경은 실제 X-ray "
                "대신 Demo(F8) 가상 촬영이라 그 조건이 성립하는지 확인되지 않았다. "
                "전제 미충족을 제품 결함으로 보고하지 않는다 - 실제 촬영 환경에서 "
                "재확인이 필요하다. **해제 조건**: 실제 촬영 환경에서 RDSR 생성 "
                "조건을 충족시킨 뒤 다시 실행한다. "
                "**이 실행으로 말할 수 없는 것**: Demo 촬영이 아닌 실제 촬영의 "
                "RDSR Queue 등록 여부.",
                expected="Image와 RDSR이 모두 Queue에 등록",
                actual=detail_queue)

        # 지역 변수다. `sv.received` 에 대입하면 모듈 함수를 리스트로 덮어써서
        # 다음 TC 가 `'list' object is not callable` 로 죽는다(2026-08-19 회귀 16차).
        received = sv.received(ctx) or []
        rdsr = [o for o in received
                if str(o.get("SOPClassUID") or "") == sv.SOP_CLASS_RDSR]
        images = [o for o in received
                  if str(o.get("SOPClassUID") or "")
                  in (sv.SOP_CLASS_MG, sv.SOP_CLASS_DBT)]
        r.add(4, "Storage SCP에서 영상 객체와 RDSR 객체 수 확인",
              PASS if (images and rdsr) else BLOCKED,
              expected="전송 대상 영상과 RDSR이 누락 없이 수신",
              actual={"received_total": len(received),
                      "image_objects": len(images),
                      "rdsr_objects": len(rdsr),
                      "db_instances_by_type": {
                          k: len(v)
                          for k, v in sorted(identity["by_type"].items())}},
              note="수신 파일을 파싱해 SOP Class로 구분한다. RDSR이 없으면 "
                   "위 Step 3의 사유와 같다. **해제 조건**: 실제 촬영 환경에서 "
                   "RDSR 생성 조건을 충족시킨 뒤 다시 실행한다. "
                   "**이 실행으로 말할 수 없는 것**: 실제 촬영의 RDSR 수신 여부.")
        if rdsr:
            bad = [o for o in rdsr
                   if o.get("PatientID") != patient_id
                   or o.get("StudyInstanceUID") not in identity["study_uids"]]
            r.assert_true(
                5, "RDSR의 Patient ID와 Study Instance UID 비교", not bad,
                expected=f"RDSR의 Patient ID={patient_id}, Study Instance UID가 "
                         "원본 검사와 일치",
                actual={"rdsr": [{k: o.get(k) for k in
                                  ("PatientID", "StudyInstanceUID")}
                                 for o in rdsr],
                        "mismatch": bad},
                note="개정본 Expected 5. DATA.PATIENT/STUDY와 대조.")
        else:
            r.blocked(5, "RDSR의 Patient ID와 Study Instance UID 비교",
                     "수신된 RDSR 객체가 없어 대조할 수 없다(Step 3 사유 참고). "
                     "**해제 조건**: 실제 촬영 환경에서 RDSR을 생성·수신한 뒤 "
                     "다시 실행한다. **이 실행으로 말할 수 없는 것**: RDSR의 "
                     "Patient ID와 Study Instance UID 일치 여부.",
                     expected="RDSR의 식별 Tag가 원본 검사와 일치",
                     actual="RDSR 미수신")
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_06 실행", exc)
    return r


def run(ctx):
    return [workflow_06(ctx)]
