"""한 캡처의 제한된 OCR 재판독과 모호한 UI 선택 차단."""
from __future__ import annotations

from difflib import SequenceMatcher
from contextvars import ContextVar
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import tempfile
import subprocess

from PIL import Image, ImageGrab, ImageOps

PROFILES = (('auto', 3, 7), ('invert', 4, 7), ('binary', 4, 6), ('auto', 4, 11))
_evidence_root = ContextVar('ocr_evidence_root', default=None)


def set_evidence_root(root):
    return _evidence_root.set(Path(root).resolve())


def reset_evidence_root(token):
    _evidence_root.reset(token)


def normalize(text):
    value = re.sub(r'[^a-z0-9]+', '', str(text or '').lower())
    return 'hvl' if value == 'avl' else value


class SelectionError(RuntimeError):
    def __init__(self, reason, detail):
        self.reason, self.detail = reason, detail
        super().__init__(f"OCR 선택 중단({reason}): {detail['wanted']!r}; "
                         f"증거={detail.get('evidence', '저장 위치 없음')}")


class PopulationChanged(RuntimeError):
    """고정 슬롯의 내용 변경: 기존 세대의 캡처를 판독 전에 폐기해야 한다."""


def prepare(image, profile):
    mode, scale, _ = profile
    gray = ImageOps.autocontrast(image.convert('L'))
    if mode == 'invert':
        gray = ImageOps.invert(gray)
    elif mode == 'binary':
        gray = gray.point(lambda value: 255 if value > 150 else 0)
        if gray.resize((1, 1)).getpixel((0, 0)) < 128:
            gray = ImageOps.invert(gray)
    resized = gray.resize((gray.width * scale, gray.height * scale),
                          Image.Resampling.LANCZOS)
    # 소형 컨트롤의 글자가 테두리에 닿지 않게 한다.
    return ImageOps.expand(resized, border=10, fill=255)


def resolve_executable(executable=None):
    from .screen import TESSERACT_EXE
    return Path(executable or shutil.which('tesseract') or TESSERACT_EXE).resolve()


