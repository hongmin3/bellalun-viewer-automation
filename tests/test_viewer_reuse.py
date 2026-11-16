# -*- coding: utf-8 -*-
"""깨끗한 Viewer면 TC 시작 재시작을 생략한다.

Validates: REQ-SPEEDUP-005
"""
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import flows

ROOT = Path(__file__).resolve().parents[1]


class FakeDb:
    def __init__(self, examining=0, ping=True, fail=False):
        self.examining, self._ping, self.fail = examining, ping, fail

    def ping(self):
        return self._ping

    def one(self, db, sql, params=None):
        if self.fail:
            raise RuntimeError("query failed")
        assert "StudyStatus" in sql and params == {"s": flows.STUDY_STATUS_EXAMINING}
        return {"n": self.examining}


def fake_ui(pid=100, login=False, dialog=False, patient=True, examined=False):
    def by_id(ctrl_id):
        return [object()] if patient and ctrl_id == flows.PATIENT["tab_new_patient"] else []
    windows = [SimpleNamespace(visible=True, text="Examined")] if examined else []
    return SimpleNamespace(pid=pid, at_login_screen=lambda: login,
                           dialog=lambda: object() if dialog else None,
                           by_id=by_id, windows=lambda: windows)


class StartCleanViewerTests(unittest.TestCase):
    def start(self, ui, db, *, force=False):
        calls = []

        def cold_start(cfg, db_, on_event=None, force_restart=None):
            calls.append(force_restart)
            return "UI", ["기동 로그"]
        cfg = {"viewer": {"force_restart": force}}
        with patch.object(flows, "ViewerUi", return_value=ui), \
                patch.object(flows, "cold_start", side_effect=cold_start), \
                patch.object(flows, "ensure_patient_screen",
                             side_effect=AssertionError("재사용 확인은 화면을 옮기지 않는다")), \
                patch.object(flows, "known_screen", return_value=["examine"]):
            result_ui, log = flows.start_clean_viewer(cfg, db)
        self.assertEqual(result_ui, "UI")
        self.assertEqual(len(calls), 1)
        return calls[0], log

    def test_clean_viewer_is_reused(self):
        force, log = self.start(fake_ui(), FakeDb())
        self.assertFalse(force)
        self.assertTrue(log[0].startswith("재시작 생략"))
        self.assertEqual(log[1], "기동 로그")

    def test_each_failed_condition_forces_restart(self):
        cases = {
            "미실행": (fake_ui(pid=None), FakeDb(), {}),
            "로그인 화면": (fake_ui(login=True), FakeDb(), {}),
            "DB": (fake_ui(), FakeDb(ping=False), {}),
            "팝업": (fake_ui(dialog=True), FakeDb(), {}),
            "Examine": (fake_ui(), FakeDb(examining=1), {}),
            "Patient 화면 아님(View·Examine)": (fake_ui(patient=False), FakeDb(), {}),
            "Examined 창": (fake_ui(examined=True), FakeDb(), {}),
            "설정": (fake_ui(), FakeDb(), {"force": True}),
            "예외": (fake_ui(), FakeDb(fail=True), {}),
        }
        for name, (ui, db, extra) in cases.items():
            with self.subTest(name):
                force, log = self.start(ui, db, **extra)
                self.assertTrue(force)
                self.assertTrue(log[0].startswith("강제 재시작"), log[0])


def _calls(path):
    return Path(ROOT / path).read_text(encoding="utf-8")


class ScopeTests(unittest.TestCase):
    REUSE = ["tests/workflow02.py", "tests/workflow10.py", "tests/workflow11.py",
             "tests/workflow12.py", "tests/workflow13.py", "core/viewer_processing.py"]
    KEEP = ["tests/workflow04.py", "tests/workflow06.py", "tests/workflow07.py",
            "tests/workflow08.py", "tests/workflow14.py", "tests/workflow15.py",
            "core/dicom_settings.py"]

    def test_reuse_scope_uses_start_clean_viewer(self):
        for path in self.REUSE:
            with self.subTest(path):
                self.assertIn("start_clean_viewer(", _calls(path))
        for path in ["tests/workflow02.py", "tests/workflow10.py", "tests/workflow11.py",
                     "tests/workflow12.py", "core/viewer_processing.py"]:
            with self.subTest(path):
                self.assertNotIn("force_restart=True", _calls(path))

    def test_wf13_keeps_account_switch_restarts(self):
        text = _calls("tests/workflow13.py")
        self.assertEqual(text.count("start_clean_viewer("), 1)
        self.assertGreaterEqual(len(re.findall(r"cold_start\([^)]*force_restart=True", text)), 2)

    def test_documented_restarts_are_kept(self):
        for path in self.KEEP:
            with self.subTest(path):
                text = _calls(path)
                self.assertIn("force_restart=True", text)
                self.assertNotIn("start_clean_viewer(", text)
