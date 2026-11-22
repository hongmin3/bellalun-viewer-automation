# -*- coding: utf-8 -*-
r"""SRS 06-10-10 Queue List Retry — 등록 당시 Storage 정보로 재전송. SPEC REQ-QUEUE-001.

체크리스트 TC가 아니다. `run-regression --select queue-retry`로 고를 때만 WF_04 자리 뒤에서
실행한다(`core/selection.py`). 선행 단계 WF_01·02가 만든 `DATA_FLOW_MWL_01` 2D 영상을 쓴다.

## 근거

- 기존 원노트 사양서(261030) 828쪽 SRS 06-10-10 Queue List, Revision "2026-10-30. Retry 사양추가":
  "Retry 버튼을 눌러 선택한 항목을 다시 전송할 수 있다." 아래
  "DICOM Storage 설정 변경 여부와 관계없이 Queue 등록 당시 저장된 정보를 기준으로 재전송한다."
- Redmine #25531(종료, Close 사유 Spec): Port를 바꾼 뒤 Failed 항목을 Retry하면 변경 전 Port로
  연결되어 다시 Failed로 표시된다. 연구소 회신은 이것이 설계 동작이며 사양서에 추가한다는 것이다.
- Operation Manual V1.0.12 문단 4035: "전송 실패한 항목을 선택 후 Retry 버튼을 클릭하여 다시 전송".

## 판정

Queue 화면에 보이는 State가 판정 기준이다. Retry 뒤 다시 Failed면 PASS다. Done이면 지금 설정으로
보낸 것이므로 FAIL이다. Failed로 남아도 재시도 신호(화면의 다른 State, DB State 변화, Viewer 로그의
같은 Queue 항목 상태 변화)가 하나도 없으면 다시 보냈는지 확인할 수 없어 FAIL로 남긴다.
Storage SCP 수신 건수, 작업 사본 행의 Port, DB State 값, Viewer 로그의 접속 대상은 참고 근거다.
"""

from __future__ import annotations

import os
import threading
import time

from core import flows, queue_ui
from core import send_verify as sv
from core import viewer_processing as vp
from core.dicom_settings import (_close_setting_window, _open_page, _set_server, _update,
                                 active_storage_rows, ensure_storage_reachable, tcp_open)
from core.result import FAIL, PASS, TCResult

TC_ID = "SPEC_QueueList_Retry"
TITLE = "SRS 06-10-10 Queue List Retry — 등록 당시 Storage 정보로 재전송"
SPEC_NOTE = ("기존 원노트 사양서(261030) 828쪽 SRS 06-10-10 Queue List(2026-10-30 Retry 사양 추가): "
             "\"DICOM Storage 설정 변경 여부와 관계없이 Queue 등록 당시 저장된 정보를 기준으로 "
             "재전송한다.\" Redmine #25531(사양으로 종료)과 같은 동작이다.")
FAILED_WAIT = 120
RETRY_WAIT = 90


# --- 화면 없이 시험하는 판단 ----------------------------------------------
def choose_closed_port(host, port, probe=tcp_open, span=10):
    """같은 호스트에서 연결이 거절되는 포트(원래 포트보다 큰 쪽부터)."""
    for candidate in range(int(port) + 1, int(port) + 1 + span):
        if candidate != int(port) and not probe(host, candidate):
            return candidate
    return None


def retry_verdict(final_state, ui_after, db_before, db_after, log_attempts):
    """Retry 뒤 화면 State와 재시도 신호로 판정한다. 반환: (status, 사유, 신호 목록).

    log_attempts는 Viewer 로그에서 읽은 이 Queue 항목의 상태 목록이다.
    """
    signals = []
    if any(state and state != "Failed" for state in ui_after):
        signals.append("화면 State 변화")
    if any(state != db_before for state in db_after):
        signals.append("DB State 변화")
    if any(state != "Failed" for state in log_attempts):
        signals.append("Viewer 로그 Queue 상태 변화")
    if final_state == "Done":
        return FAIL, "Retry가 현재 Storage 설정으로 전송해 Done이 됐다(사양과 다름).", signals
    if final_state != "Failed":
        return FAIL, f"Retry 뒤 Queue 화면 State를 Failed로 읽지 못했다: {final_state!r}", signals
    if not signals:
        return FAIL, "Retry 뒤에도 Failed지만 재시도가 일어났다는 신호가 없다.", signals
    return PASS, "등록 당시 Port로 다시 보내 다시 Failed가 됐다.", signals


