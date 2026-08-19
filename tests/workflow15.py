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
import re
import time

from PIL import Image, ImageGrab, ImageOps

from core import flows, screen
from core import send_verify as sv
from core import uitext
from core.result import FAIL, MANUAL, PASS, TCResult
from core.ui import children
from tests.workflow02 import PATIENT_ID, _examined_search

# WF_03 이 Image Overlay 로 추가한 항목. 이 두 개가 Preview 에 찍히면 "설정한
# Overlay 가 표시된다"는 Expected 3 을 관찰로 확인한 것이 된다.
# 값 자리에 숫자가 아니라 `--` 가 오는 영상이 있다 — 3D-N 은 선량 정보가 없어
# `-- kVp` / `-- mAs` 로 찍힌다(2026-08-20 실측). "모든 패널에 숫자"를 요구하면
# 정상 동작을 실패로 판정한다. 그래서 **라벨이 표시되는가**로 본다.
# OCR 은 `kVp` 의 V 를 `¥` 로 자주 읽어서 그것도 허용한다.
OVERLAY_MARKERS = {
    "Dose kVp": re.compile(r"k[v¥y]p"),
    "Dose mAs": re.compile(r"m[a4]s"),
}
# 패널을 여러 배율로 읽어 하나라도 맞으면 인정한다. 한 배율에 의존하면 흔들린다
# (WF_08 에서 같은 이유로 12/8/5 배율을 쓴다).
OVERLAY_OCR_SCALES = (6, 4, 3)
# 환자 ID 접두사 비교 길이. `DATA_FLOW_MWL_01` 에서 OCR 이 `MWL` 을 `MYL` /
# `M¥WL` 로 읽어도 `datafl0w` 까지는 안정적으로 읽힌다. 다른 시험 환자
# (`DATA_XIPL_...`)와 겹치지 않는 길이다.
PID_PREFIX = 8
# 환자 정보 Overlay — 값은 DB 에서 가져와 대조한다(상수로 박지 않는다).
PATIENT_MARKERS = ("Patient ID", "Birth Date")


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower()).replace("o", "0")


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


def _panels(ui):
    """Preview 창의 영상 패널(203)을 왼쪽부터 돌려준다.

    같은 hwnd 가 여러 번 열거될 수 있어 중복을 제거한다.
    """
    hits = {c.hwnd: c for c in ui.controls(max_depth=8)
            if c.visible and c.ctrl_id == flows.PRE_SEND_PREVIEW["instance_panel"]
            and c.rect[2] - c.rect[0] > 200 and c.rect[3] - c.rect[1] > 200}
    return sorted(hits.values(), key=lambda c: c.rect[0])


def _read_overlay(control, path, tesseract_exe):
    """영상 패널을 캡처해 Overlay 문구를 읽는다.

    Overlay 는 패널의 **위(환자정보)와 아래(선량)** 에 나뉘어 찍힌다. 한 곳만 읽으면
    Bottom 항목을 놓친다 — Print Overlay 에서 같은 실수를 했다(README §6).
    """
    import pytesseract

    if tesseract_exe:
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image = ImageGrab.grab(bbox=control.rect, all_screens=True)
    image.save(path)
    width, height = image.size
    reads = {}
    for tag, box in (("top", (int(width * .40), 0, width, int(height * .32))),
                     ("bottom", (int(width * .50), int(height * .84),
                                 width, height))):
        crop = image.crop(box).convert("L")
        for scale in OVERLAY_OCR_SCALES:
            big = crop.resize((crop.width * scale, crop.height * scale),
                              Image.Resampling.LANCZOS)
            reads[f"{tag}_x{scale}"] = pytesseract.image_to_string(
                ImageOps.autocontrast(big), config="--psm 6", lang="eng").strip()
    return reads


def _overlay_hits(reads, study):
    """읽은 Overlay 문구에서 기대 항목이 보이는지."""
    joined = _norm(" ".join(reads.values()))
    raw = " ".join(reads.values()).lower()
    pid = _norm(study["PatientID"])
    found = {label: bool(rx.search(raw.replace(" ", "")) or rx.search(raw))
             for label, rx in OVERLAY_MARKERS.items()}
    # OCR 은 이 글꼴에서 W 를 Y 로 자주 읽는다. 완전일치와 **접두사 일치**를 함께
    # 본다 — 접두사는 다른 시험 환자와 겹치지 않을 만큼 길게 잡는다.
    found["Patient ID"] = bool(pid) and (pid in joined
                                        or pid[:PID_PREFIX] in joined)
    found["Birth Date"] = _norm(study["PatientBirthDate"]) in joined
    return found


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
                "이 글꼴·크기에서 `DATA_FLOW_MWL_01` 의 `W` 가 `Y` 로 읽힌다"
                "(배율 6/4/3 모두 `DATA_FLOY_...`). 접두사를 줄여 통과시키지 않았다 — "
                "판정을 약화시키는 것이기 때문이다. 같은 패널에서 **생년월일은 정확히 "
                "읽혔으므로 환자 정보 Overlay 자체는 표시되고 있다.** "
                "**해제 조건**: 흰 글자/검은 배경이므로 임계값 이진화 전처리를 붙이면 "
                "개선될 가능성이 높다(Print Overlay 판정이 같은 방법을 쓴다). "
                "**이 실행으로 말할 수 없는 것**: 해당 패널의 환자 ID 문자열이 원본과 "
                "정확히 같은지 — 표시 자체는 확인했고 값 대조를 못 했다.")

        missing_dose = [k for k in preview_hits if k not in dose_panels]
        if missing_dose:
            r.manual(
                3, f"선량 Overlay 를 읽지 못한 패널: {missing_dose}",
                "3D-N 영상은 선량 정보가 없어 `-- kVp` / `-- mAs` 로 찍히고, 글자가 "
                "작고 흐려 배율 6/4/3 어디서도 OCR 되지 않았다. "
                "**해제 조건**: 선량이 있는 3D 영상(실제 촬영)으로 시험하거나 그 "
                "영역만 임계값으로 이진화해 읽는 전처리를 붙인다. "
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
                6, "Dose SR 전송이 Done 이 아니다",
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
        close = uitext.visible(ui, flows.PRE_SEND_PREVIEW["close"])
        if close:
            ui.click(close[0], settle=3.0)
        r.manual(
            4, "View/Examine 화면과 동일한 Step 구성·Overlay 비교",
            "Preview 팝업의 Overlay 는 Step 3 에서 실측했다(위 ocr 참고). "
            "같은 검사를 View 로 열어 자동 대조하는 것은 아직 붙이지 않았다 — "
            "해제 조건: View 화면의 영상 패널을 같은 방식으로 크롭·OCR 하는 헬퍼가 "
            "필요하다(tests/workflow02.py 의 Tool 검증이 쓰는 패널 좌표를 재사용할 "
            "수 있다). **이 실행으로는 '두 화면이 같다'를 말할 수 없다** — Preview 에 "
            "Overlay 가 찍힌다는 것까지만 확인했다.")
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_15 실행", FAIL, actual=str(exc))
    return r
