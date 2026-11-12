"""REQ-TCUP-003: run648의 원본/Import 복사본 혼동을 UI 없이 재현한다."""
from datetime import datetime
import sqlite3
from types import SimpleNamespace

import pytest

from tests import workflow15 as wf


class StudyDb:
    def __init__(self, kinds):
        self.kinds = kinds

    def studies(self):
        return [dict(Key=key, StudyInstanceUID=f"1.2.{key}",
                     PatientID=wf.PATIENT_ID, PatientBirthDate="19800101")
                for key in sorted(self.kinds, reverse=True)]

    def one(self, database, sql, params=None):
        if "FROM STUDY" in sql:
            return self.studies()[0] if self.kinds else None
        if "FROM DICOM_STORAGE" in sql:
            return dict(Key=17, Name="STORAGE", SendDoseSR=1, SCPUseType=0)
        raise AssertionError(sql)

    def query(self, database, sql, params=None):
        if "FROM STUDY" in sql:
            return self.studies()
        if "FROM INSTANCE" in sql:
            return [dict(Key=key * 10 + index, InstanceType=kind,
                         ImageInstanceUID=f"1.2.{key}.{index}")
                    for key, kinds in self.kinds.items()
                    if key == params["k"]
                    for index, kind in enumerate(kinds)]
        if "FROM OVERLAY_ITEM" in sql:
            return [dict(FieldID=115, Position=1), dict(FieldID=118, Position=1)]
        raise AssertionError(sql)


def test_study_uses_acquired_2d_raw_recon_fixture_instead_of_new_import_copy():
    # run648: 원본48의 종류0/1/2/3, 최신52에는 전송된0/2/2만 있었다.
    ctx = SimpleNamespace(db=StudyDb({48: [0, 1, 2, 3], 52: [0, 2, 2]}))
    source = wf._study(ctx)
    assert source["Key"] == 48
    assert [item["InstanceType"] for item in source["sendable"]] == [0, 2]


@pytest.mark.parametrize("kinds", [{52: [0, 2, 2]},
                                  {48: [0, 1, 2], 51: [0, 1, 2, 3]}])
def test_missing_or_ambiguous_original_is_a_precondition_error(kinds):
    with pytest.raises(RuntimeError, match="전제"):
        wf._study(SimpleNamespace(db=StudyDb(kinds)))


def test_syn_is_not_an_additional_source_requirement():
    source = wf._study(SimpleNamespace(db=StudyDb({48: [0, 1, 2]})))
    assert source["Key"] == 48


def run_to_preview(monkeypatch, tmp_path, cards):
    log = tmp_path / "Log" / "Viewer" / datetime.now().strftime("%Y_%m_%d.log")
    log.parent.mkdir(parents=True)
    log.write_bytes(b"\xff\xfe")
    ui = SimpleNamespace(selected=None)

    def click(card, **kwargs):
        ui.selected = card
        stamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S.%f")[:-3]
        line = (f"[{stamp}] [User Action] [UI] "
                f"[Study list item Click. (Study Key: {card})] "
                "[CFrameExamined::OnNotify]\r\n")
        with log.open("ab") as stream:
            stream.write(line.encode("utf-16le"))

    ui.click = click
    ctx = SimpleNamespace(db=StudyDb({48: [0, 1, 2], 52: [0, 2, 2]}),
                          cfg={"data_dir": str(tmp_path)},
                          evidence_root=str(tmp_path))
    monkeypatch.setattr(wf.flows, "cold_start", lambda *a, **k: (ui, {}))
    monkeypatch.setattr(wf.flows, "ensure_patient_screen", lambda _ui: True)
    monkeypatch.setattr(wf.sv, "ensure_transfer_syntax", lambda *a: True)
    monkeypatch.setattr(wf.sv, "queue_keys", lambda _ctx: [])
    monkeypatch.setattr(wf.sv, "clear_received", lambda _ctx: None)
    monkeypatch.setattr(wf, "_examined_search", lambda *_a: cards)
    monkeypatch.setattr(wf, "_close_leftovers", lambda *_a: None)
    selected = []

    def open_preview(_ui, scope):
        selected.append(ui.selected)
        raise RuntimeError("단위시험: Preview 앞에서 종료")

    monkeypatch.setattr(wf, "_open_preview", open_preview)
    return wf.run(ctx), selected


def test_real_run_selects_original_using_fresh_card_key_not_first_card(monkeypatch, tmp_path):
    _result, selected = run_to_preview(monkeypatch, tmp_path, [52, 48])
    assert selected == [48]


def test_real_run_does_not_send_another_study_when_original_card_is_absent(monkeypatch, tmp_path):
    result, selected = run_to_preview(monkeypatch, tmp_path, [52])
    assert selected == []
    assert result.aborted


def test_receive_wait_scopes_same_patient_to_selected_original(monkeypatch):
    from core import storagescp

    timer = SimpleNamespace(now=0)
    timer.time = lambda: timer.now
    timer.sleep = lambda seconds: setattr(timer, "now", timer.now + seconds)
    monkeypatch.setattr(wf.sv, "time", timer)

    class Server:
        def studies(self):
            return [dict(patient_id=wf.PATIENT_ID, study_instance_uid=f"1.2.{key}",
                         instance_count=1) for key in (48, 52)]

        def objects(self, *, study_uids):
            return [dict(PatientID=wf.PATIENT_ID, StudyInstanceUID=uid,
                         SOPInstanceUID=uid + ".1") for uid in study_uids]

    monkeypatch.setattr(storagescp, "server", lambda _ctx: Server())
    source = dict(Key=48, StudyInstanceUID="1.2.48")
    objects = wf._wait_received(SimpleNamespace(), source)
    assert [obj["StudyInstanceUID"] for obj in objects] == ["1.2.48"]


def test_queue_uses_real_columns_and_excludes_other_study_images():
    # INFORMATION_SCHEMA 확인: Queue에는 StudyKey/StudyInstanceUID가 없다.
    # SQLite에서 실제 SQL을 실행해 존재하지 않는 컬럼을 쓰면 실패하게 한다.
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE DICOM_STORAGE_QUEUE "
                           "([Key] INTEGER, State INTEGER, DataType INTEGER, "
                           "InstanceUID TEXT, ClassUID TEXT, PatientID TEXT)")
        connection.executemany("INSERT INTO DICOM_STORAGE_QUEUE VALUES (?,?,?,?,?,?)", [
            (20, 7, 1, None, None, wf.PATIENT_ID),  # 이전 전송의 RDSR
            (21, 7, 0, "1.2.48.1", None, wf.PATIENT_ID),
            (22, 7, 0, "1.2.52.1", None, wf.PATIENT_ID),  # 같은 환자, 다른 검사
            (23, 7, 1, None, None, wf.PATIENT_ID),
            (24, 7, 1, None, None, "OTHER"),
        ])

        class Db:
            def query(self, database, sql, params=None):
                return [dict(row) for row in connection.execute(sql, params or {})]

        source = dict(Key=48, StudyInstanceUID="1.2.48",
                      sendable=[dict(ImageInstanceUID="1.2.48.1")])
        rows = wf._queue_rows(SimpleNamespace(db=Db()), [21, 22, 23, 24], source)
        assert sorted(row["Key"] for row in rows) == [21, 23]
