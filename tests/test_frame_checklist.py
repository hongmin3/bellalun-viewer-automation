# -*- coding: utf-8 -*-
"""체크리스트 결과 xlsx 공통 "결과 요약" 시트와 TC 대응 규칙. VXvue selfcheck/test_frame_checklist.py와 같은 내용이다.

Validates: REQ-FRAME-004
"""
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook, load_workbook

from core import frame_checklist as fc
from core import report_layout


def check(step, status, title, note=''):
    return SimpleNamespace(step=step, status=status, title=title, note=note, actual='')


def result(tc_id, verdict, *checks, title='자동화 제목'):
    return SimpleNamespace(tc_id=tc_id, verdict=verdict, title=title, checks=list(checks))


def checklist():
    wb = Workbook()
    ws = wb.active
    ws.title = 'Checklist'
    ws.append(['문서 머리'])
    ws.append(['TC ID', 'Title', 'Step'])
    ws.append(['TC_A_01', '설치 확인', '1'])
    ws.append(['TC_A_02', '화면 확인', '1'])
    ws.append(['TC_A_03', '사람 전용', '1'])
    ws.append(['TC_A_01', '같은 TC의 둘째 줄', '2'])
    return wb, ws


class RowsTests(unittest.TestCase):
    def test_rows_follow_checklist_order_and_match_exact_tc_id_only(self):
        wb, ws = checklist()
        results = [result('TC_A_02', 'FAIL', check(1, 'PASS', '열기'), check(2, 'FAIL', '값 비교', '10 ≠ 3')),
                   result('TC_A_01', 'PASS', check(1, 'PASS', '설치')),
                   result('TC_A_1', 'PASS', check(1, 'PASS', '번호가 비슷한 다른 TC')),
                   result('AUTOMATION_ENVIRONMENT', 'PASS', check(1, 'PASS', '해상도'))]
        rows, extras = fc.rows_from_sheet(ws, 2, 1, results)
        self.assertEqual(['TC_A_01', 'TC_A_02', 'TC_A_03'], [r['tc_id'] for r in rows])
        self.assertEqual(['PASS', 'FAIL', fc.NOT_RUN], [r['verdict'] for r in rows])
        self.assertEqual('설치 확인', rows[0]['title'])
        self.assertEqual('[Step 2] 값 비교 — 10 ≠ 3', rows[1]['reason'])
        self.assertIn('사람이 수행', rows[2]['reason'])
        self.assertEqual('Checklist!4', rows[1]['location'])
        self.assertEqual({'TC_A_1', 'AUTOMATION_ENVIRONMENT'}, {e['tc_id'] for e in extras},
                         '번호가 비슷해도 다른 TC ID는 체크리스트 밖으로 둔다')

    def test_combined_verdict_priority(self):
        self.assertEqual('FAIL', fc.combined_verdict([result('x', 'PASS'), result('x', 'FAIL')]))
        self.assertEqual('BLOCKED', fc.combined_verdict([result('x', 'MANUAL'), result('x', 'BLOCKED')]))
        self.assertEqual(fc.NOT_RUN, fc.combined_verdict([]))


