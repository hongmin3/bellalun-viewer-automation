# -*- coding: utf-8 -*-
"""Windows Update 전후 근거 수집·변화 감지(`core.update_evidence`). 실제 PC 조회·예약 작업 등록을 하지 않는다."""

import base64
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from core import update_evidence as ue


class FakeProbe:
    def __init__(self, build="26200", ubr=7171, kbs=("KB5000001", "KB5000002"), hotfix_error=None,
                 last_success=None, installed_on="2026-10-01"):
        self.build, self.ubr, self.kbs = build, ubr, list(kbs)
        self.hotfix_error, self.last_success, self.installed_on = hotfix_error, last_success, installed_on

    def os_version(self):
        return {"CurrentBuild": self.build, "UBR": self.ubr, "DisplayVersion": "25H2",
                "EditionID": "Professional", "ProductName": "Windows 10 Pro"}

    def hotfixes(self):
        if self.hotfix_error:
            raise self.hotfix_error
        return [{"id": kb, "installed_on": self.installed_on} for kb in self.kbs]

    def last_success_time(self):
        return self.last_success


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.work = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def lines(self):
        with open(ue.history_path(self.work), encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]


class CollectTests(Base, unittest.TestCase):
    def test_record_shape(self):
        rec = ue.collect(FakeProbe(kbs=("kb5000002", "KB5000001")))
        self.assertEqual(rec["schema"], 1)
        self.assertEqual(rec["os"]["build_full"], "26200.7171")
        self.assertEqual(rec["os"]["product_name"], "Windows 11 Pro")
        self.assertEqual(rec["kbs"], ["KB5000001", "KB5000002"])
        self.assertIsNone(rec["kb_error"])
        self.assertEqual(rec["last_update_installed"], "2026-10-01")
        self.assertTrue(rec["last_update_source"].startswith("hotfix:"))

    def test_registry_last_success_preferred(self):
        rec = ue.collect(FakeProbe(last_success="2026-10-15 03:12:44"))
        self.assertEqual(rec["last_update_installed"], "2026-10-15T03:12:44+00:00")
        self.assertTrue(rec["last_update_source"].startswith("registry:"))

    def test_wmi_timeout_recorded_as_kb_error(self):
        runner = mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="powershell", timeout=60))
        probe = ue.WindowsProbe(runner=runner, timeout=60)
        probe.os_version = lambda: {"CurrentBuild": "26200", "UBR": 1}
        probe.last_success_time = lambda: None
        rec = ue.collect(probe)
        self.assertIn("시간 초과", rec["kb_error"])
        self.assertEqual(rec["kbs"], [])
        self.assertEqual(runner.call_args.kwargs["timeout"], 60)

    def test_unexpected_probe_error_recorded(self):
        rec = ue.collect(FakeProbe(hotfix_error=ValueError("bad json")))
        self.assertEqual(rec["kb_error"], "ValueError: bad json")


class CompareTests(Base, unittest.TestCase):
    def test_first_record(self):
        c = ue.compare(None, ue.collect(FakeProbe()))
        self.assertTrue(c["first_record"])
        self.assertFalse(c["changed"])
        self.assertEqual(ue.report_rows(c)[0], list(ue.REPORT_HEADER))
        self.assertTrue(ue.meta_summary(c)["update_evidence_first_record"])

    def test_build_change_detected(self):
        c = ue.compare(ue.collect(FakeProbe(ubr=7171)), ue.collect(FakeProbe(ubr=7200)))
        self.assertTrue(c["changed"])
        self.assertTrue(c["build_changed"])
        meta = ue.meta_summary(c)
        self.assertEqual((meta["os_build_before"], meta["os_build_after"]), ("26200.7171", "26200.7200"))

    def test_kb_add_remove_detected(self):
        c = ue.compare(ue.collect(FakeProbe(kbs=("KB1000001", "KB1000002"))),
                       ue.collect(FakeProbe(kbs=("KB1000002", "KB1000003"))))
        self.assertTrue(c["changed"])
        self.assertFalse(c["build_changed"])
        self.assertEqual(c["kb_added"], ["KB1000003"])
        self.assertEqual(c["kb_removed"], ["KB1000001"])
        self.assertEqual(ue.meta_summary(c)["kb_added"], "KB1000003")

    def test_kb_error_is_not_a_change(self):
        prev = ue.collect(FakeProbe())
        cur = ue.collect(FakeProbe(hotfix_error=RuntimeError("Get-HotFix 시간 초과(60초)")))
        c = ue.compare(prev, cur)
        self.assertFalse(c["changed"])
        self.assertFalse(c["kb_comparable"])

    def test_no_change(self):
        c = ue.compare(ue.collect(FakeProbe()), ue.collect(FakeProbe()))
        self.assertFalse(c["changed"])


