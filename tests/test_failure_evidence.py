# -*- coding: utf-8 -*-
"""실패 증거 수집: 실제 Viewer·Win32 없이 가짜 DLL로 계약을 확인한다."""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from core import failure_evidence as fe


class FakeKernel32:
    def __init__(self, handle=77, image="C:\\App\\VIEWER.exe"):
        self.handle, self.image, self.closed = handle, image, []

    def OpenProcess(self, access, inherit, pid):
        self.opened = (access, inherit, pid)
        return self.handle

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return 1

    def QueryFullProcessImageNameW(self, handle, flags, buf, size_ref):
        buf.value = self.image
        return 1


class FakeUser32:
    def __init__(self, gdi=500, user=800, hwnd=1234, pid=4321, title="Bellalun Viewer"):
        self.values = {fe.GR_GDIOBJECTS: gdi, fe.GR_USEROBJECTS: user}
        self.hwnd, self.pid, self.title = hwnd, pid, title

    def GetGuiResources(self, handle, flag):
        return self.values[flag]

    def GetForegroundWindow(self):
        return self.hwnd

    def GetWindowThreadProcessId(self, hwnd, pid_ref):
        pid_ref._obj.value = self.pid
        return 1

    def GetWindowTextLengthW(self, hwnd):
        return len(self.title)

    def GetWindowTextW(self, hwnd, buf, size):
        buf.value = self.title[:size - 1]
        return len(buf.value)


class GuiHandleTests(unittest.TestCase):
    def test_reads_both_counts_and_closes_handle(self):
        k32 = FakeKernel32()
        out = fe.gui_handles(4321, user32=FakeUser32(gdi=512, user=900), kernel32=k32)
        self.assertEqual(out, {"gdi": 512, "user": 900, "error": None})
        self.assertEqual(k32.opened, (fe.PROCESS_QUERY_LIMITED_INFORMATION, False, 4321))
        self.assertEqual(k32.closed, [77])

    def test_open_failure_is_recorded_not_raised(self):
        out = fe.gui_handles(4321, user32=FakeUser32(), kernel32=FakeKernel32(handle=0))
        self.assertIsNone(out["gdi"])
        self.assertIn("OpenProcess", out["error"])

    def test_missing_pid(self):
        self.assertEqual(fe.gui_handles(None)["error"], "pid 없음")

    def test_exception_inside_api_is_swallowed_and_handle_closed(self):
        k32 = FakeKernel32()
        user = FakeUser32()
        user.GetGuiResources = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
        out = fe.gui_handles(1, user32=user, kernel32=k32)
        self.assertIn("boom", out["error"])
        self.assertEqual(k32.closed, [77])

    def test_does_not_touch_shared_windll_signatures(self):
        if os.name != "nt":
            self.skipTest("Windows 전용")
        import ctypes
        shared = ctypes.windll.user32.GetGuiResources
        before = (shared.restype, shared.argtypes)
        fe.gui_handles(os.getpid())
        fe.foreground_window_info()
        fe.memory_status()
        self.assertEqual((shared.restype, shared.argtypes), before)

    def test_handle_growth_summary(self):
        summary = fe.handle_growth({
            "a.1": {"gdi": 100, "user": 200}, "a.2": {"gdi": None, "user": None,
                                                     "error": "x"},
            "a.3": {"gdi": 200, "user": 364}})
        self.assertEqual(summary["measured"], 2)
        self.assertEqual(summary["gdi_delta"], 100)
        self.assertEqual(summary["user_per_page"], 164.0)
        self.assertIsNone(fe.handle_growth({})["gdi_delta"])


class MemoryTests(unittest.TestCase):
    def test_memory_status_reads_struct(self):
        class K:
            def GlobalMemoryStatusEx(self, ref):
                ref._obj.ullAvailPhys = 2048 * 1024 * 1024
                ref._obj.ullTotalPhys = 8192 * 1024 * 1024
                ref._obj.dwMemoryLoad = 75
                return 1
        out = fe.memory_status(kernel32=K())
        self.assertEqual((out["available_mb"], out["total_mb"], out["load_percent"]),
                         (2048, 8192, 75))
        self.assertIsNone(out["error"])

    def test_memory_failure_recorded(self):
        class K:
            def GlobalMemoryStatusEx(self, ref):
                return 0
        self.assertIn("실패", fe.memory_status(kernel32=K())["error"])


