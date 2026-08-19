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
from core.result import TCResult, PASS, FAIL

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


def _send_and_verify(ctx, ui, r, step, title, scope, patient_id, wait=60):
    """전송 1회를 수행하고 수신 객체를 DB UID와 대조한다."""
    _clear_received(ctx)
    before_queue = _queue_keys(ctx)
    try:
        sent = flows.send_current_study(ui, scope=scope)
    except Exception as exc:
        r.add(step, title, FAIL,
              expected=f"전송 범위 '{scope}' 선택 후 전송", actual=str(exc))
        return None

    end = time.time() + wait
    objects = []
    while time.time() < end:
        objects = _received(ctx) or []
        if objects:
            break
        time.sleep(2)

    new_queue = _queue_keys(ctx) - before_queue
    states = ctx.db.query(
        "DATA", "SELECT [Key],State FROM DICOM_STORAGE_QUEUE ORDER BY [Key] DESC")
    expected_uids = _db_instance_uids(ctx, patient_id)
    received_uids = {o.get("SOPInstanceUID") for o in objects
                     if o.get("SOPInstanceUID")}
    unknown = received_uids - expected_uids
    detail = {
        "scope": sent, "queue_added": sorted(new_queue),
        "queue_states": states[:4],
        "received_objects": len(objects),
        "received_patient_ids": sorted({o.get("PatientID") for o in objects}),
        "received_modalities": sorted({o.get("Modality") for o in objects}),
        "received_sop_classes": sorted({o.get("SOPClassUID") for o in objects}),
        "uids_matched_db": len(received_uids & expected_uids),
        "uids_not_in_db": sorted(unknown),
    }
    ok = (bool(objects) and bool(new_queue) and not unknown
          and received_uids <= expected_uids)
    r.assert_true(
        step, title, ok,
        expected=f"수신 객체 >=1건, 모든 SOP Instance UID가 {patient_id}의 "
                 f"DB INSTANCE와 일치",
        actual=detail,
        note="Queue 상태만으로 판정하지 않고 실제 수신 객체의 UID를 DB와 "
             "대조한다(운영 지침 2절).")
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

        # Step 2 + Step 5(All Images): Examine 화면에서 전송
        flows.select_step(ui, session["step_2d"])
        vp.expand_tools(ui)
        _send_and_verify(ctx, ui, r, 2,
                         "Examine창에서 DICOM Send (All Images)",
                         "all", patient_id)

        # Step 5(Selected): 같은 화면에서 선택 영상만 전송
        flows.select_step(ui, session["step_2d"])
        vp.expand_tools(ui)
        _send_and_verify(ctx, ui, r, 5,
                         "Selected 범위로 DICOM Send",
                         "selected", patient_id)

        # Step 3/4: View창·Examined 경로
        r.manual(3, "View창에서 DICOM Send",
                 "View 화면의 Send 진입점을 아직 확정하지 못했다. Examined 툴바 14개는 "
                 "전수 확인 결과 Send가 없었고(2184=Import, 2191=Export Manager, "
                 "2192=검사 폴더 열기, 2195=폴더 찾아보기, 2197=Move Image), "
                 "View 화면 경로는 별도 실측이 필요하다.",
                 expected="View 화면에서 전송 후 수신 객체 UID 대조",
                 actual="진입점 미확정")
        r.manual(4, "Examined에서 DICOM Send",
                 "Examined 툴바에 Send 버튼이 없다(2026-08-18 전수 확인). "
                 "컨텍스트 메뉴 등 다른 경로를 확인해야 한다.",
                 expected="Examined 화면에서 전송 후 수신 객체 UID 대조",
                 actual="툴바에 Send 없음")
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_05 실행", FAIL, actual=str(exc))
    return r


def run(ctx):
    return [workflow_04(ctx)]
