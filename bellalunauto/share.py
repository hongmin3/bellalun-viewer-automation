"""명시한 실행 보고서와 선택한 증거만 담는 오프라인 공유 ZIP."""
from __future__ import annotations

import hashlib
import html
import io
import json
import ntpath
import posixpath
import re
import zipfile
from xml.etree import ElementTree
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

_REPORTS = {'.html', '.json', '.txt', '.csv', '.xlsx'}
_IMAGES = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
_ATTR = re.compile(r'''\b(href|src|action|poster)\s*=\s*(?:(["'])(.*?)\2|([^\s>]+))''', re.I | re.S)
_CSS = re.compile(r'''url\(\s*(["']?)(.*?)\1\s*\)|@import\s+["'](.*?)["']''', re.I | re.S)
_SENSITIVE = re.compile(r'password|passwd|credential|secret|token|api[_-]?key', re.I)
_SECRET_VALUE = re.compile(r'''(?:password|passwd|api[_-]?key|access[_-]?token)\s*["']?\s*[:=]\s*[^\s<,}]+''', re.I)


def _xlsx_check(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if name.endswith('.rels'):
                root = ElementTree.fromstring(archive.read(name))
                if any(item.get('TargetMode', '').lower() == 'external' for item in root):
                    raise ValueError('XLSX 외부 링크는 공유할 수 없습니다.')


def _html_references(text):
    return ([m[3] or m[4] for m in _ATTR.finditer(text)]
            + [m[2] or m[3] for m in _CSS.finditer(text)])


def _safe_name(name):
    return (bool(name) and '\\' not in name and ':' not in name
            and not name.startswith('/') and all(p not in ('', '.', '..') for p in name.split('/')))


def _sensitive(path):
    return (any(part.lower() in {'config', 'configuration', 'credentials', '.ssh'} for part in path.parts)
            or path.name.lower().startswith(('config.', 'config_', '.env'))
            or bool(_SENSITIVE.search(path.name)))


def _check_json(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if _SENSITIVE.search(key):
                raise ValueError('비밀번호·인증 설정은 공유할 수 없습니다.')
            _check_json(child)
    elif isinstance(value, list):
        for child in value:
            _check_json(child)


def _references(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'evidence', 'logs', 'dicom'}:
                for item in child if isinstance(child, list) else [child]:
                    if isinstance(item, str):
                        yield item
            else:
                yield from _references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _references(child)


def _local_path(reference, source):
    reference = html.unescape(reference)
    parsed = urlsplit(reference)
    if parsed.scheme.lower() == 'file':
        if parsed.netloc:
            return None  # 네트워크 공유를 자동 수집하지 않는다.
        raw = unquote(parsed.path)
        if re.match(r'^/[A-Za-z]:/', raw):
            raw = raw[1:]
    elif parsed.scheme and not re.match(r'^[A-Za-z]:[\\/]', reference):
        return None
    else:
        raw = unquote(reference.split('#', 1)[0].split('?', 1)[0])
    if not raw:
        return None
    candidate = Path(raw)
    return (candidate if candidate.is_absolute() else source.parent / candidate).resolve()


def _kind(path):
    suffix = path.suffix.lower()
    if suffix in _IMAGES:
        return 'evidence'
    if suffix in {'.dcm', '.dicom'}:
        return 'dicom'
    if suffix == '.log':
        return 'logs'
    if suffix == '.json' and path.name.startswith('failure_') and path.parent.name == 'failure':
        return 'logs'
    return None


def _failure_log_window(path):
    """실제 failure 증거 묶음에서 선택한 Viewer 로그 구간만 분리한다."""
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    log = value.get('log')
    if not isinstance(log, dict) or not isinstance(log.get('lines'), list):
        raise ValueError('Viewer 로그 구간 형식이 올바르지 않습니다.')
    if not all(isinstance(line, str) for line in log['lines']):
        raise ValueError('Viewer 로그 구간에 문자열이 아닌 행이 있습니다.')
    window = {key: log[key] for key in ('found', 'encoding', 'window', 'lines', 'truncated') if key in log}
    # 원본 로그 경로·메모리·창 제목·덤프 등 선택하지 않은 정보는 포함하지 않는다.
    payload = {key: value[key] for key in ('tc_id', 'event_time') if key in value}
    payload['log'] = window
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    if _SECRET_VALUE.search(data.decode('utf-8')):
        raise ValueError('로그 구간에 인증 값이 포함되어 있습니다.')
    return data


def create_package(output, *, run_id, reports, review=None, include_evidence=False,
                   include_dicom=False, include_logs=False) -> Path:
    """보고서 Path 목록과 review JSON을 공유한다. 디렉터리는 받지 않는다.

    증거는 보고서가 참조한 실행 루트의 Evidence/Log/Logs/DICOM 안 파일만
    선택 범위별로 포함한다. 관련 없는 형제 파일이나 외부 경로는 수집하지 않는다.
    """
    if not str(run_id).strip():
        raise ValueError('실행 번호가 필요합니다.')
    sources = [Path(p).resolve() for p in reports]
    if not sources:
        raise ValueError('공유할 보고서를 선택하세요.')
    review_path = Path(review).resolve() if review is not None else None
    if review_path:
        sources.append(review_path)
    selected = {'evidence': bool(include_evidence), 'dicom': bool(include_dicom), 'logs': bool(include_logs)}
    mapping, payloads, documents = {}, {}, {}

    def add(path, name):
        if _sensitive(path) or not path.is_file():
            raise ValueError('민감한 파일 또는 없는 파일은 공유할 수 없습니다: ' + path.name)
        if not _safe_name(name) or name.casefold() in {n.casefold() for n in mapping.values()}:
            raise ValueError('공유 파일 이름이 중복되거나 안전하지 않습니다: ' + name)
        mapping[path] = name
        payloads[name] = path.read_bytes()

    for source in sources:
        if source.suffix.lower() not in _REPORTS or (source == review_path and source.suffix.lower() != '.json'):
            raise ValueError('지원하지 않는 보고서 형식입니다: ' + source.name)
        add(source, ('review/' if source == review_path else 'reports/') + source.name)
        if source.suffix.lower() == '.xlsx':
            _xlsx_check(payloads[mapping[source]])
        elif _SECRET_VALUE.search(payloads[mapping[source]].decode('utf-8-sig')):
            raise ValueError('비밀번호·인증 값이 포함된 보고서는 공유할 수 없습니다.')
        if source.suffix.lower() == '.json':
            data = json.loads(payloads[mapping[source]].decode('utf-8-sig'))
            _check_json(data)
            documents[source] = data

    roots = {source.parent.parent / folder for source in sources for folder in ('Evidence', 'Log', 'Logs', 'DICOM')}
    roots = {root.resolve() for root in roots
             if root.resolve().is_relative_to(root.parent.resolve())}
    for source in sources:
        refs = list(_references(documents[source])) if source in documents else []
        if source.suffix.lower() == '.html':
            refs += _html_references(payloads[mapping[source]].decode('utf-8-sig'))
        for ref in refs:
            target = _local_path(ref, source)
            kind = _kind(target) if target else None
            if (target in mapping or not kind or not selected[kind]
                    or not any(target.is_relative_to(root) for root in roots)):
                continue
            if _sensitive(target):
                raise ValueError('민감한 증거 파일은 공유할 수 없습니다: ' + target.name)
            add(target, kind + '/' + target.name)
            if kind == 'logs' and target.suffix.lower() == '.json':
                payloads[mapping[target]] = _failure_log_window(target)

    def relative(ref, source):
        if ref.startswith('#'):
            return ref
        target = _local_path(ref, source)
        if target not in mapping:
            return None
        return quote(posixpath.relpath(mapping[target], posixpath.dirname(mapping[source])), safe='/')

    def rewrite_json(value, source, reference=False):
        if isinstance(value, dict):
            return {key: rewrite_json(child, source, reference or key in {'evidence', 'logs', 'dicom'})
                    for key, child in value.items()}
        if isinstance(value, list):
            return [rewrite_json(child, source, reference) for child in value]
        if reference and isinstance(value, str):
            return relative(value, source) or '[공유 제외]'
        return value

    for source in sources:
        name = mapping[source]
        if source in documents:
            payloads[name] = json.dumps(rewrite_json(documents[source], source), ensure_ascii=False, indent=2).encode('utf-8')
        elif source.suffix.lower() == '.html':
            def replace(match):
                ref = relative(match[3] or match[4], source)
                return f'{match[1]}="{html.escape(ref, quote=True)}"' if ref is not None else 'data-share-excluded="true"'
            text = _ATTR.sub(replace, payloads[name].decode('utf-8-sig'))
            def replace_css(match):
                ref = relative(match[2] or match[3], source)
                return 'url("' + ref + '")' if ref else 'none'
            text = _CSS.sub(replace_css, text)
            # 복수 이미지·자동 이동은 공유 보고서에 필요하지 않다.
            text = re.sub(r'''\bsrcset\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)''', '', text, flags=re.I)
            text = re.sub(r'<meta\b[^>]*http-equiv\s*=\s*["\']?refresh\b[^>]*>', '', text, flags=re.I)
            payloads[name] = text.encode('utf-8')

    manifest = {'version': 1, 'run_id': str(run_id), 'scope': selected,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'files': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(payloads.items())}}
    output = Path(output)
    if output.resolve() in mapping:
        raise ValueError('출력 ZIP이 입력 파일을 덮어쓸 수 없습니다.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payloads.items()):
            archive.writestr(name, data)
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    return output


def verify_package(path) -> list[str]:
    """압축을 풀거나 링크를 열지 않고 무결성과 오프라인 링크를 검사한다."""
    errors = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(n.casefold() for n in names)):
                errors.append('중복 ZIP 항목')
            for name in names:
                if not _safe_name(name):
                    errors.append('ZIP 경로 이탈: ' + name)
            manifest = json.loads(archive.read('manifest.json'))
            if not manifest.get('run_id') or not manifest.get('scope') or not manifest.get('created_at'):
                errors.append('manifest 실행 정보 누락')
            files = manifest['files']
            for name in set(files) - set(names):
                errors.append('파일 누락: ' + name)
            for name in set(names) - set(files) - {'manifest.json'}:
                errors.append('추가 파일: ' + name)
            for name in set(files) & set(names):
                data = archive.read(name)
                item = files[name]
                if item.get('size') != len(data) or item.get('sha256') != hashlib.sha256(data).hexdigest():
                    errors.append('크기·해시 불일치: ' + name)
                refs = []
                if name.lower().endswith('.html'):
                    refs = _html_references(data.decode('utf-8-sig'))
                elif name.lower().endswith('.json'):
                    refs = list(_references(json.loads(data.decode('utf-8-sig'))))
                elif name.lower().endswith('.xlsx'):
                    _xlsx_check(data)
                for ref in refs:
                    if ref == '[공유 제외]' or ref.startswith('#'):
                        continue
                    parsed = urlsplit(html.unescape(ref))
                    raw = unquote(parsed.path)
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(name), raw))
                    if (parsed.scheme or parsed.netloc or '\\' in raw or ntpath.isabs(raw)
                            or not _safe_name(target) or target not in files):
                        errors.append('ZIP 밖 또는 없는 링크: ' + name)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError,
            ElementTree.ParseError, zipfile.BadZipFile, RuntimeError) as exc:
        errors.append('공유 ZIP 형식 오류: ' + type(exc).__name__)
    return errors
