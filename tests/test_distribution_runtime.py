"""Safe filesystem/process tests. Validates: REQ-DIST-001, REQ-DIST-002."""
from __future__ import annotations

import importlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

try:
    runtime = importlib.import_module("bellalunauto.runtime")
except ModuleNotFoundError:
    runtime = None


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(runtime, "distribution runtime must exist")
        self.temp = tempfile.TemporaryDirectory(prefix="Bellalun 한글 ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.resources = self.root / "설치 자료"
        self.resources.mkdir()
        template = {
            "display": {"width": 1920, "enforce": True},
            "viewer": {"login": {"id": "private", "password": "secret"},
                       "accounts": {"private": "secret"}},
            "dicom": {"storage_scp": {"api_url": "http://10.1.2.3:5003",
                                       "host": "10.1.2.3", "port": 11116},
                      "servers_to_register": [{"kind": "Storage", "ip": "10.1.2.3"}]},
        }
        (self.resources / "config.example.json").write_text(json.dumps(template), encoding="utf-8")
        self.preferences = self.root / "환경 설정"

    def layout(self, **kwargs):
        return runtime.resolve_layout(resource_dir=self.resources,
                                      preferences_dir=self.preferences, **kwargs)

    @contextmanager
    def compiled_install(self):
        install = self.root / "BellalunAuto 설치"
        with patch.object(runtime, "_compiled", return_value=True), \
             patch.object(runtime.sys, "executable", str(install / "BellalunAuto.exe")):
            yield install

    def test_default_workspace_is_local_appdata_and_does_not_write(self):
        local = self.root / "local"
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
            layout = self.layout()
        self.assertEqual(layout.workspace, local / "BellalunAuto" / "workspace")
        self.assertEqual(layout.config_path, layout.workspace / "config.json")
        self.assertFalse(local.exists())

    def test_remembered_unicode_workspace_survives_cwd_change(self):
        chosen = self.root / "QA 결과"
        runtime.remember_workspace(chosen, self.preferences)
        original = Path.cwd()
        try:
            os.chdir(self.root)
            layout = self.layout()
        finally:
            os.chdir(original)
        self.assertEqual(layout.workspace, chosen)
        self.assertEqual(layout.resource_dir, self.resources)

    def test_explicit_workspace_overrides_saved_preference(self):
        runtime.remember_workspace(self.root / "old", self.preferences)
        self.assertEqual(self.layout(workspace=self.root / "new").workspace, self.root / "new")

    def test_explicit_relative_paths_resolve_once(self):
        config = self.root / "별도 설정.json"
        config.write_text("{}", encoding="utf-8")
        original = Path.cwd()
        try:
            os.chdir(self.root)
            layout = self.layout(workspace="결과", config_path="별도 설정.json")
        finally:
            os.chdir(original)
        self.assertEqual(layout.workspace, self.root / "결과")
        self.assertEqual(layout.config_path, config)

    def test_explicit_missing_config_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            self.layout(config_path=self.root / "typo.json")

    def test_defaults_are_read_only_and_contain_no_template_secrets(self):
        layout = self.layout(workspace=self.root / "work")
        config = runtime.load_config(layout)
        self.assertEqual(config["display"]["width"], 1920)
        self.assertEqual(config["dicom"]["storage_scp"]["port"], 11116)
        payload = json.dumps(config)
        for forbidden in ("private", "secret", "10.1.2.3"):
            self.assertNotIn(forbidden, payload)
        self.assertFalse(layout.workspace.exists())

    def test_existing_config_preserves_custom_settings_and_credentials(self):
        layout = self.layout(workspace=self.root / "work")
        supplied = {"viewer": {"login": {"password": "do-not-print"}}, "custom": [1, 2]}
        runtime.save_config(layout, supplied)
        self.assertEqual(runtime.load_config(layout), supplied)
        self.assertEqual(list(layout.workspace.iterdir()), [layout.config_path])

    def test_failed_atomic_replace_preserves_previous_config_and_cleans_temp(self):
        layout = self.layout(workspace=self.root / "work")
        runtime.save_config(layout, {"generation": 1})
        with patch.object(runtime.os, "replace", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                runtime.save_config(layout, {"generation": 2})
        self.assertEqual(runtime.load_config(layout), {"generation": 1})
        self.assertEqual(list(layout.workspace.iterdir()), [layout.config_path])

    def test_non_object_json_is_rejected(self):
        config = self.root / "invalid.json"
        config.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            runtime.load_config(self.layout(config_path=config))

    def test_source_child_command_has_absolute_entrypoint_and_preserves_arguments(self):
        command = runtime.child_command(["--workspace", "한글 공백", "run-regression"],
                                        executable=sys.executable, compiled=False)
        self.assertEqual(command[0], sys.executable)
        self.assertTrue(Path(command[1]).is_absolute())
        self.assertEqual(Path(command[1]).name, "BellalunAuto.py")
        self.assertEqual(command[2:], ["--workspace", "한글 공백", "run-regression"])

    def test_compiled_child_command_executes_self_once(self):
        exe = str(self.root / "설치 경로" / "BellalunAuto.exe")
        self.assertEqual(runtime.child_command(["--worker", "run-winupdate"], exe, True),
                         [exe, "--worker", "run-winupdate"])

    def test_windows_compiled_default_uses_native_exe_instead_of_missing_python(self):
        native = str(self.root / "설치 경로" / "BellalunAuto.exe")
        missing = str(self.root / "설치 경로" / "python.exe")
        self.assertFalse(Path(missing).exists())
        with patch.object(runtime, "_compiled", return_value=True), \
             patch.object(runtime.sys, "executable", missing), \
             patch.object(runtime, "_windows_executable_path", return_value=native, create=True) as locate:
            self.assertEqual(runtime.child_command(["--worker"]), [native, "--worker"])
        locate.assert_called_once_with()

    def test_source_and_explicit_executable_do_not_query_native_module(self):
        with patch.object(runtime, "_windows_executable_path", side_effect=AssertionError("unexpected native lookup"), create=True):
            self.assertEqual(runtime.child_command(["--worker"], "chosen.exe", True),
                             ["chosen.exe", "--worker"])
            self.assertEqual(runtime.child_command(["--help"], compiled=False)[0], sys.executable)

    @unittest.skipUnless(os.name == "nt", "Windows module path API")
    def test_native_executable_path_expands_truncated_buffer_and_keeps_unicode(self):
        native = "D:\\한글 설치\\" + "a" * 280 + "\\BellalunAuto.exe"
        sizes = []

        def locate(module, buffer, size):
            self.assertIsNone(module)
            sizes.append(size)
            if len(native) >= size:
                return size
            buffer.value = native
            return len(native)

        function = Mock(side_effect=locate)
        kernel = Mock(GetModuleFileNameW=function)
        with patch.object(runtime.ctypes, "WinDLL", return_value=kernel):
            self.assertEqual(runtime._windows_executable_path(), native)
        self.assertEqual(sizes, [260, 520])

    @unittest.skipUnless(os.name == "nt", "Windows module path API")
    def test_native_executable_path_failure_is_explicit_and_never_falls_back(self):
        kernel = Mock(GetModuleFileNameW=Mock(return_value=0))
        with patch.object(runtime.ctypes, "WinDLL", return_value=kernel), \
             patch.object(runtime.ctypes, "get_last_error", return_value=5), \
             patch.object(runtime, "_compiled", return_value=True):
            with self.assertRaises(OSError):
                runtime.child_command(["--worker"])

    @unittest.skipUnless(os.name == "nt", "Windows module path API")
    def test_native_executable_path_growth_has_finite_limit(self):
        sizes = []

        def truncated(module, buffer, size):
            sizes.append(size)
            return size

        kernel = Mock(GetModuleFileNameW=Mock(side_effect=truncated))
        with patch.object(runtime.ctypes, "WinDLL", return_value=kernel):
            with self.assertRaisesRegex(RuntimeError, "버퍼 한도"):
                runtime._windows_executable_path()
        self.assertEqual(sizes[-1], 32768)
        self.assertLessEqual(len(sizes), 8)

    def test_nuitka_compiled_marker_is_recognized(self):
        with patch.object(runtime, "__compiled__", object(), create=True):
            self.assertEqual(runtime.child_command(["--worker"], "BellalunAuto.exe"),
                             ["BellalunAuto.exe", "--worker"])

    def test_compiled_resources_use_executable_location(self):
        with patch.object(runtime, "__compiled__", object(), create=True), \
             patch.object(sys, "executable", str(self.root / "install" / "BellalunAuto.exe")):
            layout = runtime.resolve_layout(workspace=self.root / "work",
                                            preferences_dir=self.preferences)
        self.assertEqual(layout.resource_dir, self.root / "install" / "resources")

    def test_compiled_workspace_inside_installation_is_rejected(self):
        with self.compiled_install() as install:
            for work in (install, install / "resources" / "작업 결과"):
                with self.subTest(work=work), self.assertRaisesRegex(ValueError, "설치 폴더 밖"):
                    self.layout(workspace=work)
        self.assertFalse(install.exists())

    def test_compiled_config_inside_installation_is_rejected(self):
        with self.compiled_install() as install:
            config = install / "resources" / "config.json"
            config.parent.mkdir(parents=True)
            config.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "설치 폴더 밖"):
                self.layout(workspace=self.root / "outside", config_path=config)
            self.assertEqual(config.read_text(encoding="utf-8"), "{}")

    def test_compiled_direct_layout_save_rejects_installation_destinations_before_writing(self):
        with self.compiled_install() as install:
            for workspace, config in ((install / "work", self.root / "outside.json"),
                                      (self.root / "outside", install / "config.json")):
                layout = runtime.Layout(self.resources, workspace, config)
                with self.subTest(config=config), self.assertRaisesRegex(ValueError, "설치 폴더 밖"):
                    runtime.save_config(layout, {"fixture": True})
                self.assertFalse(config.exists())
        self.assertFalse(install.exists())

    def test_compiled_external_unicode_workspace_and_explicit_config_are_writable(self):
        workspace = self.root / "외부 작업 결과"
        config = self.root / "별도 설정.json"
        config.write_text("{}", encoding="utf-8")
        with self.compiled_install():
            layout = self.layout(workspace=workspace, config_path=config)
            runtime.save_config(layout, {"fixture": True})
            self.assertEqual(runtime.load_config(layout), {"fixture": True})
            self.assertEqual(layout.workspace, workspace)

    def test_compiled_similarly_named_sibling_folder_is_writable(self):
        with self.compiled_install() as install:
            sibling = install.with_name(install.name + "-작업")
            layout = self.layout(workspace=sibling)
            runtime.save_config(layout, {"fixture": True})
            self.assertEqual(runtime.load_config(layout), {"fixture": True})

    def test_source_mode_preserves_repository_workspace_compatibility(self):
        with self.compiled_install() as install:
            with patch.object(runtime, "_compiled", return_value=False):
                layout = self.layout(workspace=install)
                runtime.save_config(layout, {"fixture": True})
                self.assertEqual(runtime.load_config(layout), {"fixture": True})

    def test_compiled_symlink_into_installation_is_rejected(self):
        with self.compiled_install() as install:
            install.mkdir()
            alias = self.root / "외부 링크"
            try:
                alias.symlink_to(install, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks unavailable for this account")
            with self.assertRaisesRegex(ValueError, "설치 폴더 밖"):
                self.layout(workspace=alias / "결과")

    @unittest.skipUnless(os.name == "nt", "Windows global mutex")
    def test_global_lock_rejects_second_instance_and_releases_after_exception(self):
        name = "Global\\BellalunAuto-test-" + uuid.uuid4().hex
        with self.assertRaisesRegex(RuntimeError, "body error"):
            with runtime.RunLock(name):
                with self.assertRaises(runtime.AlreadyRunning):
                    with runtime.RunLock(name):
                        self.fail("second lock acquired")
                raise RuntimeError("body error")
        with runtime.RunLock(name):
            pass

    @unittest.skipUnless(os.name == "nt", "Windows global mutex")
    def test_global_lock_rejects_other_process_from_different_cwd(self):
        name = "Global\\BellalunAuto-test-" + uuid.uuid4().hex
        source_root = str(Path(__file__).resolve().parents[1])
        script = ("import sys; sys.path.insert(0, sys.argv[1]); "
                  "from bellalunauto.runtime import RunLock, AlreadyRunning\n"
                  "try:\n with RunLock(sys.argv[2]): sys.exit(8)\n"
                  "except AlreadyRunning: sys.exit(0)\n")
        with runtime.RunLock(name):
            child = subprocess.run([sys.executable, "-c", script, source_root, name],
                                   cwd=self.root, capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)


if __name__ == "__main__":
    unittest.main()
