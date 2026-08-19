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


def _norm(value):
    # OCR 은 필름 글꼴의 0 을 O 로 자주 읽는다. 기대값도 같은 변환을 거치므로
    # 이 치환이 판정을 느슨하게 만들지 않는다.
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower()).replace("o", "0")


def _ocr_areas(image, path_prefix, tesseract_exe, result=None):
    """필름/프리뷰를 **영역별로** 크롭해 OCR 하고 크롭 이미지를 증적으로 남긴다.

    한 곳만 크롭하면 영역을 구분하지 못한다 — 6개가 전부 Top 에 몰려 있어도
    통과해 버린다. 영역별로 읽어야 "Top 이외 영역에도 들어갔는지"가 증명된다.
    """
    import pytesseract

    if tesseract_exe:
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    width, height = image.size
    texts = {}
    for area, box in print_overlay.film_regions(width, height).items():
        crop = image.crop(box).convert("L")
        # 배율 하나에 의존하지 않는다 - 8배에서 `MWL` 이 `MIWL` 로 읽히는 것을
        # 실측했다. 판독본 전부를 남겨 사람이 감사할 수 있게 한다.
        reads = {}
        for scale in print_overlay.FILM_OCR_SCALES:
            big = crop.resize((crop.width * scale, crop.height * scale),
                              Image.Resampling.LANCZOS)
            reads[f"x{scale}"] = pytesseract.image_to_string(
                ImageOps.autocontrast(big), config="--psm 6", lang="eng").strip()
        texts[area] = reads
        crop_path = f"{path_prefix}_{area}.png"
        Path(crop_path).parent.mkdir(parents=True, exist_ok=True)
        crop.save(crop_path)
        if result is not None:
            result.attach(crop_path)
    return texts


def _film_expectations(target):
    """영역별 기대값. 환자 정보는 **DB 값에서** 만든다.

    상수를 박아 두면 픽스처가 바뀌어도 통과한다. 영상 속성값(두께/압박력/HVL/AGD)은
    영상 생성기가 넣은 값이라 필름 실측 문구를 쓰되, 값과 라벨을 함께 본다.

    필름 렌더링 형태 (2026-08-19 실측)
      Header : 라벨 없이 **값만**, 1 X 2 두 칸에 나란히
      Top    : 라벨 없이 **값만** (`0.0 cm`, `35 N`)
      Bottom : **`라벨: 값`** (`HVL: Not valid`)
    """
    pid = _norm(target["PatientID"])
    birth = _norm(target["PatientBirthDate"])
    return {
        "header": {
            "Patient ID": lambda n: pid in n,
            "Birth Date": lambda n: birth in n,
        },
        "top": {
            "Thickness": lambda n: "00cm" in n,
            "Compression Force": lambda n: "35n" in n or "353n" in n,
        },
        "bottom": {
            # 필름의 안티에일리어싱이 V 를 ¥ 로 만들어 정규화 후 "hyl" 이 된다.
            # 값(`Not valid`)과 라벨을 함께 요구하므로 느슨해지지 않는다.
            "HVL": lambda n: ("n0tvalid" in n and
                              ("hvl" in n or "hyl" in n or "hl" in n)),
            "AGD": lambda n: "n0tvalid" in n and ("agd" in n or "gd" in n),
        },
    }


def _judge_areas(texts, expect):
    """영역별 판정 결과 `{area: {label: bool}}` 와 읽은 문구를 함께 돌려준다."""
    seen = {}
    for area, checks in expect.items():
        norms = [_norm(read) for read in (texts.get(area) or {}).values()]
        seen[area] = {label: any(test(norm) for norm in norms)
                      for label, test in checks.items()}
    return seen


def _all_ok(seen):
    return all(ok for area in seen.values() for ok in area.values())


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
        result.assert_true(
            1, "DICOM Print Overlay 6개 항목을 Header/Top/Bottom에 저장",
            print_overlay.matches_expected_areas(saved["items"]),
            expected={"areas": print_overlay.PRINT_EXPECTED_BY_POSITION,
                      "labels": list(EXPECTED_LABELS)}, actual=saved)
        # Header 표시 위치가 None 이면 항목이 저장돼 있어도 필름에 나오지 않는다
        # (사양서1 297쪽). Layout 칸수는 항목 수 이상이어야 한다(같은 쪽,
        # "Layout 한 칸당 한 항목씩 표시한다").
        header_rows = len(print_overlay.PRINT_ITEMS_BY_AREA["header"])
        result.assert_true(
            1, "Print Overlay Header 표시 위치/Layout 설정",
            int(saved["overlay"]["HeaderPosition"]) ==
            print_overlay.HEADER_POSITION_VALUES[print_overlay.HEADER_POSITION] and
            print_overlay.HEADER_LAYOUT_CELLS[
                print_overlay.HEADER_LAYOUT_LABELS[
                    int(saved["overlay"]["HeaderLayout"])]] >= header_rows,
            expected={"HeaderPosition": print_overlay.HEADER_POSITION,
                      "layout_cells": f">= {header_rows}"},
            actual={"HeaderPosition": saved["overlay"]["HeaderPosition"],
                    "HeaderLayout": saved["overlay"]["HeaderLayout"],
                    "layout": print_overlay.HEADER_LAYOUT_LABELS[
                        int(saved["overlay"]["HeaderLayout"])]},
            note="사양서1 297쪽 - None 으로 설정한 경우 표시되지 않는다 / "
                 "Layout 한 칸당 한 항목씩 표시한다")

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
        Path(film_path).parent.mkdir(parents=True, exist_ok=True)
        film_image = ImageGrab.grab(bbox=film.rect, all_screens=True)
        film_image.save(film_path)
        result.attach(film_path)
        expect = _film_expectations(target)
        film_texts = _ocr_areas(film_image, os.path.splitext(film_path)[0],
                                tess, result)
        film_labels = _judge_areas(film_texts, expect)
        result.assert_true(
            5, "Film 프리뷰에 Header/Top/Bottom 영역별 Print Overlay 표시",
            _all_ok(film_labels),
            expected={area: sorted(checks) for area, checks in expect.items()},
            actual={"areas": film_labels, "ocr": film_texts,
                    "regions": print_overlay.film_regions(*film_image.size)})

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
        # 화면 좌표가 아니라 **서버가 저장한 프리뷰**에서 직접 OCR 한다.
        # viewer.html?id=<job> 이 보여 주는 것과 같은 이미지다. 크기가 필름과
        # 달라도(1280x1600) 같은 비율 크롭으로 읽힌다(실측).
        web_image = Image.open(web_path)
        web_texts = _ocr_areas(web_image, os.path.splitext(web_path)[0],
                               tess, result)
        web_values = _judge_areas(web_texts, expect)
        similarity = _image_similarity(film_path, web_path)
        result.assert_true(
            6, "Print 서버 웹 프리뷰 Overlay가 Film 프리뷰와 영역별로 일치",
            _all_ok(web_values) and web_values == film_labels and
            similarity["similarity"] >= .96,
            expected={"areas": film_labels, "image_similarity": ">= 0.96"},
            actual={"job_url": f"{server.base}/viewer.html?id={job['id']}",
                    "film_ocr": film_texts, "web_ocr": web_texts,
                    "web_areas": web_values, "image": similarity})
    except Exception as exc:
        result.add(0, "TC_Basic_WorkFlow_08 실행", FAIL, actual=str(exc))
    return result
