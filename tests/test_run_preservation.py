"""파일 보존의 실제 복사/해시/복구 경계 시험."""
import json
import os
from pathlib import Path
from unittest import mock

import pytest

from core.run_preservation import (PreservationError, RecoveryRequired,
                                   RunPreservation, roots_from_config, snapshot)


def setup_run(tmp_path, restore=True):
    source = tmp_path / "product"
    source.mkdir()
    (source / "original").write_bytes(b"before")
    (source / "empty").mkdir()
    run = RunPreservation(tmp_path / "work", "run-1", {"image": source}, restore)
    return source, run


def test_manifest_real_copy_and_content_restoration(tmp_path):
    source, run = setup_run(tmp_path)
    before = snapshot(source)
    prepared = run.prepare()
    assert prepared["status"] == "prepared"
    stamp = (source / "original").stat()
    (source / "original").write_bytes(b"change")
    os.utime(source / "original", ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    (source / "new").write_bytes(b"new evidence")
    result = run.finalize()
    assert result["status"] == "verified"
    assert snapshot(source) == before
    archive = Path(result["roots"]["image"]["archive"])
    assert (archive / "new").read_bytes() == b"new evidence"
    assert (archive / "original").read_bytes() == b"change"
    assert Path(prepared["manifest"]).is_file()


def test_deleted_files_empty_dirs_and_missing_roots(tmp_path):
    source, run = setup_run(tmp_path)
    run.roots["absent"] = tmp_path / "absent"
    run.prepare()
    (source / "original").unlink()
    run.roots["absent"].mkdir()
    (run.roots["absent"] / "new").write_bytes(b"keep")
    result = run.finalize()
    assert (source / "original").read_bytes() == b"before"
    assert (source / "empty").is_dir()
    assert not run.roots["absent"].exists()
    assert result["roots"]["absent"]["status"] == "no_prior_copy"
    assert (Path(result["roots"]["absent"]["archive"]) / "new").read_bytes() == b"keep"


def test_missing_backup_never_changes_source(tmp_path):
    source, run = setup_run(tmp_path)
    run.prepare()
    (run.run_dir / "before" / "image" / "original").unlink()
    (source / "original").write_bytes(b"changed")
    result = run.finalize()
    assert result["status"] == "mismatch"
    assert (source / "original").read_bytes() == b"changed"


def test_overlapping_backup_and_preexisting_refused(tmp_path):
    source, run = setup_run(tmp_path)
    with pytest.raises(PreservationError):
        RunPreservation(source / "backup", "x", {"a": source}).prepare()
    with pytest.raises(PreservationError):
        RunPreservation(tmp_path / "work", "x", {"a": source, "b": source / "empty"}).prepare()
    run.run_dir.mkdir(parents=True)
    with pytest.raises(PreservationError):
        run.prepare()


def test_interrupted_run_blocks_until_explicit_recovery(tmp_path):
    source, run = setup_run(tmp_path)
    run.prepare()
    (source / "original").write_bytes(b"after")
    with pytest.raises(RecoveryRequired):
        RunPreservation(run.workspace, "run-2", {"image": source}).prepare()
    recovered = RunPreservation.recover(run.workspace, "run-1", restore_after=True)
    assert recovered["status"] == "verified"
    assert (source / "original").read_bytes() == b"before"
    RunPreservation(run.workspace, "run-2", {"image": source}).prepare()


def test_copy_failure_durable_journal_and_no_execution_permission(tmp_path):
    source, run = setup_run(tmp_path)
    with mock.patch("core.run_preservation.shutil.copy2", side_effect=OSError("copy failed")):
        with pytest.raises(PreservationError):
            run.prepare()
    journal = json.loads((run.run_dir / "journal.json").read_text())
    assert journal["state"] == "error"
    assert (source / "original").read_bytes() == b"before"
    with pytest.raises(RecoveryRequired):
        RunPreservation(run.workspace, "run-2", {"image": source}).prepare()


def test_restore_failure_never_loses_current_data(tmp_path):
    source, run = setup_run(tmp_path)
    run.prepare()
    (source / "original").write_bytes(b"after")
    original_copy = __import__("shutil").copy2
    def failing_copy(src, dst, **kwargs):
        if "before" in Path(src).parts:
            raise OSError("restore failed")
        return original_copy(src, dst, **kwargs)
    with mock.patch("core.run_preservation.shutil.copy2", side_effect=failing_copy):
        result = run.finalize()
    assert result["status"] == "error"
    assert (run.run_dir / "archive" / "image" / "original").read_bytes() == b"after"
    assert RunPreservation.recover(run.workspace, "run-1")["status"] == "verified"


def test_links_refused_even_through_parent(tmp_path):
    source, run = setup_run(tmp_path)
    link = tmp_path / "alias"
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip("symlink 권한 없음")
    with pytest.raises(PreservationError):
        RunPreservation(tmp_path / "work", "x", {"linked": link / "empty"}).prepare()
    (source / "link").symlink_to(source / "original")
    with pytest.raises(PreservationError):
        run.prepare()


def test_config_scope_is_explicit():
    roots = roots_from_config({"data_dir": "D:/data", "xipl": {"parameter_dir": "C:/params"}}, "E:/")
    assert set(roots) == {"Config", "Image", "ImageTemp", "Export", "ExportSettingTemp", "xipl", "usb"}
    assert roots["usb"].name == "BellalunWU09"


def test_db_callbacks_only_injected_and_restore_verified(tmp_path):
    source, run = setup_run(tmp_path)
    class Adapter:
        def backup(self, destination):
            (destination / "db.bak").write_bytes(b"db")
            return {"scope": "test table columns"}
        def verify_backup(self, destination, metadata):
            return (destination / "db.bak").read_bytes() == b"db"
        def restore(self, destination, metadata):
            self.restored = True
        def verify_restored(self, destination, metadata):
            return self.restored
    run.db_adapter = Adapter()
    run.prepare()
    assert run.finalize()["db"]["status"] == "verified"


def test_finalize_is_idempotent_after_verified_restore(tmp_path):
    source, run = setup_run(tmp_path)
    run.prepare()
    first = run.finalize()
    (source / "external").write_bytes(b"created after completion")
    assert run.finalize() == first
    assert (source / "external").is_file()


def test_backup_extra_file_and_manifest_tampering_block_restore(tmp_path):
    source, run = setup_run(tmp_path)
    run.prepare()
    (run.run_dir / "before" / "image" / "extra").write_bytes(b"unexpected")
    assert run.finalize()["status"] == "mismatch"
    assert (source / "original").read_bytes() == b"before"


def test_backup_read_failure_and_corrupt_journal_block_new_run(tmp_path):
    source, run = setup_run(tmp_path)
    with mock.patch("core.run_preservation._hash", side_effect=PermissionError("locked")):
        with pytest.raises(PreservationError):
            run.prepare()
    (run.run_dir / "journal.json").write_text("{broken")
    assert RunPreservation.pending(run.workspace) == ["run-1"]


def test_partial_prepare_requires_acknowledgement_not_guessed_restore(tmp_path):
    source, run = setup_run(tmp_path)
    with mock.patch("core.run_preservation.shutil.copy2", side_effect=OSError("partial")):
        with pytest.raises(PreservationError):
            run.prepare()
    result = RunPreservation.recover(run.workspace, "run-1", acknowledge_unstarted=True)
    assert result["status"] == "unstarted_acknowledged"
    assert (source / "original").read_bytes() == b"before"
    assert RunPreservation.pending(run.workspace) == []
