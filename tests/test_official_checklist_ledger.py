import pytest
from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont

from tools.official_checklist_ledger import match_expected, read_lines, read_prior, read_source


def test_source_lines_keep_location_and_partial_strike():
    cell = Workbook().active["K16"]
    cell.value = CellRichText("1. Send\n", TextBlock(InlineFont(strike=True), "- old"),
                              " and new\n\n2. Check")
    lines = read_lines(cell)
    assert [(item["source"], item["number"], item["strike"]) for item in lines] == [
        ("K16:1", [1], "none"),
        ("K16:2", [], "partial"),
        ("K16:4", [2], "none"),
    ]
    assert lines[1]["text"] == "- old and new"


def test_only_explicit_unambiguous_expected_links_are_suggested():
    sheet = Workbook().active
    sheet["H12"] = "1. Send\n2. Read"
    sheet["I12"] = "1,2. Works\n- alternate\n6. Mismatched\nplain line"
    result = match_expected(read_lines(sheet["H12"]), read_lines(sheet["I12"]))
    assert result == {"I12:1": ["H12:1", "H12:2"]}


def test_changed_workbook_is_rejected_before_parsing(tmp_path):
    path = tmp_path / "source.xlsx"
    path.write_bytes(b"substitute")
    with pytest.raises(ValueError, match="SHA-256"):
        read_source(path, "a" * 64)


def test_historic_assessments_must_come_from_the_pinned_index(tmp_path):
    path = tmp_path / "index.json"
    path.write_text('{"sheets": [], "reports": {"extra": "unverified"}}')
    with pytest.raises(ValueError, match="SHA-256"):
        read_prior(path)
