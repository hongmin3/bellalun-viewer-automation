"""REQ-VERDICT-004·005·006, REQ-QA-002: 판정 기준표, 환경 재점검 BLOCKED, 단계 감시, 남은 실행 기록.

Validates: REQ-VERDICT-004, REQ-VERDICT-005, REQ-VERDICT-006, REQ-QA-002
제품·서버·Viewer를 실행하지 않는다.
"""
import html
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from openpyxl import Workbook

import run
from core import env_health, frame_checklist, report_layout, tc_basis
from core.result import BLOCKED, FAIL, PASS, TCResult, is_padded

ROOT = Path(__file__).resolve().parents[1]


def _load_gate():
    spec = importlib.util.spec_from_file_location("release_gate_criteria", ROOT / "tools/release_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- REQ-VERDICT-004 판정 기준표 -------------------------------------------------

def test_criteria_table_covers_all_verdicts_in_step_decision_order():
    keys = [row[0] for row in report_layout.VERDICT_CRITERIA]
    assert keys == ['SKIP', 'BLOCKED', 'FAIL', 'MANUAL', 'PASS']
    assert all(rule and not_this and action for _, rule, not_this, action in report_layout.VERDICT_CRITERIA)
    assert 'FAIL > BLOCKED > MANUAL > PASS > SKIP' in report_layout.VERDICT_PRIORITY[0]


def test_html_report_shows_criteria_before_the_body():
    page = report_layout.render_shell(title='t', product='p', subtitle='s', nav=[('overview', '결과 요약')],
                                      body_html='<section id="overview">BODY</section>')
    assert page.index('판정 기준') < page.index('BODY')
    for _, rule, not_this, action in report_layout.VERDICT_CRITERIA:
        for text in (rule, not_this, action):
            assert html.escape(text) in page
    for line in report_layout.VERDICT_PRIORITY:
        assert html.escape(line) in page


def test_summary_sheet_puts_criteria_above_the_totals():
    wb = Workbook()
    ws = frame_checklist.add_summary_sheet(wb, product='P', rows=[
        {'tc_id': 'TC_A', 'title': 'a', 'verdict': 'PASS', 'reason': '', 'location': ''}])
    cells = [(cell.row, str(cell.value)) for row in ws.iter_rows() for cell in row if cell.value is not None]
    row_of = lambda text: min(r for r, v in cells if text in v)
    assert row_of('판정 기준') < row_of('판정 합계') < row_of('TC별 결과')
    joined = '\n'.join(v for _, v in cells)
    for _, rule, not_this, action in report_layout.VERDICT_CRITERIA:
        assert rule in joined and not_this in joined and action in joined


def test_steps_after_a_failure_are_blocked_but_the_tc_stays_fail():
    result = TCResult('TC_X', 'x')
    result.add(1, '확인', PASS, stop=False)
    result.abort(0, 'TC_X 실행', RuntimeError('boom'))
    with mock.patch.object(tc_basis, 'capture', return_value={'rows': {'TC_X': {'steps': '1. a\n2. b\n3. c'}}}):
        run.pad_aborted_steps(SimpleNamespace(), [result])
    pads = [c for c in result.checks if c.title.endswith('미수행')]
    assert pads and all(c.status == BLOCKED and is_padded(c) for c in pads)
    assert all(c.unblock_condition for c in pads)
    assert result.verdict == FAIL
    assert result.counts[FAIL] == 1, 'FAIL 개수는 실제 실패만 센다'


def test_old_fail_padding_is_still_recognised():
    old = {"step": 3, "title": "Step 3 미수행", "status": "FAIL",
           "actual": "수행하지 않음(앞선 단계에서 TC 가 중단됨)"}
    assert is_padded(old) and is_padded(dict(old, status="BLOCKED"))
    assert not is_padded(dict(old, status="PASS"))


def test_gate_tolerates_blocked_padding_after_known_defect_and_rejects_other_blocked():
    gate = _load_gate()
    known = ("TC_Basic_WorkFlow_14", "Setting > Device > UPS 설정이 Export 시점 값으로 복원")
    check = lambda step, title, status, actual="확인함": {
        "step": step, "title": title, "status": status, "expected": "기대", "actual": actual, "note": ""}
    rows = [{"tc_id": tc, "verdict": "PASS", "checks": [check(1, "확인", "PASS")]}
            for tc in sorted(gate.FULL_REGRESSION_MARKERS)]
    rows.append({"tc_id": known[0], "verdict": "FAIL", "checks": [
        check(7, known[1], "FAIL", "UPS 값 다름"),
        check(8, "Step 8 미수행", "BLOCKED", gate.PAD_ACTUAL)]})
    checks, reasons = [], []
    gate._evaluate_basic({"results": rows}, checks, reasons, {known})
    assert reasons == []
    details = {c["name"]: c["detail"] for c in checks}
    assert "Step 8 미수행" in details["알려진 결함 중단으로 미검증된 Step"]

    rows.append({"tc_id": "TC_Basic_WorkFlow_05", "verdict": "BLOCKED", "checks": [
        check(0, "시험 환경 재점검", "BLOCKED")]})
    checks, reasons = [], []
    gate._evaluate_basic({"results": rows}, checks, reasons, {known})
    assert any("BLOCKED" in r and "TC_Basic_WorkFlow_05" in r for r in reasons)


# --- REQ-VERDICT-005 시험 환경 재점검 -----------------------------------------------

CFG = {"dicom": {
    "mwl_server_url": "http://srv:5000", "print_server_url": "http://srv:8000",
    "storage_scp": {"api_url": "http://srv:5003", "host": "srv", "port": 11116},
    "print_scp": {"host": "srv", "port": 11113},
    "servers_to_register": [{"kind": "MWL", "ip": "srv", "port": 11112}]}}


def _calls_in(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    needs = set()
    if re.search(r"\b(sv|send_verify|storagescp)\.(?!SENDABLE|QUEUE_STATE)[a-z_]+\(", text):
        needs.add(env_health.STORAGE)
    if re.search(r"\bmwl\.[a-z_]+\(|mwl_server_url", text):
        needs.add(env_health.MWL)
    if re.search(r"\bprintscp\.[a-z_]+\(|print_server_url", text):
        needs.add(env_health.PRINT)
    return needs


def test_requirement_table_matches_server_calls_in_tc_modules():
    for number in range(1, 17):
        tc_id = f"TC_Basic_WorkFlow_{number:02}"
        assert set(env_health.required(tc_id)) == _calls_in(f"tests/workflow{number:02}.py"), tc_id


def test_check_marks_unreachable_and_5xx_servers_down():
    tcp = lambda host, port: (port != 11116, f"{host}:{port} {'연결됨' if port != 11116 else '연결 실패'}")
    http = lambda url: (not url.endswith(":8000"), f"{url} {'HTTP 200' if not url.endswith(':8000') else 'HTTP 500 서버 오류'}")
    status = env_health.check(CFG, ["storage", "mwl", "print"], tcp=tcp, http=http)
    assert set(env_health.down_of(status)) == {"storage", "print"}
    assert status["mwl"]["ok"]


def test_http_4xx_counts_as_alive_and_5xx_as_down():
    import urllib.error
    def opener(code):
        def fail(url, timeout):
            raise urllib.error.HTTPError(url, code, "x", {}, None)
        return fail
    with mock.patch("urllib.request.urlopen", opener(404)):
        assert env_health.http_ok("http://srv:5003/api")[0] is True
    with mock.patch("urllib.request.urlopen", opener(500)):
        assert env_health.http_ok("http://srv:5003/api")[0] is False


def _down():
    return {"storage": {"ok": False, "details": ["srv:11116 연결 실패(timeout)"], "checked_at": "t"}}


def test_reclassify_turns_fail_into_blocked_and_keeps_the_observation():
    result = TCResult("TC_Basic_WorkFlow_05", "3D send")
    result.add(3, "Queue Done", FAIL, actual={"states": {"14": 3}}, note="원래 비고", stop=False)
    changed = env_health.reclassify(result, _down())
    assert changed == 1
    assert result.verdict == BLOCKED
    moved = result.checks[0]
    assert moved.actual == {"states": {"14": 3}}
    assert "원래 비고" in moved.note and moved.unblock_condition
    env_check = result.checks[-1]
    assert env_check.title == "시험 환경 재점검" and env_check.status == BLOCKED
    assert "Storage 서버" in env_check.unblock_condition


def _ctx(down=()):
    return SimpleNamespace(cfg=CFG, environment_down=set(down))


def test_guarded_rechecks_after_fail_and_skips_later_tcs_while_down():
    ctx = _ctx()
    fail = lambda c: (lambda r: (r.add(3, "Queue Done", FAIL, stop=False), r)[-1])(TCResult("TC_Basic_WorkFlow_05", "x"))
    with mock.patch.object(env_health, "check", return_value=_down()) as probe:
        rows = run.guarded(fail, ctx, "TC_Basic_WorkFlow_05", "x")
        assert rows[0].verdict == BLOCKED
        assert ctx.environment_down == {"storage"}
        ran = []
        later = run.guarded(lambda c: ran.append(1), ctx, "TC_Basic_WorkFlow_06", "y")
        assert ran == [] and later[0].verdict == BLOCKED
        assert probe.call_count == 2
    assert [o["phase"] for o in ctx.environment_outages] == ["after_fail", "before"]


def test_guarded_runs_normally_once_the_server_is_back_and_keeps_real_fail():
    ctx = _ctx(down={"storage"})
    healthy = {"storage": {"ok": True, "details": ["ok"], "checked_at": "t"}}
    fail = lambda c: (lambda r: (r.add(3, "Queue Done", FAIL, stop=False), r)[-1])(TCResult("TC_Basic_WorkFlow_06", "x"))
    with mock.patch.object(env_health, "check", return_value=healthy):
        rows = run.guarded(fail, ctx, "TC_Basic_WorkFlow_06", "x")
    assert rows[0].verdict == FAIL
    assert ctx.environment_down == set()


def test_tc_without_server_needs_is_never_probed():
    ctx = _ctx(down={"storage"})
    fail = lambda c: (lambda r: (r.add(1, "x", FAIL, stop=False), r)[-1])(TCResult("TC_Basic_WorkFlow_14", "x"))
    with mock.patch.object(env_health, "check") as probe:
        rows = run.guarded(fail, ctx, "TC_Basic_WorkFlow_14", "x")
    probe.assert_not_called()
    assert rows[0].verdict == FAIL


# --- REQ-VERDICT-006 기본 회귀 단계 감시 ----------------------------------------------

def test_run_regression_chain_runs_each_stage_under_the_watchdog():
    source = (ROOT / "run.py").read_text(encoding="utf-8")
    block = source[source.index('if args.cmd == "run-regression":'):]
    block = block[:block.index("results.extend(_regression_scope_skips")]
    assert "wu_chain.run_stage(fn, ctx, tc_id, title, guarded=guarded" in block
    assert "produced = guarded(fn, ctx, tc_id, title)" not in block
    assert 'x.verdict in ("FAIL", "BLOCKED")' in block


def test_stage_trip_also_stops_xipl_studio(monkeypatch):
    from core import wu_chain
    original_kill_xipl = wu_chain._kill_xipl_studio
    killed = []
    monkeypatch.setattr(wu_chain, "_kill_viewer", lambda: killed.append("viewer") or 7)
    monkeypatch.setattr(wu_chain, "_kill_xipl_studio", lambda: killed.append("xipl"))
    assert wu_chain._kill_product() == 7
    assert killed == ["viewer", "xipl"]
    calls = []
    original_kill_xipl(run=lambda args, **kw: calls.append((args, kw.get("timeout"))))
    assert calls and calls[0][0][-1] == "XIPL.STUDIO.exe" and calls[0][1] == 30


def test_xipl_powershell_calls_have_a_time_limit():
    for path in ("core/xipl.py", "tests/xipl_flows.py"):
        source = (ROOT / path).read_text(encoding="utf-8")
        calls = re.findall(r"subprocess\.run\((.*?)\)\n", source, re.S)
        assert calls and all("timeout=" in call for call in calls), path
    assert "SendMessageW(save_button" not in (ROOT / "core/xipl.py").read_text(encoding="utf-8")


# --- REQ-QA-002 남은 '실행 중' 기록 ----------------------------------------------------

def _write_run(root, run_id, **data):
    path = Path(root) / "Runs" / run_id / "run.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": 1, "run_id": run_id, "status": "running", **data}), encoding="utf-8")
    return path


