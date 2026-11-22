# -*- coding: utf-8 -*-
r"""SRS 06-10-10 Queue List Retry 사양 시험 (REQ-QUEUE-001).

체크리스트 TC 가 아니다. 기본기능·WU 회귀 순서와 판정에 넣지 않고
`python run.py run-queue-retry` 로만 실행한다.

사양 근거
  기존 원노트 사양서(261030) SRS 06-10-10 Queue List, Revision 2026-10-30
  "Retry 사양 추가":
    "Retry 버튼을 눌러 선택한 항목을 다시 전송할 수 있다.
     DICOM Storage 설정 변경 여부와 관계없이 Queue 등록 당시 저장된 정보를
     기준으로 재전송한다."
  같은 문장이 Redmine #25531 종료 댓글에 사양서 반영으로 인용돼 있다.
  ALM 사양서 1.0.12(261122) VP-314 본문에는 이 문장이 없다(SPEC 13절).

판정
  Queue 화면 Storage 목록의 State 문구. 틀린 Port 로 등록된 항목은 Port 를 고친
  뒤 Retry 해도 등록 당시 정보(틀린 Port)로 다시 보내므로 Failed 가 기대값이다.
  DB Queue 행, 작업 사본 Storage 행의 Port, Storage SCP 수신 건수는 참고 기록이다.

복원
  설정된 Storage 행(`SCPUseType=0`)을 실행 전 기록과 같게 UI 로 되돌리고 DB 로
  확인한다. 실행 전 행이 없었으면 시험 Storage 를 UI 로 삭제한다.
"""
import os
import time
from datetime import datetime

from core import dicom_queue as dq
from core import dicom_settings as ds
from core import flows
from core import send_verify as sv
from core import viewer_processing as vp
from core.result import TCResult, FAIL, PASS
from core.ui import children

TC_ID = "SRS_06_10_10_QUEUE_RETRY"
TITLE = "Queue List Retry: 등록 당시 Storage 정보로 재전송 (Demo)"
SPEC_NOTE = ("기존 원노트 사양서(261030) SRS 06-10-10 Queue List, 2026-10-30 개정: "
             "\"DICOM Storage 설정 변경 여부와 관계없이 Queue 등록 당시 저장된 정보를 "
             "기준으로 재전송한다.\" Redmine #25531 종료 댓글에도 같은 문장. "
             "ALM 1.0.12 VP-314 본문에는 없음(SPEC 13절).")


# --- 설정 Storage 기록·비교 (순수 함수) --------------------------------------

_FIELDS = ("Name", "AETitle", "IP", "Port", "Use")


def storage_signature(rows):
    """설정 Storage 행을 비교 가능한 정렬 튜플로 바꾼다. Key 는 비교하지 않는다."""
    out = []
    for row in rows:
        out.append((str(row.get("Name") or ""), str(row.get("AETitle") or ""),
                    str(row.get("IP") or ""), int(row.get("Port") or 0),
                    int(row.get("Use") or 0)))
    return sorted(out)


def plan_target(snapshot, storage_spec, scp_port):
    """시험에 쓸 Storage 와 복원 방식을 정한다.

    실행 전 Use=1 인 설정 Storage 가 있으면 그 서버의 Port 만 바꿔 시험하고,
    끝나면 원래 값으로 되돌린다. 없으면 설정 파일의 Storage 를 새로 등록하고
    끝나면 삭제한다(실행 전에 같은 이름의 행이 있었으면 그 값으로 되돌린다).
    """
    active = [r for r in snapshot if int(r.get("Use") or 0) == 1]
    if active:
        row = active[0]
        spec = {"name": str(row["Name"]), "ae_title": str(row["AETitle"]),
                "ip": str(row["IP"]), "port": int(scp_port)}
        return {"spec": spec, "created": False, "original": dict(row)}
    same = next((r for r in snapshot
                 if str(r.get("Name")) == str(storage_spec["name"])), None)
    spec = {"name": str(storage_spec["name"]),
            "ae_title": str(storage_spec["ae_title"]),
            "ip": str(storage_spec["ip"]), "port": int(scp_port)}
    return {"spec": spec, "created": same is None,
            "original": dict(same) if same else None}


# --- 제품 UI 조작 --------------------------------------------------------------

def _config_rows(db):
    return db.query(
        "CONFIGURATION",
        "SELECT [Key],Name,AETitle,IP,Port,[Use] FROM DICOM_STORAGE "
        "WHERE SCPUseType=@t ORDER BY [Key]", {"t": ds.STORAGE_SCP_USE_TYPE})


