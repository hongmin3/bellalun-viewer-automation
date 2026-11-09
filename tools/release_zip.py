"""검증된 Setup 산출물을 설치용 릴리즈 ZIP으로 묶는다(포터블 배포 아님).

입력은 Setup, build-info.json, SHA256SUMS.txt, 후보일 때 후보 표식만 허용한다.
build-info 필수 키: version, application.path/sha256, release_gate.status/passed.
기존 빌더 호환을 위해 입력 manifest의 후보 표식 해시는 선택 사항이다.
ZIP manifest는 자기 자신을 제외한 모든 포함 파일을 해시한다.
해시는 전송 무결성을 검사하며 Setup 내부 EXE나 UI 통과를 증명하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

MARKER = '게이트-미통과-후보.txt'
MANIFEST = 'SHA256SUMS.txt'
GUIDE = '사용안내.txt'
HASH = re.compile(r'[0-9a-fA-F]{64}')


def _digest(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(block)
    return result.hexdigest()


def _file_hash(path):
    with path.open('rb') as stream:
        return _digest(stream)


def _not_link(path):
    # resolve() 전에 조상까지 확인해야 junction/symlink 우회가 보이지 않게 되지 않는다.
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f'링크 경로 금지: {part.name}')
        if part.exists():
            info = part.stat(follow_symlinks=False)
            if getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                raise ValueError(f'재분석 경로 금지: {part.name}')
            if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
                raise ValueError(f'하드 링크 파일 금지: {part.name}')


def _parse_manifest(text, allowed):
    entries = {}
    for line in text.splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64})  (.+)', line)
        if not match:
            raise ValueError('잘못된 SHA256SUMS 형식')
        digest, name = match.groups()
        if name not in allowed or name.casefold() in {n.casefold() for n in entries}:
            raise ValueError('manifest의 중복·허용되지 않은 경로')
        entries[name] = digest.lower()
    return entries


def _inspect_release(release):
    if not release.is_dir():
        raise ValueError('release 폴더 누락')
    paths = list(release.iterdir())
    for path in paths:
        _not_link(path)
        if not path.is_file():
            raise ValueError('release에는 일반 파일만 허용됩니다')
    names = {path.name for path in paths}
    if len(names) != len({n.casefold() for n in names}):
        raise ValueError('중복 파일 이름')
    if not {'build-info.json', MANIFEST} <= names:
        raise ValueError('build-info 또는 manifest 누락')
    # 파일명 allowlist를 먼저 적용해 민감한 추가 파일은 읽지 않는다.
    preliminary = {'build-info.json', MANIFEST, MARKER}
    if any(n not in preliminary and not re.fullmatch(r'BellalunAuto-\d+\.\d+\.\d+(?:-candidate)?-setup\.exe', n)
           for n in names):
        raise ValueError('허용되지 않은 추가 릴리즈 파일')
    hashes = _parse_manifest((release / MANIFEST).read_text(encoding='utf-8-sig'), names - {MANIFEST})
    required_hashes = names - {MANIFEST, MARKER}
    if not required_hashes <= hashes.keys():
        raise ValueError('manifest에 필수 파일 해시 누락')
    for name, expected in hashes.items():
        if _file_hash(release / name) != expected:
            raise ValueError(f'SHA256 불일치: {name}')
    # 모든 입력 manifest 해시를 확인한 다음 build-info를 신뢰해 이름을 판정한다.
    try:
        info = json.loads((release / 'build-info.json').read_text(encoding='utf-8-sig'))
        version = info['version']
        application = info['application']
        app_hash = application['sha256']
        gate = info['release_gate']
        passed = gate['passed']
        status = gate['status']
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('build-info 필수 메타데이터 누락·형식 오류') from error
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('잘못된 버전')
    if release.name != version:
        raise ValueError('release 폴더명과 버전 불일치')
    if (not isinstance(app_hash, str) or not HASH.fullmatch(app_hash)
            or application.get('path') != 'BellalunAuto.exe'):
        raise ValueError('application 경로·SHA256 형식 오류')
    if type(passed) is not bool or status != ('passed' if passed else 'candidate'):
        raise ValueError('릴리즈 게이트 상태 불일치')
    candidate = not passed
    installer = f'BellalunAuto-{version}{"-candidate" if candidate else ""}-setup.exe'
    expected_names = {installer, 'build-info.json', MANIFEST}
    if candidate:
        expected_names.add(MARKER)
    if names != expected_names:
        raise ValueError('Setup 파일명·후보 표식·포함 파일 불일치')
    if candidate and not (release / MARKER).stat().st_size:
        raise ValueError('빈 후보 표식')
    # manifest에서 빠진 기존 빌더 후보 표식도 ZIP 입력으로 고정한다.
    hashes.update({name: _file_hash(release / name) for name in names - {MANIFEST} if name not in hashes})
    return version, candidate, app_hash.lower(), hashes


def _zip_info(name):
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def create_release_zip(release, output):
    """신규 ZIP을 생성하고 JSON-safe 요약을 반환한다. 기존 output은 덮어쓰지 않는다."""
    release = Path(release).expanduser().absolute()
    output = Path(output).expanduser().absolute()
    _not_link(release)
    _not_link(output)
    release = release.resolve()
    output = output.resolve()
    if output.exists():
        raise ValueError('기존 output은 덮어쓸 수 없습니다')
    if output.suffix.lower() != '.zip' or not output.parent.is_dir():
        raise ValueError('존재하는 폴더의 새 .zip 경로를 지정하십시오')
    if output.is_relative_to(release):
        raise ValueError('output은 release 폴더 밖에 지정하십시오')
    version, candidate, app_hash, hashes = _inspect_release(release)
    guide = (f'BellalunAuto {version} 설치용 릴리즈 ZIP\n'
             '압축을 푼 뒤 함께 있는 Setup(-setup.exe)을 실행하여 설치하십시오.\n'
             '기존 설정은 보존됩니다. 기존 config.json을 삭제하거나 덮어쓰지 마십시오.\n'
             + ('후보 빌드: 제품 UI 검증을 마치지 않았습니다. 정식 배포로 간주하지 마십시오.\n' if candidate else '')
             + '사내 자료가 포함된 배포물입니다. 공개 업로드 금지.\n').encode('utf-8')
    hashes[GUIDE] = hashlib.sha256(guide).hexdigest()
    manifest = ''.join(f'{hashes[name]}  {name}\n' for name in sorted(hashes)).encode('utf-8')
    temp_path = None
    try:
        fd, filename = tempfile.mkstemp(prefix=f'.{output.name}.', suffix='.tmp', dir=output.parent)
        os.close(fd)
        temp_path = Path(filename)
        with zipfile.ZipFile(temp_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(hashes):
                if name == GUIDE:
                    archive.writestr(_zip_info(name), guide)
                    continue
                _not_link(release / name)
                with (release / name).open('rb') as source, archive.open(_zip_info(name), 'w', force_zip64=True) as target:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        target.write(block)
            archive.writestr(_zip_info(MANIFEST), manifest)
        with zipfile.ZipFile(temp_path) as archive:
            if archive.testzip() is not None:
                raise ValueError('ZIP CRC 검증 실패')
            if set(archive.namelist()) != set(hashes) | {MANIFEST} or len(archive.namelist()) != len(hashes) + 1:
                raise ValueError('ZIP 포함 파일 검증 실패')
            verified = _parse_manifest(archive.read(MANIFEST).decode('utf-8'), set(hashes))
            if verified != hashes:
                raise ValueError('ZIP 내부 manifest 검증 실패')
            for name, expected in verified.items():
                with archive.open(name) as source:
                    if _digest(source) != expected:
                        raise ValueError(f'ZIP 내부 SHA256 검증 실패: {name}')
        summary = {'version': version, 'candidate': candidate, 'application_sha256': app_hash,
                   'entries': sorted([*hashes, MANIFEST]), 'sha256': _file_hash(temp_path)}
        # 같은 디렉터리의 임시 파일을 원자적으로 게시. 다른 프로세스의 output도 덮어쓰지 않는다.
        _not_link(output.parent)
        os.link(temp_path, output)
        return summary
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='기존 Setup 산출물의 설치용 릴리즈 ZIP 생성')
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = create_release_zip(args.release, args.output)
    except (ValueError, OSError, UnicodeError, zipfile.BadZipFile) as error:
        print(f'릴리즈 ZIP 생성 중단: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
