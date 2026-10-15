"""Prepare only the automation-owned USB export directory.

Drive discovery/removable-drive validation belongs to the caller. This module
accepts an absolute Windows drive-letter root, then permits only its immediate
BellalunWU09 child. No shell or recursive deletion command is used. The entire
existing tree is checked before any deletion, and each planned removal is
checked again immediately before unlink/rmdir. Errors are never ignored.
"""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import re
import stat

EXPORT_FOLDER = 'BellalunWU09'


def validate_drive_root(drive):
    """Pure lexical validation; does not inspect or write a real drive."""
    if not isinstance(drive, (str, os.PathLike)):
        raise ValueError('USB 드라이브는 절대 드라이브 루트여야 합니다.')
    value = os.fspath(drive)
    if not isinstance(value, str):
        raise ValueError('USB 드라이브 경로는 문자열이어야 합니다.')
    windows = PureWindowsPath(value)
    if (not windows.is_absolute() or not re.fullmatch('[a-zA-Z]:', windows.drive)
            or len(windows.parts) != 1 or value not in {windows.drive + '\\', windows.drive + '/'}):
        raise ValueError('E:\\ 형태의 절대 USB 드라이브 루트만 허용합니다.')
    return Path(value)


def _no_reparse_path(path):
    """lstat all existing ancestors before resolving or descending into them."""
    for candidate in reversed((path, *path.parents)):
        try:
            details = candidate.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(details.st_mode)
                or getattr(details, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f'USB 정리 경로의 링크/정션/재분석 지점 금지: {candidate}')


def _in_owned_folder(path, root, target):
    _no_reparse_path(path)
    _no_reparse_path(root)
    _no_reparse_path(target)
    if root.resolve(strict=True) != root or target.resolve(strict=False).parent != root:
        raise ValueError('USB 자동화 폴더가 검증한 드라이브 루트 밖으로 벗어났습니다.')
    resolved = path.resolve(strict=False)
    if target.name != EXPORT_FOLDER or not resolved.is_relative_to(target):
        raise ValueError('USB 자동화 전용 폴더 밖의 삭제 대상은 금지합니다.')


def _prepare_owned_folder(root, folder=EXPORT_FOLDER):
    """Shared guarded implementation; tests supply a temporary root fixture.

    The public entry point performs drive-root validation. This separate layer
    makes normal cleanup and reparse rejection testable without real USB writes.
    """
    if folder != EXPORT_FOLDER:
        raise ValueError('자동화 소유 단일 폴더 BellalunWU09만 정리할 수 있습니다.')
    root = Path(root)
    if not root.is_absolute():
        raise ValueError('정리 루트는 절대 경로여야 합니다.')
    _no_reparse_path(root)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('정리 루트가 디렉터리가 아닙니다.')
    target = root / folder
    _in_owned_folder(target, root, target)
    if not target.exists():
        target.mkdir()
        return str(target), []
    if not target.is_dir():
        raise ValueError('USB 자동화 전용 경로가 디렉터리가 아닙니다.')

    # Full preflight: nothing is removed until every existing entry is checked.
    files, directories, pending = [], [], [target]
    while pending:
        directory = pending.pop()
        _in_owned_folder(directory, root, target)
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                _in_owned_folder(path, root, target)
                details = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(details.st_mode):
                    directories.append(path)
                    pending.append(path)
                elif stat.S_ISREG(details.st_mode):
                    files.append(path)
                else:
                    raise ValueError(f'USB 폴더의 일반 파일/디렉터리가 아닌 항목 금지: {path}')

    cleared = sorted(str(path.resolve(strict=True)) for path in files)
    for path in sorted(files):
        _in_owned_folder(path, root, target)
        path.unlink()
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _in_owned_folder(path, root, target)
        path.rmdir()
    _in_owned_folder(target, root, target)
    return str(target), cleared


def prepare_export_folder(drive, folder=EXPORT_FOLDER):
    """Return (absolute target string, cleared file paths), or propagate errors."""
    return _prepare_owned_folder(validate_drive_root(drive), folder)