def _queue_rows(db, keys):
    if not keys:
        return []
    return db.query("DATA", "SELECT * FROM DICOM_STORAGE_QUEUE WHERE [Key] IN ("
                    + ",".join(str(int(k)) for k in keys) + ") ORDER BY [Key]")


def _job_ports(db, queue_rows):
    keys = sorted({int(r["StorageKey"]) for r in queue_rows
                   if r.get("StorageKey") not in (None, "")})
    if not keys:
        return []
    return db.query("CONFIGURATION",
                    "SELECT [Key],Name,IP,Port,SCPUseType FROM DICOM_STORAGE "
                    "WHERE [Key] IN (" + ",".join(map(str, keys)) + ")")


def _save_storage(ctx, ui, spec, use_only=True):
    """Setting > DICOM > Storage 에 spec 을 저장한다. 저장 행을 DB 로 돌려준다.

    `setup_all` 과 같은 조작 부품(_sync_use / _set_server / 옵션 / Transfer
    Syntax / Update)을 쓴다. Transfer Syntax 를 선언값(Implicit VR LE)으로 두는
    이유: 올바른 Port 로 보냈다면 SCP 가 받아 Done 이 되는 조건이어야, Retry 후
    Failed 가 '등록 당시 정보로 보냈기 때문'이라는 판정이 의미를 가진다.
    """
    ds._open_page(ui, "Storage")
    use_changed = ds._sync_use(ui, ctx.db, "Storage", spec["name"]) if use_only else False
    target, changed, created = ds._set_server(ui, spec)
    if created:
        box = children(target.hwnd, 1)
        if box:
            ui.click(box[0], settle=.3)
            use_changed = True
    option_changed, _ = ds._ensure_storage_options(ui)
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    ts_changed = ds._ensure_storage_transfer_syntax_control(ui, tess)
    if changed or use_changed or option_changed or ts_changed:
        ds._update(ui)
    end = time.time() + 10
    while True:
        rows = ds._saved_rows(ctx.db, "Storage", spec)
        if ds._exact_saved(rows, spec) or time.time() >= end:
            return [r for r in rows if int(r.get("SCPUseType", 0) or 0) == 0] or rows
        time.sleep(1)


def _confirm_popup(ui, before_hwnds, evidence_path=None, timeout=5):
    """삭제 확인 팝업이 뜨면 Yes/OK/Delete 버튼을 누른다. 누른 문구를 돌려준다."""
    from core import screen, uitext
    end = time.time() + timeout
    while time.time() < end:
        new = [c for c in ui.controls(max_depth=8)
               if c.visible and c.hwnd not in before_hwnds
               and c.text in ("TextButton", "Button", "OK", "Yes")]
        if new:
            if evidence_path:
                win = ui.main_window()
                if win:
                    screen.grab(win.rect, path=evidence_path)
            for button in new:
                label = (uitext.ocr(button) or "").strip()
                if label.lower() in ("yes", "ok", "delete", "confirm"):
                    ui.click(button, settle=1.0)
                    return label
            return {"unmatched_buttons": [uitext.ocr(b) for b in new]}
        time.sleep(.3)
    return None


def _delete_storage(ctx, ui, name, evidence_path=None):
    """설정 Storage 에서 name 행을 UI 로 삭제한다. 결과 dict."""
    ds._open_page(ui, "Storage")
    target = next((x for x in ds._server_items(ui) if ds._select_name(ui, x) == name), None)
    if target is None:
        return {"deleted": False, "error": f"SCP List 에 {name!r} 행이 없다"}
    ui.click(target, settle=.4)
    before = {c.hwnd for c in ui.controls(max_depth=8)}
    ui.click([c for c in ui.by_id(2432) if c.visible][0], settle=1.0)
    confirm = _confirm_popup(ui, before, evidence_path=evidence_path)
    gone = lambda: not any(str(r.get("Name")) == name for r in _config_rows(ctx.db))
    end = time.time() + 6
    while time.time() < end and not gone():
        time.sleep(.5)
    updated = False
    if not gone():
        ds._update(ui)
        updated = True
        end = time.time() + 8
        while time.time() < end and not gone():
            time.sleep(.5)
    return {"deleted": gone(), "confirm": confirm, "update_clicked": updated}


