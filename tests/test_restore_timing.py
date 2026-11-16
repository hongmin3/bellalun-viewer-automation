# -*- coding: utf-8 -*-
"""복원 단계 안의 시간 기록(`phases`, `timings`).

Validates: REQ-SPEEDUP-003
"""
import json
from types import SimpleNamespace

import pytest

from core import phase_timer
from core.run_preservation import RunPreservation

SHARED_PHASES = ["verify_backups", "archive", "restore_files", "db_precheck",
                 "db_restore", "db_restore:DATA", "db_restore:ACCOUNT", "db_verify",
                 "final_check", "archive_verify"]


class FakeClock:
    """부를 때마다 2초씩 가는 시계."""
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 2.0
        return self.now


class Adapter:
    value = b"before db"

    def backup(self, directory):
        (directory / "db.bak").write_bytes(self.value)
        return {"scope": "synthetic"}

    def verify_backup(self, directory, metadata):
        return (directory / "db.bak").is_file()

    def restore(self, directory, metadata):
        self.restore_phases = [{"phase": "db_restore:DATA", "seconds": 3.0},
                               {"phase": "db_restore:ACCOUNT", "seconds": 1.5}]
        self.value = (directory / "db.bak").read_bytes()

    def verify_restored(self, directory, metadata):
        return self.value == b"before db"


def shared_run(tmp_path, adapter):
    source = tmp_path / "product"
    source.mkdir()
    (source / "original").write_bytes(b"before")
    share = tmp_path / "share"
    share.mkdir()
    return source, RunPreservation(tmp_path / "work", "timing-1", {"image": source},
                                   restore_after=True, db_adapter=adapter, storage_dir=share)


def test_phase_timer_rounds_and_records_failed_phase(monkeypatch):
    monkeypatch.setattr(phase_timer, "_now", FakeClock())
    timer = phase_timer.PhaseTimer()
    with timer.phase("ok"):
        pass
    with pytest.raises(RuntimeError):
        with timer.phase("broken"):
            raise RuntimeError("x")
    assert timer.rows == [{"phase": "ok", "seconds": 2.0}, {"phase": "broken", "seconds": 2.0}]


def test_shared_restore_records_phases_in_order(tmp_path, monkeypatch):
    adapter = Adapter()
    source, run = shared_run(tmp_path, adapter)
    run.prepare()
    (source / "original").write_bytes(b"after")
    adapter.value = b"after db"
    monkeypatch.setattr(phase_timer, "_now", FakeClock())
    result = run.finalize()
    assert result["status"] == "verified"
    assert [row["phase"] for row in result["phases"]] == SHARED_PHASES
    by_name = {row["phase"]: row["seconds"] for row in result["phases"]}
    assert by_name["db_restore:DATA"] == 3.0
    assert all(isinstance(row["seconds"], float) for row in result["phases"])
    journal = json.loads((run.run_dir / "journal.json").read_text(encoding="utf-8"))
    assert journal["result"]["phases"] == result["phases"]


def test_failed_restore_keeps_phases_until_failure(tmp_path, monkeypatch):
    adapter = Adapter()
    source, run = shared_run(tmp_path, adapter)
    run.prepare()
    adapter.value = b"after db"

    def broken(directory, metadata):
        adapter.restore_phases = [{"phase": "db_restore:DATA", "seconds": 4.0}]
        raise OSError("restore failed")
    adapter.restore = broken
    monkeypatch.setattr(phase_timer, "_now", FakeClock())
    result = run.finalize()
    assert result["status"] == "error"
    assert [row["phase"] for row in result["phases"]] == [
        "verify_backups", "archive", "restore_files", "db_precheck", "db_restore",
        "db_restore:DATA"]


def test_execution_session_records_boundary_timings(tmp_path, monkeypatch):
    from core import execution_session as module
    monkeypatch.delenv("BELLALUN_QA_RUN", raising=False)
    data = tmp_path / "data"
    (data / "Image").mkdir(parents=True)
    (data / "Image" / "qc.img").write_bytes(b"original")
    ctx = SimpleNamespace(root=str(tmp_path / "work"), cfg={"data_dir": str(data)},
                          preservation_choice=True, db=object())

    class Database:
        def __init__(self, ctx): pass
        def estimate_bytes(self): return 0
        def backup(self, dest): return {"scope": "synthetic"}
        def verify_backup(self, *args): return True
        def restore(self, *args): pass
        def verify_restored(self, *args): return True
    monkeypatch.setattr(module, "DatabasePreservation", Database)
    monkeypatch.setattr(module, "plan_resources", lambda *a, **k: {"blocked": False})
    monkeypatch.setattr(module, "stop_product", lambda ctx: None)
    monkeypatch.setattr(module, "start_services", lambda: {"BellalunService": "RUNNING"})
    monkeypatch.setattr(module, "roots_from_config", lambda cfg, **k: {"images": data / "Image"})
    with module.execution_session(ctx, "run-regression"):
        monkeypatch.setattr(phase_timer, "_now", FakeClock())
    timings = ctx.restoration["timings"]
    assert list(timings) == ["stop_product", "finalize", "start_services"]
    assert all(value == 2.0 for value in timings.values())
    saved = json.loads(next((tmp_path / "work").glob("preservation/*/restoration.json"))
                       .read_text(encoding="utf-8"))
    assert saved["timings"] == timings


def test_database_restore_records_each_database(tmp_path, monkeypatch):
    from core import dbreset, execution_session as module
    monkeypatch.setattr(dbreset, "DATABASES", ["DATA", "ACCOUNT"])
    monkeypatch.setattr(dbreset, "staging_dir", lambda ctx: str(tmp_path))
    monkeypatch.setattr(dbreset, "_move_clauses", lambda ctx, name, path: "")
    monkeypatch.setattr(dbreset, "_restore_sql", lambda name, path, clauses: "RESTORE")
    source = tmp_path / "copies"
    source.mkdir()
    files = {}
    for name in ("DATA", "ACCOUNT"):
        (source / f"{name}.bak").write_bytes(name.encode())
        files[name] = module._sha(source / f"{name}.bak")
    queries = []
    ctx = SimpleNamespace(db=SimpleNamespace(query=lambda db, sql: queries.append(sql)))
    monkeypatch.setattr(phase_timer, "_now", FakeClock())
    adapter = module.DatabasePreservation(ctx)
    adapter.restore(source, {"files": files})
    assert [row["phase"] for row in adapter.restore_phases] == ["db_restore:DATA",
                                                                "db_restore:ACCOUNT"]
    assert queries.count("RESTORE") == 2
