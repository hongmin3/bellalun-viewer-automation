"""디스크/메모리 조회와 보수적 실행 예산. 조회 실패·미확정은 실행을 차단한다."""
from __future__ import annotations

import os
import ntpath
from pathlib import Path
import shutil
import stat

from core.run_preservation import _check_path

GIB = 1024 ** 3
MIB = 1024 ** 2


def tree_usage(root):
    """용량 gate는 내용 해시 없이 크기만 센다. 실제 사본 단계에서 해시를 검증한다."""
    root = _check_path(root)
    if not root.exists():
        return 0, 0
    if not root.is_dir():
        raise ValueError('보존 범위는 폴더여야 합니다')
    total, largest = 0, 0
    with os.scandir(root) as entries:
        for entry in entries:
            path = _check_path(entry.path)
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                subtotal, maximum = tree_usage(path)
                total += subtotal
                largest = max(largest, maximum)
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
                largest = max(largest, info.st_size)
            else:
                raise ValueError('일반 파일이 아닌 보존 항목입니다')
    return total, largest


def tree_size(root):
    return tree_usage(root)[0]


def _unc_share(path):
    value = os.fspath(path).replace('/', '\\')
    if value.casefold().startswith('\\\\?\\unc\\'):
        value = '\\\\' + value[8:]
    if value.startswith('\\\\') and not value.startswith('\\\\?\\'):
        parts = value[2:].split('\\')
        if len(parts) >= 2 and all(parts[:2]):
            return '\\\\' + '\\'.join(parts[:2])
    return None


def volume_info(path):
    """볼륨 GUID(Windows) 또는 st_dev로 같은 파일 시스템의 예약량을 합산한다."""
    share = _unc_share(path) if os.name == 'nt' else None
    if share:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        available, total, free = (ctypes.c_ulonglong() for _ in range(3))
        get_free = kernel.GetDiskFreeSpaceExW
        get_free.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong),
                             ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong)]
        get_free.restype = wintypes.BOOL
        # A share has no local volume GUID. Query quota-aware available bytes directly.
        if not get_free(share + '\\', ctypes.byref(available), ctypes.byref(total), ctypes.byref(free)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'id': 'unc:' + share.casefold(), 'free': available.value}
    path = _check_path(path)
    while not path.exists():
        if path == path.parent:
            raise OSError("볼륨을 찾지 못했습니다")
        path = path.parent
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        volume_path = ctypes.create_unicode_buffer(32768)
        get_path = kernel.GetVolumePathNameW
        get_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        get_path.restype = wintypes.BOOL
        if not get_path(str(path), volume_path, len(volume_path)):
            raise ctypes.WinError(ctypes.get_last_error())
        volume_name = ctypes.create_unicode_buffer(32768)
        get_name = kernel.GetVolumeNameForVolumeMountPointW
        get_name.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        get_name.restype = wintypes.BOOL
        if not get_name(volume_path.value, volume_name, len(volume_name)):
            raise ctypes.WinError(ctypes.get_last_error())
        identity = volume_name.value
    else:
        identity = str(path.stat().st_dev)
    return {"id": identity, "free": shutil.disk_usage(path).free}


