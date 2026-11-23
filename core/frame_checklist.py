# -*- coding: utf-8 -*-
"""체크리스트 결과 xlsx의 공통 "결과 요약" 시트 (frame/FRAME.md 2.6, REQ-FRAME-004). Bellalun·VXvue 공용.

각 제품은 기준 체크리스트 사본의 TC 행에 자기 양식대로 결과를 적는다(VXvue K열, Bellalun 결과 열).
이 모듈은 그 사본 맨 앞에 두 제품이 같은 모양으로 보이는 요약 시트를 만든다. 제품 이름·판정은 호출자가 넘긴다.

TC 대응 규칙(두 제품 공통):
- 체크리스트 행과 자동화 결과는 TC ID가 정확히 같을 때만 잇는다. 번호·제목으로 추측하지 않는다.
- 결과가 없는 체크리스트 행은 판정 "미수행"과 그 이유를 적는다.
- 체크리스트에 없는 자동화 단계(환경 준비 등)는 "체크리스트 밖 준비 단계"에 따로 모은다.
"""
from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

SHEET_TITLE = '결과 요약'
NOT_RUN = '미수행'
ORDER = ('FAIL', 'BLOCKED', 'MANUAL', 'SKIP', 'PASS', NOT_RUN)
# 레포트 배지(core/report_layout.py)와 같은 색 계열.
FILL = {'PASS': 'D8F0E6', 'FAIL': 'F8D7DA', 'MANUAL': 'FBEFD5', 'SKIP': 'E2E8F0', 'BLOCKED': 'EADCF5', NOT_RUN: 'F2F2F2'}
INK = {'PASS': '167451', 'FAIL': 'A41926', 'MANUAL': '976A15', 'SKIP': '334E68', 'BLOCKED': '71419B', NOT_RUN: '7C8794'}
LEVEL_INK = {'ok': '167451', 'bad': 'A41926', 'warn': '976A15', 'info': '334E68'}
COLUMNS = (('번호', 6), ('TC ID', 28), ('TC 제목', 38), ('판정', 11), ('확인할 내용', 70), ('체크리스트 위치', 16))
THIN = Side(style='thin', color='DCE4EC')


def verdict_counts(rows):
    counts = {key: 0 for key in ORDER}
    for row in rows:
        counts[row['verdict'] if row['verdict'] in counts else NOT_RUN] += 1
    return counts


def headline(counts):
    """요약 시트 맨 위 결론 문장과 색."""
    total_run = sum(counts[k] for k in ORDER if k != NOT_RUN)
    if total_run == 0:
        return '자동화 결과가 없습니다. 실행 기록을 확인하세요.', 'bad'
    if counts['FAIL']:
        return f"실패한 TC가 {counts['FAIL']}개 있습니다. 아래 표의 확인할 내용과 레포트를 보세요.", 'bad'
    review = counts['MANUAL'] + counts['BLOCKED']
    if review:
        return f'자동 판정은 끝났고 사람이 확인할 TC가 {review}개 있습니다.', 'warn'
    return f"자동으로 확인한 TC가 모두 통과했습니다(PASS {counts['PASS']}개).", 'ok'


def _cell(ws, row, col, value, *, bold=False, size=10, color=None, fill=None, wrap=False, center=False):
    cell = ws.cell(row, col, value)
    cell.font = Font(name='맑은 고딕', size=size, bold=bold, color=color)
    if fill:
        cell.fill = PatternFill('solid', fgColor=fill)
    cell.alignment = Alignment(wrap_text=wrap, vertical='top', horizontal='center' if center else 'left')
    return cell


