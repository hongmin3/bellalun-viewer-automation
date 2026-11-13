"""정상 완주 후 해당 실행 Image 격리 파일만 삭제하는 안전 경계."""
import json
from pathlib import Path
from unittest import mock

import pytest

from core.run_preservation import PreservationError, RunPreservation, snapshot


def finished_run(tmp_path, image_name="Image", restore=True, shared=True):
    image = tmp_path / "product" / "Image"
    config = tmp_path / "product" / "Config"
    for path in [image, config]:
        path.mkdir(parents=True)
        (path / "existing").write_bytes(b"original")
    share = tmp_path / "share"
    share.mkdir()
    run = RunPreservation(tmp_path / "work", "clean-1", {image_name: image, "Config": config},
                          restore_after=restore, storage_dir=share if shared else None)
    run.prepare()
    (image / "generated").mkdir()
    (image / "generated" / "one.dcm").write_bytes(b"new1")
    (image / "generated" / "two.dcm").write_bytes(b"newtwo")
    (config / "generated").write_bytes(b"keep config")
    (image / "existing").write_bytes(b"changed image")
    assert run.finalize()["status"] == ("verified" if restore else "preserved")
    return image, share, run


def quarantine_file(run, leaf):
    for operation in run.journal["delta_operations"]:
        if operation["kind"] == "quarantine" and operation["root"] == "Image":
            path = Path(operation["destination"]) / leaf
            if path.exists():
                return path
    raise AssertionError(leaf)


def test_cleanup_removes_only_generated_image_quarantine_and_keeps_every_copy(tmp_path):
    image, share, run = finished_run(tmp_path)
    baseline = snapshot(image)
    remote = snapshot(share)
    other = tmp_path / "product" / ".Image.bellalun-other-quarantine"
    other.mkdir()
    (other / "keep").write_bytes(b"other run")
    one, two = quarantine_file(run, "one.dcm"), quarantine_file(run, "two.dcm")
    result = run.cleanup_generated_images(normal_completion=True, services_verified=True)
    assert result["status"] == "completed"
    assert result["files_removed"] == 2
    assert result["logical_bytes_removed"] == 10
    assert not one.exists() and not two.exists()
    assert snapshot(image) == baseline
    assert snapshot(share) == remote
    assert (other / "keep").read_bytes() == b"other run"
    assert any(p.read_bytes() == b"keep config" for p in image.parent.glob(".Config.*/*"))
    assert run.finalize()["status"] == "verified"
    assert run.cleanup_generated_images(normal_completion=True, services_verified=True) == result


@pytest.mark.parametrize("normal,services,kwargs,reason", [
    (False, True, {}, "not_normal_completion"),
    (True, False, {}, "services_not_verified"),
    (True, True, {"restore": False}, "restore_not_selected"),
    (True, True, {"shared": False}, "shared_storage_not_selected"),
    (True, True, {"image_name": "image"}, "image_root_not_configured"),
])
def test_cleanup_skip_gates_leave_all_files(tmp_path, normal, services, kwargs, reason):
    image, share, run = finished_run(tmp_path, **kwargs)
    before = snapshot(tmp_path / "product")
    result = run.cleanup_generated_images(normal_completion=normal, services_verified=services)
    assert result["status"] == "skipped"
    assert result["reason"] == reason
    assert result["files_removed"] == 0
    assert snapshot(tmp_path / "product") == before


@pytest.mark.parametrize("fault", ["local_tamper", "remote_tamper", "disconnect", "path_escape", "other_run"])
def test_cleanup_verifies_all_files_and_ownership_before_any_delete(tmp_path, fault):
    image, share, run = finished_run(tmp_path)
    one, two = quarantine_file(run, "one.dcm"), quarantine_file(run, "two.dcm")
    if fault == "local_tamper":
        two.write_bytes(b"changed locally")
    elif fault == "remote_tamper":
        (run.data_dir / "archive" / "Image" / "generated" / "two.dcm").write_bytes(b"wrong")
    elif fault == "disconnect":
        share.rename(tmp_path / "offline")
    else:
        operation = next(op for op in run.journal["delta_operations"] if op["kind"] == "quarantine")
        operation["destination"] = str(tmp_path / ("outside" if fault == "path_escape" else ".Image.bellalun-other-quarantine/0"))
    result = run.cleanup_generated_images(normal_completion=True, services_verified=True)
    assert result["status"] == "cleanup_required"
    assert result["files_removed"] == 0
    assert one.exists() and two.exists()
    assert run.journal["result"]["status"] == "cleanup_required"
    assert run.journal["result"]["restoration_status"] == "verified"
    assert RunPreservation.pending(run.workspace) == [run.run_id]
    assert RunPreservation.recover(run.workspace, run.run_id)["status"] == "cleanup_required"


def test_cleanup_partial_failure_then_loaded_retry_is_accurate(tmp_path):
    image, share, run = finished_run(tmp_path)
    one, two = quarantine_file(run, "one.dcm"), quarantine_file(run, "two.dcm")
    real_unlink = Path.unlink
    def fail_second(path, *args, **kwargs):
        if path == two:
            raise PermissionError("synthetic file busy")
        return real_unlink(path, *args, **kwargs)
    with mock.patch.object(Path, "unlink", fail_second):
        result = run.cleanup_generated_images(normal_completion=True, services_verified=True)
    assert result["status"] == "cleanup_required"
    assert result["files_removed"] == 1 and result["logical_bytes_removed"] == 4
    assert not one.exists() and two.exists()
    loaded = RunPreservation.load(run.workspace, run.run_id)
    result = loaded.cleanup_generated_images(normal_completion=True, services_verified=True)
    assert result["status"] == "completed"
    assert result["files_removed"] == 2 and result["logical_bytes_removed"] == 10
    assert RunPreservation.pending(run.workspace) == []


