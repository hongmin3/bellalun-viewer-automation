"""원격 실행: 실제 localhost 전송 + 파일/DB 상태, 가짜 WinRM 경계."""
import base64
import io
import json
from pathlib import Path
import threading
import time
import hashlib
import os
import subprocess
import sys
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import pytest

from remote.bundles import BundleError, create_bundle, unpack_bundle
from remote.coordinator import Coordinator, RemoteError
from remote.service import make_server
from remote.winrm_executor import WinRMExecutor


def bundle(tmp_path):
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    (source / "run.py").write_text("print('fixture')")
    return create_bundle(source, ["run.py"])


def test_bundle_hashes_pin_content_and_roundtrip(tmp_path):
    package, identity = bundle(tmp_path)
    destination = tmp_path / "unpacked"
    result = unpack_bundle(package, destination, identity)
    assert result["bundle_id"] == identity
    assert (destination / "run.py").read_text() == "print('fixture')"
    changed = bytearray(package)
    changed[60] ^= 1
    with pytest.raises(BundleError):
        unpack_bundle(bytes(changed), tmp_path / "bad", identity)


@pytest.mark.parametrize("name", ["../escape.py", "/root.py", "C:/bad.py", "a\\b.py", "config.json", ".env"])
def test_bundle_rejects_unsafe_paths(tmp_path, name):
    with pytest.raises(BundleError):
        create_bundle(tmp_path, [name])


