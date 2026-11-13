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
            if "BELLALUN_BUNDLE_CACHE_PROBE" in script:
                return Response(b'{"hit":false}')
            if "BELLALUN_EXECUTION_POLL" in script:
                return Response(json.dumps({"receipt": json.loads(content), "progress": None, "tail": []}).encode())
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
                        "run-regression", "{restore_after}"], "timeout_seconds": 30, "worst_case_seconds": 20}
    with mock.patch.object(runner, "_vhd_guard"):
        result = runner.execute({"id": "job1", "bundle_id": "0" * 64, "restore_after": True},
                                pc, profile, b"zip bytes", tmp_path, threading.Event(), lambda line: None)
    assert result["status"] == "uncertain"  # receipt만으로 정리 완료나 잠금 해제를 주장할 수 없다.
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


class TransferSession:
    """호출마다 지연이 있는 WinRM을 call budget으로 모델링한다(실제 대기 없음)."""
    def __init__(self, hit=False, reject=None):
        self.calls = []
        self.hit = hit
        self.reject = reject
        self.estimated_delay_seconds = 0
    def run_ps(self, script):
        self.calls.append(script)
        self.estimated_delay_seconds += .2
        class Response:
            status_code = 0
            std_err = b""
            std_out = b""
        result = Response()
        if "BELLALUN_BUNDLE_CACHE_PROBE" in script:
            result.std_out = json.dumps({"hit": self.hit}).encode()
        if self.reject and self.reject in script:
            result.status_code = 1
        return result


def test_large_bundle_download_has_constant_winrm_call_budget_and_no_secret_values():
    runner = WinRMExecutor(environ={"DOWNLOAD_TOKEN": "must-not-appear-in-script"})
    session = TransferSession()
    package = b"x" * (100 * 1024 * 1024)
    pc = {"work_dir": r"C:\BellalunRemote", "bundle_download_base": "https://qa.example.invalid",
          "bundle_token_env": "DOWNLOAD_TOKEN"}
    path = runner.ensure_package(session, {"id": "job1", "bundle_id": "a" * 64}, pc, package)
    assert path.endswith(hashlib.sha256(package).hexdigest() + ".zip")
    assert len(session.calls) <= 3
    assert session.estimated_delay_seconds <= .6
    scripts = "\n".join(session.calls)
    assert scripts.count("Invoke-WebRequest") == 1
    assert "GetEnvironmentVariable" in scripts
    assert "DOWNLOAD_TOKEN" in scripts
    assert "must-not-appear-in-script" not in scripts
    assert "MaximumRedirection 0" in scripts
    assert "SkipCertificateCheck" not in scripts
    assert "ServerCertificateValidationCallback" not in scripts
    assert all(len(base64.b64encode(script.encode("utf-16-le"))) + 100 < 8191 for script in session.calls)


def test_bundle_cache_hit_never_retransfers_even_without_download_config():
    runner = WinRMExecutor()
    session = TransferSession(hit=True)
    runner.ensure_package(session, {"id": "job1", "bundle_id": "a" * 64},
                          {"work_dir": r"C:\BellalunRemote"}, b"x" * (100 * 1024 * 1024))
    assert len(session.calls) == 1
    assert "Invoke-WebRequest" not in session.calls[0]
    assert "FromBase64String" not in session.calls[0]
    assert "Get-FileHash" in session.calls[0]
    assert "ReparsePoint" in session.calls[0]


def test_large_bundle_missing_https_config_is_blocked_after_probe_only():
    runner = WinRMExecutor()
    session = TransferSession()
    with pytest.raises(RemoteError):
        runner.ensure_package(session, {"id": "job1", "bundle_id": "a" * 64},
                              {"work_dir": r"C:\BellalunRemote"}, b"x" * (1024 * 1024))
    assert len(session.calls) == 1
    with pytest.raises(RemoteError):
        runner._put(session, r"C:\bounded.txt", b"x" * (1024 * 1024))
    assert len(session.calls) == 1


