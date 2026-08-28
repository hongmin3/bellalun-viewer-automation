# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_04 — 2D 수동 DICOM Send.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.
공용 판정 헬퍼는 `core/send_verify.py`.

체크리스트 원문 (변경 금지)
  Precondition
    TC_Basic_WorkFlow_03~04가 Pass이다.
    Storage SCP가 Online이며 수신 객체 확인이 가능하다.
  Step 1. Examined 창에서 DATA_FLOW_MWL_01 검사를 선택한다.
  Step 2. Send 기능에서 IMG_FLOW_2D_01을 Selected Images로 전송한다.
  Step 3. DICOM 창의 Queue 모드에서 전송 상태를 확인한다.
  Step 4. Storage SCP에서 수신 객체를 확인한다.
  Step 5. 원본과 수신 객체의 Patient ID, Study Instance UID, Series Instance UID,
          SOP Instance UID를 비교한다.

## Step 1 을 이 TC 가 직접 밟는다 (2026-08-27)

그전에는 `viewer_processing.open_test_study` 로 검사를 열었다. 그 함수도 같은 UI
경로(Examined 검색 -> 카드 선택 -> View)를 지나가지만, **XIPL 픽스처 준비**
(Overlay 항목 보장, InstanceType 0/1/2/3 무결성 검사, 세션 dict 구성)까지 하는
공용 준비 흐름이다. 그래서 자동화 범위표는 이 TC 를 *"Step 1 의 UI 경로를 이 TC 가
직접 밟지 않는다"* 는 이유로 **부분 자동**으로 두고 있었다.

이제 `flows.open_examined_study` 로 **카드를 직접 고르고 열며**, 목록에서 무엇을
골랐는지(카드 수·순번·rect·열린 Step 수)를 Expected 1 의 근거로 남긴다. 픽스처
무결성은 화면이 아니라 DB 로 따로 확인한다 — 준비 흐름에 얹지 않기 위해서다.

## 왜 Selected Images 인가

