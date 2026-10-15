"""USB 관찰 수집 경계. 합성 로그/파일/DB만 사용하며 제품 UI는 호출하지 않는다."""
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


NOW = datetime(2026, 10, 15, 12, 0, 0)


def evidence_module():
    from core import usb_evidence
    return usb_evidence


def event(key, instant=NOW, source="CFrameExamined::OnNotify"):
    stamp = instant.strftime("%Y/%m/%d %H:%M:%S.%f")[:-3]
    return f"[{stamp}] [User Action] [UI] [Study list item Click. (Study Key: {key})] [{source}]\r\n"


def log_file(tmp_path):
    path = tmp_path / "Log" / "Viewer" / "2026_10_15.log"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe" + event(999, NOW - timedelta(seconds=1)).encode("utf-16le"))
    return path


def append(path, value):
    with path.open("ab") as stream:
        stream.write(value.encode("utf-16le"))


def test_selected_key_comes_only_from_fresh_exact_click_log(tmp_path):
    module = evidence_module()
    path = log_file(tmp_path)
    cursor = module.log_cursor(tmp_path, now=NOW)
    append(path, event(42))
    assert module.selected_study_key(cursor, timeout=0) == 42


@pytest.mark.parametrize("fresh", ["", event(41) + event(42), event(42) + event(42), event(42, NOW - timedelta(seconds=1)),
                                   event(42, source="UnrelatedSource")])
def test_missing_ambiguous_old_or_wrong_source_clicks_never_identify_a_card(tmp_path, fresh):
    module = evidence_module()
    path = log_file(tmp_path)
    cursor = module.log_cursor(tmp_path, now=NOW)
    append(path, fresh)
    with pytest.raises(module.ObservationError):
        module.selected_study_key(cursor, timeout=0)


def test_rotated_or_truncated_log_never_reuses_a_key(tmp_path):
    module = evidence_module()
    path = log_file(tmp_path)
    cursor = module.log_cursor(tmp_path, now=NOW)
    path.rename(path.with_suffix(".old"))
    path.write_bytes(b"\xff\xfe" + event(42).encode("utf-16le"))
    with pytest.raises(module.ObservationError):
        module.selected_study_key(cursor, timeout=0)


def test_inplace_rewritten_log_anchor_is_rejected(tmp_path):
    module = evidence_module()
    path = log_file(tmp_path)
    cursor = module.log_cursor(tmp_path, now=NOW)
    path.write_bytes(b"\xff\xfe" + event(998, NOW - timedelta(seconds=1)).encode("utf-16le") + event(42).encode("utf-16le"))
    with pytest.raises(module.ObservationError):
        module.selected_study_key(cursor, timeout=0)


def test_log_tail_limit_rejects_overflow_instead_of_using_partial_evidence(tmp_path):
    module = evidence_module()
    path = log_file(tmp_path)
    cursor = module.log_cursor(tmp_path, now=NOW)
    append(path, "unrelated\n" * 500 + event(42))
    with pytest.raises(module.ObservationError):
        module.selected_study_key(cursor, timeout=0, max_bytes=512)


def test_selected_key_waits_for_real_log_flush(tmp_path):
    import threading
    import time
    module = evidence_module()
    path = log_file(tmp_path)
    cursor = module.log_cursor(tmp_path, now=NOW)

    def flush_later():
        time.sleep(0.03)
        append(path, event(42))
    writer = threading.Thread(target=flush_later)
    writer.start()
    try:
        assert module.selected_study_key(cursor, timeout=0.5, poll=0.01) == 42
    finally:
        writer.join(timeout=1)


def test_truncated_log_never_reuses_a_key(tmp_path):
    module = evidence_module()
    path = log_file(tmp_path)
    cursor = module.log_cursor(tmp_path, now=NOW)
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(module.ObservationError):
        module.selected_study_key(cursor, timeout=0)


class SyntheticDb:
    def __init__(self, data_dir):
        self.data_dir = data_dir

    def query(self, database, sql, params):
        assert database == "DATA"
        assert params == {"pid": "SYNTHETIC"}
        assert "p.PatientID=@pid" in sql
        if "FROM INSTANCE" in sql:
            assert "LEFT JOIN SERIES" in sql
            assert "se.[Key]=i.SeriesKey" in sql
            return [{"key": 11, "study_key": 42, "series_uid": "synthetic.series",
                     "image_uid": "synthetic.image", "study_uid": "synthetic.study", "patient_id": "SYNTHETIC"},
                    {"key": 12, "study_key": 42, "series_uid": "synthetic.series2",
                     "image_uid": "synthetic.image2", "study_uid": "synthetic.study", "patient_id": "SYNTHETIC"}]
        return [{"key": 42, "study_uid": "synthetic.study", "patient_id": "SYNTHETIC"}]


def test_patient_snapshot_resolves_real_instance_files_and_missing_files(tmp_path):
    module = evidence_module()
    folder = tmp_path / "Image" / "Study42_20261015_120000"
    folder.mkdir(parents=True)
    image = folder / "Image11.img"
    image.write_bytes(b"synthetic-image")
    snapshot = module.patient_snapshot(SyntheticDb(tmp_path), tmp_path, "SYNTHETIC")
    assert snapshot["patient_id"] == "SYNTHETIC"
    assert snapshot["studies"] == [{"key": 42, "study_uid": "synthetic.study", "patient_id": "SYNTHETIC"}]
    first, second = snapshot["instances"]
    assert first["path"] == str(image)
    assert first["exists"] is True and first["readable"] is True and first["size"] == 15
    assert first["series_uid"] == "synthetic.series" and first["image_uid"] == "synthetic.image"
    assert second["exists"] is False and second["readable"] is False and second["size"] == 0


