# -*- coding: utf-8 -*-
"""Viewer·XIPL Studio 실행 환경 변수 보충과 XIPL_PATH 사전 확인.

2026-10-18 실측: 개발 도구를 뺀 최소 환경에서 BellalunAuto가 Viewer를 띄우자
`XIPL_PATH`가 없어 Viewer가 `Failed to initialize XIPL. XIPL is not installed. [E2100]`을
기록한 뒤 PC 전원을 껐다(System 이벤트 1074, VIEWER.exe). Viewer는 `XIPL_PATH`로
`SERVER_X64\\XIPL.KEEPALIVE.exe`를 찾는다.
"""
import os
import tempfile
import unittest
from pathlib import Path

from core import product_env


def _xipl_dir(root):
    server = Path(root) / "SERVER_X64"
    server.mkdir(parents=True)
    (server / "XIPL.KEEPALIVE.exe").write_bytes(b"")
    return str(root) + "\\"


class ProductEnvironmentTests(unittest.TestCase):
    def test_missing_registered_variable_is_added(self):
        env = product_env.product_environment(
            {"SystemRoot": r"C:\WINDOWS"}, {"XIPL_PATH": "C:\\XIPL\\"})
        self.assertEqual("C:\\XIPL\\", env["XIPL_PATH"])
        self.assertEqual(r"C:\WINDOWS", env["SystemRoot"])

    def test_existing_value_wins_case_insensitively(self):
        env = product_env.product_environment({"xipl_path": r"D:\X"}, {"XIPL_PATH": r"C:\XIPL"})
        self.assertEqual(r"D:\X", env["xipl_path"])
        self.assertNotIn("XIPL_PATH", env)

    def test_path_is_not_replaced(self):
        env = product_env.product_environment({"PATH": r"C:\WINDOWS"},
                                              {"Path": r"C:\Python;C:\WINDOWS"})
        self.assertEqual(r"C:\WINDOWS", env["PATH"])
        self.assertNotIn("Path", env)

    def test_base_is_not_modified(self):
        base = {"A": "1"}
        product_env.product_environment(base, {"B": "2"})
        self.assertEqual({"A": "1"}, base)

    def test_registered_environment_reads_windows_registry(self):
        if os.name != "nt":
            self.skipTest("Windows 전용")
        registered = product_env.registered_environment()
        self.assertTrue(any(key.upper() == "WINDIR" or key.upper() == "OS" for key in registered))


class XiplPathTests(unittest.TestCase):
    def test_valid_install_has_no_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(product_env.xipl_problem({"XIPL_PATH": _xipl_dir(tmp)}))

    def test_missing_variable_is_reported(self):
        problem = product_env.xipl_problem({"PATH": r"C:\WINDOWS"})
        self.assertIn("XIPL_PATH", problem)

    def test_variable_name_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(product_env.xipl_problem({"Xipl_Path": _xipl_dir(tmp)}))

    def test_folder_without_keepalive_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            problem = product_env.xipl_problem({"XIPL_PATH": tmp})
            self.assertIn("XIPL.KEEPALIVE.exe", problem)


class LaunchGuardTests(unittest.TestCase):
    def test_launch_refuses_viewer_without_xipl_and_does_not_start_it(self):
        from unittest import mock
        from core import ui as ui_module
        with mock.patch.object(product_env, "registered_environment", return_value={}), \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch("subprocess.Popen") as popen:
            with self.assertRaises(RuntimeError) as caught:
                ui_module.ViewerUi.launch(object.__new__(ui_module.ViewerUi), r"C:\B\VIEWER.exe", wait=0)
        popen.assert_not_called()
        self.assertIn("XIPL_PATH", str(caught.exception))
        self.assertIn("전원", str(caught.exception))

    def test_launch_passes_restored_environment(self):
        from unittest import mock
        from core import ui as ui_module
        with tempfile.TemporaryDirectory() as tmp:
            xipl = _xipl_dir(tmp)
            viewer = object.__new__(ui_module.ViewerUi)
            with mock.patch.object(product_env, "registered_environment",
                                   return_value={"XIPL_PATH": xipl}), \
                    mock.patch.dict(os.environ, {"SystemRoot": r"C:\WINDOWS"}, clear=True), \
                    mock.patch("subprocess.Popen") as popen, \
                    mock.patch("time.sleep"), \
                    mock.patch.object(ui_module.ViewerUi, "pid", new=None):
                ui_module.ViewerUi.launch(viewer, r"C:\B\VIEWER.exe", wait=0)
        self.assertEqual(xipl, popen.call_args.kwargs["env"]["XIPL_PATH"])
        self.assertEqual(r"C:\B", popen.call_args.kwargs["cwd"])


if __name__ == "__main__":
    unittest.main()
