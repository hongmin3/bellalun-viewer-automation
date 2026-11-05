# -*- coding: utf-8 -*-
"""자동화 수행 전 환경 점검.

자동화가 실패했을 때 "제품 결함"인지 "시험 환경 문제"인지 구분하지 못하면
QA 결과를 신뢰할 수 없다. 매 실행 전에 전제 조건을 먼저 확인하고,
충족되지 않으면 TC를 수행하지 않는다(오판정 방지).
"""

import os
import socket

from core import sysinfo

# XIPL.SERVER는 영상 처리 담당. 죽어 있거나 응답하지 않으면 촬영 영상의
# 영상 처리가 정상 수행되지 않아 촬영 계열 TC가 잘못된 결과를 낸다.
XIPL_PROCESS = "XIPL.SERVER"
XIPL_KEEPALIVE = "XIPL.KEEPALIVE"
XIPL_PORT = 9784


def _process_ids(name):
    out = sysinfo._ps(f"Get-Process -Name '{name}' -ErrorAction SilentlyContinue | "
                      "ForEach-Object { $_.Id }")
    return {line.strip() for line in out.splitlines() if line.strip().isdigit()}


def _listen_sockets(port):
    """port의 수신 모양 소켓 (로컬 주소, 소유 PID) 목록.

    TCP 표의 State 값은 읽지 않는다. 2026-11-05 시험 PC에서 OS가 수신 소켓 상태를
    CLOSED·FIN_WAIT_1이나 정의 밖 값(0)으로 돌려줘 `-State Listen` 조회가 실제
    수신 소켓을 놓쳤고 State 접근 자체가 예외를 냈다. 원격 포트가 0인 행만 수신
    소켓 후보로 보고, 실제로 연결을 받는지는 _accepts가 확인한다.
    """
    out = sysinfo._ps(
        f"Get-NetTCPConnection -LocalPort {int(port)} -ErrorAction SilentlyContinue | "
        "ForEach-Object { \"$($_.LocalAddress)|$($_.RemotePort)|$($_.OwningProcess)\" }")
    sockets = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3 and parts[1] == "0" and parts[2].isdigit():
            sockets.append((parts[0], parts[2]))
    return sockets


def _accepts(address, port):
    host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(address, address)
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def check_xipl():
    """XIPL.SERVER 가동 여부.

    프로세스 존재 + 서비스 포트(9784) 수신 두 가지를 모두 본다.
    프로세스만 떠 있고 포트를 못 여는 경우가 실제로 있어서 한쪽만으로는 부족하다.
    수신은 XIPL.SERVER가 소유한 수신 소켓이 실제 TCP 접속을 받는 것으로 확인한다.
    """
    procs = sysinfo.process_names()
    running = XIPL_PROCESS in procs
    keepalive = XIPL_KEEPALIVE in procs
    listening = False
    if running:
        pids = _process_ids(XIPL_PROCESS)
        owned = [addr for addr, pid in _listen_sockets(XIPL_PORT) if pid in pids]
        # TCP 표에 죽은 행이 섞일 수 있어 XIPL이 가진 수신 소켓을 차례로 본다.
        listening = any(_accepts(addr, XIPL_PORT) for addr in dict.fromkeys(owned))
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


# `requirements.txt`와 짝을 이루는 필수 패키지. 여기만 고치면 안 되고 두 곳을
# 함께 갱신한다.
#
#   Pillow      화면 캡처와 이미지 비교
#   pytesseract 커스텀 컨트롤 값 OCR (Tesseract 실행 파일은 별도 설치)
#   openpyxl    체크리스트 xlsx 읽기/결과 기록
#   pypdf       사양서 PDF에서 판정 근거 검색 (core.specs)
REQUIRED_PACKAGES = {
    "PIL": "Pillow",
    "pytesseract": "pytesseract",
    "openpyxl": "openpyxl",
    "pypdf": "pypdf",
}


def check_packages():
    """필수 패키지 설치 여부. 반환: (ok, 누락 목록, 상세 문자열)."""
    import importlib
    missing = []
    for module, package in sorted(REQUIRED_PACKAGES.items()):
        try:
            importlib.import_module(module)
        except Exception:
            missing.append(package)
    if not missing:
        return True, [], f"{len(REQUIRED_PACKAGES)}개 모두 설치됨"
    return (False, missing,
            f"누락: {', '.join(missing)} — "
            "`python -m pip install -r requirements.txt` 로 설치하십시오")


def check_all(cfg, db, require_viewer=False):
    """전체 전제 조건 점검. (ok, 항목리스트) 반환."""
    items = []

    pkg_ok, missing, pkg_detail = check_packages()
    items.append({"name": "필수 Python 패키지", "ok": pkg_ok,
                  "detail": pkg_detail, "blocking": True})

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
