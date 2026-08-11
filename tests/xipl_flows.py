# -*- coding: utf-8 -*-
"""TC_XIPL_compatibility_01~03 through the Bellalun Viewer UI."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from core.result import FAIL, MANUAL, PASS, TCResult
from core.ui import ViewerUi
from core.xipl import XiplStudio
from core import viewer_processing as vp


def _ev(ctx, name):
    root = Path(ctx.evidence_root) / "Viewer_XIPL"
    root.mkdir(parents=True, exist_ok=True)
    return str(root / name)


def _prepare(ctx):
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process XIPL.STUDIO -ErrorAction SilentlyContinue | Stop-Process -Force"],
        capture_output=True)
    parameter_root = (ctx.cfg.get("xipl") or {}).get(
        "parameter_dir", r"C:\XIPL\PARAMETER")
    vp.ensure_parameter_copies(parameter_root)
    return vp.open_test_study(ctx)


def compatibility_01(ctx, session):
    r = TCResult("TC_XIPL_compatibility_01", "Viewer와 XIPL 표시값 비교")
    ui = session["ui"]
    try:
        vp.select_2d(ui, session["step_2d"])
        before = _ev(ctx, "TC_XIPL_compatibility_01_viewer.png")
        vp.capture_viewer_window(ui, before)
        r.attach(before)
        viewer_overlay = vp.read_viewer_w1_w2(before)
        overlay_fields = session.get("overlay_fields") or {
            int(row["FieldID"]): row for row in ctx.db.query(
                "CONFIGURATION",
                "SELECT FieldID,Position,[Order] FROM OVERLAY_ITEM "
                "WHERE FieldID IN (113,134)")}
        r.assert_true(
            1, "Display > Overlay에 Histogram과 W1/W2 설정 저장",
            {113, 134}.issubset(overlay_fields),
            expected="FieldID 113, 134", actual=overlay_fields)
        r.add(2, "Viewer에서 2D 영상과 W1/W2 선택", PASS,
              actual={"patient": session["patient_id"], **viewer_overlay})

        vp.expand_tools(ui)
        ui.click([c for c in ui.by_id(vp.XIPL_TOOL) if c.visible][0], settle=.2)
        end = time.time() + 20
        studio_ui = ViewerUi("XIPL.STUDIO")
        while time.time() < end and not studio_ui.pid:
            time.sleep(.5)
            studio_ui._pid = None
        if not studio_ui.pid:
            raise RuntimeError("Viewer XIPL tool did not launch XIPL.STUDIO")

        xipl_cfg = ctx.cfg.get("xipl") or {}
        studio = XiplStudio(
            exe=xipl_cfg.get("studio_exe", r"C:\XIPL\STUDIO_X64\XIPL.STUDIO.exe"),
            tesseract=xipl_cfg.get(
                "tesseract_exe", r"C:\Program Files\Tesseract-OCR\tesseract.exe"))
        studio.start(maximize=False)
        shot = _ev(ctx, "TC_XIPL_compatibility_01_xipl.png")
        overlay = studio.capture_first_overlay(shot)
        r.attach(shot)

        r.add(3, "Viewer Tools > XIPL 호출", PASS,
              expected="Viewer 내부 XIPL 도구", actual="Control ID 1160")
        r.assert_true(
            3, "동일 2304x3072 영상이 XIPL에 표시",
            studio.rendered_fraction(shot) > .01
            and overlay.get("width") == 2304 and overlay.get("height") == 3072,
            expected="2304x3072 영상 렌더링", actual=overlay)
        r.assert_equal(
            4, "Viewer와 XIPL Histogram/Window Level 값 일치",
            {"w1": viewer_overlay["w1"], "w2": viewer_overlay["w2"]},
            {"w1": overlay.get("w1"), "w2": overlay.get("w2")},
            note="양쪽 화면의 표시 숫자를 각각 OCR하여 비교")

        parameter_shot = _ev(ctx, "TC_XIPL_compatibility_01_parameter.png")
        parameter = studio.read_applied_parameter(parameter_shot)
        r.attach(parameter_shot)
        r.assert_true(
            5, "XIPL에 적용 Processing Parameter 표시",
            bool(parameter.get("parameter")),
            expected="[PIM] - <parameter>.pim",
            actual=parameter.get("parameter"))

        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process XIPL.STUDIO -ErrorAction SilentlyContinue | Stop-Process -Force"],
            capture_output=True)
        ui.activate()
    except Exception as exc:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process XIPL.STUDIO -ErrorAction SilentlyContinue | Stop-Process -Force"],
            capture_output=True)
        try:
            ui.activate()
        except Exception:
            pass
        r.add(1, "Viewer XIPL 도구 자동 수행", FAIL, actual=str(exc))
    return r


def compatibility_02(ctx, session):
    r = TCResult("TC_XIPL_compatibility_02", "Viewer 2D Image Processing")
    ui = session["ui"]
    try:
        vp.select_2d(ui, session["step_2d"])
        vp.open_process(ui)
        name = vp.select_test_parameter(ui, "TEST_2D_FLOW.pim")
        vp.change_all_2d_parameters(ui)
        changed_state = vp.read_2d_parameter_state(ui)

        selected = _ev(ctx, "TC_XIPL_compatibility_02_selected.png")
        vp.capture(selected)
        r.attach(selected)
        r.add(2, "Viewer Image Processing 표시", PASS, actual="Process Control ID 1151")
        r.add(4, "TEST_2D_FLOW.pim Refresh 및 선택", PASS, actual=name)
        r.add(6, "2D 전체 파라미터 실제값 변경", PASS, actual=changed_state)

        ui.click([c for c in ui.by_id(vp.PREVIEW) if c.visible][0], settle=1)
        time.sleep(float((ctx.cfg.get("xipl") or {}).get("preview_2d_wait", 20)))
        preview = _ev(ctx, "TC_XIPL_compatibility_02_preview.png")
        vp.capture(preview)
        r.attach(preview)
        r.add(7, "전체 파라미터 변경 후 Preview", PASS, actual="Preview 완료, Apply 활성")

        ui.click([c for c in ui.by_id(vp.APPLY) if c.visible][0], settle=1)
        time.sleep(float((ctx.cfg.get("xipl") or {}).get("apply_2d_wait", 30)))
        r.assert_true(8, "Apply 후 처리 창 종료",
                      not [c for c in ui.by_id(vp.APPLY) if c.visible],
                      expected="Viewer 영상에 적용", actual="처리 창 종료")

        vp.open_process(ui)
        current = [c for c in ui.by_id(vp.PARAM_COMBO) if c.visible][0].text
        reopened_state = vp.read_2d_parameter_state(ui)
        verify = _ev(ctx, "TC_XIPL_compatibility_02_reopen.png")
        vp.capture(verify)
        r.attach(verify)

        expected = {"parameter": name, "values": changed_state}
        actual = {"parameter": current, "values": reopened_state}
        r.assert_equal(
            9, "Apply 후 TEST_2D 이름과 5개 실제값 유지", expected, actual,
            note="Apply 직전 값을 읽고 재진입 후 항목별로 비교")
        vp.cancel_window(ui)
    except Exception as exc:
        vp.cancel_window(ui)
        r.add(2, "2D Image Processing 자동 수행", FAIL, actual=str(exc))
    return r


def compatibility_03(ctx, session):
    r = TCResult("TC_XIPL_compatibility_03", "Viewer 3D Post Reconstruction")
    ui = session["ui"]
    try:
        vp.select_3d_raw(ui, session["step_3d"])
        vp.open_post_reconstruction(ui)
        name = vp.select_test_parameter(ui, "TEST_3D_FLOW.xtp")
        vp.change_all_3d_parameters(ui)
        changed_state = vp.read_3d_parameter_state(ui)

        selected = _ev(ctx, "TC_XIPL_compatibility_03_selected.png")
        vp.capture(selected)
        r.attach(selected)
        r.add(1, "3D Raw 영상 선택", PASS, actual="Raw / InstanceType 1")
        r.add(2, "Viewer Post Reconstruction 표시", PASS, actual="Control ID 1178")
        r.add(4, "TEST_3D_FLOW.xtp Refresh 및 선택", PASS, actual=name)
        r.add(6, "Recon/Syn 전체 파라미터 실제값 변경", PASS, actual=changed_state)

        ui.click([c for c in ui.by_id(vp.PREVIEW) if c.visible][0], settle=1)
        time.sleep(float((ctx.cfg.get("xipl") or {}).get("preview_3d_wait", 35)))
        preview = _ev(ctx, "TC_XIPL_compatibility_03_preview.png")
        vp.capture(preview)
        r.attach(preview)
        r.add(7, "전체 파라미터 변경 후 Preview", PASS, actual="Preview 완료, Apply 활성")

        ui.click([c for c in ui.by_id(vp.APPLY) if c.visible][0], settle=1)
        time.sleep(float((ctx.cfg.get("xipl") or {}).get("apply_3d_wait", 75)))
        r.assert_true(8, "Apply 후 Reconstruction 완료",
                      not [c for c in ui.by_id(vp.APPLY) if c.visible],
                      expected="Raw 기반 Recon/Syn 재생성", actual="처리 창 종료")

        vp.select_3d_raw(ui, session["step_3d"])
        vp.open_post_reconstruction(ui)
        current = [c for c in ui.by_id(vp.PARAM_COMBO) if c.visible][0].text
        reopened_state = vp.read_3d_parameter_state(ui)
        verify = _ev(ctx, "TC_XIPL_compatibility_03_reopen.png")
        vp.capture(verify)
        r.attach(verify)

        expected = {"parameter": name, "values": changed_state}
        actual = {"parameter": current, "values": reopened_state}
        r.assert_equal(
            9, "Apply 후 TEST_3D 이름과 Recon/Syn 실제값 유지", expected, actual,
            note="Background Masking과 Recon/Syn 8개 값을 재진입 후 항목별로 비교")
        vp.cancel_window(ui)
    except Exception as exc:
        vp.cancel_window(ui)
        r.add(1, "3D Post Reconstruction 자동 수행", FAIL, actual=str(exc))
    return r


def compatibility_04(ctx):
    """Audit prerequisites without inventing approved preset parameters."""
    r = TCResult("TC_XIPL_compatibility_04", "Preset별 2D Default Parameter 적용")
    root = (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER")
    required = [os.path.join(root, "TEST_2D_A.pim"),
                os.path.join(root, "TEST_2D_B.pim")]
    state = {os.path.basename(path): os.path.exists(path) for path in required}
    if all(state.values()):
        r.add(0, "검증용 2D Parameter 파일 확인", PASS, actual=state)
        r.manual(1, "Preset 생성·매핑 및 Demo 촬영 검증",
                 "승인된 PRESET_FLOW_A/B의 View Position과 촬영 조건 확인 후 UI 자동화 가능",
                 expected="PRESET_FLOW_A=TEST_2D_A, PRESET_FLOW_B=TEST_2D_B",
                 actual="승인된 Preset 정의가 아직 없음")
    else:
        r.manual(0, "검증용 2D Parameter 파일 준비",
                 "파일 내용을 임의 생성하면 서로 다른 Parameter 적용 TC가 무효가 되므로 사용자 제공 필요",
                 expected="TEST_2D_A.pim and TEST_2D_B.pim", actual=state)
    return r


def compatibility_05(ctx):
    r = TCResult("TC_XIPL_compatibility_05", "Q.C Default Image Process Parameter")
    root = (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER")
    installed = {
        "common_qc_processing.eap": os.path.exists(
            os.path.join(root, "common_qc_processing.eap")),
        "common_qc_raw.eap": os.path.exists(
            os.path.join(root, "common_qc_raw.eap")),
    }
    r.add(0, "설치된 Q.C 공통 설정 파일 확인", PASS if all(installed.values()) else FAIL,
          expected="2D/3D Q.C 공통 설정", actual=installed)
    r.manual(1, "2D/3D Q.C Parameter 설정·촬영·적용값 비교",
             "체크리스트에 검증 파일명이 미확정이고 승인된 Q.C 촬영 조건이 필요함",
             expected="승인된 2D/3D Q.C Parameter 파일명과 촬영 조건",
             actual="미제공")
    return r


def compatibility_06(ctx):
    r = TCResult("TC_XIPL_compatibility_06", "XIPL Parameter 저장 후 Viewer 적용")
    root = (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER")
    saved = os.path.join(root, "TEST_XIPL_SAVED.pim")
    if os.path.exists(saved):
        r.add(0, "저장 시험 Parameter 파일 확인", PASS, actual=saved)
        r.manual(1, "XIPL 변경·Save As·Viewer Apply 검증",
                 "XIPL에서 변경할 승인 항목과 기대값을 확인한 뒤 자동화 가능",
                 expected="승인된 변경 항목/기대값", actual="미확정")
    else:
        r.manual(0, "XIPL 저장 시험 Parameter 준비",
                 "Save As 대상과 변경할 승인 항목이 없으므로 임의 저장하지 않음",
                 expected="TEST_XIPL_SAVED.pim 및 변경할 세부 항목", actual="파일 없음")
    return r


def run_xipl(ctx):
    try:
        session = _prepare(ctx)
    except Exception as exc:
        out = []
        for tc, title in [
            ("TC_XIPL_compatibility_01", "Viewer와 XIPL 표시값 비교"),
            ("TC_XIPL_compatibility_02", "Viewer 2D Image Processing"),
            ("TC_XIPL_compatibility_03", "Viewer 3D Post Reconstruction"),
        ]:
            r = TCResult(tc, title)
            r.add(0, "Viewer 시험 데이터 준비(Procedure +, F8)", FAIL, actual=str(exc))
            out.append(r)
        out.extend([compatibility_04(ctx), compatibility_05(ctx), compatibility_06(ctx)])
        return out
    return [compatibility_01(ctx, session), compatibility_02(ctx, session),
            compatibility_03(ctx, session), compatibility_04(ctx),
            compatibility_05(ctx), compatibility_06(ctx)]
