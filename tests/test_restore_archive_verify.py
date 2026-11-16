# -*- coding: utf-8 -*-
"""파일 차이 복원에서 시험 후 보관본 전체 검증을 격리마다 반복하지 않는다.

Validates: REQ-SPEEDUP-006
"""
from unittest import mock

import pytest

from core import preservation_storage
from core.run_preservation import RunPreservation, snapshot


def shared_run(tmp_path):
    source = tmp_path / "product"
    source.mkdir()
    (source / "original").write_bytes(b"before")
    share = tmp_path / "share"
    share.mkdir()
    run = RunPreservation(tmp_path / "work", "verify-1", {"image": source},
                          restore_after=True, storage_dir=share)
    return source, run


def generated(source, count=4):
    for index in range(count):
        folder = source / f"study{index}"
        folder.mkdir()
        (folder / "image.dcm").write_bytes(b"generated %d" % index)


def counting_verify(calls):
    real = preservation_storage._verify_archive

    def verify(run):
        calls.append(run.journal.get("delta_operations") is not None)
        return real(run)
    return verify


def test_archive_is_verified_once_before_first_quarantine(tmp_path):
    source, run = shared_run(tmp_path)
    before = snapshot(source)
    run.prepare()
    generated(source)
    calls = []
    with mock.patch.object(preservation_storage, "_verify_archive", side_effect=counting_verify(calls)):
        result = run.finalize()
    assert result["status"] == "verified"
    assert snapshot(source) == before
    quarantines = [op for op in run.journal["delta_operations"] if op["kind"] == "quarantine"]
    assert len(quarantines) == 4
    # 복원 계획 뒤 전체 해시 검증은 끝의 archive_verify 1회다. 첫 격리 직전 확인은 같은 호출의
    # 보관 직후 해시 검증 뒤 목록·크기·수정 시각이 그대로라 해시를 다시 하지 않는다(REQ-SPEEDUP-007).
    # 격리마다 검증하던 1.0.24 이전 구현은 5회, 1.0.26은 2회였다.
    assert calls.count(True) == 1


def test_damaged_archive_stops_before_any_quarantine(tmp_path):
    source, run = shared_run(tmp_path)
    run.prepare()
    generated(source, 3)
    real_archive = preservation_storage._archive

    def archive_then_damage(r):
        out = real_archive(r)
        target = r.data_dir / "archive" / "image" / "study0" / "image.dcm"
        target.write_bytes(b"tampered")
        return out
    with mock.patch.object(preservation_storage, "_archive", side_effect=archive_then_damage):
        result = run.finalize()
    assert result["status"] == "error"
    assert all((source / f"study{i}" / "image.dcm").exists() for i in range(3))
    assert not any(op["phase"] == "verified" for op in run.journal["delta_operations"])
    assert not any(source.parent.glob(".product.bellalun-*-quarantine/*"))


def test_resume_verifies_again_once(tmp_path):
    source, run = shared_run(tmp_path)
    before = snapshot(source)
    run.prepare()
    generated(source, 3)
    real_save = run._save
    stopped = False

    def interrupt(state, **fields):
        nonlocal stopped
        real_save(state, **fields)
        operations = run.journal.get("delta_operations", [])
        if not stopped and sum(op.get("phase") == "verified" for op in operations) == 1:
            stopped = True
            raise KeyboardInterrupt("process stopped")
    with mock.patch.object(run, "_save", side_effect=interrupt):
        with pytest.raises(KeyboardInterrupt):
            run.finalize()
    calls = []
    with mock.patch.object(preservation_storage, "_verify_archive", side_effect=counting_verify(calls)):
        result = RunPreservation.recover(run.workspace, "verify-1")
    assert result["status"] == "verified"
    assert snapshot(source) == before
    # 재개 호출에는 앞 호출의 기억이 없어 보관 단계 재확인에서 전체 해시 검증 1회를 하고,
    # 첫 격리 직전 확인은 그 뒤 그대로인 보관본이라 해시를 다시 하지 않는다(REQ-SPEEDUP-007).
    # 끝의 archive_verify 1회를 더해 2회다. 격리마다 검증하던 이전 구현은 4회, 1.0.26은 3회였다.
    assert calls.count(True) == 2