def test_bundle_rejects_zip_traversal_and_links(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../escape", b"bad")
    with pytest.raises(BundleError):
        unpack_bundle(stream.getvalue(), tmp_path / "dest", "0" * 64)
    (tmp_path / "a.py").write_bytes(b"code")
    try:
        (tmp_path / "link.py").symlink_to(tmp_path / "a.py")
    except OSError:
        return
    with pytest.raises(BundleError):
        create_bundle(tmp_path, ["link.py"])


class FakeExecutor:
    def __init__(self):
        self.started = threading.Event()
        self.done = threading.Event()
    def validate(self, pc, profile):
        if not pc.get("enabled"):
            raise RemoteError("대상 PC 미확정")
    def execute(self, job, pc, profile, package, output, cancel, log):
        self.started.set()
        log("실행 시작")
        while not self.done.wait(.01):
            if cancel.is_set():
                return {"status": "cancelled", "stopped_verified": True}
        (output / "result.json").write_text('{"pass":true}')
        return {"status": "completed", "exit_code": 0}


def coordinator(tmp_path, executor=None):
    return Coordinator(tmp_path / "server", {"pc": {"enabled": True}},
                       {"qa": {"argv": ["python.exe", "run.py"]}},
                       executor or FakeExecutor())


def wait_state(manager, job_id, expected):
    for _ in range(200):
        record = manager.get(job_id)
        if record["status"] in expected:
            return record
        time.sleep(.01)
    pytest.fail("상태 전이 시간 초과")


def test_pc_lock_cancel_and_next_run(tmp_path):
    runner = FakeExecutor()
    manager = coordinator(tmp_path, runner)
    data, identity = bundle(tmp_path)
    manager.add_bundle(data, identity)
    job = manager.submit("pc", "qa", identity, restore_after=True)
    assert runner.started.wait(1)
    with pytest.raises(RemoteError):
        manager.submit("pc", "qa", identity)
    manager.cancel(job["id"])
    assert wait_state(manager, job["id"], {"cancelled"})["restore_after"] is True
    runner.done.set()
    next_job = manager.submit("pc", "qa", identity)
    finished = wait_state(manager, next_job["id"], {"completed", "error"})
    assert finished["status"] == "completed"
    result, result_id = manager.results(next_job["id"])
    unpack_bundle(result, tmp_path / "results", result_id, code_only=False)
    assert (tmp_path / "results" / "result.json").is_file()


def test_missing_pc_profile_and_disabled_pc_block(tmp_path):
    manager = coordinator(tmp_path)
    data, identity = bundle(tmp_path)
    manager.add_bundle(data, identity)
    with pytest.raises(RemoteError):
        manager.submit("unknown", "qa", identity)
    with pytest.raises(RemoteError):
        manager.submit("pc", "arbitrary command", identity)
    manager.pcs["pc"]["enabled"] = False
    with pytest.raises(RemoteError):
        manager.submit("pc", "qa", identity)


def test_server_restart_keeps_uncertain_pc_locked(tmp_path):
    runner = FakeExecutor()
    manager = coordinator(tmp_path, runner)
    data, identity = bundle(tmp_path)
    manager.add_bundle(data, identity)
    job = manager.submit("pc", "qa", identity)
    assert runner.started.wait(1)
    restarted = coordinator(tmp_path)
    assert restarted.get(job["id"])["status"] == "uncertain"
    with pytest.raises(RemoteError):
        restarted.submit("pc", "qa", identity)
    manager.cancel(job["id"])
    wait_state(manager, job["id"], {"cancelled"})


def test_localhost_authenticated_upload_submit_cancel_and_results(tmp_path):
    runner = FakeExecutor()
    manager = coordinator(tmp_path, runner)
    server = make_server(manager, "fixture-token", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    def request(path, data=None, token="fixture-token"):
        req = Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urlopen(req, timeout=2) as response:
            return json.load(response)
    try:
        with pytest.raises(HTTPError) as error:
            request("/jobs", token="wrong")
        assert error.value.code == 401
        data, identity = bundle(tmp_path)
        request("/bundles", {"package": base64.b64encode(data).decode(), "bundle_id": identity})
        job = request("/jobs", {"pc_id": "pc", "profile_id": "qa", "bundle_id": identity})
        assert runner.started.wait(1)
        request("/jobs/" + job["id"] + "/cancel", {})
        wait_state(manager, job["id"], {"cancelled"})
        assert "실행 시작" in request("/jobs/" + job["id"] + "/logs")["log"]
        runner.done.set()
        final = request("/jobs", {"pc_id": "pc", "profile_id": "qa", "bundle_id": identity})
        wait_state(manager, final["id"], {"completed"})
        results = request("/jobs/" + final["id"] + "/results")
        unpack_bundle(base64.b64decode(results["package"]), tmp_path / "http-results",
                      results["bundle_id"], code_only=False)
        assert (tmp_path / "http-results" / "result.json").is_file()
    finally:
        server.shutdown()
        server.server_close()


def test_winrm_validation_is_fail_closed_and_never_logs_secrets(tmp_path):
    runner = WinRMExecutor(session_factory=lambda *a, **k: None, environ={})
    with pytest.raises(RemoteError):
        runner.validate({"enabled": True}, {"argv": ["python", "run.py"]})


def test_winrm_lock_guard_and_task_use_interactive_token(tmp_path):
    seen = []
    class Response:
        status_code = 0
        std_err = b""
        std_out = b'{"logged_in":true,"unlocked":false,"user":"qa"}'
    class Session:
        def run_ps(self, script):
            seen.append(script)
            return Response()
    runner = WinRMExecutor(session_factory=lambda *a, **k: Session(), environ={"QA_PASS": "sentinel-secret"})
    pc = {"enabled": True, "endpoint": "https://fixture.invalid:5986/wsman", "user": "qa",
          "password_env": "QA_PASS", "work_dir": "C:\\BellalunRemote", "allow_uncoordinated_vhd_snapshot": True}
    profile = {"argv": ["python.exe", "run.py"], "timeout_seconds": 30}
    runner.validate(pc, profile)
    with pytest.raises(RemoteError):
        runner.execute({"id": "job1", "restore_after": False}, pc, profile, b"zip", tmp_path,
                       threading.Event(), lambda line: None)
    assert len(seen) == 1
    assert "sentinel-secret" not in "".join(seen)
    script = runner.task_script("job1", pc, profile)
    assert "Interactive" in script
    assert "Highest" in script
    assert "Start-ScheduledTask" in script


def test_winrm_full_transfer_task_receipt_and_results(tmp_path):
    from remote.winrm_executor import SESSION_PROBE
    calls = []
    content = b'{"job_id":"job1","exit_code":0,"finished":true}'
    class Response:
        status_code = 0
        std_err = b""
        def __init__(self, data):
            self.std_out = data
    class Session:
        def run_ps(self, script):
            calls.append(script)
            if script == SESSION_PROBE:
                return Response(b'{"logged_in":true,"unlocked":true,"user":"machine\\\\qa"}')
            if "$files=@()" in script:
                return Response(json.dumps([{"path": "receipt.json", "size": len(content),
                                             "sha256": hashlib.sha256(content).hexdigest()}]).encode())
            if "$s=[IO.File]::OpenRead" in script:
                return Response(base64.b64encode(content))
            if script.startswith("if(Test-Path") and "receipt.json" in script:
                return Response(content)
            return Response(b"")
    credentials = []
    def factory(*args, **kwargs):
        credentials.append(kwargs)
        return Session()
    runner = WinRMExecutor(session_factory=factory, environ={"QA_PASS": "test-secret"})
    pc = {"enabled": True, "endpoint": "https://fixture.invalid:5986/wsman", "user": "qa",
          "password_env": "QA_PASS", "work_dir": "C:\\BellalunRemote", "allow_uncoordinated_vhd_snapshot": True}
    profile = {"argv": ["{code}\\BellalunAuto.exe", "--workspace", "{workspace}",
                        "run-regression", "{restore_after}"], "timeout_seconds": 30}
    with mock.patch.object(runner, "_vhd_guard"):
        result = runner.execute({"id": "job1", "bundle_id": "0" * 64, "restore_after": True},
                                pc, profile, b"zip bytes", tmp_path, threading.Event(), lambda line: None)
    assert result["status"] == "abnormal"  # receipt만으로 정상 완주를 주장할 수 없다.
    assert (tmp_path / "receipt.json").read_bytes() == content
    assert credentials[0]["auth"] == ("qa", "test-secret")
    assert credentials[0]["server_cert_validation"] == "validate"
    assert not any("test-secret" in script for script in calls)
    assert sum("WTSQuerySessionInformation" in script for script in calls) == 2
    assert any("Register-ScheduledTask" in script for script in calls)
    assert any("Get-FileHash" in script and "Transfer hash mismatch" in script for script in calls)
    assert "--restore-after" in runner._wrapper({"id": "job1", "restore_after": True}, pc, profile).decode("utf-8-sig")


def engine_output(output, *, code=0, status="completed", report=True, complete=True):
    run_id = "20261113-120000-aabbccdd"
    record = {"run_id": run_id, "action": "run-regression", "status": status, "exit_code": code,
              "reports": [r"C:\\BellalunRemote\\job1\\workspace\\Reports\\Result_test.json"]}
    directory = output / "workspace" / "Runs" / run_id
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps(record))
    if report:
        from core.automation_health import FULL_REGRESSION_MARKERS
        reports = output / "workspace" / "Reports"
        reports.mkdir(parents=True)
        (reports / "Result_test.json").write_text(json.dumps({
            "meta": {"run_id": run_id, "execution_mode": "live", "chain_completed": complete},
            "results": [{"tc_id": tc, "verdict": "FAIL" if code == 1 else "PASS"}
                        for tc in FULL_REGRESSION_MARKERS]}))
    return {"job_id": "job1", "engine_run_id": run_id, "finished": True, "exit_code": code,
            "workspace": r"C:\BellalunRemote\job1\workspace"}


@pytest.mark.parametrize("code,status,report,complete,expected", [
    (0, "completed", True, True, "completed"), (1, "completed", True, True, "completed"),
    (2, "abnormal", False, False, "blocked"), (3, "abnormal", True, True, "abnormal"),
    (0, "completed", False, True, "abnormal"), (0, "completed", True, False, "abnormal"),
    (0, "running", True, True, "abnormal")])
def test_completion_requires_supervisor_and_same_run_full_report(tmp_path, code, status, report, complete, expected):
    receipt = engine_output(tmp_path, code=code, status=status, report=report, complete=complete)
    runner = WinRMExecutor()
    result = runner.verify_completion({"id": "job1"}, {"argv": ["engine", "run-regression"]}, receipt, tmp_path)
    assert result["status"] == expected
    assert result["engine_run_id"] == receipt["engine_run_id"]


def test_wrong_receipt_job_and_run_id_never_complete(tmp_path):
    receipt = engine_output(tmp_path)
    runner = WinRMExecutor()
    receipt["job_id"] = "different"
    assert runner.verify_completion({"id": "job1"}, {"argv": ["engine", "run-regression"]}, receipt, tmp_path)["status"] == "uncertain"


def test_winupdate_requires_all_thirteen_same_run_live_rows(tmp_path):
    receipt = engine_output(tmp_path, code=1)
    run_path = tmp_path / "workspace" / "Runs" / receipt["engine_run_id"] / "run.json"
    record = json.loads(run_path.read_text())
    record["action"] = "run-winupdate"
    run_path.write_text(json.dumps(record))
    report_path = tmp_path / "workspace" / "Reports" / "Result_test.json"
    report = json.loads(report_path.read_text())
    report["results"] = [{"tc_id": f"TC_WindowsUpdate_{i:02}", "verdict": "FAIL"} for i in range(1, 14)]
    report_path.write_text(json.dumps(report))
    runner = WinRMExecutor()
    args = ({"id": "job1"}, {"argv": ["engine", "run-winupdate"]}, receipt, tmp_path)
    assert runner.verify_completion(*args)["status"] == "completed"
    report["results"].pop()
    report_path.write_text(json.dumps(report))
    assert runner.verify_completion(*args)["status"] == "abnormal"
    report["meta"]["run_id"] = "other"
    report_path.write_text(json.dumps(report))
    assert runner.verify_completion(*args)["status"] == "abnormal"


def test_shared_interlock_missing_blocks_by_default(tmp_path):
    runner = WinRMExecutor()
    with pytest.raises(RemoteError):
        runner.acquire_interlock({"id": "job1"}, {})


def test_dashboard_shell_and_authenticated_catalog_hide_secrets(tmp_path):
    manager = coordinator(tmp_path)
    manager.pcs["pc"]["password_env"] = "MUST_NOT_APPEAR"
    server = make_server(manager, "private-test-token", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/") as response:
            html = response.read().decode()
        assert "dashboard.js" in html
        assert "private-test-token" not in html
        with pytest.raises(HTTPError):
            urlopen(base + "/catalog")
        with urlopen(Request(base + "/catalog", headers={"Authorization": "Bearer private-test-token"})) as response:
            catalog = json.load(response)
        assert catalog["pcs"][0]["id"] == "pc"
        assert catalog["profiles"][0]["id"] == "qa"
        assert "MUST_NOT_APPEAR" not in json.dumps(catalog)
    finally:
        server.shutdown()
        server.server_close()


def test_cli_real_localhost_upload_submit_and_collect(tmp_path):
    runner = FakeExecutor()
    runner.done.set()
    manager = coordinator(tmp_path, runner)
    server = make_server(manager, "cli-flow-token", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cli = Path(__file__).resolve().parents[1] / "tools" / "remote_execution.py"
    env = dict(os.environ, FLOW_TOKEN="cli-flow-token", PYTHONIOENCODING="utf-8")
    prefix = [sys.executable, str(cli), "--server", f"http://127.0.0.1:{server.server_port}", "--token-env", "FLOW_TOKEN"]
    def command(*args):
        result = subprocess.run(prefix + list(args), capture_output=True, env=env, encoding="utf-8")
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    try:
        package, identity = bundle(tmp_path)
        path = tmp_path / "upload.zip"
        path.write_bytes(package)
        assert command("upload", str(path), identity)["bundle_id"] == identity
        job = command("submit", "pc", "qa", identity, "--no-restore-after")
        wait_state(manager, job["id"], {"completed"})
        assert command("status", job["id"])["status"] == "completed"
        command("collect", job["id"], str(tmp_path / "cli-results"))
        assert (tmp_path / "cli-results" / "result.json").read_text() == '{"pass":true}'
    finally:
        server.shutdown()
        server.server_close()


def test_result_views_preserve_original_hash_and_rewrite_known_evidence(tmp_path):
    from remote.result_views import derive_views
    evidence = tmp_path / "workspace" / "Evidence"
    evidence.mkdir(parents=True)
    (evidence / "image.png").write_bytes(b"fixture-image")
    reports = tmp_path / "workspace" / "Reports"
    reports.mkdir()
    original = {"results": [{"evidence": [r"C:\BellalunRemote\job1\workspace\Evidence\image.png", r"C:\outside\private.txt"]}]}
    raw = json.dumps(original).encode()
    (reports / "Result_test.json").write_bytes(raw)
    (reports / "Result_test.html").write_text('<img src="file:///C:/BellalunRemote/job1/workspace/Evidence/image.png">')
    derivations = derive_views(tmp_path, r"C:\BellalunRemote\job1\workspace")
    result = json.loads((tmp_path / "view" / "Reports" / "Result_test.json").read_text(encoding="utf-8"))
    assert result["results"][0]["evidence"][0] == "../Evidence/image.png"
    assert "수집 범위 밖" in result["results"][0]["evidence"][1]
    assert '../Evidence/image.png' in (tmp_path / "view" / "Reports" / "Result_test.html").read_text()
    assert (reports / "Result_test.json").read_bytes() == raw
    assert any(d["source_sha256"] == hashlib.sha256(raw).hexdigest() for d in derivations)


def test_shared_interlock_requires_durable_owned_exclusive_contract(tmp_path):
    from remote.interlock import SharedInterlock
    lock = SharedInterlock({})
    lease = {"target": "pc", "owner": "job1", "domain": "vhd-and-qa", "exclusive": True,
             "durable": True, "lease_id": "lease1"}
    pc = {"shared_interlock": {"target": "pc"}}
    with mock.patch.object(lock, "_call", return_value=lease):
        assert lock.acquire({"id": "job1"}, pc)["lease_id"] == "lease1"
    for change in ({"durable": False}, {"exclusive": False}, {"owner": "other"}, {"expires": 123}):
        with mock.patch.object(lock, "_call", return_value={**lease, **change}):
            with pytest.raises(RemoteError):
                lock.acquire({"id": "job1"}, pc)


def test_cli_real_subprocess_bundle_and_missing_token_fail_closed(tmp_path):
    source = tmp_path / "code"
    source.mkdir()
    (source / "run.py").write_text("pass")
    cli = Path(__file__).resolve().parents[1] / "tools" / "remote_execution.py"
    process = subprocess.run([sys.executable, str(cli), "bundle", str(source), str(tmp_path / "code.zip"), "run.py"],
                             capture_output=True, text=True)
    assert process.returncode == 0
    assert len(json.loads(process.stdout)["bundle_id"]) == 64
    env = dict(os.environ)
    env.pop("NONEXISTENT_QA_TOKEN", None)
    blocked = subprocess.run([sys.executable, str(cli), "--token-env", "NONEXISTENT_QA_TOKEN", "list"],
                             capture_output=True, env=env)
    assert blocked.returncode == 2


def test_code_bundle_tampered_after_upload_is_blocked_before_executor(tmp_path):
    runner = FakeExecutor()
    manager = coordinator(tmp_path, runner)
    data, identity = bundle(tmp_path)
    manager.add_bundle(data, identity)
    (manager.root / "bundles" / identity / "package.zip").write_bytes(b"corrupted")
    job = manager.submit("pc", "qa", identity)
    assert wait_state(manager, job["id"], {"blocked"})["status"] == "blocked"
    assert not runner.started.is_set()


def test_vhd_jobs_missing_or_active_blocks(tmp_path):
    runner = WinRMExecutor(session_factory=lambda *a, **k: None)
    with pytest.raises(RemoteError):
        runner._vhd_guard({})
    raw = json.dumps([{"target_ip": "fixture-pc", "status": "running"}]).encode()
    with mock.patch("remote.winrm_executor.urlopen", return_value=io.BytesIO(raw)):
        with pytest.raises(RemoteError):
            runner._vhd_guard({"vhd_jobs_url": "http://localhost/jobs", "vhd_target": "fixture-pc"})
