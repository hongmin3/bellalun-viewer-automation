"""Validates: REQ-SPECSYNC-001. 동작 파일이 바뀐 커밋은 SPEC도 바꾸거나 예외 표기를 남긴다."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import spec_sync_check as sc


SPEC_TEXT = """# SPEC

## 5. 기능 요구사항

### REQ-DEMO-001 데모 기능

하는 일: 데모.
"""


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


class _Repo:
    def __init__(self, root: Path):
        self.root = root
        _git(root, "init", "-q", "-b", "main")
        _git(root, "config", "user.email", "t@example.invalid")
        _git(root, "config", "user.name", "t")
        _git(root, "config", "core.autocrlf", "false")
        self.write("SPEC.md", SPEC_TEXT)
        self.write("core/a.py", "X = 1\n")
        self.write("docs/note.md", "note\n")
        self.commit("init")

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message):
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", message)
        return _git(self.root, "rev-parse", "HEAD").strip()


class BehaviorPathTests(unittest.TestCase):
    def test_behavior_paths(self):
        for path in ("run.py", "core/ui.py", "bellalunauto/gui.py", "remote/service.py",
                     "tests/workflow01.py", "tests/test_x.py", "core/sub/deep.py"):
            self.assertTrue(sc.is_behavior_path(path), path)

    def test_non_behavior_paths(self):
        for path in ("SPEC.md", "docs/a.md", "tools/x.py", "core/readme.md", "progress.md",
                     "tests/__pycache__/x.cpython-312.pyc", "remote/static/app.js"):
            self.assertFalse(sc.is_behavior_path(path), path)

    def test_spec_paths(self):
        self.assertTrue(sc.is_spec_path("SPEC.md"))
        self.assertTrue(sc.is_spec_path("specs/export.md"))
        self.assertFalse(sc.is_spec_path("docs/SPEC.html"))


class ExemptionParseTests(unittest.TestCase):
    def test_parses_id_and_reason(self):
        found = sc.parse_exemptions("fix: x\n\n[spec-unchanged: REQ-DEMO-001 기존 사양 미충족 버그]\n")
        self.assertEqual(found, [("REQ-DEMO-001", "기존 사양 미충족 버그")])

    def test_requires_reason(self):
        self.assertEqual(sc.parse_exemptions("[spec-unchanged: REQ-DEMO-001]"), [])
        self.assertEqual(sc.parse_exemptions("[spec-unchanged: REQ-DEMO-001   ]"), [])

    def test_requires_requirement_id(self):
        self.assertEqual(sc.parse_exemptions("[spec-unchanged: 버그 수정]"), [])

    def test_comment_lines_ignored(self):
        self.assertEqual(sc.parse_exemptions("# [spec-unchanged: REQ-DEMO-001 이유]\nfix"), [])


class EvaluateTests(unittest.TestCase):
    ids = {"REQ-DEMO-001"}

    def test_behavior_without_spec_fails(self):
        problem = sc.evaluate(["core/a.py"], "fix: a", self.ids)
        self.assertIsNotNone(problem)
        self.assertIn("core/a.py", problem)

    def test_behavior_with_spec_passes(self):
        self.assertIsNone(sc.evaluate(["core/a.py", "SPEC.md"], "feat: a", self.ids))

    def test_docs_only_passes(self):
        self.assertIsNone(sc.evaluate(["docs/a.md", "progress.md"], "docs", self.ids))

    def test_exemption_with_known_id_passes(self):
        msg = "fix: a\n\n[spec-unchanged: REQ-DEMO-001 기존 사양대로 고치는 버그]"
        self.assertIsNone(sc.evaluate(["core/a.py"], msg, self.ids))

    def test_exemption_with_unknown_id_fails(self):
        msg = "fix: a\n\n[spec-unchanged: REQ-NOPE-001 이유]"
        problem = sc.evaluate(["core/a.py"], msg, self.ids)
        self.assertIsNotNone(problem)
        self.assertIn("REQ-NOPE-001", problem)


class RangeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _Repo(Path(self._tmp.name))
        self.base = _git(self.repo.root, "rev-parse", "HEAD").strip()

    def tearDown(self):
        self._tmp.cleanup()

    def test_range_flags_only_offending_commit(self):
        self.repo.write("core/a.py", "X = 2\n")
        self.repo.write("SPEC.md", SPEC_TEXT + "\n추가.\n")
        self.repo.commit("feat: with spec")
        self.repo.write("core/a.py", "X = 3\n")
        bad = self.repo.commit("fix: no spec")
        self.repo.write("docs/note.md", "n2\n")
        self.repo.commit("docs: only")
        problems = sc.check_range(self.repo.root, self.base, "HEAD")
        self.assertEqual([c for c, _ in problems], [bad])

    def test_range_accepts_exemption(self):
        self.repo.write("tests/test_a.py", "def test_a():\n    pass\n")
        self.repo.commit("test: regression\n\n[spec-unchanged: REQ-DEMO-001 기존 사양의 재현 시험]")
        self.assertEqual(sc.check_range(self.repo.root, self.base, "HEAD"), [])

    def test_rename_counts_as_behavior_change(self):
        _git(self.repo.root, "mv", "core/a.py", "docs/a.py")
        self.repo.commit("move")
        self.assertEqual(len(sc.check_range(self.repo.root, self.base, "HEAD")), 1)

    def test_main_range_exit_codes(self):
        self.assertEqual(sc.main(["--repo", str(self.repo.root), "--base", self.base]), 0)
        self.repo.write("run.py", "print(1)\n")
        self.repo.commit("feat: run")
        self.assertEqual(sc.main(["--repo", str(self.repo.root), "--base", self.base]), 1)


class StagedTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _Repo(Path(self._tmp.name))
        self.msg = Path(self._tmp.name) / "MSG"

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, message):
        self.msg.write_text(message, encoding="utf-8")
        return sc.main(["--repo", str(self.repo.root), "--staged", "--message-file", str(self.msg)])

    def test_staged_behavior_without_spec_blocks(self):
        self.repo.write("core/a.py", "X = 9\n")
        _git(self.repo.root, "add", "-A")
        self.assertEqual(self._run("fix: a\n"), 1)

    def test_staged_with_exemption_passes(self):
        self.repo.write("core/a.py", "X = 9\n")
        _git(self.repo.root, "add", "-A")
        self.assertEqual(self._run("fix: a\n\n[spec-unchanged: REQ-DEMO-001 기존 사양 버그]\n"), 0)

    def test_unstaged_change_is_not_counted(self):
        self.repo.write("core/a.py", "X = 9\n")
        self.assertEqual(self._run("docs\n"), 0)


class HookInstallTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _Repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_install_writes_marked_hook_and_blocks_commit(self):
        from tools import install_git_hooks as ih
        self.repo.write("tools/spec_sync_check.py", Path(sc.__file__).read_text(encoding="utf-8"))
        self.repo.commit("tools\n\n[spec-unchanged: REQ-DEMO-001 시험용]")
        self.assertEqual(ih.main(["--repo", str(self.repo.root)]), 0)
        hook = Path(_git(self.repo.root, "rev-parse", "--git-path", "hooks").strip())
        if not hook.is_absolute():
            hook = self.repo.root / hook
        text = (hook / "commit-msg").read_text(encoding="utf-8")
        self.assertIn(ih.MARKER, text)
        self.repo.write("core/a.py", "X = 5\n")
        _git(self.repo.root, "add", "-A")
        blocked = subprocess.run(["git", "-C", str(self.repo.root), "commit", "-q", "-m", "fix: a"],
                                 capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(blocked.returncode, 0)
        ok = subprocess.run(["git", "-C", str(self.repo.root), "commit", "-q", "-m",
                             "fix: a\n\n[spec-unchanged: REQ-DEMO-001 기존 사양 버그]"],
                            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_install_refuses_foreign_hook(self):
        from tools import install_git_hooks as ih
        hooks = self.repo.root / ".git" / "hooks"
        (hooks / "commit-msg").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        self.assertEqual(ih.main(["--repo", str(self.repo.root)]), 1)
        self.assertIn("echo mine", (hooks / "commit-msg").read_text(encoding="utf-8"))

    def test_check_reports_missing(self):
        from tools import install_git_hooks as ih
        self.assertEqual(ih.main(["--repo", str(self.repo.root), "--check"]), 1)


if __name__ == "__main__":
    unittest.main()