def _restore_storage(ctx, ui, plan, snapshot, evidence_dir):
    """설정 Storage 를 실행 전 기록과 같게 되돌린다."""
    out = {}
    if plan["created"]:
        out["delete"] = _delete_storage(ctx, ui, plan["spec"]["name"],
                                        os.path.join(evidence_dir, "queue_retry_delete.png"))
    elif plan["original"]:
        row = plan["original"]
        spec = {"name": str(row["Name"]), "ae_title": str(row["AETitle"]),
                "ip": str(row["IP"]), "port": int(row["Port"])}
        out["saved"] = _save_storage(ctx, ui, spec, use_only=False)
    # Use 상태도 실행 전과 같게 맞춘다(이름별). 같은 이름 중복 행은 손대지 않는다.
    want = {str(r["Name"]): int(r.get("Use") or 0) for r in snapshot}
    now = {str(r["Name"]): int(r.get("Use") or 0) for r in _config_rows(ctx.db)}
    if want and any(now.get(k) != v for k, v in want.items()):
        ds._open_page(ui, "Storage")
        clicked = []
        for item in ds._server_items(ui):
            name = ds._select_name(ui, item)
            if name in want and now.get(name) != want[name]:
                box = children(item.hwnd, 1)
                if box:
                    ui.click(box[0], settle=.3)
                    clicked.append(name)
        if clicked:
            ds._update(ui)
        out["use_clicked"] = clicked
    after = _config_rows(ctx.db)
    out["after"] = [dict(r) for r in after]
    out["ok"] = storage_signature(after) == storage_signature(snapshot)
    out["setting_closed"] = ds._close_setting_window(ui)
    return out


def _make_test_study(ctx, ui):
    """New Patient 로 Local 검사를 만들고 F8 Demo 촬영으로 2D 1장을 얻는다."""
    # Queue 화면 Patient ID 열이 좁아 긴 ID 는 `...` 로 잘린다(2026-11-22 실측:
    # `QRETRY_261122_151933` -> `QRETRY_261122_15...`). 열 안에 다 보이는 짧은
    # 고유 ID 를 쓴다(QR + 일·시·분·초, 10글자).
    pid = f"QR{datetime.now():%d%H%M%S}"
    flows.fill_new_patient(ui, patient_id=pid, patient_name="AUTO^QRETRY^^^",
                           birth_date="1980/01/01", sex="F",
                           study_description="AUTO Queue Retry")
    flows.start_examine_from_new_patient(ui, wait=8, on_duplicate="fail")
    study = None
    end = time.time() + 30
    while time.time() < end and not study:
        study = ctx.db.one(
            "DATA", "SELECT TOP 1 s.[Key],s.StudyInstanceUID FROM STUDY s "
                    "JOIN PATIENT p ON p.[Key]=s.PatientKey WHERE p.PatientID=@pid "
                    "ORDER BY s.[Key] DESC", {"pid": pid})
        time.sleep(1)
    if not study:
        raise RuntimeError(f"시험 검사가 DB 에 생성되지 않았습니다: {pid}")
    acq = flows.demo_acquire(ui, count=1, db=ctx.db, study_key=study["Key"])
    images = ctx.db.query(
        "DATA", "SELECT [Key],InstanceType,ImageInstanceUID FROM INSTANCE "
                "WHERE StudyKey=@k ORDER BY [Key]", {"k": study["Key"]})
    return {"patient_id": pid, "study_key": int(study["Key"]),
            "study_uid": study["StudyInstanceUID"], "acquire": acq,
            "images": images}