def test_stale_running_records_are_closed_but_live_ones_are_kept(tmp_path):
    from bellalunauto.runs import close_stale_runs
    legacy = _write_run(tmp_path, "20261123-172736-aaaa")
    dead = _write_run(tmp_path, "20261123-200000-bbbb", supervisor_pid=111)
    live = _write_run(tmp_path, "20261123-210000-cccc", supervisor_pid=222)
    done = _write_run(tmp_path, "20261123-220000-dddd", supervisor_pid=111)
    done.write_text(json.dumps({"run_id": "20261123-220000-dddd", "status": "completed"}), encoding="utf-8")
    closed = close_stale_runs(tmp_path, alive=lambda pid: pid == 222)
    assert closed == ["20261123-172736-aaaa", "20261123-200000-bbbb"]
    for path in (legacy, dead):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["status"] == "abnormal" and data["closed_reason"] and data["closed_at"]
    assert json.loads(live.read_text(encoding="utf-8"))["status"] == "running"
    assert json.loads(done.read_text(encoding="utf-8"))["status"] == "completed"


def test_new_run_records_its_supervisor_and_closes_legacy_record(tmp_path):
    from bellalunauto.runs import RunRecord
    legacy = _write_run(tmp_path, "20261123-172736-aaaa")
    record = RunRecord.create(tmp_path, "run-regression", {})
    assert record.data["supervisor_pid"] > 0
    assert json.loads(legacy.read_text(encoding="utf-8"))["status"] == "abnormal"
