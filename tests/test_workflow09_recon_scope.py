# -*- coding: utf-8 -*-
"""WF_09 Step 8 보강 판정의 Recon 범위를 고정한다.

2026-10-18 후보7 실시간 WU: WU 체인은 XIPL 묶음을 WF_09 보다 먼저 실행해 같은
환자(DATA_FLOW_MWL_01)에 Recon 이 있는 검사가 여럿 생겼다. Export 는 선택한 검사
하나(StudyKey 50, Recon series 57·58)를 내보냈고 두 Recon 이 모두 들어 있었는데,
기대 집합은 환자 전체에서 모아 다른 검사(48)의 Recon 2건을 '누락'으로 셌다.
같은 설치판의 기본기능 전체(XIPL 이 WF_09 뒤)는 PASS 였다.
"""
import unittest

from tests import workflow09


class _Db:
    """StudyKey 로 거른 질의만 그 검사의 행을 돌려준다."""

    ROWS = [
        {"StudyKey": 48, "SeriesKey": 54, "ImageInstanceUID": "old-3dn"},
        {"StudyKey": 48, "SeriesKey": 55, "ImageInstanceUID": "old-3dw"},
        {"StudyKey": 50, "SeriesKey": 57, "ImageInstanceUID": "new-3dn"},
        {"StudyKey": 50, "SeriesKey": 58, "ImageInstanceUID": "new-3dw"},
    ]

    def __init__(self):
        self.queries = []

    def query(self, database, sql, params=None):
        self.queries.append((database, sql, dict(params or {})))
        assert "StudyKey=@study" in sql, "Export 한 검사로 범위를 좁혀야 한다"
        return [dict(r) for r in self.ROWS if r["StudyKey"] == params["study"]]


class ReconExportScopeTests(unittest.TestCase):
    def test_other_studies_of_same_patient_are_not_expected_in_this_export(self):
        out = workflow09.recon_export_coverage(_Db(), 50, {"new-3dn", "new-3dw", "x"})
        self.assertTrue(out["ok"], out)
        self.assertEqual([], out["missing_recon"])
        self.assertEqual([57, 58], [s["SeriesKey"] for s in out["recon_series"]])

    def test_a_recon_of_the_exported_study_that_is_absent_still_fails(self):
        out = workflow09.recon_export_coverage(_Db(), 50, {"new-3dn"})
        self.assertFalse(out["ok"])
        self.assertEqual(["new-3dw"], out["missing_recon"])

    def test_single_recon_series_is_reported_for_skip(self):
        db = _Db()
        db.ROWS = [r for r in _Db.ROWS if r["SeriesKey"] != 58]
        out = workflow09.recon_export_coverage(db, 50, {"new-3dn"})
        self.assertEqual(1, len(out["recon_series"]))


if __name__ == "__main__":
    unittest.main()
