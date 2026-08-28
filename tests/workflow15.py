# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_15 — Pre-send Preview 표시 및 전송.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.

체크리스트 원문 (변경 금지)
  Precondition
    TC_Basic_WorkFlow_03이 Pass이다.
    DATA_FLOW_MWL_01에 2D/3D 영상이 존재한다.
    Storage SCP가 Online이며 수신 객체 확인이 가능하다.
  Step
    1. Examined 창에서 DATA_FLOW_MWL_01 검사를 선택한다.
    2. Pre-send Preview를 실행한다.
    3. Preview 팝업에 표시된 각 Step 영상과 Overlay를 확인한다.
    4. 동일 검사를 View 또는 Examine 화면에서 열어 Step 영상과 Overlay를 비교한다.
    5. Preview에서 Send를 실행한다.
    6. DICOM 창의 Queue 모드에서 전송 상태를 확인한다.
    7. Storage SCP에서 수신 객체를 확인한다.
  Expected Result
    1. 선택한 검사가 Preview 대상으로 지정된다.
    2. Send Preview 팝업이 표시된다.
    3. 검사의 각 Step 영상과 설정한 Overlay 항목이 표시된다.
    4. View 또는 Examine 화면에서 열었을 때와 동일한 Step 구성과 Overlay가 표시된다.
    5. 전송 대상 영상이 Queue에 등록된다.
    6. Queue 상태가 Done으로 표시된다.
    7. 전송 대상 영상이 누락 없이 수신되고 주요 식별 Tag가 원본과 일치한다.

**이 TC 는 2026-08-20 에 사용자 지시로 개정본을 수정한 것이다.** 이전 원문은
"Apply preview position 을 켜고 Zoom/Pan/Rotation 이 수신 영상에 반영되는지"를
요구했는데, 수신 DICOM 의 어떤 값으로 "표시 위치 일치"를 판정할지 확정할 수 없어
막혀 있었다. 원본은 `..\Baseline\Checklist_개정본_20260820_WF15수정전.xlsx`.

실측한 흐름 (2026-08-20)
  Examined 에서 검사 선택 -> **2196**(Pre-send Preview, 사용자가 툴팁으로 지목)
  -> 범위 선택 대화상자 "Do you want to send all images of the selected study?"
     502 All Images / 501 Selected / 500 Cancel
  -> `Pre-send Preview` 창(1766x978). 창 제목이 **평문으로 읽힌다.**

판정 근거
  Step 3 : 창의 `203`(UIInstanceManager) 개수 = 표시된 영상 수. DB 의 전송 대상
           영상 수와 대조한다. Overlay 는 각 패널을 OCR 해 **WF_03 이 설정한 항목**
           (Dose kVp=115 / Dose mAs=118 을 Bottom 에 추가)이 실제로 찍히는지 본다.
           실측 화면에서 하단에 `28 kVp` / `32 mAs` 로 나온다.
  Step 4 : 같은 검사를 View 로 열어 같은 방식으로 읽고 **두 화면의 Overlay 를 대조**
           한다. 팝업만 보면 "원래 화면과 같은가"를 말할 수 없다.
  Step 5~7: `core/send_verify.py` 를 재사용한다 — Queue `State=Done`, 수신 객체 수,
           Patient ID / Study·Series·SOP Instance UID 대조.