def run_ocr(image, executable, profile):
    selected = resolve_executable(executable)
    # 래퍼의 문자열 재분할을 피하고 공백 경로도 각각의 인자로 전달한다.
    with tempfile.TemporaryDirectory(prefix='bellalun-ocr-') as temp:
        source = Path(temp) / 'input.png'
        image.save(source)
        child = subprocess.run(
            [str(selected), str(source), 'stdout', '--tessdata-dir',
             str(selected.parent / 'tessdata'), '-l', 'eng', '--psm', str(profile[2]), 'tsv'],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=8,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if child.returncode:
            raise RuntimeError('OCR 실행 실패')
        parsed = list(csv.DictReader(io.StringIO(child.stdout.decode('utf-8')), delimiter='\t'))
        return {'text': [row['text'] for row in parsed], 'conf': [row['conf'] for row in parsed]}


def read_image(image, executable=None, profile=PROFILES[0]):
    made = prepare(image, profile)
    try:
        result = run_ocr(made, executable, profile)
        words = [(str(text).strip(), float(conf)) for text, conf in
                 zip(result['text'], result['conf']) if str(text).strip()]
        text = ' '.join(word for word, _ in words)
        confidence = min((conf for _, conf in words), default=0.0)
        return {'text': text, 'confidence': confidence,
                'profile': list(profile), 'error': None}
    except Exception as error:  # OCR 실패는 클릭 근거로 사용하지 않는다.
        return {'text': '', 'confidence': 0.0, 'profile': list(profile),
                'error': type(error).__name__, 'error_detail': _error_detail(error, 'ocr')}


def _error_detail(error, stage):
    """내부 고정 진단은 보존하고 외부 오류 원문은 지문으로만 식별한다."""
    message = str(error)
    safe_messages = {
        'OCR 실행 실패', '빈 컨트롤 영역', '판독 중 후보 식별자 변경',
        '선택 직전 후보 식별자 변경',
        'Print Overlay catalogue row changed during scroll',
        'Print Overlay catalogue row could not be fully revealed',
        'Print Overlay catalogue scroll made no movement',
        'Print Overlay catalogue scroll geometry did not settle',
        'Print Overlay catalogue scroll state did not settle',
        'Print Overlay catalogue origin restore mismatch',
        'Print Overlay catalogue changed during scroll',
        'Print Overlay catalogue scroll arrows not found',
        'Print Overlay catalogue invalid viewport',
        'Print Overlay catalogue insufficient overlap',
        'Print Overlay catalogue traversal limit',
        'Print Overlay catalogue partial row mismatch',
        'Print Overlay catalogue insufficient partial evidence',
        'Print Overlay catalogue overlap mismatch',
        'Print Overlay catalogue unresolved partial row',
        'Print Overlay catalogue viewport population changed',
        'Print Overlay catalogue target population not found',
        'Print Overlay catalogue control not found',
        'Print Overlay catalogue scroll control not found',
        'Print Overlay catalogue has no visible rows',
    }
    detail = {'stage': stage, 'error': type(error).__name__,
              'message': message if message in safe_messages else '[untrusted error text omitted]',
              'message_sha256': hashlib.sha256(message.encode('utf-8', errors='replace')).hexdigest()}
    foreground = '클릭 전에 Viewer 를 최전면으로 올리지 못했습니다'
    if message.startswith(foreground):
        detail['message'] = foreground + '(가린 창: [redacted]).'
    for name in ('errno', 'winerror'):
        value = getattr(error, name, None)
        if isinstance(value, int):
            detail[name] = value
    return detail


def rank(reads, wanted, match='fuzzy'):
    key = normalize(wanted)
    scores = []
    for row_reads in reads:
        best = 0.0
        for read in row_reads:
            text = normalize(read['text'])
            if not key or not text or read['confidence'] < 35:
                continue
            if match == 'exact' or len(key) <= 4:
                score = float(text == key)
            elif match == 'contains':
                score = float(key in text)
            elif match == 'prefix':
                score = float(min(len(key), len(text)) >= 4 and
                              (key.startswith(text) or text.startswith(key)))
            else:
                score = SequenceMatcher(None, key, text).ratio()
            best = max(best, score)
        scores.append(best)
    ordered = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    if not ordered or ordered[0][1] < .85:
        return None, scores, 'unreadable'
    if any(not any(normalize(read['text']) and read['confidence'] >= 35
                   for read in row_reads) for row_reads in reads):
        return None, scores, 'unreadable'
    if len(ordered) > 1 and ordered[0][1] - ordered[1][1] < .15:
        return None, scores, 'ambiguous'
    return ordered[0][0], scores, None


def _environment(executable):
    from .ocr_runtime import inspect_runtime
    value = {'os': platform.system(), 'os_version': platform.version(),
             'ocr': inspect_runtime(resolve_executable(executable))}
    if os.name == 'nt':
        import ctypes
        user = ctypes.WinDLL('user32', use_last_error=True)
        value['screen'] = [user.GetSystemMetrics(0), user.GetSystemMetrics(1)]
        try:
            value['dpi'] = user.GetDpiForSystem()
        except AttributeError:
            value['dpi'] = None
    return value


def save_failure(detail, images, executable, evidence_dir, catalogue_image=None):
    root = _evidence_root.get()
    base = (Path(evidence_dir) if evidence_dir else
            (root / 'OCR' if root else Path(tempfile.gettempdir()) / 'BellalunAuto' / 'OCR'))
    base.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix='ocr-', dir=base))
    if catalogue_image is not None:
        catalogue_image.save(target / 'catalogue-raw.png')
    for index, image in enumerate(images):
        if image is None:
            continue
        image.save(target / f'{index:03d}-raw.png')
        for attempt, profile in enumerate(PROFILES):
            prepare(image, profile).save(target / f'{index:03d}-{attempt}.png')
    detail['environment'] = _environment(executable)
    # 파일 안에는 개인 절대경로를 쓰지 않는다.
    (target / 'selection.json').write_text(
        json.dumps(detail, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    detail['evidence'] = str(target)


def judge_images(images, wanted, executable=None, match='fuzzy'):
    """이미 수집한 논리 후보도 동일한 최대 4판독과 선택 기준으로 평가한다."""
    reads = [[] for _ in images]
    selected, scores, reason, attempts = None, [], 'unreadable', 0
    for attempts, profile in enumerate(PROFILES, 1):
        for index, image in enumerate(images):
            if image is not None:
                reads[index].append(read_image(image, executable, profile))
        selected, scores, reason = rank(reads, wanted, match)
        if selected is not None and all(image is not None for image in images):
            break
        selected = None
    return selected, {'attempts': attempts, 'scores': scores, 'reads': reads, 'reason': reason}


def select(controls, wanted, executable=None, *, evidence_dir=None, match='fuzzy',
           reveal=None, diagnostics=None):
    """유일한 후보만 반환한다. OCR 실패/경합이면 증거를 남기고 예외를 낸다."""
    if match not in {'fuzzy', 'exact', 'contains', 'prefix'}:
        raise ValueError('지원하지 않는 OCR 일치 방식')
    # 같은 HWND가 중복 열거된 것은 별도 후보가 아니다.
    controls = list({control.hwnd: control for control in controls}.values())
    images, rectangles, capture_errors = [], [], []
    for index, control in enumerate(controls):
        stage = 'reveal' if reveal is not None else 'capture'
        try:
            if reveal is not None:
                fresh = reveal(control)
                if (fresh.hwnd, fresh.ctrl_id) != (control.hwnd, control.ctrl_id):
                    raise ValueError('판독 중 후보 식별자 변경')
                control = controls[index] = fresh
            stage = 'capture'
            image = ImageGrab.grab(bbox=tuple(control.rect), all_screens=True)
            if image.width < 1 or image.height < 1:
                raise ValueError('빈 컨트롤 영역')
        except PopulationChanged:
            raise
        except Exception as error:
            image = None
            capture_errors.append({'candidate': index, **_error_detail(error, stage)})
        rectangles.append(list(control.rect))
        images.append(image)
    selected, judged = judge_images(images, wanted, executable, match)
    attempts, scores, reads, reason = (judged[key] for key in
                                      ('attempts', 'scores', 'reads', 'reason'))
    if selected is not None and reveal is not None:
        try:
            fresh = reveal(controls[selected])
            if (fresh.hwnd, fresh.ctrl_id) != (controls[selected].hwnd, controls[selected].ctrl_id):
                raise ValueError('선택 직전 후보 식별자 변경')
            controls[selected] = fresh
        except Exception as error:
            capture_errors.append({'candidate': selected,
                                   **_error_detail(error, 'selection-reveal')})
            selected, reason = None, 'capture-failed'
    detail = {'schema_version': 2, 'wanted': wanted, 'match': match,
              'attempts': attempts, 'scores': scores, 'reads': reads,
              'rectangles': rectangles, 'reason': reason, 'capture_errors': capture_errors}
    if selected is None:
        if any(image is None for image in images):
            detail['reason'] = reason = 'capture-failed'
        catalogue_image = None
        if diagnostics is not None:
            try:
                detail['catalogue'] = diagnostics()
                catalogue_image = ImageGrab.grab(
                    bbox=tuple(detail['catalogue']['rect']), all_screens=True)
            except Exception as error:
                detail['diagnostics_error'] = _error_detail(error, 'failure-catalogue')
        try:
            save_failure(detail, images, executable, evidence_dir, catalogue_image)
        except Exception as error:
            detail['evidence_error'] = type(error).__name__
        raise SelectionError(reason, detail)
    return controls[selected], detail
