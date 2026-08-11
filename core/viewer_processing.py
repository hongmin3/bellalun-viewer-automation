# -*- coding: utf-8 -*-
"""Bellalun Viewer-integrated image processing automation.

The compatibility TCs must enter XIPL/PureImpact from the Viewer.  This
module intentionally never starts XIPL.STUDIO directly.
"""

from __future__ import annotations

import os
import re
import shutil
import time
import ctypes
import ctypes.wintypes as wintypes
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageGrab, ImageOps

from . import flows
from .ui import ViewerUi, children


PROC = 1151
XIPL_TOOL = 1160
POST_RECON = 1178
EXPAND_TOOLS = 1163
PARAM_COMBO = 2040
REFRESH = 2056
PREVIEW = 2054
APPLY = 2055
CANCEL = 1102

TESSERACT_EXE = os.environ.get(
    "BELLALUN_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

SLIDER_NAMES_2D = {
    2057: "Contrast",
    2058: "Sharpness",
    2059: "Brightness",
    2060: "Tone type",
    2061: "Noise reduction",
}

SLIDER_NAMES_3D = {
    2043: "Recon.Contrast",
    2044: "Recon.Sharpness",
    2045: "Recon.Brightness",
    2046: "Recon.Tone type",
    2049: "Syn.Contrast",
    2050: "Syn.Sharpness",
    2051: "Syn.Brightness",
    2052: "Syn.Tone type",
}

TC01_OVERLAY_FIELDS = {
    113: ("Histogram", 5),
    134: ("Window Level (W1/W2)", 6),
}


def capture(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    rect = wintypes.RECT()
    if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom),
                       all_screens=True).save(path)
    else:
        ImageGrab.grab(all_screens=True).save(path)
    return path