class ForegroundTests(unittest.TestCase):
    def test_foreground_info(self):
        info = fe.foreground_window_info(user32=FakeUser32(), kernel32=FakeKernel32())
        self.assertEqual(info["exe"], "VIEWER.exe")
        self.assertEqual(info["pid"], 4321)
        self.assertEqual(info["title"], "Bellalun Viewer")
        self.assertIsNone(info["error"])

    def test_no_foreground_window(self):
        info = fe.foreground_window_info(user32=FakeUser32(hwnd=0), kernel32=FakeKernel32())
        self.assertIsNone(info["exe"])
        self.assertIn("전경 창 없음", info["error"])

    def test_contamination_tristate(self):
        viewer = {"exe": "VIEWER.exe"}
        console = {"exe": "WindowsTerminal.exe", "title": "pwsh"}
        self.assertFalse(fe.looks_contaminated(viewer, ["viewer"]))
        self.assertFalse(fe.looks_contaminated(viewer, "VIEWER.EXE"))
        self.assertTrue(fe.looks_contaminated(console, ["VIEWER"]))
        self.assertIsNone(fe.looks_contaminated({"error": "x"}, ["VIEWER"]))
        self.assertIsNone(fe.looks_contaminated(viewer, []))
        self.assertIn("콘솔", fe.contamination_reason(console, ["VIEWER"]))
        self.assertIn("판단할 수 없습니다", fe.contamination_reason(None, ["VIEWER"]))

    def test_capture_guard_never_raises(self):
        def broken():
            raise OSError("denied")
        guard = fe.capture_guard(["VIEWER"], info_reader=broken)
        self.assertIsNone(guard["contaminated"])
        self.assertIn("denied", guard["foreground"]["error"])


LOG = (
    "[2026/09/08 17:17:00.000] early line\n"
    "[2026/09/08 17:18:00.100] before event\n"
    "  continuation of before\n"
    "[2026/09/08 17:18:10.000] 설정 페이지 열림\n"
    "Traceback-like line without stamp\n"
    "[2026/09/08 17:18:45.000] too late\n"
)


class LogWindowTests(unittest.TestCase):
    def write(self, folder, data):
        path = os.path.join(folder, "2026_09_08.log")
        with open(path, "wb") as stream:
            stream.write(data)
        return path

    def test_window_keeps_continuation_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, LOG.encode("utf-8"))
            out = fe.extract_log_window(path, datetime(2026, 9, 8, 17, 18, 10), 30, 30)
        self.assertTrue(out["found"])
        self.assertEqual(out["encoding"], "utf-8")
        self.assertEqual(out["lines"], [
            "[2026/09/08 17:18:00.100] before event", "  continuation of before",
            "[2026/09/08 17:18:10.000] 설정 페이지 열림",
            "Traceback-like line without stamp"])

    def test_cp949_and_utf16_fallbacks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, LOG.encode("cp949"))
            out = fe.extract_log_window(path, datetime(2026, 9, 8, 17, 18, 10))
            self.assertEqual(out["encoding"], "cp949")
            self.assertIn("[2026/09/08 17:18:10.000] 설정 페이지 열림", out["lines"])
            path = self.write(folder, b"\xff\xfe" + LOG.encode("utf-16-le"))
            out = fe.extract_log_window(path, datetime(2026, 9, 8, 17, 18, 10))
            self.assertEqual(out["encoding"], "utf-16-le")
            self.assertEqual(len(out["lines"]), 4)

    def test_missing_file_and_epoch_time(self):
        out = fe.extract_log_window(r"Z:\nope\none.log", time.time())
        self.assertFalse(out["found"])
        self.assertEqual(out["error"], "로그 파일 없음")
        self.assertIsNotNone(out["window"])

    def test_custom_parser_and_truncation(self):
        with tempfile.TemporaryDirectory() as folder:
            body = "".join("%d x\n" % i for i in range(100))
            path = self.write(folder, body.encode("utf-8"))
            out = fe.extract_log_window(
                path, datetime(2026, 1, 1, 0, 0, 50), 10, 10,
                parse=lambda line: datetime(2026, 1, 1, 0, 0, int(line.split()[0]) % 60),
                max_lines=6)
        self.assertTrue(out["truncated"])
        self.assertEqual(len(out["lines"]), 7)