def queue_retry(ctx):
    r = TCResult(TC_ID, TITLE)
    evidence_dir = os.path.join(ctx.evidence_root, "ui")
    os.makedirs(evidence_dir, exist_ok=True)
    # 회차마다 이름을 달리해 앞 회차 증거를 덮어쓰지 않는다(2026-11-22: 같은 이름이라
    # 1·2회차 캡처가 3회차로 덮여 수정 전후 비교에 쓰지 못했다).
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot = lambda name: os.path.join(evidence_dir, f"queue_retry_{stamp}_{name}.png")
    ui, plan, snapshot, examine_open = None, None, None, False
    try:
        # --- Step 0: 전제 -------------------------------------------------
        reachable, scp = ds.ensure_storage_reachable(ctx.cfg)
        scp_spec = (ctx.cfg.get("dicom") or {}).get("storage_scp") or {}
        storage_spec = next(s for s in ctx.cfg["dicom"]["servers_to_register"]
                            if s["kind"] == "Storage")
        if not reachable:
            r.blocked(0, "Storage SCP 도달 확인", expected="올바른 Port 의 SCP 연결 가능",
                      actual=scp, note="올바른 Port 로 보내면 성공하는 조건이어야 "
                      "Retry 후 Failed 가 사양 판정의 근거가 된다.")
            return r
        correct_port = int(scp_spec["port"])
        wrong = dq.choose_wrong_port(
            correct_port, lambda p: ds.tcp_open(scp_spec["host"], p),
            preferred=(ctx.cfg.get("queue_retry") or {}).get("wrong_port"))
        if wrong is None:
            r.blocked(0, "연결되지 않는 Port 선택", expected="SCP 호스트에서 닫힌 Port",
                      actual={"host": scp_spec["host"], "checked_from": correct_port + 1},
                      note="열린 Port 는 다른 SCP 가 받을 수 있어 쓰지 않는다.")
            return r
        snapshot = [dict(x) for x in _config_rows(ctx.db)]
        plan = plan_target(snapshot, storage_spec, correct_port)
        r.add(0, "실행 전 Storage 설정 기록과 시험 Port 선택", PASS,
              expected="SCP 도달 + 닫힌 Port + 설정 Storage 기록",
              actual={"scp": scp, "wrong_port": wrong, "correct_port": correct_port,
                      "configured_storage_before": snapshot,
                      "test_storage": plan["spec"]["name"],
                      "restore_by": "UI 삭제" if plan["created"] else "UI 값 복원"},
              note="복원 기준은 실행 전 CONFIGURATION.DICOM_STORAGE(SCPUseType=0) 행이다.")

        ui = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)[0]
        if not flows.ensure_patient_screen(ui):
            r.add(1, "Patient 화면 진입", FAIL, expected="Patient 화면",
                  actual={"landmarks": flows.known_screen(ui)})
            return r

        # --- Step 1: 틀린 Port 로 Storage 저장 ----------------------------
        wrong_spec = dict(plan["spec"], port=wrong)
        saved = _save_storage(ctx, ui, wrong_spec)
        ds._close_setting_window(ui)
        active = ds.active_storage_rows(ctx.db)
        r.assert_true(
            1, "틀린 Port 로 Storage 저장(단일 Use)",
            len(active) == 1 and int(active[0]["Port"]) == wrong
            and str(active[0]["Name"]) == wrong_spec["name"],
            expected=f"{wrong_spec['name']} / Port {wrong} / Use 단일",
            actual={"saved": saved, "active": active},
            note="Setting > DICOM > Storage UI 로 저장하고 DB 로 확인한다.")

        # --- Step 2: 시험 검사와 2D 영상 ----------------------------------
        if not flows.ensure_patient_screen(ui):
            r.add(2, "Patient 화면 복귀", FAIL, expected="Patient 화면",
                  actual={"landmarks": flows.known_screen(ui)})
            return r
        study = _make_test_study(ctx, ui)
        examine_open = True
        two_d = [i for i in study["images"] if int(i["InstanceType"]) == sv.INSTANCE_2D]
        r.assert_true(
            2, "Local 시험 검사 생성과 F8 Demo 2D 촬영", len(two_d) == 1,
            expected="새 Local 검사에 2D 영상 1장",
            actual={k: study[k] for k in ("patient_id", "study_key", "acquire", "images")},
            note="Service Manual 5.2.3 Demo 가상 촬영. 영상 내용은 판정하지 않는다.")
        sop = two_d[0]["ImageInstanceUID"]

        # --- Step 3: Selected Send -> Failed -------------------------------
        before_queue = sv.queue_keys(ctx)
        flows.select_step(ui, 1)
        vp.expand_tools(ui)
        sent = flows.send_current_study(ui, scope="selected")
        new_keys = sv.wait_queue_registered(ctx, before_queue, wait=60,
                                            expected_uids={sop},
                                            source_uids={sop})
        closed = flows.close_examine(ui, option="close", wait=8)
        examine_open = False
        flows.ensure_patient_screen(ui)
        dq.open_queue(ui)
        first = dq.wait_patient_state(ui, study["patient_id"], {"Failed", "Done"},
                                      timeout=240)
        dq.read_storage_rows(ui, evidence_path=shot("01_first_send"))
        q_first = _queue_rows(ctx.db, new_keys)
        r.assert_true(
            3, "틀린 Port 전송 후 Queue 화면 State = Failed", first["state"] == "Failed",
            expected="시험 Patient ID 행의 State 가 Failed",
            actual={"send": sent, "queue_keys": new_keys, "screen": first,
                    "summary": dq.summary(ui), "db_queue_reference": q_first,
                    "job_storage_reference": _job_ports(ctx.db, q_first),
                    "close_examine": closed},
            note="SRS 06-10-10 State 표의 Failed(전송 실패). 판정은 화면 문구, DB 는 참고.")

        # --- Step 4: Port 를 올바르게 고친다 -------------------------------
        dq.close_window(ui)
        flows.ensure_patient_screen(ui)
        fixed = _save_storage(ctx, ui, plan["spec"])
        echo_ok, echo_rows, echo_text, _ = ds._echo(ui, shot("02_echo"))
        ds._close_setting_window(ui)
        active = ds.active_storage_rows(ctx.db)
        r.assert_true(
            4, "Storage Port 를 올바른 값으로 수정(Update)",
            len(active) == 1 and int(active[0]["Port"]) == correct_port and echo_ok,
            expected=f"{plan['spec']['name']} / Port {correct_port} 저장 + C-ECHO 성공",
            actual={"saved": fixed, "active": active,
                    "echo": {"ok": echo_ok, "rows": echo_rows, "ocr": echo_text}},
            note="C-ECHO 는 바뀐 설정으로 보내면 받아질 조건인지 확인하는 대조다.")

        # --- Step 5: Retry -------------------------------------------------
        flows.ensure_patient_screen(ui)
        dq.open_queue(ui)
        db_before = _queue_rows(ctx.db, new_keys)
        try:
            prior = {o.get("SOPInstanceUID") for o in sv.received(
                ctx, study["patient_id"], study_uids={study["study_uid"]})}
        except Exception as exc:                                  # noqa: BLE001
            prior = f"조회 실패: {type(exc).__name__}"
        retry_since = datetime.now().strftime("%Y/%m/%d %H:%M:%S.000")
        retry = dq.retry_patient_row(ui, study["patient_id"])
        dq.read_storage_rows(ui, evidence_path=shot("03_after_retry"))
        time.sleep(3)
        db_after = _queue_rows(ctx.db, new_keys)
        try:
            arrived = sorted(o.get("SOPInstanceUID") for o in sv.received(
                ctx, study["patient_id"], study_uids={study["study_uid"]}))
        except Exception as exc:                                  # noqa: BLE001
            arrived = f"조회 실패: {type(exc).__name__}"
        try:
            log = dq.retry_log_events(
                dq.read_viewer_log_tail(ctx.cfg["data_dir"], datetime.now()),
                retry_since, new_keys[0]) if len(new_keys) == 1 else None
        except Exception as exc:                                  # noqa: BLE001
            log = {"error": f"{type(exc).__name__}: {exc}"}
        verdict, reason = dq.evaluate_retry(
            retry["states"], retry["final"],
            db_before[0] if len(db_before) == 1 else db_before,
            db_after[0] if len(db_after) == 1 else db_after,
            log_states=(log or {}).get("states"))
        r.assert_true(
            5, "Port 수정 후 Retry: 등록 당시 정보로 재전송(State = Failed)",
            retry["clicked"] and verdict == "pass",
            expected="Retry 후 재전송 신호가 있고 State 가 다시 Failed",
            actual={"verdict": verdict, "reason": reason, "retry": retry,
                    "summary": dq.summary(ui),
                    "db_queue_before_reference": db_before,
                    "db_queue_after_reference": db_after,
                    "job_storage_reference": _job_ports(ctx.db, db_after),
                    "viewer_log_reference": log,
                    "scp_received_before_reference": sorted(prior) if isinstance(prior, set) else prior,
                    "scp_received_after_reference": arrived},
            note=SPEC_NOTE + " Done 이면 바뀐 설정으로 보낸 것이라 사양과 다르다. "
                 "재전송 신호가 없으면 Retry 동작을 확인하지 못한 것이라 FAIL 이다.")
    except Exception as exc:
        r.abort(0, f"{TC_ID} 실행", exc)
    finally:
        _cleanup(ctx, r, ui, plan, snapshot, examine_open, evidence_dir)
    return r


def _cleanup(ctx, r, ui, plan, snapshot, examine_open, evidence_dir):
    if ui is None or plan is None:
        return
    try:
        dq.close_window(ui)
        if examine_open:
            flows.close_examine(ui, option="close", wait=8)
        flows.ensure_patient_screen(ui)
        out = _restore_storage(ctx, ui, plan, snapshot, evidence_dir)
        r.cleanup(0, "Storage 설정 복원", PASS if out["ok"] else FAIL,
                  expected={"configured_storage": snapshot},
                  actual=out,
                  note="실행 전 SCPUseType=0 행(Name/AE/IP/Port/Use)과 비교한다. "
                       "시험 검사와 Queue 행, 제품이 만든 작업 사본 행은 지우지 않는다.")
    except Exception as exc:                                     # noqa: BLE001
        r.cleanup(0, "Storage 설정 복원", FAIL,
                  expected={"configured_storage": snapshot},
                  actual=f"{type(exc).__name__}: {exc}",
                  note="복원하지 못했다. Setting > DICOM > Storage 를 직접 확인해야 한다.")


def run(ctx):
    return [queue_retry(ctx)]
