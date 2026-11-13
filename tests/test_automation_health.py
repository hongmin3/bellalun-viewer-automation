# -*- coding: utf-8 -*-
import json
import os
import tempfile
import time
import unittest
from datetime import datetime

from core import automation_health as health
import pytest


def _report(path, generated, ids):
    data = {
        "generated": generated,
        "results": [{"tc_id": tc_id, "verdict": "PASS"} for tc_id in ids],
    }
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(data, stream)


class AutomationHealthTests(unittest.TestCase):
    def test_latest_full_regression_ignores_individual_report(self):
        with tempfile.TemporaryDirectory() as folder:
            full = os.path.join(folder, "Result_20260820_010000.json")
            one = os.path.join(folder, "Result_20260821_010000.json")
            _report(full, "2026-08-20T01:00:00",
                    sorted(health.FULL_REGRESSION_MARKERS))
            _report(one, "2026-08-21T01:00:00", ["TC_Basic_WorkFlow_14"])
            found = health.latest_full_regression(folder)
            self.assertEqual(full, found["path"])

    def test_regression_age_marks_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "Result_20260820_010000.json")
            _report(path, "2026-08-20T01:00:00",
                    sorted(health.FULL_REGRESSION_MARKERS))
            now = datetime.fromisoformat("2026-08-25T01:00:00").timestamp()
            self.assertEqual(
                "stale", health.regression_age(folder, 3, now=now)["status"])
            self.assertEqual(
                "ok", health.regression_age(folder, 7, now=now)["status"])

    def test_state_write_is_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            health.write_state(folder, "running", regression_pid=123)
            self.assertEqual(123, health.read_state(folder)["regression_pid"])

    def test_state_write_carries_tc_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            health.write_state(
                folder, "running", regression_pid=123,
                current_tc="TC_Basic_WorkFlow_07", current_title="Emergency 검사",
                index=7, total=32, tc_started="2026-09-03T00:00:00+09:00")
            state = health.read_state(folder)
            self.assertEqual("TC_Basic_WorkFlow_07", state["current_tc"])
            self.assertEqual(7, state["index"])
            self.assertEqual(32, state["total"])

    def test_dump_filter_uses_start_time(self):
        with tempfile.TemporaryDirectory() as folder:
            old = os.path.join(folder, "VIEWER.exe.1.dmp")
            new = os.path.join(folder, "VIEWER.exe.2.dmp")
            open(old, "wb").close()
            start = time.time()
            os.utime(old, (start - 10, start - 10))
            open(new, "wb").close()
            os.utime(new, (start + 1, start + 1))
            self.assertEqual(
                [new], health.find_crash_dumps("VIEWER", since=start,
                                               dump_dir=folder))


@pytest.mark.parametrize('flag', [{'presentation_only': True}, {'report_role': 'presentation'}])
def test_completed_wu_rejects_presentation_copy_at_actual_app_entry(tmp_path, flag):
    from bellalunauto.app import completed_report
    data = {'meta': {'execution_mode': 'live', 'chain_completed': True, **flag},
            'results': [{'tc_id': f'TC_WindowsUpdate_{i:02}', 'verdict': 'PASS'} for i in range(1, 14)]}
    (tmp_path / 'Result_WindowsUpdate_fixture.json').write_text(json.dumps(data), encoding='utf-8')
    assert completed_report(tmp_path, 'run-winupdate', 0) is None


@pytest.mark.parametrize('data', [None, [], {'meta': 'invalid'}, {'results': None},
    {'results': [None]}, {'results': [{'tc_id': []}]}])
def test_completed_report_data_rejects_malformed_reports(data):
    assert health.completed_report_data(data, 'run-regression') is False
    assert health.completed_report_data(data, 'run-winupdate') is False


def test_completed_report_data_preserves_legacy_basic_and_live_wu_scope():
    basic = {'results': [{'tc_id': tc} for tc in health.FULL_REGRESSION_MARKERS]}
    assert health.completed_report_data(basic, 'run-regression') is True
    assert health.completed_report_data(basic, 'run-wu09') is False
    wu = {'meta': {'execution_mode': 'live', 'chain_completed': True},
          'results': [{'tc_id': f'TC_WindowsUpdate_{i:02}'} for i in range(1, 14)]}
    assert health.completed_report_data(wu, 'run-winupdate') is True
    wu['meta']['chain_completed'] = False
    assert health.completed_report_data(wu, 'run-winupdate') is False


@pytest.mark.parametrize('meta', [[], '', False])
def test_completed_report_rejects_malformed_metadata_with_full_markers(meta):
    data = {'meta': meta, 'results': [{'tc_id': tc} for tc in health.FULL_REGRESSION_MARKERS]}
    assert health.completed_report_data(data, 'run-regression') is False


def test_basic_report_scanner_ignores_malformed_json_shape(tmp_path):
    from bellalunauto.app import completed_report
    (tmp_path / 'Result_fixture.json').write_text('[]', encoding='utf-8')
    assert completed_report(tmp_path, 'run-regression', 0) is None


if __name__ == "__main__":
    unittest.main()
