# -*- coding: utf-8 -*-
"""TEST-TRACE-001: 통합 사양서 선택과 인용 위치 (REQ-TRACE-001). 실제 사양서를 쓰지 않는다."""

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from core import specs


class SpecPathsTest(unittest.TestCase):
    def ctx(self, folder):
        return SimpleNamespace(cfg={"knowledge_dir": folder}, root=folder)

    def test_picks_latest_unified_spec_and_ignores_old_volumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("(사양서) Bellalun Viewer 사양서1(260710).pdf",
                         "(사양서) Bellalun Viewer 사양서2(260710).pdf",
                         "(사양서) Bellalun Viewer 사양서(260901).pdf",
                         "(사양서) Bellalun Viewer 사양서(261030).pdf",
                         "Bellalun Viewer 사양서(261030).txt"):
                open(os.path.join(tmp, name), "wb").close()
            self.assertEqual(specs.spec_paths(self.ctx(tmp)),
                             {"사양서": os.path.join(tmp, "(사양서) Bellalun Viewer 사양서(261030).pdf")})

    def test_old_volumes_alone_are_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "(사양서) Bellalun Viewer 사양서1(260710).pdf"), "wb").close()
            self.assertEqual(specs.spec_paths(self.ctx(tmp)), {})


class CiteTest(unittest.TestCase):
    def test_prefers_requirement_page_over_change_memo(self):
        # 통합본에는 같은 문장이 SRS 없는 변경 메모(앞쪽)와 요구사항 본문(뒤쪽)에 함께 있다.
        hits = [{"source": "사양서", "page": 294, "srs": [], "text": "메모 설정 가능한 3D Viewposition"},
                {"source": "사양서", "page": 678, "srs": ["SRS 03-30-20"], "text": "설정 가능한 3D Viewposition"}]
        with mock.patch.object(specs, "search", return_value=hits) as search:
            line = specs.cite(None, "설정 가능한 3D Viewposition")
        self.assertIn("678쪽 SRS 03-30-20", line)
        self.assertGreater(search.call_args.kwargs["limit"], 1)

    def test_falls_back_to_first_hit_without_srs(self):
        hits = [{"source": "사양서", "page": 294, "srs": [], "text": "메모"}]
        with mock.patch.object(specs, "search", return_value=hits):
            self.assertIn("294쪽 —", specs.cite(None, "메모"))

    def test_no_hit_returns_fallback(self):
        with mock.patch.object(specs, "search", return_value=[]):
            self.assertEqual(specs.cite(None, "x", fallback="사람이 확인한 인용"), "사람이 확인한 인용")


if __name__ == "__main__":
    unittest.main()
