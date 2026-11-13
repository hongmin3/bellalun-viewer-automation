"""REQ-FOLLOWUP-004: 임시 공유 폴더만 사용하는 차이 보존/복구 시험."""
import json
import os
from pathlib import Path
import shutil
from unittest import mock

import pytest

from core.run_preservation import PreservationError, RecoveryRequired, RunPreservation, snapshot


def shared_run(tmp_path, roots=None, adapter=None):
    source = tmp_path / "product"
    source.mkdir()
    (source / "original").write_bytes(b"before")
    (source / "unchanged").write_bytes(b"same")
    (source / "empty").mkdir()
    share = tmp_path / "share"
    share.mkdir()
    run = RunPreservation(tmp_path / "work", "shared-1", roots or {"image": source},
                          restore_after=True, db_adapter=adapter, storage_dir=share)
    return source, share, run


def test_shared_payload_local_journal_and_only_changed_file_is_staged(tmp_path):
    from core.run_preservation import preserved_path
    source, share, run = shared_run(tmp_path)
    before = snapshot(source)
    run.prepare()
    assert run.run_dir == run.workspace / "preservation" / "shared-1"
    assert run.data_dir == share / "shared-1"
    assert not (run.run_dir / "before").exists()
    stamp = (source / "original").stat()
    (source / "original").write_bytes(b"change")
    os.utime(source / "original", ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    (source / "added").write_bytes(b"evidence")
    real_copy = shutil.copy2
    restored = []
    def observed_copy(src, dst, **kwargs):
        if "before" in Path(src).parts:
            restored.append(Path(src).name)
        return real_copy(src, dst, **kwargs)
    with mock.patch("core.run_preservation.shutil.copy2", side_effect=observed_copy):
        result = run.finalize()
    assert result["status"] == "verified"
    assert snapshot(source) == before
    assert restored == ["original"]
    assert preserved_path(result, "image", "unchanged").read_bytes() == b"same"
    assert preserved_path(result, "image", "original").read_bytes() == b"change"
    assert preserved_path(result, "image", "added").read_bytes() == b"evidence"
    assert not (run.data_dir / "archive" / "image" / "unchanged").exists()
    assert not list(tmp_path.glob(".product.bellalun-*-holding*"))
    assert "files" not in result["roots"]["image"]
    assert Path(result["archive_manifest"]).parent == run.run_dir


def test_shared_deleted_added_missing_roots_and_type_conflicts(tmp_path):
    source, share, run = shared_run(tmp_path)
    (source / "folder").mkdir()
    (source / "folder" / "old").write_bytes(b"old")
    run.roots["absent"] = tmp_path / "absent"
    before = snapshot(source)
    run.prepare()
    (source / "original").unlink()
    (source / "original").mkdir()
    (source / "original" / "new").write_bytes(b"conflict")
    shutil.rmtree(source / "folder")
    (source / "folder").write_bytes(b"file conflict")
    (source / "empty").rmdir()
    (source / "newempty").mkdir()
    run.roots["absent"].mkdir()
    (run.roots["absent"] / "new").write_bytes(b"new root")
    result = run.finalize()
    assert result["status"] == "verified"
    assert snapshot(source) == before
    assert not run.roots["absent"].exists()
    assert (run.data_dir / "archive" / "image" / "original" / "new").read_bytes() == b"conflict"
    assert (run.data_dir / "archive" / "image" / "folder").read_bytes() == b"file conflict"
    assert any(p.read_bytes() == b"conflict" for p in tmp_path.glob(".product.bellalun-*/**/new"))


def test_shared_disconnect_is_local_pending_and_recover_pins_store_identity(tmp_path):
    source, share, run = shared_run(tmp_path)
    run.prepare()
    (source / "original").write_bytes(b"after")
    offline = share.with_name("offline")
    share.rename(offline)
    assert run.finalize()["status"] == "error"
    assert RunPreservation.pending(run.workspace) == ["shared-1"]
    with pytest.raises(RecoveryRequired):
        RunPreservation(run.workspace, "new", {"image": source}).prepare()
    share.mkdir()
    assert RunPreservation.recover(run.workspace, "shared-1")["status"] == "error"
    assert (source / "original").read_bytes() == b"after"
    share.rmdir()
    offline.rename(share)
    result = RunPreservation.recover(run.workspace, "shared-1")
    assert result["status"] == "verified"
    assert (source / "original").read_bytes() == b"before"
    assert RunPreservation.recover(run.workspace, "shared-1") == result


def test_shared_missing_or_changed_archive_prevents_local_replacement(tmp_path):
    source, share, run = shared_run(tmp_path)
    run.prepare()
    (source / "original").write_bytes(b"after")
    real_replace = os.replace
    def fail_product_replace(src, dst):
        if Path(dst) == source / "original":
            raise OSError("interrupted replacement")
        return real_replace(src, dst)
    with mock.patch("core.run_preservation.os.replace", side_effect=fail_product_replace):
        assert run.finalize()["status"] == "error"
    archive = run.data_dir / "archive" / "image" / "original"
    assert archive.read_bytes() == b"after"
    archive.write_bytes(b"wrong")
    assert RunPreservation.recover(run.workspace, "shared-1")["status"] in {"error", "mismatch"}
    assert (source / "original").read_bytes() == b"after"


@pytest.mark.parametrize("stop_phase", ["quarantine", "stage", "replace", "verified"])
def test_shared_resume_after_journal_phase_is_durable(tmp_path, stop_phase):
    source, share, run = shared_run(tmp_path)
    before = snapshot(source)
    run.prepare()
    (source / "original").write_bytes(b"after")
    (source / "added").write_bytes(b"added")
    real_save = run._save
    stopped = False
    def interrupt(state, **fields):
        nonlocal stopped
        real_save(state, **fields)
        operations = run.journal.get("delta_operations", [])
        if not stopped and any(op.get("phase") == stop_phase for op in operations):
            stopped = True
            raise KeyboardInterrupt("process stopped")
    with mock.patch.object(run, "_save", side_effect=interrupt):
        with pytest.raises(KeyboardInterrupt):
            run.finalize()
    assert stopped
    result = RunPreservation.recover(run.workspace, "shared-1")
    assert result["status"] == "verified"
    assert snapshot(source) == before
    assert (run.data_dir / "archive" / "image" / "original").read_bytes() == b"after"
    assert RunPreservation.recover(run.workspace, "shared-1") == result


def test_shared_db_before_and_after_are_kept_before_restore(tmp_path):
    class Adapter:
        value = b"before db"
        def backup(self, directory):
            (directory / "db.bak").write_bytes(self.value)
            return {"scope": "synthetic columns"}
        def verify_backup(self, directory, metadata):
            return (directory / "db.bak").is_file()
        def restore(self, directory, metadata):
            assert self.value == b"after db"
            self.value = (directory / "db.bak").read_bytes()
        def verify_restored(self, directory, metadata):
            return self.value == b"before db"
    adapter = Adapter()
    source, share, run = shared_run(tmp_path, adapter=adapter)
    run.prepare()
    adapter.value = b"after db"
    result = run.finalize()
    assert result["status"] == "verified"
    assert (run.data_dir / "database" / "db.bak").read_bytes() == b"before db"
    assert (run.data_dir / "archive" / "database" / "db.bak").read_bytes() == b"after db"


def test_shared_existing_payload_and_overlapping_store_are_refused(tmp_path):
    source, share, run = shared_run(tmp_path)
    run.data_dir.mkdir()
    (run.data_dir / "valuable").write_bytes(b"keep")
    with pytest.raises(PreservationError):
        run.prepare()
    assert (run.data_dir / "valuable").read_bytes() == b"keep"
    with pytest.raises(PreservationError):
        RunPreservation(tmp_path / "other", "overlap", {"image": source},
                        storage_dir=source / "backups").prepare()


def test_preserved_path_refuses_escape_and_supports_legacy_archive(tmp_path):
    from core.run_preservation import preserved_path
    folder = tmp_path / "archive"
    folder.mkdir()
    (folder / "evidence").write_bytes(b"saved")
    legacy = {"roots": {"image": {"archive": str(folder)}}}
    assert preserved_path(legacy, "image", "evidence").read_bytes() == b"saved"
    assert preserved_path(legacy, "image", "missing") is None
    for relative in ["../outside", "/outside", "C:/outside", "a/../../outside"]:
        with pytest.raises(PreservationError):
            preserved_path(legacy, "image", relative)


def test_shared_archive_copy_interrupted_mid_file_can_resume_without_overwrite(tmp_path):
    source, share, run = shared_run(tmp_path)
    run.prepare()
    (source / "original").write_bytes(b"after data")
    real_copy = shutil.copy2
    def interrupted_copy(src, dst, **kwargs):
        if Path(src) == source / "original":
            Path(dst).write_bytes(b"partial")
            raise KeyboardInterrupt("lost connection mid-copy")
        return real_copy(src, dst, **kwargs)
    with mock.patch("core.run_preservation.shutil.copy2", side_effect=interrupted_copy):
        with pytest.raises(KeyboardInterrupt):
            run.finalize()
    assert (source / "original").read_bytes() == b"after data"
    result = RunPreservation.recover(run.workspace, "shared-1")
    assert result["status"] == "verified"
    assert (run.data_dir / "archive" / "image" / "original").read_bytes() == b"after data"


@pytest.mark.parametrize("destination_kind", ["product", "quarantine"])
def test_shared_crash_after_atomic_move_recovers_without_moving_twice(tmp_path, destination_kind):
    source, share, run = shared_run(tmp_path)
    before = snapshot(source)
    run.prepare()
    (source / "original").write_bytes(b"after")
    (source / "added").write_bytes(b"new evidence")
    real_replace = os.replace
    stopped = False
    def interrupted_replace(src, dst):
        nonlocal stopped
        result = real_replace(src, dst)
        selected = (Path(dst) == source / "original" if destination_kind == "product"
                    else "quarantine" in str(dst))
        if selected and not stopped:
            stopped = True
            raise KeyboardInterrupt("lost power after move")
        return result
    with mock.patch("core.run_preservation.os.replace", side_effect=interrupted_replace):
        with pytest.raises(KeyboardInterrupt):
            run.finalize()
    assert stopped
    assert RunPreservation.recover(run.workspace, "shared-1")["status"] == "verified"
    assert snapshot(source) == before


def test_shared_long_descendant_paths_are_read_and_restored(tmp_path):
    source, share, run = shared_run(tmp_path)
    relative = "/".join(["longsegment" * 4] * 7) + "/image.dcm"
    path = source / relative
    # fixture는 구현의 경로 변환 helper에 의존하지 않는다.
    native = Path("\\\\?\\" + str(path)) if os.name == "nt" else path
    native.parent.mkdir(parents=True)
    native.write_bytes(b"before long")
    run.prepare()
    native.write_bytes(b"after long")
    assert run.finalize()["status"] == "verified"
    assert native.read_bytes() == b"before long"


def test_shared_no_restore_preserves_after_files_and_db_without_changing_product(tmp_path):
    source, share, run = shared_run(tmp_path)
    run.restore_after = False
    run.prepare()
    (source / "original").write_bytes(b"after")
    result = run.finalize()
    assert result["status"] == "preserved"
    assert (source / "original").read_bytes() == b"after"
    assert (run.data_dir / "archive" / "image" / "original").read_bytes() == b"after"
    assert RunPreservation.pending(run.workspace) == []


def test_shared_product_root_replaced_by_file_is_archived_and_quarantined(tmp_path):
    source, share, run = shared_run(tmp_path)
    before = snapshot(source)
    run.prepare()
    shutil.rmtree(source)
    source.write_bytes(b"unexpected file at product root")
    result = run.finalize()
    assert result["status"] == "verified"
    assert snapshot(source) == before
    assert (run.data_dir / "archive" / "image" / ".root-file").read_bytes() == b"unexpected file at product root"
    assert any(p.is_file() and p.read_bytes() == b"unexpected file at product root"
               for p in tmp_path.glob(".product.bellalun-*-quarantine/*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows 경로 별칭")
def test_extended_length_alias_cannot_hide_overlapping_product_and_backup(tmp_path):
    source = tmp_path / "product"
    source.mkdir()
    extended = Path("\\\\?\\" + str(source))
    with pytest.raises(PreservationError, match="겹칩니다"):
        RunPreservation(source / "work", "overlap", {"image": extended}).prepare()
    assert list(source.iterdir()) == []
