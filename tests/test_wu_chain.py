# -*- coding: utf-8 -*-
"""실시간 WU 체인의 시간 상한·응답 없음·저장점·재개 (REQ-WU-002, TEST-WU-002).

가짜 단계 함수·가짜 시계·가짜 응답 검사만 쓴다. Viewer·DB를 건드리지 않는다.
"""
import ctypes
import json
import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import run
from core import flows, wu_chain
from core.result import TCResult, PASS, BLOCKED
from tests import winupdate


def _guarded(fn, ctx, tc_id, title):
    out = fn(ctx)
    return list(out) if isinstance(out, (list, tuple)) else [out]


def _passing(tc_id):
    def stage(ctx):
        r = TCResult(tc_id, tc_id)
        r.add(1, "확인", PASS, expected="x", actual="x")
        return [r]
    return stage


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class StageMonitorTests(unittest.TestCase):
    def monitor(self, responding, clock, **kw):
        m = wu_chain.StageMonitor("S", 100, clock=clock, responding=responding,
                                  pid_getter=lambda: 1, hang_seconds=30, **kw)
        m._started = clock()
        return m

    def test_timeout_trips_after_limit(self):
        clock = FakeClock()
        m = self.monitor(lambda pid: True, clock)
        clock.now = 99
        self.assertIsNone(m.check_once())
        clock.now = 100
        kind, reason = m.check_once()
        self.assertEqual(kind, "timeout")
        self.assertIn("시간 상한", reason)

    def test_hang_needs_continuous_no_response(self):
        clock = FakeClock()
        states = iter([False, True, False, False, False])
        m = self.monitor(lambda pid: next(states), clock)
        for t in (0, 10, 20, 40):          # 응답 → 다시 멈춤: 연속 시간이 새로 시작된다
            clock.now = t
            self.assertIsNone(m.check_once())
        clock.now = 50                      # 20초부터 연속 30초
        kind, reason = m.check_once()
        self.assertEqual(kind, "hang")
        self.assertIn("SMTO_ABORTIFHUNG", reason)

    def test_unknown_window_is_not_hang(self):
        clock = FakeClock()
        m = self.monitor(lambda pid: None, clock)
        for t in (0, 50, 99):
            clock.now = t
            self.assertIsNone(m.check_once())


