# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_11 — Image Reject 및 Restore.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.

체크리스트 원문 (변경 금지)
  Precondition
    DATA_FLOW_MWL_01에 2개 이상의 영상이 존재한다.
    Reject/Retake 설정이 완료되어 있다.
  Step
    1. Examined 창에서 DATA_FLOW_MWL_01 검사를 연다.
    2. IMG_FLOW_2D_01만 선택한다.
    3. Reject를 실행한다.
    4. Reject된 영상 목록에서 동일 영상을 확인한다.
    5. 동일 영상을 선택하고 Restore를 실행한다.
    6. 원래 검사에서 영상을 확인한다.
  Expected Result
    1. 올바른 검사가 열린다.
    2. 대상 영상만 선택된다.
    3. 선택한 영상만 Reject 상태가 된다.
    4. 동일 Patient/Study/Image가 Reject 목록에 표시된다.
    5. 선택한 영상이 Restore된다.
    6. 영상이 원래 검사에 다시 표시되고 다른 영상 상태는 변경되지 않는다.

실측한 흐름 (2026-08-20) — 사용자가 위치를 알려 주고 툴팁으로 확정했다
  Examined 에서 검사 선택 -> View(2182) -> 우측 Procedure 패널 썸네일에서 대상 선택
  -> **1168 "Reject Image"** -> 사유 팝업(701~707) 에서 사유 선택
  -> 영상에 빨간 `REJECTED` 스탬프, 썸네일에 되돌리기 화살표(↺)
  -> ↺ 클릭 -> "Do you want to restore the images?" -> 좌 Yes(501)

  진입점을 찾는 데 세 곳이 헛다리였다. Examined 툴바 16개에는 없고, 검사 카드
  우클릭은 메뉴가 뜨지 않고, View 화면 하단 2122/2123/2124 는 Raw/Recon/Syn 이다.
  그리고 `flows.EXAMINE` 에 "procedure_delete: 2207" 로 적혀 있던 것은 실제로
  **Left Implant** 였다 — 아이콘 추정 오류의 세 번째 사례.

판정
  `tests/dataflow.py` 의 `workflow_11_mid_evaluate` / `workflow_11_evaluate` 가
  이미 pre/mid/post DB 스냅샷 대조 로직을 갖고 있다. 여기서는 **UI 드라이버를
  붙이고** 그 판정을 재사용한다. 그 모듈은 지금까지 `run.py` 에 연결돼 있지 않아
  한 번도 실행된 적이 없었다.

  Reject 는 `INSTANCE_GROUP` 단위로 기록된다(실측):
    StatusRejected 0 -> 1 / RejectType / RejectReason / RejectUserID /
    RejectDate / RejectTime
