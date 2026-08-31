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

from core.result import FAIL, MANUAL, PASS, SKIP, TCResult
from core.ui import ViewerUi, children
from core.xipl import XiplStudio
from core import flows
from core import imginfo
from core import screen
from core import specs
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



def _qc_window(ui, anchor):
    """Q.C 테스트 창을 찾는다. anchor(창 안의 컨트롤)를 담는 최상위 창.

    Q.C 창은 거의 전체화면이라 `ui.dialog()` 의 '작은 #32770' 판정에 걸리지
    않는다. 그래서 창 목록에서 anchor 를 포함하는 것을 고른다.
    """
    al, at, ar, ab = anchor.rect
    best = None
    for w in ui.windows():
        l, t, r, b = w.rect
        if l <= al and t <= at and r >= ar and b >= ab:
            area = (r - l) * (b - t)
            if best is None or area < best[0]:
                best = (area, w)
    if best is None:
        raise flows.FlowError(
            "Q.C 테스트 창을 찾지 못했습니다(결과 콤보를 담는 창 없음).")
    return best[1]


def _canvas_point(window):
    """창 기준 상대 비율로 영상 캔버스의 한 점을 계산한다.

    캔버스는 창 좌측 영상 영역이다. 창 폭의 40%, 높이의 55% 지점을 쓴다 —
    실측(1920x1080)에서 절대좌표 (760, 550) 에 해당한다.
    """
    l, t, r, b = window.rect
    return (l + int((r - l) * 0.40), t + int((b - t) * 0.55))

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
               vp._parameter_name_key("TEST_2D_FLOW_M.pim"))
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
               vp._parameter_name_key("TEST_2D_FLOW_M.pim"))
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
        # 양쪽 모두 화면 숫자를 OCR로 읽는다. 단발 오독에 판정이 흔들리면 안 된다
        # (2026-08-19 실측: Viewer 쪽 W1 24380을 243380으로 읽어 자리수가 하나 늘었다.
        #  W2는 정확히 일치했으므로 값이 다른 게 아니라 판독이 틀린 것이다).
        #
        # 불일치하면 **양쪽을 다시 캡처해 다시 읽는다.** 진짜로 값이 다르면 재판독
        # 해도 계속 다르므로 결함이 감춰지지 않는다. 시도 기록을 actual에 남겨
        # 리포트만 보고도 "판독이 흔들렸는지 값이 달랐는지" 구분할 수 있게 한다.
        wl_attempts = [{"viewer": {"w1": viewer_overlay.get("w1"),
                                  "w2": viewer_overlay.get("w2")},
                        "xipl": {"w1": overlay.get("w1"),
                                 "w2": overlay.get("w2")}}]
        for attempt in range(2):
            last = wl_attempts[-1]
            if last["viewer"] == last["xipl"]:
                break
            reshot_viewer = _ev(
                ctx, f"TC_XIPL_compatibility_01_viewer_retry{attempt + 1}.png")
            reshot_xipl = _ev(
                ctx, f"TC_XIPL_compatibility_01_xipl_retry{attempt + 1}.png")
            try:
                screen.grab(ui.main_window().rect, path=reshot_viewer)
                again_viewer = vp.read_viewer_w1_w2(reshot_viewer)
                again_xipl = studio.capture_first_overlay(reshot_xipl)
            except Exception as exc:
                wl_attempts.append({"error": str(exc)})
                break
            wl_attempts.append(
                {"viewer": {"w1": again_viewer.get("w1"),
                            "w2": again_viewer.get("w2")},
                 "xipl": {"w1": again_xipl.get("w1"),
                          "w2": again_xipl.get("w2")}})
            r.attach(reshot_viewer)
            r.attach(reshot_xipl)
        final = wl_attempts[-1]
        r.assert_true(
            4, "Viewer와 XIPL Histogram/Window Level 값 일치",
            bool(final.get("viewer")) and final.get("viewer") == final.get("xipl"),
            expected="Viewer 표시 W1/W2 == XIPL 표시 W1/W2",
            actual={"final": final, "attempts": wl_attempts},
            note="개정본 Expected 3(뷰어에 표시된 Histogram/Window Level과 XIPL의 "
                 "값이 동일). 양쪽 모두 화면 숫자를 OCR로 읽으므로, 불일치하면 "
                 "재캡처해 다시 읽고 시도 기록을 함께 남긴다. 값이 정말 다르면 "
                 "재판독해도 계속 다르다.")

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
        r.abort(1, "Viewer XIPL 도구 자동 수행", exc)
    return r