class CollectTests(unittest.TestCase):
    def test_writes_json_with_all_sections_and_reuses_health(self):
        with tempfile.TemporaryDirectory() as folder:
            log = os.path.join(folder, "v.log")
            with open(log, "w", encoding="utf-8") as stream:
                stream.write(LOG)
            calls = []

            def exit_message(name, started):
                calls.append((name, started))
                return {"kind": "disappeared", "dumps": [], "message": "m"}

            with patch("core.automation_health.process_exit_message", exit_message):
                path, payload = fe.collect_failure_evidence(
                    os.path.join(folder, "Evidence", "failure"), tc_id="TC_WindowsUpdate_10",
                    reason="Viewer 종료", event_time=datetime(2026, 9, 8, 17, 18, 10),
                    viewer_pid=4321, log_path=log, crash_since=1000.0,
                    readers={"handles": lambda pid: {"gdi": 1, "user": 2, "error": None},
                             "memory": lambda: {"available_mb": 10, "error": None},
                             "foreground": lambda: {"exe": "pwsh.exe", "title": "t"}})
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding="utf-8") as stream:
                saved = json.load(stream)
        self.assertEqual(saved["tc_id"], "TC_WindowsUpdate_10")
        self.assertEqual(saved["handles"]["gdi"], 1)
        self.assertTrue(saved["foreground_contaminated"])
        self.assertEqual(len(saved["log"]["lines"]), 4)
        self.assertEqual(saved["crash"]["kind"], "disappeared")
        self.assertEqual(calls, [("VIEWER", 1000.0)])
        self.assertEqual(payload["memory"]["available_mb"], 10)

    def test_never_raises_even_when_everything_fails(self):
        def boom(*a, **k):
            raise RuntimeError("fail")
        with tempfile.TemporaryDirectory() as folder:
            blocker = os.path.join(folder, "file")
            open(blocker, "w").close()
            path, payload = fe.collect_failure_evidence(
                os.path.join(blocker, "sub"), tc_id="x/y", reason=None,
                event_time="not-a-time",
                readers={"handles": boom, "memory": boom, "foreground": boom,
                         "log": boom, "crash": boom})
        self.assertIsNone(path)
        self.assertIn("write_error", payload)
        self.assertIn("event_time_error", payload)
        self.assertIn("fail", payload["handles"]["error"])
        self.assertIsNone(payload["foreground_contaminated"])

    def test_default_crash_window_is_event_minus_before(self):
        seen = {}
        with tempfile.TemporaryDirectory() as folder:
            event = datetime(2026, 9, 8, 17, 18, 10)
            fe.collect_failure_evidence(
                folder, tc_id="t", reason="r", event_time=event, before=30,
                readers={"handles": lambda p: {}, "memory": lambda: {},
                         "foreground": lambda: {}, "log": lambda *a: {},
                         "crash": lambda name, since: seen.setdefault("since", since)})
        self.assertAlmostEqual(seen["since"], event.timestamp() - 30)


class SettingSweepHandleTests(unittest.TestCase):
    """`read_all` 의 per-page 핸들 기록은 판정·값 계약을 바꾸지 않는다."""

    def sweep(self, **kwargs):
        from contextlib import ExitStack
        from core import setting_values as sv
        from core.ui import Control

        pane = Control(20, 1200, '#32770', '', (400, 100, 1800, 900), True, 1)
        rail = Control(10, 1200, 'AfxWnd140u', 'SettingMenuItem', (150, 100, 350, 140), True, 1)
        with ExitStack() as stack:
            for name, value in (('_viewer_gone', False), ('setting_window', object()),
                                ('_open_page', rail), ('pane_control', pane)):
                stack.enter_context(patch.object(sv, name, return_value=value))
            stack.enter_context(patch.object(sv, 'children', return_value=[]))
            stack.enter_context(patch.object(sv, '_wait_page_settled', return_value=([], True)))
            stack.enter_context(patch.object(sv.screen, 'grab', return_value=object()))
            stack.enter_context(patch.object(sv.flows, 'open_setting'))
            stack.enter_context(patch.object(sv.flows, 'open_setting_group'))
            stack.enter_context(patch.object(sv.flows, 'setting_pages',
                                              return_value={'p1': 100, 'p2': 101}))
            return sv.read_all(SimpleNamespace(pid=10, get_text=lambda c: c.text),
                               groups=['system'], **kwargs)

    def test_records_per_page_handles_via_probe(self):
        counter = iter([(100, 200), (150, 282)])

        def probe(pid):
            self.assertEqual(pid, 10)
            gdi, user = next(counter)
            return {"gdi": gdi, "user": user, "error": None}

        result = self.sweep(handle_probe=probe)
        self.assertEqual(result["page_handles"], {
            "system.p1": {"gdi": 100, "user": 200, "error": None},
            "system.p2": {"gdi": 150, "user": 282, "error": None}})
        self.assertEqual(fe.handle_growth(result["page_handles"])["gdi_delta"], 50)

    def test_probe_failure_is_swallowed_and_sweep_unchanged(self):
        def broken(pid):
            raise OSError("denied")

        with_probe = self.sweep(handle_probe=broken)
        without = self.sweep(record_handles=False)
        self.assertEqual(with_probe["page_handles"]["system.p1"]["gdi"], None)
        self.assertIn("denied", with_probe["page_handles"]["system.p1"]["error"])
        self.assertEqual(without["page_handles"], {})
        for key in ("pages", "missing", "page_render", "viewer_died", "pane"):
            self.assertEqual(with_probe[key], without[key])

    def test_non_dict_probe_result_recorded(self):
        result = self.sweep(handle_probe=lambda pid: 5)
        self.assertIn("형식 오류", result["page_handles"]["system.p1"]["error"])


if __name__ == "__main__":
    unittest.main()
