"""WU09 adapter with fake UI/services and temporary export files only."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_winupdate_usb import import_evidence


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    from tests import winupdate, workflow03
    from core import export_manager as em, flows, usb_media, usb_evidence, usb_paths
    events = []
    root = tmp_path / "usb"
    target = root / "BellalunWU09"
    root.mkdir()
    target.mkdir()
    context = SimpleNamespace(cfg={"data_dir": str(tmp_path / "data")}, db=object(),
                              evidence_root=str(tmp_path / "Evidence"))
    source = import_evidence()
    state = SimpleNamespace(export_mode="images", export_error=None, import_error=None, after_error=None,
                            cleanup_error=None, outcome={"rows": 1, "row_selected": True, "imported_clicked": True,
                            "closed": True, "error": None, "completion": deepcopy(source["completion"])})
    manager = SimpleNamespace(pid=77, dialog=lambda: None)

    class Ui:
        def click(self, control, settle):
            events.append("click")

        def by_id(self, key):
            assert key == 2191
            return [SimpleNamespace(visible=True)]
    ui = Ui()

    def prepare(drive, *args, **kwargs):
        assert drive == str(root)
        events.append("prepare-owned-folder")
        return str(target), ["synthetic-cleared.img"]

    def export(manager_ui, wait):
        events.append("export")
        if state.export_error:
            raise RuntimeError(state.export_error)
        if state.export_mode == "images":
            for index in range(3):
                (target / f"image{index}.img").write_bytes(b"synthetic-image")
        elif state.export_mode == "empty":
            (target / "empty.img").touch()
        else:
            (target / "readme.txt").write_text("synthetic", encoding="utf-8")
        manager.pid = None
        return {"files": [str(path) for path in target.iterdir()], "closed": True}

    def attempt(ui_arg, path, *, evidence_path=None, **kwargs):
        events.append("attempt-import")
        assert path == str(target)
        assert evidence_path and Path(evidence_path).is_relative_to(context.evidence_root)
        if state.import_error:
            raise RuntimeError(state.import_error)
        return deepcopy(state.outcome)

    snapshot_count = [0]

    def snapshot(db, data_dir, patient_id):
        assert db is context.db and data_dir == context.cfg["data_dir"] and patient_id == "SYNTHETIC_USB"
        snapshot_count[0] += 1
        after = snapshot_count[0] > 1
        events.append("snapshot-after" if after else "snapshot-before")
        if after and state.after_error:
            raise RuntimeError(state.after_error)
        return deepcopy(source["after" if after else "before"])

    def observe(ui_arg, db, data_dir, patient_id):
        events.append("observe-examined")
        return {"patient_id": patient_id, "searched": True, "study_uids": ["actual-ui-observed-uid"],
                "count": 2, "observations": [{"study_key": 99}]}

    def cancel(manager_ui, timeout):
        events.append("cancel-export")
        if state.cleanup_error:
            raise RuntimeError(state.cleanup_error)
        manager.pid = None
        return True

    monkeypatch.setattr(usb_media, "find_usb_drive", lambda: str(root))
    monkeypatch.setattr(usb_paths, "prepare_export_folder", prepare)
    monkeypatch.setattr(flows, "ensure_patient_screen", lambda *args, **kwargs: True)
    monkeypatch.setattr(flows, "examined_search", lambda *args, **kwargs: [object()])
    monkeypatch.setattr(workflow03, "_open_examined", lambda *args: None)
    monkeypatch.setattr(em, "attach", lambda: manager)
    monkeypatch.setattr(em, "ViewerUi", lambda *args: manager)
    monkeypatch.setattr(em, "set_path", lambda manager, path: path)
    monkeypatch.setattr(em, "is_checked", lambda manager, key: key == em.FORMAT_IMG)
    monkeypatch.setattr(em, "set_anonymous", lambda manager, enabled: events.append(("anonymous", enabled)) or {"final": enabled})
    monkeypatch.setattr(em, "set_portable_viewer", lambda manager, enabled: events.append(("portable", enabled)) or {"final": enabled})
    monkeypatch.setattr(em, "select_only_format", lambda manager, fmt: events.append(("only-format", fmt)) or
                        {"selected": {"final": True}, "turned_off": {em.FORMAT_DICOM: {"final": False}}})
    monkeypatch.setattr(em, "export", export)
    monkeypatch.setattr(em, "cancel", cancel)
    monkeypatch.setattr(usb_media, "attempt_import", attempt)
    monkeypatch.setattr(usb_media, "cancel_browse_dialog", lambda *args: events.append("cancel-browse"))
    monkeypatch.setattr(usb_media, "close_import_dialog", lambda *args: events.append("close-import") or True)
    monkeypatch.setattr(usb_evidence, "patient_snapshot", snapshot)
    monkeypatch.setattr(usb_evidence, "observe_examined", observe)
    return SimpleNamespace(run=lambda: winupdate.run_usb_export_import(context, ui, "SYNTHETIC_USB"),
                           state=state, events=events, target=target, source=source,
                           usb_media=usb_media, em=em, manager=manager)


def test_adapter_prepares_owned_folder_and_attaches_observed_raw_evidence(adapter):
    result = adapter.run()
    assert adapter.events[0] == "prepare-owned-folder"
    assert ("anonymous", False) in adapter.events and ("portable", False) in adapter.events
    assert ("only-format", adapter.em.FORMAT_IMG) in adapter.events
    assert len(result["export"]["files"]) == 3
    assert all(item["readable"] and item["size"] > 0 for item in result["export"]["inventory"])
    assert result["import"]["evidence"]["before"] == adapter.source["before"]
    assert result["import"]["evidence"]["after"] == adapter.source["after"]
    assert result["import"]["evidence"]["examined"]["study_uids"] == ["actual-ui-observed-uid"]
    position = adapter.events.index("snapshot-before")
    assert adapter.events[position:position + 4] == ["snapshot-before", "attempt-import", "snapshot-after", "observe-examined"]
    assert result["cleanup"]["ok"] is True


@pytest.mark.parametrize("mode", ["sidecar", "empty"])
def test_missing_or_empty_img_export_never_starts_import(adapter, mode):
    adapter.state.export_mode = mode
    result = adapter.run()
    assert result.get("error")
    assert "attempt-import" not in adapter.events


def test_unknown_export_format_state_prevents_export_and_import(adapter, monkeypatch):
    monkeypatch.setattr(adapter.em, "is_checked", lambda manager, key:
                        None if key == adapter.em.FORMAT_BMP else key == adapter.em.FORMAT_IMG)
    result = adapter.run()
    assert result.get("error")
    assert "export" not in adapter.events and "attempt-import" not in adapter.events


def test_snapshot_after_is_collected_even_if_import_throws(adapter):
    adapter.state.import_error = "synthetic-import-primary"
    result = adapter.run()
    assert "synthetic-import-primary" in result["error"]
    assert "snapshot-after" in adapter.events
    assert result["import"]["evidence"]["after"] == adapter.source["after"]
    assert "observe-examined" not in adapter.events


def test_import_error_is_preserved_when_after_collection_also_fails(adapter):
    adapter.state.outcome["error"] = "synthetic-import-primary"
    adapter.state.after_error = "synthetic-snapshot-secondary"
    result = adapter.run()
    assert result["import"]["error"] == "synthetic-import-primary"
    assert "synthetic-import-primary" in result["error"]
    assert "synthetic-snapshot-secondary" in str(result)


@pytest.mark.parametrize("completion,closed,error", [
    ({"observed": False}, True, None),
    ({"observed": True, "error": "negative completion"}, True, None),
    ({"observed": True}, False, "unknown-popup-primary"),
])
def test_unconfirmed_or_unclosed_import_never_searches_examined_or_clicks_unknown_popup(adapter, completion, closed, error):
    adapter.state.outcome.update(completion=completion, closed=closed, error=error)
    result = adapter.run()
    assert "observe-examined" not in adapter.events
    if not closed:
        assert "close-import" not in adapter.events
        assert result["cleanup"]["ok"] is False
        assert result["import"]["error"] == error


def test_export_failure_remains_primary_when_cleanup_also_fails(adapter):
    adapter.state.export_error = "synthetic-export-primary"
    adapter.state.cleanup_error = "synthetic-cleanup-secondary"
    result = adapter.run()
    assert "synthetic-export-primary" in result["error"]
    assert result["cleanup"]["ok"] is False
    assert "synthetic-cleanup-secondary" in str(result["cleanup"])


def test_no_usb_performs_no_ui_or_collection(adapter, monkeypatch):
    monkeypatch.setattr(adapter.usb_media, "find_usb_drive", lambda: None)
    assert adapter.run() == {"drive": None}
    assert not adapter.events
