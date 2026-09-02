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


def _wait_visible(ui, ctrl_id, timeout, predicate=None, poll=.3):
    """`ctrl_id` 가 보일 때까지 기다린다(고정 sleep 금지, 운영 지침 1절).

    2026-08-27: 3D 인쇄 패스를 붙이면서 **두 번째 이후 필름 열기가 5초를
    넘긴다**는 것을 실측했다(첫 패스는 5초 안에 떴다). 고정 대기 뒤 한 번만
    보던 코드는 이때 "Film window did not open" 으로 죽었다 — 제품 문제가
    아니라 대기 방식 문제였다.
    """
    end = time.time() + timeout
    while True:
        found = [c for c in ui.by_id(ctrl_id)
                 if c.visible and (predicate is None or predicate(c))]
        if found:
            return found
        if time.time() >= end:
            return []
        time.sleep(poll)


def _film_panes(film):
    """Film 창에 실제로 채워진 영상 칸(ctrl_id 203)들."""
    managers = [c for c in children(film.hwnd, 4) if c.ctrl_id == 203 and c.visible]
    return list({c.hwnd: c for c in managers}.values())


def _film_from_selected_study(ui, timeout=25, select_images_verify=False):
    """Print(2188) -> Selected(501) 로 Film 창까지 연다.

    검사에 3D(Narrow/Wide) 영상이 있으면 Film 대신 "Select Images" 창이
    먼저 뜬다(2D 는 프레임이 하나뿐이라 뜨지 않는다 - `flows.select_images_window`
    가 짧게 기다려 보고 없으면 바로 넘어간다). 뜨면 Raw/Recon/Syn 프레임을
    각 1장씩 전송 목록에 담아(사양서1 SRS 02-40-60, Operation Manual 10.1.2)
    Film 로 넘긴다 - 3장이 실제로 필름에 오르는 것까지가 3D Print 의 정상
    절차다.

    `select_images_verify=True` 면 Raw/Recon/Syn 3장을 담기 전에 임시 항목을
    하나 더 추가했다 휴지통으로 지워(4 -> 3) 삭제 버튼 자체도 왕복 검증한다.
    3D 패스 중 한 번만 켜면 충분하다(반복 비용 방지).
    """
    buttons = _wait_visible(ui, 2188, 8)
    if not buttons:
        raise RuntimeError("Examined Print button (2188) not found")
    ui.click(buttons[0], settle=1)
    selected = _wait_visible(ui, 501, 8)
    if not selected:
        raise RuntimeError("Print Selected button (501) not found")
    ui.click(selected[0], settle=1)

    select_images_result = None
    si_win = flows.select_images_window(ui, timeout=5)
    if si_win is not None:
        checks = {}
        # 같은 View Position 을 다시 열면 이전에 담아 둔 항목이 남아 있을 수
        # 있다 - 항상 비우고 시작해 "이미 존재함" 경고를 원천적으로 피한다.
        flows.select_images_clear(ui, si_win)
        checks["add_raw"] = flows.select_images_add(ui, si_win, kind="raw")
        checks["add_recon"] = flows.select_images_add(ui, si_win, kind="recon")
        checks["add_syn"] = flows.select_images_add(ui, si_win, kind="syn")
        if select_images_verify:
            # 마지막에 임시 항목을 하나 더 얹었다가 곧바로 지운다 -
            # Raw/Recon/Syn 세 장은 그대로 두고 휴지통만 왕복 검증한다.
            # frame_index=1 로 **다른** Raw 프레임을 골라야 한다 - add_raw 가
            # 이미 고른 프레임(index 0)을 또 고르면 제품이 "This item already
            # exists." 경고로 막아 뒤이은 OK 클릭이 어긋난다(2026-09-02 실측).
            checks["add_extra"] = flows.select_images_add(
                ui, si_win, kind="raw", frame_index=1)
            checks["delete_extra"] = flows.select_images_delete_last(ui, si_win)
        flows.select_images_confirm(ui, si_win)
        select_images_result = checks

    film = _wait_visible(ui, 158, timeout,
                         lambda c: c.text == "CWndFilmManager")
    if not film:
        raise RuntimeError("Film window did not open")

    if select_images_result is None:
        # 2D: 이미지 1장 - 기존 1x1 단일 이미지 레이아웃/판정 그대로.
        one_by_one = _wait_visible(ui, 1141, 8, lambda c: c.rect[0] > 1400)
        if not one_by_one:
            raise RuntimeError("Film 1x1 layout button (1141) not found")
        ui.click(one_by_one[0], settle=1)
        film_area = ((film[0].rect[2] - film[0].rect[0]) *
                     (film[0].rect[3] - film[0].rect[1]))
        end = time.time() + 12
        largest, pane_area = None, 0
        while True:
            unique = _film_panes(film[0])
            largest = max(unique, key=lambda c: ((c.rect[2] - c.rect[0]) *
                                                 (c.rect[3] - c.rect[1])), default=None)
            pane_area = 0 if largest is None else (
                (largest.rect[2] - largest.rect[0]) * (largest.rect[3] - largest.rect[1]))
            if pane_area >= film_area * .85:
                break
            if time.time() >= end:
                break
            time.sleep(.3)
        if not largest:
            raise RuntimeError("Film 1x1 image pane not found")
        if pane_area < film_area * .85:
            raise RuntimeError(
                f"Film layout did not change to 1x1: pane={largest.rect}, film={film[0].rect}")
        return film[0], {"button_id": 1141, "pane": largest.rect,
                         "film": film[0].rect, "pane_ratio": pane_area / film_area,
                         "select_images": None}

    # 3D: Raw/Recon/Syn 3장 - 2x2 로 명시 전환하고 채워진 칸 3개를 기다린다.
    layout_btn = _wait_visible(ui, 1143, 8, lambda c: c.rect[0] > 1400)
    if not layout_btn:
        raise RuntimeError("Film 2x2 layout button (1143) not found")
    ui.click(layout_btn[0], settle=1)
    end = time.time() + 12
    panes = _film_panes(film[0])
    while len(panes) < 3 and time.time() < end:
        time.sleep(.3)
        panes = _film_panes(film[0])
    if len(panes) != 3:
        raise RuntimeError(
            f"2x2 Film 에서 채워진 칸을 3개 찾지 못했습니다(찾은 개수={len(panes)}, "
            f"rects={[p.rect for p in panes]}).")
    return film[0], {"button_id": 1143,
                     "panes": [p.rect for p in sorted(panes, key=lambda c: c.rect[1])],
                     "film": film[0].rect, "select_images": select_images_result}


