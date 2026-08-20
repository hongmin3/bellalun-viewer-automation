# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_12 — Study Reject 및 Restore.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.

체크리스트 원문 (변경 금지)
  Step
    1. Examined 창에서 대상 검사를 선택한다.
    2. Study Reject를 실행한다.
    3. Reject된 검사 목록에서 동일 검사를 확인한다.
    4. 동일 검사를 선택하고 Restore를 실행한다.
    5. Examined 창에서 검사를 다시 조회한다.
  Expected Result
    1. 대상 검사만 선택된다.
    2. 선택한 검사가 Reject 상태가 된다.
    3. 동일 Patient ID와 Study Instance UID의 검사가 Reject 목록에 표시된다.
    4. 선택한 검사가 Restore된다.
    5. 원래 검사 목록에 동일 검사와 영상이 표시된다.

**Precondition / Test Data 를 2026-08-20 에 수정했다.** 원문은
`DATA_FLOW_LOCAL_01`(복구 가능한 전용 시험 검사)을 요구했는데, 이 환경에서 그 검사는
**영상이 0건**이다(WF_01 이 Local 검사를 만들지만 촬영은 하지 않는다). Expected 5 가
"동일 검사와 **영상**이 표시된다"를 요구하므로 영상 없는 검사로는 판정할 수 없다.
사용자 지시: "영상은 꼭 있는 스터디여야해, 이미 촬영되고 close 가 된 스터디로
진행해도 좋아" -> `DATA_FLOW_MWL_01` 을 쓴다.

실측한 흐름 (2026-08-20) — 사용자가 캡처로 알려 주고 hover 툴팁으로 확정했다
  Examined 에서 검사 선택 -> **2186 "Reject Study"** -> 사유 팝업(701~707)
  -> 데이터 소스를 **1187 Rejected** 로 바꾸면 Reject 된 검사가 보인다
  -> 그 검사 선택 -> **같은 2186 이 "Restore Study" 로 토글**된다 -> 원복

  `2186` 은 내가 2026-08-19 에 "휴지통(삭제) — 절대 누르지 말 것" 으로 기록한
  버튼이다. 아이콘 추정 오류의 네 번째 사례다.

  `STUDY.StudyStatus` 3 -> **5** 로 바뀌고 RejectType / RejectReason /
  RejectUserID 가 기록된다(실측).

판정
  `tests/dataflow.py` 의 `workflow_12_mid_evaluate` / `workflow_12_evaluate` 를
  재사용한다. WF_11 과 마찬가지로 그 판정부는 그전까지 한 번도 실행된 적이 없었다.
