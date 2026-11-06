"""Setup의 오프라인 구성품 준비. 제품 실행·SQL 연결·DB 복원을 하지 않는다."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import subprocess

from .resources import bundled_config
from .runtime import load_config, save_config

BASELINES = {'DATA.bak', 'ACCOUNT.bak', 'CONFIGURATION.bak', 'PROCEDURE.bak'}


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def verify_assets(resources):
    resources = Path(resources)
    items = json.loads((resources / 'assets-manifest.json').read_text(encoding='utf-8'))['files']
    baseline_names = set()
    assets = (resources / 'assets').resolve()
    for item in items:
        name = item['destination']
        relative = PureWindowsPath(name)
        if relative.is_absolute() or relative.drive or '..' in relative.parts or ':' in name:
            raise ValueError('승인 자료 경로가 올바르지 않습니다.')
        target = assets.joinpath(*relative.parts).resolve()
        if not target.is_relative_to(assets):
            raise ValueError('승인 자료가 설치 자료 폴더 밖을 가리킵니다.')
        if digest(target) != item['sha256']:
            raise ValueError(f'승인 자료 SHA-256 불일치: {name}')
        if item['kind'] == 'baseline':
            baseline_names.add(name.replace('\\', '/'))
    if baseline_names != {'Baseline/' + name for name in BASELINES}:
        raise ValueError('승인 Baseline 4개가 필요합니다.')


def ocr_ready(executable):
    executable = Path(executable)
    if not executable.is_file() or not (executable.parent / 'tessdata/eng.traineddata').is_file():
        return False
    try:
        child = subprocess.run([str(executable), '--version'], stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, errors='replace', timeout=30,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return child.returncode == 0 and 'tesseract' in (child.stdout or '').lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_ocr(resources, configured):
    resources = Path(resources)
    spec = json.loads((resources / 'components.json').read_text(encoding='utf-8'))['tesseract']
    default = Path(spec['default_install_dir']) / 'tesseract.exe'
    selected = Path(configured) if configured else None
    if selected and ocr_ready(selected):
        return selected
    if selected and selected != default:
        raise ValueError('저장된 OCR 경로가 유효하지 않습니다. PC별 설정의 OCR 경로를 수정하세요.')
    candidates = [default]
    on_path = shutil.which('tesseract')
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if ocr_ready(candidate):
            return candidate
    installer = resources / 'installers' / spec['filename']
    if digest(installer) != spec['sha256']:
        raise ValueError('OCR 설치 파일 SHA-256 불일치. Setup을 다시 받아 설치하세요.')
    if os.name == 'nt':
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise ValueError('OCR 자동 설치는 관리자 권한으로 Setup을 다시 실행하세요.')
    # NSIS requires /D= as the final, unquoted argument even when it has spaces.
    command = '"' + str(installer) + '" /S /D=' + str(default.parent)
    child = subprocess.run(command,
                           stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=int(spec['timeout_sec']),
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if child.returncode != 0:
        raise ValueError(f'OCR 설치 실패(exit={child.returncode}). Setup을 다시 실행하세요.')
    if not ocr_ready(default):
        raise ValueError('OCR 설치 후 실행 또는 eng.traineddata 검사 실패. Setup을 다시 실행하세요.')
    return default


def prepare_install(layout):
    lines = ['BellalunAuto 설치 준비 결과']
    failed = False
    try:
        verify_assets(layout.resource_dir)
        lines.append('[OK] 승인 Baseline 4개·체크리스트·매뉴얼 SHA-256 확인')
        existing = layout.config_path.exists()
        if existing:
            config = bundled_config(load_config(layout), layout.resource_dir)
        else:
            from .gui import first_run_config, load_gui_config
            config = bundled_config(first_run_config(load_gui_config(layout)), layout.resource_dir)
        from .app import elevated_workspace_problems
        problems = elevated_workspace_problems(layout.workspace, config)
        if problems:
            raise ValueError('\n'.join(problems))
        baseline = Path(config.get('baseline_dir') or '')
        if not all((baseline / name).is_file() for name in BASELINES):
            raise ValueError('설정의 Baseline 경로에 백업 4개가 없습니다. PC별 설정을 확인하세요.')
        ocr = ensure_ocr(layout.resource_dir, (config.get('xipl') or {}).get('tesseract_exe', ''))
        if existing and Path((config.get('xipl') or {}).get('tesseract_exe') or '') != ocr:
            raise ValueError('기존 설정을 보존했습니다. PC별 설정의 OCR 경로를 다음 값으로 저장하세요: ' + str(ocr))
        lines.append('[OK] OCR 실행·영어 언어 파일 확인: ' + str(ocr))
        if existing:
            lines.append('[OK] 기존 PC별 설정 보존')
        else:
            config.setdefault('xipl', {})['tesseract_exe'] = str(ocr)
            save_config(layout, config)
            lines.append('[OK] PC별 경로 탐지·OCR·Baseline 설정 연결')
        lines.append('다음 행동: BellalunAuto의 준비 점검에서 제품·시험 서버·USB 상태를 확인하세요.')
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        failed = True
        lines.append(f'[FAIL] {error}')
        lines.append('다음 행동: 아래 기록과 PC별 설정을 확인한 뒤 Setup 또는 prepare-install을 다시 실행하세요.')
    summary = layout.workspace / 'install-preparation.txt'
    summary.parent.mkdir(parents=True, exist_ok=True)
    lines.append('준비 기록: ' + str(summary))
    summary.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')
    print('\n'.join(lines))
    return 1 if failed else 0