class SummarySheetTests(unittest.TestCase):
    def test_basic_writer_keeps_added_setup_out_of_official_counts(self):
        from core.checklist import write_results
        from core.result import TCResult
        with TemporaryDirectory() as folder:
            source, output = (Path(folder) / name for name in ('input.xlsx', 'output.xlsx'))
            wb, ws = checklist()
            wb.save(source)
            results = []
            for tc in ('TC_A_01', 'AUTOMATION_SETUP'):
                row = TCResult(tc, '합성 시험')
                row.add(1, '확인', 'PASS')
                row.finalize()
                results.append(row)
            write_results(source, results, out_path=output, sheet_name=ws.title)
            saved = load_workbook(output)
            try:
                rows = list(saved[fc.SHEET_TITLE].values)
                line = next(i for i, row in enumerate(rows) if row[0] == '판정 합계')
                counts = dict(zip(rows[line + 1], rows[line + 2]))
                self.assertEqual((counts['PASS'], counts[fc.NOT_RUN]), (1, 2))
                extra = next(i for i, row in enumerate(rows) if row[0] == '체크리스트 밖 준비 단계 (환경 준비·점검)')
                self.assertEqual(rows[extra + 1][1], 'AUTOMATION_SETUP')
                self.assertFalse(any('자동화 추가 항목' in row for row in rows))
                self.assertIn('자동화 추가 항목', [r[0] for r in saved[ws.title].values])
            finally:
                saved.close()

    def build(self, rows, extras=()):
        wb, _ = checklist()
        fc.add_summary_sheet(wb, product='제품', rows=rows, extras=extras, report_path='C:/r/Result_1.html',
                             info=[('실행 일시', '2026-11-23 15:00')])
        return wb

    def values(self, ws):
        return [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]

    def test_summary_is_first_active_sheet_and_keeps_checklist(self):
        wb = self.build([{'tc_id': 'TC_A_01', 'title': 't', 'verdict': 'PASS', 'reason': '', 'location': 'Checklist!3'}])
        self.assertEqual([fc.SHEET_TITLE, 'Checklist'], wb.sheetnames)
        self.assertEqual(fc.SHEET_TITLE, wb.active.title)
        self.assertEqual('TC ID', wb['Checklist'].cell(2, 1).value, '체크리스트 원본 칸은 그대로다')

    def test_headline_counts_link_legend_and_colours(self):
        rows = [{'tc_id': 'TC_A_01', 'title': 't1', 'verdict': 'PASS', 'reason': '', 'location': 'C!3'},
                {'tc_id': 'TC_A_02', 'title': 't2', 'verdict': 'MANUAL', 'reason': '화면 확인', 'location': 'C!4'},
                {'tc_id': 'TC_A_03', 'title': 't3', 'verdict': fc.NOT_RUN, 'reason': '범위 밖', 'location': 'C!5'}]
        ws = self.build(rows, [{'tc_id': 'ENV', 'title': '환경', 'verdict': 'PASS', 'reason': ''}])[fc.SHEET_TITLE]
        text = self.values(ws)
        self.assertEqual('제품 체크리스트 자동화 결과', ws.cell(1, 1).value)
        self.assertIn('사람이 확인할 TC가 1개', ws.cell(2, 1).value)
        self.assertEqual('976A15', ws.cell(2, 1).font.color.rgb[-6:])
        self.assertIn('C:/r/Result_1.html', text)
        self.assertTrue(any(c.hyperlink for row in ws.iter_rows() for c in row))
        self.assertIn('체크리스트 밖 준비 단계 (환경 준비·점검)', text)
        for key in ('PASS', 'FAIL', 'MANUAL', 'BLOCKED', 'SKIP', fc.NOT_RUN):
            self.assertIn(report_layout.VERDICT_MEANINGS[key], text, key)
        manual_cell = next(c for row in ws.iter_rows() for c in row if c.value == 'MANUAL' and c.column == 4)
        self.assertEqual(fc.FILL['MANUAL'], manual_cell.fill.fgColor.rgb[-6:])

    def test_headline_levels(self):
        self.assertEqual('bad', fc.headline(fc.verdict_counts([{'verdict': 'FAIL'}]))[1])
        self.assertEqual('ok', fc.headline(fc.verdict_counts([{'verdict': 'PASS'}, {'verdict': fc.NOT_RUN}]))[1])
        self.assertEqual('bad', fc.headline(fc.verdict_counts([{'verdict': fc.NOT_RUN}]))[1])

    def test_rebuilding_replaces_old_summary(self):
        wb = self.build([])
        fc.add_summary_sheet(wb, product='제품', rows=[])
        self.assertEqual(1, wb.sheetnames.count(fc.SHEET_TITLE))


class ReportLegendTests(unittest.TestCase):
    def test_every_report_shows_same_verdict_meanings(self):
        html = report_layout.render_shell(title='t', product='p', subtitle='s', nav=[], body_html='')
        for key in ('PASS', 'FAIL', 'MANUAL', 'BLOCKED', 'SKIP'):
            self.assertIn(report_layout.VERDICT_MEANINGS[key], html)
        self.assertNotIn('판정 뜻', report_layout.render_shell(title='t', product='p', subtitle='s', nav=[],
                                                              body_html='', legend=False))


if __name__ == '__main__':
    unittest.main()
