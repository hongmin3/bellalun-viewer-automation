"""생성물을 새 목적지에 보관하고 검증한다. 원본 이동·삭제는 하지 않는다."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import zipfile

from core.run_preservation import PreservationError, _check_path, _copy_tree, _hash, _write_json, snapshot


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _archive_path(path):
    path = _check_path(path)
    if any(part.casefold() == '.git' for part in path.parts):
        raise PreservationError('.git 자체 또는 그 안의 경로는 보관 대상으로 사용할 수 없습니다.')
    return path


def _reject_git(root):
    _archive_path(root)
    for directory, folders, files in os.walk(root, followlinks=False):
        _check_path(directory)
        for name in folders + files:
            _check_path(Path(directory) / name)
            if name.casefold() == '.git':
                raise PreservationError('Git 이력이 있는 .git 범위는 보관 도구에 넣을 수 없습니다.')


def _capacity_parent(destination):
    current = destination.parent
    while not current.exists():
        current = current.parent
    _check_path(current)
    if not current.is_dir():
        raise PreservationError('보관 목적지의 상위 경로가 폴더가 아닙니다.')
    return current


def inspect_archive(source, destination, *, compress=False):
    """정확한 목록·해시·현재 용량을 읽어 계획한다. 폴더나 파일을 만들지 않는다."""
    source, destination = _archive_path(source), _archive_path(destination)
    if (source == destination or source in destination.parents or destination in source.parents):
        raise PreservationError('원본과 보관 목적지가 겹칩니다.')
    if destination.exists():
        raise PreservationError('기존 목적지는 덮어쓰거나 재사용하지 않습니다. 새 폴더를 선택하세요.')
    if not source.is_dir():
        raise PreservationError('존재하는 원본 폴더를 선택하세요.')
    _reject_git(source)
    inventory = snapshot(source)
    total = sum(row['size'] for row in inventory['files'].values())
    manifest = {'schema': 1, 'source': str(source), 'mode': 'zip' if compress else 'copy',
                'source_bytes': total, 'snapshot': inventory}
    names = list(inventory['directories']) + list(inventory['files'])
    # 실제 원본 크기와 파일명/목록에서 계산한다. ZIP의 최악 확장·헤더·ZIP64를
    # 보수적으로 예약하며 압축률을 추정해 공간 부족을 통과시키지 않는다.
    overhead = (sum(2 * len(name.encode('utf-8')) + 512 for name in names)
                + (total // 16383 + 1) * 5) if compress else 0
    required = total + overhead + len(_encoded(manifest)) * 2 + 65536
    free = shutil.disk_usage(_capacity_parent(destination)).free
    if free < required:
        raise PreservationError('보관 목적지의 여유 공간이 실제 파일과 검증 기록의 예약량보다 부족합니다.')
    return {'state': 'planned', 'source': str(source), 'destination': str(destination),
            'mode': manifest['mode'], 'source_bytes': total, 'required_bytes': required,
            'available_bytes': free, 'manifest': manifest}


def _validate_inventory(inventory):
    if (not isinstance(inventory, dict) or inventory.get('exists') is not True
            or not isinstance(inventory.get('directories'), list)
            or not isinstance(inventory.get('files'), dict)):
        raise PreservationError('보관 manifest의 파일 목록 형식이 올바르지 않습니다.')
    names = inventory['directories'] + list(inventory['files'])
    if len(names) != len(set(names)):
        raise PreservationError('보관 manifest에 중복 경로가 있습니다.')
    for name in names:
        if (not isinstance(name, str) or not name or '\\' in name
                or PurePosixPath(name).is_absolute() or ':' in name
                or any(part in {'', '.', '..'} for part in name.split('/'))
                or any(part.casefold() == '.git' for part in name.split('/'))):
            raise PreservationError('보관 manifest에 안전하지 않은 상대 경로가 있습니다.')
    for row in inventory['files'].values():
        if (not isinstance(row, dict) or type(row.get('size')) is not int or row['size'] < 0
                or not re.fullmatch('[a-f0-9]{64}', str(row.get('sha256', '')))):
            raise PreservationError('보관 manifest의 크기 또는 해시가 올바르지 않습니다.')


def _zip_inventory(path, expected):
    """추출하지 않고 ZIP의 정확한 구성·원문 크기·원문 SHA-256을 확인한다."""
    _check_path(path)
    names = {name + '/' for name in expected['directories']} | set(expected['files'])
    actual = {'exists': True, 'directories': [], 'files': {}}
    with zipfile.ZipFile(path, 'r') as archive:
        members = archive.infolist()
        if len(members) != len(names) or {member.filename for member in members} != names:
            raise PreservationError('ZIP 파일 목록이 manifest와 다릅니다.')
        for member in members:
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode) or member.external_attr & 0x400:
                raise PreservationError('ZIP에 링크 항목이 있습니다.')
            if member.is_dir():
                actual['directories'].append(member.filename[:-1])
                continue
            target = expected['files'][member.filename]
            if member.file_size != target['size'] or member.flag_bits & 1:
                raise PreservationError('ZIP의 원문 크기가 다르거나 암호화된 항목입니다.')
            digest = hashlib.sha256()
            count = 0
            with archive.open(member) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    count += len(block)
                    if count > target['size']:
                        raise PreservationError('ZIP 항목이 계획한 원문 크기를 넘습니다.')
                    digest.update(block)
            actual['files'][member.filename] = {'size': count, 'sha256': digest.hexdigest()}
    actual['directories'].sort()
    return actual


def _verify_payload(destination, manifest):
    expected = manifest['snapshot']
    _validate_inventory(expected)
    if manifest['mode'] == 'copy':
        if snapshot(destination / 'content') != expected:
            raise PreservationError('보관 사본의 목록 또는 SHA-256이 manifest와 다릅니다.')
        return {'snapshot_sha256': hashlib.sha256(_encoded(expected)).hexdigest()}
    if manifest['mode'] != 'zip':
        raise PreservationError('보관 형식을 확인할 수 없습니다.')
    path = _check_path(destination / 'archive.zip')
    if _zip_inventory(path, expected) != expected:
        raise PreservationError('ZIP 원문의 목록 또는 SHA-256이 manifest와 다릅니다.')
    return {'sha256': _hash(path), 'size': path.stat().st_size}


def verify_archive(destination):
    """보관본과 영수증을 다시 읽어 검증한다. 원본 폴더는 읽거나 변경하지 않는다."""
    destination = _archive_path(destination)
    try:
        manifest_path = _check_path(destination / 'manifest.json')
        receipt_path = _check_path(destination / 'receipt.json')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if (manifest.get('schema') != 1 or receipt.get('state') != 'complete'
                or receipt.get('manifest_sha256') != _hash(manifest_path)):
            raise PreservationError('보관 완료 영수증 또는 manifest 해시가 일치하지 않습니다.')
        payload = _verify_payload(destination, manifest)
        if receipt.get('payload') != payload:
            raise PreservationError('보관본 해시가 완료 영수증과 다릅니다.')
        allowed = {'manifest.json', 'receipt.json', 'archive.zip' if manifest['mode'] == 'zip' else 'content'}
        if {path.name for path in destination.iterdir()} != allowed:
            raise PreservationError('선택한 보관 폴더에 manifest 밖의 항목이 있습니다.')
        return {'state': 'verified', 'destination': str(destination), 'mode': manifest['mode'],
                'source_bytes': manifest['source_bytes'], 'payload': payload}
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        raise PreservationError('보관본 또는 검증 기록을 읽거나 검증하지 못했습니다.') from error


def archive_artifacts(source, destination, *, compress=False, apply=False):
    """기본은 무기록 계획. apply=True일 때 새 목적지로 복사/ZIP 후 읽어 검증한다."""
    plan = inspect_archive(source, destination, compress=compress)
    if not apply:
        return plan
    source, destination = _check_path(plan['source']), _check_path(plan['destination'])
    destination.mkdir(parents=True, exist_ok=False)
    manifest_path, receipt_path = destination / 'manifest.json', destination / 'receipt.json'
    manifest = plan['manifest']
    try:
        _write_json(manifest_path, manifest)
        _write_json(receipt_path, {'state': 'copying', 'mode': manifest['mode']})
        if compress:
            with zipfile.ZipFile(destination / 'archive.zip', 'x', compression=zipfile.ZIP_DEFLATED,
                                 allowZip64=True, strict_timestamps=False) as archive:
                for name in manifest['snapshot']['directories']:
                    _check_path(source / name)
                    archive.write(source / name, arcname=name + '/')
                for name in manifest['snapshot']['files']:
                    _check_path(source / name)
                    archive.write(source / name, arcname=name)
            with (destination / 'archive.zip').open('r+b') as stored:
                os.fsync(stored.fileno())
        else:
            _copy_tree(source, destination / 'content', manifest['snapshot'])
        payload = _verify_payload(destination, manifest)
        _reject_git(source)
        if snapshot(source) != manifest['snapshot']:
            raise PreservationError('보관 도중 원본이 변경되어 성공으로 처리할 수 없습니다.')
        receipt = {'schema': 1, 'state': 'complete', 'mode': manifest['mode'],
                   'manifest_sha256': _hash(manifest_path), 'payload': payload,
                   'source_bytes': plan['source_bytes']}
        _write_json(receipt_path, receipt)
        verify_archive(destination)
        return dict(receipt, destination=str(destination), receipt=str(receipt_path))
    except Exception as error:
        # 부분 사본도 자동 삭제하지 않는다. 실패 상태를 남기고 원본은 보존한다.
        try:
            _write_json(receipt_path, {'state': 'error', 'error_type': type(error).__name__})
        except OSError:
            pass
        if isinstance(error, PreservationError):
            raise
        raise PreservationError('보관에 실패했습니다. 원본과 부분 사본은 보존합니다.') from error