def compatibility_02(ctx, session):
    r = TCResult("TC_XIPL_compatibility_02", "Viewer 2D Image Processing")
    ui = session["ui"]
    try:
        vp.select_2d(ui, session["step_2d"])
        vp.open_process(ui)
        name = vp.select_test_parameter(ui, "TEST_2D_FLOW_M.pim")
        parameter_path = os.path.join(
            (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER"),
            "TEST_2D_FLOW_M.pim")
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
        r.assert_equal(4, "TEST_2D_FLOW_M.pim Refresh 및 선택",
                       "TEST_2D_FLOW_M.pim", name)
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
                      vp._parameter_name_key("TEST_2D_FLOW_M.pim") and
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
        r.abort(2, "2D Image Processing 자동 수행", exc)
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
        # 2026-08-26: 픽스처에 3D-W 스텝을 넣으면서 Raw 가 **2건**(3D-N, 3D-W)이
        # 됐다. 예전 판정은 `len(source_raw) == 1` 을 요구해 여기서 막혔고, 정작
        # 확인해야 할 Post Reconstruction 을 한 번도 수행하지 못했다.
        # 이 TC 의 대상은 **3D-N 의 Raw** 다 — 먼저 촬영한 쪽(Key 오름차순 첫 건)이고,
        # 위에서 선택한 스텝도 `session["step_3d"]`(3D-N)이다.
        raw_target = source_raw[0] if source_raw else None
        r.assert_true(1, "3D Raw 원본 영상 선택",
                      bool(raw_target) and bool(raw_target.get("ImageInstanceUID")),
                      expected="3D-N 의 InstanceType=1 한 건과 고유 Image Instance UID",
                      actual={"target": raw_target,
                              "all_raw": source_raw,
                              "note": ("픽스처에 3D-W 가 있으면 Raw 는 2건이 정상"
                                       if len(source_raw) > 1 else "")})
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
        r.abort(1, "3D Post Reconstruction 자동 수행", exc)
    return r


def _general_combo_shows(ui, ctrl_id, filename):
    """콤보가 지금 `filename` 을 표시하고 있는가.

    커스텀 콤보의 `WM_GETTEXT` 는 값을 **앞 8자로 잘라서** 돌려준다(실측:
    `2227` -> `Pure Whi`). 잘려도 결정적이므로 **접두사**로 본다.

    읽을 수 없는 환경(빈 문자열)에서는 `None` 을 돌려준다 — 그때는 확인을
    건너뛰고 DB 대조에 맡긴다. 없는 근거로 실패시키지 않는다.
    """
    hits = [c for c in ui.by_id(ctrl_id) if c.visible]
    if not hits:
        return None
    shown = (ui.get_text(hits[0]) or "").strip()
    if not shown or shown in ("StaticText", "TextButton", "ItemWnd"):
        return None
    key = shown.upper().rstrip(".")
    return len(key) >= 4 and filename.upper().startswith(key)


def _click_general_param_combo(ui, ctrl_id, filename, wait=1.0, attempts=4):
    """Setting > Procedure > General 콤보를 열고 filename 항목을 고른다.

    **좌표로 후보를 고르려던 시도는 세 번 다 틀렸다** — 같은 화면에 2D/3D-N/3D-W
    콤보가 나란히 있고, 다른 콤보가 이미 같은 파일명을 표시하고 있으면 그것을
    누를 수 있기 때문이다.

      1. 제약 없음 -> 3D-W 복원이 **3D-N 콤보**를 눌러 조용히 실패(20차 회귀)
      2. `min_y`(콤보 아래만) -> 세 번째 콤보의 드롭다운은 위로도 열려 **후보 0개**
      3. `exclude_rects`(형제 콤보 제외) -> 3D-N 드롭다운이 3D-W 콤보를 **덮어서**
         진짜 항목까지 지워짐(21차 회귀)

    그래서 좌표를 가정하지 않는다. **누른 뒤 콤보 표시값으로 확인하고, 틀리면
    다음 후보로 다시 누른다.** 표시값을 읽을 수 없으면 확인을 건너뛰고 호출부의
    DB 대조에 맡긴다(`_set_default_recon`).
    """
    combo = [c for c in ui.by_id(ctrl_id) if c.visible]
    if not combo:
        raise flows.FlowError(f"Default Parameter 콤보(ID {ctrl_id})를 찾지 못했습니다.")
    tried = []
    for candidate in range(attempts):
        opened = [c for c in ui.by_id(ctrl_id) if c.visible]
        if not opened:
            break
        ui.click(opened[0], settle=wait)
        picked = vp.click_viewer_text(ui, filename, settle=wait,
                                      candidate=candidate)
        if not picked and candidate == 0:
            # 목록이 길어 대상이 화면 밖일 수 있다.
            cx, cy = opened[0].center
            ui.wheel((cx, cy + 60), -3, settle=.3)
            picked = vp.click_viewer_text(ui, filename, settle=wait)
        if not picked:
            tried.append({"candidate": candidate, "result": "후보 없음"})
            break
        shows = _general_combo_shows(ui, ctrl_id, filename)
        tried.append({"candidate": candidate, "shows": shows})
        if shows is not False:      # True(일치) 또는 None(읽을 수 없음)
            return {"attempts": candidate + 1, "verified": shows, "tried": tried}
        # 다른 것을 눌렀다. 다음 후보로 다시 시도한다.
        time.sleep(.4)
    raise flows.FlowError(
        f"콤보(ID {ctrl_id})에서 '{filename}'을 고르지 못했습니다. 시도={tried}")


def _select_preset_column_item(ui, x, row_index, wait=.5):
    """View Position 다이얼로그의 한 컬럼에서 row_index(0=None) 항목을 고른다."""
    y = 344 + 35 * row_index + 17
    ui.click((x, y), settle=wait)


# Roll 컬럼(x=1357) 행 인덱스. Prefix(M/S)는 실제 Magnification Table 장착이
# 필요해 Demo 촬영이 차단된다(2026-08-14 실측: 상태 배너 "Inappropriate Mag
# Table", ready=False). Roll은 그런 하드웨어 전제 없이 Demo로 정상 촬영되어
# CC 기본 View Position에 Roll만 바꿔 서로 다른 새 조합(RCCRL/RCCRM)을 만든다.
_PRESET_ROLL_X = 1357


def _add_preset_2d_pair(ui, roll_row):
    """Setting > Procedure > Preset(2D)에 CC+Roll 조합(R/L 쌍)을 추가한다."""
    add_btn = [c for c in ui.by_id(flows.PRESET_2D_ADD) if c.visible]
    if not add_btn:
        raise flows.FlowError("Preset(2D) Add 버튼(2548)을 찾지 못했습니다.")
    ui.click(add_btn[0], settle=1.0)
    dlg = ui.wait_dialog(timeout=6)
    if not dlg:
        raise flows.FlowError("View Position 다이얼로그가 열리지 않았습니다.")
    _select_preset_column_item(ui, _PRESET_ROLL_X, roll_row)
    ok = [c for c in ui.by_id(1101) if c.visible]
    if not ok:
        raise flows.FlowError("View Position 추가 OK 버튼을 찾지 못했습니다.")
    ui.click(ok[0], settle=1.5)
    err_ok = [c for c in ui.by_id(flows.SETTING_CONFIRM_OK) if c.visible]
    if err_ok:
        ui.click(err_ok[0], settle=1)
        raise flows.FlowError("Preset(2D) 추가 실패(이미 존재하거나 오류)")


def _scroll_preset_list_to_bottom(ui, rounds=20):
    list_ctrl = [c for c in ui.by_id(flows.PRESET_2D_LIST) if c.visible]
    if not list_ctrl:
        raise flows.FlowError("Preset(2D) 목록(2554)을 찾지 못했습니다.")
    l, t, rr, b = list_ctrl[0].rect
    center = ((l + rr) // 2, (t + b) // 2)
    for _ in range(rounds):
        ui.wheel(center, -3, settle=.03)
    time.sleep(.3)
    return list_ctrl[0]


def _find_preset_row_y(ctx, ui, name_text, tag):
    """Preset(2D) 목록을 스크롤해 name_text 행을 OCR로 찾고 절대 y좌표를 반환한다."""
    list_ctrl = _scroll_preset_list_to_bottom(ui)
    shot = _ev(ctx, f"TC_XIPL_compatibility_04_{tag}_list.png")
    vp.capture_viewer_window(ui, shot)
    boxes = vp.find_text_boxes(shot, name_text)
    if not boxes:
        raise flows.FlowError(f"Preset(2D) 목록에서 '{name_text}' 행을 찾지 못했습니다.")
    win = ui.main_window()
    x, y, w, h, _ = max(boxes, key=lambda b: b[4])
    row_y = win.rect[1] + y + h / 2
    return list_ctrl, row_y, shot


def _alias_preset_row(ctx, ui, name_text, alias, tag, param_filename=None):
    """name_text 행의 Alias를 설정하고, param_filename이 있으면 같은 행의
    Parameter도 함께 바꾼다.

    두 조작 모두 name_text(개명 전 원래 Name, 예: RSCC)로 한 번만 찾은 좌표를
    쓴다 - Alias 편집 직후에는 셀이 말줄임표로 표시돼("PRESET_FL...") 새
    Alias 문자열로 다시 찾을 수 없기 때문이다.
    """
    list_ctrl, row_y, shot = _find_preset_row_y(ctx, ui, name_text, tag)
    alias_x = list_ctrl.rect[0] + 160
    ui.click((alias_x, row_y), settle=.1)
    ui.click((alias_x, row_y), settle=.6)
    edits = [c for c in ui.controls(max_depth=8) if c.ctrl_id == 6 and c.cls == "Edit"]
    if not edits:
        raise flows.FlowError(f"'{name_text}' 행의 Alias 편집 상자를 찾지 못했습니다.")
    ui.type_text(edits[0], alias)
    ui.key("ENTER", settle=.5)
    if param_filename:
        param_x = list_ctrl.rect[0] + 274
        ui.click((param_x, row_y), settle=.1)
        ui.click((param_x, row_y), settle=.8)
        # 드롭다운은 파일 개수가 늘수록 목록이 길어지므로, 대상 파일이
        # 초기 화면 밖(아래)에 있을 수 있다. 스크롤 후 못 찾으면 시도한다.
        if not vp.click_viewer_text(ui, param_filename, settle=1.0):
            ui.wheel((param_x, row_y + 60), -3, settle=.3)
            if not vp.click_viewer_text(ui, param_filename, settle=1.0):
                raise flows.FlowError(
                    f"'{name_text}' 행의 Parameter 목록에서 '{param_filename}'을 찾지 못했습니다.")
    return shot


def _add_view_position_by_alias(ui, alias):
    """Procedure + 로 alias(2D Preset)를 촬영 Step으로 등록한다."""
    before = len(flows.step_items(ui))
    # `+` 클릭이 삼켜지는 경우가 있어 재시도를 포함한 공용 함수를 쓴다 —
    # `vp.add_view_position` 과 **같은 클릭·같은 실패 모드**다(근거는
    # `core/viewer_processing.open_view_position_dialog` docstring).
    vp.open_view_position_dialog(ui)
    if not vp.click_viewer_text(ui, alias, settle=.5):
        raise flows.FlowError(f"View Position 목록에서 '{alias}' 타일을 찾지 못했습니다.")
    ok = [c for c in ui.by_id(1101) if c.visible]
    if not ok:
        raise flows.FlowError("View Position OK 버튼을 찾지 못했습니다.")
    ui.click(ok[0], settle=1)
    after = len(flows.step_items(ui))
    if after != before + 1:
        raise flows.FlowError(f"Step 등록 실패: {before}->{after}")
    return after


def _ensure_test_parameters(ctx, r, step_title, needed):
    """개별 실행 시 없는 시험 파라미터만 만들고, 결과를 리포트에 남긴다.

    회귀(`run-regression`)는 시작 시 `vp.reset_parameter_copies()`로 TEST_*를
    전부 지우고 새로 만든다. 반면 TC를 단독 실행할 때는 파일이 아직 없을 수
    있는데, 예전에는 그때 MANUAL로 빠져 TC 자체를 수행하지 못했다. 이제 제품
    기본 파라미터에서 없는 것만 복사해 진행한다(있으면 그대로 재사용).
    복사 원본이 없을 때만(제품 설치 손상) MANUAL로 남긴다.

    반환값이 False면 호출자는 즉시 r을 반환해야 한다.
    """
    root = (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER")
    try:
        outcome = vp.ensure_parameter_copies(root)
    except FileNotFoundError as exc:
        r.manual(0, step_title,
                 "제품 기본 파라미터가 없어 시험 파라미터를 만들 수 없습니다. "
                 f"XIPL PARAMETER 폴더({root})와 설치 상태를 확인하십시오.",
                 expected=needed, actual=f"원본 없음: {exc}")
        return False
    state = {name: os.path.exists(os.path.join(root, name)) for name in needed}
    if not all(state.values()):
        r.manual(0, step_title, "시험 파라미터 생성 후에도 파일이 확인되지 않습니다.",
                 expected=needed, actual=state)
        return False
    r.add(0, step_title, PASS,
          expected=needed,
          actual={"files": state,
                  "created": [os.path.basename(x) for x in outcome["created"]],
                  "reused": [os.path.basename(x) for x in outcome["reused"]]})
    return True


def _owned_test_presets(ctx):
    """자동화가 만든 시험 Preset 행만 고른다.

    Alias로 찾지 않는다. Alias 셀은 UI에서 말줄임표로 잘려 OCR 재탐색이 안 되고
    (`_alias_preset_row` 주석 참고), 쌍으로 생성되는 반대쪽(L...) 행은 Alias가
    비어 있다. 대신 **`Type=0`(2D)이면서 `Roll`이 'RL'/'RM'** 인 행만 고른다 -
    제품 기본 Preset은 `Roll`이 비어 있어(2026-08-18 실측) 겹치지 않는다.
    """
    return ctx.db.query(
        "PROCEDURE",
        "SELECT [Key],Alias,Laterality,PositioningKey,Roll FROM VIEW_POSITION_PRESET "
        "WHERE Type=0 AND Roll IN ('RL','RM') ORDER BY [Key]")


def _preset_row_name(row):
    """목록의 Name 컬럼에 표시되는 문자열(예: RCCRL)."""
    side = "R" if int(row["Laterality"]) == 2 else "L"
    return f"{side}CC{row['Roll']}"


def _delete_test_presets(ctx, ui):
    """시험 Preset을 **UI로** 삭제해 TC_04를 반복 실행 가능하게 만든다.

    `core/db.py`는 조회 전용이고 저장소는 상태 변경을 UI로만 한다(운영 지침).
    그래서 DB에서 지우지 않고 Setting > Procedure > Preset(2D)의 Delete(2549)를
    누른다. 행은 잘리지 않는 Name 컬럼(RCCRL 등)으로 찾는다.

    엉뚱한 행을 지우면 사용자 Preset이 사라지므로, 삭제 전후 전체 Key 집합을
    비교해 **의도한 Key만 사라졌는지 확인**하고 아니면 예외를 던진다.
    """
    targets = _owned_test_presets(ctx)
    if not targets:
        return {"deleted": [], "detail": "삭제할 시험 Preset 없음"}

    def all_keys():
        return {int(r["Key"]) for r in ctx.db.query(
            "PROCEDURE", "SELECT [Key] FROM VIEW_POSITION_PRESET")}

    before = all_keys()
    expected = {int(r["Key"]) for r in targets}
    names = [_preset_row_name(r) for r in targets]

    flows.open_procedure_setting(ui, "preset")
    removed = []
    for index, name in enumerate(names):
        try:
            list_ctrl, row_y, _ = _find_preset_row_y(ctx, ui, name, f"del{index}")
        except Exception:
            continue                      # 이미 사라진 행(쌍 삭제 등)은 건너뛴다
        ui.click((list_ctrl.rect[0] + 60, row_y), settle=.4)
        delete = [c for c in ui.by_id(flows.PRESET_2D_DELETE) if c.visible]
        if not delete:
            raise flows.FlowError("Preset(2D) Delete 버튼(2549)을 찾지 못했습니다.")
        ui.click(delete[0], settle=.8)
        flows.confirm_setting_dialog(ui, timeout=3)
        removed.append(name)

    flows.setting_update(ui)
    flows.confirm_setting_dialog(ui)

    after = all_keys()
    gone = before - after
    if gone - expected:
        raise flows.FlowError(
            f"시험 Preset 외의 행이 삭제됐습니다: 예상={sorted(expected)} "
            f"실제 삭제={sorted(gone)}")
    left = _owned_test_presets(ctx)
    if left:
        raise flows.FlowError(
            f"시험 Preset이 남아 있습니다: {[_preset_row_name(r) for r in left]}")
    return {"deleted": sorted(gone), "clicked_rows": removed}


def compatibility_04(ctx):
    r = TCResult("TC_XIPL_compatibility_04", "Preset별 2D Default Parameter 적용")
    root = (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER")
    if not _ensure_test_parameters(ctx, r, "검증용 2D Parameter 파일 준비",
                                   [vp.PARAM_2D_A, vp.PARAM_2D_B]):
        return r

    # 이전 실행이 남긴 시험 Preset이 있으면 Add가 "이미 존재"로 실패해 TC를
    # 아예 수행할 수 없다. 예전에는 이를 MANUAL로 보고하고 사용자가 손으로
    # 지우게 했지만, 그러면 이 TC가 깨끗한 DB 없이는 두 번 돌지 않는다.
    # 이제 UI로 직접 지운다(아래 _delete_test_presets 참고 - DB는 조회 전용).
    leftover = _owned_test_presets(ctx)
    cleanup = None
    if leftover:
        cfg_pre = ctx.cfg["viewer"]
        ui_pre = ViewerUi()
        ui_pre.ensure_ready(cfg_pre["exe"], cfg_pre["login"]["id"],
                            cfg_pre["login"]["password"])
        flows.ensure_patient_screen(ui_pre)
        try:
            cleanup = _delete_test_presets(ctx, ui_pre)
        except Exception as exc:
            r.manual(0, "이전 실행의 시험 Preset 정리",
                     "UI 자동 삭제에 실패했습니다. Setting > Procedure > Preset(2D)에서 "
                     f"{[_preset_row_name(x) for x in leftover]} 행을 수동 삭제한 뒤 "
                     "다시 실행하십시오.",
                     expected="시험 Preset 없음", actual=str(exc))
            return r
        r.add(0, "이전 실행의 시험 Preset UI 자동 삭제", PASS,
              expected="Type=0, Roll RL/RM 행 전부 삭제", actual=cleanup)

    cfg = ctx.cfg["viewer"]
    ui = ViewerUi()
    # Step 1 이 이 값을 바꾼다. **원복 목표값을 바꾸기 전에 읽어 둔다.**
    baseline_param = ctx.db.scalar(
        "PROCEDURE", "SELECT DefaultImgProcess FROM PROCEDURE_COMMON")
    try:
        ui.ensure_ready(cfg["exe"], cfg["login"]["id"], cfg["login"]["password"])
        flows.ensure_patient_screen(ui)

        # Step 1: Setting > Procedure > General 의 2D Default Parameter 변경
        flows.open_procedure_setting(ui, "general")
        _click_general_param_combo(ui, flows.PROCEDURE_GENERAL_PARAM_2D, "TEST_2D_A_M.pim")
        flows.setting_update(ui)
        flows.confirm_setting_dialog(ui)
        default_param = ctx.db.scalar(
            "PROCEDURE", "SELECT DefaultImgProcess FROM PROCEDURE_COMMON")
        r.assert_equal(1, "Setting > Procedure > General 2D Default Parameter 저장",
                       "TEST_2D_A_M.pim", default_param,
                       note="PROCEDURE.PROCEDURE_COMMON.DefaultImgProcess 조회")

        # Step 2~4: Preset(2D)에 PRESET_FLOW_A/B 추가 및 매핑
        flows.open_procedure_setting(ui, "preset")
        _add_preset_2d_pair(ui, 1)  # Roll=RL -> RCCRL/LCCRL
        shot_a = _alias_preset_row(ctx, ui, "RCCRL", "PRESET_FLOW_A", "a")
        r.attach(shot_a)

        _add_preset_2d_pair(ui, 2)  # Roll=RM -> RCCRM/LCCRM
        shot_b = _alias_preset_row(ctx, ui, "RCCRM", "PRESET_FLOW_B", "b",
                                   param_filename="TEST_2D_B_M.pim")
        r.attach(shot_b)

        flows.setting_update(ui)
        flows.confirm_setting_dialog(ui)

        presets = {row["Alias"]: row["XIPLParamName"] for row in ctx.db.query(
            "PROCEDURE", "SELECT Alias,XIPLParamName FROM VIEW_POSITION_PRESET "
                        "WHERE Alias IN ('PRESET_FLOW_A','PRESET_FLOW_B')")}
        r.assert_equal(2, "PRESET_FLOW_A 추가 및 Default Parameter 매핑",
                       "TEST_2D_A_M.pim", presets.get("PRESET_FLOW_A"),
                       note="PROCEDURE.VIEW_POSITION_PRESET.Alias/XIPLParamName 조회")
        r.assert_true(3, "PRESET_FLOW_B 추가", "PRESET_FLOW_B" in presets,
                      expected="VIEW_POSITION_PRESET에 PRESET_FLOW_B 존재",
                      actual=presets)
        r.assert_equal(4, "PRESET_FLOW_B Parameter 변경 저장",
                       "TEST_2D_B_M.pim", presets.get("PRESET_FLOW_B"),
                       note="PROCEDURE.VIEW_POSITION_PRESET.XIPLParamName 조회")

        close = [c for c in ui.by_id(4) if c.visible and c.rect[0] > 1700
                 and c.rect[1] < 100]
        if close:
            ui.click(close[0], settle=1.5)

        # Step 5: New Patient에서 DATA_XIPL_PRESET_01 검사 시작
        #
        # 이 TC는 검사를 열어 둔 채 끝난다(마지막에 닫지 않는다). 그래서 재실행
        # 시에는 시작 시점에 이미 Examine 모드이고, 그 상태에서는 Patient 화면의
        # New Patient 탭(2285)에 갈 수 없다. 실측(2026-08-18): 이전 실행이 남긴
        # `XIPL PRESET TEST` 검사가 기본 Procedure 4스텝과 함께 열려 있어
        # Step 5가 "New Patient 탭 컨트롤(2285)을 찾지 못했습니다"로 죽었고,
        # 그 전 실행에서는 그 4스텝을 세어 "Step 등록 실패: 0->4"가 됐다.
        # Q.C 실행 전 검사를 닫아야 하는 것과 같은 종류의 전제 조건이다.
        if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
            # 영상이 없는 잔여 검사는 Close 시 삭제 확인이 뜨고, 사용자 승인에
            # 따라 삭제한다(core/flows.py::confirm_study_delete). 다른 환자의
            # 검사가 지워지는 일은 없어야 하므로 전후 Study Key 집합을 비교해
            # 이 TC의 환자 것만 사라졌는지 확인한다.
            def _study_keys():
                return {int(x["Key"]) for x in ctx.db.query(
                    "DATA", "SELECT [Key] FROM STUDY")}

            def _own_keys():
                return {int(x["Key"]) for x in ctx.db.query(
                    "DATA", "SELECT s.[Key] FROM STUDY s JOIN PATIENT p "
                            "ON p.[Key]=s.PatientKey WHERE p.PatientID=@pid",
                    {"pid": "DATA_XIPL_PRESET_01"})}

            before_studies, own_before = _study_keys(), _own_keys()
            flows.close_examine(ui, option="close", wait=10)
            gone = before_studies - _study_keys()
            if gone - own_before:
                raise flows.FlowError(
                    f"이 TC의 환자가 아닌 검사가 삭제됐습니다: {sorted(gone)} "
                    f"(허용 {sorted(own_before)})")
            if gone:
                r.add(0, "이전 실행의 빈 검사 정리", PASS,
                      expected="DATA_XIPL_PRESET_01의 영상 없는 검사만 삭제",
                      actual={"deleted_study_keys": sorted(gone)},
                      note="촬영 영상이 없는 검사를 Close하면 제품이 삭제 확인을 "
                           "띄운다(사용자 승인). 영상이 있으면 확인 자체가 뜨지 않는다.")
        flows.ensure_patient_screen(ui, wait=3)
        patient_id = "DATA_XIPL_PRESET_01"
        flows.fill_new_patient(ui, patient_id, "XIPL PRESET TEST", sex="F")
        flows.start_examine_from_new_patient(ui, wait=6, on_duplicate="use_existing")
        study = ctx.db.one(
            "DATA", "SELECT TOP 1 s.[Key] FROM STUDY s JOIN PATIENT p "
                    "ON p.[Key]=s.PatientKey WHERE p.PatientID=@pid "
                    "ORDER BY s.[Key] DESC", {"pid": patient_id})
        r.assert_true(5, "New Patient로 검사 시작", bool(study),
                      expected=f"PatientID={patient_id} Study 존재", actual=study)

        # New Patient는 기본 4-View(RCC/LCC/RMLO/LMLO) 템플릿을 자동 등록한다.
        # Demo F8은 "선택된" Step이 아니라 등록 순서대로 다음 미촬영 Step을
        # 채운다(Service Manual: 선택 Step과 획득 영상은 무관). PRESET_FLOW_A/B가
        # 그 다음 순번이 되도록, 이미 등록된 기본 Step을 먼저 모두 촬영해 비운다.
        #
        # 고정 대기(settle=14) 대신 TC_XIPL_compatibility_07(`_acquire_pre_registered_steps`
        # /`_acquire_mode`)과 같은 `vp.wait_new_group` 상태 기반 대기로 바꿨다 — INSTANCE_GROUP이
        # 실제로 늘어나는 것을 신호로 쓴다(2026-08-24 실측: 2D는 14초 고정 대기가 2.8~2.9초로
        # 충분했다). 아래 Step 8이 촬영 직후 그 영상의 Parameter를 바로 읽으므로, 영상이 실제로
        # 커밋되기 전에 읽어 오판정될 위험도 고정 대기보다 줄어든다.
        study_key = int(study["Key"])
        _acquire_pre_registered_steps(ctx, ui, study_key)

        # Step 6~7: 각 Preset으로 2D 1회씩 촬영
        step_a = _add_view_position_by_alias(ui, "PRESET_FLOW_A")
        known_a = set(vp.acquired_groups(ctx.db, study_key))
        acquire_a = flows.demo_acquire_step(ui, step_a, settle=0)
        wait_a = vp.wait_new_group(ctx.db, study_key, known_a,
                                   required_types=vp.INSTANCE_TYPES_2D)
        step_b = _add_view_position_by_alias(ui, "PRESET_FLOW_B")
        known_b = set(vp.acquired_groups(ctx.db, study_key))
        acquire_b = flows.demo_acquire_step(ui, step_b, settle=0)
        wait_b = vp.wait_new_group(ctx.db, study_key, known_b,
                                   required_types=vp.INSTANCE_TYPES_2D)

        # Step 8: 각 영상의 Image Processing 적용 Parameter가 서로 다른지 확인
        vp.select_2d(ui, step_a)
        vp.open_process(ui)
        combo_a = [c for c in ui.by_id(vp.PARAM_COMBO) if c.visible]
        applied_a = ui.combo_value(combo_a[0]) if combo_a else None
        shot_img_a = _ev(ctx, "TC_XIPL_compatibility_04_image_a.png")
        vp.capture_viewer_window(ui, shot_img_a)
        r.attach(shot_img_a)
        vp.cancel_window(ui)

        vp.select_2d(ui, step_b)
        vp.open_process(ui)
        combo_b = [c for c in ui.by_id(vp.PARAM_COMBO) if c.visible]
        applied_b = ui.combo_value(combo_b[0]) if combo_b else None
        shot_img_b = _ev(ctx, "TC_XIPL_compatibility_04_image_b.png")
        vp.capture_viewer_window(ui, shot_img_b)
        r.attach(shot_img_b)
        vp.cancel_window(ui)

        match_a = _parameter_display_matches("TEST_2D_A_M.pim", applied_a or "")
        match_b = _parameter_display_matches("TEST_2D_B_M.pim", applied_b or "")
        r.assert_true(6, "첫 영상(PRESET_FLOW_A)에 TEST_2D_A_M.pim 적용",
                      match_a, expected="TEST_2D_A_M.pim",
                      actual={"acquire": acquire_a, "wait": wait_a,
                              "displayed": applied_a})
        r.assert_true(7, "두 번째 영상(PRESET_FLOW_B)에 TEST_2D_B_M.pim 적용",
                      match_b, expected="TEST_2D_B_M.pim",
                      actual={"acquire": acquire_b, "wait": wait_b,
                              "displayed": applied_b})
        r.assert_true(8, "각 영상에 서로 다른 지정 Parameter 표시",
                      match_a and match_b and applied_a != applied_b,
                      expected="영상별 서로 다른 Parameter",
                      actual={"image_a": applied_a, "image_b": applied_b})

        # 정리는 이제 다음 실행이 스스로 한다(시험 Preset은 UI로 삭제하고,
        # 영상 없는 잔여 검사는 Close 시 삭제 확인을 처리한다). 그래서 예전의
        # "수동 삭제할 것" MANUAL 안내는 더 이상 사실이 아니라 제거했다.
        r.add(0, "정리 절차", PASS,
              expected="다음 실행이 시험 Preset과 잔여 검사를 자동 정리",
              actual="자동 정리(수동 개입 불필요)",
              note="시험 Preset은 _delete_test_presets가 UI로 삭제하고, 영상 없는 "
                   "잔여 검사는 close_examine의 삭제 확인 처리로 정리된다. "
                   "둘 다 삭제 전후 DB 대조로 대상 외 삭제를 막는다.")
    except Exception as exc:
        r.abort(0, "TC_XIPL_compatibility_04 실행", exc)
    finally:
        # Step 1 이 바꾼 `PROCEDURE_COMMON.DefaultImgProcess` 를 되돌린다.
        #
        # 이 TC 는 그동안 이 값을 `TEST_2D_A_M.pim` 으로 **바꿔 놓은 채 끝났다**
        # (2026-08-28 까지). 뒤따르는 TC 가 "2D 기본 파라미터" 를 전제로 판정하면
        # 그 오염을 그대로 물려받는다. **DB 를 직접 고치지 않고 UI 로 되돌린다**
        # (운영 지침 13절 — DB 는 조회 전용).
        _restore_default_2d_param(ctx, r, ui, baseline_param)
    return r


def _restore_default_2d_param(ctx, r, ui, baseline_param):
    """`Setting > Procedure > General` 의 2D Default Parameter 를 되돌린다.

    정리 경로이므로 **무엇을 하든 예외를 밖으로 내지 않는다.** 결과는
    `r.cleanup` 으로 남긴다(`finally` 에서 `r.add(FAIL)` 을 부르면 정리 블록이
    `StepFailed` 를 던져 TC 밖으로 샌다 — `core/result.cleanup` 주석 참고).
    """
    if not baseline_param:
        return
    now = ctx.db.scalar(
        "PROCEDURE", "SELECT DefaultImgProcess FROM PROCEDURE_COMMON")
    if str(now) == str(baseline_param):
        r.cleanup(0, "2D Default Parameter 원복", PASS,
                  expected=baseline_param,
                  actual=f"{now} (바뀌지 않아 되돌릴 것이 없음)")
        return
    try:
        if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
            flows.close_examine(ui, option="close", wait=10)
        flows.ensure_patient_screen(ui, wait=3)
        flows.open_procedure_setting(ui, "general")
        _click_general_param_combo(ui, flows.PROCEDURE_GENERAL_PARAM_2D,
                                   baseline_param)
        flows.setting_update(ui)
        flows.confirm_setting_dialog(ui)
        after = ctx.db.scalar(
            "PROCEDURE", "SELECT DefaultImgProcess FROM PROCEDURE_COMMON")
        r.cleanup(0, "2D Default Parameter 원복",
                  PASS if str(after) == str(baseline_param) else FAIL,
                  expected=baseline_param, actual=after,
                  note="PROCEDURE.PROCEDURE_COMMON.DefaultImgProcess 를 UI 로 "
                       "되돌리고 DB 값으로 확인했다.")
    except Exception as exc:                           # noqa: BLE001
        r.cleanup(0, "2D Default Parameter 원복", FAIL,
                  expected=baseline_param,
                  actual=f"{type(exc).__name__}: {exc}",
                  note="되돌리지 못했다. 다음 실행 전에 Setting > Procedure > "
                       f"General 의 2D Default Parameter 를 {baseline_param!r} "
                       "로 되돌려야 뒤따르는 TC 가 오염된 값을 물려받지 않는다.")


def _last_3d_recon_param(log_text):
    """Q.C 3D(ACR Phantom 3D-N/3D-W) 재구성 시작 로그에서 egp/eap 이름을 읽는다.

    반환하는 `reconstruction_file`(egp)이 3D-N 은 narrow_standard.egp,
    3D-W 는 wide_standard.egp 로 갈린다(2026-08-27 실측). `parameter`(eap)는
    Setting > Q.C 의 3D Default Recon Parameter 하나를 두 항목이 공유한다.
    """
    pattern = re.compile(
        r"Initialize Reconstruction\.\s*\(([^,]+),\s*([^,\)]+)", re.I)
    hits = pattern.findall(log_text)
    if not hits:
        return {}
    egp, eap = hits[-1]
    return {"reconstruction_file": egp.strip(), "parameter": eap.strip()}


_QC_RESULT_COMBOS = {"fiber": 2738, "speck": 2739, "mass": 2740}

#: Q.C 합격 기준이 들어 있는 설정 컬럼. 2D 는 `ACR*`, 3D(Tomo)는 `TomoACR*` 다.
#  값을 코드에 박지 않는다 — 제품이 이 값과 비교해 Pass/Fail 을 정하므로
#  **기준도 제품에서 읽어** 판정한다(2026-08-28 실측: 둘 다 4.0/3.0/3.0).
_QC_THRESHOLD_COLUMNS = {
    "2d": {"fiber": "ACRFiber", "speck": "ACRSpeck", "mass": "ACRMass"},
    "3d": {"fiber": "TomoACRFiber", "speck": "TomoACRSpeck",
           "mass": "TomoACRMass"},
}


def _qc_thresholds(ctx, kind):
    """Setting > Q.C 에 저장된 합격 기준을 읽는다."""
    row = ctx.db.one(
        "CONFIGURATION",
        "SELECT ACRFiber,ACRSpeck,ACRMass,TomoACRFiber,TomoACRSpeck,"
        "TomoACRMass FROM QC_COMMON") or {}
    out = {}
    for key, column in _QC_THRESHOLD_COLUMNS[kind].items():
        try:
            out[key] = float(row.get(column))
        except (TypeError, ValueError):
            raise flows.FlowError(
                f"Q.C 합격 기준 {column} 을 읽지 못했습니다: {row.get(column)!r}")
    return out


def _qc_score_items(ui, combo_id, tesseract_exe=None):
    """열려 있는 Q.C 점수 콤보의 항목을 (컨트롤, 숫자값)으로 읽는다.

    **좌표를 쓰지 않는다.** 예전에는 "합격 기준 이상에 해당하는 값"의 화면
    절대좌표(`1760,364` 등)를 눌렀는데, 그것은 창 위치·해상도가 달라지면 다른
    값을 고르고도 고른 줄 모른다(AGENTS.md 5절). 실제로 22차 회귀에서
    `QC_STUDY.Result=0` 이 나온 원인으로 의심된다 — 기준 미만 값을 골랐는데
    자동화는 "합격 점수를 넣었다"고 기록했다.
    """
    from core import uitext as _uitext

    popups = [w for w in ui.windows() if w.text == "ItemList"]
    if not popups:
        raise flows.FlowError(
            f"Q.C 점수 콤보({combo_id}) 목록이 열리지 않았습니다.")
    items = sorted({c.hwnd: c for c in children(popups[0].hwnd, 4)
                    if c.visible and c.text == "TextButton"}.values(),
                   key=lambda c: c.rect[1])
    out = []
    for item in items:
        text = (_uitext.ocr(item, tesseract_exe) or "").strip()
        match = re.search(r"\d+(?:\.\d+)?", text.replace(",", "."))
        out.append((item, float(match.group()) if match else None, text))
    return out


def _qc_pick_score(ui, key, threshold, want_pass, tesseract_exe=None):
    """Q.C 점수 콤보에서 **경계값**을 골라 누른다.

    `want_pass=True` 면 기준 **이상** 중 가장 낮은 값(= 합격 경계),
    `False` 면 기준 **미만** 중 가장 높은 값(= 불합격 경계)을 고른다.
    경계를 고르는 이유: "기준 이상이면 Pass, 미만이면 Fail" 이라는 제품 로직을
    가장 좁은 간격에서 확인하기 위해서다.

    반환: {"picked": float, "items": [...], "boundary": "pass"|"fail"}
    """
    combo_id = _QC_RESULT_COMBOS[key]
    hits = [c for c in ui.by_id(combo_id) if c.visible]
    if not hits:
        raise flows.FlowError(f"Q.C 결과 콤보 '{key}'(ID {combo_id})를 찾지 못했습니다.")
    ui.click(hits[0], settle=1.0)
    items = _qc_score_items(ui, combo_id, tesseract_exe)
    readable = [(ctrl, value, text) for ctrl, value, text in items
                if value is not None]
    if not readable:
        raise flows.FlowError(
            f"Q.C '{key}' 콤보 항목을 숫자로 읽지 못했습니다: "
            f"{[t for _, _, t in items]}")
    if want_pass:
        candidates = [x for x in readable if x[1] >= threshold]
        chosen = min(candidates, key=lambda x: x[1]) if candidates else None
    else:
        candidates = [x for x in readable if x[1] < threshold]
        chosen = max(candidates, key=lambda x: x[1]) if candidates else None
    if chosen is None:
        raise flows.FlowError(
            f"Q.C '{key}' 콤보에 기준 {threshold} "
            f"{'이상' if want_pass else '미만'}인 항목이 없습니다: "
            f"{[v for _, v, _ in readable]}")
    ui.click(chosen[0], settle=1.0)
    return {"picked": chosen[1], "threshold": threshold,
            "items": [v for _, v, _ in readable],
            "boundary": "pass" if want_pass else "fail"}


def _qc_recover(ui):
    """`_qc_pick_score` 실패로 남은 Q.C 테스트 창을 Cancel 로 닫는다.

    기준 미만/이상 항목을 못 찾으면 `_qc_pick_score` 가 Save 를 누르기 전에
    예외를 던진다 — 창이 열린 채로 남는다. 이 창은 거의 전체화면이라 뒤이은
    메인 메뉴 클릭을 가리고, 실측(2026-08-28)으로 `TC_XIPL_compatibility_05`
    가 Step 4 진입에서 `메인 메뉴가 열리지 않았습니다`로 전체가 중단됐다.

    **한 번만 누르면 안 된다.** `_qc_pick_score` 가 실패할 때 콤보 팝업
    (`ItemList`)이 아직 열려 있을 수 있고, 그 팝업이 마우스를 붙잡고 있어서
    **첫 클릭은 팝업만 닫고 Cancel 은 못 누른다**(2026-08-28 실측 — 예외 없이
    "성공"했는데도 창이 안 닫혔다). 그래서 Cancel 이 안 보일 때까지(=창이
    실제로 닫힐 때까지) 반복한다. 정리 경로이므로 실패해도 예외를 밖으로
    내지 않는다.
    """
    try:
        for _ in range(3):
            cancel = [c for c in ui.controls()
                      if c.ctrl_id == 1102 and c.visible and c.rect[0] > 1500]
            if not cancel:
                return
            ui.click(cancel[0], settle=1.5)
            ui.sweep_dialogs(timeout=2)
    except Exception:                                  # noqa: BLE001
        pass


def _qc_save(ui):
    """Q.C 테스트 창의 Save 를 누른다."""
    save = [c for c in ui.controls()
            if c.ctrl_id == 1103 and c.visible and c.rect[0] > 1500]
    if not save:
        raise flows.FlowError("Q.C 테스트 Save 버튼을 찾지 못했습니다.")
    ui.click(save[0], settle=2.5)


def _qc_set_scores_and_save(ui, thresholds, want_pass=True,
                            fail_item="fiber", tesseract_exe=None):
    """Fiber/Speck/Mass 를 골라 저장한다.

    `want_pass=False` 면 `fail_item` **하나만** 기준 미만으로 넣고 나머지는
    합격 경계로 넣는다. 한 항목만 떨어뜨려야 "그 항목 때문에 Fail 이 됐다"고
    말할 수 있다 — 전부 떨어뜨리면 어느 조건이 작용했는지 구분되지 않는다.
    """
    picked = {}
    for key in _QC_RESULT_COMBOS:
        pass_this = want_pass or key != fail_item
        picked[key] = _qc_pick_score(ui, key, thresholds[key], pass_this,
                                     tesseract_exe)
    _qc_save(ui)
    return picked


def _qc_launch_and_expose(ctx, ui, tile_xy, tag, log_mark, click_time, log_ready):
    """Q.C 창에서 tile_xy의 ▶ 버튼으로 테스트를 열고 Demo(F8)로 촬영한다.

    log_ready(log_text)는 Viewer 로그(타임스탬프로 click_time 이후만 필터)에
    파라미터 적용 완료 로그가 찍혔는지 판정하는 콜백이다. 로그 등장을 완료
    신호로 삼아 고정 sleep 없이 기다린다.
    """
    ui.click(tile_xy, settle=2)
    # ACR Phantom 창은 거의 전체화면 크기라 ui.wait_dialog()의 '작은 #32770'
    # 판정에 걸리지 않는다. 대신 이 창에 고유한 Fiber 결과 콤보(2738)로 확인한다.
    end_open = time.time() + 8
    opened = []
    while time.time() < end_open:
        opened = [c for c in ui.by_id(_QC_RESULT_COMBOS["fiber"]) if c.visible]
        if opened:
            break
        time.sleep(.3)
    if not opened:
        raise flows.FlowError(f"{tag}: Q.C 테스트 창이 열리지 않았습니다.")
    # 캔버스에 포커스를 줘야 F8이 인식된다. **절대 데스크톱 좌표를 쓰지 않는다**
    # (AGENTS.md 5절) — Fiber 결과 콤보(2738)가 속한 Q.C 창의 rect 에서 캔버스
    # 중앙을 계산한다. 이전에는 `(760, 550)` 이 박혀 있어 창 위치나 해상도가
    # 달라지면 엉뚱한 곳을 누를 수 있었다(2026-08-21 점검에서 발견).
    qc_win = _qc_window(ui, opened[0])
    ui.click(_canvas_point(qc_win), settle=.5)
    ui.key("F8", settle=1)
    end = time.time() + 30
    ready = False
    while time.time() < end:
        log_text = _log_lines_from(_viewer_log_since(log_mark), click_time)
        if log_ready(log_text):
            ready = True
            break
        time.sleep(.5)
    if not ready:
        raise flows.FlowError(f"{tag}: F8 촬영 후 파라미터 적용 로그를 확인하지 못했습니다.")
    shot = _ev(ctx, f"TC_XIPL_compatibility_05_{tag}_captured.png")
    vp.capture_viewer_window(ui, shot)
    return shot


def _pick_combo_item(ui, combo, wanted, rounds=8):
    """열려 있는 콤보 팝업을 스크롤하며 *wanted* 항목을 찾아 클릭한다.

    Q.C 파라미터 콤보는 PARAMETER 폴더의 파일을 알파벳 순으로 나열하는데,
    보이는 행이 6개 정도뿐이어서 `TEST_*`처럼 뒤쪽에 오는 이름은 처음 화면에
    없다(2026-08-18 실측: TEST_QC_2D_M.pim은 10개 항목 중 9번째라 화면 밖).
    기존 코드는 스크롤을 딱 한 번(-3)만 해서 닿지 못하고 실패했다. 파일이
    늘어날수록 더 아래로 밀리므로 고정 횟수 대신 찾을 때까지 굴린다.

    스크롤이 끝에 닿아 화면이 더 바뀌지 않으면 중단한다(무한 대기 금지).
    """
    if vp.click_viewer_text(ui, wanted, settle=1.0):
        return True
    cx, cy = combo.center
    previous = None
    for _ in range(rounds):
        ui.wheel((cx, cy + 60), -3, settle=.4)
        if vp.click_viewer_text(ui, wanted, settle=1.0):
            return True
        shot = os.path.join(os.environ.get("TEMP", "."), "bellalun_combo_scroll.png")
        vp.capture_viewer_window(ui, shot)
        try:
            with open(shot, "rb") as stream:
                signature = hashlib.sha256(stream.read()).hexdigest()
        except OSError:
            signature = None
        if signature is not None and signature == previous:
            break                       # 더 굴러도 화면이 같으면 목록 끝
        previous = signature
    return False


def compatibility_05(ctx):
    r = TCResult("TC_XIPL_compatibility_05", "Q.C Default Image Process Parameter")
    root = (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER")
    if not _ensure_test_parameters(ctx, r, "검증용 Q.C Parameter 파일 준비",
                                   [vp.PARAM_QC_2D, vp.PARAM_QC_3D]):
        return r

    cfg = ctx.cfg["viewer"]
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    ui = ViewerUi()
    try:
        ui.ensure_ready(cfg["exe"], cfg["login"]["id"], cfg["login"]["password"])
        flows.ensure_patient_screen(ui)

        # Step 1: Setting > Q.C > Setting 의 2D Default Image Process Parameter 변경
        flows.open_qc_setting(ui, "setting_2d")
        combo2d = [c for c in ui.by_id(flows.QC_PARAM_2D) if c.visible]
        if not combo2d:
            raise flows.FlowError("Q.C 2D Default Parameter 콤보를 찾지 못했습니다.")
        ui.click(combo2d[0], settle=1.0)
        if not _pick_combo_item(ui, combo2d[0], vp.PARAM_QC_2D):
            raise flows.FlowError(
                f"Q.C 2D 콤보에서 {vp.PARAM_QC_2D}을 찾지 못했습니다.")
        flows.setting_update(ui)
        flows.confirm_setting_dialog(ui)

        # Step 2: Setting > Q.C > Setting(3D)의 3D Default Image Process Parameter 변경
        flows.open_qc_setting(ui, "setting_3d")
        combo3d = [c for c in ui.by_id(flows.QC_PARAM_3D) if c.visible]
        if not combo3d:
            raise flows.FlowError("Q.C 3D Default Parameter 콤보를 찾지 못했습니다.")
        ui.click(combo3d[0], settle=1.0)
        if not _pick_combo_item(ui, combo3d[0], vp.PARAM_QC_3D):
            raise flows.FlowError(
                f"Q.C 3D 콤보에서 {vp.PARAM_QC_3D}을 찾지 못했습니다.")
        flows.setting_update(ui)
        flows.confirm_setting_dialog(ui)

        qc_common = ctx.db.one(
            "CONFIGURATION", "SELECT DefaultProcessParam,DefaultReconParam FROM QC_COMMON") or {}
        r.assert_equal(1, "Setting > Q.C > Setting 2D Default Image Process Parameter 저장",
                       "TEST_QC_2D_M.pim", qc_common.get("DefaultProcessParam"),
                       note="CONFIGURATION.QC_COMMON.DefaultProcessParam 조회")
        r.assert_equal(2, "Setting > Q.C > Setting(3D) 3D Default Image Process Parameter 저장",
                       "TEST_QC_3D.eap", qc_common.get("DefaultReconParam"),
                       note="CONFIGURATION.QC_COMMON.DefaultReconParam 조회")

        close = [c for c in ui.by_id(4) if c.visible and c.rect[0] > 1700 and c.rect[1] < 100]
        if close:
            ui.click(close[0], settle=1.5)
        flows.ensure_patient_screen(ui)

        # Step 3: 2D Q.C 항목(ACR Phantom) 1회 촬영
        #
        # Q.C 테스트를 실행하려면 **열려 있던 Examine 검사를 먼저 닫아야 한다**
        # (2026-08-18 사용자 확인). 닫지 않으면 Q.C 창에서 ▶를 눌러도 테스트
        # 창이 뜨지 않는다. 단독 실행에서는 열린 검사가 없어 그냥 통과했고,
        # 회귀에서는 앞선 TC가 남긴 검사 때문에 이 지점에서만 실패했다
        # (실측: "2d: Q.C 테스트 창이 열리지 않았습니다").
        # 이미 Patient 화면이면 close_examine이 할 일이 없으므로, 열려 있을
        # 때만 닫는다. 'close'는 강제 종료가 아니라 정상 종료다(flows 주석 참고).
        if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
            flows.close_examine(ui, option="close", wait=10)
        flows.ensure_patient_screen(ui, wait=3)

        click_time_2d = datetime.now()
        log_mark_2d = _viewer_log_mark(ctx)
        flows.open_qc_tool(ui)
        shot_2d = _qc_launch_and_expose(
            ctx, ui, (343, 223), "2d", log_mark_2d, click_time_2d,
            lambda text: _last_2d_process(text).get("parameter") == "TEST_QC_2D_M.pim")
        r.attach(shot_2d)
        thresholds_2d = _qc_thresholds(ctx, "2d")
        picked_2d = _qc_set_scores_and_save(
            ui, thresholds_2d, want_pass=True, tesseract_exe=tess)
        log_2d = _log_lines_from(_viewer_log_since(log_mark_2d), click_time_2d)
        applied_2d = _last_2d_process(log_2d)
        qc_2d = ctx.db.one(
            "DATA", "SELECT TOP 1 [Key],Result,Detail FROM QC_STUDY WHERE Type=11 "
                    "ORDER BY [Key] DESC") or {}
        r.assert_true(
            3, "2D Q.C(ACR Phantom) 1회 촬영 및 TEST_QC_2D_M.pim 적용",
            applied_2d.get("parameter") == "TEST_QC_2D_M.pim",
            expected="Viewer 로그에 Image Process Param Name:TEST_QC_2D_M.pim 기록",
            actual={"log": applied_2d, "qc_study": qc_2d},
            note="개정본 Expected 3 은 '2D Q.C 영상에 지정 Parameter가 적용된다' 다 "
                 "— **채점 통과(Pass)를 요구하지 않는다.** 그래서 파라미터 적용만 "
                 "판정하고, 채점 로직 자체는 아래에서 경계값 양방향으로 따로 "
                 "확인한다.")

        # Step 3 확장 — **채점 로직을 경계값 양방향으로 검증한다** (2026-08-28
        # 사용자 요청). "기준 이상이면 Pass / 미만이면 Fail" 이 실제로 그렇게
        # 동작하는지 Demo 환경에서 확인하는 것이 목적이다.
        #
        # 예전에는 `QC_STUDY.Result == 1` 을 파라미터 판정에 **묶어서** 요구했다.
        # 그런데 점수를 화면 절대좌표로 골라서(`1760,364`) 무엇을 골랐는지 알 수
        # 없었고, 22차 회귀는 `Result=0` 으로 FAIL 했다. 이제 항목을 OCR 로 읽어
        # **기준 경계값**을 고르므로 무엇을 넣었는지가 판정에 남는다.
        r.assert_true(
            3, "Q.C 채점 — 합격 경계값 입력 시 Pass",
            qc_2d.get("Result") == 1,
            expected={"입력": {k: v["picked"] for k, v in picked_2d.items()},
                      "기준": thresholds_2d, "QC_STUDY.Result": 1},
            actual={"qc_study": qc_2d, "picked": picked_2d},
            note="Setting > Q.C 의 합격 기준(CONFIGURATION.QC_COMMON.ACRFiber/"
                 "ACRSpeck/ACRMass)을 DB 에서 읽어, 각 항목에서 **기준 이상 중 "
                 "가장 낮은 값**(합격 경계)을 골랐다. 기준값을 코드에 박지 않고 "
                 "제품 설정에서 읽으므로 기준이 바뀌어도 따라간다.")

        # 같은 검사에 **기준 미만** 점수를 넣어 다시 저장하면 Fail 이 되는지.
        # Fiber 하나만 떨어뜨린다 — 전부 떨어뜨리면 어느 조건이 작용했는지
        # 구분되지 않는다.
        # 저장된 Q.C 를 다시 여는 경로는 실측하지 않았으므로 **2D Q.C 를 한 번
        # 더 촬영한다.** 이미 검증된 경로(`_qc_launch_and_expose`)를 재사용하는
        # 것이라 추측이 들어가지 않는다. Demo(F8) 촬영이라 비용도 작다.
        fail_picked, qc_2d_fail, fail_note = None, {}, ""
        pass_key = qc_2d.get("Key")
        try:
            click_time_fail = datetime.now()
            log_mark_fail = _viewer_log_mark(ctx)
            flows.open_qc_tool(ui)
            shot_fail = _qc_launch_and_expose(
                ctx, ui, (343, 223), "2d_fail_boundary", log_mark_fail,
                click_time_fail,
                lambda text: _last_2d_process(text).get("parameter")
                == "TEST_QC_2D_M.pim")
            r.attach(shot_fail)
            fail_picked = _qc_set_scores_and_save(
                ui, thresholds_2d, want_pass=False, fail_item="fiber",
                tesseract_exe=tess)
            qc_2d_fail = ctx.db.one(
                "DATA", "SELECT TOP 1 [Key],Result,Detail FROM QC_STUDY "
                        "WHERE Type=11 ORDER BY [Key] DESC") or {}
            if qc_2d_fail.get("Key") == pass_key:
                # 새 행이 생기지 않았다면 위 Pass 행을 다시 읽은 것이다.
                # 그 행으로 Fail 을 주장하면 거짓이 된다.
                fail_note = (f"2D Q.C 를 다시 촬영했는데 QC_STUDY 에 새 행이 "
                             f"생기지 않았다(Key={pass_key} 그대로).")
                fail_picked = None
        except Exception as exc:                       # noqa: BLE001
            fail_note = f"{type(exc).__name__}: {exc}"
            _qc_recover(ui)
        if fail_picked:
            r.assert_true(
                3, "Q.C 채점 — 불합격 경계값 입력 시 Fail",
                qc_2d_fail.get("Result") == 0,
                expected={"입력": {k: v["picked"] for k, v in fail_picked.items()},
                          "기준": thresholds_2d, "QC_STUDY.Result": 0},
                actual={"qc_study": qc_2d_fail, "picked": fail_picked},
                note="Fiber 만 **기준 미만 중 가장 높은 값**(불합격 경계)으로 "
                     "낮추고 나머지는 합격 경계 그대로 두었다. 위 Pass 판정과 "
                     "쌍을 이뤄 '기준 이상이면 Pass, 미만이면 Fail' 이라는 제품 "
                     "채점 로직을 경계에서 확인한다 — 한쪽만 보면 제품이 항상 "
                     "Pass 를 주더라도 통과한다.")
        else:
            r.add(3, "Q.C 채점 — 불합격 경계값 입력 시 Fail", MANUAL,
                  expected="기준 미만 점수 입력 시 QC_STUDY.Result=0",
                  actual=fail_note or "수행하지 못함",
                  note="불합격 경계 확인을 위해 2D Q.C 를 한 번 더 촬영하려 했으나 "
                       "수행하지 못했다. **해제 조건**: 위 사유를 해소한 뒤 다시 "
                       "실행한다. **이 실행으로 말할 수 없는 것**: 기준 미만 "
                       "점수를 넣었을 때 제품이 Fail 로 판정하는지 여부 — 합격 "
                       "쪽만 확인했다.",
                  stop=False)

        # Step 4: 3D Q.C 항목(ACR Phantom 3D-N) 1회 촬영
        click_time_3d = datetime.now()
        log_mark_3d = _viewer_log_mark(ctx)
        flows.open_qc_tool(ui)
        shot_3d = _qc_launch_and_expose(
            ctx, ui, (343, 562), "3d", log_mark_3d, click_time_3d,
            lambda text: _last_3d_recon_param(text).get("parameter") == "TEST_QC_3D.eap")
        r.attach(shot_3d)
        thresholds_3d = _qc_thresholds(ctx, "3d")
        picked_3d = _qc_set_scores_and_save(
            ui, thresholds_3d, want_pass=True, tesseract_exe=tess)
        log_3d = _log_lines_from(_viewer_log_since(log_mark_3d), click_time_3d)
        applied_3d = _last_3d_recon_param(log_3d)
        qc_3d = ctx.db.one(
            "DATA", "SELECT TOP 1 [Key],Result,Detail FROM QC_STUDY WHERE Type=16 "
                    "ORDER BY [Key] DESC") or {}
        r.assert_true(
            4, "3D Q.C(ACR Phantom 3D-N) 1회 촬영 및 TEST_QC_3D.eap 적용",
            applied_3d.get("parameter") == "TEST_QC_3D.eap",
            expected="Viewer 로그에 Initialize Reconstruction(..., TEST_QC_3D.eap) 기록",
            actual={"log": applied_3d, "qc_study": qc_3d},
            note="개정본 Expected 4 는 '3D Q.C 영상에 지정 Parameter가 적용된다' "
                 "다. 채점 결과는 아래에서 따로 판정한다.")
        r.assert_true(
            4, "3D Q.C 채점 — 합격 경계값 입력 시 Pass",
            qc_3d.get("Result") == 1,
            expected={"입력": {k: v["picked"] for k, v in picked_3d.items()},
                      "기준": thresholds_3d, "QC_STUDY.Result": 1},
            actual={"qc_study": qc_3d, "picked": picked_3d},
            note="3D 기준은 CONFIGURATION.QC_COMMON.TomoACRFiber/TomoACRSpeck/"
                 "TomoACRMass 에서 읽는다. 불합격 경계는 2D 에서 확인한다 — "
                 "3D 는 재구성까지 도는 촬영이라 한 번 더 돌리는 비용이 크고, "
                 "채점 로직은 2D/3D 가 같은 구현이다(같은 콤보·같은 Save 경로).")

        # Step 4(확장): 3D Q.C 항목(ACR Phantom 3D-W) 1회 촬영
        #
        # 개정본 범위는 3D-N 하나였지만, 사용자가 "3D 의 모든 경우의 수의
        # 영향성을 보고 싶다"고 요청해 3D-W 를 추가했다(2026-08-27).
        # 제품에 실제로 3D-W 항목이 있는지부터 실측으로 확인했다 — Q.C 창
        # Image Quality (3D) 그룹에 'ACR Phantom (3D-N)'(343,562) 바로 아래
        # 'ACR Phantom (3D-W)'(343,606) 가 존재한다. 1회 수행 실측 결과:
        #   * QC_STUDY.Type = 17 (2D=11, 3D-N=16 과 구분된다)
        #   * 재구성 로그 = Initialize Reconstruction.(wide_standard.egp,
        #     TEST_QC_3D.eap)  ← 3D-N 은 narrow_standard.egp
        # 즉 Default Recon Parameter 는 3D 공용 설정 하나를 쓰되 **재구성
        # 기하는 항목별로 갈린다**. 그래서 파라미터 일치만이 아니라 egp 가
        # wide 인지까지 함께 본다 - 이것이 3D-W 가 정말 wide 로 돌았다는 근거다.
        wide_enabled = (ctx.cfg.get("test_data") or {}).get("include_3d_wide", True)
        applied_3dw = {}
        if wide_enabled:
            click_time_3dw = datetime.now()
            log_mark_3dw = _viewer_log_mark(ctx)
            flows.open_qc_tool(ui)
            shot_3dw = _qc_launch_and_expose(
                ctx, ui, (343, 606), "3d_wide", log_mark_3dw, click_time_3dw,
                lambda text: _last_3d_recon_param(text).get("parameter") == "TEST_QC_3D.eap")
            r.attach(shot_3dw)
            picked_3dw = _qc_set_scores_and_save(
                ui, thresholds_3d, want_pass=True, tesseract_exe=tess)
            log_3dw = _log_lines_from(_viewer_log_since(log_mark_3dw), click_time_3dw)
            applied_3dw = _last_3d_recon_param(log_3dw)
            qc_3dw = ctx.db.one(
                "DATA", "SELECT TOP 1 [Key],Result,Detail FROM QC_STUDY WHERE Type=17 "
                        "ORDER BY [Key] DESC") or {}
            r.assert_true(
                4, "3D Q.C(ACR Phantom 3D-W) 1회 촬영 및 TEST_QC_3D.eap 적용 (커버리지 확장)",
                applied_3dw.get("parameter") == "TEST_QC_3D.eap"
                and applied_3dw.get("reconstruction_file") == "wide_standard.egp"
                and qc_3dw.get("Result") == 1,
                expected="Viewer 로그에 Initialize Reconstruction(wide_standard.egp, "
                         "TEST_QC_3D.eap) 기록, QC_STUDY.Type=17 / Result=Pass",
                actual={"log": applied_3dw, "qc_study": qc_3dw,
                        "picked": picked_3dw, "기준": thresholds_3d},
                note="개정본 범위 밖의 확장이다 — 3D-N/3D-W 두 경우 모두 같은 "
                     "Default Recon Parameter 를 받는지 확인한다. "
                     "config.json > test_data.include_3d_wide 로 끌 수 있다.")
        else:
            r.add(4, "3D Q.C(ACR Phantom 3D-W) 1회 촬영 (커버리지 확장)", SKIP,
                  expected="ACR Phantom (3D-W) 수행",
                  actual="test_data.include_3d_wide=false 로 비활성",
                  note="3D-W 픽스처를 끈 설정에서는 수행하지 않는다.")

        # Step 5: 각 Q.C 영상의 적용 Parameter가 설정값과 일치
        expected_param = {"2D": "TEST_QC_2D_M.pim", "3D-N": "TEST_QC_3D.eap"}
        actual_param = {"2D": applied_2d.get("parameter"),
                        "3D-N": applied_3d.get("parameter")}
        param_ok = (applied_2d.get("parameter") == "TEST_QC_2D_M.pim"
                    and applied_3d.get("parameter") == "TEST_QC_3D.eap")
        if wide_enabled:
            expected_param["3D-W"] = "TEST_QC_3D.eap"
            actual_param["3D-W"] = applied_3dw.get("parameter")
            param_ok = param_ok and applied_3dw.get("parameter") == "TEST_QC_3D.eap"
        r.assert_true(5, "각 Q.C 영상의 적용 Parameter가 설정값과 일치",
                      param_ok, expected=expected_param, actual=actual_param)
    except Exception as exc:
        r.abort(0, "TC_XIPL_compatibility_05 실행", exc)
    return r


def compatibility_06(ctx, session):
    r = TCResult("TC_XIPL_compatibility_06", "XIPL Parameter 저장 후 Viewer 적용")
    ui = session["ui"]
    root = (ctx.cfg.get("xipl") or {}).get("parameter_dir", r"C:\XIPL\PARAMETER")
    saved_path = os.path.join(root, "TEST_XIPL_SAVED_M.pim")
    field_name, target_value = "Contrast", 15
    try:
        # TC_04/05는 각자 Setting과 Q.C 화면으로 이동하고 시험 검사를 되돌리지
        # 않는다. 그래서 회귀 순서(01~06)에서 이 TC에 올 때는 세션이 열어 둔
        # 검사가 화면에 없다(2026-08-18 실측: "Step이 0개라 1번째를 선택할 수
        # 없습니다"로 즉시 실패). 앞선 TC의 화면 상태에 기대지 않고, 스텝이
        # 안 보이면 픽스처를 다시 열어 자기 전제를 스스로 만든다.
        if not flows.step_items(ui):
            session = vp.open_test_study(ctx)
            ui = session["ui"]
        vp.select_2d(ui, session["step_2d"])

        studio, studio_ui = _launch_xipl(ctx, ui)
        shot_xipl = _ev(ctx, "TC_XIPL_compatibility_06_xipl.png")
        overlay = studio.capture_first_overlay(shot_xipl)
        r.attach(shot_xipl)
        r.assert_true(1, "Tool의 XIPL 기능 실행", bool(studio_ui.pid),
                      expected="Viewer XIPL tool(1160) 실행 후 XIPL.STUDIO PID 생성",
                      actual={"pid": studio_ui.pid, "overlay": overlay})

        before_shot = _ev(ctx, "TC_XIPL_compatibility_06_before.png")
        before_parameter = studio.read_applied_parameter(before_shot)
        before_name = str(before_parameter.get("parameter") or "")
        if not before_name.lower().endswith(".pim"):
            # Same race already handled in compatibility_01: XIPL occasionally
            # renders the correct raster/WL while its PIM editor remains
            # "Untitled", so set_pim_field would silently edit the wrong (or
            # no) document. Reinvoke once from the same selected Viewer
            # instance and re-read before proceeding.
            _stop_xipl()
            ui.activate()
            vp.select_2d(ui, session["step_2d"])
            studio, studio_ui = _launch_xipl(ctx, ui)
            shot_xipl = _ev(ctx, "TC_XIPL_compatibility_06_xipl_retry.png")
            overlay = studio.capture_first_overlay(shot_xipl)
            r.attach(shot_xipl)
            before_parameter = studio.read_applied_parameter(before_shot)
        field_change = studio.set_pim_field(field_name, target_value)
        preview_shot = _ev(ctx, "TC_XIPL_compatibility_06_preview.png")
        studio.capture(preview_shot)
        r.attach(preview_shot)
        r.assert_true(2, "변경 값이 XIPL Preview에 적용",
                      field_change["after"] == target_value,
                      expected={"field": field_name, "value": target_value},
                      actual={"before_parameter": before_parameter, "change": field_change})

        if os.path.exists(saved_path):
            os.remove(saved_path)
        studio.save_as(saved_path, wait=2)
        r.assert_true(3, "새 Parameter 파일 생성",
                      os.path.isfile(saved_path),
                      expected=saved_path, actual=os.path.isfile(saved_path))

        _stop_xipl()
        ui.activate()

        # Step 4: Viewer로 돌아와 대상 영상(IMG_FLOW_2D_01, InstanceType=0) 선택
        vp.select_2d(ui, session["step_2d"])
        source_2d = [row for row in session["instances"]
                     if int(row["InstanceType"]) == 0]
        r.assert_true(4, "Viewer로 돌아와 대상 영상 선택",
                      len(source_2d) == 1 and bool(source_2d[0].get("ImageInstanceUID")),
                      expected="InstanceType=0 한 건과 고유 Image Instance UID",
                      actual=source_2d)

        # Step 5: Image Processing에서 저장한 Parameter 선택
        # Viewer는 Parameter를 "선택"하는 순간 XIPL ImageProcess를 돌리고
        # "Image Process Param Name:<file>, Contrast: ...\" 로그를 남긴다.
        # Apply 자체는 이 로그를 다시 남기지 않으므로(창을 닫고 ImageAction
        # 결과 파일만 쓴다), Apply 클릭 이후 구간에서 이 로그를 찾으면
        # 존재할 수 없는 증거를 기다리게 된다. TC_02는 Apply 전에 Preview를
        # 눌러 이 로그를 만들지만 TC_06 흐름에는 Preview가 없다. 그래서
        # 파일명/값 로그 증거는 "선택" 구간에서 확보한다.
        select_log_mark = _viewer_log_mark(ctx)
        vp.open_process(ui)
        name = vp.select_test_parameter(ui, "TEST_XIPL_SAVED_M.pim")
        selected_state = _read_state_retry(vp.read_2d_parameter_state, ui)
        selected_log = _last_2d_process(_viewer_log_since(select_log_mark))
        shot_selected = _ev(ctx, "TC_XIPL_compatibility_06_selected.png")
        vp.capture(shot_selected)
        r.attach(shot_selected)
        log_name_ok = (vp._parameter_name_key(selected_log.get("parameter")) ==
                       vp._parameter_name_key("TEST_XIPL_SAVED_M.pim"))
        log_value_ok = selected_log.get("values", {}).get(field_name) == target_value
        r.assert_true(
            5, "저장한 Parameter가 목록에 표시되고 선택됨",
            _parameter_display_matches("TEST_XIPL_SAVED_M.pim", name)
            and selected_state.get(field_name) == target_value
            and log_name_ok and log_value_ok,
            expected={"parameter": "TEST_XIPL_SAVED_M.pim", field_name: target_value},
            actual={"displayed_parameter": name, "values": selected_state,
                    "selected_log": selected_log})

        # Step 6: Apply 실행 → 대상 영상에 변경된 세부 설정 적용
        action_before = _directory_state(
            os.path.join(ctx.cfg["data_dir"], "Image", "ImageAction"))
        ui.click([c for c in ui.by_id(vp.APPLY) if c.visible][0], settle=1)
        apply_limit = float((ctx.cfg.get("xipl") or {}).get("apply_2d_wait", 30))

        def _saved_apply_complete():
            files_after = _directory_state(
                os.path.join(ctx.cfg["data_dir"], "Image", "ImageAction"))
            delta = _new_files(action_before, files_after)
            closed = not [c for c in ui.by_id(vp.APPLY) if c.visible]
            detail = {"window_closed": closed, "image_action_files": delta}
            return (closed and bool(delta),
                    "file/control completion detected", detail)

        _poll_completion(r, "TEST_XIPL_SAVED Apply", _saved_apply_complete, apply_limit)
        applied_log = selected_log

        vp.open_process(ui)
        reopened_name = [c for c in ui.by_id(vp.PARAM_COMBO) if c.visible][0].text
        reopened_state = _read_state_retry(vp.read_2d_parameter_state, ui)
        verify_shot = _ev(ctx, "TC_XIPL_compatibility_06_result.png")
        vp.capture(verify_shot)
        r.attach(verify_shot)
        retained = (_parameter_display_matches("TEST_XIPL_SAVED_M.pim", reopened_name)
                    and reopened_state.get(field_name) == target_value)
        r.assert_true(
            6, "변경된 세부 설정이 대상 영상에 적용",
            retained,
            expected={"parameter": "TEST_XIPL_SAVED_M.pim", field_name: target_value},
            actual={"displayed_parameter": reopened_name, "values": reopened_state,
                    "applied_log": applied_log},
            note="Apply 후 Image Processing에 재진입하여 UI 표시값을 다시 읽어 비교")
        vp.cancel_window(ui)
    except Exception as exc:
        _stop_xipl()
        try:
            vp.cancel_window(ui)
        except Exception:
            pass
        r.abort(0, "TC_XIPL_compatibility_06 실행", exc)
    return r


# =====================================================================
#  TC_XIPL_compatibility_07 — 촬영 모드별 3D Default Recon Parameter 적용
# =====================================================================
#
# ## 기준 문서 (AGENTS.md 0절)
#
# TC 원문: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`
#          `TC_XIPL_compatibility_07` (2026-08-24 추가, 9단계)
#
# 기대 동작의 근거
#
# | 문서 | 확인한 내용 |
# |---|---|
# | 사양서1 186쪽 **SRS 03-10-110** | "3D Viewposition은 촬영 모드 (Narrow / Wide)에 **따라 각각** Reconstruction Parameter를 설정한다.(.xtp)" / "기본 영상 처리 파라미터는 Setting > Procedure > General 에서 설정할 수 있다" / "촬영을 진행한 Viewposition이 Preset으로 등록되어 있는 경우 해당 Viewposition에 설정해 놓은 영상 처리 파라미터로 영상처리를 진행한다" / "2D License의 경우 Reconstruction Parameter 설정 항목이 표시되지 않는다" |
# | 사양서1 196쪽 **SRS 03-30-20** | 설정 가능한 3D Viewposition = `CC, MLO, LM, SIO, ML, LMO, ISO, XCCL, XCCM, AT, TAN`, "FB 및 CV는 촬영 불가" |
# | 사양서1 277쪽 **SRS 03-50-230** | "영상을 획득 시 설정한 xtp 파일을 Combo 박스에 자동으로 선택된다" / "Apply를 누르게 되면 해당 img 파일에 영상 조정 파라미터 값들이 저장된다" / Post Reconstruction↔XTP 항목 매핑표 |
# | Service Manual `Procedure 그룹 > General 메뉴` | `Reconstruction parameter for 3D-N` = "3D Narrow 촬영 View Position에 적용되는 Recon 파라미터", `for 3D-W` = Wide. "Preset에 새로 추가하는 View Position이나 영상 처리 파라미터 및 Recon 파라미터가 등록되어 있지 않은 View Position을 촬영할 때, Default로 설정한 파라미터를 적용합니다." "Tomo 촬영을 지원하지 않는 시스템이 연결되어 있거나 2D 전용 License가 등록되어 있을 경우, Reconstruction Parameter를 설정하는 항목은 표시되지 않습니다." |
# | Service Manual `Preset 메뉴` | 목록 열 = `Name / Alias / XIPL Param(2D) / Recon Param(3D)`. "Preset은 2D / 3D-N / 3D-W 각각 총 40개씩" |
#
# ## `TC_XIPL_compatibility_04`(2D)와 무엇이 다른가
#
# `_04`는 **Preset별**로 2D 파라미터가 갈리는지 본다(Preset 2개 추가 → 각각 촬영).
# `_07`은 **촬영 모드별**(Narrow/Wide)로 3D Recon 파라미터가 갈리는지 본다. 사양이
# 3D에만 요구하는 축이 모드이고(`SRS 03-10-110`), 2D에는 이 축이 아예 없다. 그래서
# 중복이 아니다 — `_04`가 못 보는 것을 본다.
#
# ## 판정 근거를 어디서 읽는가
#
# 적용된 3D Recon 파라미터 **이름은 DB에 없다.** `DATA` 데이터베이스의 컬럼을
# 전수 조회해 확인했다(2026-08-24). 그래서 두 곳을 교차로 읽는다.
#
#   1. **`.img` 파일의 `<ReconParam>`** — `core/imginfo.py`. 사양서1이 저장 위치로
#      명시한 곳이고 `XtpName`/`EgpName`이 그대로 들어 있다. 화면보다 강한 증거다.
#   2. **Post Reconstruction 창의 Parameter 콤보** — 사양서1 277쪽이 "획득 시
#      설정한 xtp가 자동 선택된다"고 정한 화면 표시. 파일과 대조해 둘이 어긋나면
#      제품 결함이다.
#
# 촬영 모드 자체는 `INSTANCE_GROUP.Type/ExposureMode`(1=Narrow, 2=Wide,
# `tests/system_compat.py`에서 대조 확정)로 확정한다.
#
# ## SKIP 기준 (AGENTS.md 7절)
#
# Reconstruction Parameter 설정 항목이 **화면에 없으면** Tomo 미지원 시스템이거나
# 2D 전용 License다(Service Manual). 그때는 이 TC의 검증 대상 자체가 없으므로
# **실제로 화면을 열어 확인한 그 단계에서** SKIP한다. 다른 이유로 콤보를 못 찾은
# 것과 구분하기 위해 두 콤보가 **모두** 없을 때만 SKIP이고, 하나만 없으면 FAIL이다.
#
# GPU 미탑재는 이 TC의 SKIP 사유가 **아니다.** `_03`과 달리 여기서는
# Reconstruction을 다시 돌리지 않고 촬영 결과만 읽는다. 촬영 자체가 GPU 없이
# 성립하지 않으면 Step 5/6이 정직하게 FAIL해야 한다.

#: 사양서1 196쪽 SRS 03-30-20 의 "설정 가능한 3D Viewposition" 11종.
#: `PROCEDURE.VIEW_POSITION_POSITIONING.Name` 과 같은 표기다.
SPEC_3D_VIEW_POSITIONS = ("CC", "MLO", "LM", "SIO", "ML", "LMO", "ISO",
                          "XCCL", "XCCM", "AT", "TAN")
#: 같은 절의 "FB 및 CV는 촬영 불가".
SPEC_3D_EXCLUDED_POSITIONS = ("FB", "CV")

#: `VIEW_POSITION_PRESET.Type` / `INSTANCE_GROUP.ExposureMode` 의 모드 값.
#: Type 은 2026-08-24 실측(Type=1/2 각 11개 Positioning = 사양 11종과 일치),
#: ExposureMode 는 `tests/system_compat.py` 가 대조 확정한 값이다.
XIPL07_MODES = (
    {"key": "3d", "label": "3D-N", "preset_type": 1, "exposure_mode": 1,
     "combo": flows.PROCEDURE_GENERAL_PARAM_3D_N, "param": vp.PARAM_3D_NARROW,
     "db_column": "DefaultReconNarrow",
     "caption": "3D-N", "rotation": "-7.5~7.5도"},
    {"key": "3d-w", "label": "3D-W", "preset_type": 2, "exposure_mode": 2,
     "combo": flows.PROCEDURE_GENERAL_PARAM_3D_W, "param": vp.PARAM_3D_WIDE,
     "db_column": "DefaultReconWide",
     "caption": "3D-W", "rotation": "-15~15도"},
)

XIPL07_PATIENT_ID = "DATA_XIPL_3D_01"
XIPL07_PATIENT_NAME = "XIPL 3D PARAM TEST"


def _procedure_defaults(ctx):
    """`PROCEDURE.PROCEDURE_COMMON` 의 Default 파라미터 3개."""
    row = ctx.db.one(
        "PROCEDURE", "SELECT DefaultImgProcess,DefaultReconNarrow,"
                     "DefaultReconWide FROM PROCEDURE_COMMON")
    return dict(row or {})


def _set_default_recon(ui, mode, filename, ctx=None, attempts=3):
    """Setting > Procedure > General 에서 한 모드의 Default Recon Parameter 변경.

    `ctx` 를 주면 **저장 후 DB 로 확인하고 어긋나면 다시 시도**한다. 화면 조작이
    조용히 빗나가는 것을 마지막에 잡는 결정적 사후 확인이다 —
    `PROCEDURE.PROCEDURE_COMMON` 은 추측이 개입하지 않는 근거다.

    2026-08-24/25 에 이 자리에서 두 번 조용히 실패했다(콤보 후보를 좌표로 고르려던
    시도). 이제 `_click_general_param_combo` 가 표시값으로 한 번, 여기서 DB 로 한 번
    확인한다.
    """
    detail = []
    for attempt in range(1, attempts + 1):
        flows.open_procedure_setting(ui, "general")
        picked = _click_general_param_combo(ui, mode["combo"], filename)
        flows.setting_update(ui)
        flows.confirm_setting_dialog(ui)
        if ctx is None:
            return {"attempts": attempt, "picked": picked, "verified": None}
        saved = _procedure_defaults(ctx).get(mode["db_column"])
        detail.append({"attempt": attempt, "picked": picked, "db": saved})
        if saved == filename:
            return {"attempts": attempt, "picked": picked, "verified": True,
                    "detail": detail}
        time.sleep(.5)
    raise flows.FlowError(
        f"{mode['label']} Default Recon Parameter 를 {filename!r} 로 저장하지 "
        f"못했습니다(DB {mode['db_column']} 가 따라오지 않음). 시도={detail}")


def _recon_combos_present(ui):
    """General 페이지에 3D-N/3D-W Recon Parameter 콤보가 보이는지."""
    return {mode["label"]: bool([c for c in ui.by_id(mode["combo"]) if c.visible])
            for mode in XIPL07_MODES}


def _preset_recon_rows(ctx, preset_type):
    """한 모드(`Type`)의 Preset 행을 Positioning 이름과 함께 돌려준다."""
    return ctx.db.query(
        "PROCEDURE",
        "SELECT p.[Key],p.Type,p.Laterality,p.Alias,p.XIPLParamName,"
        "       g.Name AS PositionName "
        "FROM VIEW_POSITION_PRESET p "
        "JOIN VIEW_POSITION_POSITIONING g ON g.[Key]=p.PositioningKey "
        "WHERE p.Type=@t ORDER BY p.[Key]", {"t": int(preset_type)})


def _preset_recon_summary(rows):
    """Preset 행 목록을 `{위치 이름 집합, 파라미터 집합, 행 수}` 로 요약한다."""
    return {"positions": sorted({str(r["PositionName"]) for r in rows}),
            "parameters": sorted({str(r["XIPLParamName"] or "") for r in rows}),
            "rows": len(rows)}


#: Preset 페이지에서 **실제로 읽히는 단어**와 최소 등장 횟수 (2026-08-24 실측).
#:
#: 화면 구성은 `Preset (2D)` / `Preset (3D-N)` / `Preset (3D-W)` 세 목록이고,
#: 열 이름이 2D 는 `XIPL Param`, 3D 는 `Recon Param` 이다 — Service Manual
#: `Preset 메뉴` 의 표(`Name / Alias / XIPL Param(2D) / Recon Param(3D)`)와 일치한다.
#:
#: **다중 단어로는 찾을 수 없다.** `find_text_boxes` 는 OCR 의 *단어* 박스를
#: 대조하므로 `"Recon Param"` 은 0건이다. 그리고 `"3D-N"` 도 0건이다 — 제목이
#: 괄호까지 한 단어로 읽혀 `"(3D-N)"` 이어야 한다. 처음에 `"3D-N"` 으로 찾다가
#: Step 3 이 FAIL 했고, 캡처로 실제 판독을 확인해 고쳤다(추측하지 않았다).
XIPL07_PRESET_PAGE_WORDS = {
    "(3D-N)": 1,      # Preset (3D-N) 목록 제목
    "(3D-W)": 1,      # Preset (3D-W) 목록 제목
    "Recon": 2,       # 3D 목록 두 개의 `Recon Param` 열 이름
    "XIPL": 1,        # 2D 목록의 `XIPL Param` 열 이름 (대조군)
}


def _preset_page_words(shot):
    """Preset 페이지 캡처에서 위 단어들의 등장 횟수를 읽는다."""
    counts = {}
    for word in XIPL07_PRESET_PAGE_WORDS:
        try:
            counts[word] = len(vp.find_text_boxes(shot, word))
        except Exception as exc:                       # noqa: BLE001
            counts[word] = f"<ocr err {exc}>"
    return counts


def _preset_page_captions(ctx, ui, r):
    """Setting > Procedure > Preset 화면이 모드별 목록을 표시하는지 OCR 로 읽는다.

    3D-N/3D-W 목록의 **컨트롤 ID 는 실측되지 않았다**(2D 목록만 2554 로 확정돼
    있다). 그래서 목록을 조작하지 않고, 화면에 그 두 항목과 **문서에 적힌 열
    이름**이 표시되는지만 확인한다. 조작이 필요 없는 이유는 판정 대상이
    Setting > Procedure > General 의 모드별 Default 이기 때문이다(체크리스트 Step 1~2).

    반환: {"ocr": {단어: 횟수}, "ok": bool, "shot": 경로}
    """
    flows.open_procedure_setting(ui, "preset")
    shot = _ev(ctx, "TC_XIPL_compatibility_07_preset_page.png")
    vp.capture_viewer_window(ui, shot)
    r.attach(shot)
    counts = _preset_page_words(shot)
    ok = all(isinstance(counts.get(word), int)
             and counts[word] >= need
             for word, need in XIPL07_PRESET_PAGE_WORDS.items())
    return {"ocr": counts, "ok": ok, "shot": shot}


def _acquire_pre_registered_steps(ctx, ui, study_key):
    """New Patient 가 자동 등록한 기본 2D Step 을 먼저 비운다.

    `TC_XIPL_compatibility_04` 가 같은 이유로 같은 일을 한다 — New Patient 는
    기본 4-View 템플릿을 등록하고, 그 미촬영 Step 이 남아 있으면 이후 F8 이
    의도한 3D Step 이 아니라 그것을 채울 수 있다. 두 해석 중 어느 쪽이어도
    안전하도록 **먼저 비운다.**

    고정 대기 대신 `vp.wait_new_group` 으로 DB 에 영상이 들어오는 것을 기다린다.
    """
    outcome = []
    total = len(flows.step_items(ui))
    for index in range(1, total + 1):
        known = set(vp.acquired_groups(ctx.db, study_key))
        info = flows.demo_acquire_step(ui, index, settle=0)
        if info.get("skipped"):
            outcome.append(info)
            continue
        waited = vp.wait_new_group(ctx.db, study_key, known,
                                  required_types=vp.INSTANCE_TYPES_2D,
                                  timeout=120)
        info["wait"] = {"waited": waited["waited"],
                        "timed_out": waited["timed_out"]}
        outcome.append(info)
    return {"pre_registered_steps": total, "acquired": outcome}


def _acquire_mode(ctx, ui, study_key, mode):
    """한 모드의 View Position 을 등록하고 1회 Demo 촬영한다.

    반환: {"step":.., "acquire":.., "group":.., "instances":.., "wait":..}
    """
    step = vp.add_view_position(ui, mode["key"])
    known = set(vp.acquired_groups(ctx.db, study_key))
    info = flows.demo_acquire_step(ui, step, settle=0)
    if info.get("skipped"):
        return {"step": step, "acquire": info, "group": None, "instances": [],
                "wait": None}
    xipl_cfg = ctx.cfg.get("xipl") or {}
    waited = vp.wait_new_group(
        ctx.db, study_key, known, required_types=vp.INSTANCE_TYPES_3D,
        timeout=float(xipl_cfg.get("acquire_3d_timeout", 240)))
    return {"step": step, "acquire": info, "group": waited["group"],
            "instances": waited["instances"],
            "wait": {"waited": waited["waited"],
                     "timed_out": waited["timed_out"]}}


def _read_applied_recon(ctx, ui, mode, study_key, acquired):
    """한 모드 영상의 적용 Recon Parameter 를 **화면과 파일 두 곳에서** 읽는다.

    화면: Post Reconstruction 창의 Parameter 콤보(사양서1 277쪽 — 획득 시 설정한
          xtp 가 자동 선택된다).
    파일: Reconstruction 결과 영상(`InstanceType=2`)의 `<ReconParam>`.
    """
    out = {"displayed": None, "file": None, "img_path": None, "shot": None,
            "error": None}
    try:
        vp.select_3d_raw(ui, acquired["step"])
        vp.open_post_reconstruction(ui)
        combo = [c for c in ui.by_id(vp.PARAM_COMBO) if c.visible]
        out["displayed"] = ui.combo_value(combo[0]) if combo else None
        shot = _ev(ctx, f"TC_XIPL_compatibility_07_{mode['label']}_postrecon.png")
        vp.capture_viewer_window(ui, shot)
        out["shot"] = shot
    finally:
        try:
            vp.cancel_window(ui)
        except Exception:                              # noqa: BLE001
            pass
    recon = [row for row in acquired["instances"]
             if int(row["InstanceType"]) == 2]
    if recon:
        path = imginfo.instance_image_path(ctx.cfg["data_dir"], study_key,
                                           int(recon[0]["Key"]))
        out["img_path"] = path
        if path:
            try:
                out["file"] = imginfo.recon_param(path)
            except imginfo.ImgInfoError as exc:
                out["error"] = str(exc)
        else:
            out["error"] = "Reconstruction 영상의 .img 파일을 찾지 못했습니다."
    else:
        out["error"] = "InstanceType=2(Reconstruction) 영상이 없습니다."
    return out


def compatibility_07(ctx):
    r = TCResult("TC_XIPL_compatibility_07",
                 "촬영 모드별 3D Default Recon Parameter 적용")
    needed = [mode["param"] for mode in XIPL07_MODES]
    if not _ensure_test_parameters(ctx, r, "검증용 3D Recon Parameter 파일 준비",
                                   needed):
        return r

    before_defaults = _procedure_defaults(ctx)
    r.add(0, "시험 전 Default Parameter 기록", PASS,
          expected="복원 대상 값 확보",
          actual=before_defaults,
          note="Step 9 에서 이 값으로 되돌린다. 3D-N/3D-W 는 각각 "
               "PROCEDURE.PROCEDURE_COMMON.DefaultReconNarrow / DefaultReconWide.")

    cfg = ctx.cfg["viewer"]
    ui = ViewerUi()
    restored = None
    study_key = None
    completed = False
    try:
        ui.ensure_ready(cfg["exe"], cfg["login"]["id"], cfg["login"]["password"])
        flows.ensure_patient_screen(ui)

        # --- Step 1~2: 모드별 Default Recon Parameter 변경 -----------------
        flows.open_procedure_setting(ui, "general")
        present = _recon_combos_present(ui)
        general_shot = _ev(ctx, "TC_XIPL_compatibility_07_general.png")
        vp.capture_viewer_window(ui, general_shot)
        r.attach(general_shot)
        if not any(present.values()):
            # 실제로 화면을 열어 확인한 이 단계에서만 판단한다(AGENTS.md 7절).
            r.skip(1, "3D-N/3D-W Default Recon Parameter 설정 항목",
                   "Setting > Procedure > General 에 Reconstruction Parameter "
                   "설정 항목이 없다. Service Manual 'Procedure 그룹 > General "
                   "메뉴' — \"Tomo 촬영을 지원하지 않는 시스템이 연결되어 있거나 "
                   "2D 전용 License가 등록되어 있을 경우, Reconstruction Parameter"
                   "를 설정하는 항목은 표시되지 않습니다.\" 이 환경에는 검증 대상이 "
                   "없으므로 TC 전체를 수행하지 않는다.",
                   expected="3D-N/3D-W Recon Parameter 콤보 표시",
                   actual=present)
            return r
        if not all(present.values()):
            r.add(1, "3D-N/3D-W Default Recon Parameter 설정 항목", FAIL,
                  expected="두 콤보가 함께 표시(사양서1 SRS 03-10-110 — 모드별 "
                           "각각 설정)",
                  actual=present,
                  note="한쪽만 없는 것은 '3D 미지원'으로 설명되지 않는다. "
                       "미지원이면 두 항목이 함께 사라진다(Service Manual).")
            return r

        for index, mode in enumerate(XIPL07_MODES, start=1):
            _set_default_recon(ui, mode, mode["param"], ctx=ctx)
            saved = _procedure_defaults(ctx)
            if index == 1:
                r.assert_equal(
                    1, f"{mode['label']} Default Recon Parameter 저장",
                    mode["param"], saved.get(mode["db_column"]),
                    note=f"PROCEDURE.PROCEDURE_COMMON.{mode['db_column']} 조회. "
                         + specs.cite(ctx, r"기본 영상 처리 파라미터는 Setting > "
                                           r"Procedure > General"))
            else:
                other = XIPL07_MODES[0]
                r.assert_true(
                    2, f"{mode['label']} 저장 및 {other['label']} 설정 유지",
                    saved.get(mode["db_column"]) == mode["param"]
                    and saved.get(other["db_column"]) == other["param"],
                    expected={other["db_column"]: other["param"],
                              mode["db_column"]: mode["param"]},
                    actual=saved,
                    note="모드별로 **각각** 설정된다는 것이 이 TC 의 핵심이다. "
                         + specs.cite(ctx, r"촬영 모드 \(Narrow / Wide\)에 따라 "
                                           r"각각 Reconstruction"))

        # --- Step 3: Preset 화면의 모드별 Recon Parameter 목록 -------------
        captions = _preset_page_captions(ctx, ui, r)
        per_mode = {}
        for mode in XIPL07_MODES:
            rows = _preset_recon_rows(ctx, mode["preset_type"])
            per_mode[mode["label"]] = _preset_recon_summary(rows)
        spec_ok = all(
            set(per_mode[mode["label"]]["positions"]) == set(SPEC_3D_VIEW_POSITIONS)
            for mode in XIPL07_MODES)
        excluded_ok = all(
            not (set(per_mode[mode["label"]]["positions"])
                 & set(SPEC_3D_EXCLUDED_POSITIONS))
            for mode in XIPL07_MODES)
        listed_ok = bool(captions["ok"])
        r.assert_true(
            3, "3D-N/3D-W Recon Parameter 가 모드별로 각각 표시",
            listed_ok and spec_ok and excluded_ok,
            expected={"화면 단어(최소 횟수)": dict(XIPL07_PRESET_PAGE_WORDS),
                      "모드별 View Position": list(SPEC_3D_VIEW_POSITIONS),
                      "촬영 불가(목록에 없어야 함)": list(SPEC_3D_EXCLUDED_POSITIONS)},
            actual={"ocr": captions["ocr"], "preset": per_mode},
            note="화면 표시는 Preset 페이지 OCR 로 확인한다 — 목록 제목 "
                 "`Preset (3D-N)`/`Preset (3D-W)` 과 열 이름 `Recon Param` 2개, "
                 "대조군으로 2D 의 `XIPL Param` 1개. 열 이름은 Service Manual "
                 "`Preset 메뉴` 의 표(`Name / Alias / XIPL Param(2D) / "
                 "Recon Param(3D)`)와 같다. 구성은 "
                 "PROCEDURE.VIEW_POSITION_PRESET × VIEW_POSITION_POSITIONING "
                 "전수 대조. " + specs.cite(ctx, r"설정 가능한 3D Viewposition"))

        close = [c for c in ui.by_id(4) if c.visible and c.rect[0] > 1700
                 and c.rect[1] < 100]
        if close:
            ui.click(close[0], settle=1.5)

        # --- Step 4: 시험 검사 시작 ---------------------------------------
        # 이전 실행이 검사를 열어 둔 채 끝났으면 New Patient 탭에 갈 수 없다
        # (`_04` 와 같은 전제). 영상 없는 잔여 검사만 닫는다.
        if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
            flows.close_examine(ui, option="close", wait=10)
        flows.ensure_patient_screen(ui, wait=3)
        flows.fill_new_patient(ui, XIPL07_PATIENT_ID, XIPL07_PATIENT_NAME,
                               sex="F")
        flows.start_examine_from_new_patient(ui, wait=6,
                                             on_duplicate="use_existing")
        study = ctx.db.one(
            "DATA", "SELECT TOP 1 s.[Key] FROM STUDY s JOIN PATIENT p "
                    "ON p.[Key]=s.PatientKey WHERE p.PatientID=@pid "
                    "ORDER BY s.[Key] DESC", {"pid": XIPL07_PATIENT_ID})
        study_key = int(study["Key"]) if study else None
        r.assert_true(4, "New Patient 로 시험 검사 시작", bool(study_key),
                      expected=f"PatientID={XIPL07_PATIENT_ID} Study 존재",
                      actual=study)
        if not study_key:
            return r

        prep = _acquire_pre_registered_steps(ctx, ui, study_key)
        r.add(0, "기본 등록 Step 선행 촬영", PASS,
              expected="3D Step 이 다음 미촬영 Step 이 되도록 기본 템플릿 비움",
              actual=prep,
              note="New Patient 가 자동 등록하는 기본 View 템플릿을 먼저 채운다"
                   "(`_04` 와 같은 전제). 고정 대기 없이 DB 영상 도착을 기다린다.")

        # --- Step 5~6: 모드별 3D 촬영 -------------------------------------
        acquired = {}
        for index, mode in enumerate(XIPL07_MODES, start=5):
            got = _acquire_mode(ctx, ui, study_key, mode)
            acquired[mode["label"]] = got
            group = got["group"] or {}
            types = sorted(int(row["InstanceType"]) for row in got["instances"])
            uids = [str(row.get("ImageInstanceUID") or "")
                    for row in got["instances"]]
            mode_ok = (int(group.get("Type", -1)) == 1
                       and int(group.get("ExposureMode", -1))
                       == mode["exposure_mode"])
            shot = _ev(ctx,
                       f"TC_XIPL_compatibility_07_{mode['label']}_acquired.png")
            vp.capture_viewer_window(ui, shot)
            r.attach(shot)
            title = f"{mode['label']} 영상 촬영"
            if index == 6:
                other = acquired[XIPL07_MODES[0]["label"]]["group"] or {}
                distinct = (int(group.get("ExposureMode", -1))
                            != int(other.get("ExposureMode", -2)))
                title = f"{mode['label']} 영상 촬영 및 3D-N 과 모드 구분"
            else:
                distinct = True
            r.assert_true(
                index, title,
                types == [1, 2, 3] and mode_ok and distinct
                and all(uids) and len(set(uids)) == len(uids),
                expected=(f"동일 Group 에 InstanceType 1(Raw)/2(Recon)/3(Syn) "
                          f"각 1건, Image Instance UID 유일, "
                          f"INSTANCE_GROUP.Type=1 및 "
                          f"ExposureMode={mode['exposure_mode']}"
                          f"({mode['label']})"
                          + (", 3D-N 과 다른 ExposureMode" if index == 6 else "")),
                actual={"acquire": got["acquire"], "wait": got["wait"],
                        "group": group, "instances": got["instances"],
                        "mode_ok": mode_ok, "distinct": distinct},
                note="실제 X-ray 대신 Demo(F8) 가상 촬영(Service Manual 5.2.3). "
                     "영상 내용은 Step 과 무관하므로 DB 구조와 ExposureMode 로만 "
                     f"판정한다. 체크리스트 비고의 회전 범위 {mode['rotation']} 는 "
                     "실물 장비 없이는 확인 대상이 아니다.")

        # --- Step 7: 화면 표시 Recon Parameter ----------------------------
        applied = {}
        for mode in XIPL07_MODES:
            applied[mode["label"]] = _read_applied_recon(
                ctx, ui, mode, study_key, acquired[mode["label"]])
            if applied[mode["label"]]["shot"]:
                r.attach(applied[mode["label"]]["shot"])
        displayed = {label: value["displayed"] for label, value in applied.items()}
        display_ok = all(
            isinstance(value, str) and value.strip().lower().endswith(".xtp")
            for value in displayed.values())
        r.assert_true(
            7, "각 영상에 촬영 모드의 Recon Parameter 표시",
            display_ok,
            expected="두 영상 모두 Post Reconstruction Parameter 콤보에 .xtp 표시",
            actual={"displayed": displayed,
                    "exposure_mode": {label: (value["group"] or {}).get("ExposureMode")
                                      for label, value in acquired.items()}},
            note="사양서1 277쪽 SRS 03-50-230 — \"영상을 획득 시 설정한 xtp 파일을 "
                 "Combo 박스에 자동으로 선택된다\". 화면이 표시하는 촬영 모드"
                 "(narrow/wide) 문구는 컨트롤이 실측되지 않아 읽지 않고, 모드는 "
                 "INSTANCE_GROUP.ExposureMode 로 확정한다(더 강한 근거).")

        # --- Step 8: 파일에 기록된 Recon Parameter -------------------------
        records = {label: value["file"] for label, value in applied.items()}
        errors = {label: value["error"] for label, value in applied.items()
                  if value["error"]}
        xtp = {label: (record or {}).get("XtpName") for label, record in records.items()}
        egp = {label: (record or {}).get("EgpName") for label, record in records.items()}
        allowed = {}
        rule = {}
        for mode in XIPL07_MODES:
            preset_values = {str(row["XIPLParamName"] or "") for row in
                             _preset_recon_rows(ctx, mode["preset_type"])}
            allowed[mode["label"]] = {"preset": sorted(preset_values),
                                      "default": mode["param"]}
            name = xtp.get(mode["label"])
            if name == mode["param"]:
                rule[mode["label"]] = "General Default 적용"
            elif name in preset_values:
                rule[mode["label"]] = "Preset 설정값 적용"
            else:
                rule[mode["label"]] = "사양에 없는 값"
        names_ok = all(rule[mode["label"]] != "사양에 없는 값"
                       for mode in XIPL07_MODES)
        # `EgpName` 은 촬영 모드를 따라간다(3D-N 실측: narrow_standard.egp).
        # Wide 쪽 값은 실측되지 않았으므로 **특정 파일명을 기대하지 않고**
        # "두 모드가 서로 다르다"까지만 판정한다.
        egp_values = [egp[mode["label"]] for mode in XIPL07_MODES]
        egp_ok = all(egp_values) and len(set(egp_values)) == len(egp_values)
        # `_parameter_display_matches("", "")` 는 True 다. 파일과 화면이 **둘 다
        # 비어 있을 때** 교차 확인이 통과한 것처럼 보이면 안 되므로 값이 있는지를
        # 먼저 본다(판정 전체는 `names_ok`/`errors` 로도 막히지만, 리포트의
        # `cross_ok` 가 거짓 안심을 주지 않게 한다).
        cross_ok = all(
            bool((xtp.get(mode["label"]) or "").strip())
            and bool((displayed.get(mode["label"]) or "").strip())
            and _parameter_display_matches(xtp[mode["label"]],
                                           displayed[mode["label"]])
            for mode in XIPL07_MODES)
        r.assert_true(
            8, "각 영상에 촬영 모드별 Recon Parameter 기록",
            not errors and names_ok and egp_ok and cross_ok,
            expected={"XtpName": "모드별 Preset 설정값 또는 그 모드의 General "
                                  "Default 중 하나(사양서1 SRS 03-10-110)",
                      "EgpName": "모드별로 서로 다른 값",
                      "화면-파일 일치": "Post Reconstruction 표시 = img XtpName"},
            actual={"xtp": xtp, "egp": egp, "적용 규칙": rule,
                    "허용값": allowed, "displayed": displayed,
                    "img": {label: value["img_path"]
                            for label, value in applied.items()},
                    "recon_param": records, "errors": errors},
            note="적용된 3D Recon 파라미터 이름은 DB 에 없다(DATA 컬럼 전수 조회, "
                 "2026-08-24). 사양서1 SRS 03-50-230 이 저장 위치로 명시한 "
                 ".img 의 <ReconParam> 을 core/imginfo.py 로 읽어 화면 표시와 "
                 "교차 확인한다. 어느 규칙(Preset/Default)이 적용됐는지도 함께 "
                 "기록한다 — 둘 다 사양이 정한 정상 경로다.")

        # --- Step 9: 설정 원복 -------------------------------------------
        flows.close_examine(ui, option="close", wait=10)
        flows.ensure_patient_screen(ui, wait=3)
        restored = _restore_default_recon(ui, ctx, before_defaults)
        r.assert_true(
            9, "3D-N/3D-W Default Recon Parameter 원복",
            restored["ok"],
            expected={mode["db_column"]: before_defaults.get(mode["db_column"])
                      for mode in XIPL07_MODES},
            actual=restored,
            note="다음 TC 와 다음 실행이 시험 설정을 물려받지 않게 한다. "
                 "실패하면 그 사실을 판정으로 남긴다(조용히 넘기지 않는다).")
        completed = True
    except Exception as exc:                           # noqa: BLE001
        r.abort(0, "TC_XIPL_compatibility_07 실행", exc,
                note=_safe_screen_context(ui))
    finally:
        if restored is None:
            # 본문에서 원복까지 가지 못했다. 남은 설정이 이후 3D TC 를 오염시키므로
            # 여기서 한 번 더 시도하고 결과를 반드시 기록한다.
            try:
                if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
                    flows.close_examine(ui,
                                        option="close" if completed else "suspend",
                                        wait=8)
                flows.ensure_patient_screen(ui, wait=3)
                fallback = _restore_default_recon(ui, ctx, before_defaults)
            except Exception as exc:                   # noqa: BLE001
                fallback = {"ok": False, "error": str(exc)}
            r.cleanup(0, "예외 종료 후 Default Recon Parameter 원복",
                  PASS if fallback.get("ok") else FAIL,
                  expected={mode["db_column"]: before_defaults.get(mode["db_column"])
                            for mode in XIPL07_MODES},
                  actual=fallback,
                  note="원복하지 못하면 다음 3D 촬영이 시험 파라미터를 쓰게 된다. "
                       "회귀는 시작 시 기준 스냅샷을 복원하지만 단독 실행은 "
                       "그렇지 않다.")
    return r


def _restore_default_recon(ui, ctx, before_defaults):
    """3D-N/3D-W Default Recon Parameter 를 시험 전 값으로 UI 로 되돌린다."""
    detail = {}
    for mode in XIPL07_MODES:
        original = before_defaults.get(mode["db_column"])
        if not original:
            detail[mode["label"]] = "원래 값이 비어 있어 복원 대상 아님"
            continue
        try:
            _set_default_recon(ui, mode, original, ctx=ctx)
            detail[mode["label"]] = f"{original} 로 복원 시도"
        except Exception as exc:                       # noqa: BLE001
            detail[mode["label"]] = f"복원 실패: {exc}"
    after = _procedure_defaults(ctx)
    ok = all(after.get(mode["db_column"]) == before_defaults.get(mode["db_column"])
             for mode in XIPL07_MODES)
    return {"ok": ok, "before": before_defaults, "after": after,
            "detail": detail}


def _safe_screen_context(ui):
    """실패 시점 화면 컨텍스트. 수집 자체가 실패해도 판정을 가리지 않는다."""
    try:
        return f"실패 시점 화면: {flows._screen_context(ui)}"
    except Exception as exc:                           # noqa: BLE001
        return f"실패 시점 화면 수집 실패: {exc}"


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
            r.abort(0, "Viewer 시험 데이터 준비(Procedure +, F8)", exc)
            out.append(r)
        r6 = TCResult("TC_XIPL_compatibility_06", "XIPL Parameter 저장 후 Viewer 적용")
        r6.abort(0, "Viewer 시험 데이터 준비(Procedure +, F8)", exc)
        # `_04`/`_05`/`_07` 은 공용 픽스처(`_prepare`)를 쓰지 않고 스스로 검사를
        # 만든다. 그래서 픽스처 준비가 실패해도 그대로 수행한다.
        out.extend([compatibility_04(ctx), compatibility_05(ctx), r6,
                    compatibility_07(ctx)])
        return out
    return [compatibility_01(ctx, session), compatibility_02(ctx, session),
            compatibility_03(ctx, session), compatibility_04(ctx),
            compatibility_05(ctx), compatibility_06(ctx, session),
            compatibility_07(ctx)]