# ---------------------------------------------------------------------------
# 3D 커버리지 확장 (2026-08-27 사용자 요청)
#
# 사용자 요청: "dicom send/print/export 할 때 3D 의 모든 경우의 수를 전부
# 테스트하고 싶어. 무지성으로 3D-W 를 촬영하고 싶은 게 아니라 모든 경우의 수의
# 영향성을 보고 싶다." 기존 WF_08 은 Examined 우측 썸네일 중 **맨 위 한 장
# (2D LCC)** 만 Selected 로 인쇄해, 3D-N / 3D-W 는 단 한 번도 필름에 오르지
# 않았다.
#
# 실측(2026-08-27):
#   * Examined 에서 Print(2188) 를 누르면 "Do you want to print all images of
#     the selected study?" 대화상자가 뜬다 - All Images(502) / Selected(501) /
#     Cancel(500). `Selected` 는 **그 순간 선택돼 있는 썸네일 한 장**만 필름에
#     올린다. 그래서 썸네일을 바꿔 가며 세 번 돌리면 2D / 3D-N / 3D-W 를 각각
#     인쇄할 수 있다.
#   * 우측 썸네일은 `text == "ScrollWnd"` 이고 x > 1600 인 컨트롤이며, 위에서
#     부터 `LCC` / `LCC (3D-N)` / `LCC (3D-W)` 다. **ctrl_id 를 믿으면 안 된다**
#     - 같은 날 같은 화면에서 13/14/15 와 11/12 를 모두 관측했다(창을 다시 열면
#     달라진다). y 정렬로 순서를 잡고 **라벨 OCR** 로 종류를 확정한다.
#   * Print SCP 가 돌려주는 job 메타데이터는 Film 단위(id / received_at /
#     calling_ae_title / film_size_id)라 **어떤 영상이 실렸는지는 알려 주지
#     않는다**. 따라서 "필름 프리뷰 == 서버 프리뷰" 만 보면 세 번 모두 같은
#     영상을 보내도 전부 통과해 버린다. 그래서 교차 대조를 함께 한다 - 각
#     서버 프리뷰는 **자기 필름과 가장 닮아야** 한다. 임의의 유사도 임계값을
#     새로 고르지 않아도 되고("3D-N 과 3D-W 가 얼마나 달라야 하는가"는 근거를
#     댈 수 없는 수치다), 세 장이 실제로 다른 영상이라는 것이 증명된다.
_THUMB_LABEL_BAND = 26          # 썸네일 하단 라벨 띠 높이(실측)