def plan_resources(roots, backup_dir, generation_reserves, product_headroom_bytes,
                   *, volume_probe=None, memory_available_bytes=None,
                   db_backup_bytes=0, archive_reserve_bytes=None, restore_after=False,
                   incremental_restore=False, root_headroom_bytes=None):
    """예약량은 path->bytes, root별 누락은 unknown이다. headroom은 제품 볼륨별 한 번.

    DB 사전 크기는 호출자가 조회해 db_backup_bytes로 전달한다. 기존 로컬 복원은
    원래 파일 전체 재작성량을 예약하고 incremental_restore는 볼륨별 최대 파일만 예약한다.
    공용 모드에서는 복원 선택과 관계없이 시험 후 파일과 DB 보관량을 예약한다.
    archive_reserve_bytes가 None이면 사전 크기+root 생성 예약량을 보관 예상량으로 쓴다.
    메모리는 이미 조회한 available 값을 전달한다(unknown은 BLOCK).
    """
    probe = volume_probe or volume_info
    def path_key(path):
        share = _unc_share(path)
        if share:
            value = os.fspath(path).replace('/', '\\')
            if value.casefold().startswith('\\\\?\\unc\\'):
                value = '\\\\' + value[8:]
            return ntpath.normcase(ntpath.normpath(value))
        return os.path.normcase(os.path.abspath(os.fspath(path)))
    def valid_amount(amount, role):
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ValueError(f"{role} 예상량 미확정")
        return amount
    items, volumes = [], {}
    def item(key, level, actual, expected):
        items.append({"key": key, "label": key, "level": level, "actual": actual,
                      "expected": expected, "blocks_run": level == "BLOCK",
                      "hint": "예산/조회 근거를 확인하고 공간을 확보하세요. 자동 삭제하지 않습니다." if level == "BLOCK" else ""})
    def budget(path, amount, role):
        valid_amount(amount, role)
        data = probe(Path(path))
        if (not data or not data.get("id") or isinstance(data.get("free"), bool)
                or not isinstance(data.get("free"), int) or data["free"] < 0):
            raise ValueError(f"{role} 볼륨 여유 조회 불가")
        volume = volumes.setdefault(str(data["id"]), {"id": str(data["id"]),
                                  "free": data["free"], "required": 0, "allocations": []})
        volume["free"] = min(volume["free"], data["free"])
        volume["required"] += amount
        volume["allocations"].append({"path": str(path), "role": role, "bytes": amount})
        return volume["id"]
    if isinstance(memory_available_bytes, bool) or not isinstance(memory_available_bytes, int) or memory_available_bytes < 0:
        item("memory", "BLOCK", "조회 불가", "2 GiB 이상; 1 GiB 미만 차단")
    else:
        level = "BLOCK" if memory_available_bytes < GIB else "WARN" if memory_available_bytes < 2 * GIB else "OK"
        item("memory", level, memory_available_bytes, 2 * GIB)
    try:
        if not roots:
            raise ValueError("보존 범위 미확정")
        usage = {name: tree_usage(path) for name, path in roots.items()}
        sizes = {name: data[0] for name, data in usage.items()}
        if isinstance(db_backup_bytes, bool) or not isinstance(db_backup_bytes, int) or db_backup_bytes < 0:
            raise ValueError("DB 백업량 미확정")
        budget(backup_dir, sum(sizes.values()) + db_backup_bytes, "backup")
        reserves = {path_key(p): value
                    for p, value in generation_reserves.items()}
        headroom_overrides = {path_key(p): value for p, value in (root_headroom_bytes or {}).items()}
        headrooms, restore_staging = {}, {}
        for name, path in roots.items():
            identity = budget(path, reserves.get(path_key(path)), "generation")
            if restore_after:
                if incremental_restore:
                    current = restore_staging.get(identity, (path, 0))
                    restore_staging[identity] = (path, max(current[1], usage[name][1]))
                else:
                    budget(path, sizes[name], "restore_copy")
            headroom = valid_amount(headroom_overrides.get(path_key(path), product_headroom_bytes), 'product_headroom')
            current = headrooms.get(identity, (path, 0))
            headrooms[identity] = (path, max(current[1], headroom))
        for path, amount in headrooms.values():
            budget(path, amount, 'product_headroom')
        for path, amount in restore_staging.values():
            budget(path, amount, 'restore_copy')
        root_paths = {path_key(path) for path in roots.values()}
        for path, amount in generation_reserves.items():
            if path_key(path) not in root_paths:
                budget(path, amount, "generation")
        if (restore_after or incremental_restore) and archive_reserve_bytes is None:
            archive_reserve_bytes = sum(sizes.values()) + sum(reserves[path] for path in root_paths)
            if incremental_restore:
                archive_reserve_bytes += db_backup_bytes
        if archive_reserve_bytes is not None:
            budget(backup_dir, archive_reserve_bytes, "archive")
    except Exception as exc:
        item("resource_budget", "BLOCK", str(exc), "모든 볼륨의 명시적 예약량과 가용 공간")
    for identity, volume in volumes.items():
        item("disk:" + identity, "OK" if volume["free"] >= volume["required"] else "BLOCK",
             volume["free"], volume["required"])
    return {"items": items, "volumes": list(volumes.values()),
            "blocked": any(i["blocks_run"] for i in items)}
