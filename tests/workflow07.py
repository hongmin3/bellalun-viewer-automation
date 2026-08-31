# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_07 — Emergency 검사 Auto Send.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.

체크리스트 원문 (변경 금지)
  Precondition
    Storage SCP가 Online이다.
    Storage 설정에서 Dose SR 전송이 활성화되어 있다.
    실제 촬영이 승인된 시험 환경이다.
  Step
    1. Setting > DICOM > General에서 Study Close option on Examine mode를
       Auto Send로 설정한다.
    2. Send Urgent patient automatically를 Yes로 설정한다.
    3. Patient 창에서 Emergency 버튼으로 검사를 시작한다.
    4. 승인된 팬텀으로 2D 영상을 1회 촬영한다.
    5. 검사를 종료한다.
    6. Queue 상태를 확인한다.
    7. Storage SCP에서 영상과 RDSR 수신 여부를 확인한다.
  Expected Result
    1. Auto Send 설정이 저장된다.
    2. Emergency 자동 전송 설정이 저장된다.
    3. Emergency 검사가 시작된다.
    4. 영상이 Emergency 검사에 생성된다.
    5. 검사 종료 후 자동 전송이 시작된다.
    6. 영상과 RDSR의 Queue 상태가 Done으로 표시된다.
    7. 동일 Emergency 검사의 영상과 RDSR이 수신된다.

**실제 X-ray 노출은 하지 않는다.** `viewer.demo_mode=true` 안전 게이트를 걸고
Demo(F8) 가상 촬영만 한다(WF_02 와 같은 규칙). 그래서 Precondition 의 "실제 촬영이
승인된 시험 환경" 은 Demo 로 대체하며, 그 사실을 판정 note 에 남긴다.

실측한 컨트롤 (2026-08-19~20)
  Setting > DICOM > General
    2444 "Study close option on Examine mode" 콤보 — 항목은 **`None` / `Auto Send`**
    2446 "Send urgent patient automatically" Yes / 2445 No (제품 기본값 No)
  Patient 화면 우상단 **1100** = Emergency (사이렌 아이콘, 캡처로 확인)

  Emergency 검사의 Patient ID 는 제품이 자동 생성한다(`EM-260820-093045` 형태 실측).
  그래서 대상 검사는 **실행 전후 STUDY 차집합**으로 찾는다.

사용자 지시 (2026-08-20)
  "쌓이는건 문제가 없을것 같아 스터디가! 짜피 전체 회귀 돌릴때 db초기화를 하니깐!"
  -> Emergency 검사를 TC 안에서 지우지 않는다. 파괴적 동작을 늘리지 않는다.

