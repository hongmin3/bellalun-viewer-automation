# -*- coding: utf-8 -*-
"""Bellalun Viewer 2D/3D 영상 Tool 조작과 화면 변화 판정."""

import os
import re
import time

from PIL import Image, ImageChops, ImageGrab, ImageStat


EXPAND_TOOLS = 1163
TOOL_WINDOW_LEVEL = 1115
TOOL_ZOOM = 1113
TOOL_PAN = 1114
TOOL_ARROW = 1130
TYPE_RECON = 2123


def _visible(ui, ctrl_id):
    return [c for c in ui.by_id(ctrl_id)
            if c.visible and c.rect[2] - c.rect[0] >= 12
            and c.rect[3] - c.rect[1] >= 12]


def ensure_expanded(ui):
    """W/L과 Annotation 도구가 보이도록 Tool 패널을 펼친다."""
    if _visible(ui, TOOL_WINDOW_LEVEL) and _visible(ui, TOOL_ARROW):
        return
    expand = _visible(ui, EXPAND_TOOLS)
    if not expand:
        raise RuntimeError("Tool 확장 버튼(1163)을 찾지 못했습니다.")
    ui.click(expand[0], settle=1)
    if not _visible(ui, TOOL_WINDOW_LEVEL) or not _visible(ui, TOOL_ARROW):
        raise RuntimeError("Tool 패널을 펼친 뒤 W/L 또는 Annotation 도구가 없습니다.")


def ensure_collapsed(ui):
    """영상 변화 기준 캡처를 위해 확장 Tool 패널을 접는다."""
    if not _visible(ui, TOOL_WINDOW_LEVEL):
        return
    expand = _visible(ui, EXPAND_TOOLS)
    if not expand:
        raise RuntimeError("Tool 확장 버튼(1163)을 찾지 못했습니다.")
    ui.click(expand[0], settle=1)
    if _visible(ui, TOOL_WINDOW_LEVEL):
        raise RuntimeError("Tool 패널이 접히지 않았습니다.")


def image_bbox(ui, pane="left"):
    """선택 영상 pane의 Viewer 창 상대 영역."""
    win = ui.main_window()
    if not win:
        raise RuntimeError("Viewer 주 창을 찾지 못했습니다.")
    left, top, right, bottom = win.rect
    width, height = right - left, bottom - top
    if width < 1200 or height < 700:
        raise RuntimeError(f"Viewer 창 크기가 예상보다 작습니다: {win.rect}")
    if pane == "left":
        x1, x2 = .01, .37
    elif pane == "right":
        x1, x2 = .38, .74
    else:
        raise RuntimeError(f"알 수 없는 영상 pane: {pane}")
    return (left + int(width * x1), top + int(height * .07),
            left + int(width * x2), top + int(height * .94))


