"""마무리된 실행의 보존본을 최근 N회만 남기는 정리(REQ-FOLLOWUP-004).

Validates: REQ-FOLLOWUP-004
"""
import json
import os

from core.preservation_retention import (DEFAULT_KEEP_RUNS, PRUNING_DIR, keep_runs_from_options,
                                         prune_old_runs)
from core.run_preservation import RunPreservation


def _product(tmp_path):
    image = tmp_path / "product" / "Image"
    config = tmp_path / "product" / "Config"
    for path in (image, config):
        path.mkdir(parents=True, exist_ok=True)
        (path / "existing").write_bytes(b"original")
    return image, config


def _finished_local_run(tmp_path, run_id):
    """실제 보존·복원을 거쳐 격리 사본(.Image.bellalun-<실행>-<번호>)이 남은 마무리된 실행."""
    image, config = _product(tmp_path)
    run = RunPreservation(tmp_path / "work", run_id, {"Image": image, "Config": config}, restore_after=True)
    run.prepare()
    (image / f"generated-{run_id}.dcm").write_bytes(b"x" * 100)
    assert run.finalize()["status"] == "verified"
    return run


def _holdings(tmp_path, run_id):
    parent = tmp_path / "product"
    return sorted(p.name for p in parent.iterdir() if f".bellalun-{run_id}-" in p.name)


def test_keeps_latest_three_finished_runs_and_removes_older_runs_with_their_copies(tmp_path):
    ids = [f"20261120-0{n}0000-aaaa000{n}" for n in range(1, 6)]
    for run_id in ids:
        _finished_local_run(tmp_path, run_id)
    assert _holdings(tmp_path, ids[0]), "실제 복원은 격리 사본을 남긴다"
    # 다른 실행·다른 이름의 폴더는 지우지 않는다
    unrelated = [tmp_path / "product" / ".Image.bellalun-other-1", tmp_path / "product" / f".Image.bellalun-{ids[0]}-x"]
    for path in unrelated:
        path.mkdir()

    summary = prune_old_runs(tmp_path / "work", keep=3, current_run_id=ids[-1])

    assert summary["status"] == "completed", summary
    assert summary["kept"] == list(reversed(ids[2:]))
    assert sorted(summary["removed"]) == ids[:2]
    assert summary["bytes_removed"] > 0
    remaining = sorted(p.name for p in (tmp_path / "work" / "preservation").iterdir())
    assert remaining == ids[2:]
    for run_id in ids[:2]:
        expected = [f".Image.bellalun-{ids[0]}-x"] if run_id == ids[0] else []
        assert _holdings(tmp_path, run_id) == expected, run_id
    for run_id in ids[2:]:
        assert _holdings(tmp_path, run_id), f"남긴 실행의 격리 사본은 그대로: {run_id}"
    assert all(path.exists() for path in unrelated)
    assert (tmp_path / "product" / "Image" / "existing").read_bytes() == b"original", "제품 원본은 그대로"
    assert not (tmp_path / "work" / PRUNING_DIR).exists()
    assert RunPreservation.pending(tmp_path / "work") == []


