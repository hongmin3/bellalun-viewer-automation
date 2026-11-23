# -*- coding: utf-8 -*-
"""설치 폴더 권한과 이전 데이터 옮기기 (frame/FRAME.md 2.5, REQ-FRAME-003). Bellalun·VXvue 공용.

설치 폴더(`C:\\BellalunAuto`, `C:\\VXvueAuto`)는 `C:\\` 바로 아래에 있어 기본으로 "인증된 사용자 수정"
권한을 물려받는다. 관리자 권한으로 도는 자동화의 실행 파일·DLL을 일반 사용자가 바꾸지 못하도록
상속을 끊고 관리자·SYSTEM만 쓰게 한다. 사용자가 써야 하는 데이터 폴더만 따로 수정 권한을 준다.

두 함수 모두 설치 직후 관리자 권한의 설치 준비(`prepare-install`)에서 부른다.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

ADMINISTRATORS = '*S-1-5-32-544'
SYSTEM = '*S-1-5-18'
USERS = '*S-1-5-32-545'
SETTINGS_FILE = Path('Settings') / 'config.json'


def harden_commands(app_dir, writable=()):
    """실행할 icacls 명령 목록. 계정 이름 대신 SID를 써서 한국어·영어 Windows에서 같게 동작한다."""
    app = Path(app_dir)
    commands = [['icacls', str(app), '/inheritance:r', '/grant:r',
                 ADMINISTRATORS + ':(OI)(CI)F', SYSTEM + ':(OI)(CI)F', USERS + ':(OI)(CI)RX']]
    for name in writable:
        commands.append(['icacls', str(app / name), '/grant', USERS + ':(OI)(CI)M'])
    return commands


def harden(app_dir, writable=(), runner=subprocess.run):
    """설치 폴더를 관리자만 쓰게 하고 `writable` 데이터 폴더만 사용자 수정 권한을 준다. 실패하면 OSError."""
    app = Path(app_dir)
    if not app.is_dir():
        raise OSError(f'설치 폴더가 없습니다: {app}')
    for name in writable:
        (app / name).mkdir(parents=True, exist_ok=True)
    for command in harden_commands(app, writable):
        proc = runner(command, stdin=subprocess.DEVNULL, capture_output=True,
                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if proc.returncode != 0:
            detail = (proc.stdout or b'') + (proc.stderr or b'')
            if isinstance(detail, bytes):
                detail = detail.decode('utf-8', 'replace')
            raise OSError(f'권한을 바꾸지 못했습니다(종료 {proc.returncode}): {" ".join(command)} {detail.strip()[:200]}')


def migrate(legacy_dir, app_dir, settings_name='config.json'):
    """이전 데이터 폴더의 내용을 새 설치 폴더로 복사한다. 이미 있는 파일은 덮어쓰지 않는다.

    `legacy_dir/config.json`은 `app_dir/Settings/config.json`으로, 나머지는 같은 이름의 하위 폴더로 간다.
    이전 폴더는 지우지 않는다. 결과: {'copied': 파일 수, 'kept': 이미 있어 건너뛴 파일 수, 'source': 경로 또는 None}
    """
    legacy, app = Path(legacy_dir), Path(app_dir)
    result = {'copied': 0, 'kept': 0, 'source': None}
    if not legacy.is_dir():
        return result
    try:
        if legacy.resolve() == app.resolve() or app.resolve().is_relative_to(legacy.resolve()):
            return result
    except OSError:
        return result
    result['source'] = str(legacy)
    for source in sorted(legacy.rglob('*')):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(legacy)
        target = app / SETTINGS_FILE if relative == Path(settings_name) else app / relative
        if target.exists():
            result['kept'] += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        result['copied'] += 1
    return result


def legacy_program_files(product_folder, data_folder):
    """예전 설치판의 데이터 폴더 후보(Program Files 아래). 있는 것만 돌려준다."""
    roots = {os.environ.get('ProgramW6432'), os.environ.get('ProgramFiles')} - {None, ''}
    return [path for path in (Path(root) / product_folder / data_folder for root in sorted(roots)) if path.is_dir()]
