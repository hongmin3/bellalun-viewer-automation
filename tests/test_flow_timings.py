# -*- coding: utf-8 -*-
"""판정 기록 시각과 Viewer 시작·Setting 대기 진단 시간을 결과에 남긴다.

Validates: REQ-SPEEDUP-008
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import run
from core import flows, result
from core.result import PASS, TCResult


def test_check_records_time_in_json_only():
    r = TCResult("TC_X", "x")
    r.add(1, "step", PASS)
    data = r.checks[0].as_dict()
    assert datetime.fromisoformat(data["recorded_at"])
    html = result._report_value(data.get("actual", ""))
    assert "recorded_at" not in html


def test_drain_folds_rail_waits_and_clears():
    flows.drain_timings()
    flows._rail_wait_stats[("page", "pane")] = [3, 1.5]
    flows._rail_wait_stats[("group", "timeout")] = [1, 3.0]
    flows.note_timing("viewer", "Viewer 시작(start_clean_viewer)", datetime.now(), 41.0,
                      "restart", "앞 TC가 View 화면")
    rows = flows.drain_timings()
    assert [r["kind"] for r in rows] == ["viewer", "setting_wait", "setting_wait"]
    assert rows[0]["outcome"] == "restart" and rows[0]["duration_seconds"] == 41.0
    assert {(r["outcome"], r["detail"]) for r in rows[1:]} == {("timeout", "count=1"), ("pane", "count=3")}
    assert flows.drain_timings() == []


def test_start_clean_viewer_notes_decision():
    flows.drain_timings()
    with patch.object(flows, "viewer_reuse_check", return_value=(False, "앞 TC가 View 화면")), \
            patch.object(flows, "cold_start", return_value=(object(), [])):
        flows.start_clean_viewer({}, None)
    rows = flows.drain_timings()
    assert rows[0]["kind"] == "viewer"
    assert rows[0]["outcome"] == "restart"
    assert rows[0]["detail"] == "앞 TC가 View 화면"


def test_guarded_attaches_timings_to_first_result_only_for_that_tc():
    flows.drain_timings()
    flows.note_timing("viewer", "stale", datetime.now(), 1.0, "reuse")  # 앞 TC 밖의 기록

    def tc(ctx):
        flows.note_timing("viewer", "Viewer 시작(start_clean_viewer)", datetime.now(), 2.0, "reuse", "깨끗함")
        first, second = TCResult("TC_A", "a"), TCResult("TC_B", "b")
        first.add(1, "s", PASS)
        second.add(1, "s", PASS)
        return [first, second]
    ctx = SimpleNamespace()
    with patch.object(run, "_viewer_log_path", return_value=None):
        rows = run.guarded(tc, ctx, "TC_A", "a")
    assert [t["name"] for t in rows[0].timings] == ["Viewer 시작(start_clean_viewer)"]
    assert rows[1].timings == []


def test_guarded_exception_keeps_timings():
    flows.drain_timings()

    def tc(ctx):
        flows.note_timing("viewer", "Viewer 시작(start_clean_viewer)", datetime.now(), 2.0, "restart")
        raise RuntimeError("boom")
    ctx = SimpleNamespace()
    with patch.object(run, "_viewer_log_path", return_value=None), \
            patch.object(run, "_stage_causes", return_value=[]):
        rows = run.guarded(tc, ctx, "TC_A", "a")
    assert rows[0].timings and rows[0].timings[0]["outcome"] == "restart"