class RunStageTests(unittest.TestCase):
    def test_trip_kills_viewer_and_records_blocked(self):
        kills, evidence = [], []
        released = threading.Event()

        class TripNow:
            def __init__(self, stage_id, timeout, on_trip):
                self.on_trip, self.kind, self.reason = on_trip, None, None

            def start(self):
                self.kind, self.reason = "timeout", "단계 시간 상한 1분을 넘었다."
                threading.Thread(target=self.on_trip, args=(self,), daemon=True).start()
                return self

            def stop(self):
                pass

        def stuck_stage(ctx):
            released.wait(5)                # 감시자가 Viewer를 끝내면 단계가 예외로 빠져나온다
            raise RuntimeError("Viewer 없음")

        def kill():
            kills.append(1)
            released.set()

        produced, trip = wu_chain.run_stage(
            stuck_stage, SimpleNamespace(cfg={}), "TC_Basic_WorkFlow_04", "2D Send",
            guarded=lambda fn, ctx, i, t: run.guarded(fn, ctx, i, t),
            monitor_factory=TripNow, kill=kill, interrupt=lambda: None, grace=5,
            before_kill=lambda m: evidence.append(m.kind))
        self.assertEqual(kills, [1])
        self.assertEqual(evidence, ["timeout"])
        self.assertEqual(trip["kind"], "timeout")
        self.assertEqual([r.tc_id for r in produced], ["TC_Basic_WorkFlow_04"])
        self.assertEqual(produced[0].verdict, BLOCKED)
        self.assertIn("시간 상한", produced[0].checks[0].note)

    def test_subset_stage_blocks_every_output_tc(self):
        produced = wu_chain.blocked_results("TC_XIPL_compatibility_subset", "XIPL",
                                            "hang", "응답 없음")
        self.assertEqual([r.tc_id for r in produced],
                         [tc for tc, _ in wu_chain.STAGE_OUTPUTS["TC_XIPL_compatibility_subset"]])
        self.assertTrue(all(r.verdict == BLOCKED for r in produced))

    def test_normal_stage_returns_results_without_trip(self):
        produced, trip = wu_chain.run_stage(
            _passing("A"), SimpleNamespace(cfg={}), "A", "A", guarded=_guarded, timeout=60,
            monitor_factory=lambda *a, **k: wu_chain.StageMonitor(
                *a, responding=lambda pid: True, pid_getter=lambda: None, poll=0.01, **k),
            kill=lambda: self.fail("kill must not run"))
        self.assertIsNone(trip)
        self.assertEqual(produced[0].verdict, PASS)

    def test_stage_timeout_config_override(self):
        self.assertEqual(wu_chain.stage_timeout("X", {"winupdate": {"stage_timeouts": {"X": 5}}}), 5)
        self.assertEqual(wu_chain.stage_timeout("TC_WindowsUpdate_10"),
                         wu_chain.STAGE_TIMEOUTS["TC_WindowsUpdate_10"])


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "work", wu_chain.CHECKPOINT_NAME)
        self.identity = wu_chain.chain_identity(["A", "B"])

    def tearDown(self):
        self.tmp.cleanup()

    def saved(self):
        cp = wu_chain.Checkpoint(self.path, self.identity)
        cp.complete("A", _passing("A")(None))
        return cp

    def test_resume_uses_source_identity_of_first_run(self):
        # 재개 실행이 다른 커밋이면 리포트가 그 차이를 알 수 있어야 한다(REQ-DIST-005).
        import run
        first = type("Ctx", (), {"source_identity_at_start": {"source_commit": "a" * 40,
                                                              "source_dirty": False}})()
        cp = self.saved()
        run._bind_checkpoint_source(first, cp, resume=False)
        cp.save()
        later = type("Ctx", (), {"source_identity_at_start": {"source_commit": "b" * 40,
                                                              "source_dirty": False}})()
        loaded = wu_chain.Checkpoint.load(self.path, self.identity)
        run._bind_checkpoint_source(later, loaded, resume=True)
        self.assertEqual(later.source_identity_at_start["source_commit"], "a" * 40)

    def test_roundtrip_and_atomic_file(self):
        self.saved()
        loaded = wu_chain.Checkpoint.load(self.path, self.identity)
        self.assertTrue(loaded.done("A"))
        self.assertFalse(loaded.done("B"))
        self.assertEqual(loaded.results("A")[0]["verdict"], "PASS")
        leftovers = [n for n in os.listdir(os.path.dirname(self.path)) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_corrupted_or_edited_checkpoint_is_rejected(self):
        self.saved()
        with open(self.path, encoding="utf-8") as f:
            envelope = json.load(f)
        envelope["payload"]["stages"]["A"]["results"][0]["verdict"] = "FAIL"
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(envelope, f)
        with self.assertRaisesRegex(wu_chain.CheckpointError, "해시"):
            wu_chain.Checkpoint.load(self.path, self.identity)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ 잘린 파일")
        with self.assertRaises(wu_chain.CheckpointError):
            wu_chain.Checkpoint.load(self.path, self.identity)

    def test_other_chain_missing_or_finished_checkpoint_is_rejected(self):
        with self.assertRaisesRegex(wu_chain.CheckpointError, "없습니다"):
            wu_chain.Checkpoint.load(self.path, self.identity)
        cp = self.saved()
        with self.assertRaisesRegex(wu_chain.CheckpointError, "체인 구성"):
            wu_chain.Checkpoint.load(self.path, wu_chain.chain_identity(["A"]))
        cp.finish()
        with self.assertRaisesRegex(wu_chain.CheckpointError, "끝난"):
            wu_chain.Checkpoint.load(self.path, self.identity)

    def test_result_from_dict_restores_verdict_and_skip_policy(self):
        r = TCResult("TC_WindowsUpdate_10", "Setting")
        r.add(1, "a", PASS)
        r.skip(2, "b", "사유", blocks_verdict=True)
        back = wu_chain.result_from_dict(r.as_dict())
        self.assertEqual(back.verdict, r.verdict)
        self.assertTrue(back.checks[1].blocks_verdict)


class KeepAwakeTests(unittest.TestCase):
    def test_nested_sets_once_and_restores(self):
        calls = []
        with wu_chain.keep_awake(calls.append):
            with wu_chain.keep_awake(calls.append):
                pass
        self.assertEqual(calls, [wu_chain._KEEP, wu_chain.ES_CONTINUOUS])

    def test_restores_on_exception(self):
        calls = []
        with self.assertRaises(ValueError):
            with wu_chain.keep_awake(calls.append):
                raise ValueError
        self.assertEqual(calls[-1], wu_chain.ES_CONTINUOUS)

    @unittest.skipUnless(os.name == "nt", "Windows 전용")
    def test_shared_windll_prototypes_untouched(self):
        shared = ctypes.windll.user32.SendMessageTimeoutW
        before = (shared.argtypes, shared.restype)
        wu_chain.viewer_responding(0)
        wu_chain._user32()
        wu_chain._set_execution_state(wu_chain.ES_CONTINUOUS)
        self.assertEqual((shared.argtypes, shared.restype), before)


class ChainResumeTests(unittest.TestCase):
    """체인 전체를 가짜 단계로 돌려 중단 → 재개 시 완료 단계를 다시 실행하지 않는지 본다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = SimpleNamespace(cfg={}, db=object(), root=self.tmp.name,
                                   evidence_root=os.path.join(self.tmp.name, "Evidence"))
        self.calls = []
        self.crash_at = None
        self.finished = []
        self.observe_tail = lambda stage_id: None

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self, tc_id):
        def fn(ctx):
            self.calls.append(tc_id)
            if tc_id == self.crash_at:
                raise KeyboardInterrupt  # 체인 중간 강제 종료 흉내
            return _passing(tc_id)(ctx)
        return fn

    def run_chain(self, resume):
        stages = [(self.stage(t), t, t) for t in
                  ("AUTOMATION_ENVIRONMENT_RESET", "DICOM_Server_Setup", "TC_A", "TC_B")]

        def wu10(ctx, ui):
            self.calls.append("TC_WindowsUpdate_10")
            self.observe_tail("TC_WindowsUpdate_10")
            return _passing("TC_WindowsUpdate_10")(ctx)[0]

        def usb(ctx, ui):
            self.calls.append("WU09_USB")
            self.observe_tail("WU09_USB")
            return {"drive": None}

        def finish(ctx, wu_results, elapsed=0, **kw):
            self.finished.append(kw)
            return 0

        preflight = {"items": [], "blocked": False, "environment": {}, "fingerprint": {}}
        with patch.object(run, "_wu_chain_stages", return_value=stages), \
                patch.object(run, "_wu_preflight", return_value=preflight), \
                patch.object(run, "shutdown_viewer", return_value={}), \
                patch.object(run, "recover_viewer_after_termination"), \
                patch.object(run, "_finish_winupdate", side_effect=finish), \
                patch.object(flows, "cold_start", return_value=(object(), {})), \
                patch.object(winupdate, "run_usb_export_import", side_effect=usb), \
                patch.object(winupdate, "run_setting_display", side_effect=wu10), \
                patch.object(wu_chain, "keep_awake", side_effect=lambda: _null()),                 patch.object(wu_chain, "StageMonitor", _QuietMonitor),                 patch("core.env_preflight.summary_for_report", return_value={}):
            return run._run_winupdate_chain(self.ctx, resume=resume)

    def test_tail_progress_identifies_stage_before_product_action(self):
        # Validates: REQ-QA-002. 실제 체인의 USB/설정 검사 진입 때 저장된 진행을 읽는다.
        from bellalunauto.runs import RunRecord
        record = RunRecord.create(self.tmp.name, "run-winupdate", {}, consent=True)
        observed = []
        self.observe_tail = lambda stage_id: observed.append(
            (stage_id, record.refresh_progress().copy()))
        with patch.dict(os.environ, {"BELLALUN_QA_RUN": record.data["run_id"]}):
            self.assertEqual(self.run_chain(resume=False), 0)
        self.assertEqual([stage for stage, _ in observed], list(run.WU_TAIL_STAGES))
        self.assertEqual([(stage, progress["current_tc"], progress["completed"], progress["total"])
                          for stage, progress in observed],
                         [("WU09_USB", "WU09_USB", 4, 6),
                          ("TC_WindowsUpdate_10", "TC_WindowsUpdate_10", 5, 6)])

    def test_interrupted_chain_resumes_only_remaining_stages(self):
        self.crash_at = "TC_B"
        with self.assertRaises(KeyboardInterrupt):
            self.run_chain(resume=False)
        self.assertEqual(self.calls, ["AUTOMATION_ENVIRONMENT_RESET", "DICOM_Server_Setup",
                                      "TC_A", "TC_B"])
        self.calls.clear()
        self.crash_at = None
        self.assertEqual(self.run_chain(resume=True), 0)
        self.assertEqual(self.calls, ["TC_B", "WU09_USB", "TC_WindowsUpdate_10"])
        meta = self.finished[-1]["extra_meta"]
        self.assertTrue(meta["resumed"])
        self.assertEqual(meta["reused_stages"],
                         ["AUTOMATION_ENVIRONMENT_RESET", "DICOM_Server_Setup", "TC_A"])
        self.assertTrue(self.finished[-1]["chain_completed"])
        # 끝난 저장점으로는 다시 재개하지 않는다.
        self.assertEqual(self.run_chain(resume=True), 2)

    def test_resume_without_or_with_corrupt_checkpoint_is_refused(self):
        self.assertEqual(self.run_chain(resume=True), 2)
        path = wu_chain.checkpoint_path(self.tmp.name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"payload": {}, "sha256": "0"}')
        self.assertEqual(self.run_chain(resume=True), 2)
        self.assertEqual(self.calls, [])

    def test_blocked_precondition_stops_chain(self):
        def blocked(ctx):
            r = TCResult("DICOM_Server_Setup", "x")
            r.blocked(0, "단계 시간 상한 초과", "사유")
            return [r]
        stages = [(_passing("AUTOMATION_ENVIRONMENT_RESET"), "AUTOMATION_ENVIRONMENT_RESET", "r"),
                  (blocked, "DICOM_Server_Setup", "d"), (self.stage("TC_A"), "TC_A", "a")]
        with patch.object(run, "_wu_chain_stages", return_value=stages), \
                patch.object(run, "_wu_preflight", return_value={"items": [], "blocked": False,
                                                                  "environment": {}, "fingerprint": {}}), \
                patch.object(run, "shutdown_viewer", return_value={}), \
                patch.object(run, "recover_viewer_after_termination"), \
                patch.object(run, "_finish_winupdate",
                             side_effect=lambda *a, **k: self.finished.append(k) or 0),                 patch.object(wu_chain, "StageMonitor", _QuietMonitor),                 patch("core.env_preflight.summary_for_report", return_value={}):
            run._run_winupdate_chain(self.ctx)
        self.assertNotIn("TC_A", self.calls)
        self.assertFalse(self.finished[-1]["chain_completed"])

    def test_preflight_block_starts_nothing(self):
        blocked = {"items": [], "blocked": True, "environment": {}, "fingerprint": {}}
        with patch.object(run, "_wu_preflight", return_value=blocked), \
                patch.object(run, "_wu_chain_stages", side_effect=AssertionError):
            self.assertEqual(run._run_winupdate_chain(self.ctx), 2)
        self.assertFalse(os.path.exists(wu_chain.checkpoint_path(self.tmp.name)))


class _QuietMonitor:
    def __init__(self, *a, **k):
        self.kind = self.reason = None

    def start(self):
        return self

    def stop(self):
        pass


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


if __name__ == "__main__":
    unittest.main()
