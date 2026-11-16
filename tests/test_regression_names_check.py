"""Validates: REQ-DIST-003. 회귀 이름 검사가 사슬 함수를 보고 주석 속 이름은 세지 않는다."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_regression_names as checker  # noqa: E402

GOOD = '''
def _basic_chain_stages():
    from tests.install import install_01
    from tests.workflow01 import run as run_workflow01
    return [(install_01, "A", ""), (run_workflow01, "B", "")]


def main(args):
    if args.cmd == "run-regression":
        # install_02 는 주석에만 나온다
        chain = _basic_chain_stages()
        print("install_03 은 문자열에만 나온다")
        return chain
'''


class RegressionNamesCheckTests(unittest.TestCase):
    def test_repository_passes(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tools/check_regression_names.py")],
                              capture_output=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stdout.decode("utf-8", "replace"))

    def test_names_in_comments_and_strings_are_not_counted(self):
        report = checker.check(GOOD)
        self.assertEqual(report["missing"], {})
        self.assertIn("_basic_chain_stages", report["regions"])
        self.assertEqual(report["used"]["_basic_chain_stages"], {"install_01", "run_workflow01"})

    def test_missing_import_in_chain_function_is_detected(self):
        bad = GOOD.replace("    from tests.install import install_01\n", "")
        self.assertEqual(checker.check(bad)["missing"], {"_basic_chain_stages": ["install_01"]})

    def test_import_in_other_branch_does_not_bind(self):
        bad = GOOD.replace('''        chain = _basic_chain_stages()''', '''        chain = [run_emergency]''') + '''
    if args.cmd == "run-wf10":
        from tests.workflow10 import run as run_emergency
'''
        self.assertEqual(checker.check(bad)["missing"], {"run-regression": ["run_emergency"]})

    def test_no_region_or_no_used_name_fails(self):
        self.assertTrue(checker.check("x = 1\n")["errors"])
        empty = "def main(args):\n    if args.cmd == 'run-regression':\n        return 0\n"
        self.assertTrue(checker.check(empty)["errors"])


if __name__ == "__main__":
    unittest.main()
