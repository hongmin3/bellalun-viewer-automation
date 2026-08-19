# -*- coding: utf-8 -*-
"""TC_Basic_WorkFlow_05 — DICOM Send(2D).

체크리스트 원문 (변경 금지):
  Step 1. Setting - DICOM - DICOM Storage 등록한다.
  Step 2. Examine창에서 DICOM Send
  Step 3. View창에서 DICOM Send
  Step 4. Examined에서 DICOM Send
  Step 5. Selected/All Images
  Expected: 6. 선택한 영상이 등록된 SCP서버로 전송된다

판정 근거(운영 지침 2절):
  Queue 상태만 보지 않는다. **실제 수신된 DICOM 객체의 SOP Instance UID를 DB의
  INSTANCE.ImageInstanceUID와 대조**해 "등록된 SCP 서버로 전송되었다"를 증명한다.

2026-08-18 실측으로 확정한 전제 (자세한 근거는 NEXT_TASK.md):
  * Send 버튼(1148)은 **영상을 선택해야** 활성화된다. 사양도 "전송할 검사 항목
    또는 영상을 선택하십시오"라고 명시한다.
  * 첫 Send 클릭이 삼켜지는 일이 있어 재시도가 필요하다
    (`flows.send_current_study`가 처리).
  * Bunny는 수신 객체를 `Receive`가 아니라 **`Temp`** 에 저장한다.
  * Storage 서버의 Transfer Syntax가 JPEG2000이면 Bunny가 Presentation Context를
    **Rejected**하여 전송이 실패한다. Implicit VR LE로 맞춰야 한다.
"""

import os
import time

from core import dicomlite, flows
from core import viewer_processing as vp
from core import dicom_settings as ds
from core.dicom_settings import ensure_bunny
from core.result import TCResult, PASS, FAIL, MANUAL

# Storage 서버 Option 컨트롤 (Setting > DICOM > Storage), 2026-08-18 실측.
# Transfer Syntax 관련 상수와 조작은 WF04와 공유하려고
# `core/dicom_settings.py`로 옮겼다(`ds.STORAGE_TRANSFER_SYNTAX`,
# `ds.TRANSFER_SYNTAX_IMPLICIT`, `ds.ensure_storage_transfer_syntax`).
STORAGE_MODALITY = 2460


def _received(ctx):
    root = (ctx.cfg.get("dicom") or {}).get("received_root") or ""
    if not root or not os.path.isdir(root):
        return None
    return dicomlite.scan_dir(root)


def _clear_received(ctx):
    """수신 폴더를 비운다. 이번 전송으로 도착한 것만 세기 위한 준비다."""
    root = (ctx.cfg.get("dicom") or {}).get("received_root") or ""
    removed = 0
    if root and os.path.isdir(root):
        for dirpath, _, files in os.walk(root):
            for name in files:
                try:
                    os.remove(os.path.join(dirpath, name))
                    removed += 1
                except OSError:
                    pass
    return removed


def _queue_keys(ctx):
    return {int(r["Key"]) for r in ctx.db.query(
        "DATA", "SELECT [Key] FROM DICOM_STORAGE_QUEUE")}


def _db_instance_uids(ctx, patient_id):
    rows = ctx.db.query(
        "DATA",
        "SELECT i.ImageInstanceUID FROM INSTANCE i "
        "JOIN STUDY s ON s.[Key] = i.StudyKey "
        "JOIN PATIENT p ON p.[Key] = s.PatientKey "
        "WHERE p.PatientID = @pid AND i.ImageInstanceUID IS NOT NULL",
        {"pid": patient_id})
    return {r["ImageInstanceUID"] for r in rows}


