# -*- coding: utf-8 -*-
"""TC_XIPL_compatibility_01~03 through the Bellalun Viewer UI."""

from __future__ import annotations

import os
import hashlib
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime
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


_LOG_LINE_TS = re.compile(r"^\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]")


def _log_lines_from(log_text, not_before):
    """Keep only lines whose own timestamp is >= not_before.

    A byte-offset log_mark can still admit a line that was logically written
    before the mark: Viewer's log writer buffers output, so a slow-to-flush
    line (e.g. the Preview action's own delayed "Terminate PostReconThread
    normally closed", observed ~2-3s after its progress bar already reported
    eNoti:5) can appear only after we have already re-marked the file for
    the next action (Apply).  Filtering by each line's own embedded
    timestamp — instead of trusting file-append ordering — is what actually
    keeps a leftover Preview-thread completion from being misread as Apply's.
    """
    if not_before is None:
        return log_text
    kept = []
    for line in log_text.splitlines():
        m = _LOG_LINE_TS.match(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S.%f")
        except ValueError:
            continue
        if ts >= not_before:
            kept.append(line)
    return "\n".join(kept)


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


def _poll_completion(result, name, predicate, timeout, poll=.5):
    """Wait up to timeout, but leave immediately when product evidence is complete."""
    started_wall, started = datetime.now(), time.perf_counter()
    deadline = time.monotonic() + float(timeout)
    last = None
    while time.monotonic() < deadline:
        try:
            done, reason, detail = predicate()
            last = detail
            if done:
                result.record_timing(name, started_wall, started, reason, detail)
                return detail
        except Exception as exc:
            last = repr(exc)
        time.sleep(poll)
    result.record_timing(name, started_wall, started, "timeout", last)
    raise RuntimeError(f"{name} timed out after {timeout}s; last={last}")


def _preview_2d_complete(log_mark, expected_values):
    applied = _last_2d_process(_viewer_log_since(log_mark))
    values_ok = applied.get("values") == expected_values
    name_ok = (vp._parameter_name_key(applied.get("parameter")) ==
               vp._parameter_name_key("TEST_2D_FLOW.pim"))
    detail = {"log": applied, "values_match": values_ok}
    return name_ok and values_ok, "log completion detected", detail


def _apply_2d_complete(ctx, ui, log_mark, files_before, expected_values):
    applied = _last_2d_process(_viewer_log_since(log_mark))
    files_after = _directory_state(
        os.path.join(ctx.cfg["data_dir"], "Image", "ImageAction"))
    delta = _new_files(files_before, files_after)
    closed = not [c for c in ui.by_id(vp.APPLY) if c.visible]
    values_ok = applied.get("values") == expected_values
    name_ok = (vp._parameter_name_key(applied.get("parameter")) ==
               vp._parameter_name_key("TEST_2D_FLOW.pim"))
    detail = {"window_closed": closed, "log": applied,
              "image_action_files": delta}
    return (closed and name_ok and values_ok and bool(delta),
            "log/file/control completion detected", detail)


def _post_recon_complete(log_mark, ui, require_closed, not_before=None):
    log_text = _log_lines_from(_viewer_log_since(log_mark), not_before)
    thread_done = "Terminate PostReconThread normally closed" in log_text
    closed = not [c for c in ui.by_id(vp.APPLY) if c.visible]
    parameter_seen = bool(re.search(
        r"Initialize Reconstruction\.[^\r\n]*TEST_3D_FLOW\.xtp", log_text, re.I))
    errors = re.findall(
        r"Failed to initialize Recon\.\s*Error:\s*([^\]\r\n]+)", log_text, re.I)
    progress_done = bool(re.search(
        r"ProgressBar Show \(CDlgPostReconstruction::OnProgressImageProcess,\s*eNoti:5\)",
        log_text, re.I))
    gpu_unavailable = bool(errors) and all(
        re.sub(r"[^a-z]", "", error.lower()) in {"nogpu", "nogpus"}
        for error in errors)
    processing_done = thread_done or (
        parameter_seen and gpu_unavailable and progress_done)
    done = processing_done and (closed if require_closed else True)
    detail = {"thread_done": thread_done, "window_closed": closed,
              "progress_done": progress_done, "parameter_seen": parameter_seen,
              "gpu_unavailable": gpu_unavailable, "errors": errors}
    return done, "log/control completion detected", detail


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


def _refresh_fixture(ctx):
    """Recreate today's DATA_FLOW_MWL_01 fixture via WF01 (MWL delete+recreate,
    Local suspend) then WF02 (Demo F8 2D/3D acquisition).

    Standalone XIPL runs (run-xipl-01/02/03) must never silently reuse a
    fixture from a previous day: WF01 already deletes/re-registers the MWL
    order for today on every run, so re-running WF01+WF02 here guarantees
    the InstanceType 0/1/2/3 fixture open_test_study() looks for is today's.
    """
    from tests.workflow01 import run as run_wf01
    from tests.workflow02 import run as run_wf02

    wf01 = run_wf01(ctx)
    if wf01.verdict == FAIL:
        raise RuntimeError(
            "오늘 날짜 시험 데이터 준비를 위한 WF01 재실행이 실패했습니다: "
            f"{[c.actual for c in wf01.checks if c.status == FAIL]}")
    wf02 = run_wf02(ctx)
    if wf02.verdict == FAIL:
        raise RuntimeError(
            "오늘 날짜 시험 데이터 준비를 위한 WF02 재실행이 실패했습니다: "
            f"{[c.actual for c in wf02.checks if c.status == FAIL]}")


def _prepare(ctx):
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process XIPL.STUDIO -ErrorAction SilentlyContinue | Stop-Process -Force"],
        capture_output=True)
    parameter_root = (ctx.cfg.get("xipl") or {}).get(
        "parameter_dir", r"C:\XIPL\PARAMETER")
    vp.ensure_parameter_copies(parameter_root)
    patient_id = (ctx.cfg.get("xipl") or {}).get("test_patient_id", "DATA_FLOW_MWL_01")
    if not vp.fixture_is_fresh(ctx, patient_id):
        _refresh_fixture(ctx)
    return vp.open_test_study(ctx)