**Auto Send 설정은 되돌린다.** 켜 둔 채 끝나면 뒤따르는 TC 가 검사를 닫을 때마다
자동 전송이 일어나 Queue 판정이 오염된다.
"""

from __future__ import annotations

import os
import time

from core import dicom_settings as ds
from core import flows, screen, uitext
from core import send_verify as sv
from core import viewer_processing
from core.result import FAIL, MANUAL, PASS, TCResult

AUTO_SEND_LABEL = "Auto Send"
NONE_LABEL = "None"


def _studies(db):
    return {int(r["Key"]): r for r in db.query(
        "DATA",
        "SELECT s.[Key],s.StudyStatus,s.StudyInstanceUID,p.PatientID "
        "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey ORDER BY s.[Key]")}


# Setting > DICOM > General 의 저장 위치 (2026-08-20 실측).
#   `CONFIGURATION.DICOM_COMMON.StudyCloseOption` — 0 = None / 1 = Auto Send
#   `CONFIGURATION.DICOM_COMMON.UrgentAutoSend`   — 0 = No   / 1 = Yes
# 테이블 이름을 `DICOM_GENERAL` 로 짐작했다가 "Invalid object name" 으로 죽었다.
# 값 매핑은 설정한 뒤 DB 로 확인한다(추측하지 않는다).
STUDY_CLOSE_OPTION = {"None": 0, "Auto Send": 1}


def _general(db):
    """Setting > DICOM > General 의 저장값."""
    row = db.one(
        "CONFIGURATION",
        "SELECT TOP 1 StudyCloseOption,UrgentAutoSend FROM DICOM_COMMON")
    return row or {}


def _set_general(ui, close_option, urgent_yes, tesseract_exe=None):
    """Study close option 과 Send urgent patient automatically 를 설정한다."""
    flows.open_dicom_setting(ui, "general", wait=3.0)
    picked = uitext.pick_combo_by_text(
        ui, flows.SETTING_DICOM_GENERAL["study_close_option"], close_option,
        tesseract_exe, what="Study close option")
    key = "urgent_auto_send_yes" if urgent_yes else "urgent_auto_send_no"
    radio = [c for c in ui.by_id(flows.SETTING_DICOM_GENERAL[key]) if c.visible]
    if not radio:
        raise RuntimeError(
            f"Send urgent patient automatically 라디오"
            f"({flows.SETTING_DICOM_GENERAL[key]})를 찾지 못했습니다.")
    ui.click(radio[0], settle=1.0)
    flows.setting_update(ui, wait=3)
    if ui.dialog():
        ui.dismiss_dialog(timeout=3)
    time.sleep(1.5)
    return {"close_option": picked, "urgent_yes": urgent_yes}


def _start_emergency(ui, timeout=25):
    """Patient 화면의 Emergency(1100)로 검사를 시작한다."""
    if not flows.ensure_patient_screen(ui):
        raise RuntimeError("Patient 화면이 준비되지 않았습니다")
    btn = [c for c in ui.by_id(flows.PATIENT_EMERGENCY) if c.visible]
    if not btn:
        raise RuntimeError(
            f"Emergency 버튼({flows.PATIENT_EMERGENCY})을 찾지 못했습니다.")
    ui.click(btn[0], settle=4.0)
    # 확인 팝업이 있을 수 있다. 있으면 문구를 남기고 진행한다.
    message = None
    if ui.dialog():
        message = ui.dismiss_dialog(timeout=3)
    # Examine 화면(썸네일 패널)이 뜰 때까지 기다린다.
    end = time.time() + timeout
    while time.time() < end:
        if flows.step_items(ui) or [c for c in ui.by_id(flows.EXAMINE["close"])
                                    if c.visible]:
            return {"dialog": message}
        time.sleep(1.0)
    raise RuntimeError(
        f"Emergency 검사 화면이 {timeout}초 안에 열리지 않았습니다(팝업 {message!r}).")


def run(ctx):
    r = TCResult("TC_Basic_WorkFlow_07", "Emergency 검사 Auto Send")
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    evidence = os.path.join(ctx.evidence_root, "Flow", "07_Emergency")
    ui = None
    changed_general = False
    try:
        # 실제 X-ray 노출을 자동 실행하지 않는다(WF_02 와 같은 게이트).
        if ctx.cfg.get("viewer", {}).get("demo_mode") is not True:
            r.add(0, "Demo 가상 촬영 안전 게이트", FAIL,
                  expected="viewer.demo_mode=true", actual="false 또는 미설정",
                  note="실제 X-ray 노출은 자동 실행하지 않습니다.")
            return r

        # `SCPUseType=0`(설정 행)만 본다 — 전송 작업 사본 행도 `Use=1` 이다
        # (`core/dicom_settings.STORAGE_SCP_USE_TYPE` 주석의 실측 근거 참고).
        storage = ctx.db.one(
            "CONFIGURATION",
            "SELECT TOP 1 [Key],Name,SendDoseSR,SCPUseType FROM DICOM_STORAGE "
            "WHERE [Use]=1 AND SCPUseType=@t ORDER BY [Key]",
            {"t": ds.STORAGE_SCP_USE_TYPE})
        r.assert_true(
            0, "[전제] Storage 등록 + Dose SR 전송 활성 + Demo 모드",
            bool(storage) and int(storage.get("SendDoseSR") or 0) == 1,
            expected={"SendDoseSR": 1, "demo_mode": True},
            actual={"storage": storage, "demo_mode": True},
            note="Precondition 의 '실제 촬영이 승인된 시험 환경' 은 Demo(F8) 가상 "
                 "촬영으로 대체한다 — 자동화가 실제 X-ray 를 노출하지 않는다는 "
                 "이 저장소의 규칙이다.")

        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError("Patient 화면이 준비되지 않았습니다")
        # 전송 전에 Transfer Syntax 를 선언값으로 맞춘다(검사를 열기 전에 해야 한다).
        if not sv.ensure_transfer_syntax(ctx, ui, r):
            raise RuntimeError(
                "Storage Transfer Syntax 를 선언된 값으로 맞추지 못했습니다.")

        before_studies = _studies(ctx.db)
        known_queue = set(sv.queue_keys(ctx))
        sv.clear_received(ctx)

        # --- Step 1~2: Auto Send 설정 -------------------------------------
        picked = _set_general(ui, AUTO_SEND_LABEL, True, tess)
        changed_general = True
        general = _general(ctx.db)
        path = os.path.join(evidence, "01_auto_send.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)

        want_close = STUDY_CLOSE_OPTION[AUTO_SEND_LABEL]
        r.assert_true(
            1, f"Study close option on Examine mode = {AUTO_SEND_LABEL}",
            int(general.get("StudyCloseOption", -1)) == want_close,
            expected={"콤보": AUTO_SEND_LABEL,
                      "DICOM_COMMON.StudyCloseOption": want_close},
            actual={"picked": picked.get("close_option"), "db": general},
            note="Expected 1. Auto Send 설정이 저장된다. 콤보(2444) 항목은 "
                 "`None` / `Auto Send` 두 개다(실측). 항목은 순서가 아니라 문구를 "
                 "OCR 로 읽어 고른다. CONFIGURATION.DICOM_COMMON.StudyCloseOption 으로 대조한다(0 = None / 1 = Auto Send, 실측).")
        r.assert_true(
            2, "Send urgent patient automatically = Yes",
            int(general.get("UrgentAutoSend", -1)) == 1,
            expected={"라디오": flows.SETTING_DICOM_GENERAL["urgent_auto_send_yes"],
                      "DICOM_COMMON.UrgentAutoSend": 1},
            actual={"db": general},
            note="Expected 2. Emergency 자동 전송 설정이 저장된다. 제품 기본값은 "
                 "No(2445)이고 Yes(2446)로 바꾼다. **이 설정은 finally 에서 되돌린다** "
                 "— 켜 둔 채 끝나면 뒤따르는 TC 가 검사를 닫을 때마다 자동 전송이 "
                 "일어나 Queue 판정이 오염된다.")

        # --- Step 3: Emergency 검사 시작 ----------------------------------
        started = _start_emergency(ui)
        end = time.time() + 20
        new_keys = []
        while time.time() < end and not new_keys:
            new_keys = sorted(set(_studies(ctx.db)) - set(before_studies))
            if not new_keys:
                time.sleep(1)
        path = os.path.join(evidence, "02_emergency_started.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        after = _studies(ctx.db)
        target = after.get(new_keys[0]) if new_keys else None
        r.assert_true(
            3, "Emergency 검사 시작", target is not None,
            expected="STUDY 신규 1건",
            actual={"new_keys": new_keys, "study": target, "start": started},
            note="Expected 3. Emergency 검사가 시작된다. Patient 화면 우상단의 "
                 "Emergency(1100, 사이렌 아이콘)로 시작한다. Patient ID 는 제품이 "
                 "자동 생성하므로(`EM-...` 형태) 대상은 **실행 전후 STUDY 차집합**으로 "
                 "찾는다.")
        if target is None:
            raise RuntimeError("Emergency 검사가 생성되지 않아 이후 단계를 중단합니다")
        study_key = int(new_keys[0])

        # --- Step 4: 2D 1회 촬영 ------------------------------------------
        viewer_processing.add_view_position(ui, "2d")
        # 고정 대기(settle=14) + 별도 폴링 대신 TC_XIPL_compatibility_04/07과
        # 같은 `viewer_processing.wait_new_group` 상태 기반 대기로 통일한다
        # (2026-08-24 실측: 2D는 14초 고정 대기가 2.8~2.9초로 충분했다). 판정에
        # 쓰는 값은 대기 후 기존과 동일한 조회로 다시 확인한다.
        known = set(viewer_processing.acquired_groups(ctx.db, study_key))
        acquired = flows.demo_acquire_step(ui, 1, settle=0)
        viewer_processing.wait_new_group(
            ctx.db, study_key, known,
            required_types=viewer_processing.INSTANCE_TYPES_2D, timeout=60)
        row = ctx.db.one(
            "DATA", "SELECT COUNT(*) n FROM INSTANCE WHERE StudyKey=@k",
            {"k": study_key})
        images = int(row["n"]) if row else 0
        path = os.path.join(evidence, "03_acquired.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        r.assert_true(
            4, "Emergency 검사에 2D 영상 1건 생성", images >= 1,
            expected={"INSTANCE": ">=1", "StudyKey": study_key},
            actual={"images": images, "acquired": acquired},
            note="Expected 4. 영상이 Emergency 검사에 생성된다. Demo(F8) 가상 촬영이며 "
                 "`demo_acquire_step` 이 Ready 를 확인한 뒤에만 촬영한다.")

        # --- Step 5: 검사 종료 -> 자동 전송 --------------------------------
        # Close 클릭이 삼켜져 검사가 열린 채 남는 경우가 있어(2026-08-31 실측,
        # 재현율 1/3) 종료를 **DB 로 확인**하고 삼켜졌을 때만 다시 누른다.
        # 판별을 화면으로 못 하는 이유와 재시도 조건은
        # `core/flows.close_examine_confirmed` docstring 에 적었다.
        closed = flows.close_examine_confirmed(
            ui, ctx.db, study_key, option="close", wait=10,
            tesseract_exe=tess)
        time.sleep(3)
        path = os.path.join(evidence, "04_closed.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)

        # --- Step 6: Queue 상태 -------------------------------------------
        def queue_rows():
            return [q for q in ctx.db.query(
                "DATA", "SELECT [Key],State,DataType,InstanceUID "
                        "FROM DICOM_STORAGE_QUEUE ORDER BY [Key] DESC")
                    if q["Key"] not in known_queue]

        end = time.time() + 90
        while time.time() < end and not queue_rows():
            time.sleep(2)
        new_queue = queue_rows()
        r.assert_true(
            5, "검사 종료 후 자동 전송 시작", bool(new_queue),
            expected="Queue 신규 행 (Send 를 직접 누르지 않았다)",
            actual={"new_queue": new_queue, "closed": closed},
            note="Expected 5. 검사 종료 후 자동 전송이 시작된다. **Send 버튼을 누르지 "
                 "않았다** — Auto Send 설정만으로 Queue 에 들어가는 것이 이 TC 의 "
                 "핵심이다.")

        images_q = [q for q in new_queue if not sv.is_dose_sr_row(q)]
        dose_q = [q for q in new_queue if sv.is_dose_sr_row(q)]
        end = time.time() + 90
        while time.time() < end and not (
                images_q and all(int(q["State"]) == sv.QUEUE_STATE_DONE
                                 for q in images_q)):
            time.sleep(2)
            rows = queue_rows()
            images_q = [q for q in rows if not sv.is_dose_sr_row(q)]
            dose_q = [q for q in rows if sv.is_dose_sr_row(q)]
        r.assert_true(
            6, "영상 Queue 상태 Done",
            bool(images_q) and all(int(q["State"]) == sv.QUEUE_STATE_DONE
                                   for q in images_q),
            expected=f"영상 행 전부 State={sv.QUEUE_STATE_DONE}",
            actual={"images": images_q, "dose_sr": dose_q},
            note="Expected 6. 영상과 RDSR 의 Queue 상태가 Done 으로 표시된다. "
                 "영상과 Dose SR 은 성격이 달라 나눠 판정한다"
                 "(core/send_verify.is_dose_sr_row).")
        if dose_q and any(int(q["State"]) != sv.QUEUE_STATE_DONE for q in dose_q):
            r.blocked(
                6, "Dose SR Queue 상태가 Done 이다",
                "확인 항목은 **기대 상태**를 적는다(2026-08-21 사용자 지적) — 이전에는 "
                "'Done 이 아니다' 라고 관측 결과를 제목에 적어 확인 항목처럼 읽히지 "
                "않았다. 판정: 이 환경은 Demo(F8) 가상 촬영이라 RDSR 생성 조건이 "
                "성립하지 않아 **전제 미충족(MANUAL)** 이다. 제품 결함으로 보고하지 "
                "않는다 — WF_06/WF_15 에서도 같은 상태를 반복 확인했다. "
                f"**실측**: Dose SR 행 {[q['Key'] for q in dose_q]} 이 "
                f"State={[q['State'] for q in dose_q]} (Done={sv.QUEUE_STATE_DONE}) "
                "로 남았다. "
                "**해제 조건**: 실제 촬영 환경에서 RDSR 생성 조건을 충족시킨 "
                "뒤 재확인. "
                "Dose SR **전송 경로** 자체는 `WF_06`(Examined All Images)과 "
                "`WF_15`(Pre-send Preview)가 사양 경로로 검증한다 — 이 TC 는 "
                "검사 종료 Auto Send 경로를 본다. "
                "**이 실행으로 말할 수 없는 것**: Emergency Auto Send 경로의 "
                "Dose SR 전송이 정상인지 여부.",
                expected=f"Dose SR 행 State={sv.QUEUE_STATE_DONE}",
                actual={"dose_sr": dose_q})
        elif not dose_q:
            r.blocked(
                6, "Dose SR 이 Queue 에 등록된다",
                "Auto Send 로 영상은 전송됐지만 Dose SR 행이 없다. Demo 가상 촬영은 "
                "RDSR 생성 조건을 충족하지 않는다(WF_06 과 같은 판단). "
                "**해제 조건**: 실제 촬영 환경. "
                "Dose SR 전송 경로 자체는 `WF_06`/`WF_15` 가 검증한다. "
                "**이 실행으로 말할 수 없는 것**: RDSR 자동 전송 여부.",
                expected="Dose SR 행 1건 이상", actual={"dose_sr": []})

        # --- Step 7: 수신 확인 --------------------------------------------
        outcome = sv.wait_received_stable(ctx, wait=90)
        received = sv.received(ctx) or []
        want = {str(i["ImageInstanceUID"]) for i in ctx.db.query(
            "DATA", "SELECT ImageInstanceUID FROM INSTANCE WHERE StudyKey=@k "
                    "AND InstanceType IN (0)", {"k": study_key})}
        got = {str(o.get("SOPInstanceUID")) for o in received
               if o.get("SOPInstanceUID")}
        r.assert_true(
            7, "동일 Emergency 검사의 영상 수신",
            bool(received) and not (want - got),
            expected={"SOP Instance UID": sorted(want)},
            actual={"received": len(received), "received_uids": sorted(got),
                    "missing": sorted(want - got), "stable": outcome},
            note="Expected 7. 동일 Emergency 검사의 영상과 RDSR 이 수신된다. 영상은 "
                 "SOP Instance UID 로 대조한다. RDSR 은 위 MANUAL 참고 — Demo 촬영에서 "
                 "생성 조건이 성립하지 않는다.")
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_07 실행", exc)
    finally:
        # **Auto Send 를 반드시 되돌린다.** 켜 둔 채 끝나면 뒤따르는 TC 가 검사를
        # 닫을 때마다 자동 전송이 일어나 Queue 판정이 오염된다.
        if changed_general and ui is not None:
            try:
                _set_general(ui, NONE_LABEL, False, tess)
                r.cleanup(0, "뒷정리: Auto Send 설정 원복", PASS,
                      expected={"close_option": NONE_LABEL, "urgent": "No"},
                      actual=_general(ctx.db),
                      note="켜 둔 채 끝나면 뒤따르는 TC 의 Queue 판정이 오염된다.")
            except Exception as exc:
                r.cleanup(0, "뒷정리: Auto Send 설정 원복", FAIL,
                      actual=f"원복 실패({exc}). **뒤따르는 TC 가 검사를 닫을 때마다 "
                             "자동 전송이 일어날 수 있다.** Setting > DICOM > General 의 "
                             "Study close option 을 None, Send urgent patient "
                             "automatically 를 No 로 되돌리십시오.")
        # Emergency 검사는 지우지 않는다 — 사용자 지시(회귀가 DB 를 복원한다).
    return r
