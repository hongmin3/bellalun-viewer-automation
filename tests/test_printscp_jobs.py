"""공유 Print SCP에서 이 Viewer가 보낸 job만 고르는지 확인한다.

Validates: REQ-REGRESSION-001
"""
from unittest import mock

import pytest

from core.printscp import PrintServer
from tests import workflow08 as wf


def _job(job_id, ae):
    return {"id": job_id, "calling_ae_title": ae, "film_size_id": "8INX10IN"}


def _server(*snapshots):
    server = PrintServer("http://print.invalid")
    server.jobs = mock.Mock(side_effect=list(snapshots) + [snapshots[-1]] * 20)
    return server


def test_foreign_job_arriving_first_is_skipped_until_own_job_arrives():
    # 1.0.7 WF08: QXLink job 371 이 먼저, Bellalun job 372 가 8초 뒤에 도착했다.
    server = _server([_job(370, "BELLALUN")],
                     [_job(370, "BELLALUN"), _job(371, "QXLink")],
                     [_job(370, "BELLALUN"), _job(371, "QXLink"), _job(372, "BELLALUN")])
    with mock.patch("time.sleep"):
        jobs = server.wait_for_jobs(count=1, timeout=60, poll=.5, exclude_ids={"370"},
                                    calling_ae="BELLALUN")
    assert [j["id"] for j in jobs] == [372]


def test_without_calling_ae_any_new_job_counts_as_before():
    server = _server([_job(371, "QXLink")])
    with mock.patch("time.sleep"):
        jobs = server.wait_for_jobs(count=1, timeout=60, exclude_ids=())
    assert [j["id"] for j in jobs] == [371]


def test_wait_own_job_returns_own_job_and_records_foreign_ones():
    server = _server([_job(371, "QXLink"), _job(372, "BELLALUN")])
    with mock.patch("time.sleep"):
        job, ignored = wf._wait_own_job(server, {"370"}, "BELLALUN", timeout=30)
    assert job["id"] == 372
    assert ignored == [{"id": 371, "calling_ae_title": "QXLink"}]


def test_wait_own_job_times_out_when_only_foreign_jobs_arrive():
    server = _server([_job(371, "QXLink")])
    with mock.patch("time.sleep"), mock.patch("time.time", side_effect=[0, 0, 100, 100, 100]):
        job, ignored = wf._wait_own_job(server, set(), "BELLALUN", timeout=30)
    assert job is None and ignored == [{"id": 371, "calling_ae_title": "QXLink"}]


def test_station_ae_is_required():
    db = mock.Mock()
    db.one.return_value = {"StationAETitle": "BELLALUN"}
    assert wf._station_ae(db) == "BELLALUN"
    db.one.return_value = {"StationAETitle": ""}
    with pytest.raises(RuntimeError, match="Station AE"):
        wf._station_ae(db)
