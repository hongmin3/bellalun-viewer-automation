# -*- coding: utf-8 -*-
"""``run.py run-regression``을 바깥에서 감시하는 실행 래퍼.

회귀 Python 자체가 강제종료되면 그 프로세스 안의 ``try/finally``나 리포터는
실행될 수 없다. 이 래퍼는 별도 프로세스로 기다렸다가 **새 전체 회귀 리포트가
생겼는지** 확인한다. 없으면 비정상 종료로 기록하고 Viewer를 안전 종료한 뒤
Windows 알림을 보낸다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime

from core import automation_health as health


ROOT = os.path.dirname(os.path.abspath(__file__))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = list(argv or sys.argv[1:])
    started = time.time()
    command = ([sys.executable, os.path.join(ROOT, "run.py")]
               + argv + ["run-regression"])
    child_env = os.environ.copy()
    child_env["BELLALUN_EXTERNAL_GUARD"] = "1"
    child = subprocess.Popen(command, cwd=ROOT, env=child_env)
    health.write_state(
        ROOT, "running", wrapper_pid=os.getpid(), regression_pid=child.pid,
        started=datetime.now().astimezone().isoformat(timespec="seconds"),
        command=command)
    code = child.wait()
    report = health.latest_full_regression(
        os.path.join(ROOT, "Reports"), since=started - 2)
    if report:
        health.write_state(ROOT, "completed", exit_code=code, report=report)
        verdicts = " / ".join(
            "%s %s" % item for item in sorted(report["verdicts"].items()))
        health.notify_windows(
            "Bellalun 전체 회귀 완료",
            "%s · %s" % (verdicts, os.path.basename(report["path"])),
            "warning" if code else "info")
        return code

    detail = health.process_exit_message("VIEWER", started)
    cleanup = None
    try:
        from run import shutdown_viewer
        cleanup = shutdown_viewer("회귀 Python 비정상 종료 후 외부 감시 정리")
    except Exception as exc:                          # noqa: BLE001
        cleanup = {"state": "정리 호출 실패: %s: %s" %
                            (type(exc).__name__, exc)}
    health.write_state(
        ROOT, "abnormal_exit", exit_code=code, process=detail,
        cleanup=cleanup, message="새 전체 회귀 리포트가 생성되지 않았습니다.")
    health.notify_windows(
        "Bellalun 회귀 비정상 종료",
        "리포트가 생성되지 않았습니다. %s" % detail["message"], "error", 12)
    print("[FAIL] 회귀 프로세스가 리포트 없이 종료됐습니다.")
    print("  %s" % detail["message"])
    print("  Viewer 정리: %s" % cleanup)
    print("  상태: %s" % health.state_path(ROOT))
    return code if code else 3


if __name__ == "__main__":
    sys.exit(main())
