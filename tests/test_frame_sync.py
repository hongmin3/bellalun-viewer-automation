# -*- coding: utf-8 -*-
"""공통 자동화 프레임 사본 검사.

Validates: REQ-FRAME-001
"""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("frame_sync_check", REPO / "frame" / "sync_check.py")
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)


class RepoFrameTests(unittest.TestCase):
    def test_this_checkout_matches_lock_and_sibling(self):
        out = io.StringIO()
        self.assertEqual(sync.check(REPO, out), 0, out.getvalue())


class SiblingSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.a = self._repo("A/auto", {"shared.txt": "같은 내용\n"})
        self.b = self.tmp / "B" / "auto"

    def _repo(self, rel, files):
        root = self.tmp / rel
        (root / "frame").mkdir(parents=True)
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        lock = {"version": 1, "products": {"a": "A/auto", "b": "B/auto"},
                "files": {name: "" for name in files}}
        (root / sync.LOCK_NAME).write_text(json.dumps(lock), encoding="utf-8")
        sync.update_lock(root, io.StringIO())
        return root

    def _check(self, root):
        out = io.StringIO()
        return sync.check(root, out), out.getvalue()

    def test_missing_sibling_folder_is_notice_only(self):
        code, text = self._check(self.a)
        self.assertEqual(code, 0, text)
        self.assertIn("[안내]", text)

    def test_sibling_without_frame_fails(self):
        self.b.mkdir(parents=True)
        code, text = self._check(self.a)
        self.assertEqual(code, 1)
        self.assertIn("미반영", text)

    def test_edit_without_lock_update_fails(self):
        (self.a / "shared.txt").write_text("바뀐 내용\n", encoding="utf-8")
        code, text = self._check(self.a)
        self.assertEqual(code, 1)
        self.assertIn("잠금과 다름: shared.txt", text)

    def test_propagate_makes_both_sides_pass(self):
        self.b.mkdir(parents=True)
        (self.a / "shared.txt").write_text("바뀐 내용\n", encoding="utf-8")
        sync.update_lock(self.a, io.StringIO())
        self.assertEqual(self._check(self.a)[0], 1)  # 형제에 아직 반영 전
        self.assertEqual(sync.propagate(self.a, io.StringIO()), 0)
        self.assertEqual(self._check(self.a)[0], 0)
        self.assertEqual(self._check(self.b)[0], 0)

    def test_sibling_edit_is_detected_from_other_side(self):
        self.b.mkdir(parents=True)
        sync.propagate(self.a, io.StringIO())
        (self.b / "shared.txt").write_text("형제만 바꿈\n", encoding="utf-8")
        sync.update_lock(self.b, io.StringIO())
        code, text = self._check(self.a)
        self.assertEqual(code, 1)
        self.assertIn("내용 다름: shared.txt", text)

    def test_line_endings_do_not_count_as_difference(self):
        self.b.mkdir(parents=True)
        sync.propagate(self.a, io.StringIO())
        (self.b / "shared.txt").write_bytes("같은 내용\r\n".encode("utf-8"))
        self.assertEqual(self._check(self.a)[0], 0)


if __name__ == "__main__":
    unittest.main()
