"""XIPL PID/window readiness with a virtual clock. Never launch or input UI."""
from types import SimpleNamespace

import pytest


class Clock:
    def __init__(self):
        self.elapsed = 0.0

    def now(self):
        return self.elapsed

    def sleep(self, seconds):
        self.elapsed += seconds


def driver(monkeypatch, *, visible_at=0, died_at=None, ready_at=0, replaced_at=None):
    from core import xipl
    clock = Clock()
    calls = []

    class FakeUi:
        @property
        def pid(self):
            if died_at is not None and clock.elapsed >= died_at:
                return None
            return 43 if replaced_at is not None and clock.elapsed >= replaced_at else 42

        def main_window(self):
            if self.pid is None or clock.elapsed < visible_at:
                return None
            if clock.elapsed < ready_at:
                return SimpleNamespace(hwnd=101, text="", rect=(0, 0, 650, 566))
            return SimpleNamespace(hwnd=102, text="XIPL STUDIO", rect=(0, 0, 1024, 768))

        def click(self, point, settle):
            calls.append(("login_click", point))
            clock.sleep(settle)

    monkeypatch.setattr(xipl, "time", SimpleNamespace(time=clock.now, monotonic=clock.now, sleep=clock.sleep))
    monkeypatch.setattr(xipl, "ViewerUi", lambda name: FakeUi())
    monkeypatch.setattr(xipl, "ctypes", SimpleNamespace(windll=SimpleNamespace(user32=SimpleNamespace(
        ShowWindow=lambda *args: calls.append(("show", args)),
        SetForegroundWindow=lambda *args: calls.append(("foreground", args))))))

    def never_launch(*args, **kwargs):
        raise AssertionError("An existing Viewer-launched process must not be relaunched.")
    monkeypatch.setattr(xipl.subprocess, "Popen", never_launch)
    studio = xipl.XiplStudio(exe="C:/synthetic/XIPL.STUDIO.exe")
    monkeypatch.setattr(studio, "_place_normal_window", lambda hwnd: calls.append(("place", hwnd)))
    monkeypatch.setattr(studio, "_uia_invoke_named", lambda *args: False)
    monkeypatch.setattr(studio, "click_text", lambda *args: False)
    return studio, clock, calls


def test_default_wait_accepts_23_second_real_world_window_startup(monkeypatch):
    studio, clock, calls = driver(monkeypatch, visible_at=23.5)
    window = studio.start()
    assert window.hwnd == 102
    assert 23.5 <= clock.elapsed < 25
    assert ("place", 102) in calls


def test_window_wait_is_bounded_and_reports_live_pid_and_executable(monkeypatch):
    studio, clock, calls = driver(monkeypatch, visible_at=100)
    with pytest.raises(RuntimeError) as error:
        studio.start(timeout=2)
    assert "42" in str(error.value) and "C:/synthetic/XIPL.STUDIO.exe" in str(error.value)
    assert 2 <= clock.elapsed < 3
    assert not calls


def test_process_exit_during_window_startup_fails_immediately(monkeypatch):
    studio, clock, calls = driver(monkeypatch, visible_at=100, died_at=3)
    with pytest.raises(RuntimeError) as error:
        studio.start(timeout=90)
    assert "종료" in str(error.value) and "42" in str(error.value)
    assert 3 <= clock.elapsed < 4
    assert not calls


def test_replacement_process_cannot_satisfy_original_startup(monkeypatch):
    studio, clock, calls = driver(monkeypatch, visible_at=10, replaced_at=1)
    with pytest.raises(RuntimeError) as error:
        studio.start(timeout=90)
    assert "42" in str(error.value) and "43" in str(error.value)
    assert clock.elapsed < 2
    assert not calls


def test_login_window_is_not_accepted_as_a_ready_studio(monkeypatch):
    studio, clock, calls = driver(monkeypatch, ready_at=100)
    with pytest.raises(RuntimeError) as error:
        studio.start(timeout=2)
    assert "로그인" in str(error.value) and "42" in str(error.value)
    assert not any(action[0] == "show" for action in calls)


def test_slow_login_waits_for_real_work_window_and_returns_early(monkeypatch):
    studio, clock, calls = driver(monkeypatch, ready_at=23.5)
    window = studio.start()
    assert window.hwnd == 102
    assert 23.5 <= clock.elapsed < 25
    assert ("place", 102) in calls
