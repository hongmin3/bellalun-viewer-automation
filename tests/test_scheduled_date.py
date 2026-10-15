"""Scheduled column semantics with fake controls/OCR; never access live UI."""
from types import SimpleNamespace

import pytest

from core import flows, screen


def control(hwnd, text, rect, *, ctrl_id=1, cls="AfxWnd140u"):
    return SimpleNamespace(hwnd=hwnd, text=text, rect=rect, ctrl_id=ctrl_id, cls=cls, visible=True)


def words(label, left=100, top=10):
    result = []
    for text in label.split():
        result.append({"text": text, "rect": (left, top, left + len(text) * 7, top + 14)})
        left += len(text) * 7 + 5
    return result


def test_exact_scheduled_label_box_never_accepts_birth_date():
    assert flows._scheduled_label_box(words("Birth Date")) is None
    assert flows._scheduled_label_box(words("Scheduled Study DateTime")) == (100, 10, 264, 24)


def test_scheduled_label_does_not_join_unrelated_rows():
    tokens = words("Scheduled", top=10) + words("Study DateTime", top=70)
    assert flows._scheduled_label_box(tokens) is None


@pytest.fixture
def settings(monkeypatch):
    events = []
    state = SimpleNamespace(page=0, checked=False, fail_check=False)
    box = control(10, "ListCtrl", (400, 500, 850, 800), ctrl_id=2334)
    row = control(11, "ListItem", (400, 720, 850, 755))
    checkbox = control(12, "CheckBox", (410, 723, 439, 752))
    update = control(13, "Update", (850, 930, 1080, 990), ctrl_id=flows.SETTING_UPDATE_BUTTON)

    class Ui:
        def by_id(self, key):
            return [box] if key == 2334 else [update] if key == flows.SETTING_UPDATE_BUTTON else []

        def wheel(self, target, notches, settle):
            assert target is box and notches == -5
            events.append("small-wheel")
            state.page += 1

        def click(self, target, settle):
            if target is checkbox:
                events.append("scheduled-checkbox")
                if not state.fail_check:
                    state.checked = True
            elif target is update:
                events.append("update")
            else:
                raise AssertionError("Never click a guessed bottom-of-list coordinate.")

    def children(hwnd, depth):
        if hwnd == box.hwnd:
            return [row, checkbox, row, checkbox]
        if hwnd == row.hwnd:
            return [checkbox, checkbox]
        return []

    monkeypatch.setattr(flows, "children", children)
    monkeypatch.setattr(flows, "open_group_page", lambda *args, **kwargs: None)
    monkeypatch.setattr(flows, "confirm_setting_dialog", lambda *args, **kwargs: events.append("confirmed"))
    monkeypatch.setattr(flows, "_scheduled_words", lambda rect, **kwargs:
                        words("Scheduled Study DateTime", 470, 730) if state.page >= 2 else words("Procedure", 470, 730), raising=False)
    monkeypatch.setattr(screen, "radio_selected", lambda target, **kwargs: state.checked if target is checkbox else True)
    monkeypatch.setattr(screen, "grab", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("No live capture")))
    return Ui(), state, events


def test_settings_find_actual_label_after_small_wheels_then_check_update_and_readback(settings):
    ui, state, events = settings
    result = flows.ensure_scheduled_datetime_column(ui)
    assert result["was_on"] is False and result["now_on"] is True and result["changed"] is True
    assert events == ["small-wheel", "small-wheel", "scheduled-checkbox", "update", "confirmed"]


def test_already_checked_exact_scheduled_row_is_not_toggled(settings):
    ui, state, events = settings
    state.checked = True
    result = flows.ensure_scheduled_datetime_column(ui)
    assert result["was_on"] is True and result["changed"] is False
    assert events == ["small-wheel", "small-wheel"]


def test_failed_scheduled_checkbox_readback_does_not_save_settings(settings):
    ui, state, events = settings
    state.fail_check = True
    with pytest.raises(flows.FlowError):
        flows.ensure_scheduled_datetime_column(ui)
    assert "scheduled-checkbox" in events and "update" not in events


@pytest.fixture
def patient(monkeypatch):
    state = SimpleNamespace(scrolls=0, available_at=0, actual="2026/10/15 AM 09:00", absent_scroll=False)
    box = control(20, "StudyList", (0, 0, 1000, 500), ctrl_id=2147)
    header = control(21, "", (0, 0, 1200, 30), cls="SysHeader32")
    viewport = control(22, "StudyListScrollWnd", (0, 0, 985, 485))
    row = control(23, "StudyListItem", (0, 38, 1200, 98))
    reads = []

    class Ui:
        def by_id(self, key):
            return [box] if key == 2147 else []

        def main_window(self):
            return control(24, "Viewer", (0, 0, 1024, 768))

    def scroll(ui, clicks):
        if state.absent_scroll:
            return False
        state.scrolls += 1
        row.rect = (-20 * state.scrolls, 38, 1200 - 20 * state.scrolls, 98)
        header.rect = (-20 * state.scrolls, 0, 1200 - 20 * state.scrolls, 30)
        return True

    def ocr(rect, **kwargs):
        reads.append(rect)
        # DOB is visible at x100; only the Scheduled header column is valid.
        return state.actual if rect[0] >= 500 else "1980/01/01"

    monkeypatch.setattr(flows, "children", lambda hwnd, depth: [header, viewport, row, header])
    monkeypatch.setattr(flows, "_study_items", lambda ui: [row])
    monkeypatch.setattr(flows, "scroll_study_list_right", scroll)
    monkeypatch.setattr(flows, "_scheduled_words", lambda rect, **kwargs:
                        words("Scheduled Study DateTime", 600, 10) if state.scrolls >= state.available_at
                        else words("Birth Date", 100, 10), raising=False)
    monkeypatch.setattr(screen, "ocr", ocr)
    return Ui(), state, reads


def test_scheduled_reader_uses_header_column_roi_not_whole_row(patient):
    ui, state, reads = patient
    result = flows.read_scheduled_datetime(ui)
    assert result["date"] == "20261015"
    assert len(reads) == 1 and reads[0][0] >= 500 and reads[0][1:4:2] == (38, 98)


def test_wrong_scheduled_date_is_returned_without_searching_for_expected_date(patient):
    ui, state, reads = patient
    state.actual = "2026/10/14 AM 09:00"
    result = flows.read_scheduled_datetime(ui)
    assert result["date"] == "20261014" and state.scrolls == 0


def test_birth_date_only_is_never_a_scheduled_date_even_if_expected_would_equal_dob(patient):
    ui, state, reads = patient
    state.available_at = 99
    state.absent_scroll = True
    result = flows.read_scheduled_datetime(ui)
    assert result["date"] == "" and result["error"]
    assert not reads


def test_reader_observes_final_scroll_result_instead_of_previous_frame(patient):
    ui, state, reads = patient
    state.available_at = 2
    result = flows.read_scheduled_datetime(ui, max_scroll=2)
    assert state.scrolls == 2
    assert result["date"] == "20261015"


def test_invalid_or_ambiguous_calendar_dates_do_not_become_a_scheduled_date(patient):
    ui, state, reads = patient
    for value in ("2026/02/30", "2026/10/14 2026/10/15", "2026/02/30 2026/10/15"):
        state.actual = value
        result = flows.read_scheduled_datetime(ui)
        assert result["date"] == "" and result["error"]
