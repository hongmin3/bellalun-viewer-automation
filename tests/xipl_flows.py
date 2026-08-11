# -*- coding: utf-8 -*-
"""TC_XIPL_compatibility_01~03 through the Bellalun Viewer UI."""

from __future__ import annotations

import os
import hashlib
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from core.result import FAIL, MANUAL, PASS, TCResult
from core.ui import ViewerUi
from core.xipl import XiplStudio
from core import viewer_processing as vp


def _ev(ctx, name):
    root = Path(ctx.evidence_root) / "Viewer_XIPL"
    root.mkdir(parents=True, exist_ok=True)
    return str(root / name)


def _preview_delta(before_path, after_path):
    """Compare only the processed preview pane, excluding parameter controls."""
    before = Image.open(before_path).convert("RGB")
    after = Image.open(after_path).convert("RGB")
    width, height = before.size
    box = (int(width * .365), int(height * .055),
           int(width * .710), int(height * .900))
    diff = ImageChops.difference(before.crop(box), after.crop(box)).convert("L")
    histogram = diff.histogram()
    total = max(1, sum(histogram))
    return {
        "mean_delta": round(ImageStat.Stat(diff).mean[0], 3),
        "changed_ratio": round(sum(histogram[13:]) / total, 6),
    }


def _directory_state(path):
    root = Path(path)
    if not root.exists():
        return {}
    return {str(item): {"size": item.stat().st_size,
                        "mtime_ns": item.stat().st_mtime_ns}
            for item in root.iterdir() if item.is_file()}


def _new_files(before, after):
    return {path: state for path, state in after.items()
            if path not in before or before[path] != state}


def _file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    stat = os.stat(path)
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "sha256": digest.hexdigest()}


def _result_state(ctx, study_key):
    """DB identity and bytes for the Recon/Synthetic outputs of one study."""
    rows = ctx.db.query(
        "DATA", "SELECT [Key],InstanceType,ImageInstanceUID,ContentDate,ContentTime "
        "FROM INSTANCE WHERE StudyKey=@study AND InstanceType IN (2,3) "
        "ORDER BY InstanceType,[Key]", {"study": study_key})
    roots = sorted(Path(ctx.cfg["data_dir"]).joinpath("Image").glob(
        f"Study{study_key}_*"))
    files = {}
    for row in rows:
        for root in roots:
            candidate = root / f"Image{row['Key']}.img"
            if candidate.exists():
                files[str(candidate)] = _file_digest(candidate)
                break
    return {"instances": rows, "files": files}


def _viewer_log_mark(ctx):
    path = Path(ctx.cfg["data_dir"]) / "Log" / "Viewer" / time.strftime("%Y_%m_%d.log")
    return path, path.stat().st_size if path.exists() else 0


def _viewer_log_since(mark):
    path, offset = mark
    if not path.exists():
        return ""
    with path.open("rb") as stream:
        signature = stream.read(2)
        stream.seek(offset)
        data = stream.read()
    if signature in (b"\xff\xfe", b"\xfe\xff"):
        encoding = "utf-16-le" if signature == b"\xff\xfe" else "utf-16-be"
        return data.decode(encoding, errors="replace").lstrip("\ufeff")
    return data.decode("utf-8", errors="replace")


def _last_2d_process(log_text):
    pattern = re.compile(
        r"Image Process Param Name\s*:\s*([^,\]]+),\s*"
        r"Contrast\s*:\s*(\d+),\s*Sharpness\s*:\s*(\d+),\s*"
        r"Brightness\s*:\s*(\d+),\s*Tone Type\s*:\s*(\d+),\s*"
        r"Noise Reduction\s*:\s*(\d+)", re.I)
    hits = pattern.findall(log_text)
    if not hits:
        return {}
    name, contrast, sharpness, brightness, tone, noise = hits[-1]
    return {"parameter": name.strip(), "values": {
        "Contrast": int(contrast), "Sharpness": int(sharpness),
        "Brightness": int(brightness), "Tone type": int(tone),
        "Noise reduction": int(noise)}}


def _parameter_display_matches(expected, displayed):
    expected_key = vp._parameter_name_key(expected)
    displayed_key = vp._parameter_name_key(displayed)
    return (displayed_key == expected_key or
            len(displayed_key) >= 6 and expected_key.startswith(displayed_key))


def _read_state_retry(reader, ui, attempts=4):
    """Retry OCR while the custom parameter window finishes repainting."""
    last_error = None
    for _ in range(attempts):
        try:
            return reader(ui)
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise last_error


