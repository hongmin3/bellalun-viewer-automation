"""Module checker import and module/class alias regression tests."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ModuleAttrCheckerTests(unittest.TestCase):
    def check_source(self, source, root=ROOT):
        from tools.check_module_attrs import check_paths
        with tempfile.TemporaryDirectory(prefix="module checker ") as folder:
            path = Path(folder) / "candidate.py"
            path.write_text(source, encoding="utf-8")
            return check_paths([path], root=root)

    def test_import_is_quiet_and_preserves_cwd(self):
        with tempfile.TemporaryDirectory(prefix="checker import ") as folder:
            script = (
                "import pathlib,sys; sys.path.insert(0,sys.argv[1]); "
                "before=pathlib.Path.cwd(); import tools.check_module_attrs; "
                "assert pathlib.Path.cwd()==before"
            )
            result = subprocess.run([sys.executable, "-c", script, str(ROOT)],
                                    cwd=folder, capture_output=True, text=True,
                                    encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_imported_class_policy_is_not_module_pollution(self):
        messages = self.check_source(
            "from core.result import TCResult as lowercase\n"
            "lowercase.stop_on_fail = False\n")
        self.assertEqual(messages, [])

    def test_imported_function_attributes_are_not_module_pollution(self):
        messages = self.check_source(
            "from core.result import write_reports as writer\n"
            "writer.policy = False\n")
        self.assertEqual(messages, [])

    def test_from_import_module_function_overwrite_is_detected(self):
        messages = self.check_source("from core import result as sv\nsv.write_reports = []\n")
        self.assertEqual(len(messages), 1)
        self.assertIn("sv.write_reports = ...", messages[0])

    def test_direct_import_module_function_overwrite_is_detected(self):
        messages = self.check_source("import core.result as sv\nsv.write_reports = []\n")
        self.assertEqual(len(messages), 1)
        self.assertIn("sv.write_reports = ...", messages[0])

    def test_uppercase_module_alias_is_not_mistaken_for_class(self):
        messages = self.check_source("from core import result as TCResult\nTCResult.write_reports = []\n")
        self.assertEqual(len(messages), 1)
        self.assertIn("TCResult.write_reports = ...", messages[0])

    def test_existing_module_name_is_allowed_and_missing_name_is_detected(self):
        messages = self.check_source(
            "from core import result as module\n"
            "print(module.write_reports)\n"
            "print(module.this_function_does_not_exist)\n")
        self.assertEqual(len(messages), 1)
        self.assertIn("module.this_function_does_not_exist 이 core.result 에 없습니다", messages[0])

    def test_local_module_file_is_checked_even_when_module_import_fails(self):
        with tempfile.TemporaryDirectory(prefix="checker root ") as folder:
            root = Path(folder)
            package = root / "core"
            package.mkdir()
            (package / "checker_unimportable.py").write_text("raise RuntimeError('unavailable')\n",
                                                            encoding="utf-8")
            messages = self.check_source(
                "from core import checker_unimportable as SV\nSV.func = []\n", root=root)
        self.assertEqual(len(messages), 1)
        self.assertIn("SV.func = ...", messages[0])


if __name__ == "__main__":
    unittest.main()