# --- 제품 조작 ---------------------------------------------------------------
def _spec_of(row, port=None):
    return {"name": str(row["Name"]), "ae_title": str(row["AETitle"]), "ip": str(row["IP"]),
            "port": int(port if port is not None else row["Port"])}


def _setting_row(ctx, key):
    return ctx.db.one("CONFIGURATION",
                      "SELECT [Key],Name,AETitle,IP,Port,[Use],SCPUseType FROM DICOM_STORAGE "
                      "WHERE [Key]=@k", {"k": int(key)}) or {}


def _apply_port(ctx, ui, original, port, timeout=10):
    """Setting > DICOM > Storage에서 같은 행의 Port만 바꾸고 DB로 확인한다."""
    _open_page(ui, "Storage")
    _, changed, created = _set_server(ui, _spec_of(original, port))
    if created:
        raise RuntimeError("대상 Storage 행을 목록에서 찾지 못해 새 행이 만들어졌습니다.")
    if changed:
        _update(ui)
    closed = _close_setting_window(ui)
    end = time.time() + timeout
    row = _setting_row(ctx, original["Key"])
    while int(row.get("Port") or 0) != int(port) and time.time() < end:
        time.sleep(1)
        row = _setting_row(ctx, original["Key"])
    return {"changed": changed, "setting_closed": closed, "row": row,
            "ok": int(row.get("Port") or 0) == int(port)}


def _queue_job(ctx, key):
    job = ctx.db.one("DATA", "SELECT [Key],State,StorageKey,OriginalStorageKey,InstanceUID,DataType "
                             "FROM DICOM_STORAGE_QUEUE WHERE [Key]=@k", {"k": int(key)}) or {}
    if job.get("StorageKey") is not None:
        job["storage_copy"] = _setting_row(ctx, job["StorageKey"])
    return job


def _target(rows, patient_id):
    """이번 항목 행. 같은 환자의 행이 여럿이면 Done이 아닌 행이 하나일 때만 고른다."""
    row = queue_ui.pick_row(rows, patient_id)
    if row is not None:
        return row
    open_rows = [r for r in rows if r["state"] != "Done"
                 and any(queue_ui.contains_id(t, patient_id) for t in r["texts"].values())]
    return open_rows[0] if len(open_rows) == 1 else None


def _watch_row(ui, ctx, patient_id, want, timeout, shot_dir, label):
    """화면에서 이번 행의 State가 want 중 하나가 될 때까지 읽는다."""
    end = time.time() + timeout
    history, last = [], {}
    n = 0
    while True:
        n += 1
        path = os.path.join(shot_dir, f"{label}_{n:02}.png")
        rows, _ = queue_ui.read_rows(ui, evidence_path=path)
        row = _target(rows, patient_id)
        last = {"row": row, "rows": rows, "shot": path}
        history.append(row["state"] if row else None)
        if row and row["state"] in want:
            return {"state": row["state"], "history": history, **last}
        if time.time() >= end:
            return {"state": row["state"] if row else None, "history": history, **last}
        time.sleep(1.5)


class _DbStatePoller(threading.Thread):
    """Retry 전후 DB State를 짧은 간격으로 기록한다(참고 근거)."""

    def __init__(self, ctx, key, interval=.2):
        super().__init__(daemon=True)
        self.ctx, self.key, self.interval = ctx, int(key), interval
        self.states, self.stop_event = [], threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            try:
                value = self.ctx.db.scalar("DATA", "SELECT State FROM DICOM_STORAGE_QUEUE "
                                                   "WHERE [Key]=@k", {"k": self.key})
                if not self.states or self.states[-1] != value:
                    self.states.append(value)
            except Exception:                                  # noqa: BLE001
                pass
            self.stop_event.wait(self.interval)

    def finish(self):
        self.stop_event.set()
        self.join(timeout=5)
        return self.states


