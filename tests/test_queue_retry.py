"""REQ-QUEUE-001: Queue Retry 사양 시험의 화면 판독·판정·복원 계획 (제품을 조작하지 않는다)."""
from types import SimpleNamespace

from core import dicom_queue as dq
from tests import queue_retry as qr


def test_parse_state_reads_first_column_and_tolerates_small_ocr_errors():
    assert dq.parse_state("Failed Image STORAGE AUTO QRETRY_261122_151000") == "Failed"
    assert dq.parse_state("Faiied Image STORAGE") == "Failed"
    assert dq.parse_state("Done Image STORAGE") == "Done"
    assert dq.parse_state("Sendinq Image") == "Sending"
    # 어느 값에도 가깝지 않으면 추측하지 않는다.
    assert dq.parse_state("Image STORAGE QRETRY") is None
    assert dq.parse_state("") is None


def test_rows_for_patient_matches_only_the_test_patient_despite_ocr_noise():
    rows = [{"text": "Failed Image STORAGE AUTO QRETRY QRETRY_26112215I000"},
            {"text": "Done Image STORAGE OTHER BF_AUTO_261122_150000"}]
    hits = dq.rows_for_patient(rows, "QRETRY_261122_151000")
    assert hits == [rows[0]]
    # 일치하는 행이 없으면 다른 행(첫 행)으로 대체하지 않는다.
    assert dq.rows_for_patient(rows, "QRETRY_261122_999999") == []
    assert dq.rows_for_patient(rows, "") == []


def test_choose_wrong_port_skips_open_ports_and_respects_preference():
    opened = {11117, 11118}
    assert dq.choose_wrong_port(11116, lambda p: p in opened) == 11119
    assert dq.choose_wrong_port(11116, lambda p: False, preferred=12000) == 12000
    # 지정 Port 가 열려 있으면 다른 번호로 바꾸지 않고 None 이다.
    assert dq.choose_wrong_port(11116, lambda p: True, preferred=12000) is None
    assert dq.choose_wrong_port(11116, lambda p: True, span=3) is None


def test_evaluate_retry_verdicts():
    row = {"Key": 5, "State": 4}
    assert dq.evaluate_retry(["Pending", "Failed"], "Failed")[0] == "pass"
    # 화면 중간 상태를 놓쳐도 DB 행 변화가 있으면 재전송 신호로 본다.
    assert dq.evaluate_retry(["Failed"], "Failed", row, {"Key": 5, "State": 4,
                                                         "RetryCount": 1})[0] == "pass"
    # Done 은 바뀐 설정으로 보냈다는 뜻이라 사양과 다르다.
    assert dq.evaluate_retry(["Sending", "Done"], "Done")[0] == "done"
    # 신호가 하나도 없으면 PASS 로 두지 않는다.
    assert dq.evaluate_retry(["Failed"], "Failed", row, dict(row))[0] == "no_signal"
    assert dq.evaluate_retry([None], None)[0] == "unread"
    assert dq.evaluate_retry(["Sending"], "Sending")[0] == "other"


def test_storage_signature_ignores_key_and_order():
    a = [{"Key": 1, "Name": "S", "AETitle": "AE", "IP": "1.2.3.4", "Port": 11116, "Use": 1}]
    b = [{"Key": 9, "Name": "S", "AETitle": "AE", "IP": "1.2.3.4", "Port": "11116", "Use": "1"}]
    assert qr.storage_signature(a) == qr.storage_signature(b)
    c = [dict(b[0], Port=11119)]
    assert qr.storage_signature(a) != qr.storage_signature(c)
    assert qr.storage_signature([]) == []


def test_plan_target_reuses_active_storage_or_creates_and_deletes():
    cfg = {"name": "STORAGE", "ae_title": "STORAGE_SCP", "ip": "10.0.0.1", "port": 11116}
    empty = qr.plan_target([], cfg, 11116)
    assert empty["created"] is True and empty["original"] is None
    assert empty["spec"] == {"name": "STORAGE", "ae_title": "STORAGE_SCP",
                             "ip": "10.0.0.1", "port": 11116}

    active = {"Key": 3, "Name": "PACS", "AETitle": "PACS_AE", "IP": "10.0.0.1",
              "Port": 104, "Use": 1}
    plan = qr.plan_target([active], cfg, 11116)
    assert plan["created"] is False and plan["original"] == active
    assert plan["spec"]["name"] == "PACS" and plan["spec"]["port"] == 11116

    inactive = dict(active, Name="STORAGE", Use=0)
    plan = qr.plan_target([inactive], cfg, 11116)
    assert plan["created"] is False and plan["original"] == inactive


