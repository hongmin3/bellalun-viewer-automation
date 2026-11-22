# -*- coding: utf-8 -*-
"""Queue List Retry 시험의 화면 없는 판단 부분.

Validates: REQ-QUEUE-001, REQ-SPEEDUP-002
"""

import pytest

import run
from core import queue_ui, selection
from core.result import FAIL, PASS
from tests import queue_retry as qr


# --- State 판독 ------------------------------------------------------------
@pytest.mark.parametrize("token,expected", [
    ("Failed", "Failed"), ("Faited", "Failed"), ("FAILED", "Failed"),
    ("Done", "Done"), ("Pendinq", "Pending"), ("Sending", "Sending"),
    ("Stopped", "Stopped"), ("-", None), ("Image", None), ("", None),
    # 좁은 State 칸의 줄임 표시(2026-11-22 실기 캡처 step5_01.png의 `Send...`).
    ("Send...", "Sending"), ("Send..", "Sending"), ("Pend…", "Pending"),
    ("Stopp...", "Stopped"), ("Sen...", None), ("Send", None),
])
def test_parse_state_reads_srs_values_only(token, expected):
    assert queue_ui.parse_state(token) == expected


def test_parse_row_takes_state_from_first_column_and_type():
    row = queue_ui.parse_row("Failed - Image STORAGE DATA^FLOW DATA_FLOW_MWL_01")
    assert row["state"] == "Failed"
    assert row["type"] == "Image"


def test_merge_reads_votes_and_refuses_conflicting_state():
    reads = {
        "auto": [{"y": 250, "text": "Failed - Image STORAGE A DATA_FLOW_MWL_01"},
                 {"y": 280, "text": "Done - Image STORAGE B OTHER_ID"}],
        "bin150i": [{"y": 253, "text": "Faited - Image STORAGE A DATA_FLOW_MWL_01"},
                    {"y": 279, "text": "Failed - Image STORAGE B OTHER_ID"}],
    }
    rows = queue_ui.merge_reads(reads)
    assert [r["y"] for r in rows] == [250, 280]
    assert rows[0]["state"] == "Failed"
    # 변형마다 State가 다르면 특정 값으로 판정하지 않는다.
    assert rows[1]["state"] is None


def test_pick_row_requires_single_match_and_accepts_truncated_id():
    rows = [{"y": 250, "state": "Failed", "type": "Image",
             "texts": {"auto": "Failed - Image STORAGE A DATA_FLOW_MWL"}, "votes": ["Failed"]},
            {"y": 280, "state": "Done", "type": "Image",
             "texts": {"auto": "Done - Image STORAGE A OTHER"}, "votes": ["Done"]}]
    assert queue_ui.pick_row(rows, "DATA_FLOW_MWL_01")["y"] == 250
    assert queue_ui.pick_row(rows, "DATA_FLOW_MWL_01", state="Done") is None
    twice = rows + [{**rows[0], "y": 310}]
    assert queue_ui.pick_row(twice, "DATA_FLOW_MWL_01") is None


# --- 포트와 판정 -------------------------------------------------------------
def test_choose_closed_port_skips_open_ports():
    open_ports = {11116, 11117}
    probe = lambda host, port: port in open_ports
    assert qr.choose_closed_port("10.0.0.1", 11116, probe=probe) == 11118
    assert qr.choose_closed_port("10.0.0.1", 11116, probe=lambda h, p: True) is None


def test_retry_done_is_fail_because_current_setting_was_used():
    status, reason, _ = qr.retry_verdict("Done", ["Sending", "Done"], 4, [4, 2, 7], ["k"])
    assert status == FAIL and "Done" in reason


def test_retry_failed_with_signal_is_pass():
    assert qr.retry_verdict("Failed", ["Failed"], 4, [4], ["Pending", "Failed"])[0] == PASS
    assert qr.retry_verdict("Failed", ["Failed"], 4, [4, 1, 4], [])[0] == PASS
    assert qr.retry_verdict("Failed", ["Pending", "Failed"], 4, [4], [])[0] == PASS


def test_retry_failed_without_any_signal_is_fail():
    status, reason, signals = qr.retry_verdict("Failed", ["Failed", "Failed"], 4, [4], [])
    assert status == FAIL and not signals and "신호" in reason


def test_retry_unreadable_state_is_fail():
    assert qr.retry_verdict(None, [None], 4, [4, 1], ["x"])[0] == FAIL