def _db_identity(ctx, patient_id):
    """원본 검사의 식별 Tag를 DB에서 읽는다.

    개정본 Step 5는 **Patient ID / Study Instance UID / Series Instance UID /
    SOP Instance UID 네 개**를 비교하라고 한다. 이전 구현은 SOP Instance UID와
    Patient ID만 봤다.

    반환: {"patient_id": ..., "study_uids": {...}, "series_uids": {...},
           "sop_uids": {...}, "by_type": {InstanceType: {sop_uid, ...}}}
    """
    rows = ctx.db.query(
        "DATA",
        "SELECT i.ImageInstanceUID, i.InstanceType, se.SeriesInstanceUID, "
        "s.StudyInstanceUID FROM INSTANCE i "
        "JOIN STUDY s ON s.[Key] = i.StudyKey "
        "JOIN PATIENT p ON p.[Key] = s.PatientKey "
        "LEFT JOIN SERIES se ON se.[Key] = i.SeriesKey "
        "WHERE p.PatientID = @pid AND i.ImageInstanceUID IS NOT NULL",
        {"pid": patient_id})
    by_type = {}
    for row in rows:
        by_type.setdefault(int(row["InstanceType"]), set()).add(
            row["ImageInstanceUID"])
    return {
        "patient_id": patient_id,
        "study_uids": {r["StudyInstanceUID"] for r in rows if r.get("StudyInstanceUID")},
        "series_uids": {r["SeriesInstanceUID"] for r in rows if r.get("SeriesInstanceUID")},
        "sop_uids": {r["ImageInstanceUID"] for r in rows},
        "by_type": by_type,
    }


def _wait_received_stable(ctx, wait=60, settle_rounds=3, poll=2.0):
    """수신 개수가 **더 늘지 않을 때까지** 기다린 뒤 목록을 확정한다.

    이전 구현은 UID가 하나라도 보이면 즉시 break 해서, 실제로 여러 건이 도착해도
    판정에는 1건으로 기록됐다(2026-08-19 실측: SCP 로그에 C-STORE 5건인데 판정은
    전부 '수신 1건'). 그러면 "몇 개가 왔는가"를 요구하는 개정본 Expected를
    검증할 수 없다 - Selected(1개)와 All(전체)의 차이가 시험 대상이다.

    개수가 `settle_rounds`회 연속 같으면 확정한다.
    """
    end = time.time() + wait
    objects, stable = [], 0
    while time.time() < end:
        current = _received(ctx) or []
        if current and len(current) == len(objects):
            stable += 1
            if stable >= settle_rounds:
                return current
        else:
            stable = 0
        objects = current
        time.sleep(poll)
    return objects


def _ensure_transfer_syntax(ctx, ui, r):
    """Storage Transfer Syntax를 사양이 선언한 값으로 맞추고 판정을 기록한다.

    실제 조작은 `core.dicom_settings.ensure_storage_transfer_syntax`가 한다
    (WF04와 공유 — 근거와 호출 시점 주의사항은 그 함수 주석 참고).

    **검사를 열기 전에 호출해야 한다.** 검사 진행 중에 Setting을 드나들면
    Examine 화면의 영상 선택이 풀려 Send 버튼이 비활성이 되고, 전송 범위
    대화상자가 아예 뜨지 않는다(2026-08-18 회귀에서 Step 2/5가 이렇게 실패했다).
    """
    outcome = ds.ensure_storage_transfer_syntax(ctx, ui)
    r.add(1, "Storage 서버 등록 및 Transfer Syntax 확인",
          PASS if outcome["ok"] else FAIL,
          expected=f"TransferSyntax={ds.TRANSFER_SYNTAX_IMPLICIT} (Implicit VR LE)",
          actual=outcome,
          note="DICOM Conformance Statement V1.3W1 Proposed Presentation Context "
               "Table이 네트워크 Storage SCU에 선언한 값. 제품 기본값인 JPEG 2000 "
               "Lossless(1.2.840.10008.1.2.4.90)는 conformant SCP가 Presentation "
               "Context를 거절해 전송이 실패한다(Bunny 로그 실측). "
               "CONFIGURATION.DICOM_STORAGE로 대조.")
    return outcome["ok"]


QUEUE_STATE_DONE = 7          # DICOM_STORAGE_QUEUE.State (2026-08-18 실측)

# DICOM Conformance Statement V1.3W1 Proposed Presentation Context Table
SOP_CLASS_MG = "1.2.840.10008.5.1.4.1.1.1.2"      # Digital Mammography X-Ray Image
SOP_CLASS_DBT = "1.2.840.10008.5.1.4.1.1.13.1.3"  # Breast tomosynthesis Image
SOP_CLASS_RDSR = "1.2.840.10008.5.1.4.1.1.88.67"  # X-Ray Radiation Dose SR


