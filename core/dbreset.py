# -*- coding: utf-8 -*-
"""회귀 테스트 전 BELLALUN DB를 알려진 기준 상태로 되돌리는 백업/복원.

`core/db.py`의 조회 전용 원칙과 별개로, 이 모듈은 사용자가 명시적으로 승인한
초기화 목적의 BACKUP/RESTORE만 제공한다(DELETE/UPDATE는 여전히 제공하지 않는다).
기준 백업은 "진짜 클린 설치" 상태가 아니라, 사용자가 승인한 시점(예: 첫 baseline
스냅샷 생성 시)의 DATA/ACCOUNT/CONFIGURATION/PROCEDURE 상태다.
"""

import os
import subprocess

DATABASES = ["DATA", "ACCOUNT", "CONFIGURATION", "PROCEDURE"]

# BELLALUN Viewer/Bunny 관련 프로세스. DB 단독 접속을 위해 restore 전 종료한다.
APP_PROCESSES = ["VIEWER", "Bunny", "BellalunService", "SERVICE.DELEGATOR",
                  "SystemLauncher", "ImageExtractor", "UPSHandler"]


def _bracket(name):
    return f"[{name}]"


def backup_dir(ctx):
    d = os.path.join(ctx.cfg.get("data_dir", r"D:\BellalunData"), "Backup", "Baseline")
    os.makedirs(d, exist_ok=True)
    return d


def stop_app_processes():
    for name in APP_PROCESSES:
        subprocess.run(
            ["taskkill", "/IM", f"{name}.exe", "/F", "/T"],
            capture_output=True)


def backup_baseline(ctx):
    """현재 4개 DB를 기준 스냅샷(.bak)으로 저장한다. 기존 파일은 덮어쓴다."""
    d = backup_dir(ctx)
    stop_app_processes()
    saved = {}
    for db in DATABASES:
        path = os.path.join(d, f"{db}.bak")
        sql = (f"BACKUP DATABASE {_bracket(db)} TO DISK = N'{path}' "
               f"WITH INIT, FORMAT, STATS=10")
        ctx.db.query("master", sql)
        saved[db] = path
    return saved


def has_baseline(ctx):
    d = backup_dir(ctx)
    return all(os.path.exists(os.path.join(d, f"{db}.bak")) for db in DATABASES)


def restore_baseline(ctx):
    """기준 스냅샷(.bak)으로 4개 DB를 되돌린다. 앱 프로세스는 먼저 종료한다."""
    d = backup_dir(ctx)
    if not has_baseline(ctx):
        raise FileNotFoundError(
            f"기준 백업이 없습니다: {d}. 먼저 backup_baseline()으로 생성하세요.")
    stop_app_processes()
    for db in DATABASES:
        path = os.path.join(d, f"{db}.bak")
        b = _bracket(db)
        ctx.db.query("master", f"ALTER DATABASE {b} SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        ctx.db.query("master", f"RESTORE DATABASE {b} FROM DISK = N'{path}' WITH REPLACE")
        ctx.db.query("master", f"ALTER DATABASE {b} SET MULTI_USER")