"""

from __future__ import annotations

import os
import time

from core import flows, screen, snapshot, uitext
from core.result import FAIL, MANUAL, PASS, TCResult
from tests.dataflow import workflow_12_evaluate, workflow_12_mid_evaluate
from tests.workflow02 import PATIENT_ID, _examined_search

REASON = "artifacts"        # 사용자: "사유는 아무거나 무관하다"


def _studies(db):
    return {int(r["Key"]): r for r in db.query(
        "DATA",
        "SELECT s.[Key],s.StudyStatus,s.RejectType,s.RejectReason,s.RejectUserID,"
        "s.StudyInstanceUID,p.PatientID FROM STUDY s "
        "JOIN PATIENT p ON p.[Key]=s.PatientKey ORDER BY s.[Key]")}


def _rejected(db):
    return {k: v for k, v in _studies(db).items()
            if int(v["StudyStatus"]) == flows.STUDY_STATUS_REJECTED}


def _target(db):
    """영상이 있는 대상 검사. Expected 5 가 영상 표시를 요구한다."""
    row = db.one(
        "DATA",
        "SELECT TOP 1 s.[Key],s.StudyInstanceUID,p.PatientID,"
        "(SELECT COUNT(*) FROM INSTANCE i WHERE i.StudyKey=s.[Key]) images "
        "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid AND EXISTS "
        "(SELECT 1 FROM INSTANCE i WHERE i.StudyKey=s.[Key]) "
        "ORDER BY s.[Key] DESC", {"pid": PATIENT_ID})
    if not row:
        raise RuntimeError(
            f"영상이 있는 검사를 찾지 못했습니다: {PATIENT_ID}. "
            "Expected 5 가 '동일 검사와 영상이 표시된다'를 요구하므로 영상 없는 "
            "검사로는 판정할 수 없습니다.")
    return row


def _reject_or_restore(ui, tesseract_exe=None):
    """`2186` 을 누른다. 상태에 따라 Reject Study / Restore Study 로 동작한다."""
    hits = [c for c in ui.by_id(flows.EXAMINED_REJECT_STUDY) if c.visible]
    if not hits:
        raise RuntimeError(
            f"Reject/Restore Study 버튼({flows.EXAMINED_REJECT_STUDY})을 "
            "찾지 못했습니다.")
    ui.click(hits[0], settle=2.5)


def _pick_reason(ui, reason, tesseract_exe):
    """사유 팝업에서 사유를 고른다. Study Reject 도 Image Reject 와 같은 팝업이다."""
    ctrl_id = flows.REJECT_REASONS[reason]
    hits = uitext.visible(ui, ctrl_id)
    if not hits:
        raise RuntimeError(
            f"Reject 사유 팝업({ctrl_id})을 찾지 못했습니다.")
    text = uitext.ocr(hits[0], tesseract_exe)
    if uitext.norm(reason.split("_")[0]) not in uitext.norm(text):
        raise RuntimeError(
            f"사유 {ctrl_id} 가 {reason!r} 이 아닙니다(읽은 값 {text!r}).")
    ui.click(hits[0], settle=3.0)
    return {"reason": reason, "ctrl_id": ctrl_id, "ocr": text}


def _wait(check, timeout=15):
    end = time.time() + timeout
    while time.time() < end and not check():
        time.sleep(1)
    return check()


def run(ctx):
    r = TCResult("TC_Basic_WorkFlow_12", "Study Reject 및 Restore")
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    evidence = os.path.join(ctx.evidence_root, "Flow", "12_StudyReject")
    ui = None
    rejected_here = False
    try:
        target = _target(ctx.db)
        reasons = ctx.db.query(
            "CONFIGURATION",
            "SELECT [Key],[Type],Reason FROM REJECT_REASON ORDER BY [Key]")
        want_reason = next(
            (x for x in reasons
             if uitext.norm(REASON.split("_")[0]) in uitext.norm(x["Reason"])), None)
        if want_reason is None:
            raise RuntimeError(f"REJECT_REASON 에 {REASON!r} 이 없습니다")

        r.assert_true(
            0, "[전제] 영상이 있는 대상 검사", int(target["images"]) > 0,
            expected={"PatientID": PATIENT_ID, "영상": ">=1"},
            actual=target,
            note="개정본 원문은 DATA_FLOW_LOCAL_01 을 요구했는데 이 환경에서 그 검사는 "
                 "영상이 0건이다(WF_01 이 Local 검사를 만들지만 촬영은 하지 않는다). "
                 "Expected 5 가 '동일 검사와 영상이 표시된다'를 요구하므로 영상이 있는 "
                 "검사로 수행한다(사용자 지시, 2026-08-20 TC 문서도 함께 수정).")

        already = _rejected(ctx.db)
        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError("Patient 화면이 준비되지 않았습니다")

        if already:
            # 이전 실행이 남긴 Reject 를 먼저 원복한다. 남겨 두면 "Reject 되었다"는
            # 판정이 거짓으로 통과한다.
            # **데이터 소스 드롭리스트(2200)는 Examined 창이 열린 뒤에만 보인다.**
            # 조회를 먼저 해 창을 띄운다.
            _examined_search(ui, PATIENT_ID)
            flows.select_examined_source(ui, "rejected", tess)
            rows = _examined_search(ui, PATIENT_ID)
            if rows:
                ui.click(rows[0], settle=1.5)
                _reject_or_restore(ui, tess)
                if ui.dialog():
                    ui.dismiss_dialog(timeout=3)
                _wait(lambda: not _rejected(ctx.db))
            flows.select_examined_source(ui, "all", tess)
            if _rejected(ctx.db):
                raise RuntimeError(
                    f"이전 실행이 남긴 Reject 검사를 원복하지 못했습니다: "
                    f"{sorted(_rejected(ctx.db))}. 판정이 오염되므로 중단합니다.")

        pre = snapshot.take(ctx.db)

        # --- Step 1 -----------------------------------------------------
        rows = _examined_search(ui, PATIENT_ID)
        if not rows:
            raise RuntimeError(f"Examined 목록이 비어 있습니다: {PATIENT_ID}")
        ui.click(rows[0], settle=1.5)
        path = os.path.join(evidence, "01_selected.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        r.assert_true(
            1, "Examined 에서 대상 검사 선택", len(rows) >= 1,
            expected={"PatientID": PATIENT_ID, "StudyKey": target["Key"]},
            actual={"visible_cards": len(rows), "target": target},
            note="Expected 1. 대상 검사만 선택된다.")

        # --- Step 2: Study Reject ---------------------------------------
        _reject_or_restore(ui, tess)
        picked = _pick_reason(ui, REASON, tess)
        rejected_here = True
        if ui.dialog():
            ui.dismiss_dialog(timeout=3)
        _wait(lambda: bool(_rejected(ctx.db)))
        mid = snapshot.take(ctx.db)
        path = os.path.join(evidence, "02_rejected.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)

        marked = _rejected(ctx.db)
        r.assert_true(
            2, f"선택한 검사가 Reject 상태(StudyStatus="
               f"{flows.STUDY_STATUS_REJECTED})",
            len(marked) == 1 and int(target["Key"]) in marked
            and int(marked[int(target["Key"])]["RejectType"])
            == int(want_reason["Type"])
            and marked[int(target["Key"])]["RejectReason"] == want_reason["Reason"],
            expected={"StudyStatus": flows.STUDY_STATUS_REJECTED,
                      "RejectType": want_reason["Type"],
                      "RejectReason": want_reason["Reason"],
                      "대상": target["Key"]},
            actual={"rejected": marked, "picked": picked},
            note="Expected 2. 선택한 검사가 Reject 상태가 된다. 2186(Reject Study)은 "
                 "Image Reject 와 **같은 사유 팝업**(701~707)을 쓴다. "
                 "REJECT_REASON.Type 이 STUDY.RejectType 에 기록된다.")

        mid_result = workflow_12_mid_evaluate(ctx, pre, mid)
        for check in mid_result.checks:
            r.add(2, check.title, check.status,
                  expected=check.expected, actual=check.actual, note=check.note)

        # --- Step 3: Reject 목록에서 확인 --------------------------------
        picked_source = flows.select_examined_source(ui, "rejected", tess)
        rows_rej = _examined_search(ui, PATIENT_ID)
        path = os.path.join(evidence, "03_rejected_list.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        row = marked.get(int(target["Key"]), {})
        r.assert_true(
            3, "Reject 목록에 동일 Patient ID / Study Instance UID 표시",
            len(rows_rej) >= 1
            and row.get("PatientID") == PATIENT_ID
            and row.get("StudyInstanceUID") == target["StudyInstanceUID"],
            expected={"PatientID": PATIENT_ID,
                      "StudyInstanceUID": target["StudyInstanceUID"]},
            actual={"cards": len(rows_rej), "db_row": row,
                    "source": picked_source},
            note="Expected 3. Reject 된 검사는 기본 목록에서 빠지므로 Examined 의 "
                 "데이터 소스를 Rejected(1187)로 바꿔야 보인다. 화면 카드 수와 함께 "
                 "DB 의 Patient ID / Study Instance UID 를 대조한다.")

        # --- Step 4: Restore --------------------------------------------
        if not rows_rej:
            raise RuntimeError("Rejected 목록이 비어 Restore 대상을 고를 수 없습니다")
        ui.click(rows_rej[0], settle=1.5)
        _reject_or_restore(ui, tess)          # 같은 2186 이 Restore Study 로 동작
        if ui.dialog():
            ui.dismiss_dialog(timeout=3)
        restored = _wait(lambda: not _rejected(ctx.db))
        rejected_here = not restored
        path = os.path.join(evidence, "04_restored.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        r.assert_true(
            4, "선택한 검사 Restore", restored,
            expected=f"StudyStatus={flows.STUDY_STATUS_REJECTED} 인 검사 0건",
            actual={"remaining": sorted(_rejected(ctx.db))},
            note="Expected 4. 선택한 검사가 Restore 된다. **같은 2186 버튼이 Rejected "
                 "검사를 선택하면 'Restore Study' 로 토글된다**(hover 툴팁으로 확정). "
                 "아이콘도 휴지통에서 되돌리기 화살표로 바뀐다.")

        # --- Step 5: 원래 목록에서 재조회 --------------------------------
        flows.select_examined_source(ui, "all", tess)
        rows_back = _examined_search(ui, PATIENT_ID)
        post = snapshot.take(ctx.db)
        images = ctx.db.one(
            "DATA", "SELECT COUNT(*) n FROM INSTANCE WHERE StudyKey=@k",
            {"k": target["Key"]})
        path = os.path.join(evidence, "05_back_in_list.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        r.assert_true(
            5, "원래 목록에 동일 검사와 영상이 표시",
            len(rows_back) >= 1 and int(images["n"]) == int(target["images"]),
            expected={"카드": ">=1", "영상": target["images"]},
            actual={"cards": len(rows_back), "images": images["n"]},
            note="Expected 5. 원래 검사 목록에 동일 검사와 영상이 표시된다. "
                 "데이터 소스를 All 로 돌려 조회하고, 영상 건수가 Reject 전과 같은지 "
                 "DB 로 대조한다.")

        post_result = workflow_12_evaluate(ctx, pre, post)
        for check in post_result.checks:
            r.add(5, check.title, check.status,
                  expected=check.expected, actual=check.actual, note=check.note)
    except Exception as exc:
        r.add(0, "TC_Basic_WorkFlow_12 실행", FAIL, actual=str(exc))
    finally:
        # Reject 상태로 끝나면 뒤따르는 TC 가 오염된다(기본 목록에서 검사가 빠진다).
        if rejected_here and ui is not None:
            try:
                flows.select_examined_source(ui, "rejected", tess)
                rows = _examined_search(ui, PATIENT_ID)
                if rows:
                    ui.click(rows[0], settle=1.5)
                    _reject_or_restore(ui, tess)
                    if ui.dialog():
                        ui.dismiss_dialog(timeout=3)
                    _wait(lambda: not _rejected(ctx.db))
                flows.select_examined_source(ui, "all", tess)
                left = _rejected(ctx.db)
                r.add(0, "뒷정리: Reject 상태 원복",
                      PASS if not left else MANUAL,
                      expected="Reject 검사 0건",
                      actual=f"남은 검사 {sorted(left)}" if left else "원복 확인")
            except Exception as exc:
                r.add(0, "뒷정리: Reject 상태 원복", MANUAL,
                      actual=f"원복 실패({exc}). Reject 된 검사가 남아 기본 목록에서 "
                             "빠지므로 뒤따르는 TC 가 영향을 받을 수 있습니다. "
                             "DB 기준 복원으로 해소됩니다.")
    return r
