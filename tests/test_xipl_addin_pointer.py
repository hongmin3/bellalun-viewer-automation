# -*- coding: utf-8 -*-
"""XIPL PIM 편집기(AddInProcess.exe) 클릭은 XIPL.STUDIO 의 직접 자식만, 그 클릭 동안만 허용한다.

Validates: REQ-REGRESSION-001

run702 실측: 설치판 1.0.19 기본 전체의 XIPL06 이 `AddInProcess.exe pid=9504
class=HwndWrapper[Process;...]` 창(=PIM 편집기)을 다른 프로그램으로 보고 멈췄다.
"""
import subprocess
from types import SimpleNamespace
from unittest import mock

from core import ui as ui_mod
from core.xipl import XiplStudio

STUDIO, ADDIN, OTHER = 424242, 9504, 777


def test_helper_pid_owned_only_when_listed():
    ui = SimpleNamespace(pid=STUDIO, helper_pids=frozenset())
    assert ui_mod._owned(ui, STUDIO)
    assert not ui_mod._owned(ui, ADDIN)
    ui.helper_pids = frozenset({ADDIN})
    assert ui_mod._owned(ui, ADDIN)
    assert not ui_mod._owned(ui, OTHER)
    assert not ui_mod._owned(SimpleNamespace(pid=None, helper_pids={ADDIN}), ADDIN)


def test_pointer_guard_accepts_addin_editor_but_not_other_program():
    ui = ui_mod.ViewerUi("XIPL.STUDIO")
    ui._pid = STUDIO
    owner = {}
    with mock.patch.object(ui_mod.ViewerUi, "pid", new=STUDIO), \
            mock.patch.object(ui_mod, "_window_at_point", lambda p: 17371240), \
            mock.patch.object(ui_mod, "_pid_of", lambda h: owner["pid"]):
        owner["pid"] = ADDIN
        ui.helper_pids = frozenset({ADDIN})
        assert ui.require_front_for_pointer(point=(700, 220)) is True
        owner["pid"] = OTHER
        with mock.patch.object(ui, "bring_to_front", return_value={"ok": False, "blocking": None}):
            try:
                ui.require_front_for_pointer(point=(700, 220))
            except ui_mod.ForegroundError:
                pass
            else:
                raise AssertionError("다른 프로그램 창 클릭이 허용됐다")


def test_set_pim_field_allows_addin_child_only_during_blur_click(monkeypatch):
    studio = object.__new__(XiplStudio)
    seen = []
    studio.ui = SimpleNamespace(pid=STUDIO, helper_pids=frozenset(),
                                main_window=lambda: SimpleNamespace(rect=(448, 156, 1472, 924)))
    studio.ui.click = lambda point, settle=0: seen.append((point, studio.ui.helper_pids))
    monkeypatch.setattr(subprocess, "run",
                        lambda c, **k: subprocess.CompletedProcess(c, 0, b"OK|10|15", b""))
    monkeypatch.setattr("core.xipl.child_pids",
                        lambda pid, name: frozenset({ADDIN}) if (pid, name) == (STUDIO, "AddInProcess.exe") else frozenset())
    assert studio.set_pim_field("Contrast", 15)["after"] == 15.0
    assert seen == [((448 + 205, 156 + 65), frozenset({ADDIN}))]
    assert studio.ui.helper_pids == frozenset()