def test_unfinished_runs_are_never_counted_or_removed(tmp_path):
    ids = [f"20261121-0{n}0000-bbbb000{n}" for n in range(1, 5)]
    for run_id in ids:
        _finished_local_run(tmp_path, run_id)
    preservation = tmp_path / "work" / "preservation"
    # 가장 오래된 실행: 마무리 대기, 두 번째: 정리 대기 표시
    journal = json.loads((preservation / ids[0] / "journal.json").read_text(encoding="utf-8"))
    journal["execution_finalization_pending"] = True
    (preservation / ids[0] / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
    (preservation / ids[1] / "image-cleanup-pending.json").write_text("{}", encoding="utf-8")
    broken = preservation / "20261119-000000-broken01"
    broken.mkdir()   # journal 없음: 복구 대상이므로 건드리지 않는다

    summary = prune_old_runs(tmp_path / "work", keep=1)

    assert summary["kept"] == [ids[3]]
    assert summary["removed"] == [ids[2]]
    assert sorted(p.name for p in preservation.iterdir()) == sorted([ids[0], ids[1], ids[3], broken.name])
    assert _holdings(tmp_path, ids[0]) and _holdings(tmp_path, ids[1])


def test_shared_store_copy_of_a_removed_run_is_removed_too(tmp_path):
    image, config = _product(tmp_path)
    share = tmp_path / "share"
    share.mkdir()
    ids = ["20261122-010000-cccc0001", "20261122-020000-cccc0002"]
    for run_id in ids:
        run = RunPreservation(tmp_path / "work", run_id, {"Image": image, "Config": config},
                              restore_after=True, storage_dir=share)
        run.prepare()
        (image / f"generated-{run_id}.dcm").write_bytes(b"y" * 50)
        assert run.finalize()["status"] == "verified"
        run.finish_execution_finalization()
    assert (share / ids[0]).exists() and (share / ids[1]).exists()

    summary = prune_old_runs(tmp_path / "work", keep=1, current_run_id=ids[1])

    assert summary["removed"] == [ids[0]], summary
    assert not (share / ids[0]).exists()
    assert (share / ids[1]).exists()
    assert (share / ".bellalun-preservation-store.json").exists(), "저장소 표시는 남긴다"
    assert _holdings(tmp_path, ids[0]) == []


def test_interrupted_purge_resumes_and_does_not_block_the_next_run(tmp_path):
    ids = [f"20261123-0{n}0000-dddd000{n}" for n in range(1, 4)]
    for run_id in ids:
        _finished_local_run(tmp_path, run_id)
    work = tmp_path / "work"
    # 지난 정리가 실행 폴더를 옮긴 뒤 멈춘 상태
    staging = work / PRUNING_DIR
    staging.mkdir()
    os.replace(work / "preservation" / ids[0], staging / ids[0])
    assert RunPreservation.pending(work) == [], "옮겨 둔 폴더는 다음 실행을 막지 않는다"

    summary = prune_old_runs(work, keep=2)

    assert ids[0] in summary["removed"]
    assert not staging.exists()
    assert _holdings(tmp_path, ids[0]) == []
    assert sorted(p.name for p in (work / "preservation").iterdir()) == ids[1:]


def test_keep_option_defaults_and_zero_disables(tmp_path):
    assert keep_runs_from_options({}) == DEFAULT_KEEP_RUNS == 3
    assert keep_runs_from_options(None) == 3
    assert keep_runs_from_options({"keep_runs": 5}) == 5
    assert keep_runs_from_options({"keep_runs": 0}) == 0
    for bad in (-1, "3", True, 2.5):
        assert keep_runs_from_options({"keep_runs": bad}) == 3
    _finished_local_run(tmp_path, "20261124-010000-eeee0001")
    _finished_local_run(tmp_path, "20261124-020000-eeee0002")
    summary = prune_old_runs(tmp_path / "work", keep=0)
    assert summary["status"] == "skipped" and summary["reason"] == "disabled_by_config"
    assert len(list((tmp_path / "work" / "preservation").iterdir())) == 2


def test_run_end_calls_retention_with_configured_keep_and_records_result(tmp_path, monkeypatch):
    """실행 끝 흐름은 판정과 무관하게 정리를 부르고 restoration.json에 결과를 남긴다."""
    from types import SimpleNamespace
    import run
    from core import preservation_retention
    calls = []

    def fake_prune(workspace, keep, current_run_id=None):
        calls.append((workspace, keep, current_run_id))
        return {"status": "completed", "keep": keep, "removed": ["old"]}

    monkeypatch.setattr(preservation_retention, "prune_old_runs", fake_prune)
    run_dir = tmp_path / "work" / "preservation" / "20261125-010000-ffff0001"
    run_dir.mkdir(parents=True)
    session = SimpleNamespace(workspace=tmp_path / "work", run_id=run_dir.name, run_dir=run_dir,
                              cleanup_generated_images=lambda **k: {"status": "skipped", "reason": "fixture"})
    ctx = SimpleNamespace(root=str(tmp_path), reports_root=str(tmp_path / "Reports"),
                          cfg={"preservation": {"keep_runs": 5}}, run_id=run_dir.name,
                          restoration={"status": "verified", "services": {}})
    run._finish_generated_image_cleanup(ctx, SimpleNamespace(cmd="run-regression"), session, 0, 0, [], True)
    assert calls == [(tmp_path / "work", 5, run_dir.name)]
    assert ctx.restoration["retention"]["removed"] == ["old"]
    saved = json.loads((run_dir / "restoration.json").read_text(encoding="utf-8"))
    assert saved["retention"]["keep"] == 5