"""

from __future__ import annotations

import os
import time

# 크롭/OCR/PIL 사용은 `core/image_overlay.py` 로 옮겼다(2026-08-21) — 여기서
# 다시 import 하면 쓰지 않는 이름이 남아 "이 모듈이 직접 OCR 한다"고 오해된다.
from core import dicom_settings as ds
from core import flows, image_overlay, screen
from core import send_verify as sv
from core import uitext
from core.result import FAIL, MANUAL, PASS, SKIP, TCResult
from tests.workflow02 import PATIENT_ID, _examined_search

# Overlay 크롭·OCR·판정은 `core/image_overlay.py` 로 옮겼다(2026-08-21).
# `TC_Basic_WorkFlow_03` Step 5 도 같은 판정을 하므로 구현을 하나로 둔다 —
# OCR 경로가 둘이면 한쪽만 고쳐 다른 쪽이 조용히 낡는다. 근거와 실측 경위는
# 그 모듈 docstring 에 있다.
OVERLAY_MARKERS = image_overlay.OVERLAY_MARKERS
OVERLAY_OCR_SCALES = image_overlay.OCR_SCALES
PID_PREFIX = image_overlay.PID_PREFIX
PATIENT_MARKERS = image_overlay.PATIENT_MARKERS
_norm = image_overlay.norm


def _study(ctx):
    row = ctx.db.one(
        "DATA",
        "SELECT TOP 1 s.[Key],s.StudyInstanceUID,p.PatientID,p.PatientBirthDate "
        "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid AND EXISTS (SELECT 1 FROM INSTANCE i "
        "WHERE i.StudyKey=s.[Key]) ORDER BY s.[Key] DESC", {"pid": PATIENT_ID})
    if not row:
        raise RuntimeError(f"검사를 찾지 못했습니다: {PATIENT_ID}")
    row["instances"] = ctx.db.query(
        "DATA",
        "SELECT [Key],InstanceType,ImageInstanceUID FROM INSTANCE "
        "WHERE StudyKey=@k ORDER BY [Key]", {"k": row["Key"]})
    # **전송 대상만** 기대값으로 삼는다. 사양서1 125쪽(SRS 06-30-30 문맥)
    # "3D 영상은 Recon 영상이 전송된다" 이므로 Raw/Syn 은 오지 않는다
    # (`core/send_verify.SENDABLE_3D_TYPES`). DB 의 전체 영상과 대조하면 정상 동작을
    # 누락으로 판정한다 — 2026-08-20 에 실제로 그렇게 틀렸다.
    keep = (sv.INSTANCE_2D,) + tuple(sv.SENDABLE_3D_TYPES)
    row["sendable"] = [i for i in row["instances"]
                       if int(i["InstanceType"]) in keep]
    return row


_panels = image_overlay.panels


def _read_overlay(control, path, tesseract_exe):
    return image_overlay.read_panel(control, path, tesseract_exe,
                                    scales=OVERLAY_OCR_SCALES)


def _overlay_hits(reads, study):
    return image_overlay.hits(reads, study)


def _open_preview(ui, scope="all"):
    """Pre-send Preview 를 열고 창을 돌려준다."""
    btn = uitext.visible(ui, flows.EXAMINED_PRE_SEND_PREVIEW)
    if not btn:
        raise RuntimeError(
            f"Pre-send Preview 버튼({flows.EXAMINED_PRE_SEND_PREVIEW})을 "
            "찾지 못했습니다.")
    before = {w.hwnd for w in ui.windows()}
    ui.click(btn[0], settle=2.5)

    # 범위 선택 대화상자. 버튼 ID 를 맹신하지 않고 좌우 순서와 함께 확인한다.
    pick = uitext.visible(ui, flows.PRE_SEND_SCOPE[scope])
    if not pick:
        raise RuntimeError(
            f"전송 범위 대화상자의 {scope}({flows.PRE_SEND_SCOPE[scope]}) 버튼을 "
            "찾지 못했습니다. Pre-send Preview 가 열리지 않았을 수 있습니다.")
    ui.click(pick[0], settle=6.0)

    end = time.time() + 15
    while time.time() < end:
        fresh = [w for w in ui.windows() if w.hwnd not in before
                 and w.rect[2] - w.rect[0] > 1200]
        if fresh and _panels(ui):
            return max(fresh, key=lambda w: (w.rect[2] - w.rect[0]) *
                       (w.rect[3] - w.rect[1]))
        time.sleep(1)
    raise RuntimeError("Pre-send Preview 창이 열리지 않았습니다.")


def run(ctx):
    r = TCResult("TC_Basic_WorkFlow_15", "Pre-send Preview 표시 및 전송")
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    evidence = os.path.join(ctx.evidence_root, "Flow", "15_PreSendPreview")
    ui = None
    try:
        study = _study(ctx)
        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError("Patient 화면이 준비되지 않았습니다")

        # 전제: Storage 서버와 Transfer Syntax. WF_04~06 과 같은 준비를 쓴다.
        # 이 함수가 스스로 Step 1 판정을 기록하고 **bool 을** 돌려준다.
        # **검사를 열기 전에** 불러야 한다(그 함수 주석 참고).
        if not sv.ensure_transfer_syntax(ctx, ui, r):
            raise RuntimeError(
                "Storage Transfer Syntax 를 선언된 값으로 맞추지 못했습니다. "
                "이 상태로 전송하면 conformant SCP 가 거절하므로 중단합니다.")
        # 전제 — Storage 설정의 Send Dose SR. 사양서1 125쪽 SRS 06-30-30 이
        # Dose SR 전송을 이 옵션에 건다. `SCPUseType=0`(설정 행)만 본다 — 전송
        # 작업 사본 행도 `Use=1` 이라 그것을 집으면 엉뚱한 행을 판정한다
        # (`core/dicom_settings.STORAGE_SCP_USE_TYPE` 주석 참고).
        storage_row = ctx.db.one(
            "CONFIGURATION",
            "SELECT TOP 1 [Key],Name,SendDoseSR,SCPUseType FROM DICOM_STORAGE "
            "WHERE [Use]=1 AND SCPUseType=@t ORDER BY [Key]",
            {"t": ds.STORAGE_SCP_USE_TYPE}) or {}
        send_dose_sr = int(storage_row.get("SendDoseSR") or 0) == 1
        r.add(1, "[전제] Storage 설정의 Send Dose SR", PASS if send_dose_sr else SKIP,
              expected="CONFIGURATION.DICOM_STORAGE.SendDoseSR = 1",
              actual=storage_row,
              note="사양서1 125쪽 SRS 06-30-30 — 'Send Dose SR 옵션이 활성화되어 "
                   "있을 때' 만 Dose SR 을 전송한다. 꺼져 있으면 Dose SR 판정을 "
                   "SKIP 하고 영상 전송만 본다(끄는 것도 정상 설정이다).")

        known = set(sv.queue_keys(ctx))
        sv.clear_received(ctx)

        # --- Step 1 -------------------------------------------------------
        rows = _examined_search(ui, PATIENT_ID)
        if not rows:
            raise RuntimeError("Examined 목록이 비어 있습니다")
        ui.click(rows[0], settle=1.5)
        r.assert_true(1, "Examined 창에서 대상 검사 선택", bool(rows),
                      expected={"PatientID": PATIENT_ID},
                      actual={"visible": len(rows), "study": study["Key"]},
                      note="Expected 1. 선택한 검사가 Preview 대상으로 지정된다.")

        # --- Step 2 -------------------------------------------------------
        window = _open_preview(ui, scope="all")
        panels = _panels(ui)
        path = os.path.join(evidence, "01_preview_window.png")
        screen.grab(window.rect, path=path)
        r.attach(path)
        r.assert_true(
            2, "Pre-send Preview 팝업 표시", bool(panels),
            expected={"창 크기": ">1200px", "영상 패널(203)": ">=1"},
            actual={"window": window.rect, "panels": [c.rect for c in panels]},
            note="Expected 2. Send Preview 팝업이 표시된다. Examined 툴바 2196 -> "
                 "범위 선택(All Images=502) 순서로 진입한다. 2196 은 사용자가 툴팁으로 "
                 "지목해 확정했다 — 아이콘만으로는 '검사 내 검색'으로 오인했다.")

        # --- Step 3 -------------------------------------------------------
        preview_reads = {}
        preview_hits = {}
        for index, panel in enumerate(panels, start=1):
            reads = _read_overlay(
                panel, os.path.join(evidence, f"02_preview_panel{index}.png"), tess)
            preview_reads[f"panel{index}"] = reads
            preview_hits[f"panel{index}"] = _overlay_hits(reads, study)
            r.attach(os.path.join(evidence, f"02_preview_panel{index}.png"))

        sendable = len(study["sendable"])
        # 환자 정보 Overlay 가 **모든 패널**에 있다는 것은 생년월일로 본다 — 숫자라
        # 어느 배율에서도 안정적으로 읽힌다.
        birth_ok = all(v["Birth Date"] for v in preview_hits.values())
        # 환자 ID 가 원본과 일치하는지는 **한 패널 이상**에서 확인한다. 3D-N 패널은
        # 이 글꼴에서 `FLOW` 가 `FLOY` 로 읽혀(배율 6/4/3 모두) 일치하지 않는다.
        # 접두사를 줄여 억지로 통과시키지 않고, 읽지 못한 패널을 아래에 남긴다.
        pid_panels = [k for k, v in preview_hits.items() if v["Patient ID"]]
        # 선량 Overlay 는 **영상 종류마다 표시 가능한 값이 다르다** —
        # 사양서1 233쪽 SRS 03-50-10 의 표: Dose kVp/mAs 는 2D O / 3D Raw O /
        # 3D Recon X / 3D Sync X. 라벨은 어느 종류에나 찍히고 값 자리에 `--` 가
        # 들어간다(실측 크롭). 그래서 라벨 유무가 아니라 **값이 찍혔는가**로
        # 갈라 사양표와 대조한다(`image_overlay.dose_state`).
        # 2026-08-27 이전에는 "3D 패널은 읽지 못했다" 며 MANUAL 로 남겼는데,
        # 저장된 크롭을 다시 OCR 하니 `--k¥p` / `-- mAs` 로 정확히 읽혔다.
        # 못 읽은 것이 아니라 **읽고도 값/미표시를 구분하지 않았던 것**이다.
        preview_dose = {k: image_overlay.dose_state(v)
                        for k, v in preview_reads.items()}
        dose_panels = [k for k, v in preview_dose.items()
                       if v["Dose kVp"] == "value" and v["Dose mAs"] == "value"]
        dash_panels = [k for k, v in preview_dose.items()
                       if v["Dose kVp"] == "dash" and v["Dose mAs"] == "dash"]
        unread_dose = [k for k, v in preview_dose.items()
                       if "none" in v.values()]
        # 전송 대상 중 사양상 선량 **값**이 표시되어야 하는 영상 수.
        # Preview 에 오르는 3D 는 Recon 뿐이므로(sv.SENDABLE_3D_TYPES) 보통 2D 1건.
        dose_expected_n = sum(
            1 for i in study["sendable"]
            if image_overlay.dose_expected(i["InstanceType"]))
        dose_dash_n = len(study["sendable"]) - dose_expected_n
        dose_spec_ok = (len(dose_panels) == dose_expected_n
                        and len(dash_panels) == dose_dash_n
                        and not unread_dose)
        r.assert_true(
            3, "각 Step 영상과 설정한 Overlay 항목 표시",
            bool(panels) and birth_ok and bool(pid_panels) and dose_spec_ok,
            expected={"영상 패널 수": f"전송 대상 {sendable}건에 대응 "
                                    f"(DB 전체 {len(study['instances'])}건)",
                      "생년월일": "모든 패널",
                      "환자 ID": "한 패널 이상에서 원본과 일치",
                      "선량 값이 찍힌 패널 수": dose_expected_n,
                      "선량이 `--` 인 패널 수": dose_dash_n},
            actual={"panels": len(panels), "overlay": preview_hits,
                    "birth_date_all_panels": birth_ok,
                    "patient_id_panels": pid_panels,
                    "dose_state": preview_dose,
                    "dose_value_panels": dose_panels,
                    "dose_dash_panels": dash_panels,
                    "dose_unreadable_panels": unread_dose,
                    "sendable_types": [sv.INSTANCE_NAMES.get(
                        int(i["InstanceType"]), i["InstanceType"])
                        for i in study["sendable"]],
                    "ocr": preview_reads},
            note="Expected 3. 검사의 각 Step 영상과 설정한 Overlay 항목이 표시된다. "
                 "Overlay 는 패널 위(환자정보)와 아래(선량)를 나눠 읽는다 — 한 곳만 "
                 "읽으면 Bottom 항목을 놓친다. Dose kVp(115)/Dose mAs(118)는 WF_03 이 "
                 "Bottom 에 추가한 항목이고, 환자 ID·생년월일은 DB 값과 대조한다. "
                 "선량은 **값이 찍힌 패널 수**를 사양표와 대조한다 — "
                 f"{image_overlay.DOSE_SPEC_CITE}. 전송 대상은 2D 와 3D Recon "
                 "이므로(사양서1 125쪽 SRS 06-30-30 '3D 영상은 Recon 영상이 "
                 "전송된다') 값이 찍혀야 하는 패널은 2D 쪽뿐이고, Recon 패널이 "
                 "`-- kVp`/`-- mAs` 로 나오는 것이 **사양대로의 정상**이다. "
                 "패널과 영상을 순서로 짝짓지 않고 **개수로** 대조한다 — 순서 "
                 "가정 없이 사양표를 검증하기 위해서다.")
        if unread_dose:
            r.add(3, f"선량 Overlay 를 읽지 못한 패널: {unread_dose}", FAIL,
                  expected="모든 패널에서 선량 항목이 값 또는 `--` 로 판독",
                  actual={k: preview_dose[k] for k in unread_dose},
                  note="라벨조차 읽히지 않았다. 크롭 원본이 "
                       "`Evidence/Flow/15_PreSendPreview/02_preview_panelN_bottom.png` "
                       "로 저장돼 있으니 **먼저 그 이미지를 눈으로 본다**(운영 지침: "
                       "OCR 실패는 캡처를 먼저 본다). 이미지에 문구가 온전하면 "
                       "전처리 문제이고, 실제로 없으면 Overlay 미표시다.",
                  stop=False)

        missing_pid = [k for k in preview_hits if k not in pid_panels]
        if missing_pid:
            r.blocked(
                3, f"환자 ID 를 읽지 못한 패널: {missing_pid}",
                "2026-08-21 에 전처리를 강화했는데도(명암 반전 / 임계값 이진화 150·110 / "
                "NEAREST 확대 x psm 6·7, `core/uitext.read_overlay_text`) 이 패널에서는 "
                "읽히지 않았다. 접두사를 줄여 통과시키지 않았다 — 판정을 약화시키는 "
                "것이기 때문이다. 같은 패널에서 **생년월일은 정확히 읽혔으므로 환자 정보 "
                "Overlay 자체는 표시되고 있다.** 크롭 원본이 "
                "`Evidence/Flow/15_PreSendPreview/02_preview_panelN_top.png` 로 저장돼 "
                "있으니 **먼저 그 이미지를 눈으로 보고** 글자가 실제로 어떻게 찍혔는지 "
                "확인한다(운영 지침: OCR 실패는 캡처를 먼저 본다). "
                "**해제 조건**: 크롭 이미지에서 문자열이 온전하면 전처리를 더 손보고, "
                "실제로 잘려 있거나 흐리면 Overlay 표시 자체를 제품 관점에서 확인한다. "
                "**이 실행으로 말할 수 없는 것**: 해당 패널의 환자 ID 문자열이 원본과 "
                "정확히 같은지 — 표시 자체는 확인했고 값 대조를 못 했다.")

        # --- Step 5: Send (Step 4 는 창을 닫은 뒤에 비교한다) ----------------
        send = uitext.visible(ui, flows.PRE_SEND_PREVIEW["send"])
        if not send:
            raise RuntimeError(
                f"Preview 의 Send({flows.PRE_SEND_PREVIEW['send']})를 "
                "찾지 못했습니다.")
        ui.click(send[0], settle=4.0)
        if ui.dialog():
            ui.dismiss_dialog(timeout=3)

        # --- Step 6~7: Queue 와 수신 --------------------------------------
        outcome = sv.wait_received_stable(ctx, wait=90)
        new_queue = [k for k in sv.queue_keys(ctx) if k not in known]

        # 수신이 안정됐다고 Queue 가 Done 이 된 것은 아니다. State 가 Done 이 될
        # 때까지 따로 기다린다 — 2026-08-20 에 State=3 하나가 남아 FAIL 했다.
        def queue_rows():
            return [q for q in ctx.db.query(
                "DATA", "SELECT [Key],State,DataType,InstanceUID,ClassUID "
                        "FROM DICOM_STORAGE_QUEUE ORDER BY [Key] DESC")
                    if q["Key"] in new_queue]

        def image_rows():
            # All Images 를 고르면 Dose SR 도 Queue 에 들어간다. 성격이 달라
            # 함께 판정하면 안 된다(`sv.is_dose_sr_row`).
            return [q for q in queue_rows() if not sv.is_dose_sr_row(q)]

        def dose_rows():
            return [q for q in queue_rows() if sv.is_dose_sr_row(q)]

        def all_done(rows):
            return bool(rows) and all(int(q["State"]) == sv.QUEUE_STATE_DONE
                                      for q in rows)

        # 영상뿐 아니라 **Dose SR 행까지** Done 을 기다린다. 사양서1 288쪽
        # SRS 03-50-250 이 이 경로(Examined + Send Preview + 모든 영상)에서
        # Dose SR 전송을 요구하므로, 영상만 기다리고 판정하면 아직 진행 중인
        # Dose SR 을 "실패" 로 잘못 읽는다.
        end = time.time() + 90
        while time.time() < end and not (all_done(image_rows())
                                         and all_done(dose_rows())):
            time.sleep(2)
        identity = sv.db_identity(ctx, PATIENT_ID)
        received = sv.received(ctx) or []

        r.assert_true(
            5, "전송 대상 영상이 Queue에 등록", bool(new_queue),
            expected="DICOM_STORAGE_QUEUE 신규 행",
            actual={"new_queue": new_queue},
            note="Expected 5. Preview 의 Send(1148)는 Examine 화면의 tool_send 와 "
                 "같은 ID다.")

        images = image_rows()
        dose_sr = dose_rows()

        # --- Step 5-b: Dose SR 이 Queue 에 등록되었는가 (사양) ---------------
        #
        # 사양서1 **288쪽 SRS 03-50-250**:
        #   "Dose SR 은 Examine/View 모드에서 Send Preview 버튼을 클릭했을 경우
        #    전송되지 않는다. (Examine/View 모드의 Send 버튼 클릭 동작과 사양 동일)
        #    **Examined 모드에서 Send Preview 버튼을 클릭했을 경우 모든 영상을
        #    선택했을 경우에만 Dose SR 을 전송한다.**"
        # 이 TC 는 정확히 그 경로다 — Examined 목록에서 검사를 고르고(Step 1),
        # Pre-send Preview 를 All Images(502)로 열어(Step 2) Send 한다(Step 5).
        # 그러므로 Dose SR 이 오지 않으면 **전제 미충족이 아니라 사양 위반**이다.
        # 2026-08-27 이전에는 Demo 촬영을 이유로 MANUAL 로 남겼는데, 같은 날
        # `WF_06`(Examined Send 경로)이 RDSR 을 실제로 받아 그 전제가 틀렸음이
        # 드러났다 — Demo 촬영에서도 RDSR 은 생성된다.
        if send_dose_sr:
            r.assert_true(
                5, "Dose SR 이 Queue 에 등록(사양: Examined + Send Preview + 모든 영상)",
                bool(dose_sr),
                expected="DICOM_STORAGE_QUEUE 에 DataType=1(Dose SR) 행 1건 이상",
                actual={"dose_sr_rows": dose_sr, "image_rows": len(images)},
                note="사양서1 288쪽 SRS 03-50-250 — \"Examined 모드에서 Send Preview "
                     "버튼을 클릭했을 경우 모든 영상을 선택했을 경우에만 Dose SR 을 "
                     "전송한다\". 같은 사양이 Examine/View 모드의 Send Preview 는 "
                     "전송하지 않는다고 못박으므로, **경로를 지킨 이 실행에서는 "
                     "전송되는 것이 정상**이다. Queue 의 `ClassUID` 는 제품이 채우지 "
                     "않아(실측 전부 None) 구분자로 쓸 수 없고 `DataType`(0=영상, "
                     "1=Dose SR)으로 가른다(core/send_verify.is_dose_sr_row).")
        else:
            r.add(5, "Dose SR 이 Queue 에 등록", SKIP,
                  expected="Storage 설정의 Send Dose SR 활성화 상태에서만 판정",
                  actual={"SendDoseSR": storage_row.get("SendDoseSR")},
                  note="사양서1 125쪽 SRS 06-30-30 은 Dose SR 전송을 'Send Dose SR "
                       "옵션이 활성화되어 있을 때' 로 한정한다. 꺼져 있으면 오지 않는 "
                       "것이 정상이라 판정하지 않는다.")

        r.assert_true(
            6, "영상 Queue 상태 Done",
            bool(images) and all(int(q["State"]) == sv.QUEUE_STATE_DONE
                                 for q in images),
            expected=f"영상 행 전부 State={sv.QUEUE_STATE_DONE}",
            actual={"images": images, "dose_sr": dose_sr},
            note="Expected 6. Queue 상태가 Done으로 표시된다. All Images 를 고르면 "
                 "Dose SR 도 Queue 에 들어가므로 영상 행만 대조한다 — 구분은 "
                 "DataType / InstanceUID 로 한다"
                 "(core/send_verify.is_dose_sr_row). Dose SR 행은 바로 아래에서 "
                 "따로 판정한다.")
        if dose_sr:
            r.assert_true(
                6, "Dose SR Queue 상태 Done",
                all(int(q["State"]) == sv.QUEUE_STATE_DONE for q in dose_sr),
                expected=f"Dose SR 행 전부 State={sv.QUEUE_STATE_DONE}",
                actual={"dose_sr": dose_sr},
                note="Expected 6 을 Dose SR 행에도 적용한다. 사양(288쪽 SRS "
                     "03-50-250)이 이 경로에서 Dose SR 전송을 요구하므로 등록만이 "
                     "아니라 **완료까지** 본다.")

        uids = {str(o.get("SOPInstanceUID")) for o in received
                if o.get("SOPInstanceUID")}
        expected_uids = {str(i["ImageInstanceUID"]) for i in study["sendable"]}
        # 수신 객체 중 RDSR 은 영상이 아니다 — 제품이 검사 단위로 만드는 보고서라
        # `DATA.INSTANCE` 에 행이 없고, 사양서1 2163행이 "Dose SR 에서 사용 시
        # 내부적으로 영상의 Instance UID 마지막에 '.1.1' 을 붙인다" 고 한다.
        # 영상 UID 대조에 섞으면 "DB 에 없는 UID" 로 잡혀 정상이 FAIL 이 된다.
        rdsr_objects = [o for o in received
                        if str(o.get("SOPClassUID") or "") == sv.SOP_CLASS_RDSR]
        image_objects = [o for o in received if o not in rdsr_objects]
        image_uids = {str(o.get("SOPInstanceUID")) for o in image_objects
                      if o.get("SOPInstanceUID")}
        missing = expected_uids - image_uids
        r.assert_true(
            7, "수신 객체의 식별 Tag가 원본과 일치",
            bool(image_objects) and not missing,
            expected={"SOP Instance UID(전송 대상만)": sorted(expected_uids)},
            actual={"received": len(received), "received_uids": sorted(uids),
                    "image_objects": len(image_objects),
                    "rdsr_objects": len(rdsr_objects),
                    "missing": sorted(missing), "stable": outcome,
                    "identity": identity},
            note="Expected 7. 전송 대상 영상이 누락 없이 수신되고 주요 식별 Tag가 "
                 "원본과 일치한다. 3D 는 사양에 따라 Recon 만 전송되므로 "
                 "(core/send_verify.SENDABLE_3D_TYPES) 누락 판정은 DB 의 전체 영상이 "
                 "아니라 전송 대상과 대조해야 한다 — 아래 note 참고. RDSR 은 영상이 "
                 "아니라 검사 단위 보고서라 이 대조에서 빼고 바로 아래에서 따로 "
                 "판정한다.")

        # --- Step 7-b: 수신한 RDSR 의 식별 Tag ------------------------------
        if send_dose_sr:
            bad_rdsr = [o for o in rdsr_objects
                        if o.get("PatientID") != PATIENT_ID
                        or o.get("StudyInstanceUID") not in identity["study_uids"]]
            r.assert_true(
                7, "수신한 Dose SR(RDSR)의 Patient ID·Study Instance UID 일치",
                bool(rdsr_objects) and not bad_rdsr,
                expected={"SOP Class UID": sv.SOP_CLASS_RDSR,
                          "PatientID": PATIENT_ID,
                          "StudyInstanceUID": sorted(identity["study_uids"])},
                actual={"rdsr": [{k: o.get(k) for k in
                                  ("PatientID", "StudyInstanceUID",
                                   "SOPInstanceUID")} for o in rdsr_objects],
                        "mismatch": bad_rdsr},
                note="사양서1 288쪽 SRS 03-50-250 이 이 경로의 Dose SR 전송을 "
                     "요구하므로 Queue 등록·완료에 이어 **실제 수신 객체**까지 "
                     "확인한다. SOP Class UID 는 개정본 WF_06 Test Data 가 명시한 "
                     f"{sv.SOP_CLASS_RDSR}(X-Ray Radiation Dose SR Storage, DICOM "
                     "Conformance Statement V1.3W1 선언)이다.")

        # --- Step 4: View 화면과 대조 ---------------------------------------
        # 2026-08-21 구현. 그전에는 "View 화면 패널을 크롭·OCR 하는 헬퍼가 없다"는
        # 이유로 MANUAL 이었다. Preview 창의 패널과 **같은 컨트롤 ID(203)** 를 View
        # 화면도 쓰기 때문에 `_panels()` 를 그대로 재사용할 수 있다(실측 확인).
        close = uitext.visible(ui, flows.PRE_SEND_PREVIEW["close"])
        if close:
            ui.click(close[0], settle=3.0)

        view_hits, view_reads, view_panels = {}, {}, []
        view_opened = False
        try:
            rows = _examined_search(ui, PATIENT_ID)
            if not rows:
                raise RuntimeError(f"Examined 목록이 비어 있습니다: {PATIENT_ID}")
            ui.click(rows[0], settle=1.2)
            view_btn = uitext.visible(ui, flows.EXAMINED_VIEW_BUTTON)
            if not view_btn:
                raise RuntimeError(
                    f"Examined 의 View 버튼({flows.EXAMINED_VIEW_BUTTON})을 "
                    "찾지 못했습니다.")
            ui.click(view_btn[0], settle=8.0)
            view_opened = True
            view_panels = _panels(ui)
            for index, panel in enumerate(view_panels, 1):
                path = os.path.join(evidence, f"04_view_panel{index}.png")
                reads = _read_overlay(panel, path, tess)
                view_reads[f"panel{index}"] = reads
                view_hits[f"panel{index}"] = _overlay_hits(reads, study)
                r.attach(path)
        except Exception as exc:                       # noqa: BLE001
            r.manual(
                4, "View 화면과 동일한 Step 구성·Overlay 비교",
                f"View 화면을 열지 못해 대조하지 못했다({type(exc).__name__}: {exc}). "
                "**해제 조건**: Examined 조회와 View 버튼(2182) 경로를 확인한다. "
                "**이 실행으로 말할 수 없는 것**: 두 화면의 Overlay 가 같은지.")
        else:
            # 같은 항목이 **양쪽 모두에서** 관찰되는지로 판정한다. 픽셀 비교가 아니라
            # 항목 관찰 비교다 — 두 화면은 창 크기·Layout 이 달라 픽셀이 같을 수 없고,
            # Expected 4 가 요구하는 것은 "동일한 Step 구성과 Overlay" 이기 때문이다.
            labels = list(OVERLAY_MARKERS) + list(PATIENT_MARKERS)
            preview_any = {lab: any(v.get(lab) for v in preview_hits.values())
                           for lab in labels}
            view_any = {lab: any(v.get(lab) for v in view_hits.values())
                        for lab in labels}
            same_labels = [lab for lab in labels
                           if preview_any[lab] == view_any[lab]]
            diff_labels = [lab for lab in labels
                           if preview_any[lab] != view_any[lab]]
            # 선량은 라벨 유무가 아니라 **값이 찍혔는가**까지 본다. 두 화면 모두
            # 같은 영상을 보여 주므로 값이 찍힌 패널 수도 같아야 한다 — 단
            # View 화면은 3D 종류 전환(2122/2123/2124)이 있어 동시 표시 구성이
            # 다를 수 있으므로(아래 패널 수 판정 주석 참고) 개수가 다르면
            # 판정하지 않고 관측으로 남긴다.
            view_dose = {k: image_overlay.dose_state(v)
                         for k, v in view_reads.items()}
            view_value_panels = [k for k, v in view_dose.items()
                                 if v["Dose kVp"] == "value"
                                 and v["Dose mAs"] == "value"]
            dose_same = (len(view_panels) == len(panels)
                         and len(view_value_panels) == len(dose_panels))
            r.assert_true(
                4, "View 화면에 Preview 와 동일한 Overlay 항목 표시",
                bool(view_panels) and not diff_labels,
                expected={"Overlay 항목 관찰 결과": labels},
                actual={"일치 항목": same_labels,
                        "불일치 항목": diff_labels,
                        "preview": preview_any, "view": view_any,
                        "preview 선량": preview_dose, "view 선량": view_dose,
                        "선량 값 패널 수 일치": dose_same},
                note="Expected 4. **픽셀 비교가 아니라 항목 관찰 비교**다 — 두 화면은 "
                     "창 크기와 Layout 이 달라 픽셀이 같을 수 없고, Expected 4 가 "
                     "요구하는 것은 '동일한 Step 구성과 Overlay' 다. Preview 창과 "
                     "View 화면이 같은 패널 컨트롤(203)을 쓰므로 같은 크롭·OCR "
                     "경로로 읽었다. 읽지 못한 항목이 양쪽 모두 없으면 '둘 다 안 "
                     "읽혔다'로 일치 처리되므로, 항목별 관찰 결과를 actual 에 그대로 "
                     "남겨 사람이 확인할 수 있게 한다.")
            # 패널 수는 **판정하지 않고 관측만 기록한다.** View 화면은 3D 영상 종류
            # 전환 버튼(2122 Raw / 2123 Recon / 2124 Syn)이 있어 한 번에 보여주는
            # 구성이 Preview(전송 대상)와 설계상 다를 수 있다. 그 차이가 정상인지
            # 문서로 확인되지 않았으므로 다르다는 것만으로 FAIL 하지 않는다 —
            # 확인되지 않은 가정으로 FAIL 을 만들지 않는다는 원칙이다.
            same_count = len(view_panels) == len(panels)
            r.add(4, "Preview / View 의 영상 패널 수",
                  PASS if same_count else MANUAL,
                  expected=f"참고 정보 (Preview {len(panels)}개)",
                  actual={"preview": len(panels), "view": len(view_panels)},
                  note="" if same_count else
                       "두 화면의 패널 수가 다르다. View 화면은 3D 영상 종류 전환"
                       "(2122 Raw / 2123 Recon / 2124 Syn)이 있어 한 번에 보여주는 "
                       "구성이 Preview(전송 대상)와 설계상 다를 수 있고, 그것이 "
                       "정상인지는 문서로 확인되지 않았다. **해제 조건**: 사양에서 "
                       "View 화면의 동시 표시 범위를 확인하거나, 종류 전환 버튼으로 "
                       "Preview 와 같은 범위를 맞춘 뒤 비교한다. "
                       "**이 실행으로 말할 수 없는 것**: 이 차이가 결함인지 여부.")
        finally:
            if view_opened:
                try:
                    vclose = uitext.visible(ui, flows.VIEW_CLOSE)
                    if vclose:
                        ui.click(vclose[0], settle=3.0)
                    if ui.dialog():
                        ui.dismiss_dialog(timeout=3)
                except Exception:                      # noqa: BLE001
                    pass
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_15 실행", exc)
    return r