class StorageTests(Base, unittest.TestCase):
    def test_save_and_load_last(self):
        ue.save(ue.collect(FakeProbe(ubr=1)), self.work)
        ue.save(ue.collect(FakeProbe(ubr=2)), self.work)
        self.assertEqual(ue.load_last(self.work)["os"]["ubr"], 2)
        self.assertTrue(ue.history_path(self.work).endswith(os.path.join("update-evidence", "history.jsonl")))

    def test_corrupt_line_skipped_with_warning(self):
        ue.save(ue.collect(FakeProbe(ubr=1)), self.work)
        with open(ue.history_path(self.work), "a", encoding="utf-8") as f:
            f.write('{"schema": 1, "os": {"bu')          # 중단으로 잘린 줄(줄바꿈 없음)
        warnings = []
        self.assertEqual(ue.load_last(self.work, log=warnings.append)["os"]["ubr"], 1)
        self.assertEqual(len(warnings), 1)
        ue.save(ue.collect(FakeProbe(ubr=3)), self.work)     # 잘린 줄과 섞이지 않는다
        self.assertEqual(ue.load_last(self.work, log=warnings.append)["os"]["ubr"], 3)

    def test_load_last_ignores_run_result_lines(self):
        ue.save(ue.collect(FakeProbe(ubr=5)), self.work)
        ue._append(self.work, {"schema": 1, "kind": "run_result", "exit_code": 0})
        self.assertEqual(ue.load_last(self.work)["os"]["ubr"], 5)

    def test_missing_history(self):
        self.assertIsNone(ue.load_last(self.work))


class WatchTests(Base, unittest.TestCase):
    def test_first_record_not_run(self):
        run = mock.Mock(return_value=0)
        res = ue.watch(self.work, run, probe=FakeProbe())
        run.assert_not_called()
        self.assertFalse(res["ran"])
        self.assertTrue(res["comparison"]["first_record"])
        self.assertFalse(self.lines()[-1]["triggered"])

    def test_no_change_not_run(self):
        ue.watch(self.work, mock.Mock(), probe=FakeProbe())
        run = mock.Mock(return_value=0)
        res = ue.watch(self.work, run, probe=FakeProbe())
        run.assert_not_called()
        self.assertFalse(res["ran"])
        self.assertEqual(len(self.lines()), 2)

    def test_change_runs_exactly_once(self):
        ue.watch(self.work, mock.Mock(), probe=FakeProbe(ubr=1))
        run = mock.Mock(return_value=0)
        res = ue.watch(self.work, run, probe=FakeProbe(ubr=2, kbs=("KB5000001", "KB5000009")))
        run.assert_called_once_with()
        self.assertTrue(res["ran"])
        self.assertEqual(res["exit_code"], 0)
        lines = self.lines()
        self.assertTrue(lines[-2]["triggered"])
        self.assertEqual(lines[-1]["kind"], "run_result")
        self.assertEqual(lines[-1]["exit_code"], 0)
        # 같은 상태로 다시 감시하면 돌리지 않는다
        again = mock.Mock()
        ue.watch(self.work, again, probe=FakeProbe(ubr=2, kbs=("KB5000001", "KB5000009")))
        again.assert_not_called()

    def test_run_exception_still_records(self):
        ue.watch(self.work, mock.Mock(), probe=FakeProbe(ubr=1))
        run = mock.Mock(side_effect=RuntimeError("체인 중단"))
        res = ue.watch(self.work, run, probe=FakeProbe(ubr=2))
        run.assert_called_once_with()
        self.assertTrue(res["ran"])
        self.assertIn("체인 중단", res["error"])
        self.assertEqual(ue.load_last(self.work)["os"]["ubr"], 2)
        self.assertTrue(ue.load_last(self.work)["triggered"])
        self.assertIn("체인 중단", self.lines()[-1]["error"])

    def test_record_saved_before_run(self):
        ue.watch(self.work, mock.Mock(), probe=FakeProbe(ubr=1))
        seen = {}

        def run():
            seen["last"] = ue.load_last(self.work)["os"]["ubr"]
            return 0
        ue.watch(self.work, run, probe=FakeProbe(ubr=2))
        self.assertEqual(seen["last"], 2)


class TaskTests(unittest.TestCase):
    def test_task_command_built_not_executed(self):
        with mock.patch.object(subprocess, "run") as run, mock.patch.object(subprocess, "call") as call, \
                mock.patch.object(subprocess, "Popen") as popen:
            cmd = ue.install_task_command(r"C:\Py\pythonw.exe", r"C:\repo\run.py")
            script = ue.task_script(r"C:\Py\pythonw.exe", r"C:\repo\run.py")
            logon = ue.task_script(r"C:\Py\pythonw.exe", r"C:\repo\run.py", schedule="logon")
            remove = ue.remove_task_command()
        run.assert_not_called()
        call.assert_not_called()
        popen.assert_not_called()
        self.assertEqual(cmd[0], "powershell")
        self.assertEqual(base64.b64decode(cmd[-1]).decode("utf-16-le"), script)
        self.assertIn("Register-ScheduledTask -TaskName 'Bellalun_WU_UpdateWatch'", script)
        self.assertIn("-Daily -At 09:00", script)
        self.assertIn("update-watch", script)
        self.assertIn("-AtLogOn", logon)
        self.assertEqual(remove, ["schtasks", "/Delete", "/F", "/TN", ue.TASK_NAME])

    def test_bad_schedule_rejected(self):
        with self.assertRaises(ValueError):
            ue.task_script("p", "r", schedule="hourly")
        with self.assertRaises(ValueError):
            ue.task_script("p", "r", at="9시")


class TaskPrivilegeTests(unittest.TestCase):
    def test_task_runs_elevated_in_interactive_session(self):
        script = ue.task_script("pythonw.exe", "run.py")
        self.assertIn("-RunLevel Highest", script)
        self.assertIn("-LogonType Interactive", script)
        self.assertNotIn("-RunLevel Limited", script)


if __name__ == "__main__":
    unittest.main()