def _send_and_verify(ctx, ui, r, patient_id, scope="selected",
                     expect_count=None, expect_types=None, wait=90,
                     step_queue=3, step_receive=4, step_tags=5):
    """전송 1회를 수행하고 개정본 Step 3~5를 각각 판정한다.

    개정본 `TC_Basic_WorkFlow_04`의 Expected는 세 가지를 따로 요구한다.
      Step 3. Queue 상태가 Done으로 표시된다.
      Step 4. Storage SCP에 **2D 객체 1개**가 수신된다(개수까지 명시).
      Step 5. 원본과 수신 객체의 **Patient ID / Study·Series·SOP Instance UID**가
              일치한다(네 개 태그).
    한 판정으로 묶으면 어디가 틀렸는지 리포트에서 구분되지 않으므로 나눈다.

    `expect_count`가 주어지면 **정확히 그 개수**를 요구한다. 이전 구현은 ">=1건"만
    봐서 Selected와 All의 차이를 검증하지 못했다.
    """
    _clear_received(ctx)
    before_queue = _queue_keys(ctx)
    try:
        sent = flows.send_current_study(ui, scope=scope)
    except Exception as exc:
        r.add(step_queue, f"전송 범위 '{scope}' 선택 후 전송", FAIL,
              expected=f"Send 후 범위 대화상자에서 '{scope}' 선택", actual=str(exc))
        return None

    objects = _wait_received_stable(ctx, wait=wait)
    new_queue = sorted(_queue_keys(ctx) - before_queue)

    # --- Step 3: Queue 등록과 Done 상태 --------------------------------
    states = {int(row["Key"]): int(row["State"]) for row in ctx.db.query(
        "DATA", "SELECT [Key],State FROM DICOM_STORAGE_QUEUE")}
    added_states = {k: states.get(k) for k in new_queue}
    done = [k for k, v in added_states.items() if v == QUEUE_STATE_DONE]
    r.assert_true(
        step_queue, "DICOM 창 Queue 모드에서 전송 상태 확인",
        bool(new_queue) and len(done) == len(new_queue),
        expected=f"이번 전송 항목이 Queue에 등록되고 전부 State={QUEUE_STATE_DONE}"
                 "(Done)",
        actual={"scope": sent, "queue_added": new_queue,
                "states": added_states, "done": done},
        note="DATA.DICOM_STORAGE_QUEUE.State로 대조. 개정본 Expected 3.")

    # --- Step 4: 수신 객체 개수 ----------------------------------------
    identity = _db_identity(ctx, patient_id)
    detail = {
        "received_objects": len(objects),
        "received_patient_ids": sorted({o.get("PatientID") for o in objects}),
        "received_modalities": sorted({o.get("Modality") for o in objects}),
        "received_sop_classes": sorted({o.get("SOPClassUID") for o in objects}),
    }
    if expect_count is None:
        count_ok = bool(objects)
        count_expected = "수신 객체 >=1건"
    else:
        count_ok = len(objects) == expect_count
        count_expected = f"수신 객체 정확히 {expect_count}건"
    r.assert_true(
        step_receive, "Storage SCP에서 수신 객체 확인", count_ok,
        expected=count_expected, actual=detail,
        note="Queue 상태가 아니라 **실제 수신 파일**을 파싱해 센다. 개수가 더 늘지 "
             "않고 안정될 때까지 기다린 뒤 확정한다(운영 지침 2절).")

    # --- Step 5: 식별 Tag 4개 비교 -------------------------------------
    got = {
        "PatientID": {o.get("PatientID") for o in objects if o.get("PatientID")},
        "StudyInstanceUID": {o.get("StudyInstanceUID") for o in objects
                             if o.get("StudyInstanceUID")},
        "SeriesInstanceUID": {o.get("SeriesInstanceUID") for o in objects
                              if o.get("SeriesInstanceUID")},
        "SOPInstanceUID": {o.get("SOPInstanceUID") for o in objects
                           if o.get("SOPInstanceUID")},
    }
    mismatch = {
        "PatientID": sorted(got["PatientID"] - {identity["patient_id"]}),
        "StudyInstanceUID": sorted(got["StudyInstanceUID"] - identity["study_uids"]),
        "SeriesInstanceUID": sorted(got["SeriesInstanceUID"] - identity["series_uids"]),
        "SOPInstanceUID": sorted(got["SOPInstanceUID"] - identity["sop_uids"]),
    }
    tags_ok = bool(objects) and not any(mismatch.values())
    r.assert_true(
        step_tags, "원본과 수신 객체의 식별 Tag 비교", tags_ok,
        expected=f"Patient ID / Study·Series·SOP Instance UID 4개가 모두 "
                 f"{patient_id}의 DB 값과 일치",
        actual={"received": {k: sorted(v) for k, v in got.items()},
                "not_in_db": mismatch},
        note="DATA의 PATIENT/STUDY/SERIES/INSTANCE와 대조. 개정본 Expected 5가 "
             "요구하는 네 개 태그 전부를 본다.")

    detail.update({"queue_added": new_queue, "tag_mismatch": mismatch})
    if expect_types is not None:
        detail["instance_types_in_db"] = {
            k: len(v) for k, v in sorted(identity["by_type"].items())}
    return detail