def add_summary_sheet(wb, *, product, rows, info=(), extras=(), report_path=None, meanings=None):
    """`wb` 맨 앞에 결과 요약 시트를 만든다.

    rows: 체크리스트 순서의 [{'tc_id','title','verdict','reason','location'}]. verdict는 판정 또는 '미수행'.
    info: [(항목, 값)] — 실행 일시, 체크리스트 원본, 제품 버전 등.
    extras: 체크리스트 밖 준비 단계 [{'tc_id','title','verdict','reason'}].
    meanings: {판정: 뜻}. 없으면 레포트와 같은 문장(core/report_layout.VERDICT_MEANINGS)을 쓴다.
    """
    if meanings is None:
        from core.report_layout import VERDICT_MEANINGS as meanings
    if SHEET_TITLE in wb.sheetnames:
        del wb[SHEET_TITLE]
    ws = wb.create_sheet(SHEET_TITLE, 0)
    ws.sheet_view.showGridLines = False
    for index, (_, width) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[ws.cell(1, index).column_letter].width = width

    counts = verdict_counts(rows)
    text, level = headline(counts)
    _cell(ws, 1, 1, f'{product} 체크리스트 자동화 결과', bold=True, size=16)
    _cell(ws, 2, 1, text, bold=True, size=12, color=LEVEL_INK[level])
    line = 4
    for label, value in info:
        _cell(ws, line, 1, label, bold=True, color='527087')
        ws.merge_cells(start_row=line, start_column=1, end_row=line, end_column=2)
        _cell(ws, line, 3, str(value), wrap=True)
        ws.merge_cells(start_row=line, start_column=3, end_row=line, end_column=5)
        line += 1
    if report_path:
        _cell(ws, line, 1, '레포트(HTML)', bold=True, color='527087')
        ws.merge_cells(start_row=line, start_column=1, end_row=line, end_column=2)
        link = _cell(ws, line, 3, str(report_path), color='186B96')
        link.hyperlink = str(report_path)
        ws.merge_cells(start_row=line, start_column=3, end_row=line, end_column=5)
        line += 1

    line += 1
    _cell(ws, line, 1, '판정 합계', bold=True, size=12)
    line += 1
    for index, key in enumerate(ORDER):
        _cell(ws, line, 1 + index, key, bold=True, color=INK[key], fill=FILL[key], center=True)
        _cell(ws, line + 1, 1 + index, counts[key], bold=True, size=12, color=INK[key], center=True)
    line += 3

    _cell(ws, line, 1, 'TC별 결과 (체크리스트 순서)', bold=True, size=12)
    line += 1
    for index, (name, _) in enumerate(COLUMNS, start=1):
        cell = _cell(ws, line, index, name, bold=True, fill='E8EDF6', center=True)
        cell.border = Border(bottom=THIN)
    ws.freeze_panes = ws.cell(line + 1, 1)
    header_line = line
    for number, row in enumerate(rows, start=1):
        line += 1
        verdict = row['verdict']
        values = (number, row['tc_id'], row.get('title', ''), verdict, row.get('reason', ''), row.get('location', ''))
        for col, value in enumerate(values, start=1):
            cell = _cell(ws, line, col, value, wrap=col in (3, 5), center=col in (1, 4))
            cell.border = Border(bottom=THIN)
        _cell(ws, line, 4, verdict, bold=True, color=INK.get(verdict, INK[NOT_RUN]),
              fill=FILL.get(verdict, FILL[NOT_RUN]), center=True).border = Border(bottom=THIN)
    ws.auto_filter.ref = f'A{header_line}:F{max(line, header_line)}'

    if extras:
        line += 2
        _cell(ws, line, 1, '체크리스트 밖 준비 단계 (환경 준비·점검)', bold=True, size=12)
        for row in extras:
            line += 1
            _cell(ws, line, 2, row['tc_id'])
            _cell(ws, line, 3, row.get('title', ''), wrap=True)
            _cell(ws, line, 4, row['verdict'], bold=True, color=INK.get(row['verdict'], INK[NOT_RUN]),
                  fill=FILL.get(row['verdict'], FILL[NOT_RUN]), center=True)
            _cell(ws, line, 5, row.get('reason', ''), wrap=True)

    line += 2
    _cell(ws, line, 1, '판정 뜻', bold=True, size=12)
    for key in ORDER:
        if key in meanings:
            line += 1
            _cell(ws, line, 1, key, bold=True, color=INK[key], fill=FILL[key], center=True)
            ws.merge_cells(start_row=line, start_column=1, end_row=line, end_column=2)
            _cell(ws, line, 3, meanings[key], wrap=True)
            ws.merge_cells(start_row=line, start_column=3, end_row=line, end_column=5)
    wb.active = 0
    return ws


def first_reason(result_rows):
    """한 TC의 결과 목록에서 사람이 먼저 볼 한 줄. PASS뿐이면 빈 문자열."""
    for result in result_rows:
        for check in getattr(result, 'checks', []):
            if check.status != 'PASS':
                text = ' '.join(str(check.note or check.actual or check.title or '').split())
                title = ' '.join(str(check.title or '').split())
                reason = f'[Step {check.step}] {title}' + (f' — {text}' if text and text != title else '')
                return reason[:300]
    return ''


TITLE_HEADERS = ('Title', 'TC Title', 'Test Case Title', 'Test Item', '제목', '시험 항목')


def combined_verdict(results):
    """같은 TC ID의 결과 여럿을 한 판정으로. FAIL > BLOCKED > MANUAL > PASS > SKIP."""
    verdicts = [getattr(r, 'verdict', None) for r in results]
    for key in ('FAIL', 'BLOCKED', 'MANUAL', 'PASS', 'SKIP'):
        if key in verdicts:
            return key
    return NOT_RUN


def rows_from_sheet(ws, header_row, tc_col, results, *, is_tc=lambda tc_id: bool(tc_id),
                    not_run_reason='이번 실행 범위에 없거나 자동화하지 않는 항목입니다. 체크리스트 기준으로 사람이 수행하세요.'):
    """체크리스트 시트 순서대로 요약 행을 만든다. TC ID가 정확히 같은 결과만 잇는다.

    반환: (rows, extras). extras는 체크리스트에 없는 자동화 결과(준비·환경 점검 등).
    """
    by_id = {}
    for result in results:
        by_id.setdefault(result.tc_id, []).append(result)
    title_col = next((c for c in range(1, ws.max_column + 1)
                      if str(ws.cell(header_row, c).value or '').strip() in TITLE_HEADERS), None)
    rows, seen = [], set()
    for row in range(header_row + 1, ws.max_row + 1):
        tc_id = str(ws.cell(row, tc_col).value or '').strip()
        if not tc_id or not is_tc(tc_id) or tc_id in seen:
            continue
        seen.add(tc_id)
        hits = by_id.get(tc_id, [])
        title = str(ws.cell(row, title_col).value or '').strip() if title_col else ''
        verdict = combined_verdict(hits) if hits else NOT_RUN
        rows.append({'tc_id': tc_id, 'title': title or (hits[0].title if hits else ''), 'verdict': verdict,
                     'reason': first_reason(hits) if hits else not_run_reason,
                     'location': f'{ws.title}!{row}'})
    extras = [{'tc_id': tc_id, 'title': hits[0].title, 'verdict': combined_verdict(hits), 'reason': first_reason(hits)}
              for tc_id, hits in by_id.items() if tc_id not in seen]
    return rows, extras
