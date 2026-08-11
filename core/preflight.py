# -*- coding: utf-8 -*-
"""자동화 수행 전 환경 점검.

자동화가 실패했을 때 "제품 결함"인지 "시험 환경 문제"인지 구분하지 못하면
QA 결과를 신뢰할 수 없다. 매 실행 전에 전제 조건을 먼저 확인하고,
충족되지 않으면 TC를 수행하지 않는다(오판정 방지).
"""

import os

from core import sysinfo

# XIPL.SERVER는 영상 처리 담당. 죽어 있거나 응답하지 않으면 촬영 영상의
# 영상 처리가 정상 수행되지 않아 촬영 계열 TC가 잘못된 결과를 낸다.
XIPL_PROCESS = "XIPL.SERVER"
XIPL_KEEPALIVE = "XIPL.KEEPALIVE"
XIPL_PORT = 9784


def _listening_ports():
    out = sysinfo._ps(
        "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
        "ForEach-Object { \"$($_.LocalPort):$($_.OwningProcess)\" }")
    ports = {}
    for line in out.splitlines():
        if ":" in line:
            p, pid = line.strip().split(":", 1)
            if p.isdigit():
                ports[int(p)] = pid
    return ports


def check_xipl():
    """XIPL.SERVER 가동 여부.

    프로세스 존재 + 서비스 포트(9784) LISTEN 두 가지를 모두 본다.
    프로세스만 떠 있고 포트를 못 여는 경우가 실제로 있어서 한쪽만으로는 부족하다.
    """
    procs = sysinfo.process_names()
    running = XIPL_PROCESS in procs
    keepalive = XIPL_KEEPALIVE in procs
    listening = XIPL_PORT in _listening_ports()
    return {
        "ok": running and listening,
        "process": running,
        "keepalive": keepalive,
        "port_listening": listening,
        "port": XIPL_PORT,
        "detail": ("정상" if running and listening else
                   "XIPL.SERVER 미기동" if not running else
                   f"XIPL.SERVER는 떠 있으나 포트 {XIPL_PORT} 미개방"),
    }


def check_all(cfg, db, require_viewer=False):
    """전체 전제 조건 점검. (ok, 항목리스트) 반환."""
    items = []

    x = check_xipl()
    items.append({"name": "XIPL.SERVER 가동", "ok": x["ok"], "detail": x["detail"],
                  "blocking": True})

    items.append({"name": "관리자 권한", "ok": sysinfo.is_elevated(),
                  "detail": "UI 조작에는 관리자 권한 필수 (UIPI)",
                  "blocking": True})

    svc = sysinfo.service_state(cfg.get("sql_service_name", "MSSQL$BELLALUN"))
    items.append({"name": "SQL Server(BELLALUN) 서비스",
                  "ok": bool(svc) and svc["status"] == "Running",
                  "detail": svc["status"] if svc else "서비스 없음",
                  "blocking": True})

    items.append({"name": "BELLALUN DB 접속", "ok": db.ping(),
                  "detail": cfg.get("sql_server"), "blocking": True})

    inst = cfg.get("install_dir", "")
    items.append({"name": "설치 경로", "ok": os.path.isdir(inst),
                  "detail": inst, "blocking": False})

    if require_viewer:
        running = "VIEWER" in sysinfo.process_names()
        items.append({"name": "Viewer 기동", "ok": running,
                      "detail": "미기동 시 러너가 실행", "blocking": False})

    ok = all(i["ok"] for i in items if i["blocking"])
    return ok, items


def report(items):
    lines = []
    for i in items:
        mark = "OK  " if i["ok"] else ("FAIL" if i["blocking"] else "WARN")
        lines.append(f"  [{mark}] {i['name']}: {i['detail']}")
    return "\n".join(lines)
