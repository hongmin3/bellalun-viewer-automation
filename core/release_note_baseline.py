"""승인 문서의 명시한 release만 읽는다. 원문·개인 경로를 출력에 복제하지 않는다."""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import re
from zipfile import ZipFile, BadZipFile
import xml.etree.ElementTree as ET

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
VERSION = re.compile(r'\d+(?:\.\d+){2,3}')


class BaselineError(ValueError):
    pass


def extract_baseline(path, release_version, *, install_dir=None, approved=False):
    """여러 판이 들어 있는 DOCX에서 정확히 지정한 버전만 선택한다.

    DB 버전·OS 지원·무인 설치 인자는 module 표에서 추정하지 않는다.
    파일 위치는 실제 설치 폴더의 유일한 이름 일치로만 연결한다.
    """
    if not VERSION.fullmatch(str(release_version)):
        raise BaselineError('명시한 release 버전 형식이 잘못되었습니다')
    path = Path(path)
    try:
        with ZipFile(path) as archive:
            if archive.getinfo('word/document.xml').file_size > 16 * 1024 * 1024:
                raise BaselineError('Release Note XML이 너무 큽니다')
            root = ET.fromstring(archive.read('word/document.xml'))
        document_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError, BadZipFile, ET.ParseError) as error:
        raise BaselineError('Release Note DOCX를 읽을 수 없습니다') from error
    body = root.find('w:body', NS)
    if body is None:
        raise BaselineError('Release Note 본문이 없습니다')
    current = None
    found = False
    files, modules = {}, {}
    for node in body:
        if node.tag == f'{{{NS["w"]}}}p':
            text = _text(node)
            if VERSION.fullmatch(text):
                current = text
                found = found or current == release_version
        elif node.tag == f'{{{NS["w"]}}}tbl' and current == release_version:
            rows = [[_text(cell) for cell in row.findall('w:tc', NS)]
                    for row in node.findall('w:tr', NS)]
            if not rows or len(rows[0]) < 2:
                continue
            header = [re.sub(r'\s+', '', cell).lower() for cell in rows[0]]
            if header[0] not in {'module', 'modulename'} or 'version' not in header[1]:
                continue
            target = files if 'productversion' in header[1] else modules
            for row in rows[1:]:
                if len(row) < 2:
                    continue
                name, version = row[0].strip(), re.sub(r'\s+', '', row[1])
                if not name or not VERSION.fullmatch(version):
                    continue
                if name in target and target[name] != version:
                    raise BaselineError('같은 release의 모듈 버전이 서로 다릅니다')
                target[name] = version
    if not found or not files:
        raise BaselineError('명시한 버전의 Package Configuration 표를 찾지 못했습니다')
    resolved, unresolved = {}, {}
    for name, version in files.items():
        if Path(name).name != name or ':' in name or '\\' in name or '/' in name:
            raise BaselineError('구성 표에 안전하지 않은 모듈 이름이 있습니다')
        matches = []
        if install_dir is not None:
            directory = Path(install_dir)
            try:
                matches = [p for p in directory.rglob('*') if p.name.casefold() == name.casefold()
                           and p.is_file() and not p.is_symlink()]
            except OSError as error:
                raise BaselineError('설치 폴더의 파일 위치를 확인할 수 없습니다') from error
        if len(matches) == 1:
            resolved[matches[0].relative_to(directory).as_posix()] = version
        else:
            unresolved[name] = {'expected': version,
                                'status': 'ambiguous' if len(matches) > 1 else 'path_unconfirmed'}
    return {'release_note': {
                '_source': path.name, '_source_sha256': document_sha256,
                '_selected_release': release_version, '_file_version_kind': 'product',
                '_approval': {'status': 'approved_source' if approved else 'pending'},
                'programs': {'Bellalun': release_version}, 'files': resolved,
                'db_software_version': None, '_module_versions': modules,
                '_unresolved_files': unresolved},
            'missing_baselines': ['db_software_version'], 'unresolved_files': unresolved}


def _text(element):
    return ''.join(node.text or '' for node in element.findall('.//w:t', NS)).strip()


def product_version(path):
    """Release Note가 지정한 ProductVersion을 조회한다. FileVersion으로 대체하지 않는다."""
    if os.name != 'nt' or not Path(path).is_file():
        return None
    from ctypes import wintypes
    version = ctypes.WinDLL('version', use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                     ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, data):
        return None
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if version.VerQueryValueW(data, r'\VarFileInfo\Translation', ctypes.byref(pointer), ctypes.byref(length)):
        translations = (ctypes.c_ushort * (length.value // 2)).from_address(pointer.value)
        for i in range(0, len(translations) - 1, 2):
            key = f'\\StringFileInfo\\{translations[i]:04x}{translations[i+1]:04x}\\ProductVersion'
            if version.VerQueryValueW(data, key, ctypes.byref(pointer), ctypes.byref(length)):
                return ctypes.wstring_at(pointer.value, max(0, length.value - 1)).strip() or None
    if version.VerQueryValueW(data, '\\', ctypes.byref(pointer), ctypes.byref(length)) and length.value >= 24:
        fixed = (ctypes.c_uint32 * 6).from_address(pointer.value)
        if fixed[0] == 0xFEEF04BD:
            return '.'.join(str(part) for part in (fixed[4] >> 16, fixed[4] & 65535,
                                                  fixed[5] >> 16, fixed[5] & 65535))
    return None