def test_empty_image_is_not_readable_evidence(tmp_path):
    module = evidence_module()
    folder = tmp_path / "Image" / "Study42_20261015_120000"
    folder.mkdir(parents=True)
    (folder / "Image11.img").touch()
    item = module.patient_snapshot(SyntheticDb(tmp_path), tmp_path, "SYNTHETIC")["instances"][0]
    assert item["exists"] is True
    assert item["readable"] is False
    assert item["size"] == 0


def test_snapshot_reads_independent_img_xml_uids_without_copying_db(tmp_path, monkeypatch):
    module = evidence_module()
    folder = tmp_path / "Image" / "Study42_20261015_120000"
    folder.mkdir(parents=True)
    image = folder / "Image11.img"
    image.write_bytes(b"synthetic-image")

    def parsed_sections(path):
        assert Path(path) == image
        return {"study": {"InstanceUID": "xml.independent.study"},
                "series": {"InstanceUID": "xml.independent.series"},
                "instance": {"InstanceUID": "xml.independent.image"}}
    monkeypatch.setattr(module.imginfo, "sections", parsed_sections)
    item = module.patient_snapshot(SyntheticDb(tmp_path), tmp_path, "SYNTHETIC")["instances"][0]
    assert item["file_identity"] == {"study_uid": "xml.independent.study", "series_uid": "xml.independent.series",
                                     "image_uid": "xml.independent.image"}
    assert item["study_uid"] == "synthetic.study"
    assert not item.get("file_identity_error")


@pytest.mark.parametrize("failure", ["parse", "missing"])
def test_snapshot_keeps_xml_parse_or_missing_uid_errors_as_nonproof(tmp_path, monkeypatch, failure):
    module = evidence_module()
    folder = tmp_path / "Image" / "Study42_20261015_120000"
    folder.mkdir(parents=True)
    (folder / "Image11.img").write_bytes(b"synthetic-image")

    def parsed_sections(path):
        if failure == "parse":
            raise module.imginfo.ImgInfoError("synthetic invalid IMG XML")
        return {"study": {"InstanceUID": "actual.partial.uid"}}
    monkeypatch.setattr(module.imginfo, "sections", parsed_sections)
    item = module.patient_snapshot(SyntheticDb(tmp_path), tmp_path, "SYNTHETIC")["instances"][0]
    assert item["file_identity_error"]
    assert item["file_identity"].get("image_uid") is None


def test_examined_observation_uses_each_fresh_ui_key_to_lookup_actual_uid(tmp_path, monkeypatch):
    import sys
    module = evidence_module()
    path = log_file(tmp_path)
    actual_cursor = module.log_cursor
    monkeypatch.setattr(module, "log_cursor", lambda data_dir: actual_cursor(data_dir, now=NOW))
    cards = [SimpleNamespace(rect=(0, 0, 20, 20), key=42), SimpleNamespace(rect=(0, 30, 20, 50), key=43)]

    def search(ui, patient_id):
        assert patient_id == "SYNTHETIC"
        return cards

    class FakeUi:
        def click(self, card, settle):
            append(path, event(card.key))

    class FakeDb:
        def one(self, database, sql, params):
            assert database == "DATA" and "s.[Key]=@key" in sql and "p.PatientID=@pid" in sql
            assert params["pid"] == "SYNTHETIC"
            return {"key": params["key"], "study_uid": "db.observed." + str(params["key"]), "patient_id": "SYNTHETIC"}

    monkeypatch.setitem(sys.modules, "core.flows", SimpleNamespace(examined_search=search))
    result = module.observe_examined(FakeUi(), FakeDb(), tmp_path, "SYNTHETIC")
    assert result["patient_id"] == "SYNTHETIC" and result["searched"] is True
    assert result["study_uids"] == ["db.observed.42", "db.observed.43"]
    assert result["count"] == 2
    assert [item["study_key"] for item in result["observations"]] == [42, 43]
    assert result["observations"][0]["log_offset"] < result["observations"][1]["log_offset"]


def test_examined_observation_rejects_lookup_for_unrelated_patient(tmp_path, monkeypatch):
    import sys
    module = evidence_module()
    path = log_file(tmp_path)
    actual_cursor = module.log_cursor
    monkeypatch.setattr(module, "log_cursor", lambda data_dir: actual_cursor(data_dir, now=NOW))
    card = SimpleNamespace(rect=(0, 0, 20, 20))
    monkeypatch.setitem(sys.modules, "core.flows", SimpleNamespace(examined_search=lambda ui, pid: [card]))

    class FakeUi:
        def click(self, selected, settle):
            append(path, event(42))

    db = SimpleNamespace(one=lambda *args: {"key": 42, "study_uid": "unrelated", "patient_id": "OTHER"})
    with pytest.raises(module.ObservationError):
        module.observe_examined(FakeUi(), db, tmp_path, "SYNTHETIC")