class _FakeUi:
    def __init__(self):
        self.clicked = []

    def by_id(self, ctrl_id):
        return [SimpleNamespace(visible=True, ctrl_id=ctrl_id, rect=(0, 0, 10, 10))]

    def click(self, target, settle=0):
        self.clicked.append(getattr(target, "ctrl_id", target))


def test_retry_patient_row_records_transition_and_stops_on_failed(monkeypatch):
    ui = _FakeUi()
    row = lambda state: {"text": f"{state} Image QRETRY_1", "state": state,
                         "click": "row"}
    sequence = iter([row("Failed"), row("Pending"), row("Sending"), row("Failed")])
    monkeypatch.setattr(dq, "patient_row", lambda ui, pid: (next(sequence), []))
    monkeypatch.setattr(dq.time, "sleep", lambda s: None)
    out = dq.retry_patient_row(ui, "QRETRY_1", watch=30)
    assert out["clicked"] and out["before"] == "Failed"
    assert out["states"] == ["Pending", "Sending", "Failed"]
    assert out["final"] == "Failed"
    assert ui.clicked == ["row", dq.STORAGE_RETRY]


def test_retry_patient_row_does_not_click_when_test_row_is_missing(monkeypatch):
    ui = _FakeUi()
    monkeypatch.setattr(dq, "patient_row",
                        lambda ui, pid: (None, [{"text": "Done Image OTHER"}]))
    out = dq.retry_patient_row(ui, "QRETRY_1")
    assert out["clicked"] is False and ui.clicked == []
    assert out["rows"] == ["Done Image OTHER"]


# 2026-11-22 실제 회차의 Queue 화면 캡처를 OCR 한 문구. 열이 좁아 Patient ID 가 잘렸다.
REAL_ROW = "Failed - Image STORAGE AUTO QRETRY QRETRY_261122_15..."


def test_truncated_patient_id_from_real_capture_matches_by_prefix_only():
    rows = [{"text": REAL_ROW}]
    assert dq.rows_for_patient(rows, "QRETRY_261122_151933") == rows
    assert dq.parse_state(REAL_ROW) == "Failed"
    # 잘리지 않은 다른 ID 는 접두어로 일치시키지 않는다.
    assert dq.rows_for_patient([{"text": "Failed - Image STORAGE A QRETRY_261122_15"}],
                               "QRETRY_261122_151933") == []
    # 잘린 부분이 너무 짧으면 구별할 수 없어 일치로 보지 않는다.
    assert dq.rows_for_patient([{"text": "Failed - Image STORAGE A QR..."}],
                               "QRETRY_261122_151933") == []
    # Patient Name 칸의 문구만으로는 일치시키지 않는다(마지막 열 기준).
    assert dq.rows_for_patient([{"text": "Failed - Image QR22151933 OTHER_ID"}],
                               "QR22151933") == []


def test_rows_from_ocr_data_groups_lines_and_drops_header():
    data = {"text": ["State", "Commitment", "Patient", "ID", "Failed", "-", "Image",
                     "QR22151933", "Done", "Image", "QR22150000"],
            "conf": ["90"] * 11,
            "block_num": [1] * 11, "par_num": [1] * 11,
            "line_num": [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3],
            "left": [10, 60, 400, 460, 10, 80, 120, 500, 10, 120, 500],
            "top": [5, 5, 5, 5, 100, 100, 100, 100, 190, 190, 190],
            "height": [20] * 11}
    rows = dq.rows_from_ocr_data(data, scale=3, left=188, top=210)
    assert [r["text"] for r in rows] == ["Failed - Image QR22151933", "Done Image QR22150000"]
    assert [r["state"] for r in rows] == ["Failed", "Done"]
    assert rows[0]["y"] == 210 + 110 // 3 and rows[0]["click"] == (218, rows[0]["y"])
    assert dq.rows_for_patient(rows, "QR22151933") == [rows[0]]


def test_merge_rows_keeps_selected_row_seen_by_only_one_variant():
    auto = [{"text": "Failed - Image STORAGE AUTO QRETRY QRETRY_261122_15...",
             "state": "Failed", "y": 259}]
    binary = [{"text": "Failed - Image STORAGE AUTO QRETRY QRETRY_261122_15...",
               "state": "Failed", "y": 258},
              {"text": "Failed - Image STORAGE AUTO QRETRY QR22152904",
               "state": "Failed", "y": 294}]
    rows = dq.merge_rows(auto, binary)
    assert len(rows) == 2 and rows[0]["y"] in (258, 259) and rows[1]["y"] == 294
    assert dq.rows_for_patient(rows, "QR22152904") == [rows[1]]
    # 같은 높이면 State 를 읽은 후보를 남긴다.
    weak = [{"text": "Fa1|ed Image QR22152904", "state": None, "y": 295}]
    assert dq.merge_rows(weak, binary)[1]["state"] == "Failed"