def _fixture_sop(ctx, patient_id):
    row = ctx.db.one(
        "DATA", "SELECT TOP 1 s.[Key] FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
                "WHERE p.PatientID=@pid AND EXISTS (SELECT 1 FROM INSTANCE i WHERE "
                "i.StudyKey=s.[Key] AND i.InstanceType=@t) ORDER BY s.[Key] DESC",
        {"pid": patient_id, "t": sv.INSTANCE_2D})
    return row


def queue_retry(ctx):
    r = TCResult(TC_ID, TITLE)
    cfg = ctx.cfg
    patient_id = (cfg.get("xipl") or {}).get("test_patient_id", "DATA_FLOW_MWL_01")
    shot_dir = os.path.join(ctx.evidence_root, "ui", "queue_retry")
    os.makedirs(shot_dir, exist_ok=True)
    ui, original, view_open, port_changed = None, None, False, False
    try:
        # --- Step 0: 전제 --------------------------------------------------
        reachable, storage = ensure_storage_reachable(cfg)
        rows = active_storage_rows(ctx.db)
        if not reachable or len(rows) != 1:
            r.blocked(0, "Storage 설정과 SCP 도달", note="설정된 Storage 1행과 도달 가능한 SCP가 필요하다.",
                      expected="활성 Storage 1행 + SCP running/TCP 연결",
                      actual={"active_rows": rows, "scp": storage})
            return r
        original = dict(rows[0])
        wrong = choose_closed_port(original["IP"], original["Port"])
        if wrong is None:
            r.blocked(0, "틀린 Port 후보", note="같은 호스트에서 연결이 거절되는 포트를 찾지 못했다.",
                      expected=f"{original['IP']}의 닫힌 포트", actual=None)
            return r
        if not _fixture_sop(ctx, patient_id):
            r.blocked(0, "시험 2D 검사", note="WF_01·02가 만든 2D 검사가 없다.",
                      expected=f"{patient_id}의 2D 영상", actual=None)
            return r
        r.add(0, "전제: Storage 설정·닫힌 Port·시험 검사", PASS,
              expected="활성 Storage 1행, 원래 Port 연결 가능, 같은 호스트의 닫힌 Port",
              actual={"original": original, "wrong_port": wrong, "scp": storage},
              note="틀린 Port는 연결이 거절되는 포트를 고른다. 원래 Port로는 정상 수신된다.")

        ui = flows.cold_start(cfg, ctx.db, force_restart=True)[0]
        if not flows.ensure_patient_screen(ui):
            r.add(1, "Patient 화면 진입", FAIL, expected="Patient 화면",
                  actual={"landmarks": flows.known_screen(ui)})
            return r

        # --- Step 1: 틀린 Port로 변경 ----------------------------------------
        applied = _apply_port(ctx, ui, original, wrong)
        port_changed = True
        r.assert_true(1, "Storage Port를 닫힌 포트로 변경", applied["ok"],
                      expected=f"{original['Name']} 행 Port={wrong} (AE·IP 유지)", actual=applied,
                      note="Setting > DICOM > Storage에서 같은 행의 Port만 바꾸고 Update했다. DB로 확인한다.")

        # --- Step 2: 2D Selected 전송 ---------------------------------------
        opened = flows.open_examined_study(ui, patient_id, card="oldest", data_dir=cfg["data_dir"])
        view_open = True
        flows.select_step(ui, 1)
        vp.expand_tools(ui)
        identity = sv.db_identity(ctx, patient_id, study_key=opened["study_key"])
        sops = set(identity["by_type"].get(sv.INSTANCE_2D, set()))
        if len(sops) != 1:
            r.blocked(2, "선택한 2D 단계의 원본 SOP", note="선택 단계의 2D SOP가 1건이어야 한다.",
                      expected=1, actual=sorted(sops))
            return r
        before_received = {o.get("SOPInstanceUID") for o in
                           sv.received(ctx, patient_id, study_uids=identity["study_uids"])}
        if sops & before_received:
            r.blocked(2, "전송 전 SCP 수신 여부", note="이미 수신된 SOP는 새 수신을 구별할 수 없다.",
                      expected="시험 SOP 미수신", actual=sorted(sops & before_received))
            return r
        before_queue = sv.queue_keys(ctx)
        sent = flows.send_current_study(ui, scope="selected")
        queue_evidence = {}
        new_keys = sv.wait_queue_registered(ctx, before_queue, wait=60, expected_uids=sops,
                                            source_uids=identity["sop_uids"],
                                            diagnostics=queue_evidence)
        r.assert_true(2, "2D 영상을 Selected로 전송해 Queue 등록", len(new_keys) == 1
                      and set(queue_evidence.get("queue_observed_uids", [])) == sops,
                      expected="선택한 2D SOP 1건이 새 Queue 항목으로 등록",
                      actual={"scope": sent, "queue_added": new_keys, "observation": queue_evidence,
                              "study_key": opened["study_key"], "sop": sorted(sops)},
                      note="View 화면 Send는 SRS 03-10-50에 따라 Dose SR을 보내지 않으므로 1건이다.")
        key = new_keys[0]
        flows.close_view_study(ui)
        view_open = False

        # --- Step 3: Queue 화면 Failed ---------------------------------------
        queue_ui.open_queue(ui)
        failed = _watch_row(ui, ctx, patient_id, {"Failed", "Done"}, FAILED_WAIT, shot_dir, "step3")
        job = _queue_job(ctx, key)
        r.assert_true(3, "Queue 화면에서 이번 항목 State = Failed", failed["state"] == "Failed",
                      expected="닫힌 Port로 등록된 항목의 State가 Failed",
                      actual={"state": failed["state"], "history": failed["history"],
                              "row": failed["row"], "screenshot": failed["shot"],
                              "counters": queue_ui.read_counters(ui),
                              "reference_db": {"queue_key": key, "state": job.get("State"),
                                               "job_copy_port": (job.get("storage_copy") or {}).get("Port"),
                                               "original_storage_key": job.get("OriginalStorageKey")}},
                      note="판정은 화면 State다. DB State와 작업 사본 행 Port는 참고로만 남긴다.")
        queue_ui.close_window(ui)

        # --- Step 4: Port 원래대로 --------------------------------------------
        restored = _apply_port(ctx, ui, original, original["Port"])
        port_changed = not restored["ok"]
        job = _queue_job(ctx, key)
        r.assert_true(4, "Storage Port를 원래 값으로 되돌림", restored["ok"],
                      expected=f"{original['Name']} 행 Port={original['Port']}",
                      actual={**restored, "reference_job_copy_port":
                              (job.get("storage_copy") or {}).get("Port")},
                      note="작업 사본 행(SCPUseType<>0)의 Port는 바뀌지 않는 것이 등록 당시 정보다(참고).")

        # --- Step 5: Retry ---------------------------------------------------
        queue_ui.open_queue(ui)
        rows_before, _ = queue_ui.read_rows(ui, evidence_path=os.path.join(shot_dir, "step5_before.png"))
        target = queue_ui.pick_row(rows_before, patient_id, state="Failed")
        if target is None:
            r.add(5, "Retry할 Failed 행 특정", FAIL, expected="이번 환자의 Failed 행 1개",
                  actual={"rows": rows_before},
                  note="행을 하나로 특정하지 못해 Retry를 누르지 않았다.")
            return r
        queue_ui.select_row(ui, target)
        log_path = queue_ui.viewer_log_path(cfg["data_dir"])
        mark = queue_ui.log_mark(log_path)
        db_before = ctx.db.scalar("DATA", "SELECT State FROM DICOM_STORAGE_QUEUE WHERE [Key]=@k",
                                  {"k": key})
        poller = _DbStatePoller(ctx, key)
        poller.start()
        try:
            tip = queue_ui.click_retry(ui)
            time.sleep(2)
            after = _watch_row(ui, ctx, patient_id, {"Done"}, RETRY_WAIT, shot_dir, "step5")
            # Failed는 Retry 직후에도 남아 있을 수 있어 즉시 끝내지 않는다. 로그와 화면을
            # 다시 읽어 마지막 상태를 확정한다.
            log_events = queue_ui.queue_log_events(queue_ui.log_lines_since(log_path, mark), key)
        finally:
            db_after = poller.finish()
        final, _ = queue_ui.read_rows(ui, evidence_path=os.path.join(shot_dir, "step5_final.png"))
        final_row = _target(final, patient_id)
        final_state = final_row["state"] if final_row else after["state"]
        received_after = {o.get("SOPInstanceUID") for o in
                          sv.received(ctx, patient_id, study_uids=identity["study_uids"])}
        status, reason, signals = retry_verdict(final_state, after["history"], db_before,
                                                db_after, log_events["states"])
        job = _queue_job(ctx, key)
        r.add(5, "Retry 뒤 Queue 화면 State", status,
              expected="Retry 뒤 등록 당시(닫힌) Port로 다시 보내 State가 다시 Failed",
              actual={"final_state": final_state, "reason": reason, "signals": signals,
                      "ui_history": after["history"], "retry_tooltip": tip,
                      "screenshot": os.path.join(shot_dir, "step5_final.png"),
                      "counters": queue_ui.read_counters(ui),
                      "reference": {"db_state_before": db_before, "db_states_after": db_after,
                                    "viewer_log_states": log_events["states"],
                                    "viewer_log_connects": log_events["connects"],
                                    "viewer_log_lines": log_events["lines"][:12],
                                    "registered_target": f"{original['IP']}:{wrong}",
                                    "scp_received_sop": sorted(sops & received_after),
                                    "job_copy_port": (job.get("storage_copy") or {}).get("Port"),
                                    "current_setting_port": original["Port"]}},
              note=SPEC_NOTE + " 판정은 화면 State다. SCP 수신·DB·Viewer 로그(상태 줄과 "
                                 "`Storage> Connecting to` 접속 대상)는 참고 근거다.")
    except Exception as exc:                                   # noqa: BLE001
        r.abort(0, f"{TC_ID} 실행", exc)
    finally:
        _cleanup(ctx, r, ui, original, view_open, port_changed)
    return r