def test_cleanup_crash_after_unlink_is_resumed_from_durable_intent(tmp_path):
    image, share, run = finished_run(tmp_path)
    one, two = quarantine_file(run, "one.dcm"), quarantine_file(run, "two.dcm")
    real_unlink = Path.unlink
    def stop_after_unlink(path, *args, **kwargs):
        real_unlink(path, *args, **kwargs)
        if path == one:
            raise KeyboardInterrupt("power lost")
    with mock.patch.object(Path, "unlink", stop_after_unlink):
        with pytest.raises(KeyboardInterrupt):
            run.cleanup_generated_images(normal_completion=True, services_verified=True)
    assert not one.exists() and two.exists()
    assert RunPreservation.pending(run.workspace) == [run.run_id]
    loaded = RunPreservation.load(run.workspace, run.run_id)
    assert loaded.cleanup_generated_images()["status"] == "skipped"
    assert two.exists()
    result = loaded.cleanup_generated_images(normal_completion=True, services_verified=True)
    assert result["status"] == "completed"
    assert result["files_removed"] == 2 and result["logical_bytes_removed"] == 10


def test_cleanup_links_block_all_deletion(tmp_path):
    image, share, run = finished_run(tmp_path)
    one, two = quarantine_file(run, "one.dcm"), quarantine_file(run, "two.dcm")
    target = tmp_path / "outside"
    target.write_bytes(b"outside")
    try:
        (one.parent / "link").symlink_to(target)
    except OSError:
        pytest.skip("symlink 권한 없음")
    result = run.cleanup_generated_images(normal_completion=True, services_verified=True)
    assert result["status"] == "cleanup_required" and result["files_removed"] == 0
    assert one.exists() and two.exists() and target.read_bytes() == b"outside"


def test_cleanup_journal_failure_returns_required_and_keeps_local_pending(tmp_path):
    image, share, run = finished_run(tmp_path)
    one, two = quarantine_file(run, "one.dcm"), quarantine_file(run, "two.dcm")
    with mock.patch.object(run, "_save", side_effect=OSError("journal replace busy")):
        result = run.cleanup_generated_images(normal_completion=True, services_verified=True)
    assert result["status"] == "cleanup_required"
    assert result["files_removed"] == 0
    assert one.exists() and two.exists()
    assert RunPreservation.pending(run.workspace) == [run.run_id]


def test_cleanup_disconnected_share_can_retry_after_reconnect(tmp_path):
    image, share, run = finished_run(tmp_path)
    offline = tmp_path / "offline"
    share.rename(offline)
    assert run.cleanup_generated_images(normal_completion=True, services_verified=True)["status"] == "cleanup_required"
    offline.rename(share)
    loaded = RunPreservation.load(run.workspace, run.run_id)
    result = loaded.cleanup_generated_images(normal_completion=True, services_verified=True)
    assert result["status"] == "completed" and result["files_removed"] == 2
    assert RunPreservation.pending(run.workspace) == []


def test_cleanup_unfinished_restore_and_failed_db_never_delete(tmp_path):
    image, share, run = finished_run(tmp_path)
    one = quarantine_file(run, "one.dcm")
    for field, value in [("status", "mismatch"), ("db", {"status": "mismatch"})]:
        original = run.journal["result"][field]
        run.journal["result"][field] = value
        result = run.cleanup_generated_images(normal_completion=True, services_verified=True)
        assert result["status"] == "skipped" and result["reason"] == "restoration_not_verified"
        assert one.exists()
        run.journal["result"][field] = original


def test_cleanup_completion_proof_is_pinned_and_never_overwritten(tmp_path):
    image, share, run = finished_run(tmp_path)
    report = {"meta": {"run_id": run.run_id, "chain_completed": True}, "results": ["synthetic"]}
    proof = run.pin_cleanup_completion(report, "run-regression")
    path = Path(proof["report"])
    assert json.loads(path.read_text(encoding="utf-8")) == report
    assert len(proof["sha256"]) == 64
    assert proof["run_id"] == run.run_id and proof["command"] == "run-regression"
    assert RunPreservation.load(run.workspace, run.run_id).journal["normal_completion_before_cleanup"] == proof
    assert run.pin_cleanup_completion(report, "run-regression") == proof
    with pytest.raises(PreservationError):
        run.pin_cleanup_completion(dict(report, results=["different"]), "run-regression")
    assert json.loads(path.read_text(encoding="utf-8")) == report


@pytest.mark.parametrize("run_id,completed,command", [("different", True, "run-regression"),
                                                       ("clean-1", False, "run-regression"),
                                                       ("clean-1", True, "run-wf01")])
def test_cleanup_completion_proof_rejects_unrelated_or_unfinished_report(tmp_path, run_id, completed, command):
    image, share, run = finished_run(tmp_path)
    with pytest.raises(PreservationError):
        run.pin_cleanup_completion({"meta": {"run_id": run_id, "chain_completed": completed}}, command)
    assert not (run.run_dir / "cleanup-completion.json").exists()
