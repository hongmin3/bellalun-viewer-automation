# -*- coding: utf-8 -*-
"""회귀 테스트 전 BELLALUN DB를 알려진 기준 상태로 되돌리는 백업/복원.

`core/db.py`의 조회 전용 원칙과 별개로, 이 모듈은 사용자가 명시적으로 승인한
초기화 목적의 BACKUP/RESTORE만 제공한다(DELETE/UPDATE는 여전히 제공하지 않는다).
기준 백업은 "진짜 클린 설치" 상태가 아니라, 사용자가 승인한 시점(예: 첫 baseline
스냅샷 생성 시)의 DATA/ACCOUNT/CONFIGURATION/PROCEDURE 상태다.

기준 스냅샷 위치 (2026-08-18 사용자 확정):
  운영자가 `.bak` 4개를 **저장소 상위 폴더의 `Baseline\\`**(즉
  `<...>\\Bellalun Viewer\\Baseline`)에 넣어 두고, 그 폴더가 PC마다 다른
  드라이브/사용자 경로에 있어도 자동화가 스스로 찾아야 한다. 그래서 절대경로를
  하드코딩하지 않고 `config.json` 위치(`ctx.root`) 기준 상대경로로 탐색한다.

**왜 그대로 RESTORE하지 않고 복사하는가 (실측 근거)**
  SQL Server는 `.bak`을 자동화 실행 계정이 아니라 **자기 서비스 계정**으로 읽는다.
  이 PC의 `SQL Server (BELLALUN)`은 `NT AUTHORITY\\LOCALSERVICE`로 실행되어
  사용자 프로필/OneDrive 아래를 읽을 수 없다. 실제로 원본 경로를 그대로 주면
  `Cannot open backup device ... Operating system error 5(액세스가 거부되었습니다)`로
  실패한다(2026-08-18 실측). 게다가 OneDrive 폴더는 파일이 클라우드 전용
  placeholder일 수 있어 서비스 계정이 실체를 못 볼 위험도 있다.
  따라서 복원 직전에 `<data_dir>\\Backup\\Baseline`(앱 데이터 루트, 서비스 계정이
  읽을 수 있는 위치)로 복사한 뒤 그 사본에서 RESTORE한다.
"""

import os
import shutil
import subprocess

DATABASES = ["DATA", "ACCOUNT", "CONFIGURATION", "PROCEDURE"]

# BELLALUN Viewer/Bunny 관련 프로세스. DB 단독 접속을 위해 restore 전 종료한다.
APP_PROCESSES = ["VIEWER", "Bunny", "BellalunService", "SERVICE.DELEGATOR",
                  "SystemLauncher", "ImageExtractor", "UPSHandler"]


def _bracket(name):
    return f"[{name}]"


def source_dir(ctx):
    """운영자가 기준 `.bak`을 두는 폴더를 찾는다(PC 독립).

    `config.json`이 있는 `auto` 폴더를 기준으로 위로 올라가며 `Baseline`
    폴더를 찾는다. 저장소를 어느 PC 어느 드라이브에 클론해도 동작한다.
    `config.json > baseline_dir`로 명시하면 그 값을 최우선으로 쓴다.
    """
    override = (ctx.cfg.get("baseline_dir") or "").strip()
    if override:
        return override
    here = os.path.abspath(ctx.root)
    for _ in range(4):                      # auto -> Bellalun Viewer -> 자동화 ...
        here = os.path.dirname(here)
        if not here:
            break
        candidate = os.path.join(here, "Baseline")
        if os.path.isdir(candidate):
            return candidate
    # 못 찾으면 상위 폴더의 Baseline을 기대 경로로 돌려준다(오류 메시지에 사용).
    return os.path.join(os.path.dirname(os.path.abspath(ctx.root)), "Baseline")


def staging_dir(ctx):
    """SQL Server 서비스 계정이 읽을 수 있는 복원용 사본 폴더."""
    d = os.path.join(ctx.cfg.get("data_dir", r"D:\BellalunData"), "Backup", "Baseline")
    os.makedirs(d, exist_ok=True)
    return d


# 이전 이름 호환(백업 생성 시 저장 위치).
backup_dir = staging_dir


def stop_app_processes():
    for name in APP_PROCESSES:
        subprocess.run(
            ["taskkill", "/IM", f"{name}.exe", "/F", "/T"],
            capture_output=True)


def backup_baseline(ctx):
    """현재 4개 DB를 기준 스냅샷(.bak)으로 저장한다.

    SQL Server가 직접 쓸 수 있는 staging 폴더에 백업한 뒤, 운영자가 관리하는
    `Baseline` 폴더로도 복사해 둔다(그 폴더가 PC 이관/공유의 기준이다).
    """
    staging = staging_dir(ctx)
    stop_app_processes()
    saved = {}
    for db in DATABASES:
        path = os.path.join(staging, f"{db}.bak")
        sql = (f"BACKUP DATABASE {_bracket(db)} TO DISK = N'{path}' "
               f"WITH INIT, FORMAT, STATS=10")
        ctx.db.query("master", sql)
        saved[db] = path

    target = source_dir(ctx)
    try:
        os.makedirs(target, exist_ok=True)
        for db in DATABASES:
            shutil.copy2(saved[db], os.path.join(target, f"{db}.bak"))
        saved["_copied_to"] = target
    except OSError as exc:
        # 백업 자체는 성공했으므로 복사 실패로 전체를 실패시키지 않는다.
        saved["_copy_error"] = f"{target}: {exc}"
    return saved