def _cleanup(ctx, r, ui, original, view_open, port_changed):
    if ui is None:
        return
    try:
        if queue_ui.is_open(ui):
            queue_ui.close_window(ui)
        if view_open:
            flows.close_view_study(ui)
    except Exception as exc:                                   # noqa: BLE001
        r.cleanup(0, "DICOM 창·검사 닫기", FAIL, actual=f"{type(exc).__name__}: {exc}")
    if original is None:
        return
    try:
        if port_changed:
            _apply_port(ctx, ui, original, original["Port"])
        row = _setting_row(ctx, original["Key"])
        same = all(str(row.get(k)) == str(original.get(k)) for k in ("Name", "AETitle", "IP", "Port", "Use"))
        r.cleanup(0, "Storage 설정 원복 확인", PASS if same else FAIL,
                  expected={k: original.get(k) for k in ("Name", "AETitle", "IP", "Port", "Use")},
                  actual=row, note="시험 전 DB 값과 이름·AE·IP·Port·Use가 같아야 한다.")
    except Exception as exc:                                   # noqa: BLE001
        r.cleanup(0, "Storage 설정 원복 확인", FAIL, actual=f"{type(exc).__name__}: {exc}",
                  note="Storage Port가 시험 값으로 남았을 수 있다. Setting에서 확인한다.")


def run(ctx):
    return [queue_retry(ctx)]