def _thumbnail_controls(ui):
    """Examined 우측 썸네일 컨트롤을 위에서 아래 순서로 돌려준다."""
    found = {}
    for c in ui.controls():
        if c.visible and c.text == "ScrollWnd" and c.rect[0] > 1600:
            found[c.hwnd] = c          # core.ui.children 은 중복을 준다
    return sorted(found.values(), key=lambda c: c.rect[1])


def _thumb_label(control, tesseract_exe):
    import pytesseract

    if tesseract_exe:
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
    box = (control.rect[0], control.rect[3] - _THUMB_LABEL_BAND,
           control.rect[2], control.rect[3] + 2)
    image = ImageGrab.grab(bbox=box, all_screens=True).convert("L")
    image = ImageOps.autocontrast(image)
    image = image.resize((image.width * 4, image.height * 4))
    return pytesseract.image_to_string(image, config="--psm 7", lang="eng").strip()


def _thumbnails(ui, tesseract_exe):
    """썸네일 목록을 라벨 OCR 로 2D / 3D-N / 3D-W 로 분류한다."""
    out = []
    for c in _thumbnail_controls(ui):
        label = ""
        if tesseract_exe:
            try:
                label = _thumb_label(c, tesseract_exe)
            except Exception:
                label = ""
        # `_norm` 은 영숫자만 남긴다: 'LCC(3D-N) ,t,@' -> 'lcc3dnt'
        norm = _norm(label)
        kind = "3D-N" if "3dn" in norm else "3D-W" if "3dw" in norm else "2D"
        out.append({"control": c, "rect": c.rect, "label": label, "kind": kind})
    return out


def _ensure_thumbnails(ctx, ui, target, tesseract_exe, expected=2, wait=8):
    """썸네일이 보일 때까지 기다리고, 안 보이면 Examined 를 다시 열어 잡는다."""
    end = time.time() + wait
    while time.time() < end:
        if len(_thumbnail_controls(ui)) >= expected:
            return _thumbnails(ui, tesseract_exe)
        time.sleep(.4)
    _open_examined_fixture(ctx, ui, target)     # 필름을 닫고 돌아온 뒤 복구
    return _thumbnails(ui, tesseract_exe)