def workflow_04(ctx):
    r = TCResult("TC_Basic_WorkFlow_04", "2D 수동 DICOM Send")
    patient_id = (ctx.cfg.get("xipl") or {}).get(
        "test_patient_id", "DATA_FLOW_MWL_01")
    try:
        if not ensure_bunny(ctx.cfg):
            r.add(0, "Storage SCP(Bunny) 기동", FAIL,
                  expected="Bunny 실행 및 수신 포트 대기", actual="기동/포트 확인 실패")
            return r
        root = (ctx.cfg.get("dicom") or {}).get("received_root") or ""
        if not root or not os.path.isdir(root):
            r.add(0, "수신 폴더 확인", FAIL,
                  expected="config.json > dicom.received_root 실재 폴더",
                  actual=root or "미설정")
            return r

        # Step 1: Storage 등록 상태와 전송 가능한 Transfer Syntax 확인.
        # **검사를 열기 전에** 한다 — Setting을 드나들면 Examine 화면의 영상 선택이
        # 풀려 Send가 비활성이 된다(2026-08-18 회귀 실패 원인).
        ui = flows.cold_start(ctx.cfg, ctx.db)[0]
        if not flows.ensure_patient_screen(ui):
            r.add(1, "Storage 서버 등록 및 Transfer Syntax 확인", FAIL,
                  expected="Patient 화면에서 Setting 진입",
                  actual={"landmarks": flows.known_screen(ui)})
            return r
        if not _ensure_transfer_syntax(ctx, ui, r):
            return r

        # 설정을 끝낸 뒤에 검사를 연다.
        session = vp.open_test_study(ctx)
        ui = session["ui"]

        # --- Step 1: 대상 검사 선택 ------------------------------------
        r.assert_true(
            1, "Examined 창에서 대상 검사 선택",
            bool(session.get("study_key")) or bool(session.get("step_2d")),
            expected=f"{patient_id} 검사가 전송 대상으로 열린다",
            actual={"study": session.get("study_key"),
                    "step_2d": session.get("step_2d")},
            note="개정본 Expected 1. 이후 Send는 이 검사의 영상을 대상으로 한다.")

        # --- Step 2: 2D 영상을 Selected Images로 전송 -------------------
        # 개정본은 **Selected Images**로 2D 영상 1개를 보내고 "2D 객체 1개가
        # 수신된다"까지 요구한다(Expected 4). All Images 전송은 별개 TC
        # (WF_06 All Images 및 Dose SR 전송)이므로 여기서 하지 않는다.
        flows.select_step(ui, session["step_2d"])
        vp.expand_tools(ui)
        outcome = _send_and_verify(ctx, ui, r, patient_id, scope="selected",
                                   expect_count=1)
        r.assert_true(
            2, "Send 기능에서 2D 영상을 Selected Images로 전송",
            bool(outcome) and bool(outcome.get("queue_added")),
            expected="선택한 2D 영상이 Queue에 등록된다",
            actual=outcome or "전송 실패",
            note="개정본 Expected 2. Selected 범위 대화상자를 실제로 선택한다.")

        if outcome and outcome.get("received_sop_classes"):
            r.assert_true(
                4, "수신 객체가 Digital Mammography X-Ray Image Storage인지",
                outcome["received_sop_classes"] == [SOP_CLASS_MG],
                expected=f"SOP Class UID = {SOP_CLASS_MG}",
                actual=outcome["received_sop_classes"],
                note="DICOM Conformance Statement V1.3W1 Proposed Presentation "
                     "Context Table의 Digital Mammography X-ray Image Storage - "
                     "For Presentation. 2D 영상임을 SOP Class로 확인한다.")
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_04 실행", FAIL, actual=str(exc))
    return r


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
    * RDSR이 도착하지 않으면 **FAIL이 아니라 MANUAL**로 보고한다. Precondition이
      "RDSR 생성 조건을 충족"을 요구하는데 이 환경은 Demo(F8) 가상 촬영이라 그
      조건이 성립하는지 확인되지 않았다. 전제 미충족을 제품 결함처럼 보고하지
      않는다(운영 지침 2절). 관측값은 증적으로 남긴다.
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

        storage = ctx.db.one(
            "CONFIGURATION",
            "SELECT TOP 1 [Key],Name,SendDoseSR FROM DICOM_STORAGE "
            "WHERE [Use]=1 ORDER BY [Key]") or {}
        r.assert_true(
            0, "[전제] Storage 설정의 Dose SR 전송 활성화",
            int(storage.get("SendDoseSR") or 0) == 1,
            expected="CONFIGURATION.DICOM_STORAGE.SendDoseSR = 1",
            actual=storage,
            note="개정본 Precondition. 0이면 RDSR이 Queue에 등록되지 않는다.")
        if not _ensure_transfer_syntax(ctx, ui, r):
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
        identity = _db_identity(ctx, patient_id)
        outcome = _send_and_verify(ctx, ui, r, patient_id, scope="all",
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
                       if str(row.get("ClassUID") or "") == SOP_CLASS_RDSR]
        image_queued = [row for row in added
                        if str(row.get("ClassUID") or "")
                        in (SOP_CLASS_MG, SOP_CLASS_DBT)]
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
                note=f"RDSR SOP Class UID {SOP_CLASS_RDSR}(체크리스트 Test Data)로 "
                     "구분한다. DICOM_STORAGE_QUEUE.ClassUID 대조.")
        else:
            r.manual(
                3, "Queue에서 Image와 DSR Type 항목 확인",
                "Queue에 RDSR SOP Class 항목이 없다. 개정본 Precondition은 '검사가 "
                "종료되어 RDSR 생성 조건을 충족'을 요구하는데, 이 환경은 실제 X-ray "
                "대신 Demo(F8) 가상 촬영이라 그 조건이 성립하는지 확인되지 않았다. "
                "전제 미충족을 제품 결함으로 보고하지 않는다 - 실제 촬영 환경에서 "
                "재확인이 필요하다.",
                expected="Image와 RDSR이 모두 Queue에 등록",
                actual=detail_queue)

        received = _received(ctx) or []
        rdsr = [o for o in received
                if str(o.get("SOPClassUID") or "") == SOP_CLASS_RDSR]
        images = [o for o in received
                  if str(o.get("SOPClassUID") or "")
                  in (SOP_CLASS_MG, SOP_CLASS_DBT)]
        r.add(4, "Storage SCP에서 영상 객체와 RDSR 객체 수 확인",
              PASS if (images and rdsr) else MANUAL,
              expected="전송 대상 영상과 RDSR이 누락 없이 수신",
              actual={"received_total": len(received),
                      "image_objects": len(images),
                      "rdsr_objects": len(rdsr),
                      "db_instances_by_type": {
                          k: len(v)
                          for k, v in sorted(identity["by_type"].items())}},
              note="수신 파일을 파싱해 SOP Class로 구분한다. RDSR이 없으면 "
                   "위 Step 3의 사유와 같다.")
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
            r.manual(5, "RDSR의 Patient ID와 Study Instance UID 비교",
                     "수신된 RDSR 객체가 없어 대조할 수 없다(Step 3 사유 참고).",
                     expected="RDSR의 식별 Tag가 원본 검사와 일치",
                     actual="RDSR 미수신")
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_06 실행", FAIL, actual=str(exc))
    return r