def test_retry_patient_row_stops_when_row_stays_unreadable(monkeypatch):
    ui = _FakeUi()
    first = {"text": "Failed Image QR1", "state": "Failed", "click": "row"}
    calls = iter([(first, [])] + [(None, [])] * 1000)
    clock = {"t": 0.0}
    monkeypatch.setattr(dq, "patient_row", lambda ui, pid: next(calls))
    monkeypatch.setattr(dq.time, "time", lambda: clock["t"])
    monkeypatch.setattr(dq.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    out = dq.retry_patient_row(ui, "QR1", watch=120, poll=1.0)
    assert out["final"] is None and len(out["states"]) <= dq.UNREAD_LIMIT + 2
    assert dq.evaluate_retry(out["states"], out["final"])[0] == "unread"


# 2026-11-22 2회차 Viewer 로그 원문(Queue Key 2). Port 수정 뒤 Retry 가 11117 로 연결했다.
REAL_LOG = """[2026/11/22 15:30:07.578] [Info]           [DICOM]          [Storage>      Server connection failed]
[2026/11/22 15:30:08.323] [Info]           [DICOM]          [Update Queue Storage Item : 2(Failed, -)]
[2026/11/22 15:31:04.922] [Info]           [DICOM]          [Update Queue Storage Item : 2(Pending, -)]
[2026/11/22 15:31:04.927] [Info]           [DICOM]          [Storage Item(2) state change to Sending]
[2026/11/22 15:31:04.932] [Info]           [DICOM]          [Update Queue Storage Item : 2(Sending, -)]
[2026/11/22 15:31:04.934] [Info]           [DICOM]          [Storage>      Connecting to 10.13.0.222:11117]                    [SYSTEM::CDICOMStorage::SendInstance]
[2026/11/22 15:31:25.992] [Info]           [DICOM]          [Storage>      Server connection failed]
[2026/11/22 15:31:26.072] [Info]           [DICOM]          [Update Queue Storage Item : 2(Failed, -)]
[2026/11/22 15:31:30.000] [Info]           [DICOM]          [Update Queue Storage Item : 12(Done, -)]""".splitlines()


def test_retry_log_events_from_real_log():
    out = dq.retry_log_events(REAL_LOG, "2026/11/22 15:31:00.000", 2)
    assert out["states"] == ["Pending", "Sending", "Failed"]
    assert out["connect"] == ["10.13.0.222:11117"]
    # Retry 전 줄과 다른 Key(12) 줄은 넣지 않는다.
    assert all("15:30:" not in line and ": 12(" not in line for line in out["lines"])
    verdict, reason = dq.evaluate_retry([None, "Failed"], "Failed",
                                        log_states=out["states"])
    assert verdict == "pass" and "제품 로그" in reason
    # 로그 신호가 있어도 화면 최종값이 Done 이면 사양과 다르다.
    assert dq.evaluate_retry(["Done"], "Done", log_states=out["states"])[0] == "done"


def test_merge_rows_does_not_let_longer_noisy_text_hide_the_test_row():
    # 2026-11-22 3회차 캡처의 실제 두 판독 결과(같은 행).
    auto = [{"text": "Failed - Image STORAGE AUTO QRETRY QR22153835", "state": "Failed", "y": 119}]
    binary = [{"text": "Failed - Image STORAGE AUTO OQRETRY QOR22153835", "state": "Failed", "y": 119}]
    rows = dq.merge_rows(auto, binary)
    assert len(rows) == 1 and rows[0]["text"] == auto[0]["text"]
    assert dq.rows_for_patient(rows, "QR22153835") == rows
    # 순서를 바꿔 넘겨도 후보를 모두 보므로 찾는다.
    assert dq.rows_for_patient(dq.merge_rows(binary, auto), "QR22153835")


def test_parse_state_accepts_truncated_state_column():
    # 2026-11-22 4회차: Retry 직후 화면 문구.
    assert dq.parse_state("Send... - Image STORAGE AUTO QRETRY QR22154738") == "Sending"
    assert dq.parse_state("Pend... - Image STORAGE") == "Pending"
    assert dq.parse_state("Stop... - Image") == "Stopped"
    # 3글자 이하 조각이나 여러 값에 걸리는 조각은 추측하지 않는다.
    assert dq.parse_state("Se... - Image") is None


def test_decode_log_handles_utf16_viewer_log():
    raw = ("\ufeff" + "\r\n".join(REAL_LOG[2:5])).encode("utf-16-le")
    lines = dq.decode_log(raw, True)
    out = dq.retry_log_events(lines, "2026/11/22 15:31:00.000", 2)
    assert out["states"] == ["Pending", "Sending"]
    assert dq.decode_log("a\r\nb".encode("utf-8"), False) == ["a", "b"]
