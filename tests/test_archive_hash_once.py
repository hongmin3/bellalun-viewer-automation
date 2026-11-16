# -*- coding: utf-8 -*-
"""보관·복원 마무리에서 같은 파일을 반복 해시하지 않는다.

Validates: REQ-SPEEDUP-007
"""
import os
from pathlib import Path
from unittest import mock

import pytest

from core import preservation_storage, run_preservation
from core.run_preservation import PreservationError, RunPreservation, snapshot


def shared_run(tmp_path):
    source = tmp_path / "product"
    source.mkdir()
    (source / "original").write_bytes(b"before")
    share = tmp_path / "share"
    share.mkdir()
    run = RunPreservation(tmp_path / "work", "hash-1", {"image": source},
                          restore_after=True, storage_dir=share)
    return source, run


def generated(source, count=3):
    for index in range(count):
        folder = source / f"study{index}"
        folder.mkdir()
        (folder / "image.dcm").write_bytes(b"generated %d" % index)


def counting_hash(counter):
    real = run_preservation._hash

    def hashed(path):
        counter[Path(path)] = counter.get(Path(path), 0) + 1
        return real(path)
    return hashed


def test_finalize_reads_each_generated_file_fewer_times(tmp_path):
    source, run = shared_run(tmp_path)
    before = snapshot(source)
    run.prepare()
    generated(source)
    counter = {}
    hashed = counting_hash(counter)
    with mock.patch.object(run_preservation, "_hash", side_effect=hashed), \
            mock.patch.object(preservation_storage, "_hash", side_effect=hashed):
        result = run.finalize()
    assert result["status"] == "verified"
    assert snapshot(source) == before
    archived = run.data_dir / "archive" / "image" / "study0" / "image.dcm"
    product = source / "study0" / "image.dcm"
    # 보관 사본(최종 이름): 보관 직후 전체 검증 1회 + 끝의 archive_verify 1회.
    # 복사 직후 대조는 임시 이름에서 한다. 1.0.26 코드로 같은 시험을 돌리면 6회였다.
    assert counter[archived] == 2
    # 생성 원본: 시험 후 목록 1회 + 복사 뒤 1회 + 보관 끝 대조 1회 + 격리 직전 1회.
    # 1.0.26 코드는 복사 전 대조·계획 재대조·계획 목록 작성까지 7회였다.
    assert counter[product] == 4


def test_plan_entry_matches_hashed_entry(tmp_path):
    source, run = shared_run(tmp_path)
    run.prepare()
    generated(source, 2)
    (source / "study0" / "sub").mkdir()
    (source / "study0" / "sub" / "x.dcm").write_bytes(b"x")
    (source / "loose.dcm").write_bytes(b"loose")
    current = snapshot(source)
    for relative in ["study0", "study1", "loose.dcm", "study0/sub"]:
        derived = preservation_storage._entry_from_snapshot(current, relative)
        assert derived == preservation_storage._entry(source / relative)
    assert preservation_storage._entry_from_snapshot(current, "") is None
    assert preservation_storage._entry_from_snapshot(current, "missing") is None


def test_archive_changed_after_verify_is_hashed_again_and_stops(tmp_path):
    source, run = shared_run(tmp_path)
    run.prepare()
    generated(source, 2)
    real_archive = preservation_storage._archive

    def archive_then_damage(r):
        out = real_archive(r)
        target = r.data_dir / "archive" / "image" / "study1" / "image.dcm"
        target.write_bytes(b"tampered!")
        return out
    with mock.patch.object(preservation_storage, "_archive", side_effect=archive_then_damage):
        result = run.finalize()
    assert result["status"] == "error"
    assert (source / "study1" / "image.dcm").exists()
    assert not any(op["phase"] == "verified" for op in run.journal["delta_operations"])


def test_same_size_rewrite_with_new_mtime_is_detected(tmp_path):
    source, run = shared_run(tmp_path)
    run.prepare()
    generated(source, 1)
    real_archive = preservation_storage._archive

    def archive_then_rewrite(r):
        out = real_archive(r)
        target = r.data_dir / "archive" / "image" / "study0" / "image.dcm"
        stamp = target.stat()
        target.write_bytes(b"generated X")  # 같은 크기, 다른 내용
        os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000))
        return out
    with mock.patch.object(preservation_storage, "_archive", side_effect=archive_then_rewrite):
        result = run.finalize()
    assert result["status"] == "error"
    assert (source / "study0" / "image.dcm").exists()


def test_source_changed_after_archive_is_hashed_again_in_plan(tmp_path):
    source, run = shared_run(tmp_path)
    run.prepare()
    generated(source, 1)
    real_archive = preservation_storage._archive

    def archive_then_change(r):
        out = real_archive(r)
        (source / "study0" / "late.dcm").write_bytes(b"late")
        return out
    with mock.patch.object(preservation_storage, "_archive", side_effect=archive_then_change):
        result = run.finalize()
    assert result["status"] == "error"
    assert (source / "study0" / "late.dcm").exists()


def test_copy_of_changed_source_is_rejected_without_destination(tmp_path):
    source = tmp_path / "a.bin"
    source.write_bytes(b"changed")
    expected = {"size": 6, "sha256": "0" * 64}
    destination = tmp_path / "out" / "a.bin"
    with pytest.raises(PreservationError):
        preservation_storage._file_copy(source, destination, expected,
                                        temporary_dir=tmp_path / "copying")
    assert not destination.exists()


def test_resume_has_no_memory_and_hashes_again(tmp_path):
    source, run = shared_run(tmp_path)
    run.prepare()
    generated(source, 2)
    run.finalize()
    fresh = RunPreservation.load(run.workspace, "hash-1")
    assert getattr(fresh, "_verified_archive", None) is None
    assert getattr(fresh, "_verified_roots", None) is None
