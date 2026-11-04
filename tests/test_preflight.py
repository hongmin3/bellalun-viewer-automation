# -*- coding: utf-8 -*-
"""실행 전 PC 점검(core.env_preflight) — 가짜 sysinfo probe로 항목별 OK/WARN/BLOCK."""
import ctypes
import datetime
import os
import unittest

from core import env_preflight as pf

GIB = 1024 ** 3
WORK = r"C:\BellalunAuto 작업"
ENTRIES = [{"id": "pro", "os_edition": "Windows 11 Pro", "build_ubr": "26200",
            "resolution": "1920x1080", "dpi": 96, "viewer_version": None}]


def _probe(**over):
    probe = {
        "display": {"actual": (1920, 1080), "dpi": 96},
        "taskbar_autohide": False,
        "usb_drive": "E:\\",
        "reboot_pending": [],
        "now": datetime.datetime(2026, 11, 4, 9, 0, 0),
        "clock_skew_seconds": 0.0,
        "memory": {"avail": 6 * GIB, "total": 16 * GIB},
        "os_edition": "Windows 11 Pro",
        "build_ubr": "26200.7171",
        "viewer_version": "1.0.0.1",
    }
    probe.update(over)
    return probe


def _run(work_dir=WORK, entries=ENTRIES, **over):
    return pf.run_preflight({}, work_dir, probe=_probe(**over), entries=entries)


def _item(result, key):
    return next(i for i in result["items"] if i["key"] == key)


class ItemShapeTests(unittest.TestCase):
    def test_all_ok(self):
        result = _run()
        self.assertFalse(result["blocked"])
        self.assertEqual({"OK"}, {i["level"] for i in result["items"]})
        for item in result["items"]:
            self.assertEqual({"key", "label", "level", "actual", "expected",
                              "blocks_run", "hint"}, set(item))
        self.assertEqual("verified", result["environment"]["status"])
        self.assertEqual("26200.7171", result["fingerprint"]["build_ubr"])


class DisplayTests(unittest.TestCase):
    def test_resolution_mismatch_blocks(self):
        result = _run(display={"actual": (1600, 900), "dpi": 96})
        self.assertEqual("BLOCK", _item(result, "resolution")["level"])
        self.assertTrue(_item(result, "resolution")["blocks_run"])
        self.assertTrue(result["blocked"])

    def test_dpi_mismatch_blocks(self):
        result = _run(display={"actual": (1920, 1080), "dpi": 120})
        self.assertEqual("BLOCK", _item(result, "dpi")["level"])
        self.assertTrue(result["blocked"])

    def test_cfg_expected_values_are_used(self):
        cfg = {"display": {"width": 1600, "height": 900, "expected_dpi": 120}}
        result = pf.run_preflight(cfg, WORK, entries=ENTRIES,
                                  probe=_probe(display={"actual": (1600, 900), "dpi": 120}))
        self.assertEqual("OK", _item(result, "resolution")["level"])
        self.assertEqual("OK", _item(result, "dpi")["level"])


class WarnItemTests(unittest.TestCase):
    def test_taskbar_autohide_warns_only(self):
        result = _run(taskbar_autohide=True)
        self.assertEqual("WARN", _item(result, "taskbar_autohide")["level"])
        self.assertFalse(result["blocked"])

    def test_no_usb_warns_wu09_skip(self):
        item = _item(_run(usb_drive=None), "usb_drive")
        self.assertEqual("WARN", item["level"])
        self.assertIn("WU_09 USB 단계 SKIP 예정", item["hint"])

    def test_reboot_pending_warns(self):
        item = _item(_run(reboot_pending=["Windows Update"]), "reboot_pending")
        self.assertEqual("WARN", item["level"])
        self.assertIn("Windows Update", item["actual"])

    def test_clock_year_and_skew_warn(self):
        self.assertEqual("WARN", _item(_run(now=datetime.datetime(2009, 1, 1)), "clock")["level"])
        self.assertEqual("WARN", _item(_run(clock_skew_seconds=-400), "clock")["level"])
        self.assertEqual("OK", _item(_run(clock_skew_seconds=200), "clock")["level"])

    def test_probe_error_is_warn_not_crash(self):
        def boom():
            raise OSError("조회 실패")
        result = _run(taskbar_autohide=boom, reboot_pending=boom, memory=boom)
        for key in ("taskbar_autohide", "reboot_pending", "memory"):
            self.assertEqual("WARN", _item(result, key)["level"])
        self.assertFalse(result["blocked"])


