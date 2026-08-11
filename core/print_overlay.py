# -*- coding: utf-8 -*-
"""Bellalun DICOM Print Overlay configuration helpers.

The catalogue is custom-drawn, so Win32 exposes each row as ``ListItem``
without its label.  Selection therefore uses the stable list/control IDs and
verifies the row text with OCR before clicking it.
"""

from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

from PIL import ImageGrab, ImageOps

from . import flows
from .ui import children


OVERLAY_NAME = "TC_WF03_OVERLAY"

# Catalogue indexes observed in Bellalun 1.0.12.105.  OCR verification below
# deliberately fails closed if another build changes the order.
PRINT_ITEMS = (
    ("Patient ID", 0),
    ("Birth Date", 2),
    ("Thickness", 34),
    ("Compression Force", 35),
    ("HVL", 36),
    ("AGD", 37),
)


def _visible(ui, control_id):
    return [c for c in ui.by_id(control_id) if c.visible]


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _ocr(control, tesseract_exe):
    import pytesseract

    if tesseract_exe:
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    image = ImageGrab.grab(bbox=control.rect, all_screens=True).convert("L")
    image = ImageOps.autocontrast(image).resize((image.width * 3, image.height * 3))
    return pytesseract.image_to_string(image, config="--psm 7", lang="eng").strip()


def _catalogue_row(ui, list_id, index, expected, tesseract_exe):
    lists = _visible(ui, list_id)
    if not lists:
        raise RuntimeError(f"Print Overlay catalogue control {list_id} not found")
    catalogue = lists[0]
    nested = children(catalogue.hwnd, 5)
    scrolls = [c for c in nested if c.text == "Scroll" and c.visible]
    if not scrolls:
        raise RuntimeError("Print Overlay catalogue scroll control not found")
    arrows = children(scrolls[0].hwnd, 2)
    up = [c for c in arrows if c.ctrl_id == 1 and c.visible]
    down = [c for c in arrows if c.ctrl_id == 2 and c.visible]
    if not up or not down:
        raise RuntimeError("Print Overlay catalogue scroll arrows not found")

    # Always return to a known origin.  A no-op click at the limit is safe.
    for _ in range(50):
        ui.click(up[0], settle=.015)

    rows = sorted({c.hwnd: c for c in children(catalogue.hwnd, 5)
                   if c.text == "ListItem" and c.visible}.values(),
                  key=lambda c: c.rect[1])
    if not rows:
        raise RuntimeError("Print Overlay catalogue has no visible rows")
    # Bellalun's custom scrollbar does not move exactly one row per arrow
    # click.  For lower catalogue entries, jump to the bottom through the
    # scroll track and identify the intended visible row by OCR.
    if index >= len(rows):
        l, t, r, b = catalogue.rect
        for _ in range(12):
            ui.click((r - 8, b - 25), settle=.08)
    rows = sorted({c.hwnd: c for c in children(catalogue.hwnd, 5)
                   if c.text == "ListItem" and c.visible}.values(),
                  key=lambda c: c.rect[1])
    candidates = []
    for row in rows:
        observed = _ocr(row, tesseract_exe)
        score = SequenceMatcher(None, _norm(expected), _norm(observed)).ratio()
        if _norm(expected) and _norm(expected) in _norm(observed):
            score = 1.0
        # At the native 35px row height Tesseract consistently reads the
        # leading H in HVL as A.  Keep this narrow and explicit; do not relax
        # the threshold for other catalogue labels.
        if _norm(expected) == "hvl" and _norm(observed).startswith("avl"):
            score = 1.0
        candidates.append((score, row, observed))
    score, row, observed = max(candidates, key=lambda item: item[0])
    if score < .72:
        raise RuntimeError(
            f"Print Overlay item not found: expected={expected!r}, "
            f"best OCR={observed!r}, score={score:.3f}")
    return row, observed


def _saved(db, name=OVERLAY_NAME):
    overlay = db.one(
        "CONFIGURATION", "SELECT * FROM PRINT_OVERLAY WHERE Name=@name",
        {"name": name})
    if not overlay:
        return None
    items = db.query(
        "CONFIGURATION", "SELECT PrintOverlayKey,Position,FieldID,[Order] "
        "FROM PRINT_OVERLAY_ITEM WHERE PrintOverlayKey=@key "
        "ORDER BY Position,[Order]", {"key": overlay["Key"]})
    return {"overlay": overlay, "items": items}