def _print_thumbnail(ui, server, thumb, tag, evidence_dir, known,
                     job_timeout=90, select_images_verify=False):
    """썸네일 한 장을 Selected 로 필름에 올려 인쇄하고 서버 프리뷰까지 받는다.

    반환: `{"film": 필름 캡처 경로, "web": 서버 프리뷰 경로, "job": job, ...}`
    """
    ui.click(thumb["control"], settle=1.0)
    film, layout = _film_from_selected_study(
        ui, select_images_verify=select_images_verify)
    Path(evidence_dir).mkdir(parents=True, exist_ok=True)
    film_path = os.path.join(evidence_dir, f"07_film_{tag}.png")
    ImageGrab.grab(bbox=film.rect, all_screens=True).save(film_path)

    pane_check = None
    if layout.get("panes"):
        # Raw/Recon/Syn 이 실제로 **서로 다른** 영상인지 - 필름에 채워진 세
        # 칸을 각각 잘라 셋을 서로 비교한다(2D/3D-N/3D-W 필름끼리 비교하는
        # `_cross_match`와 같은 목적을, 한 필름 안의 세 칸 사이에서 본다).
        film_img = Image.open(film_path)
        ox, oy = film.rect[0], film.rect[1]
        crops = []
        for idx, rect in enumerate(layout["panes"]):
            left, top, right, bottom = rect
            crop_path = os.path.join(evidence_dir, f"07_film_{tag}_pane{idx}.png")
            film_img.crop((left - ox, top - oy, right - ox, bottom - oy)).save(crop_path)
            crops.append(crop_path)
        pairs, distinct = {}, True
        for a in range(len(crops)):
            for b in range(a + 1, len(crops)):
                sim = _image_similarity(crops[a], crops[b])
                pairs[f"{a}-{b}"] = sim
                if sim["mean_delta"] < 1.0:   # 사실상 동일 = 같은 프레임이 중복 선택됨
                    distinct = False
        pane_check = {"crops": crops, "pairs": pairs, "distinct": distinct}

    print_buttons = [c for c in ui.by_id(1149) if c.visible]
    if not print_buttons:
        raise RuntimeError(f"{tag}: Film Print button (1149) not found")
    ui.click(print_buttons[0], settle=2)
    dialog = ui.dialog()
    if dialog:
        buttons = ui.dialog_buttons(dialog)
        if len(buttons) == 1:          # 단일 버튼 안내창만 닫는다
            ui.click(buttons[0], settle=1)

    jobs = server.wait_for_jobs(count=1, timeout=job_timeout, poll=.5,
                                exclude_ids=known)
    if not jobs:
        raise RuntimeError(
            f"{tag}: Print SCP did not receive a new job within {job_timeout} seconds")
    job = jobs[-1]
    web_path = os.path.join(evidence_dir, f"07_print_job_{tag}_{job['id']}.png")
    Path(web_path).write_bytes(server.preview(job["id"]))
    return {"film": film_path, "web": web_path, "job": job, "layout": layout,
            "similarity": _image_similarity(film_path, web_path),
            "pane_check": pane_check}


def _cross_match(prints):
    """각 서버 프리뷰가 '자기 필름' 과 가장 닮았는지 본다.

    같은 영상을 세 번 보냈다면 어떤 필름과 비교해도 유사도가 고만고만해져서
    자기 짝이 최댓값이 되지 못한다. 임계값을 새로 정하지 않고 판정할 수 있다.
    """
    kinds = list(prints)
    table, ok = {}, True
    for kind in kinds:
        scores = {other: _image_similarity(prints[other]["film"],
                                           prints[kind]["web"])["similarity"]
                  for other in kinds}
        best = max(scores, key=scores.get)
        table[kind] = {"scores": scores, "best_match": best}
        if best != kind:
            ok = False
    return ok, table


# 필름 OCR 판독·판정은 `core/print_overlay.py` 로 옮겼다(2026-08-21).
# `TC_Basic_WorkFlow_03` Step 6 도 같은 판정을 하므로 구현을 하나로 둔다 —
# OCR 경로가 둘이면 한쪽만 고쳐 다른 쪽이 조용히 낡는다.
_norm = print_overlay.film_norm


def _ocr_areas(image, path_prefix, tesseract_exe, result=None):
    attach = result.attach if result is not None else None
    return print_overlay.ocr_film_areas(image, path_prefix, tesseract_exe,
                                        attach=attach)


