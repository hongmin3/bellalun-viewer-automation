"""Pin official WF/WU workbooks and build a local, source-addressed planning ledger."""

import argparse
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock


WF_NAME = "(TC) R-23-2346_BellalunViewer_기본기능_Checklist.xlsx"
WU_NAME = "(TC) R-25-782_Bellalun Viewer_Windows Update 호환성 검증 Checklist.xlsx"
WF_SHA = "cbda58193d0685c9a55008a35fa15636645a7ecc17f17a43a8c35f3d83e7a78a"
WU_SHA = "2d859f008c0f7cb83260207417beae33b039a8aa267260151be8f6573280d3d4"
BASELINE_INDEX_SHA = "c30b73034c0c88c266ef1c6c237526e4ad2b36834dee595a3abdb74b608ed762"
SHEETS = {
    "Basic Function Checklist": ("WF", WF_NAME, WF_SHA, range(2, 71),
                                 "C", "I", {"precondition": "J", "action": "K",
                                            "expected": "L", "test_data": "M"}),
    "Screening Test": ("WF", WF_NAME, WF_SHA, range(11, 21),
                       None, "AB", {"action": "C", "expected": "D"}),
    "Checklist": ("WU", WU_NAME, WU_SHA, range(6, 19),
                  "B", "F", {"precondition": "G", "action": "H",
                              "expected": "I", "test_data": "J"}),
}
NUMBER = re.compile(r"^(\d+(?:\s*,\s*\d+)*)(?:\.(?!\d)|\))(?=\s|[^\d.]|$)")


def read_source(path, expected_hash):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError(f"{path.name}: 원본 SHA-256 불일치")
    return load_workbook(io.BytesIO(data), rich_text=True)


def read_prior(path):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != BASELINE_INDEX_SHA:
        raise ValueError("#191 기준선 인덱스 SHA-256 불일치")
    return json.loads(data.decode("utf-8-sig"))


def read_lines(cell):
    if cell.value is None:
        return []
    runs = cell.value if isinstance(cell.value, CellRichText) else [str(cell.value)]
    text = "".join(str(run) for run in runs)
    strike_flags = []
    for run in runs:
        struck = cell.font.strike
        if isinstance(run, TextBlock) and run.font.strike is not None:
            struck = run.font.strike
        strike_flags.extend([bool(struck)] * len(str(run)))
    offset = 0
    lines = []
    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        flags = [flag for char, flag in zip(line, strike_flags[offset:]) if not char.isspace()]
        offset += len(line)
        if not flags:
            continue
        number = NUMBER.match(line.lstrip())
        strike = "full" if all(flags) else "partial" if any(flags) else "none"
        lines.append({
            "source": f"{cell.coordinate}:{line_number}",
            "text": line.rstrip("\r\n"),
            "number": [int(value) for value in number[1].split(",")] if number else [],
            "strike": strike,
        })
    return lines


def match_expected(actions, expectations):
    numbers = {}
    for line in actions:
        if len(line["number"]) == 1 and line["strike"] == "none":
            numbers.setdefault(line["number"][0], []).append(line["source"])
    return {
        line["source"]: [numbers[n][0] for n in line["number"]]
        for line in expectations if line["strike"] == "none" and line["number"]
        and all(len(numbers.get(n, [])) == 1 for n in line["number"])
    }


def _new_evidence():
    return dict(run_id=None, report_sha256=None, operation=None, observation=None,
                failure_control=None, verdict=None, restoration=None)


def build_ledger(workbooks, prior):
    prior_sheets = {entry["sheet"]: entry for entry in prior["sheets"]}
    if set(prior_sheets) != set(SHEETS) or len(prior["sheets"]) != len(SHEETS):
        raise ValueError("#191 원장 시트 누락·중복")
    sheets = []
    counts = {"WF": Counter(), "WU": Counter()}
    for name, (kind, filename, sha, row_range, id_col, title_cols, columns) in SHEETS.items():
        sheet = workbooks[kind][name]
        old = prior_sheets[name]
        if (old["source"], old["sha256"]) != (filename, sha):
            raise ValueError(f"{name}: #191 원본 식별 불일치")
        old_rows = {row["row"]: row for row in old["rows"]}
        if set(old_rows) != set(row_range) or len(old_rows) != len(old["rows"]):
            raise ValueError(f"{name}: #191 행 누락·중복")
        rows = []
        for row in row_range:
            baseline = old_rows[row]
            hidden = bool(sheet.row_dimensions[row].hidden)
            if hidden != baseline["hidden"]:
                raise ValueError(f"{name}!{row}: #191 숨김 상태 불일치")
            cells = {role: read_lines(sheet[f"{column}{row}"])
                     for role, column in columns.items()}
            if not cells["action"]:
                raise ValueError(f"{name}!{row}: 대상 행에 원본 Step 없음")
            identifier = sheet[f"{id_col}{row}"].value if id_col else None
            title = [str(sheet[f"{col}{row}"].value).strip()
                     for col in title_cols if sheet[f"{col}{row}"].value is not None]
            state = baseline["assessment"][2 if kind == "WF" else 1]
            counts[kind][state] += 1
            links = match_expected(cells["action"], cells["expected"])
            for role, lines in cells.items():
                for line in lines:
                    strike = line["strike"]
                    line["applicability"] = {
                        "none": "in_scope", "full": "struck_in_source",
                        "partial": "review_struck_text",
                    }[strike]
                    if role == "expected":
                        line["candidate_actions"] = links.get(line["source"], [])
                    if strike != "full":
                        line["current_evidence"] = _new_evidence()
            rows.append({
                "row": row, "hidden": hidden, "id_cell": f"{id_col}{row}" if id_col else None,
                "tc": str(identifier).strip() if identifier else f"{name}!{row}",
                "title": " / ".join(title), "source_lines": cells,
                "baseline_191": {"classification": state,
                                 "assessment": baseline["assessment"],
                                 "observations": baseline["observations"]},
            })
        sheets.append({"suite": kind, "source": filename, "sha256": sha, "sheet": name,
                       "sheet_state": sheet.sheet_state, "rows": rows})
    return {"schema": 1, "baseline_source": "PC1/job212/1.0.27/b9940f8",
            "baseline_index_sha256": BASELINE_INDEX_SHA,
            "baseline_counts": counts, "baseline_reports": prior["reports"],
            "sheets": sheets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wf", type=Path, required=True)
    parser.add_argument("--wu", type=Path, required=True)
    parser.add_argument("--baseline-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        prior = read_prior(args.baseline_index)
        workbooks = {"WF": read_source(args.wf, WF_SHA), "WU": read_source(args.wu, WU_SHA)}
        ledger = build_ledger(workbooks, prior)
        payload = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"원장 생성 실패: {exc}\n")
    print(json.dumps(ledger["baseline_counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
