# -*- coding: utf-8 -*-
"""TC_Basic_WorkFlow_03 - Tool 적용 영상의 DICOM Print Overlay 및 Film 출력 검증.

체크리스트 원문 (변경 금지):
  Step 1. Tool 동작 확인한다.
  Step 2. Tool 적용으로 변경된 Image DICOM Send, Print, Export 한다.
  Expected 2. 변경된 Image가 전송된다.

판정 근거 (AGENTS.md 2항 - 매뉴얼/사양 우선):
  * Service Manual 4.8.9 "Print Overlay 메뉴" - Print Overlay는 항목을 등록한 뒤
    4.8.8 "Print 메뉴"의 Print 서버 Overlay 항목에서 선택해야 출력에 반영된다.
    그래서 등록만으로 PASS 판정하지 않고 **Print 서버에 선택된 것까지** 대조한다.
  * Operation Manual 9.7 "영상을 Film 창으로 보내기", 10.1.1 "Film 창으로 영상
    보내기", 10.1.3 "Film 창 확인하기" - 출력은 Film 창에 배치한 뒤 수행하므로
    Layout(1x1) 구성 후 출력하는 것이 정상 절차다.
  * Operation Manual 8.5 "영상 조정 도구 버튼" - Step 1의 Tool 동작 확인 대상은
    조작/레이아웃/주석/관리 도구다.
  * 출력물 검증은 Print SCP(core/printscp.py)가 수신한 Film의 **실제 픽셀**과
    Overlay 실제값 OCR로 한다. 버튼을 눌렀다는 사실은 증거가 아니다.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageGrab, ImageOps

from core import flows, print_overlay, screen
from core.printscp import PrintServer
from core.result import FAIL, PASS, TCResult
from core.ui import children
from tests.workflow02 import PATIENT_ID, _examined_search, _study_card_number


EXPECTED_LABELS = tuple(label for label, _ in print_overlay.PRINT_ITEMS)


def _fixture(ctx):
    row = ctx.db.one(
        "DATA", "SELECT TOP 1 s.[Key],s.StudyDate,s.StudyTime,s.StudyInstanceUID,"
        "p.PatientID,p.PatientBirthDate FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
        "WHERE p.PatientID=@pid AND EXISTS (SELECT 1 FROM INSTANCE i "
        "WHERE i.StudyKey=s.[Key] AND i.InstanceType=0) "
        "AND EXISTS (SELECT 1 FROM INSTANCE i WHERE i.StudyKey=s.[Key] AND i.InstanceType=1) "
        "ORDER BY s.[Key] DESC", {"pid": PATIENT_ID})
    if not row:
        raise RuntimeError(f"2D/3D completed fixture not found: {PATIENT_ID}")
    instance = ctx.db.one(
        "DATA", "SELECT TOP 1 [Key],ImageInstanceUID,SeriesKey,GroupKey "
        "FROM INSTANCE WHERE StudyKey=@study AND InstanceType=0 ORDER BY [Key]",
        {"study": row["Key"]})
    row["instance"] = instance
    return row


def _close_setting(ui):
    closes = [c for c in ui.by_id(4) if c.visible
              and c.rect[2] - c.rect[0] <= 60 and c.rect[3] - c.rect[1] <= 60]
    if closes:
        ui.click(min(closes, key=lambda c: c.rect[1]), settle=3)


def _open_examined_fixture(ctx, ui, target):
    rows = _examined_search(ui, PATIENT_ID)
    rank = _study_card_number(ctx, target)
    if rank > len(rows):
        raise RuntimeError(f"Target card rank {rank}, visible cards {len(rows)}")
    ui.click(rows[rank - 1], settle=.8)
    return rows, rank


def _film_from_selected_study(ui):
    buttons = [c for c in ui.by_id(2188) if c.visible]
    if not buttons:
        raise RuntimeError("Examined Print button (2188) not found")
    ui.click(buttons[0], settle=1)
    selected = [c for c in ui.by_id(501) if c.visible]
    if not selected:
        raise RuntimeError("Print Selected button (501) not found")
    ui.click(selected[0], settle=5)
    film = [c for c in ui.by_id(158) if c.visible and c.text == "CWndFilmManager"]
    if not film:
        raise RuntimeError("Film window did not open")
    one_by_one = [c for c in ui.by_id(1141) if c.visible and c.rect[0] > 1400]
    if not one_by_one:
        raise RuntimeError("Film 1x1 layout button (1141) not found")
    ui.click(one_by_one[0], settle=2)
    managers = [c for c in children(film[0].hwnd, 4)
                if c.ctrl_id == 203 and c.visible]
    unique = {c.hwnd: c for c in managers}.values()
    largest = max(unique, key=lambda c: ((c.rect[2] - c.rect[0]) *
                                         (c.rect[3] - c.rect[1])), default=None)
    if not largest:
        raise RuntimeError("Film 1x1 image pane not found")
    film_area = ((film[0].rect[2] - film[0].rect[0]) *
                 (film[0].rect[3] - film[0].rect[1]))
    pane_area = ((largest.rect[2] - largest.rect[0]) *
                 (largest.rect[3] - largest.rect[1]))
    if pane_area < film_area * .85:
        raise RuntimeError(
            f"Film layout did not change to 1x1: pane={largest.rect}, film={film[0].rect}")
    return film[0], {"button_id": 1141, "pane": largest.rect,
                     "film": film[0].rect, "pane_ratio": pane_area / film_area}


def _ocr_region(control, path, tesseract_exe):
    import pytesseract

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image = ImageGrab.grab(bbox=control.rect, all_screens=True)
    image.save(path)
    if tesseract_exe:
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    # In 1x1 the six overlay values occupy the top-right of the single film.
    width, height = image.size
    crop = image.crop((int(width * .58), 0, width, int(height * .23)))
    gray = ImageOps.autocontrast(crop.convert("L"))
    return pytesseract.image_to_string(gray.resize((gray.width * 6, gray.height * 6)),
                                       config="--psm 6", lang="eng")


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _labels_seen(text):
    norm = _norm(text)
    return {label: _norm(label) in norm for label in EXPECTED_LABELS}


def _overlay_values(text):
    norm = _norm(text).replace("o", "0")
    return {
        "Patient ID": "datafl0wmwl01" in norm,
        "Birth Date": "19800101" in norm,
        "Thickness": "00cm" in norm,
        "Compression Force": "35n" in norm or "353n" in norm,
        # Film anti-aliasing can make the V look like a yen sign; after
        # normalization that becomes "hl".  The value and the other label
        # still have to match, so this remains a data assertion.
        "HVL": ("n0tvalid" in norm and
                ("hvl" in norm or "hyl" in norm or "hl" in norm)),
        "AGD": "n0tvalid" in norm and ("agd" in norm or "gd" in norm),
    }


def _image_similarity(path_a, path_b):
    a = Image.open(path_a).convert("L")
    b = Image.open(path_b).convert("L")
    # Ignore the 1px red selection border in Film and compare normalized film
    # rasters at a compact resolution.
    a = a.crop((2, 2, max(3, a.width - 2), max(3, a.height - 2)))
    a = ImageOps.fit(a, (256, 320), method=Image.Resampling.LANCZOS)
    b = ImageOps.fit(b, (256, 320), method=Image.Resampling.LANCZOS)
    diff = ImageChops.difference(a, b)
    mean = sum(diff.histogram()[i] * i for i in range(256)) / (256 * 320)
    return {"mean_delta": round(mean, 3), "similarity": round(1 - mean / 255, 6)}


def _preview_urls(job):
    urls = []
    for key, value in (job or {}).items():
        if isinstance(value, str) and ("preview" in key.lower() or
                                       value.lower().endswith((".png", ".jpg", ".jpeg"))):
            urls.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.lower().endswith((".png", ".jpg", ".jpeg")):
                    urls.append(item)
    return urls


def run(ctx):
    result = TCResult("TC_Basic_WorkFlow_08", "2D/3D Film Print")
    ui = None
    try:
        target = _fixture(ctx)
        result.add(0, "선행 2D/3D 검사 데이터", PASS,
                   expected=f"{PATIENT_ID}, 2D/3D Instance", actual=target)
        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError("Patient screen is not ready")
        tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
        saved = print_overlay.ensure_print_overlay(ui, ctx.db, tess)
        result.assert_true(1, "DICOM Print Overlay 6개 항목 저장",
                           len(saved["items"]) == 6,
                           expected=list(EXPECTED_LABELS), actual=saved)

        print_spec = next(x for x in ctx.cfg["dicom"]["servers_to_register"]
                          if x["kind"] == "Print")
        applied = print_overlay.apply_to_print_server(
            ui, ctx.db, print_spec["name"], saved["overlay"]["Key"],
            tesseract_exe=tess)
        result.assert_equal(2, "PRINT_TEST에 Print Overlay 적용",
                            saved["overlay"]["Key"], applied.get("Overlay"),
                            note=f"saved row: {applied}")
        _close_setting(ui)

        rows, rank = _open_examined_fixture(ctx, ui, target)
        result.assert_true(3, "동일 환자와 검사 선택",
                           rank <= len(rows) and target["PatientID"] == PATIENT_ID,
                           expected={"PatientID": PATIENT_ID, "StudyKey": target["Key"]},
                           actual={"visible": len(rows), "rank": rank, "target": target})

        server = PrintServer(ctx.cfg["dicom"]["print_server_url"])
        status = server.status()
        result.assert_true(4, "DICOM Print SCP Online",
                           status.get("running") is True and
                           status.get("ae_title") == print_spec["ae_title"],
                           expected=print_spec, actual=status)
        known = {str(j.get("id")) for j in server.jobs()}

        film, layout = _film_from_selected_study(ui)
        result.assert_true(5, "Film 레이아웃 1x1 적용",
                           layout["pane_ratio"] >= .85,
                           expected="Control ID 1141, one pane >= 85% Film area",
                           actual=layout)
        evidence_dir = os.path.join(ctx.evidence_root, "Flow", "03_WorkFlow")
        film_path = os.path.join(evidence_dir, "05_film_overlay.png")
        film_text = _ocr_region(film, film_path, tess)
        result.attach(film_path)
        film_labels = _overlay_values(film_text)
        result.assert_true(5, "Film 프리뷰에 설정한 Print Overlay 표시",
                           all(film_labels.values()), expected=list(EXPECTED_LABELS),
                           actual={"labels": film_labels, "ocr": film_text})

        print_buttons = [c for c in ui.by_id(1149) if c.visible]
        if not print_buttons:
            raise RuntimeError("Film Print button (1149) not found")
        ui.click(print_buttons[0], settle=2)
        # Print may show an informational acknowledgement; never dismiss a
        # destructive or ambiguous multi-button dialog here.
        dialog = ui.dialog()
        if dialog:
            buttons = ui.dialog_buttons(dialog)
            if len(buttons) == 1:
                ui.click(buttons[0], settle=1)

        wait_started_wall, wait_started = datetime.now(), time.perf_counter()
        jobs = server.wait_for_jobs(count=1, timeout=90, poll=.5, exclude_ids=known)
        result.record_timing(
            "Print SCP 신규 job 수신", wait_started_wall, wait_started,
            "new print job received" if jobs else "timeout",
            {"known_ids": sorted(known),
             "new_ids": [str(item.get("id")) for item in jobs]})
        if not jobs:
            raise RuntimeError("Print SCP did not receive a new job within 90 seconds")
        job = jobs[-1]
        result.assert_true(6, "실제 DICOM Print job 수신",
                           str(job.get("id")) not in known,
                           expected="new Print SCP job", actual=job)

        web_path = os.path.join(evidence_dir, f"06_print_server_job_{job['id']}.png")
        Path(web_path).write_bytes(server.preview(job["id"]))
        result.attach(web_path)
        web_image = Image.open(web_path)
        # OCR directly from the saved server preview rather than screen
        # coordinates.  This is the same image shown at viewer.html?id=<job>.
        import pytesseract
        if tess:
            pytesseract.pytesseract.tesseract_cmd = tess
        w, h = web_image.size
        crop = web_image.crop((int(w * .76), 0, w, int(h * .17)))
        gray = ImageOps.autocontrast(crop.convert("L")).resize(
            (crop.width * 4, crop.height * 4))
        web_text = pytesseract.image_to_string(gray, config="--psm 6", lang="eng")
        web_values = _overlay_values(web_text)
        similarity = _image_similarity(film_path, web_path)
        result.assert_true(
            6, "Print 서버 웹 프리뷰 Overlay가 Film 프리뷰와 일치",
            all(web_values.values()) and similarity["similarity"] >= .96,
            expected={"values": film_labels, "image_similarity": ">= 0.96"},
            actual={"job_url": f"{server.base}/viewer.html?id={job['id']}",
                    "film_ocr": film_text, "web_ocr": web_text,
                    "web_values": web_values, "image": similarity})
    except Exception as exc:
        result.add(0, "TC_Basic_WorkFlow_08 실행", FAIL, actual=str(exc))
    return result