_film_expectations = print_overlay.film_expectations
_judge_areas = print_overlay.judge_film_areas
_all_ok = print_overlay.film_all_ok


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

        # 인쇄 대상 썸네일 확인 (2D / 3D-N / 3D-W)
        wide_enabled = (ctx.cfg.get("test_data") or {}).get("include_3d_wide", True)
        want = ["2D", "3D-N"] + (["3D-W"] if wide_enabled else [])
        thumbs = _ensure_thumbnails(ctx, ui, target, tess, expected=len(want))
        by_kind = {}
        for item in thumbs:
            by_kind.setdefault(item["kind"], item)
        result.assert_true(
            4, "Examined 썸네일에 " + " / ".join(want) + " 가 모두 존재 (커버리지 확장)",
            all(kind in by_kind for kind in want),
            expected=want,
            actual=[{"kind": t["kind"], "label": t["label"], "rect": t["rect"]}
                    for t in thumbs],
            note="개정본 범위 밖의 확장이다 — 3D 의 모든 경우의 수를 Print 까지 "
                 "태우기 위한 전제 확인이다. 썸네일 ctrl_id 는 창을 다시 열면 "
                 "바뀌므로 y 순서 + 라벨 OCR 로 고른다(2026-08-27 실측). "
                 "config.json > test_data.include_3d_wide 로 3D-W 를 끌 수 있다.")
        if "2D" in by_kind:
            # 지금까지는 '기본 선택이 맨 위 2D' 라는 암묵적 가정에 기대고
            # 있었다. 세 패스를 대칭으로 만들면서 명시적으로 고른다.
            ui.click(by_kind["2D"]["control"], settle=1.0)

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

        # --- 3D 인쇄 패스 (커버리지 확장) --------------------------------
        # 2D 는 위에서 Overlay OCR 까지 끝났다. 3D-N / 3D-W 는 "그 영상이
        # 실제로 필름에 올라가 Print SCP 까지 갔는가"가 확인할 점이다.
        prints = {"2D": {"film": film_path, "web": web_path, "job": job,
                         "similarity": similarity}}
        known.add(str(job.get("id")))
        for i, kind in enumerate(want[1:]):
            flows.close_film(ui, tess)
            thumbs = _ensure_thumbnails(ctx, ui, target, tess, expected=len(want))
            picked = next((t for t in thumbs if t["kind"] == kind), None)
            if picked is None:
                result.add(7, f"{kind} 영상 Film Print (커버리지 확장)", FAIL,
                           expected=f"{kind} 썸네일 선택",
                           actual=[t["label"] for t in thumbs],
                           note="필름을 닫고 돌아온 뒤 썸네일을 다시 찾지 못했다.")
                continue
            tag = kind.replace("-", "").lower()
            verify_select_images = (i == 0)
            done = _print_thumbnail(ui, server, picked, tag, evidence_dir, known,
                                    select_images_verify=verify_select_images)
            known.add(str(done["job"].get("id")))
            prints[kind] = done
            result.attach(done["film"])
            result.attach(done["web"])
            result.assert_true(
                7, f"{kind} 영상 Film Print 후 Print SCP 수신 및 프리뷰 일치 (커버리지 확장)",
                str(done["job"].get("id")) not in {str(job.get("id"))}
                and done["similarity"]["similarity"] >= .96,
                expected={"new_job": True, "image_similarity": ">= 0.96"},
                actual={"thumbnail": picked["label"], "job": done["job"],
                        "job_url": f"{server.base}/viewer.html?id={done['job']['id']}",
                        "image": done["similarity"]},
                note="Print SCP job 메타데이터는 Film 단위라 어떤 영상이 실렸는지 "
                     "알려 주지 않는다 — 필름 프리뷰와 서버 프리뷰의 픽셀 일치로 "
                     "본다. 어느 영상인지는 다음 교차 대조가 증명한다.")

            si = done["layout"].get("select_images")
            select_ok = (si is not None
                         and si["add_raw"]["after"] == si["add_raw"]["before"] + 1
                         and si["add_recon"]["after"] == si["add_recon"]["before"] + 1
                         and si["add_syn"]["after"] == si["add_syn"]["before"] + 1)
            note = ("3D 검사는 Print > Selected 이후 Select Images 창에서 View "
                    "Position 의 프레임을 Raw/Recon/Syn Type 별로 각 1장씩 전송 "
                    "목록에 담아야 Film 에 3장이 함께 오른다(사양서1 SRS 02-40-60, "
                    "Operation Manual 10.1.2).")
            if verify_select_images:
                select_ok = (select_ok and si["add_extra"]["after"]
                             == si["add_extra"]["before"] + 1
                             and si["delete_extra"]["after"]
                             == si["delete_extra"]["before"] - 1)
                note += (" 이 창을 처음 다루는 3D 패스에서는 임시 항목을 하나 더 "
                         "얹었다 휴지통으로 지워(2026-09-02 실측) 삭제 버튼도 "
                         "왕복 검증하고, Raw/Recon/Syn 세 장은 그대로 둔다.")
            result.assert_true(
                7, f"{kind} Select Images 창에서 Raw/Recon/Syn 추가"
                   + (" 및 휴지통 삭제" if verify_select_images else "")
                   + " (커버리지 확장)",
                select_ok,
                expected="Raw/Recon/Syn 추가마다 전송 목록 +1"
                         + ("(임시 항목 삭제는 -1)" if verify_select_images else ""),
                actual=si, note=note)

            pc = done.get("pane_check")
            if pc:
                for path in pc["crops"]:
                    result.attach(path)
                result.assert_true(
                    7, f"{kind} Film 의 Raw/Recon/Syn 세 칸이 서로 다른 영상 "
                       "(커버리지 확장)",
                    len(pc["crops"]) == 3 and pc["distinct"],
                    expected="세 칸의 픽셀이 서로 달라야 한다(같은 프레임 중복 선택 아님)",
                    actual=pc,
                    note="Print SCP job 메타데이터는 Film 단위라 어떤 프레임이 "
                         "실렸는지 알려 주지 않는다 — 필름에 채워진 세 칸을 각각 "
                         "잘라 서로 비교해 실제로 다른 영상임을 증명한다.")

            film_img = Image.open(done["film"])
            header_texts = _ocr_areas(film_img, os.path.splitext(done["film"])[0]
                                       + "_header", tess, result)
            header_ok = _judge_areas(header_texts, expect).get("header", {})
            result.assert_true(
                7, f"{kind} Film 프리뷰에 Print Overlay Header 표시 (커버리지 확장)",
                _all_ok({"header": header_ok}),
                expected={"header": sorted(label for label, _ in
                                           print_overlay.PRINT_ITEMS_BY_AREA["header"])},
                actual={"ocr": header_texts.get("header"), "areas": header_ok},
                note="Header 는 필름 전체 상단에 한 번만 표시되는 공용 영역이라 "
                     "칸 배치(1x1/2x2)와 무관하게 그대로 확인할 수 있다. Top/Bottom "
                     "은 2D 처럼 한 이미지 전체를 가정한 위치라 다중 칸 필름에서는 "
                     "따로 판정하지 않는다 — 서버 프리뷰와의 픽셀 일치(위 Print SCP "
                     "검증)가 그 영역들까지 포함해 손실 없이 전송됐음을 증명한다.")

        if len(prints) >= 2:
            matched, table = _cross_match(prints)
            result.assert_true(
                7, "인쇄된 " + " / ".join(prints) + " 필름이 서로 다른 영상 (커버리지 확장)",
                matched,
                expected="각 서버 프리뷰는 자기 필름과 가장 닮아야 한다",
                actual=table,
                note="같은 영상을 여러 번 보내도 '필름==서버' 판정만으로는 전부 "
                     "통과한다. 자기 짝이 최댓값인지 보면 임계값을 새로 정하지 "
                     "않고도 서로 다른 영상임이 증명된다.")
    except Exception as exc:
        result.abort(0, "TC_Basic_WorkFlow_08 실행", exc)
    return result