def capture_viewer(ui, path):
    win = ui.main_window()
    if not win:
        raise RuntimeError("Viewer 주 창을 찾지 못했습니다.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ImageGrab.grab(bbox=win.rect, all_screens=True).save(path)
    return path


def _capture_pane(ui, path, pane):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ImageGrab.grab(bbox=image_bbox(ui, pane), all_screens=True).save(path)
    return path


def visual_delta(before_path, after_path, threshold=12):
    before = Image.open(before_path).convert("RGB")
    after = Image.open(after_path).convert("RGB")
    diff = ImageChops.difference(before, after).convert("L")
    hist = diff.histogram()
    total = max(1, sum(hist))
    changed = sum(hist[threshold + 1:])
    return {
        "mean_delta": round(ImageStat.Stat(diff).mean[0], 3),
        "changed_ratio": round(changed / total, 6),
    }


def _point(bbox, x_ratio, y_ratio):
    left, top, right, bottom = bbox
    return (left + int((right - left) * x_ratio),
            top + int((bottom - top) * y_ratio))


def _optional_wl_ocr(path, pane="left"):
    if pane == "right":
        try:
            import pytesseract
            image = Image.open(path).convert("RGB")
            width, height = image.size
            crop = image.crop((int(width * .62), int(height * .23),
                               int(width * .74), int(height * .42)))
            crop = crop.resize((crop.width * 5, crop.height * 5),
                               Image.Resampling.LANCZOS)
            text = pytesseract.image_to_string(
                crop, config="--psm 6 -c tessedit_char_whitelist=Ww0123456789: ")
            pairs = re.findall(
                r"W[1lI]\s*[:;]?\s*(\d+?)\s*W2\s*[:;]?\s*(\d+)", text, re.I)
            if not pairs:
                raise RuntimeError(f"right pane W1/W2 OCR failed: {text!r}")
            w1, w2 = pairs[0]
            return {"w1": int(w1), "w2": int(w2), "ocr": text.strip()}
        except Exception as exc:
            return {"error": str(exc), "pane": pane}
    try:
        from core.viewer_processing import read_viewer_w1_w2
        return read_viewer_w1_w2(path)
    except Exception as exc:
        return {"error": str(exc)}


def apply_tool_sequence(ui, evidence_dir, prefix, pane="left"):
    """W/L, Zoom, Pan, Arrow Annotation을 적용하고 화면 변화를 반환한다."""
    ensure_collapsed(ui)
    bbox = image_bbox(ui, pane)
    records = []

    base_full = capture_viewer(ui, os.path.join(evidence_dir, f"{prefix}_00_baseline.png"))
    previous = _capture_pane(
        ui, os.path.join(evidence_dir, f"{prefix}_00_pane.png"), pane)
    wl_before = _optional_wl_ocr(base_full, pane)

    if pane == "right":
        specs = [
            ("Window Level", TOOL_WINDOW_LEVEL, (.43, .58), (.57, .43), .0005),
            ("Pan", TOOL_PAN, (.25, .54), (.43, .54), .0005),
            ("Zoom", TOOL_ZOOM, (.48, .62), (.48, .42), .0010),
            ("Annotation (Arrow)", TOOL_ARROW, (.40, .38), (.58, .51), .00005),
        ]
    else:
        specs = [
            ("Window Level", TOOL_WINDOW_LEVEL, (.43, .58), (.57, .43), .0100),
            ("Zoom", TOOL_ZOOM, (.48, .62), (.48, .42), .0100),
            ("Pan", TOOL_PAN, (.43, .54), (.59, .54), .0060),
            ("Annotation (Arrow)", TOOL_ARROW, (.40, .38), (.58, .51), .00005),
        ]
    for index, (name, ctrl_id, start_ratio, end_ratio, min_ratio) in enumerate(specs, 1):
        if ctrl_id in (TOOL_WINDOW_LEVEL, TOOL_ARROW):
            ensure_expanded(ui)
        controls = _visible(ui, ctrl_id)
        if not controls:
            records.append({"name": name, "control_id": ctrl_id, "supported": False,
                            "passed": False, "error": "visible control not found"})
            continue
        ui.click(controls[0], settle=.5)
        ui.drag(_point(bbox, *start_ratio), _point(bbox, *end_ratio),
                duration=.8, settle=.8)
        time.sleep(.4)
        full_path = capture_viewer(
            ui, os.path.join(evidence_dir, f"{prefix}_{index:02d}_{name.split()[0].lower()}.png"))
        pane_path = _capture_pane(
            ui, os.path.join(evidence_dir, f"{prefix}_{index:02d}_pane.png"), pane)
        delta = visual_delta(previous, pane_path)
        passed = delta["changed_ratio"] >= min_ratio
        record = {"name": name, "control_id": ctrl_id, "supported": True,
                  "passed": passed, "minimum_changed_ratio": min_ratio,
                  "evidence": full_path, **delta}
        if name == "Window Level":
            # 사양(Service Manual "Window Level Option", Operation Manual
            # "W/L 사용하기")이 정의하는 W/L의 결과는 **W1/W2 값의 증가 또는
            # 감소**다. 화면 픽셀 변화율은 그 대리 지표일 뿐이라, 값이 분명히
            # 바뀌었는데도 변화가 임계값에 못 미쳐 FAIL로 뒤집히는 일이 있었다
            # (2026-08-18 실측: changed_ratio 0.0 인데 mean_delta 0.522).
            # 그래서 값 증감을 **주 판정**으로 쓰고, 값을 읽지 못한 경우에만
            # 픽셀 변화율로 판정한다.
            record["ocr_before"] = wl_before
            record["ocr_after"] = _optional_wl_ocr(full_path, pane)
            before_values = (wl_before.get("w1"), wl_before.get("w2"))
            after_values = (record["ocr_after"].get("w1"),
                            record["ocr_after"].get("w2"))
            if None not in before_values + after_values:
                changed = [
                    {"name": key, "before": before, "after": after,
                     "direction": "increase" if after > before
                                  else "decrease" if after < before else "same"}
                    for key, before, after in
                    (("W1", before_values[0], after_values[0]),
                     ("W2", before_values[1], after_values[1]))]
                record["window_level_values"] = changed
                record["verdict_basis"] = "W1/W2 값 증감(사양 기준)"
                record["passed"] = any(x["direction"] != "same" for x in changed)
            else:
                record["verdict_basis"] = (
                    "W1/W2 값을 읽지 못해 화면 변화율로 대체 판정 "
                    "(Overlay가 꺼져 있으면 값을 읽을 수 없다)")
        records.append(record)
        previous = pane_path
    return records


def select_recon(ui):
    recon = _visible(ui, TYPE_RECON)
    if not recon:
        raise RuntimeError("3D Recon 타입 버튼(2123)을 찾지 못했습니다.")
    ui.click(recon[0], settle=2)
    return recon[0]