"""

from __future__ import annotations

import os
import time

from core import flows, screen, snapshot, uitext
from core.result import FAIL, MANUAL, PASS, TCResult
from tests.dataflow import workflow_11_evaluate, workflow_11_mid_evaluate
from tests.workflow02 import PATIENT_ID, _examined_search

REASON = "artifacts"        # 사용자: "사유는 아무거나 무관하다"


def _rejected_keys(db):
    return {int(r["Key"]) for r in db.query(
        "DATA", "SELECT [Key],StatusRejected FROM INSTANCE_GROUP")
        if int(r["StatusRejected"] or 0) == 1}


def _open_view(ui):
    """Examined 에서 대상 검사를 열어 View 모드로 들어간다."""
    rows = _examined_search(ui, PATIENT_ID)
    if not rows:
        raise RuntimeError(f"Examined 목록이 비어 있습니다: {PATIENT_ID}")
    ui.click(rows[0], settle=1.2)
    view = uitext.visible(ui, flows.EXAMINED_VIEW_BUTTON)
    if not view:
        raise RuntimeError(
            f"Examined 의 View 버튼({flows.EXAMINED_VIEW_BUTTON})을 찾지 못했습니다.")
    ui.click(view[0], settle=8.0)
    return rows


def _thumbnails(ui):
    return uitext.list_rows(ui, flows.THUMBNAIL_LIST,
                            item_text=flows.THUMBNAIL_ITEM)


def _pick_reason(ui, reason, tesseract_exe):
    """사유 팝업에서 사유를 고른다. **문구를 OCR 로 확인**한 뒤 누른다.

    순서로 고르면 사유가 늘거나 순서가 바뀔 때 조용히 다른 것을 고른다.
    """
    ctrl_id = flows.REJECT_REASONS[reason]
    hits = uitext.visible(ui, ctrl_id)
    if not hits:
        raise RuntimeError(
            f"Reject 사유 팝업({ctrl_id})을 찾지 못했습니다. "
            "Reject 버튼이 눌리지 않았을 수 있습니다.")
    text = uitext.ocr(hits[0], tesseract_exe)
    if uitext.norm(reason.split("_")[0]) not in uitext.norm(text):
        raise RuntimeError(
            f"사유 {ctrl_id} 가 {reason!r} 이 아닙니다(읽은 값 {text!r}). "
            "엉뚱한 사유를 고르지 않도록 중단합니다.")
    ui.click(hits[0], settle=3.0)
    return {"reason": reason, "ctrl_id": ctrl_id, "ocr": text}


def _confirm_restore(ui, tesseract_exe=None, timeout=8):
    """Restore 확인 팝업에서 **Yes** 를 누른다.

    문구는 "Do you want to restore the images?" 이고 좌 Yes(501) / 우 No(500) 다.
    `ui.dismiss_dialog()` 는 No 를 눌러 원복이 되지 않았다(2026-08-20 실측) —
    계정 삭제 팝업과 같은 함정이다. 좌우 순서와 ID 를 함께 확인한다.
    """
    from core.ui import children

    end = time.time() + timeout
    dlg = None
    while time.time() < end:
        dlg = ui.dialog()
        if dlg:
            break
        time.sleep(.4)
    if not dlg:
        return None
    message = ""
    try:
        message = flows.read_dialog_message(ui, dlg, tesseract_exe) or ""
    except Exception:
        message = ""
    buttons = sorted(
        [c for c in children(dlg.hwnd, 6) if c.visible
         and 60 < c.rect[2] - c.rect[0] < 220 and 30 < c.rect[3] - c.rect[1] < 70],
        key=lambda c: c.rect[0])
    if len(buttons) < 2:
        raise RuntimeError(
            f"Restore 확인 팝업의 버튼을 찾지 못했습니다(문구 {message!r}, "
            f"버튼 {[(b.ctrl_id, b.rect) for b in buttons]}).")
    yes = buttons[0]
    if yes.ctrl_id != flows.RESTORE_CONFIRM["yes"]:
        raise RuntimeError(
            f"Restore 확인 버튼 구성이 예상과 다릅니다 "
            f"(기대 좌={flows.RESTORE_CONFIRM['yes']}, 실제 "
            f"{[(b.ctrl_id, b.rect[0]) for b in buttons]}, 문구 {message!r}). "
            "잘못된 버튼을 누르지 않도록 중단합니다.")
    ui.click(yes, settle=3.0)
    return {"message": message.strip(), "clicked": yes.ctrl_id}


def run(ctx):
    r = TCResult("TC_Basic_WorkFlow_11", "Image Reject 및 Restore")
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    evidence = os.path.join(ctx.evidence_root, "Flow", "11_Reject")
    ui = None
    rejected_here = False
    try:
        # --- 전제 확인 --------------------------------------------------
        # Reject/Retake 설정을 **바꾸지 않고 확인**한다. 제품 기본값이 이미 요건을
        # 만족한다(2026-08-19 실측: Use reject reason 켜짐, Reason 5건 이상).
        # REJECT_REASON 컬럼은 Key / Type / Reason 이다(2026-08-20 실측). 7건이고
        # 사유 팝업(701~707)의 7개와 정확히 대응한다. `Type` 이
        # `INSTANCE_GROUP.RejectType` 에 기록되므로 고른 사유를 값으로 대조할 수 있다
        # (Artifacts=1 / Mispositioning=2 / ... / Others=0).
        reasons = ctx.db.query(
            "CONFIGURATION",
            "SELECT [Key],[Type],Reason FROM REJECT_REASON ORDER BY [Key]")
        want_reason = next(
            (x for x in reasons
             if uitext.norm(REASON.split("_")[0]) in uitext.norm(x["Reason"])), None)
        if want_reason is None:
            raise RuntimeError(
                f"REJECT_REASON 에 {REASON!r} 이 없습니다: "
                f"{[x['Reason'] for x in reasons]}")
        groups = ctx.db.query(
            "DATA", "SELECT g.[Key] FROM INSTANCE_GROUP g JOIN INSTANCE i "
                    "ON i.GroupKey=g.[Key] JOIN STUDY s ON s.[Key]=i.StudyKey "
                    "JOIN PATIENT p ON p.[Key]=s.PatientKey "
                    "WHERE p.PatientID=@pid GROUP BY g.[Key]",
            {"pid": PATIENT_ID})
        r.assert_true(
            0, "[전제] 영상 2건 이상 + Reject 사유 등록",
            len(groups) >= 2 and len(reasons) >= 1,
            expected={"영상 그룹": ">=2", "Reject 사유": ">=1"},
            actual={"groups": len(groups),
                    "reasons": [x["Reason"] for x in reasons],
                    "선택할 사유": want_reason},
            note="Setting > Study > Reject/Retake 의 제품 기본값이 요건을 만족하므로 "
                 "설정을 바꾸지 않고 확인만 한다(Use reject reason 켜짐, "
                 "Always display rejected images 켜짐).")

        already = _rejected_keys(ctx.db)
        if already:
            raise RuntimeError(
                f"이미 Reject 상태인 영상 그룹이 있습니다: {sorted(already)}. "
                "판정이 오염되므로 중단합니다 — 먼저 Restore 하거나 DB 를 복원하십시오.")

        pre = snapshot.take(ctx.db)

        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError("Patient 화면이 준비되지 않았습니다")

        # --- Step 1 -----------------------------------------------------
        rows = _open_view(ui)
        thumbs = _thumbnails(ui)
        r.assert_true(
            1, "Examined 에서 대상 검사를 열어 View 모드 진입", bool(thumbs),
            expected={"PatientID": PATIENT_ID, "썸네일": ">=2"},
            actual={"visible_cards": len(rows), "thumbnails": len(thumbs)},
            note="Expected 1. 올바른 검사가 열린다.")
        if len(thumbs) < 2:
            raise RuntimeError(
                f"썸네일이 {len(thumbs)}개뿐입니다. '다른 영상 상태는 변경되지 "
                "않는다'(Expected 6)를 확인할 수 없어 중단합니다.")

        # --- Step 2 -----------------------------------------------------
        ui.click(thumbs[0], settle=1.5)
        path = os.path.join(evidence, "01_selected.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        r.assert_true(
            2, "대상 영상 하나만 선택", True,
            expected="첫 썸네일(2D) 선택",
            actual={"selected_rect": thumbs[0].rect,
                    "thumbnails": [t.rect for t in thumbs]},
            note="Expected 2. 대상 영상만 선택된다. Multi Select(1169)를 쓰지 않으므로 "
                 "단일 선택이다. 선택 결과는 Step 3 의 'Reject 1건'으로 확인된다.")

        # --- Step 3: Reject ---------------------------------------------
        btn = uitext.visible(ui, flows.EXAMINE["reject_image"])
        if not btn:
            raise RuntimeError(
                f"Reject Image 버튼({flows.EXAMINE['reject_image']})을 "
                "찾지 못했습니다.")
        ui.click(btn[0], settle=2.5)
        picked = _pick_reason(ui, REASON, tess)
        rejected_here = True
        if ui.dialog():
            ui.dismiss_dialog(timeout=3)

        end = time.time() + 15
        while time.time() < end and not _rejected_keys(ctx.db):
            time.sleep(1)
        mid = snapshot.take(ctx.db)
        path = os.path.join(evidence, "02_rejected.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)

        # 고른 사유가 DB 에 그대로 기록됐는지 값으로 대조한다. `REJECT_REASON.Type`
        # 이 `INSTANCE_GROUP.RejectType` 에 들어간다(실측).
        marked = ctx.db.query(
            "DATA", "SELECT [Key],StatusRejected,RejectType,RejectReason,"
                    "RejectUserID FROM INSTANCE_GROUP WHERE StatusRejected=1")
        r.assert_true(
            3, f"고른 사유({want_reason['Reason']})가 DB에 기록",
            len(marked) == 1
            and int(marked[0]["RejectType"]) == int(want_reason["Type"])
            and marked[0]["RejectReason"] == want_reason["Reason"],
            expected={"RejectType": want_reason["Type"],
                      "RejectReason": want_reason["Reason"]},
            actual=marked,
            note="화면에서 고른 사유와 DB 값을 대조한다. REJECT_REASON.Type 이 "
                 "INSTANCE_GROUP.RejectType 에 기록된다(Artifacts=1 / "
                 "Mispositioning=2 / ... / Others=0, 2026-08-20 실측). "
                 "사유 항목은 순서가 아니라 문구를 OCR 로 읽어 골랐다.")

        # `tests/dataflow.py` 의 중간 판정을 재사용한다.
        mid_result = workflow_11_mid_evaluate(ctx, pre, mid)
        for check in mid_result.checks:
            r.add(3, check.title, check.status,
                  expected=check.expected, actual=check.actual,
                  note=(check.note or "") +
                       f" [사유 선택: {picked}] Reject 는 INSTANCE_GROUP 단위로 "
                       f"StatusRejected/RejectType/RejectReason/RejectUserID/"
                       f"RejectDate/RejectTime 에 기록된다(실측).")

        # --- Step 4: Reject 목록 확인 ------------------------------------
        # `Always display rejected images` 가 켜져 있어 Reject 된 영상이 같은 목록에
        # 남고 화면에 빨간 `REJECTED` 스탬프가 찍힌다. 그 상태를 DB 로 확인한다.
        rejected = ctx.db.query(
            "DATA",
            "SELECT g.[Key],g.StatusRejected,g.RejectReason,g.RejectUserID,"
            "p.PatientID,s.StudyInstanceUID FROM INSTANCE_GROUP g "
            "JOIN INSTANCE i ON i.GroupKey=g.[Key] "
            "JOIN STUDY s ON s.[Key]=i.StudyKey "
            "JOIN PATIENT p ON p.[Key]=s.PatientKey "
            "WHERE g.StatusRejected=1 GROUP BY g.[Key],g.StatusRejected,"
            "g.RejectReason,g.RejectUserID,p.PatientID,s.StudyInstanceUID")
        r.assert_true(
            4, "Reject 목록에 동일 Patient/Study/Image 표시",
            len(rejected) == 1 and rejected[0]["PatientID"] == PATIENT_ID,
            expected={"Reject 1건": PATIENT_ID},
            actual=rejected,
            note="Expected 4. 동일 Patient/Study/Image 가 Reject 목록에 표시된다. "
                 "Always display rejected images 가 켜져 있어 같은 목록에 남고 "
                 "영상에 빨간 REJECTED 스탬프가 찍힌다(증적 캡처). Patient ID 와 "
                 "Study Instance UID 를 DB 로 대조한다.")

        # --- Step 5: Restore --------------------------------------------
        thumbs = _thumbnails(ui)
        point = flows.restore_point(thumbs[0])
        ui.click(point, settle=3.0)
        confirmed = _confirm_restore(ui, tess)
        if confirmed is None:
            raise RuntimeError(
                "Restore 확인 팝업이 나타나지 않았습니다. ↺ 아이콘 위치가 "
                f"{point} 로 계산됐는데 눌리지 않았을 수 있습니다.")
        rejected_here = False

        end = time.time() + 15
        while time.time() < end and _rejected_keys(ctx.db):
            time.sleep(1)
        post = snapshot.take(ctx.db)
        path = os.path.join(evidence, "03_restored.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)

        r.assert_true(
            5, "선택한 영상 Restore", not _rejected_keys(ctx.db),
            expected="StatusRejected=1 인 그룹 0건",
            actual={"remaining": sorted(_rejected_keys(ctx.db)),
                    "dialog": confirmed},
            note="Expected 5. 선택한 영상이 Restore 된다. ↺ 는 별도 컨트롤이 아니라 "
                 "썸네일 안에 그려져 있어 rect 에서 위치를 계산한다"
                 "(flows.restore_point). 확인 팝업은 좌 Yes(501)/우 No(500) 이고 "
                 "dismiss_dialog 는 No 를 눌러 원복되지 않는다.")

        # --- Step 6: 원복 확인 (dataflow 판정 재사용) ---------------------
        post_result = workflow_11_evaluate(ctx, pre, post)
        for check in post_result.checks:
            if check.status == MANUAL and "Reject 목록" in check.title:
                continue        # Step 4 에서 이미 DB 로 확인했다
            r.add(6, check.title, check.status,
                  expected=check.expected, actual=check.actual, note=check.note)
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_11 실행", FAIL, actual=str(exc))
    finally:
        # Reject 한 상태로 끝나면 뒤따르는 TC 가 오염된다. 원복을 시도하고,
        # 못 하면 리포트에 분명히 남긴다(회귀는 DB 기준 복원으로 시작한다).
        if rejected_here and ui is not None:
            try:
                thumbs = _thumbnails(ui)
                if thumbs:
                    ui.click(flows.restore_point(thumbs[0]), settle=2.5)
                    _confirm_restore(ui, tess)
                left = _rejected_keys(ctx.db)
                r.add(0, "뒷정리: Reject 상태 원복",
                      PASS if not left else MANUAL,
                      expected="StatusRejected=1 인 그룹 0건",
                      actual=f"남은 그룹 {sorted(left)}" if left else "원복 확인")
            except Exception as exc:
                r.add(0, "뒷정리: Reject 상태 원복", MANUAL,
                      actual=f"원복 실패({exc}). Reject 상태가 남아 뒤따르는 TC 가 "
                             "영향을 받을 수 있습니다. DB 기준 복원으로 해소됩니다.")
    return r