def _read_2d_parameter_file(path):
    """Read the five approved baseline values from the actual .pim XML."""
    node = ET.parse(path).getroot().find(".//ImgPrcParam")
    if node is None:
        raise RuntimeError(f"ImgPrcParam node not found: {path}")
    fields = {
        "Contrast": "Contrast", "Sharpness": "Sharpness",
        "Brightness": "Brightness", "Tone type": "ToneType",
        "Noise reduction": "NoiseReduction",
    }
    try:
        return {label: int(node.attrib[attr]) for label, attr in fields.items()}
    except (KeyError, ValueError) as exc:
        raise RuntimeError(f"Invalid 2D parameter baseline in {path}: {exc}") from exc


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
        source_2d = [row for row in session["instances"]
                     if int(row["InstanceType"]) == 0]
        r.assert_true(
            2, "Viewer에서 유일한 2D 원본 영상과 W1/W2 선택",
            len(source_2d) == 1 and bool(source_2d[0].get("ImageInstanceUID")),
            expected="InstanceType=0 한 건과 고유 Image Instance UID",
            actual={"patient": session["patient_id"], "instance": source_2d,
                    **viewer_overlay})

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

        r.assert_true(3, "Viewer Tools > XIPL 프로세스 기동",
                      bool(studio_ui.pid),
                      expected="Control ID 1160 실행 후 XIPL.STUDIO PID 생성",
                      actual={"control_id": 1160, "pid": studio_ui.pid})
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
        parameter_name = str(parameter.get("parameter") or "")
        parameter_path = os.path.join(
            (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER"),
            parameter_name)
        r.assert_true(
            5, "XIPL에 적용 Processing Parameter 표시",
            parameter_name.lower().endswith(".pim") and os.path.isfile(parameter_path),
            expected="[PIM]의 실제 설치 .pim 파일명",
            actual={"parameter": parameter_name, "exists": os.path.isfile(parameter_path)})

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
        parameter_path = os.path.join(
            (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER"),
            "TEST_2D_FLOW.pim")
        baseline_state = _read_2d_parameter_file(parameter_path)
        vp.change_all_2d_parameters(ui)
        changed_state = _read_state_retry(vp.read_2d_parameter_state, ui)

        selected = _ev(ctx, "TC_XIPL_compatibility_02_selected.png")
        vp.capture(selected)
        r.attach(selected)
        r.assert_true(2, "Viewer Image Processing 화면 데이터 표시",
                      bool([c for c in ui.by_id(vp.PARAM_COMBO) if c.visible])
                      and set(baseline_state) == set(vp.SLIDER_NAMES_2D.values()),
                      expected="Parameter 목록과 5개 지원값 컨트롤",
                      actual={"control_id": 1151, "baseline": baseline_state})
        r.assert_equal(4, "TEST_2D_FLOW.pim Refresh 및 선택",
                       "TEST_2D_FLOW.pim", name)
        changed_fields = {key: {"before": baseline_state[key],
                                "after": changed_state[key]}
                          for key in changed_state
                          if baseline_state.get(key) != changed_state.get(key)}
        r.assert_true(6, "2D 전체 파라미터 실제값 변경",
                      set(changed_fields) == set(changed_state),
                      expected="5개 지원값 모두 변경",
                      actual=changed_fields)

        log_mark = _viewer_log_mark(ctx)
        action_before = _directory_state(
            os.path.join(ctx.cfg["data_dir"], "Image", "ImageAction"))
        ui.click([c for c in ui.by_id(vp.PREVIEW) if c.visible][0], settle=1)
        time.sleep(float((ctx.cfg.get("xipl") or {}).get("preview_2d_wait", 20)))
        preview = _ev(ctx, "TC_XIPL_compatibility_02_preview.png")
        vp.capture(preview)
        r.attach(preview)
        preview_delta = _preview_delta(selected, preview)
        apply_visible = bool([c for c in ui.by_id(vp.APPLY) if c.visible])
        r.assert_true(7, "원본과 변경 Preview 구분 표시",
                      preview_delta["changed_ratio"] >= .005 and apply_visible,
                      expected="처리 pane 변화율 >= 0.005 및 Apply 활성",
                      actual={"delta": preview_delta, "apply_visible": apply_visible})

        ui.click([c for c in ui.by_id(vp.APPLY) if c.visible][0], settle=1)
        time.sleep(float((ctx.cfg.get("xipl") or {}).get("apply_2d_wait", 30)))
        action_after = _directory_state(
            os.path.join(ctx.cfg["data_dir"], "Image", "ImageAction"))
        action_delta = _new_files(action_before, action_after)
        applied = _last_2d_process(_viewer_log_since(log_mark))
        apply_closed = not [c for c in ui.by_id(vp.APPLY) if c.visible]
        applied_ok = (vp._parameter_name_key(applied.get("parameter")) ==
                      vp._parameter_name_key("TEST_2D_FLOW.pim") and
                      applied.get("values") == changed_state)
        r.assert_true(8, "변경 결과가 대상 영상에 적용",
                      apply_closed and applied_ok and bool(action_delta),
                      expected="처리 로그의 파일명/5개 값 일치 및 ImageAction 결과 생성",
                      actual={"window_closed": apply_closed, "log": applied,
                              "image_action_files": action_delta})

        vp.open_process(ui)
        current = [c for c in ui.by_id(vp.PARAM_COMBO) if c.visible][0].text
        reopened_state = _read_state_retry(vp.read_2d_parameter_state, ui)
        verify = _ev(ctx, "TC_XIPL_compatibility_02_reopen.png")
        vp.capture(verify)
        r.attach(verify)

        actual = {"displayed_parameter": current, "applied_log": applied,
                  "values": reopened_state}
        r.assert_true(
            9, "Apply 후 TEST_2D 이름과 5개 실제값 유지",
            _parameter_display_matches(name, current)
            and applied_ok and reopened_state == changed_state,
            expected={"parameter": name, "values": changed_state}, actual=actual,
            note=("콤보 UIA text는 폭에 따라 접미사가 잘릴 수 있어 prefix를 확인하고, "
                  "전체 파일명은 Viewer 처리 로그에서 정확히 대조"))
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
        baseline_state = _read_state_retry(vp.read_3d_parameter_state, ui)
        vp.change_all_3d_parameters(ui)
        changed_state = _read_state_retry(vp.read_3d_parameter_state, ui)

        selected = _ev(ctx, "TC_XIPL_compatibility_03_selected.png")
        vp.capture(selected)
        r.attach(selected)
        source_raw = [row for row in session["instances"]
                      if int(row["InstanceType"]) == 1]
        r.assert_true(1, "3D Raw 원본 영상 선택",
                      len(source_raw) == 1 and bool(source_raw[0].get("ImageInstanceUID")),
                      expected="InstanceType=1 한 건과 고유 Image Instance UID",
                      actual=source_raw)
        r.assert_true(2, "Viewer Post Reconstruction 지원 데이터 표시",
                      bool([c for c in ui.by_id(vp.PARAM_COMBO) if c.visible])
                      and set(baseline_state) == {
                          "Recon.Background Masking", "Syn.Background Masking",
                          *vp.SLIDER_NAMES_3D.values()},
                      expected="3D-N Parameter 목록, Recon/Syn 10개 지원값",
                      actual={"control_id": 1178, "baseline": baseline_state})
        r.assert_equal(4, "TEST_3D_FLOW.xtp Refresh 및 선택",
                       "TEST_3D_FLOW.xtp", name)
        changed_fields = {key: {"before": baseline_state[key],
                                "after": changed_state[key]}
                          for key in changed_state
                          if baseline_state.get(key) != changed_state.get(key)}
        r.assert_true(6, "Recon/Syn 전체 파라미터 실제값 변경",
                      set(changed_fields) == set(changed_state),
                      expected="Background Masking 2개와 수치 8개 모두 변경",
                      actual=changed_fields)

        log_mark = _viewer_log_mark(ctx)
        result_before = _result_state(ctx, session["study_key"])
        ui.click([c for c in ui.by_id(vp.PREVIEW) if c.visible][0], settle=1)
        time.sleep(float((ctx.cfg.get("xipl") or {}).get("preview_3d_wait", 35)))
        preview = _ev(ctx, "TC_XIPL_compatibility_03_preview.png")
        vp.capture(preview)
        r.attach(preview)
        preview_delta = _preview_delta(selected, preview)
        apply_visible = bool([c for c in ui.by_id(vp.APPLY) if c.visible])
        r.assert_true(7, "원본과 변경 Preview 구분 표시",
                      preview_delta["changed_ratio"] >= .005 and apply_visible,
                      expected="처리 pane 변화율 >= 0.005 및 Apply 활성",
                      actual={"delta": preview_delta, "apply_visible": apply_visible})

        ui.click([c for c in ui.by_id(vp.APPLY) if c.visible][0], settle=1)
        time.sleep(float((ctx.cfg.get("xipl") or {}).get("apply_3d_wait", 75)))
        log_text = _viewer_log_since(log_mark)
        result_after = _result_state(ctx, session["study_key"])
        apply_closed = not [c for c in ui.by_id(vp.APPLY) if c.visible]
        recon_error = re.findall(
            r"Failed to initialize Recon\.\s*Error:\s*([^\]\r\n]+)", log_text, re.I)
        parameter_seen = bool(re.search(
            r"Initialize Reconstruction\.[^\r\n]*TEST_3D_FLOW\.xtp",
            log_text, re.I))
        r.assert_true(8, "Apply 후 Post Reconstruction 완료",
                      apply_closed and parameter_seen and not recon_error,
                      expected="TEST_3D_FLOW.xtp 처리 로그와 Recon 초기화 오류 없음",
                      actual={"window_closed": apply_closed,
                              "parameter_seen": parameter_seen,
                              "errors": recon_error})

        db_changed = result_before["instances"] != result_after["instances"]
        files_changed = result_before["files"] != result_after["files"]
        valid_types = {int(row["InstanceType"]) for row in result_after["instances"]}
        r.assert_true(9, "해당 검사에 Recon/Synthetic 결과 영상 생성",
                      valid_types == {2, 3} and (db_changed or files_changed)
                      and not recon_error,
                      expected="InstanceType 2/3 결과의 DB 또는 파일 해시/시간 변화",
                      actual={"before": result_before, "after": result_after,
                              "db_changed": db_changed,
                              "files_changed": files_changed,
                              "errors": recon_error})
        verify = _ev(ctx, "TC_XIPL_compatibility_03_result.png")
        vp.capture_viewer_window(ui, verify)
        r.attach(verify)
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
