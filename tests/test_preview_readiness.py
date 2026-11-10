"""Preview 준비와 렌더 지연을 실제 TC 경로에서 재현한다(UI/DB 입력 없음)."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from core import ui as ui_module
from core import viewer_processing as vp
from core.result import FAIL, PASS
from tests import xipl_flows as flow


class Clock:
    def __init__(self):
        self.now = 0.0

    def sleep(self, seconds):
        self.now += seconds


class PreviewControl:
    def __init__(self, identifier, clock, ready_at):
        self.ctrl_id = identifier
        self.hwnd = identifier
        self.visible = True
        self.text = "TEST_2D_FLOW_M.pim"
        self.rect = (0, 0, 200, 200)
        self.clock, self.ready_at = clock, ready_at

    @property
    def enabled(self):
        return self.clock.now >= self.ready_at


class PreviewReadinessTests(unittest.TestCase):
    def run_flow(self, *, ready_at=2, cancel_ready_at=None, render=None,
                 log_at=0, timeout=8):
        clock = Clock()
        changed = {name: 2 for name in vp.SLIDER_NAMES_2D.values()}
        baseline = {name: 1 for name in changed}
        controls = {identifier: PreviewControl(identifier, clock, ready_at)
                    for identifier in (vp.PREVIEW, vp.APPLY, vp.CANCEL, vp.PARAM_COMBO)}
        if cancel_ready_at is not None:
            controls[vp.CANCEL].ready_at = cancel_ready_at
        events = {"applied": False, "preview_started": False,
                  "preview_captures": [], "apply_times": []}
        render = render or (lambda seconds: 70 if seconds >= 4 else 0)

        def by_id(identifier):
            if events["applied"] and identifier == vp.APPLY:
                return []
            return [controls[identifier]] if identifier in controls else []

        def click(control, **kwargs):
            if control.ctrl_id == vp.PREVIEW:
                events["preview_started"] = True
            elif control.ctrl_id == vp.APPLY:
                events["apply_times"].append(clock.now)
                events["applied"] = True

        ui = SimpleNamespace(by_id=by_id, click=click)
        log = ("Image Process Param Name : TEST_2D_FLOW_M.pim, Contrast : 2, "
               "Sharpness : 2, Brightness : 2, Tone Type : 2, Noise Reduction : 2")

        def capture(path):
            value = render(clock.now) if events["preview_started"] else 0
            image = (value if isinstance(value, Image.Image)
                     else Image.new("RGB", (200, 200), (value, value, value)))
            image.save(path)
            if Path(path).name.endswith("_preview.png"):
                events["preview_captures"].append(clock.now)
            return path

        with TemporaryDirectory() as root, ExitStack() as stack:
            ctx = SimpleNamespace(evidence_root=root,
                                  cfg={"data_dir": root,
                                       "xipl": {"preview_2d_wait": timeout}})
            for name in ("select_2d", "open_process", "change_all_2d_parameters",
                         "cancel_window"):
                stack.enter_context(patch.object(vp, name))
            stack.enter_context(patch.object(vp, "select_test_parameter",
                                             return_value="TEST_2D_FLOW_M.pim"))
            stack.enter_context(patch.object(vp, "read_2d_parameter_state",
                                             return_value=changed))
            stack.enter_context(patch.object(vp, "capture", side_effect=capture))
            stack.enter_context(patch.object(flow, "_read_2d_parameter_file",
                                             return_value=baseline))
            stack.enter_context(patch.object(flow, "_viewer_log_mark",
                                             return_value=(Path(root) / "log", 0)))
            stack.enter_context(patch.object(flow, "_viewer_log_since",
                                             side_effect=lambda _: log if clock.now >= log_at else ""))
            stack.enter_context(patch.object(flow, "_directory_state",
                                             side_effect=lambda _: {"image": {"size": 1}}
                                             if events["applied"] else {}))
            stack.enter_context(patch.object(flow, "_apply_2d_complete",
                                             return_value=(True, "applied", {})))
            stack.enter_context(patch.object(flow.time, "sleep", side_effect=clock.sleep))
            stack.enter_context(patch.object(flow.time, "monotonic", side_effect=lambda: clock.now))
            stack.enter_context(patch.object(flow.time, "perf_counter", side_effect=lambda: clock.now))
            result = flow.compatibility_02(ctx, {"ui": ui, "step_2d": 1})
            events["finished"] = clock.now
            preview_path = Path(root) / "Viewer_XIPL" / "TC_XIPL_compatibility_02_preview.png"
            if preview_path.exists():
                with Image.open(preview_path) as image:
                    events["saved_pixel"] = image.getpixel((100, 100))
        return result, events

    def test_parameter_log_before_enabled_and_render_does_not_capture_early(self):
        result, events = self.run_flow()
        step = next(check for check in result.checks if check.step == 7)
        self.assertEqual(PASS, step.status)
        self.assertGreaterEqual(events["apply_times"][0], 4.5)
        self.assertEqual((70, 70, 70), events["saved_pixel"])

    def test_render_must_stop_changing_before_apply(self):
        def render(seconds):
            return 0 if seconds < 3 else 40 if seconds < 4 else 90
        result, events = self.run_flow(ready_at=0, render=render)
        self.assertEqual(PASS, next(check for check in result.checks if check.step == 7).status)
        self.assertGreaterEqual(events["apply_times"][0], 4.5)
        self.assertEqual((90, 90, 90), events["saved_pixel"])

    def test_visible_but_permanently_disabled_apply_is_readiness_timeout(self):
        result, events = self.run_flow(ready_at=999, render=lambda _: 70)
        self.assertFalse(events["applied"])
        self.assertTrue(result.aborted)
        self.assertEqual("timeout", result.timings[-1]["outcome"])
        self.assertIn("apply_enabled", result.timings[-1]["detail"])

    def test_cancel_must_be_enabled_as_well_as_apply(self):
        result, events = self.run_flow(ready_at=0, cancel_ready_at=999, render=lambda _: 70)
        self.assertFalse(events["applied"])
        self.assertTrue(result.aborted)
        self.assertEqual("timeout", result.timings[-1]["outcome"])

    def test_complete_unchanged_image_is_visual_failure_not_readiness_timeout(self):
        result, events = self.run_flow(ready_at=1, render=lambda _: 0)
        step = next(check for check in result.checks if check.step == 7)
        self.assertEqual(FAIL, step.status)
        self.assertFalse(events["applied"])
        self.assertGreaterEqual(events["finished"], 8)
        self.assertEqual("completed without visible image change", result.timings[-1]["outcome"])
        self.assertIn("changed_ratio", str(step.actual))

    def test_missing_parameter_log_is_timeout_even_if_frame_ready(self):
        result, events = self.run_flow(ready_at=0, log_at=999, render=lambda _: 70)
        self.assertFalse(events["applied"])
        self.assertEqual("timeout", result.timings[-1]["outcome"])

    def test_never_stable_frame_is_readiness_timeout(self):
        result, events = self.run_flow(ready_at=0,
                                      render=lambda seconds: 40 if int(seconds * 2) % 2 else 90)
        self.assertFalse(events["applied"])
        self.assertEqual("timeout", result.timings[-1]["outcome"])

    def test_original_visual_change_threshold_still_separates_58_and_59_pixels(self):
        # Pane = 69 * 169 = 11661 pixels. 58/11661 < .005 < 59/11661.
        for pixels, expected in ((58, FAIL), (59, PASS)):
            image = Image.new("RGB", (200, 200))
            for x in range(73, 73 + pixels):
                image.putpixel((x, 11), (70, 70, 70))
            with self.subTest(pixels=pixels):
                result, events = self.run_flow(ready_at=0, render=lambda _: image)
                step = next(check for check in result.checks if check.step == 7)
                self.assertEqual(expected, step.status)
                self.assertEqual(expected == PASS, events["applied"])

    def test_3d_log_completion_does_not_require_the_new_2d_controls(self):
        for require_closed in (False, True):
            ui = SimpleNamespace(by_id=lambda _: [] if require_closed
                                 else [SimpleNamespace(visible=True)])
            with self.subTest(require_closed=require_closed), patch.object(
                    flow, "_viewer_log_since",
                    return_value="Terminate PostReconThread normally closed"):
                done, _, detail = flow._post_recon_complete(None, ui, require_closed)
            self.assertTrue(done)
            self.assertTrue(detail["thread_done"])

    def test_3d_preview_waits_for_enabled_apply_and_cancel_after_completion_log(self):
        # 1.0.8 run110 XIPL03: eNoti:5 직후 Apply가 아직 비활성(Receive Synthetic
        # image)인데 눌러 클릭이 무시됐고, Apply 대기가 120초 뒤 timeout 됐다.
        log = ("[Initialize Reconstruction. (narrow_standard.egp, TEST_3D_FLOW.xtp, x)]\n"
               "[Failed to initialize Recon. Error: No GPUS]\n"
               "[ProgressBar Show (CDlgPostReconstruction::OnProgressImageProcess, eNoti:5)]\n"
               "[Terminate PostReconThread normally closed]")
        for enabled, expected in ((False, False), (True, True)):
            control = SimpleNamespace(visible=True, enabled=enabled)
            ui = SimpleNamespace(by_id=lambda _: [control])
            with self.subTest(enabled=enabled), patch.object(
                    flow, "_viewer_log_since", return_value=log):
                done, _, detail = flow._post_recon_preview_ready(None, ui)
            self.assertEqual(expected, done)
            self.assertTrue(detail["progress_done"])
            self.assertEqual(enabled, detail["apply_enabled"])
            self.assertEqual(enabled, detail["cancel_enabled"])

    def test_3d_preview_waits_for_preview_thread_exit_even_without_gpu(self):
        # 1.0.9 run111 회귀 XIPL03: eNoti:5 뒤 Apply·Cancel이 활성이었지만 Preview
        # PostReconThread 종료 로그 전에 Apply를 눌렀다. Viewer는 Apply를 처리하지
        # 않았고 스레드는 120초 뒤 창을 닫을 때에야 끝났다. 성공한 실행은 모두
        # eNoti:5 1~3초 뒤 종료 로그가 남은 다음 Apply를 눌렀다.
        log = ("[Initialize Reconstruction. (narrow_standard.egp, TEST_3D_FLOW.xtp, x)]\n"
               "[Failed to initialize Recon. Error: No GPUS]\n"
               "[ProgressBar Show (CDlgPostReconstruction::OnProgressImageProcess, eNoti:5)]")
        control = SimpleNamespace(visible=True, enabled=True)
        ui = SimpleNamespace(by_id=lambda _: [control])
        for tail, expected in (("", False), ("\n[Terminate PostReconThread normally closed]", True)):
            with self.subTest(thread_exit=bool(tail)), patch.object(
                    flow, "_viewer_log_since", return_value=log + tail):
                done, _, detail = flow._post_recon_preview_ready(None, ui)
            self.assertEqual(expected, done)
            self.assertEqual(expected, detail["thread_done"])

    def test_3d_preview_ready_still_requires_completion_log(self):
        control = SimpleNamespace(visible=True, enabled=True)
        ui = SimpleNamespace(by_id=lambda _: [control])
        with patch.object(flow, "_viewer_log_since", return_value=""):
            done, _, detail = flow._post_recon_preview_ready(None, ui)
        self.assertFalse(done)
        self.assertTrue(detail["apply_enabled"])

    def test_control_enabled_reads_live_handle_without_constructor_change(self):
        control = ui_module.Control(0x123456789, 1, "Button", "Apply",
                                    (0, 0, 100, 30), True, 0)
        with patch.object(ui_module._u32p, "IsWindowEnabled", side_effect=(False, True)):
            self.assertEqual(False, getattr(control, "enabled", None))
            self.assertEqual(True, getattr(control, "enabled", None))


if __name__ == "__main__":
    unittest.main()
