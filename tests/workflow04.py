# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_04 — 2D 수동 DICOM Send.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.
공용 판정 헬퍼는 `core/send_verify.py`.
"""

from core import dicom_settings as ds
from core import send_verify as sv
from core.result import TCResult, FAIL

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
        if not sv.ensure_transfer_syntax(ctx, ui, r):
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
        outcome = sv.send_and_verify(ctx, ui, r, patient_id, scope="selected",
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
                outcome["received_sop_classes"] == [sv.SOP_CLASS_MG],
                expected=f"SOP Class UID = {sv.SOP_CLASS_MG}",
                actual=outcome["received_sop_classes"],
                note="DICOM Conformance Statement V1.3W1 Proposed Presentation "
                     "Context Table의 Digital Mammography X-ray Image Storage - "
                     "For Presentation. 2D 영상임을 SOP Class로 확인한다.")
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_04 실행", FAIL, actual=str(exc))
    return r


def run(ctx):
    return [workflow_04(ctx)]
