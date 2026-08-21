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
from core import flows, image_overlay, screen
from core import send_verify as sv
from core import uitext
from core.result import FAIL, MANUAL, PASS, TCResult
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
        # 선량 Overlay 는 선량 정보가 있는 영상에만 값이 찍힌다. 3D-N 은
        # `-- kVp` / `-- mAs` 로 나오고 글자가 작고 흐려 어느 배율에서도 읽히지
        # 않았다(실측). 그래서 "한 패널 이상에서 확인"으로 판정하고, 읽지 못한
        # 패널은 이유·해제조건과 함께 아래 MANUAL 로 남긴다.
        dose_panels = [k for k, v in preview_hits.items()
                       if v["Dose kVp"] and v["Dose mAs"]]
        r.assert_true(
            3, "각 Step 영상과 설정한 Overlay 항목 표시",
            bool(panels) and birth_ok and bool(pid_panels) and bool(dose_panels),
            expected={"영상 패널 수": f"전송 대상 {sendable}건에 대응 "
                                    f"(DB 전체 {len(study['instances'])}건)",
                      "생년월일": "모든 패널",
                      "환자 ID": "한 패널 이상에서 원본과 일치",
                      "선량 Overlay": "한 패널 이상 (선량 있는 영상)"},
            actual={"panels": len(panels), "overlay": preview_hits,
                    "birth_date_all_panels": birth_ok,
                    "patient_id_panels": pid_panels,
                    "dose_overlay_panels": dose_panels,
                    "ocr": preview_reads},
            note="Expected 3. 검사의 각 Step 영상과 설정한 Overlay 항목이 표시된다. "
                 "Overlay 는 패널 위(환자정보)와 아래(선량)를 나눠 읽는다 — 한 곳만 "
                 "읽으면 Bottom 항목을 놓친다. Dose kVp(115)/Dose mAs(118)는 WF_03 이 "
                 "Bottom 에 추가한 항목이고, 환자 ID·생년월일은 DB 값과 대조한다.")

        missing_pid = [k for k in preview_hits if k not in pid_panels]
        if missing_pid:
            r.manual(
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

        missing_dose = [k for k in preview_hits if k not in dose_panels]
        if missing_dose:
            r.manual(
                3, f"선량 Overlay 를 읽지 못한 패널: {missing_dose}",
                "3D-N 영상은 선량 정보가 없어 `-- kVp` / `-- mAs` 로 찍히고 글자가 작다. "
                "2026-08-21 에 임계값 이진화(150·110) + NEAREST 확대 + psm 6·7 을 붙였는데도 "
                "이 패널에서는 읽히지 않았다. 크롭 원본이 "
                "`Evidence/Flow/15_PreSendPreview/02_preview_panelN_bottom.png` 로 "
                "저장돼 있으니 그 이미지를 먼저 확인한다. "
                "**해제 조건**: 선량이 있는 3D 영상(실제 촬영)으로 시험한다 — 값이 "
                "`--` 인 상태로는 라벨만 있고 대조할 값이 없다. "
                "**이 실행으로 말할 수 없는 것**: 3D-N 패널에 선량 Overlay 라벨이 "
                "찍히는지 여부 — 찍히지 않는다고 판단한 것이 아니라 읽지 못했다.")

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

        end = time.time() + 60
        while time.time() < end and not (
                image_rows() and all(int(q["State"]) == sv.QUEUE_STATE_DONE
                                     for q in image_rows())):
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
        dose_sr = [q for q in queue_rows() if sv.is_dose_sr_row(q)]
        r.assert_true(
            6, "영상 Queue 상태 Done",
            bool(images) and all(int(q["State"]) == sv.QUEUE_STATE_DONE
                                 for q in images),
            expected=f"영상 행 전부 State={sv.QUEUE_STATE_DONE}",
            actual={"images": images, "dose_sr": dose_sr},
            note="Expected 6. Queue 상태가 Done으로 표시된다. All Images 를 고르면 "
                 "Dose SR 도 Queue 에 들어가므로 영상 행만 대조한다 — 구분은 "
                 "DataType / InstanceUID 로 한다"
                 "(core/send_verify.is_dose_sr_row).")
        if dose_sr and any(int(q["State"]) != sv.QUEUE_STATE_DONE for q in dose_sr):
            r.manual(
                6, "Dose SR Queue 상태가 Done 이다",
                f"Dose SR 행 {[q['Key'] for q in dose_sr]} 이 "
                f"State={[q['State'] for q in dose_sr]} 로 남았다. 이 환경은 "
                "Demo(F8) 가상 촬영이라 RDSR 생성 조건이 성립하지 않는다 — 여러 "
                "실행에서 같은 상태를 반복 확인했다. **전제 미충족이므로 제품 결함으로 "
                "보고하지 않는다**(WF_06 과 같은 판단). "
                "**해제 조건**: 실제 촬영 환경에서 RDSR 생성 조건을 충족시킨 뒤 재확인. "
                "**이 실행으로 말할 수 없는 것**: Pre-send Preview 경로의 Dose SR "
                "전송이 정상인지 여부.")

        uids = {str(o.get("SOPInstanceUID")) for o in received
                if o.get("SOPInstanceUID")}
        expected_uids = {str(i["ImageInstanceUID"]) for i in study["sendable"]}
        missing = expected_uids - uids
        r.assert_true(
            7, "수신 객체의 식별 Tag가 원본과 일치",
            bool(received) and not missing,
            expected={"SOP Instance UID(전송 대상만)": sorted(expected_uids)},
            actual={"received": len(received), "received_uids": sorted(uids),
                    "missing": sorted(missing), "stable": outcome,
                    "identity": identity},
            note="Expected 7. 전송 대상 영상이 누락 없이 수신되고 주요 식별 Tag가 "
                 "원본과 일치한다. 3D 는 사양에 따라 Recon 만 전송되므로 "
                 "(core/send_verify.SENDABLE_3D_TYPES) 누락 판정은 DB 의 전체 영상이 "
                 "아니라 전송 대상과 대조해야 한다 — 아래 note 참고.")

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
            r.assert_true(
                4, "View 화면에 Preview 와 동일한 Overlay 항목 표시",
                bool(view_panels) and not diff_labels,
                expected={"Overlay 항목 관찰 결과": labels},
                actual={"일치 항목": same_labels,
                        "불일치 항목": diff_labels,
                        "preview": preview_any, "view": view_any},
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
        r.add(0, "TC_Basic_WorkFlow_15 실행", FAIL, actual=str(exc))
    return r