def ensure_print_overlay(ui, db, tesseract_exe, name=OVERLAY_NAME):
    """Create the six-item TC overlay through Setting > DICOM > Print Overlay."""
    current = _saved(db, name)
    if current and len(current["items"]) == len(PRINT_ITEMS):
        return current

    flows.open_dicom_setting(ui, "print_overlay", wait=3)
    if current:
        rows = sorted({c.hwnd: c for c in children(_visible(ui, 2485)[0].hwnd, 4)
                       if c.text == "ListItem" and c.visible}.values(),
                      key=lambda c: c.rect[1])
        if not rows:
            raise RuntimeError(f"Saved Print Overlay is not selectable: {name}")
        ui.click(rows[0], settle=.5)
        # A partially configured named overlay is not silently duplicated.
        raise RuntimeError(
            f"Print Overlay {name} exists with {len(current['items'])} items; "
            "manual review is required before replacing it")

    add = _visible(ui, 2431)
    name_edit = _visible(ui, 2490)
    add_top = _visible(ui, 2503)
    if not add or not name_edit or not add_top:
        raise RuntimeError("Print Overlay add/name/top controls not found")
    ui.click(add[0], settle=.8)
    ui.type_text(name_edit[0], name, clear=True, settle=.5)

    selected = []
    for label, index in PRINT_ITEMS:
        row, observed = _catalogue_row(ui, 2489, index, label, tesseract_exe)
        ui.click(row, settle=.2)
        ui.click(add_top[0], settle=.5)
        if ui.dialog():
            message = ui.dismiss_dialog(timeout=2)
            raise RuntimeError(f"Failed to add Print Overlay item {label}: {message}")
        selected.append({"label": label, "catalogue_index": index, "ocr": observed})

    flows.setting_update(ui, wait=3)
    if ui.dialog():
        ui.dismiss_dialog(timeout=2)
    end = time.time() + 10
    saved = _saved(db, name)
    while time.time() < end and (not saved or len(saved["items"]) != len(PRINT_ITEMS)):
        time.sleep(1)
        saved = _saved(db, name)
    if not saved or len(saved["items"]) != len(PRINT_ITEMS):
        raise RuntimeError(f"Print Overlay was not saved completely: {saved}")
    saved["selected"] = selected
    return saved


def apply_to_print_server(ui, db, print_name, overlay_key,
                          overlay_name=OVERLAY_NAME, tesseract_exe=None):
    """Select the saved overlay on the named DICOM Print server and persist it."""
    flows.open_dicom_setting(ui, "print", wait=2)
    server_list = _visible(ui, 2429)
    if not server_list:
        raise RuntimeError("DICOM Print SCP list not found")
    rows = sorted({c.hwnd: c for c in children(server_list[0].hwnd, 5)
                   if c.text == "ListItem" and c.visible}.values(),
                  key=lambda c: c.rect[1])
    if not rows:
        raise RuntimeError(f"DICOM Print server is not visible: {print_name}")
    ui.click(rows[0], settle=.6)
    combo = _visible(ui, 2474)
    if not combo:
        raise RuntimeError("DICOM Print Overlay selector (2474) not found")
    ui.click(combo[0], settle=.4)
    popups = [w for w in ui.windows() if w.text == "ItemList"]
    options = []
    for c in children(popups[-1].hwnd, 4) if popups else []:
        if c.text == "TextButton" and c.visible:
            options.append(c)
    options = sorted({c.hwnd: c for c in options}.values(), key=lambda c: c.rect[1])
    # TextButton IDs are the current dropdown ordinal, not PRINT_OVERLAY.Key.
    # Read the rendered labels and select the configured overlay by name.
    observed = [(c, _ocr(c, tesseract_exe)) for c in options]
    scored = [(SequenceMatcher(None, _norm(overlay_name), _norm(label)).ratio(),
               c, label) for c, label in observed]
    best = max(scored, default=(0.0, None, ""), key=lambda item: item[0])
    exact = [best[1]] if best[0] >= .85 else []
    if not exact:
        raise RuntimeError(
            f"Print Overlay dropdown has no named item {overlay_name!r}; "
            f"available={[(c.ctrl_id, label) for c, label in observed]}, "
            f"best_score={best[0]:.3f}")
    ui.click(exact[0], settle=.5)
    flows.setting_update(ui, wait=3)
    if ui.dialog():
        ui.dismiss_dialog(timeout=2)
    row = db.one(
        "CONFIGURATION", "SELECT p.[Key],p.Name,d.Overlay FROM DICOM_PRINT p "
        "JOIN DICOM_PRINT_DICOM d ON d.PrintKey=p.[Key] WHERE p.Name=@name",
        {"name": print_name}) or {}
    if int(row.get("Overlay", -1)) != int(overlay_key):
        raise RuntimeError(
            f"Print server overlay was not applied: expected={overlay_key}, actual={row}")
    return row
