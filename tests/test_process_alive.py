# -*- coding: utf-8 -*-
"""ViewerUi._alive: 다른 프로세스가 핸들을 쥔 종료 프로세스를 살아 있다고 보지 않는다.

2026-11-26 job270 WU_09: 제품 로그에 Export Manager closed(21:20:21)가 남았는데도
OpenProcess 성공만으로 생존을 판정해 60초 종료 대기가 FAIL 했다.
"""
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 프로세스 핸들 동작")


def test_exited_process_with_open_handle_is_not_alive():
    from core.ui import ViewerUi

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        proc.wait(timeout=30)
        # Popen 이 프로세스 핸들을 아직 쥐고 있어 커널 객체가 남아 있다.
        assert proc._handle
        assert ViewerUi._alive(proc.pid) is False
    finally:
        proc.wait()


def test_running_process_is_alive():
    from core.ui import ViewerUi

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert ViewerUi._alive(proc.pid) is True
    finally:
        proc.kill()
        proc.wait()
    assert ViewerUi._alive(proc.pid) is False


def test_missing_pid_is_not_alive():
    from core.ui import ViewerUi

    assert ViewerUi._alive(0) is False