# INSTANCE.InstanceType (이 저장소 전반에서 쓰는 값)
INSTANCE_2D = 0
INSTANCE_RAW = 1
INSTANCE_RECON = 2
INSTANCE_SYN = 3
INSTANCE_NAMES = {0: "2D", 1: "Raw", 2: "Recon", 3: "Syn"}

# 3D 검사에서 **네트워크로 실제 전송되는** InstanceType.
#
# 근거 1 (사양서 명문) - `(사양서) Bellalun Viewer 사양서1` **125쪽**,
#   SRS 06-30-30(Storage) 문맥:
#     "3D 영상은 Recon 영상이 전송된다. Recon 영상이 없을 경우 영상은 전송되지
#      않는다."
#   체크리스트 WF_05 Test Data가 "Recon 영상만 전송 여부는 검증 버전 사양 추가
#   확인 필요"라고 남긴 의문의 답이 이 문장이다. `core.specs`로 사양서를 검색해
#   찾았다(2026-08-19).
#
# 근거 2 (DICOM 선언) - DICOM Conformance Statement V1.3W1 "Proposed Presentation
#   Context Table": 네트워크 Storage SCU가 선언한 Abstract Syntax는 Digital
#   Mammography X-Ray Image Storage **- For Presentation**, Breast tomosynthesis
#   Image Storage, X-Ray Radiation Dose SR Storage 세 가지다.
#   **For Processing(1.2.840.10008.5.1.4.1.1.1.1)은 문서 전체에 선언돼 있지 않다**
#   (grep 0건). Raw(투영영상)는 For Processing 계열이라 전송 대상이 아니다.
#
# 근거 3 (실측) - 2026-08-19: All Images 전송 후 수신 객체를 SOP Instance UID로
#   DB와 대조하니, DB에 InstanceType 0/1/2/3이 각 1건인데 수신은 **2D(0)와
#   Recon(2)** 두 건이었다. 수신 SOP Class는 ...1.1.1.2 와 ...13.1.3 두 종뿐이다.
#
# 세 근거가 일치한다. 3D 중 전송되는 것은 **Recon만**이다.
SENDABLE_3D_TYPES = (INSTANCE_RECON,)