def capture_viewer_window(ui, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    win = ui.main_window()
    if not win:
        raise RuntimeError("Viewer window is not available")
    ImageGrab.grab(bbox=win.rect, all_screens=True).save(path)
    return path


def read_viewer_w1_w2(image_path):
    """OCR the selected left 2D pane's W1/W2 overlay."""
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for Viewer overlay OCR") from exc
    if os.path.exists(TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    image = Image.open(image_path).convert("RGB")
    w, h = image.size
    # In the standard 1x2 Viewer layout the selected 2D pane occupies the
    # left 38% of the window. Its Histogram/W1/W2 overlay is upper-right.
    crop = image.crop((int(w * .25), int(h * .22),
                       int(w * .38), int(h * .42)))
    crop = crop.resize((crop.width * 5, crop.height * 5),
                       Image.Resampling.LANCZOS)
    text = pytesseract.image_to_string(
        crop,
        config="--psm 6 -c tessedit_char_whitelist=Ww0123456789: ")
    pairs = re.findall(
        r"W[1lI]\s*[:;]?\s*(\d+?)\s*W2\s*[:;]?\s*(\d+)", text, re.I)
    if not pairs:
        # Layout/DPI fallback: scan the whole Viewer window.  Duplicate pairs
        # are accepted only when every visible pane reports the same values.
        full = image.resize((image.width * 2, image.height * 2),
                            Image.Resampling.LANCZOS)
        fallback = pytesseract.image_to_string(
            full, config="--psm 11 -c tessedit_char_whitelist=Ww0123456789: ")
        text = text + "\n" + fallback
        pairs = re.findall(
            r"W[1lI]\s*[:;]?\s*(\d+?)\s*W2\s*[:;]?\s*(\d+)", text, re.I)
    if not pairs:
        raise RuntimeError(f"Viewer W1/W2 overlay OCR failed: {text!r}")
    values = {(int(w1), int(w2)) for w1, w2 in pairs}
    if len(values) != 1:
        raise RuntimeError(f"Viewer selected-pane W1/W2 is ambiguous: {values}")
    w1, w2 = values.pop()
    return {"w1": w1, "w2": w2, "ocr": text.strip()}


def ensure_parameter_copies(parameter_root=r"C:\XIPL\PARAMETER"):
    """Reset every automation-owned test parameter from its clean source.

    Test outputs must never leak from a previous run.  Delete only the five
    explicitly managed TEST_* files below, then recreate byte-for-byte copies
    from the installed default parameters.  Unrelated/user parameter files are
    intentionally left untouched.
    """
    parameter_root = os.path.abspath(parameter_root)
    specs = [
        (os.path.join(parameter_root, "Standard_Default_M.pim"),
         os.path.join(parameter_root, "TEST_2D_FLOW.pim")),
        (os.path.join(parameter_root, "Standard_Default_M.pim"),
         os.path.join(parameter_root, "TEST_2D_A.pim")),
        (os.path.join(parameter_root, "Standard_Default_M.pim"),
         os.path.join(parameter_root, "TEST_2D_B.pim")),
        (os.path.join(parameter_root, "Standard_Default_M.pim"),
         os.path.join(parameter_root, "TEST_XIPL_SAVED.pim")),
        (os.path.join(parameter_root, "DBT_Standard_Default.xtp"),
         os.path.join(parameter_root, "TEST_3D_FLOW.xtp")),
    ]
    for source, _ in specs:
        if not os.path.exists(source):
            raise FileNotFoundError(source)

    parameter_root = os.path.normcase(parameter_root)
    for _, target in specs:
        resolved = os.path.normcase(os.path.abspath(target))
        if os.path.commonpath([parameter_root, resolved]) != parameter_root:
            raise RuntimeError(f"Unsafe test parameter target: {target}")
        if os.path.exists(target):
            os.remove(target)

    for source, target in specs:
        shutil.copy2(source, target)
    return [target for _, target in specs]


def ensure_tc01_overlay(ui, db):
    """Configure Histogram and W1/W2 through Setting > Display > Overlay."""
    def saved_fields():
        rows = db.query(
            "CONFIGURATION",
            "SELECT FieldID,Position,[Order] FROM OVERLAY_ITEM "
            "WHERE FieldID IN (113,134) ORDER BY FieldID")
        return {int(row["FieldID"]): row for row in rows}

    current = saved_fields()
    missing = [field_id for field_id in TC01_OVERLAY_FIELDS
               if field_id not in current]
    if not missing:
        return current

    flows.open_setting(ui, wait=3)
    flows.open_setting_group(ui, "display", wait=2)
    flows._click_setting_control(ui, 201, "Display > Overlay", wait=2)
    available = _visible(ui, 2382)
    add_top = _visible(ui, 2383)
    if not available or not add_top:
        raise RuntimeError("Display > Overlay item controls not found")

    for field_id in missing:
        label, catalogue_index = TC01_OVERLAY_FIELDS[field_id]
        rows = sorted({c.hwnd: c for c in children(available[0].hwnd, 5)
                       if c.text == "ListItem" and c.visible}.values(),
                      key=lambda c: c.rect[1])
        if len(rows) <= catalogue_index:
            raise RuntimeError(f"Overlay catalogue item not visible: {label}")
        ui.click(rows[catalogue_index], settle=.4)
        ui.click(add_top[0], settle=.8)
        dialog = ui.dialog()
        if dialog:
            message = ui.dismiss_dialog(timeout=2)
            raise RuntimeError(f"Failed to add Overlay item {label}: {message}")

    flows.setting_update(ui, wait=3)
    end = time.time() + 8
    actual = saved_fields()
    while time.time() < end and any(x not in actual for x in missing):
        time.sleep(1)
        actual = saved_fields()
    if any(x not in actual for x in missing):
        raise RuntimeError(f"Overlay settings were not saved: {actual}")

    closes = [c for c in ui.by_id(4) if c.visible
              and c.rect[2] - c.rect[0] <= 60
              and c.rect[3] - c.rect[1] <= 60]
    if closes:
        ui.click(min(closes, key=lambda c: c.rect[1]), settle=2)
    return actual


def add_view_position(ui, mode):
    """Register LCC 2D or LCC(3D-N) through Procedure +."""
    before = len(flows.step_items(ui))
    add = [c for c in ui.by_id(1171) if c.visible
           and c.rect[2] - c.rect[0] >= 12 and c.rect[3] - c.rect[1] >= 12]
    if not add:
        raise RuntimeError("Procedure add button (1171) not found")
    ui.click(add[0], settle=1)
    dlg = ui.wait_dialog(timeout=6)
    if not dlg:
        raise RuntimeError("View Position dialog did not open")
    l, t, r, b = dlg.rect
    width, height = r - l, b - t
    if width < 500 or height < 450:
        raise RuntimeError(f"Unexpected View Position dialog geometry: {dlg.rect}")

    # Bellalun 1.0.12 exposes stable IDs for tabs, LCC, OK and Cancel.
    # Use those before any window-relative fallback so dialog size changes do
    # not select LMLO or miss the OK button.
    if mode == "3d":
        tabs = [c for c in ui.by_id(2083) if c.visible
                and c.rect[2] - c.rect[0] >= 100]
        if not tabs:
            raise RuntimeError("Preset (3D-N) tab (2083) not found")
        ui.click(tabs[0], settle=.7)
    elif mode != "2d":
        raise RuntimeError(f"Unsupported View Position mode: {mode}")

    lcc_id = 852 if mode == "3d" else 802
    lcc = [c for c in ui.by_id(lcc_id) if c.visible
           and c.rect[2] - c.rect[0] >= 100]
    ok = [c for c in ui.by_id(1101) if c.visible
          and c.rect[2] - c.rect[0] >= 80]
    if not lcc or not ok:
        cancel = [c for c in ui.by_id(1102) if c.visible]
        if cancel:
            ui.click(cancel[0], settle=.5)
        raise RuntimeError(f"LCC card ({lcc_id}) or OK button (1101) not found")
    ui.click(lcc[0], settle=.5)
    ui.click(ok[0], settle=1)
    after = len(flows.step_items(ui))
    if after != before + 1:
        raise RuntimeError(f"Procedure step registration failed: {before}->{after}")
    return after


def open_test_study(ctx):
    """Open the dedicated 2D+3D Viewer fixture by Patient ID.

    DATA_FLOW_MWL_01 was prepared through Procedure + with LCC and LCC(3D-N)
    and contains InstanceType 0/1/2/3.  Reusing the fixture makes repeated
    processing tests deterministic and avoids a local Procedure's unrelated
    default steps.
    """
    patient_id = ctx.cfg.get("xipl", {}).get("test_patient_id", "DATA_FLOW_MWL_01")
    row = ctx.db.one(
        "DATA", "SELECT TOP 1 s.[Key] FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid AND EXISTS (SELECT 1 FROM INSTANCE i "
        "WHERE i.StudyKey=s.[Key] AND i.InstanceType=1) ORDER BY s.[Key] DESC",
        {"pid": patient_id})
    if not row:
        raise RuntimeError(f"Viewer XIPL fixture not found: PatientID={patient_id}")
    instance_rows = ctx.db.query(
        "DATA", "SELECT [Key],InstanceType,ImageInstanceUID,SeriesKey,GroupKey "
        "FROM INSTANCE WHERE StudyKey=@study ORDER BY [Key]", {"study": row["Key"]})
    types = {int(x["InstanceType"]) for x in instance_rows}
    if not {0, 1, 2, 3}.issubset(types):
        raise RuntimeError(f"Fixture requires InstanceType 0/1/2/3; actual={sorted(types)}")

    ui, _ = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
    # Open the completed local study through View, not through MWL Examine.
    # Re-opening the MWL row would create another study with the same UID.
    patient_ready = False
    last_error = None
    for _ in range(8):
        try:
            patient_ready = flows.ensure_patient_screen(ui)
        except Exception as exc:
            last_error = exc
        if patient_ready:
            break
        time.sleep(1)
    if not patient_ready:
        raise RuntimeError(
            f"Could not enter Patient screen after login: {last_error}")
    overlay_fields = ensure_tc01_overlay(ui, ctx.db)
    if not flows.open_main_menu(ui):
        raise RuntimeError("Viewer main menu did not open")
    view = [c for c in ui.by_id(flows.MAIN_MENU["item_view"])
            if c.visible and c.rect[2] - c.rect[0] > 20]
    if not view:
        raise RuntimeError("View menu item not found")
    ui.click(view[0], settle=5)

    field = [c for c in ui.by_id(2177) if c.visible]
    search = [c for c in ui.by_id(2178) if c.visible]
    button = [c for c in ui.by_id(2179) if c.visible]
    if not field or not search or not button:
        raise RuntimeError("View search controls not found")
    ui.click(field[0], settle=.5)
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    items, seen = [], set()
    for c in children(popups[0].hwnd, 3):
        if c.text == "TextButton" and c.visible and c.hwnd not in seen:
            seen.add(c.hwnd); items.append(c)
    patient_id_item = [c for c in items if c.ctrl_id == 2]
    if not patient_id_item:
        raise RuntimeError("Patient ID search option not found")
    ui.click(patient_id_item[0], settle=.5)
    ui.set_text(search[0], patient_id)
    ui.click(button[0], settle=3)

    study_list = [c for c in ui.by_id(2199) if c.visible]
    rows, seen = [], set()
    for c in children(study_list[0].hwnd, 4) if study_list else []:
        if c.text == "StudyListItem" and c.visible and c.hwnd not in seen:
            seen.add(c.hwnd); rows.append(c)
    if not rows:
        raise RuntimeError(f"View search returned no rows: {patient_id}")
    # View cards are newest-first.  The completed fixture is the oldest card;
    # any newer blank duplicate is intentionally ignored.
    ui.click(sorted(rows, key=lambda c: (c.rect[1], c.rect[0]))[-1], settle=1)
    open_button = [c for c in ui.by_id(2182) if c.visible]
    if not open_button:
        raise RuntimeError("View button not found")
    ui.click(open_button[0], settle=8)
    steps = flows.step_items(ui)
    if len(steps) != 2:
        raise RuntimeError(f"Fixture must expose exactly 2 acquired steps; actual={len(steps)}")
    return {"ui": ui, "study_key": row["Key"], "patient_id": patient_id,
            "step_2d": 1, "step_3d": 2, "initial_steps": 2,
            "overlay_fields": overlay_fields, "instances": instance_rows}


def _visible(ui, ctrl_id):
    return [c for c in ui.by_id(ctrl_id) if c.visible]


def expand_tools(ui):
    if not _visible(ui, POST_RECON) or not _visible(ui, XIPL_TOOL):
        ui.click(_visible(ui, EXPAND_TOOLS)[0], settle=1)


def select_2d(ui, index):
    flows.select_step(ui, index)
    time.sleep(1)


def select_3d_raw(ui, index):
    flows.select_step(ui, index)
    time.sleep(1)
    raw = _visible(ui, 2122)
    if raw:
        ui.click(raw[0], settle=1)


def open_process(ui):
    ui.click(_visible(ui, PROC)[0], settle=2)
    if not _visible(ui, PARAM_COMBO):
        raise RuntimeError("Viewer Image Processing window did not open")


def open_post_reconstruction(ui):
    expand_tools(ui)
    ui.click(_visible(ui, POST_RECON)[0], settle=3)
    if not _visible(ui, PARAM_COMBO) or not _visible(ui, 2043):
        raise RuntimeError("Viewer Post Reconstruction window did not open")


def _parameter_name_key(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _ocr_parameter_row(control):
    """Return OCR candidates for one visible Parameter dropdown row."""
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for Parameter selection") from exc
    if os.path.exists(TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    image = ImageGrab.grab(bbox=control.rect, all_screens=True).convert("RGB")
    gray = ImageOps.autocontrast(ImageOps.grayscale(image))
    variants = [gray]
    variants.extend(gray.point(lambda p, cut=cut: 255 if p >= cut else 0)
                    for cut in (120, 160, 200))
    out = []
    for variant in variants:
        scaled = variant.resize((variant.width * 5, variant.height * 5),
                                Image.Resampling.LANCZOS)
        text = pytesseract.image_to_string(
            scaled,
            config=("--psm 7 "
                    "-c tessedit_char_whitelist="
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"))
        text = text.strip()
        if text and text not in out:
            out.append(text)
    return out


def _parameter_popup_rows(ui, popup):
    """Only rows geometrically contained by the open ItemList popup."""
    pl, pt, pr, pb = popup.rect
    seen, rows = set(), []
    for c in children(popup.hwnd, 4):
        l, t, r, b = c.rect
        if (c.text == "TextButton" and c.visible and c.hwnd not in seen
                and l >= pl and r <= pr and t >= pt and b <= pb
                and r - l >= 80 and b - t >= 18):
            seen.add(c.hwnd)
            rows.append(c)
    return sorted(rows, key=lambda c: c.rect[1])


def select_test_parameter(ui, expected_name):
    """OCR the dropdown and click only the row matching *expected_name*.

    Additional parameter files can change both list length and ordering.  No
    row index is assumed: visible rows are read, the popup is scrolled when
    necessary, and a click occurs only for an unambiguous filename match.
    """
    ui.click(_visible(ui, REFRESH)[0], settle=1)
    expected_key = _parameter_name_key(expected_name)
    pages_seen = set()
    observations = []
    ui.click(_visible(ui, PARAM_COMBO)[0], settle=.5)
    # Stop on a repeated OCR page, not on a small fixed item count.  The high
    # ceiling only guards against a pathological custom list that never
    # reports the same page while refusing to reach its end.
    for _ in range(100):
        popups = [w for w in ui.windows() if w.text == "ItemList"]
        if not popups:
            raise RuntimeError("Parameter list did not open")
        popup = popups[0]
        rows = _parameter_popup_rows(ui, popup)
        if not rows:
            ui.key("ESC", settle=.2)
            raise RuntimeError("No Parameter rows were found inside ItemList")

        scored = []
        page_text = []
        for row in rows:
            texts = _ocr_parameter_row(row)
            page_text.extend(texts)
            for text in texts:
                key = _parameter_name_key(text)
                score = SequenceMatcher(None, expected_key, key).ratio()
                scored.append((score, key == expected_key, row, text))
        observations.append(page_text)
        exact = [x for x in scored if x[1]]
        if len({x[2].hwnd for x in exact}) == 1:
            target = exact[0][2]
            ui.click(target, settle=1)
            return ui.combo_value(_visible(ui, PARAM_COMBO)[0]) or expected_name

        # OCR may confuse one character (e.g. D/0). Accept only one strong
        # candidate with a clear margin over every other row.
        ranked = sorted(scored, key=lambda x: x[0], reverse=True)
        if ranked and ranked[0][0] >= .88:
            runner_up = next((x for x in ranked[1:]
                              if x[2].hwnd != ranked[0][2].hwnd), None)
            if not runner_up or ranked[0][0] - runner_up[0] >= .08:
                ui.click(ranked[0][2], settle=1)
                return ui.combo_value(_visible(ui, PARAM_COMBO)[0]) or expected_name

        signature = tuple(sorted(_parameter_name_key(x) for x in page_text))
        if signature in pages_seen:
            ui.key("ESC", settle=.2)
            break
        pages_seen.add(signature)
        # Keep the list open while scrolling; clicking the combo again at the
        # top of the next loop would close it, so scroll now and OCR directly.
        ui.wheel(((popup.rect[0] + popup.rect[2]) // 2,
                  (popup.rect[1] + popup.rect[3]) // 2), -5, settle=.7)
    raise RuntimeError(
        f"Parameter {expected_name!r} was not recognized in the dropdown; "
        f"OCR pages={observations}")


def increment_slider(ui, slider_id):
    slider = _visible(ui, slider_id)[0]
    plus = [c for c in children(slider.hwnd, 2) if c.ctrl_id == 2 and c.visible]
    if not plus:
        raise RuntimeError(f"Slider {slider_id} + button not found")
    ui.click(plus[0], settle=1)


def shift_slider(ui, slider_id, direction, clicks=8):
    """Move a parameter strongly using only its bounded +/- UI buttons."""
    slider = _visible(ui, slider_id)[0]
    button_id = 2 if direction == "+" else 1
    buttons = [c for c in children(slider.hwnd, 2)
               if c.ctrl_id == button_id and c.visible]
    if not buttons:
        raise RuntimeError(f"Slider {slider_id} {direction} button not found")
    for _ in range(clicks):
        ui.click(buttons[0], settle=.12)


def _slider_value_bbox(slider):
    """Locate the custom-drawn numeric value area from +/- geometry."""
    buttons = {c.ctrl_id: c for c in children(slider.hwnd, 2)
               if c.ctrl_id in (1, 2) and c.visible}
    if 1 not in buttons or 2 not in buttons:
        raise RuntimeError(f"Slider {slider.ctrl_id} +/- buttons not found")
    l, t, r, b = slider.rect
    minus, plus = buttons[1], buttons[2]
    left_gap = minus.rect[0] - l
    right_gap = r - plus.rect[2]
    if left_gap >= right_gap and left_gap >= 12:
        return (l, t, minus.rect[0], b)
    if right_gap >= 12:
        return (plus.rect[2], t, r, b)
    raise RuntimeError(
        f"Slider {slider.ctrl_id} numeric value area not found: rect={slider.rect}")


def _ocr_integer(image):
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for XIPL value verification") from exc
    if os.path.exists(TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    elif not shutil.which("tesseract"):
        raise RuntimeError(f"Tesseract executable not found: {TESSERACT_EXE}")

    gray = ImageOps.autocontrast(ImageOps.grayscale(image))
    gray = gray.resize((max(1, gray.width * 6), max(1, gray.height * 6)),
                       Image.Resampling.LANCZOS)
    variants = [gray, gray.point(lambda p: 0 if p < 190 else 255)]
    texts = []
    for candidate in variants:
        text = pytesseract.image_to_string(
            candidate,
            config="--psm 7 -c tessedit_char_whitelist=0123456789").strip()
        texts.append(text)
        hits = re.findall(r"\d+", text)
        if len(hits) == 1:
            value = int(hits[0])
            if 0 <= value <= 100:
                return value
    raise RuntimeError(f"Slider value OCR failed: {texts}")


def read_slider_value(ui, slider_id):
    slider = _visible(ui, slider_id)
    if not slider:
        raise RuntimeError(f"Slider {slider_id} is not visible")
    image = ImageGrab.grab(bbox=_slider_value_bbox(slider[0]), all_screens=True)
    return _ocr_integer(image)


def _pink_count(control):
    # Capture the absolute bbox directly. Cropping an all-screens composite is
    # wrong on multi-monitor desktops whose virtual origin is not (0, 0).
    crop = ImageGrab.grab(bbox=control.rect, all_screens=True).convert("RGB")
    return sum(1 for red, green, blue in crop.getdata()
               if red >= 175 and green <= 150 and blue <= 190
               and red >= green + 45)


def read_radio_choice(ui, use_id, not_use_id):
    use = _visible(ui, use_id)
    not_use = _visible(ui, not_use_id)
    if not use or not not_use:
        raise RuntimeError(f"Radio controls are not visible: {use_id}/{not_use_id}")
    counts = {"Use": _pink_count(use[0]),
              "Not use": _pink_count(not_use[0])}
    if counts["Use"] == counts["Not use"]:
        raise RuntimeError(f"Radio selection could not be distinguished: {counts}")
    return max(counts, key=counts.get)


def read_2d_parameter_state(ui):
    """Read every 2D value rendered in the Image Processing window."""
    return {name: read_slider_value(ui, slider_id)
            for slider_id, name in SLIDER_NAMES_2D.items()}


def read_3d_parameter_state(ui):
    """Read Background Masking plus every Recon/Syn numeric value."""
    state = {
        "Recon.Background Masking": read_radio_choice(ui, 2041, 2042),
        "Syn.Background Masking": read_radio_choice(ui, 2047, 2048),
    }
    state.update({name: read_slider_value(ui, slider_id)
                  for slider_id, name in SLIDER_NAMES_3D.items()})
    return state


def change_all_2d_parameters(ui):
    """Give every 2D parameter a conspicuous, non-default value."""
    changes = [(2057, "+", 8),   # Contrast
               (2058, "-", 8),   # Sharpness
               (2059, "+", 8),   # Brightness
               (2060, "-", 10),  # Tone type
               (2061, "+", 8)]   # Noise reduction
    for slider_id, direction, clicks in changes:
        shift_slider(ui, slider_id, direction, clicks)
    return changes


def change_all_3d_parameters(ui):
    """Change Background Masking and every Recon/Syn parameter strongly."""
    # Flip Background Masking to Not use for both output types.
    ui.click(_visible(ui, 2042)[0], settle=.4)
    ui.click(_visible(ui, 2048)[0], settle=.4)
    changes = [
        (2043, "+", 8), (2044, "-", 8),
        (2045, "+", 8), (2046, "-", 10),
        (2049, "-", 8), (2050, "+", 8),
        (2051, "-", 8), (2052, "-", 10),
    ]
    for slider_id, direction, clicks in changes:
        shift_slider(ui, slider_id, direction, clicks)
    return changes


def preview_and_apply(ui, preview_wait, apply_wait):
    ui.click(_visible(ui, PREVIEW)[0], settle=1)
    time.sleep(preview_wait)
    if not _visible(ui, APPLY):
        raise RuntimeError("Apply button unavailable after Preview")
    ui.click(_visible(ui, APPLY)[0], settle=1)
    time.sleep(apply_wait)
    return not _visible(ui, APPLY)


def cancel_window(ui):
    hits = _visible(ui, CANCEL)
    if hits:
        ui.click(hits[0], settle=1)
