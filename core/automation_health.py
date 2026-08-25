# -*- coding: utf-8 -*-
"""회귀 실행 상태, 제품 종료, Windows 알림을 한 곳에서 다룬다.

두 겹으로 동작한다.

* ``run.py`` 안에서는 TC가 끝날 때 Viewer가 사라졌는지 확인한다.
* ``tools_run_regression.py``는 회귀 Python **바깥**에서 기다린다. 따라서 Python
  자체가 예외·강제종료로 사라져 리포트를 못 남긴 경우도 감지할 수 있다.

상태 파일은 ``work/regression_state.json``에 원자적으로 쓴다. ``work/``는 Git
제외 대상이므로 환자·환경 정보가 저장소에 올라가지 않는다.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


STATE_FILE = os.path.join("work", "regression_state.json")
CRASH_DUMP_DIR = os.path.expandvars(r"%LOCALAPPDATA%\CrashDumps")

# 전체 회귀가 끝까지 도달했는지 구분하는 표식. 전제 실패로 조기 종료된 리포트나
# 개별 TC 리포트를 "마지막 정상 전체 회귀"로 오인하지 않는다.
FULL_REGRESSION_MARKERS = {
    "AUTOMATION_ENVIRONMENT_RESET",
    "DICOM_Server_Setup",
    "TC_Basic_WorkFlow_14",
    "TC_XIPL_compatibility_07",
}


def _iso_now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def state_path(root):
    return os.path.join(root, STATE_FILE)


def write_state(root, status, **detail):
    """회귀 상태를 JSON으로 원자적 기록하고 기록 내용을 돌려준다."""
    path = state_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"status": status, "updated": _iso_now(), **detail}
    fd, tmp = tempfile.mkstemp(prefix="regression_state_", suffix=".json",
                               dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return payload


def read_state(root):
    path = state_path(root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def find_crash_dumps(process_name, since=None, dump_dir=None):
    """이번 실행 중 생긴 WER 덤프를 오래된 순서로 돌려준다.

    WER 기본 이름은 ``VIEWER.exe.<pid>.dmp``다. 오래된 덤프를 이번 종료의
    근거로 쓰지 않도록 ``since``(epoch 초)를 항상 넘기는 것이 원칙이다.
    """
    folder = dump_dir or CRASH_DUMP_DIR
    pattern = os.path.join(folder, "%s.exe.*.dmp" % process_name)
    found = glob.glob(pattern)
    if since is not None:
        found = [path for path in found if os.path.getmtime(path) >= since]
    return sorted(found, key=os.path.getmtime)


def _report_time(data, path):
    raw = data.get("generated")
    if raw:
        try:
            return datetime.fromisoformat(raw).timestamp()
        except (TypeError, ValueError):
            pass
    return os.path.getmtime(path)


def _is_full_regression(data):
    ids = {row.get("tc_id") for row in data.get("results", [])}
    return FULL_REGRESSION_MARKERS <= ids


def latest_full_regression(reports_dir, since=None):
    """가장 최근의 **끝까지 완료된 전체 회귀** JSON 정보.

    파일명만 보지 않고 TC ID 표식을 대조한다. 개별 실행과 전제 실패 조기 종료도
    같은 ``Result_*.json`` 이름을 쓰기 때문이다.
    """
    candidates = sorted(
        glob.glob(os.path.join(reports_dir, "Result_*.json")),
        key=os.path.getmtime, reverse=True)
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            continue
        stamp = _report_time(data, path)
        if since is not None and stamp < since:
            continue
        if not _is_full_regression(data):
            continue
        results = data.get("results", [])
        verdicts = {}
        for row in results:
            verdict = row.get("verdict") or "UNKNOWN"
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
        return {"path": path, "generated": data.get("generated"),
                "timestamp": stamp, "tc_count": len(results),
                "verdicts": verdicts}
    return None


def regression_age(reports_dir, max_age_days=7, now=None):
    """마지막 완료 전체 회귀의 경과일과 상태(``ok/stale/missing``)."""
    latest = latest_full_regression(reports_dir)
    if latest is None:
        return {"status": "missing", "max_age_days": max_age_days,
                "message": "완료된 전체 회귀 리포트를 찾지 못했습니다."}
    current = now.timestamp() if hasattr(now, "timestamp") else (
        float(now) if now is not None else datetime.now().timestamp())
    age_days = max(0.0, (current - latest["timestamp"]) / 86400.0)
    status = "stale" if age_days > float(max_age_days) else "ok"
    return {"status": status, "age_days": round(age_days, 2),
            "max_age_days": max_age_days, "latest": latest,
            "message": ("마지막 완료 전체 회귀가 %.1f일 전입니다." % age_days)}


def notify_windows(title, message, level="info", timeout_seconds=8):
    """Windows 알림 영역에 풍선 알림을 비동기로 표시한다.

    외부 패키지나 계정 연동이 없다. 실패해도 회귀를 깨지 않고 ``False``를
    반환한다. 단위 시험은 ``BELLALUN_DISABLE_NOTIFICATIONS=1``로 비활성화한다.
    """
    if os.environ.get("BELLALUN_DISABLE_NOTIFICATIONS") == "1":
        return False
    if os.name != "nt":
        return False
    icon = "Error" if level == "error" else (
        "Warning" if level == "warning" else "Info")
    # NotifyIcon의 제목/본문 길이 제한을 넘기지 않는다.
    safe_title = str(title).replace("'", "''")[:63]
    safe_message = str(message).replace("'", "''")[:240]
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information;"
        "$n.Visible=$true;"
        "$n.BalloonTipIcon=[System.Windows.Forms.ToolTipIcon]::%s;"
        "$n.BalloonTipTitle='%s';$n.BalloonTipText='%s';"
        "$n.ShowBalloonTip(%d);Start-Sleep -Seconds %d;$n.Dispose()"
        % (icon, safe_title, safe_message, int(timeout_seconds * 1000),
           max(2, int(timeout_seconds))))
    encoded = __import__("base64").b64encode(
        script.encode("utf-16-le")).decode("ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-EncodedCommand", encoded],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=flags)
        return True
    except OSError:
        return False


def process_exit_message(process_name, started):
    dumps = find_crash_dumps(process_name, since=started)
    if dumps:
        return {"kind": "crash", "dumps": dumps,
                "message": "WER 크래시 덤프 확인: %s" % dumps[-1]}
    return {"kind": "disappeared", "dumps": [],
            "message": "프로세스가 사라졌지만 새 WER 덤프는 없습니다."}
