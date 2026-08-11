# -*- coding: utf-8 -*-
"""체크리스트 xlsx에 TC별 자동화 판정 결과를 기록한다.

원본 `Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 의 TC 행 순서를 그대로 두고
오른쪽에 결과 열만 덧붙여 별도 파일로 저장한다. 원본은 수정하지 않는다.
"""

import os
import shutil
from datetime import datetime

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from core.result import PASS, FAIL, MANUAL, SKIP

RESULT_HEADERS = ["자동화 판정", "판정 일시", "PASS", "FAIL", "MANUAL", "SKIP",
                  "실패 항목", "수동 확인 항목", "증적"]

FILLS = {
    PASS:   PatternFill("solid", fgColor="C6EFCE"),
    FAIL:   PatternFill("solid", fgColor="FFC7CE"),
    MANUAL: PatternFill("solid", fgColor="FFEB9C"),
    SKIP:   PatternFill("solid", fgColor="E7E6E6"),
    "미수행": PatternFill("solid", fgColor="F2F2F2"),
}
FONTS = {
    PASS:   Font(color="006100", bold=True),
    FAIL:   Font(color="9C0006", bold=True),
    MANUAL: Font(color="9C6500", bold=True),
    SKIP:   Font(color="808080"),
    "미수행": Font(color="A6A6A6"),
}


def _find_header_row(ws, tc_col_name="TC ID"):
    for row in range(1, min(ws.max_row, 20) + 1):
        for col in range(1, ws.max_column + 1):
            if str(ws.cell(row, col).value or "").strip() == tc_col_name:
                return row, col
    raise ValueError(f"'{tc_col_name}' 헤더를 찾지 못했습니다.")


def write_results(source_xlsx, results, out_path=None, sheet_name=None):
    """판정 결과를 체크리스트에 기록하고 저장 경로를 반환한다.

    results: TCResult 리스트. TC ID로 행을 매칭한다.
    체크리스트에 없는 TC ID는 시트 끝에 '자동화 추가 항목'으로 덧붙인다.
    """
    if not os.path.isfile(source_xlsx):
        raise FileNotFoundError(source_xlsx)

    out_path = out_path or os.path.join(
        os.path.dirname(source_xlsx) or ".",
        f"Checklist_Result_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    shutil.copyfile(source_xlsx, out_path)

    wb = load_workbook(out_path)
    ws = wb[sheet_name] if sheet_name else _pick_tc_sheet(wb)
    hdr_row, tc_col = _find_header_row(ws)

    # 결과 열 확보 (이미 있으면 재사용)
    existing = {str(ws.cell(hdr_row, c).value or "").strip(): c
                for c in range(1, ws.max_column + 1)}
    first_new = ws.max_column + 1
    col_of = {}
    for i, name in enumerate(RESULT_HEADERS):
        col_of[name] = existing.get(name, first_new + i)
        cell = ws.cell(hdr_row, col_of[name], name)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    by_id = {}
    for r in results:
        by_id.setdefault(r.tc_id, []).append(r)

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    written, matched_ids = 0, set()

    for row in range(hdr_row + 1, ws.max_row + 1):
        tc_id = str(ws.cell(row, tc_col).value or "").strip()
        if not tc_id:
            continue
        hits = by_id.get(tc_id)
        if not hits:
            _set(ws, row, col_of["자동화 판정"], "미수행")
            continue
        matched_ids.add(tc_id)
        _write_row(ws, row, col_of, hits, stamp)
        written += 1

    # 체크리스트에 없는 TC (예: _mid 보조 판정)
    extra = [tid for tid in by_id if tid not in matched_ids]
    if extra:
        row = ws.max_row + 2
        ws.cell(row, tc_col, "자동화 추가 항목").font = Font(bold=True)
        for tid in sorted(extra):
            row += 1
            ws.cell(row, tc_col, tid)
            _write_row(ws, row, col_of, by_id[tid], stamp)

    for name in RESULT_HEADERS:
        ws.column_dimensions[
            ws.cell(hdr_row, col_of[name]).column_letter].width = (
            12 if name in ("자동화 판정", "PASS", "FAIL", "MANUAL", "SKIP") else 40)

    wb.save(out_path)
    return {"path": out_path, "written": written, "extra": len(extra),
            "sheet": ws.title}


def _pick_tc_sheet(wb):
    for ws in wb:
        for row in range(1, min(ws.max_row, 20) + 1):
            for col in range(1, ws.max_column + 1):
                if str(ws.cell(row, col).value or "").strip() == "TC ID":
                    return ws
    return wb.active


def _set(ws, row, col, value, status=None):
    cell = ws.cell(row, col, value)
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    key = status or (value if value in FILLS else None)
    if key in FILLS:
        cell.fill = FILLS[key]
        cell.font = FONTS[key]
    return cell


def _write_row(ws, row, col_of, hits, stamp):
    verdicts = [h.verdict for h in hits]
    verdict = (FAIL if FAIL in verdicts else
               MANUAL if MANUAL in verdicts else
               PASS if PASS in verdicts else SKIP)

    total = {PASS: 0, FAIL: 0, MANUAL: 0, SKIP: 0}
    fails, manuals, evidence = [], [], []
    for h in hits:
        for k, v in h.counts.items():
            total[k] += v
        for c in h.checks:
            if c.status == FAIL:
                fails.append(f"[Step {c.step}] {c.title} — 기대={c.expected} / 실제={c.actual}")
            elif c.status == MANUAL:
                manuals.append(f"[Step {c.step}] {c.title}")
        evidence.extend(h.evidence)

    _set(ws, row, col_of["자동화 판정"], verdict, verdict)
    _set(ws, row, col_of["판정 일시"], stamp)
    for k in (PASS, FAIL, MANUAL, SKIP):
        _set(ws, row, col_of[k], total[k])

    for name, items in (("실패 항목", fails), ("수동 확인 항목", manuals),
                        ("증적", evidence)):
        cell = ws.cell(row, col_of[name], "\n".join(items) if items else "")
        cell.alignment = Alignment(vertical="top", wrap_text=True)