@pytest.mark.parametrize("failure", ["BELLALUN_BUNDLE_CACHE_PROBE", "BELLALUN_BUNDLE_HTTPS_DOWNLOAD"])
def test_cache_reparse_corruption_and_fresh_download_failure_never_fall_back(failure):
    runner = WinRMExecutor()
    session = TransferSession(reject=failure)
    pc = {"work_dir": r"C:\BellalunRemote", "bundle_download_base": "https://qa.example.invalid",
          "bundle_token_env": "DOWNLOAD_TOKEN"}
    with pytest.raises(RemoteError):
        runner.ensure_package(session, {"id": "job1", "bundle_id": "a" * 64}, pc, b"x" * (1024 * 1024))
    assert len(session.calls) <= 2


def test_authenticated_binary_bundle_download_returns_original_bytes_and_hash(tmp_path):
    manager = coordinator(tmp_path)
    data, identity = bundle(tmp_path)
    manager.add_bundle(data, identity)
    server = make_server(manager, "binary-fixture-token", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/bundles/{identity}/download"
    try:
        with pytest.raises(HTTPError) as failure:
            urlopen(url)
        assert failure.value.code == 401
        with urlopen(Request(url, headers={"Authorization": "Bearer binary-fixture-token"})) as response:
            received = response.read()
            assert response.headers["Content-Type"] == "application/zip"
            assert response.headers["X-Content-SHA256"] == hashlib.sha256(data).hexdigest()
        assert received == data
        unpack_bundle(received, tmp_path / "binary-unpacked", identity)
        (manager.root / "bundles" / identity / "package.zip").write_bytes(b"corrupt")
        with pytest.raises(HTTPError):
            urlopen(Request(url, headers={"Authorization": "Bearer binary-fixture-token"}))
    finally:
        server.shutdown()
        server.server_close()


def test_live_poll_is_one_bounded_call_and_deduplicates_progress_tail():
    runner = WinRMExecutor()
    class PollSession(TransferSession):
        def run_ps(self, script):
            super().run_ps(script)
            class Response:
                status_code = 0
                std_err = b""
                std_out = json.dumps({"receipt": None, "progress": {"run_id": "20261113-120000-aabbccdd",
                    "current_tc": "TC_fixture", "index": 2, "total": 13}, "tail": ["first", "second"]}).encode()
            return Response()
    session = PollSession()
    state = runner._poll(session, r"C:\BellalunRemote\job1")
    assert len(session.calls) == 1
    script = session.calls[0]
    assert "receipt.json" in script and "qa_progress.json" in script and "stdout.log" in script
    assert "-Tail 5" in script and "Substring" in script
    logs, seen = [], {}
    runner._emit_progress(state, seen, logs.append, {})
    runner._emit_progress(state, seen, logs.append, {})
    assert len(logs) == 3
    assert "TC_fixture" in logs[0] and "2/13" in logs[0]
    state["tail"] = ["second", "third"]
    runner._emit_progress(state, seen, logs.append, {})
    assert logs[-1] == "third"
    assert logs.count("second") == 1


def test_operational_profile_timeout_requires_worst_case_margin():
    runner = WinRMExecutor(session_factory=lambda *a, **k: None, environ={"QA_PASS": "secret"})
    pc = {"enabled": True, "endpoint": "https://fixture.invalid:5986/wsman", "user": "qa",
          "password_env": "QA_PASS", "work_dir": r"C:\BellalunRemote"}
    base = {"argv": ["engine.exe", "run-regression", "{restore_after}"], "worst_case_seconds": 18000}
    runner.validate(pc, base)
    from remote.winrm_executor import DEFAULT_TIMEOUT_SECONDS, DEFAULT_STOP_GRACE_SECONDS
    assert DEFAULT_TIMEOUT_SECONDS == 21600
    assert str(DEFAULT_TIMEOUT_SECONDS + DEFAULT_STOP_GRACE_SECONDS + 60) in runner.task_script("job1", pc, base)
    with pytest.raises(RemoteError):
        runner.validate(pc, {**base, "timeout_seconds": 18000})
    with pytest.raises(RemoteError):
        runner.validate(pc, {"argv": base["argv"]})
    args = runner._arguments({"id": "job1", "restore_after": False}, pc, base)
    assert "--stop-file" in args
    assert args[args.index("--stop-file") + 1] == r"C:\BellalunRemote\job1\stop.request"


def test_cooperative_cancel_requests_stop_before_forced_kill_and_waits_for_receipt(tmp_path):
    runner = WinRMExecutor(poll_seconds=0)
    session = TransferSession()
    receipt = engine_output(tmp_path)
    receipt["exit_code"] = 130
    record_path = tmp_path / "workspace" / "Runs" / receipt["engine_run_id"] / "run.json"
    record = json.loads(record_path.read_text())
    record.update(status="stopped", exit_code=130)
    record_path.write_text(json.dumps(record))
    preservation = tmp_path / "workspace" / "preservation" / receipt["engine_run_id"]
    preservation.mkdir(parents=True)
    (preservation / "restoration.json").write_text(json.dumps({"run_id": receipt["engine_run_id"], "status": "verified"}))
    job = {"id": "job1", "restore_after": True}
    pc = {"work_dir": r"C:\BellalunRemote"}
    with mock.patch.object(runner, "_poll", return_value={"receipt": receipt, "progress": None, "tail": []}), \
         mock.patch.object(runner, "_collect"), mock.patch.object(runner, "_stop") as forced:
        result = runner._cancel_running(session, job, pc, {"argv": ["engine", "run-regression"],
                                         "stop_grace_seconds": 5}, tmp_path, lambda line: None, {})
    assert result["status"] == "cancelled"
    assert result["stopped_verified"]
    assert not forced.called
    assert "stop.request" in session.calls[0]


def test_stopped_supervisor_without_restoration_result_is_uncertain(tmp_path):
    runner = WinRMExecutor(poll_seconds=0)
    receipt = engine_output(tmp_path)
    receipt["exit_code"] = 130
    path = tmp_path / "workspace" / "Runs" / receipt["engine_run_id"] / "run.json"
    record = json.loads(path.read_text())
    record.update(status="stopped", exit_code=130)
    path.write_text(json.dumps(record))
    with mock.patch.object(runner, "_collect"):
        outcome = runner._finish_receipt(TransferSession(), {"id": "job1", "restore_after": True},
                                         {"work_dir": r"C:\BellalunRemote"}, {"argv": ["engine", "run-regression"]},
                                         tmp_path, receipt, cancelling=True)
    assert outcome["status"] == "uncertain"
    assert not outcome["stopped_verified"]
    assert outcome["process_stopped_verified"] is True


def test_uncertain_force_stop_after_grace_keeps_lock_status(tmp_path):
    runner = WinRMExecutor(poll_seconds=0)
    with mock.patch.object(runner, "_request_stop"), \
         mock.patch.object(runner, "_poll", return_value={"receipt": None, "progress": None, "tail": []}), \
         mock.patch.object(runner, "_stop", return_value=False) as forced, \
         mock.patch("remote.winrm_executor.time.monotonic", side_effect=[0, 2]):
        result = runner._cancel_running(TransferSession(), {"id": "job1"}, {"work_dir": r"C:\BellalunRemote"},
                                        {"stop_grace_seconds": 1}, tmp_path, lambda line: None, {})
    assert forced.called
    assert result["status"] == "uncertain"


@pytest.mark.parametrize("code,supervisor", [(0, "completed"), (1, "completed"),
                                             (2, "abnormal"), (3, "abnormal"), (130, "stopped")])
@pytest.mark.parametrize("restore_after,restoration_status", [(True, None), (True, "error"),
                                                             (False, None), (False, "error")])
def test_every_started_exit_without_verified_cleanup_keeps_lock_uncertain(
        tmp_path, code, supervisor, restore_after, restoration_status):
    runner = WinRMExecutor()
    receipt = engine_output(tmp_path, code=code, status=supervisor)
    if restoration_status is not None:
        path = tmp_path / "workspace" / "preservation" / receipt["engine_run_id"] / "restoration.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"run_id": receipt["engine_run_id"], "status": restoration_status}))
    with mock.patch.object(runner, "_collect"):
        result = runner._finish_receipt(TransferSession(), {"id": "job1", "restore_after": restore_after},
                                        {"work_dir": r"C:\BellalunRemote"}, {"argv": ["engine", "run-regression"]},
                                        tmp_path, receipt, cancelling=False)
    assert result["status"] == "uncertain"
    assert result["stopped_verified"] is False
    assert result["process_stopped_verified"] is True
    assert result["cleanup_verified"] is False


def test_restore_failure_holds_shared_lease_and_coordinator_pc_lock(tmp_path):
    class FailureExecutor(WinRMExecutor):
        def validate(self, pc, profile):
            pass
        def acquire_interlock(self, job, pc):
            return {"lease_id": "fixture-lease"}
        def _execute(self, job, pc, profile, package, output, cancel, log, marker):
            marker["task_requested"] = True
            receipt = engine_output(output, code=3, status="abnormal")
            receipt["job_id"] = job["id"]
            return self._finish_receipt(TransferSession(), job, pc, profile, output, receipt)
        def _collect(self, session, root, output):
            pass
    runner = FailureExecutor()
    manager = Coordinator(tmp_path / "server", {"pc": {"work_dir": r"C:\BellalunRemote"}},
                          {"qa": {"argv": ["engine", "run-regression"]}}, runner)
    package, identity = bundle(tmp_path)
    manager.add_bundle(package, identity)
    with mock.patch.object(runner, "release_interlock") as release:
        job = manager.submit("pc", "qa", identity, restore_after=True)
        record = wait_state(manager, job["id"], {"uncertain", "abnormal"})
        assert record["status"] == "uncertain"
        assert not release.called
        with pytest.raises(RemoteError):
            manager.submit("pc", "qa", identity, restore_after=False)


@pytest.mark.parametrize("route", ["download", "duplicate_upload"])
def test_legacy_bundle_without_zip_digest_is_verified_and_migrated_atomically(tmp_path, route):
    manager = coordinator(tmp_path)
    package, identity = bundle(tmp_path)
    manager.add_bundle(package, identity)
    directory = manager.root / "bundles" / identity
    (directory / "package.sha256").unlink()
    if route == "download":
        received, digest = manager.bundle_download(identity)
        assert received == package
        assert digest == hashlib.sha256(package).hexdigest()
    else:
        manager.add_bundle(package, identity)
    assert (directory / "package.sha256").read_text() == hashlib.sha256(package).hexdigest()
    assert (directory / "package.zip").read_bytes() == package


@pytest.mark.parametrize("route", ["download", "duplicate_upload"])
def test_legacy_corrupt_bundle_is_not_blessed_with_digest(tmp_path, route):
    manager = coordinator(tmp_path)
    package, identity = bundle(tmp_path)
    manager.add_bundle(package, identity)
    directory = manager.root / "bundles" / identity
    (directory / "package.sha256").unlink()
    (directory / "package.zip").write_bytes(b"corrupt")
    with pytest.raises((BundleError, RemoteError)):
        if route == "download":
            manager.bundle_download(identity)
        else:
            manager.add_bundle(b"corrupt", identity)
    assert not (directory / "package.sha256").exists()


@pytest.mark.parametrize("prefix", [["BellalunAuto.exe"], ["python.exe", "-m", "bellalunauto.app"],
                                    ["python.exe", "launcher.py"]])
def test_stop_file_is_an_application_option_after_python_launcher(tmp_path, prefix):
    runner = WinRMExecutor()
    profile = {"argv": prefix + ["--workspace", "{workspace}", "run-regression", "{restore_after}"]}
    result = runner._arguments({"id": "job1", "restore_after": False}, {"work_dir": r"C:\BellalunRemote"}, profile)
    assert result[:len(prefix)] == prefix
    assert result[result.index("run-regression") - 2:result.index("run-regression")] == ["--stop-file", r"C:\BellalunRemote\job1\stop.request"]


@pytest.mark.parametrize("exception_kind", ["bundle", "blocked"])
def test_errors_after_task_start_are_never_misreported_as_preflight_block(tmp_path, exception_kind):
    from remote.coordinator import RemoteBlocked
    class StartedError(WinRMExecutor):
        def validate(self, pc, profile):
            pass
        def acquire_interlock(self, job, pc):
            return {"lease_id": "fixture-lease"}
        def _execute(self, job, pc, profile, package, output, cancel, log, marker):
            marker["task_requested"] = True
            if exception_kind == "bundle":
                raise BundleError("result path rejected")
            raise RemoteBlocked("post-start authority response unavailable")
    runner = StartedError()
    manager = coordinator(tmp_path, runner)
    package, identity = bundle(tmp_path)
    manager.add_bundle(package, identity)
    with mock.patch.object(runner, "release_interlock") as release:
        job = manager.submit("pc", "qa", identity, restore_after=True)
        record = wait_state(manager, job["id"], {"uncertain", "blocked"})
        assert record["status"] == "uncertain"
        assert not release.called
        with pytest.raises(RemoteError):
            manager.submit("pc", "qa", identity)