# --- Viewer 로그 -------------------------------------------------------------
#: 2026-11-22 실기 run 20261122-163800-2b5b7f9c의 Viewer 로그 줄(공백만 줄임).
REAL_RETRY_LOG = [
    "[2026/11/22 16:48:55.572] [Info] [DICOM] [Update Queue Storage Item : 13(Failed, -)]",
    "[2026/11/22 16:49:32.307] [Info] [DICOM] [Update Item(13) in DICOM Storage Queue ]",
    "[2026/11/22 16:49:32.308] [Info] [DICOM] [Update Queue Storage Item : 13(Pending, -)]",
    "[2026/11/22 16:49:32.313] [Info] [DICOM] [Storage Item(13) state change to Sending]",
    "[2026/11/22 16:49:32.316] [Info] [DICOM] [Update Queue Storage Item : 13(Sending, -)]",
    "[2026/11/22 16:49:32.318] [Info] [DICOM] [Storage>      Connecting to 10.13.0.222:11117]",
    "[2026/11/22 16:49:53.355] [Info] [DICOM] [Storage>      Server connection failed]",
    "[2026/11/22 16:49:53.415] [Info] [DICOM] [Update Queue Storage Item : 13(Failed, -)]",
    "[2026/11/22 16:50:10.000] [Info] [DICOM] [Storage>      Connecting to 10.13.0.222:11116]",
    "[2026/11/22 16:50:11.000] [Info] [DICOM] [Update Queue Storage Item : 130(Sending, -)]",
]


def test_queue_log_events_follow_one_key_and_its_connect_target():
    events = queue_ui.queue_log_events(REAL_RETRY_LOG, 13)
    assert events["states"] == ["Failed", "Pending", "Sending", "Failed"]
    # 항목이 Failed로 돌아간 뒤의 접속 줄과 Key 130은 세지 않는다.
    assert events["connects"] == ["10.13.0.222:11117"]
    assert qr.retry_verdict("Failed", [None], 3, [3], events["states"])[2] == ["Viewer 로그 Queue 상태 변화"]
    assert qr.retry_verdict("Failed", [None], 3, [3], ["Failed"])[0] == FAIL


def test_viewer_log_reads_utf16_after_mark(tmp_path):
    path = tmp_path / "2026_11_22.log"
    path.write_bytes(b"\xff\xfe" + (REAL_RETRY_LOG[0] + "\r\n").encode("utf-16-le"))
    mark = queue_ui.log_mark(str(path))
    with open(path, "ab") as f:
        f.write(("\r\n".join(REAL_RETRY_LOG[1:]) + "\r\n").encode("utf-16-le"))
    events = queue_ui.queue_log_events(queue_ui.log_lines_since(str(path), mark), 13)
    assert events["states"] == ["Pending", "Sending", "Failed"]
    assert queue_ui.log_lines_since(str(tmp_path / "none.log"), 0) == []
    assert queue_ui.viewer_log_path("C:/D").replace("\\", "/").startswith("C:/D/Log/Viewer/")


# --- 선택 실행 ---------------------------------------------------------------
@pytest.mark.parametrize("name", ["queue-retry", "queue_retry", "SPEC_QueueList_Retry"])
def test_selection_accepts_queue_retry_with_fixture(name):
    plan = selection.resolve([name])
    executed = plan["executed"]
    assert plan["requested"] == ["SPEC_QueueList_Retry"]
    assert plan["dependencies"] == ["TC_Basic_WorkFlow_02"]
    assert "TC_Basic_WorkFlow_04" not in executed
    assert executed.index("SPEC_QueueList_Retry") > executed.index("TC_Basic_WorkFlow_02")


def test_full_chain_is_unchanged_and_optional_sits_after_wf04():
    assert "SPEC_QueueList_Retry" not in selection.BASIC_CHAIN_IDS
    extended = selection.with_optional(selection.BASIC_CHAIN_IDS)
    position = extended.index("SPEC_QueueList_Retry")
    assert extended[position - 1] == "TC_Basic_WorkFlow_04"
    assert tuple(x for x in extended if x != "SPEC_QueueList_Retry") == selection.BASIC_CHAIN_IDS


def test_selected_chain_inserts_optional_stage(monkeypatch):
    marker = object()
    monkeypatch.setattr(run, "_optional_stages",
                        lambda: [(marker, "SPEC_QueueList_Retry", "Retry")])
    stages = [(None, sid, sid) for sid in selection.BASIC_CHAIN_IDS]
    picked = run._selected_chain_stages(stages, selection.resolve(["wf04", "queue-retry"]))
    ids = [s[1] for s in picked]
    assert ids[ids.index("TC_Basic_WorkFlow_04") + 1] == "SPEC_QueueList_Retry"
    unpicked = run._selected_chain_stages(stages, selection.resolve(["wf04"]))
    assert "SPEC_QueueList_Retry" not in [s[1] for s in unpicked]
