# -*- coding: utf-8 -*-
r"""DICOM Send 판정의 공용 부분 — Queue / 수신 객체 / 식별 Tag 대조.

WF_04(2D) / WF_05(3D) / WF_06(All Images + Dose SR)이 공유한다. TC 별 절차는
`tests/workflow04.py` / `workflow05.py` / `workflow06.py` 에 있다.

판정 원칙 (운영 지침 2절): **Queue 상태만 보지 않는다.** 실제 수신 객체의
Patient ID / Study·Series·SOP Instance UID 를 DB 원본과 대조하고, SOP Class 로
객체 종류까지 확인한다. 로그 문구 하나로 성공을 단정하지 않는다.

`tests/send_flows.py`(삭제됨)에서 분리했다(2026-08-19). 파일명이 담당 TC 를 드러내도록
TC 함수를 번호별 모듈로 옮기면서, 인프라에 해당하는 이 부분만 core 로 내렸다.
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


def received(ctx):
    root = (ctx.cfg.get("dicom") or {}).get("received_root") or ""
    if not root or not os.path.isdir(root):
        return None
    return dicomlite.scan_dir(root)


def clear_received(ctx):
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


def queue_keys(ctx):
    return {int(r["Key"]) for r in ctx.db.query(
        "DATA", "SELECT [Key] FROM DICOM_STORAGE_QUEUE")}


def db_instance_uids(ctx, patient_id):
    rows = ctx.db.query(
        "DATA",
        "SELECT i.ImageInstanceUID FROM INSTANCE i "
        "JOIN STUDY s ON s.[Key] = i.StudyKey "
        "JOIN PATIENT p ON p.[Key] = s.PatientKey "
        "WHERE p.PatientID = @pid AND i.ImageInstanceUID IS NOT NULL",
        {"pid": patient_id})
    return {r["ImageInstanceUID"] for r in rows}


def db_identity(ctx, patient_id):
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


def wait_received_stable(ctx, wait=60, settle_rounds=3, poll=2.0):
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
        current = received(ctx) or []
        if current and len(current) == len(objects):
            stable += 1
            if stable >= settle_rounds:
                return current
        else:
            stable = 0
        objects = current
        time.sleep(poll)
    return objects


def ensure_transfer_syntax(ctx, ui, r):
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

# Queue 행이 영상인지 Dose SR 인지 가른다 (2026-08-20 실측).
#   영상 : DataType 이 1 이 아니고 InstanceKey / InstanceUID 가 실제 값
#   RDSR : DataType = 1, InstanceKey = -1, InstanceUID = NULL
# 이 환경(Demo F8 가상 촬영)에서는 RDSR 행이 **항상 State=3 으로 남는다** — 여러
# 실행에서 반복 확인했다(Key 32/35/38). RDSR 생성 조건이 성립하지 않기 때문이고
# 제품 결함이 아니다(WF_06 과 같은 판단).
QUEUE_DATATYPE_DOSE_SR = 1


def is_dose_sr_row(row):
    """Queue 행이 Dose SR 인가."""
    return (int(row.get("DataType") or 0) == QUEUE_DATATYPE_DOSE_SR
            and not row.get("InstanceUID"))

# DICOM Conformance Statement V1.3W1 Proposed Presentation Context Table
SOP_CLASS_MG = "1.2.840.10008.5.1.4.1.1.1.2"      # Digital Mammography X-Ray Image
SOP_CLASS_DBT = "1.2.840.10008.5.1.4.1.1.13.1.3"  # Breast tomosynthesis Image
SOP_CLASS_RDSR = "1.2.840.10008.5.1.4.1.1.88.67"  # X-Ray Radiation Dose SR


def send_and_verify(ctx, ui, r, patient_id, scope="selected",
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
    clear_received(ctx)
    before_queue = queue_keys(ctx)
    try:
        sent = flows.send_current_study(ui, scope=scope)
    except Exception as exc:
        r.add(step_queue, f"전송 범위 '{scope}' 선택 후 전송", FAIL,
              expected=f"Send 후 범위 대화상자에서 '{scope}' 선택", actual=str(exc))
        return None

    objects = wait_received_stable(ctx, wait=wait)
    new_queue = sorted(queue_keys(ctx) - before_queue)

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
    identity = db_identity(ctx, patient_id)
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