def _launch_xipl(ctx, ui):
    """Launch XIPL from the selected Viewer image and return both drivers."""
    vp.expand_tools(ui)
    tools = [c for c in ui.by_id(vp.XIPL_TOOL) if c.visible]
    if not tools:
        raise RuntimeError("Viewer XIPL tool (1160) not found")
    ui.click(tools[0], settle=.2)
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
    return studio, studio_ui


def _stop_xipl():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process XIPL.STUDIO -ErrorAction SilentlyContinue | Stop-Process -Force"],
        capture_output=True)


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

        studio, studio_ui = _launch_xipl(ctx, ui)
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
        parameter_attempts = []
        parameter = studio.read_applied_parameter(parameter_shot)
        parameter_attempts.append(parameter)
        retry_overlay_valid = True
        parameter_name = str(parameter.get("parameter") or "")
        parameter_root = (ctx.cfg.get("xipl") or {}).get(
            "parameter_dir", r"C:\XIPL\PARAMETER")
        parameter_path = os.path.join(parameter_root, parameter_name)
        if not (parameter_name.lower().endswith(".pim") and
                os.path.isfile(parameter_path)):
            # XIPL occasionally opens the correct raster/WL while its PIM
            # editor remains "Untitled".  Reinvoke once from the same selected
            # Viewer instance and accept it only if the image identity still
            # matches before reading the applied PIM again.
            _stop_xipl()
            ui.activate()
            vp.select_2d(ui, session["step_2d"])
            studio, studio_ui = _launch_xipl(ctx, ui)
            retry_shot = _ev(ctx, "TC_XIPL_compatibility_01_xipl_retry.png")
            retry_overlay = studio.capture_first_overlay(retry_shot)
            r.attach(retry_shot)
            retry_overlay_valid = (
                retry_overlay.get("width") == 2304 and
                retry_overlay.get("height") == 3072 and
                retry_overlay.get("w1") == viewer_overlay["w1"] and
                retry_overlay.get("w2") == viewer_overlay["w2"])
            parameter = studio.read_applied_parameter(parameter_shot)
            parameter_attempts.append(parameter)
        r.attach(parameter_shot)
        parameter_name = str(parameter.get("parameter") or "")
        parameter_path = os.path.join(parameter_root, parameter_name)
        r.assert_true(
            5, "XIPL에 적용 Processing Parameter 표시",
            retry_overlay_valid and parameter_name.lower().endswith(".pim")
            and os.path.isfile(parameter_path),
            expected="[PIM]의 실제 설치 .pim 파일명",
            actual={"parameter": parameter_name, "exists": os.path.isfile(parameter_path),
                    "same_image_after_retry": retry_overlay_valid,
                    "attempts": parameter_attempts})

        _stop_xipl()
        ui.activate()
    except Exception as exc:
        _stop_xipl()
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
        preview_limit = float((ctx.cfg.get("xipl") or {}).get("preview_2d_wait", 20))
        _poll_completion(
            r, "XIPL 2D Preview", lambda: _preview_2d_complete(log_mark, changed_state),
            preview_limit)
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
        apply_limit = float((ctx.cfg.get("xipl") or {}).get("apply_2d_wait", 30))
        _poll_completion(
            r, "XIPL 2D Apply",
            lambda: _apply_2d_complete(ctx, ui, log_mark,
                                       action_before, changed_state),
            apply_limit)
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
        xipl_cfg = ctx.cfg.get("xipl") or {}
        # The legacy preview_3d_wait was only a blind settle delay.  Repeated
        # live runs varied from about 38s to 80s, so keep a generous ceiling
        # while still returning as soon as the thread-end log appears.
        post_recon_limit = float(xipl_cfg.get("post_recon_timeout", 120))
        preview_limit = float(xipl_cfg.get("preview_3d_timeout", post_recon_limit))
        preview_completion = _poll_completion(
            r, "XIPL 3D Preview", lambda: _post_recon_complete(log_mark, ui, False),
            preview_limit)
        preview = _ev(ctx, "TC_XIPL_compatibility_03_preview.png")
        vp.capture(preview)
        r.attach(preview)
        preview_delta = _preview_delta(selected, preview)
        apply_visible = bool([c for c in ui.by_id(vp.APPLY) if c.visible])
        r.assert_true(7, "원본과 변경 Preview 구분 표시",
                      preview_delta["changed_ratio"] >= .005 and apply_visible,
                      expected="처리 pane 변화율 >= 0.005 및 Apply 활성",
                      actual={"delta": preview_delta, "apply_visible": apply_visible})

        apply_log_mark = _viewer_log_mark(ctx)
        apply_click_time = datetime.now()
        ui.click([c for c in ui.by_id(vp.APPLY) if c.visible][0], settle=1)
        apply_limit = float(xipl_cfg.get("apply_3d_timeout", post_recon_limit))
        _poll_completion(
            r, "XIPL 3D Apply",
            lambda: _post_recon_complete(apply_log_mark, ui, True,
                                         not_before=apply_click_time),
            apply_limit)
        # Filter by each line's own timestamp, not just byte offset: a live
        # run on 2026-08-14 showed the Preview action's own thread-exit line
        # ("Terminate PostReconThread normally closed") land in the log only
        # after Apply's mark was taken, so an unfiltered read misread it as
        # Apply's own completion (thread_done True in 0.567s -- far too fast
        # for a real Post Recon cycle, which the same run's Preview stage
        # took ~9.7s to reach even via progress bar, and ~12s via thread-exit).
        log_text = _log_lines_from(_viewer_log_since(apply_log_mark), apply_click_time)
        result_after = _result_state(ctx, session["study_key"])
        apply_closed = not [c for c in ui.by_id(vp.APPLY) if c.visible]
        thread_done = "Terminate PostReconThread normally closed" in log_text
        recon_error = re.findall(
            r"Failed to initialize Recon\.\s*Error:\s*([^\]\r\n]+)", log_text, re.I)
        # Confirmed on 2026-08-14 (Viewer log 09:18:08-09:18:43): Apply does
        # NOT re-emit "Initialize Reconstruction ... TEST_3D_FLOW.xtp" the
        # way Preview does -- it reuses the already-previewed computation and
        # only logs its own Do Post Reconstruction/progress/thread-exit
        # cycle. So parameter_seen is recorded for visibility only; it is
        # not a pass/fail condition here. Step 9's reopen-and-compare is the
        # authoritative check that TEST_3D_FLOW.xtp and its 10 values survived
        # Apply.
        parameter_seen = bool(re.search(
            r"Initialize Reconstruction\.[^\r\n]*TEST_3D_FLOW\.xtp",
            log_text, re.I))
        gpu_unavailable = bool(recon_error) and all(
            re.sub(r"[^a-z]", "", error.lower()) in {"nogpu", "nogpus"}
            for error in recon_error)
        unexpected_error = recon_error if not gpu_unavailable else []
        r.assert_true(8, "Apply 요청 처리 완료",
                      apply_closed and thread_done and not unexpected_error,
                      expected=("Apply 창 닫힘 + Apply 자체의 신규 Post Recon 완료 로그; "
                                "GPU 미탑재 환경의 No GPUS만 허용"),
                      actual={"window_closed": apply_closed,
                              "thread_done": thread_done,
                              "parameter_seen": parameter_seen,
                              "gpu_unavailable": gpu_unavailable,
                              "errors": recon_error},
                      note=("Apply는 Preview와 달리 Initialize Reconstruction 로그를 다시 "
                            "남기지 않는다(2026-08-14 실측). 선택 파라미터 유지 여부는 "
                            "Step 9 재진입 비교가 판정한다. GPU가 없으면 실제 Reconstruction "
                            "산출물은 별도 SKIP으로 기록한다."))

        db_changed = result_before["instances"] != result_after["instances"]
        files_changed = result_before["files"] != result_after["files"]
        valid_types = {int(row["InstanceType"]) for row in result_after["instances"]}

        # Apply must persist the selected file and every changed value when
        # the tool is opened again.  This assertion is independent of GPU
        # availability and therefore also runs on GPU-less test machines.
        vp.open_post_reconstruction(ui)
        reopened_name = [c for c in ui.by_id(vp.PARAM_COMBO) if c.visible][0].text
        reopened_state = _read_state_retry(vp.read_3d_parameter_state, ui)
        reopen_shot = _ev(ctx, "TC_XIPL_compatibility_03_reopen.png")
        vp.capture(reopen_shot)
        r.attach(reopen_shot)
        retained = (_parameter_display_matches(name, reopened_name)
                    and reopened_state == changed_state)
        reopen_expected = {"parameter": name, "values": changed_state}
        reopen_actual = {"displayed_parameter": reopened_name,
                         "values": reopened_state, "retained": retained}
        r.assert_true(
            9, "Apply 후 TEST_3D 이름과 Recon/Syn 10개 값 유지", retained,
            expected=reopen_expected, actual=reopen_actual,
            note=("Apply 후 Post Reconstruction에 재진입하여 UI 표시값을 다시 읽어 비교. "
                  "기본값 복원은 GPU 유무와 관계없이 FAIL"))
        vp.cancel_window(ui)

        output_actual = {"before": result_before, "after": result_after,
                         "db_changed": db_changed,
                         "files_changed": files_changed,
                         "errors": recon_error}
        # Apply's own log never repeats "Failed to initialize Recon: No GPUS"
        # (it doesn't reinitialize at all -- see Step 8 note), so whether the
        # machine actually has no GPU can only be read from the Preview
        # attempt, which does perform and log a real initialize/error cycle.
        preview_gpu_unavailable = bool(preview_completion.get("gpu_unavailable"))
        if preview_gpu_unavailable:
            r.skip(10, "Recon/Synthetic 결과 영상 생성",
                   "GPU 미탑재 환경에서 Viewer가 'No GPUS'를 반환하여 산출물 검증 제외")
        else:
            r.assert_true(10, "해당 검사에 Recon/Synthetic 결과 영상 생성",
                          valid_types == {2, 3} and (db_changed or files_changed)
                          and not recon_error,
                          expected="InstanceType 2/3 결과의 DB 또는 파일 해시/시간 변화",
                          actual=output_actual)
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