def _present(directory):
    return [db for db in DATABASES
            if os.path.exists(os.path.join(directory, f"{db}.bak"))]


def has_baseline(ctx):
    """운영자 `Baseline` 폴더 또는 staging 사본에 4개 `.bak`이 모두 있는가."""
    return (len(_present(source_dir(ctx))) == len(DATABASES) or
            len(_present(staging_dir(ctx))) == len(DATABASES))


def baseline_state(ctx):
    """리포트에 남길 기준 스냅샷 탐색 결과."""
    src, stg = source_dir(ctx), staging_dir(ctx)
    return {"baseline_dir": src, "baseline_found": _present(src),
            "staging_dir": stg, "staging_found": _present(stg)}


def _quote(value):
    return str(value).replace("'", "''")


def _move_clauses(ctx, db, bak_path):
    r"""`.bak`의 논리 파일을 **이 PC의 실제 경로**로 옮기는 WITH MOVE 절.

    `.bak`에는 백업을 뜬 PC의 물리 경로가 그대로 박혀 있다(실측: 기준 스냅샷은
    `D:\BellalunData\Database\DATA.mdf`, 복원 대상 PC는
    `C:\BellalunData\Database\DATA.mdf`). 그대로 RESTORE하면
    `Directory lookup for the file ... operating system error 3(경로를 찾을 수
    없음)`으로 실패한다. QA PC마다 BellalunData 드라이브가 다르므로
    (`run.py::_resolve_data_dir` 참고) 경로를 하드코딩하지 않고,
    현재 DB가 쓰는 물리 경로(`sys.master_files`)로 매핑한다.

    현재 DB가 없어 매핑할 대상이 없으면(신규 PC) `<data_dir>\Database`에
    논리 파일명 기준으로 배치한다.
    """
    listing = ctx.db.query("master", f"RESTORE FILELISTONLY FROM DISK = N'{_quote(bak_path)}'")
    current = {row["name"]: row["physical_name"] for row in ctx.db.query(
        "master",
        "SELECT name, physical_name FROM sys.master_files "
        f"WHERE DB_NAME(database_id) = N'{_quote(db)}'")}
    fallback_dir = os.path.join(ctx.cfg.get("data_dir", r"D:\BellalunData"), "Database")
    clauses = []
    for row in listing:
        logical = row.get("LogicalName")
        if not logical:
            continue
        target = current.get(logical)
        if not target:
            suffix = ".ldf" if str(row.get("Type", "")).upper() == "L" else ".mdf"
            target = os.path.join(fallback_dir, f"{logical}{suffix}")
        clauses.append(f"MOVE N'{_quote(logical)}' TO N'{_quote(target)}'")
    return clauses


def restore_baseline(ctx):
    """기준 스냅샷으로 4개 DB를 되돌린다.

    운영자 `Baseline` 폴더의 `.bak`을 staging 폴더로 복사한 뒤 복원한다
    (모듈 docstring의 서비스 계정 권한 문제 참고). `Baseline` 폴더가 없고
    staging 사본만 있으면 그 사본으로 복원한다.
    """
    src, stg = source_dir(ctx), staging_dir(ctx)
    if len(_present(src)) == len(DATABASES):
        for db in DATABASES:
            shutil.copy2(os.path.join(src, f"{db}.bak"),
                         os.path.join(stg, f"{db}.bak"))
    elif len(_present(stg)) != len(DATABASES):
        raise FileNotFoundError(
            f"기준 스냅샷(.bak 4개)을 찾지 못했습니다. "
            f"{DATABASES} 를 '{src}' 에 두거나 "
            f"`python run.py snapshot-baseline`으로 먼저 생성하세요. "
            f"현재 상태={baseline_state(ctx)}")

    stop_app_processes()
    moved = {}
    for db in DATABASES:
        path = os.path.join(stg, f"{db}.bak")
        b = _bracket(db)
        move = _move_clauses(ctx, db, path)
        moved[db] = move
        restore = (f"RESTORE DATABASE {b} FROM DISK = N'{path}' WITH REPLACE"
                   + ("".join(f", {m}" for m in move) if move else ""))
        ctx.db.query("master", f"ALTER DATABASE {b} SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        try:
            ctx.db.query("master", restore)
        finally:
            # 복원이 실패해도 SINGLE_USER로 방치하면 Viewer가 아예 접속하지 못한다.
            ctx.db.query("master", f"ALTER DATABASE {b} SET MULTI_USER")
    return {"restored": DATABASES, "from": stg, "source": src, "moved": moved}