개정본 Step 2 는 **Selected Images** 로 2D 영상 1개를 보내고 "2D 객체 1개가
수신된다"(Expected 4)까지 요구한다. All Images 전송은 별개 TC(`WF_06` All Images
및 Dose SR 전송)이므로 여기서 하지 않는다. 이 경로는 사양서1 173쪽 SRS 03-10-50
("Examine/View 모드에서 Send/Multi-Send 버튼을 클릭했을 때는 Dose SR 을 전송하지
않는다")에 따라 **Dose SR 이 오지 않는 것이 정상**이고, 그래서 수신 객체를 정확히
1건으로 요구할 수 있다.
"""

from core import flows
from core import send_verify as sv
from core import viewer_processing as vp
from core.dicom_settings import ensure_storage_reachable
from core.result import TCResult, FAIL, PASS


def _fixture(ctx, patient_id):
    """대상 검사와 그 영상 구성을 DB 에서 확인한다(화면 조작 전에)."""
    row = ctx.db.one(
        "DATA",
        "SELECT TOP 1 s.[Key],s.StudyInstanceUID FROM STUDY s "
        "JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid AND EXISTS (SELECT 1 FROM INSTANCE i "
        "WHERE i.StudyKey=s.[Key] AND i.InstanceType=@2d) ORDER BY s.[Key] DESC",
        {"pid": patient_id, "2d": sv.INSTANCE_2D})
    if not row:
        raise RuntimeError(
            f"2D 영상을 가진 검사를 찾지 못했습니다: PatientID={patient_id}")
    row["instances"] = ctx.db.query(
        "DATA", "SELECT [Key],InstanceType,ImageInstanceUID FROM INSTANCE "
        "WHERE StudyKey=@k ORDER BY [Key]", {"k": row["Key"]})
    return row


def workflow_04(ctx):
    r = TCResult("TC_Basic_WorkFlow_04", "2D 수동 DICOM Send")
    patient_id = (ctx.cfg.get("xipl") or {}).get(
        "test_patient_id", "DATA_FLOW_MWL_01")
    ui = None
    try:
        reachable, storage = ensure_storage_reachable(ctx.cfg)
        if not reachable:
            r.add(0, "Storage SCP 도달 확인", FAIL,
                  expected="SCP running + DICOM 포트 연결", actual=storage,
                  note="2026-08-26 Bunny 대신 원격 Storage SCP 웹 서버를 쓴다. "
                       "수신 확인도 파일이 아니라 HTTP API 로 한다.")
            return r

        study = _fixture(ctx, patient_id)
        types = sorted({int(i["InstanceType"]) for i in study["instances"]})
        r.assert_true(
            0, "[전제] 대상 검사에 2D 영상 존재", sv.INSTANCE_2D in types,
            expected=f"PatientID={patient_id} 검사에 InstanceType="
                     f"{sv.INSTANCE_2D}(2D) 영상 1건 이상",
            actual={"study": study["Key"],
                    "instance_types": [sv.INSTANCE_NAMES.get(t, t)
                                       for t in types]},
            note="개정본 Test Data 의 IMG_FLOW_2D_01 에 해당한다. 화면 조작 전에 "
                 "DB 로 확인한다 — 준비가 안 된 상태에서 UI 를 밟으면 실패 원인이 "
                 "'전송 실패' 로 뭉개진다.")

        # Step 1 전에 Storage 등록 상태와 Transfer Syntax 를 확정한다.
        # **검사를 열기 전에** 한다 — Setting을 드나들면 Examine 화면의 영상 선택이
        # 풀려 Send가 비활성이 된다(2026-08-18 회귀 실패 원인).
        #
        # `force_restart=True` 인 이유: 그전에 이 TC 가 쓰던
        # `viewer_processing.open_test_study` 가 검사를 열기 전에 **Viewer 를
        # 재시작**했고, 그 동작을 이어받는다. 2026-08-27 에 재시작 없이 돌렸더니
        # Send 는 눌려 Queue 행까지 생겼는데 **State=3 에서 20분 넘게 멈추고
        # DICOM Storage 로그에 전송 시도 기록조차 남지 않았다**(오래 떠 있던
        # Viewer 세션에서 관측). 재시작이 그 상태를 없앤다.
        ui = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)[0]
        if not flows.ensure_patient_screen(ui):
            r.add(1, "Storage 서버 등록 및 Transfer Syntax 확인", FAIL,
                  expected="Patient 화면에서 Setting 진입",
                  actual={"landmarks": flows.known_screen(ui)})
            return r
        if not sv.ensure_transfer_syntax(ctx, ui, r):
            return r

        # --- Step 1: Examined 목록에서 대상 검사를 직접 골라 연다 ----------
        opened = flows.open_examined_study(ui, patient_id, card="oldest")
        steps = flows.step_items(ui)
        r.assert_true(
            1, "Examined 창에서 대상 검사 선택",
            bool(steps) and opened["cards"] >= 1,
            expected=f"Patient ID 로 검색한 {patient_id} 검사 카드를 골라 View 로 "
                     f"열면 촬영 Step 이 보인다",
            actual={"검색 카드 수": opened["cards"],
                    "고른 카드(0-based)": opened["picked"],
                    "카드 rect": opened["picked_rect"],
                    "열린 Step 수": len(steps),
                    "DB study": study["Key"]},
            note="개정본 Expected 1. **이 TC 가 직접 밟는 경로다** — Examined(View) "
                 "화면에서 검색 항목을 Patient ID 로 바꾸고 조회 범위를 Month 로 "
                 "넓혀 검색한 뒤(기본 Today 로는 재사용 픽스처가 안 나온다), "
                 "카드를 골라 View(2182)로 연다(core/flows.open_examined_study). "
                 "검색어가 Patient ID 이므로 목록에 나온 카드는 모두 그 환자의 "
                 "검사이고, 카드는 StudyDate/Time 내림차순이라 재사용 픽스처는 "
                 "가장 오래된 카드다. 열린 검사가 실제로 이 검사인지는 Step 5 의 "
                 "Study Instance UID 대조가 최종적으로 보증한다.")

        # --- Step 2: 2D 영상을 Selected Images로 전송 -------------------
        flows.select_step(ui, 1)
        vp.expand_tools(ui)
        outcome = sv.send_and_verify(ctx, ui, r, patient_id, scope="selected",
                                     expect_count=1)
        r.assert_true(
            2, "Send 기능에서 2D 영상을 Selected Images로 전송",
            bool(outcome) and bool(outcome.get("queue_added")),
            expected="선택한 2D 영상이 Queue에 등록된다",
            actual=outcome or "전송 실패",
            note="개정본 Expected 2. Selected 범위 대화상자를 실제로 선택한다. "
                 "첫 Step 이 2D 다 — 픽스처의 Step 순서는 WF_02 가 만든 "
                 "2D -> 3D-N -> 3D-W 그대로이고, 전송 객체가 2D SOP Class 1건인지는 "
                 "Step 4 가 확인한다.")

        if outcome and outcome.get("received_sop_classes"):
            r.assert_true(
                4, "수신 객체가 Digital Mammography X-Ray Image Storage인지",
                outcome["received_sop_classes"] == [sv.SOP_CLASS_MG],
                expected=f"SOP Class UID = {sv.SOP_CLASS_MG}",
                actual=outcome["received_sop_classes"],
                note="DICOM Conformance Statement V1.3W1 Proposed Presentation "
                     "Context Table의 Digital Mammography X-ray Image Storage - "
                     "For Presentation. 2D 영상임을 SOP Class로 확인한다. "
                     "이 경로(View 모드 Send)는 사양서1 173쪽 SRS 03-10-50 에 따라 "
                     "Dose SR 을 전송하지 않으므로 수신은 영상 1건뿐이어야 한다.")
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_04 실행", exc)
    finally:
        # **연 검사를 닫는다.** 이 TC 는 Examined 에서 카드를 골라 View 로 열므로,
        # 닫지 않으면 다음 TC 가 Examined 화면을 찾지 못한다 — 2026-08-28 실측:
        # WF_04 직후 `WF_06` 이 `Examined 검색 컨트롤(2177/2178/2179)을 찾지
        # 못했습니다` 로 진입조차 못 했다. 자기가 만든 화면 상태는 자기가 되돌린다
        # (운영 지침 12절 — 다른 TC 가 남긴 상태를 가정하지 않는다).
        _close_view(r, ui)
    return r


def _close_view(r, ui):
    """View 로 연 검사를 닫고 Examined 로 돌아간다. 예외를 밖으로 내지 않는다."""
    if ui is None:
        return
    try:
        closed = flows.close_view_study(ui)
        r.cleanup(0, "연 검사 닫기", PASS if closed else FAIL,
                  expected="View 화면을 닫고 Examined 목록으로 복귀",
                  actual=closed or "닫기 버튼을 찾지 못했다",
                  note="다음 TC 가 Examined 진입을 전제하므로 여기서 되돌린다.")
    except Exception as exc:                           # noqa: BLE001
        r.cleanup(0, "연 검사 닫기", FAIL,
                  expected="View 화면을 닫고 Examined 목록으로 복귀",
                  actual=f"{type(exc).__name__}: {exc}",
                  note="다음 TC 가 Examined 진입에 실패할 수 있다.")


def run(ctx):
    return [workflow_04(ctx)]