def workflow_05(ctx):
    r"""TC_Basic_WorkFlow_05 - 3D 수동 DICOM Send.

    체크리스트 원문 (변경 금지) - 개정본 시트 `개정 TC` row 15:
      Precondition
        TC_Basic_WorkFlow_03이 Pass이다.
        Storage SCP가 Online이며 수신 객체 확인이 가능하다.
        3D 전송 대상 영상 종류는 검증 버전 사양과 일치하도록 설정되어 있다.
      Step 1. Examined 창에서 DATA_FLOW_MWL_01 검사를 선택한다.
      Step 2. Send 기능에서 3D 전송 대상 영상을 선택한다.
      Step 3. DICOM 창의 Queue 모드에서 전송 상태를 확인한다.
      Step 4. Storage SCP에서 수신 객체를 확인한다.
      Step 5. 원본과 수신 객체의 Patient ID, Study Instance UID,
              Series Instance UID, SOP Instance UID를 비교한다.
      Test Data: 3D 대상 - Recon 영상만 전송 여부는 검증 버전 사양 추가 확인 필요

    전송 대상은 **Raw / Recon / Syn 세 종류를 모두 포함**한다(사용자 확정,
    2026-08-19). 픽스처는 `WF_02`가 만든 3D-N 검사로 InstanceType 1/2/3이 각
    1건씩 있다.

    그중 **실제로 수신되는 것은 Recon뿐**이다. 사양서1 125쪽이 "3D 영상은 Recon
    영상이 전송된다"고 명문으로 정한다(근거 전체는 `SENDABLE_3D_TYPES` 주석).
    그래서 Raw/Syn 미수신은 FAIL이 아니고, 판정은 "사양이 정한 대상이 누락 없이
    왔는가"로 한다. 제품이 나중에 Raw/Syn도 보내게 바뀌면 `db_3d_types` /
    `received_types` 기록으로 드러난다.
    """
    r = TCResult("TC_Basic_WorkFlow_05", "3D 수동 DICOM Send")
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
        if not _ensure_transfer_syntax(ctx, ui, r):
            return r

        session = vp.open_test_study(ctx)
        ui = session["ui"]
        identity = _db_identity(ctx, patient_id)
        by_type = identity["by_type"]
        db_3d = {t: len(v) for t, v in sorted(by_type.items())
                 if t in (INSTANCE_RAW, INSTANCE_RECON, INSTANCE_SYN)}

        r.assert_true(
            0, "[전제] 3D 전송 대상 영상 종류 확인",
            all(db_3d.get(t) for t in (INSTANCE_RAW, INSTANCE_RECON,
                                       INSTANCE_SYN)),
            expected="검사에 Raw/Recon/Syn 각 1건 이상 존재",
            actual={"db_3d_types": {INSTANCE_NAMES[t]: n
                                    for t, n in db_3d.items()}},
            note="개정본 Precondition. 전송 대상은 Raw/Recon/Syn 전부이며, 그중 "
                 "네트워크로 선언된 것은 Recon이다(SENDABLE_3D_TYPES 주석 참고).")

        r.assert_true(
            1, "Examined 창에서 대상 검사 선택",
            bool(session.get("study_key")),
            expected=f"{patient_id} 검사가 전송 대상으로 열린다",
            actual={"study": session.get("study_key")},
            note="개정본 Expected 1.")

        # Step 2: 3D 스텝을 선택해 3D 영상을 전송 대상으로 삼는다.
        flows.select_step(ui, session["step_3d"])
        vp.expand_tools(ui)
        expected_uids = set()
        for t in SENDABLE_3D_TYPES:
            expected_uids |= by_type.get(t, set())
        outcome = _send_and_verify(ctx, ui, r, patient_id, scope="all",
                                   expect_count=None, wait=120)
        if outcome is None:
            return r
        r.assert_true(
            2, "Send 기능에서 3D 전송 대상 영상 선택 후 전송",
            bool(outcome.get("queue_added")),
            expected="사양에 정의된 3D 객체가 Queue에 등록된다",
            actual=outcome,
            note="개정본 Expected 2.")

        # 수신 객체를 InstanceType으로 되짚어 어떤 3D 종류가 왔는지 남긴다.
        received = _received(ctx) or []
        received_uids = {o.get("SOPInstanceUID") for o in received
                         if o.get("SOPInstanceUID")}
        uid_to_type = {}
        for t, uids in by_type.items():
            for u in uids:
                uid_to_type[u] = t
        received_types = sorted({uid_to_type[u] for u in received_uids
                                 if u in uid_to_type})
        missing = expected_uids - received_uids
        r.assert_true(
            4, "Storage SCP에서 전송 대상 3D 객체 수신 확인",
            bool(expected_uids) and not missing,
            expected={"declared_3d_types": [INSTANCE_NAMES[t]
                                            for t in SENDABLE_3D_TYPES],
                      "objects": len(expected_uids)},
            actual={"received_total": len(received),
                    "received_types": [INSTANCE_NAMES.get(t, t)
                                       for t in received_types],
                    "received_sop_classes": sorted(
                        {o.get("SOPClassUID") for o in received}),
                    "db_3d_types": {INSTANCE_NAMES[t]: n
                                    for t, n in db_3d.items()},
                    "declared_missing": sorted(missing)},
            note="개정본 Expected 4(전송 대상 3D 객체가 누락 없이 수신). 전송 "
                 "대상에는 Raw/Recon/Syn을 모두 포함했지만, **사양서1 125쪽"
                 "(SRS 06-30-30 문맥)이 \"3D 영상은 Recon 영상이 전송된다\"고 "
                 "명시**한다. DICOM Conformance Statement도 For Processing(Raw)을 "
                 "선언하지 않으며, 실측도 Recon만 수신됨을 확인했다. 따라서 "
                 "Raw/Syn 미수신은 결함이 아니다. 제품이 바뀌면 received_types로 "
                 "드러난다.")
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_05 실행", FAIL, actual=str(exc))
    return r


def run(ctx):
    return [workflow_04(ctx)]


def run_all_images(ctx):
    return [workflow_06(ctx)]


def run_3d(ctx):
    return [workflow_05(ctx)]
