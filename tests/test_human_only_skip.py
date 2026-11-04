"""사람이 직접 하는 TC 는 MANUAL 이 아니라 SKIP 으로 남긴다(2026-11-05 사용자 결정, REQ-VERDICT-002)."""
import os
import tempfile
import unittest

from openpyxl import load_workbook

from core.result import SKIP
from core import winupdate_report
from tests import winupdate, workflow16

HUMAN_ONLY_WU = ("TC_WindowsUpdate_01", "TC_WindowsUpdate_12", "TC_WindowsUpdate_13")


def _no_sysinfo_results():
    from unittest.mock import patch
    with patch.multiple("core.sysinfo", pc_info=lambda: {}, os_update_info=lambda: {}):
        return winupdate.build_wu_results({}, live_extra={})


class HumanOnlyVerdictTests(unittest.TestCase):
    def test_wu_human_only_tcs_are_skip_with_reason(self):
        results = {r.tc_id: r for r in _no_sysinfo_results()}
        for tc in HUMAN_ONLY_WU:
            r = results[tc]
            self.assertEqual(r.verdict, SKIP, tc)
            self.assertTrue(all(c.status == SKIP for c in r.checks), tc)
            self.assertIn("사람이 직접", r.checks[0].note, tc)
            self.assertIs(r.checks[0].blocks_verdict, False, tc)

    def test_human_only_set_matches_wu_mapping(self):
        self.assertEqual(set(winupdate.HUMAN_ONLY_TCS) & {r.tc_id for r in _no_sysinfo_results()},
                         set(HUMAN_ONLY_WU))

    def test_workflow16_is_skip(self):
        r = workflow16.run(None)
        self.assertEqual(r.verdict, SKIP)
        self.assertIn("TC_Basic_WorkFlow_16", winupdate.HUMAN_ONLY_TCS)


class SkipReasonColumnTests(unittest.TestCase):
    def test_skip_reason_is_written_next_to_result(self):
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..",
                           "Windows Update 호환성 검증 Checklist_Bellalun Viewer_R-25-782.xlsx")
        if not os.path.isfile(src):
            self.skipTest("기준 체크리스트 없음")
        results = _no_sysinfo_results()
        with tempfile.TemporaryDirectory() as folder:
            out = winupdate_report.write_results(src, results, out_path=os.path.join(folder, "o.xlsx"))["path"]
            ws = load_workbook(out)[winupdate_report.CHECKLIST_SHEET]
            hdr, tc_col = winupdate_report._find_header_row(ws)
            found = {}
            for row in range(hdr + 1, ws.max_row + 1):
                tc = ws.cell(row, tc_col).value
                if tc in HUMAN_ONLY_WU:
                    found[tc] = (ws.cell(row, winupdate_report.NEW_RESULT_COL).value,
                                 ws.cell(row, winupdate_report.NEW_COMMENT_COL).value)
            self.assertEqual(set(found), set(HUMAN_ONLY_WU))
            for tc, (verdict, reason) in found.items():
                self.assertEqual(verdict, "Skip", tc)
                self.assertIn("사람이 직접", reason or "", tc)


if __name__ == "__main__":
    unittest.main()
