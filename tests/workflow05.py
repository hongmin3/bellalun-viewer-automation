# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_05 — 3D 수동 DICOM Send.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.
전송 대상 3D 영상 종류(`SENDABLE_3D_TYPES`)의 사양 근거는 `core/send_verify.py`.
"""

from core import dicom_settings as ds
from core import flows
from core import send_verify as sv
from core import viewer_processing as vp
from core.dicom_settings import ensure_storage_reachable
from core.result import TCResult, FAIL, SKIP

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

    그중 **실제로 수신되는 것은 Recon뿐**이다. 사양서 599쪽이 "3D 영상은 Recon
    영상이 전송된다"고 명문으로 정한다(근거 전체는 `sv.SENDABLE_3D_TYPES` 주석).
    같은 검사에서 Raw/Syn이 신규 Queue에 들어가거나 SCP에 새로 수신되면 실패다.
    2D와 Dose SR은 이 3D 인스턴스 판정에서 제외한다.
    """
    r = TCResult("TC_Basic_WorkFlow_05", "3D 수동 DICOM Send")
    patient_id = (ctx.cfg.get("xipl") or {}).get(
        "test_patient_id", "DATA_FLOW_MWL_01")
    try:
        reachable, storage = ensure_storage_reachable(ctx.cfg)
        if not reachable:
            r.add(0, "Storage SCP 도달 확인", FAIL,
                  expected="SCP running + DICOM 포트 연결", actual=storage,
                  note="2026-08-26 Bunny 대신 원격 Storage SCP 웹 서버를 쓴다.")
            return r

        ui = flows.cold_start(ctx.cfg, ctx.db)[0]
        if not flows.ensure_patient_screen(ui):
            r.add(0, "Patient 화면 진입", FAIL,
                  expected="Setting 진입 가능한 Patient 화면",
                  actual={"landmarks": flows.known_screen(ui)})
            return r
        if not sv.ensure_transfer_syntax(ctx, ui, r):
            return r

        session = vp.open_test_study(ctx)
        ui = session["ui"]
        identity = sv.db_identity(ctx, patient_id, study_key=session["study_key"])
        by_type = identity["by_type"]
        db_3d = {t: len(v) for t, v in sorted(by_type.items())
                 if t in (sv.INSTANCE_RAW, sv.INSTANCE_RECON, sv.INSTANCE_SYN)}

        r.assert_true(
            0, "[전제] 3D 전송 대상 영상 종류 확인",
            all(db_3d.get(t) for t in (sv.INSTANCE_RAW, sv.INSTANCE_RECON,
                                       sv.INSTANCE_SYN)),
            expected="검사에 Raw/Recon/Syn 각 1건 이상 존재",
            actual={"db_3d_types": {sv.INSTANCE_NAMES[t]: n
                                    for t, n in db_3d.items()}},
            note="개정본 Precondition. 전송 대상은 Raw/Recon/Syn 전부이며, 그중 "
                 "네트워크로 선언된 것은 Recon이다(sv.SENDABLE_3D_TYPES 주석 참고).")

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
        for t in sv.SENDABLE_3D_TYPES:
            expected_uids |= by_type.get(t, set())
        outcome = sv.send_and_verify(ctx, ui, r, patient_id, scope="all",
                                   expect_count=None, wait=120,
                                   study_key=session["study_key"],
                                   fresh_image_types=sv.SENDABLE_3D_TYPES)
        if outcome is None:
            return r
        r.assert_true(
            2, "Send 기능에서 3D 전송 대상 영상 선택 후 전송",
            bool(outcome.get("queue_added")),
            expected="사양에 정의된 3D 객체가 Queue에 등록된다",
            actual=outcome,
            note="개정본 Expected 2.")

        received_uids = set(outcome["received_image_uids"])
        queued_uids = set(outcome["queue_observed_uids"])
        not_sendable = set().union(*(by_type.get(t, set())
                                     for t in (sv.INSTANCE_RAW, sv.INSTANCE_SYN)))
        unexpected_3d = {"queue": sorted(queued_uids & not_sendable),
                         "received": sorted(received_uids & not_sendable)}
        uid_to_type = {}
        for t, uids in by_type.items():
            for u in uids:
                uid_to_type[u] = t
        received_types = sorted({uid_to_type[u] for u in received_uids
                                 if u in uid_to_type})
        missing = expected_uids - received_uids
        r.assert_true(
            4, "Storage SCP에서 전송 대상 3D 객체 수신 확인",
            bool(expected_uids) and not missing and not any(unexpected_3d.values()),
            expected={"declared_3d_types": [sv.INSTANCE_NAMES[t]
                                            for t in sv.SENDABLE_3D_TYPES],
                      "objects": len(expected_uids), "unexpected_3d": 0},
            actual={"received_total": outcome["received_objects"],
                    "received_types": [sv.INSTANCE_NAMES.get(t, t)
                                       for t in received_types],
                    "received_sop_classes": outcome["received_sop_classes"],
                    "db_3d_types": {sv.INSTANCE_NAMES[t]: n
                                    for t, n in db_3d.items()},
                    "declared_missing": sorted(missing),
                    "unexpected_3d": unexpected_3d},
            note="R-23-2346 Basic Function Checklist K16:L16 및 R-25-782 Checklist H12:I12. "
                 "신규 Queue와 해당 검사 SCP의 전송 전후 영상 SOP를 비교한다.")

        # --- 3D-N / 3D-W 구분 (픽스처 확장, 2026-08-26) --------------------
        #
        # 두 촬영 모드 모두 SOP Class 는 DBT 로 같아서 **객체만 보면 구분되지
        # 않는다.** 그래서 DB 의 Series 로 되짚는다 — 3D-N 과 3D-W 는 각각 자기
        # Series/Group 을 갖는다(WF_02 가 그렇게 만든다). 픽스처에 3D-W 가 없으면
        # (`test_data.include_3d_wide=false`) 확인할 대상이 없으므로 SKIP 이다.
        recon_uids = by_type.get(sv.INSTANCE_RECON, set())
        recon_series = ctx.db.query(
            "DATA",
            "SELECT SeriesKey, COUNT(*) AS n FROM INSTANCE "
            "WHERE StudyKey=@study AND InstanceType=@t "
            "GROUP BY SeriesKey ORDER BY SeriesKey",
            {"study": session["study_key"], "t": sv.INSTANCE_RECON})
        received_recon = sorted(recon_uids & received_uids)
        if len(recon_series) < 2:
            r.add(4, "3D-N / 3D-W 각각 수신 확인", SKIP,
                  expected="Recon Series 2개(3D-N, 3D-W)",
                  actual=f"픽스처의 Recon Series {len(recon_series)}개 — "
                         f"3D-W 스텝이 없다",
                  note="`config.json > test_data.include_3d_wide` 를 켜고 WF_02 로 "
                       "픽스처를 다시 만들면 3D-W 스텝이 생긴다.")
        else:
            r.assert_true(
                4, "3D-N / 3D-W 각각 수신 확인",
                len(received_recon) == len(recon_uids) and len(recon_uids) >= 2,
                expected=f"Recon {len(recon_uids)}건(3D-N·3D-W 각 1건) 전부 수신",
                actual={"recon_series": [dict(x) for x in recon_series],
                        "received_recon": len(received_recon),
                        "missing_recon": sorted(recon_uids - received_uids)},
                note="3D-N 과 3D-W 는 SOP Class 가 DBT 로 같아 객체만으로는 "
                     "구분되지 않는다. DB Series 로 되짚어 **두 촬영 모드가 모두** "
                     "전송·수신됐는지 본다.")
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_05 실행", exc)
    return r


def run(ctx):
    return [workflow_05(ctx)]