class MemoryTests(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual("OK", _item(_run(memory={"avail": 2 * GIB}), "memory")["level"])
        self.assertEqual("WARN", _item(_run(memory={"avail": int(1.5 * GIB)}), "memory")["level"])
        result = _run(memory={"avail": GIB // 2})
        self.assertEqual("BLOCK", _item(result, "memory")["level"])
        self.assertTrue(result["blocked"])


class WorkDirTests(unittest.TestCase):
    def test_percent_blocks(self):
        result = _run(work_dir=r"C:\작업 %TEMP%")
        self.assertEqual("BLOCK", _item(result, "work_dir_chars")["level"])
        self.assertTrue(result["blocked"])

    def test_long_path_warns_like_selfcheck(self):
        from bellalunauto.app import WORKSPACE_PATH_LIMIT
        result = _run(work_dir="C:\\" + "a" * WORKSPACE_PATH_LIMIT)
        item = _item(result, "work_dir_length")
        self.assertEqual("WARN", item["level"])
        self.assertFalse(item["blocks_run"])
        self.assertFalse(result["blocked"])
        ok = _item(_run(work_dir="C:\\" + "a" * (WORKSPACE_PATH_LIMIT - 3)), "work_dir_length")
        self.assertEqual("OK", ok["level"])


class EnvironmentItemTests(unittest.TestCase):
    def test_unregistered_environment_is_warn_not_block(self):
        result = _run(os_edition="Windows 10 Pro", build_ubr="19045.1")
        item = _item(result, "environment")
        self.assertEqual("unregistered", result["environment"]["status"])
        self.assertEqual("WARN", item["level"])
        self.assertFalse(item["blocks_run"])
        self.assertFalse(result["blocked"])

    def test_empty_registry_list_is_warn(self):
        result = _run(entries=[])
        self.assertEqual("WARN", _item(result, "environment")["level"])
        self.assertFalse(result["blocked"])


class OutputTests(unittest.TestCase):
    def test_format_lines_and_summary(self):
        result = _run(usb_drive=None, os_edition="Windows 10 Pro")
        text = "\n".join(pf.format_lines(result))
        self.assertIn("[WARN ] 이동식 드라이브", text)
        self.assertIn("요약: OK", text)
        summary = pf.summary_for_report(result)
        self.assertTrue(summary["환경 대조"].startswith("미등록 환경(WARN): 차이 "))
        self.assertEqual("OK 8 / WARN 2 / BLOCK 0", summary["사전 점검"])
        self.assertIn("사전 점검 상세", summary)

    def test_summary_verified(self):
        summary = pf.summary_for_report(_run())
        self.assertEqual("검증됨 (pro)", summary["환경 대조"])
        self.assertNotIn("사전 점검 상세", summary)


@unittest.skipUnless(os.name == "nt", "Windows 전용 ctypes 규칙")
class PrivateCtypesTests(unittest.TestCase):
    def test_shared_windll_prototypes_unchanged(self):
        import importlib
        k32 = ctypes.windll.kernel32.GlobalMemoryStatusEx
        sh = ctypes.windll.shell32.SHAppBarMessage
        before = (k32.argtypes, k32.restype, sh.argtypes, sh.restype)
        importlib.reload(pf)
        self.assertEqual(before, (k32.argtypes, k32.restype, sh.argtypes, sh.restype))

    def test_real_memory_and_taskbar_readable(self):
        mem = pf.real_memory()
        self.assertGreater(mem["total"], 0)
        self.assertIsInstance(pf.real_taskbar_autohide(), bool)


if __name__ == "__main__":
    unittest.main()
