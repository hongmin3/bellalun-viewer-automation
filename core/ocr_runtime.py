"""OCR 실행 환경 식별. 사용자 경로와 외부 오류 원문은 결과에 싣지 않는다."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess

REFERENCE_VERSION = '5.5.3'


def _digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def inspect_runtime(executable):
    """Return JSON-safe version/file identity; never install or alter OCR.

    reference_match compares the parsed engine version, not an approved binary
    hash. Both file hashes support comparisons between machines and runs. No
    cache is retained, so replacing either file is visible on the next call.
    """
    result = {'executable_sha256': None, 'version_line': None, 'version': None,
              'eng_traineddata_sha256': None, 'reference_version': REFERENCE_VERSION,
              'reference_match': False, 'errors': []}
    try:
        path = Path(executable)
    except (TypeError, ValueError):
        result['errors'].append('executable_invalid')
        return result
    for file, key, error in (
            (path, 'executable_sha256', 'executable_unreadable'),
            (path.parent / 'tessdata/eng.traineddata', 'eng_traineddata_sha256',
             'eng_traineddata_unreadable')):
        try:
            result[key] = _digest(file)
        except (OSError, ValueError):
            result['errors'].append(error)
    if result['executable_sha256'] is None:
        return result
    try:
        child = subprocess.run([str(path), '--version'], stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding='utf-8',
                               errors='replace', timeout=30,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        result['errors'].append('version_timeout')
        return result
    except (OSError, ValueError):
        result['errors'].append('version_failed')
        return result
    if child.returncode:
        result['errors'].append('version_failed')
        return result
    line = (child.stdout or '').splitlines()
    first = line[0].strip() if line else ''
    # Only a standard version banner is safe to retain. Unexpected process
    # output may contain private paths or user data; never copy it to reports.
    match = re.fullmatch(r'tesseract\s+v?(\d+\.\d+\.\d+)(?:[.\-+][0-9A-Za-z.\-+]*)?',
                         first, re.IGNORECASE)
    if match:
        result['version_line'] = first
        result['version'] = match.group(1)
    else:
        result['errors'].append('version_unrecognized')
    result['reference_match'] = (result['version'] == REFERENCE_VERSION
                                 and not result['errors'])
    return result
