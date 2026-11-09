"""저장된 컨트롤 크롭을 실제 선택 경로와 같은 판독/판정으로 재생한다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from PIL import Image

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import ocr_selection


def replay(manifest, executable=None):
    path = Path(manifest).resolve()
    corpus = json.loads(path.read_text(encoding='utf-8-sig'))
    cases = corpus.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('cases에 비교할 캡처가 필요합니다.')
    results = []
    for case in cases:
        images = []
        if 'expected' not in case or not case.get('wanted') or not case.get('images'):
            raise ValueError('wanted, images, expected 필수')
        for name in case['images']:
            source = path.parent / name
            if source.is_symlink() or not source.resolve().is_relative_to(path.parent):
                raise ValueError('manifest 폴더 밖 캡처는 허용하지 않습니다.')
            with Image.open(source) as opened:
                images.append(opened.convert('RGB'))
        wanted = case['wanted']
        reads = [[] for _ in images]
        chosen, scores, reason = None, [], 'unreadable'
        for profile in ocr_selection.PROFILES:
            for index, image in enumerate(images):
                reads[index].append(ocr_selection.read_image(image, executable, profile))
            chosen, scores, reason = ocr_selection.rank(reads, wanted, case.get('match', 'fuzzy'))
            if chosen is not None:
                break
        passed = (chosen == case['expected'] and
                  ('reason' not in case or reason == case['reason']))
        results.append({'name': case.get('name', str(len(results))), 'passed': passed,
                        'selected': chosen, 'reason': reason, 'scores': scores,
                        'attempts': len(reads[0]) if reads else 0})
    return {'cases': results, 'passed': sum(row['passed'] for row in results),
            'failed': sum(not row['passed'] for row in results)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='OCR 저장 캡처 오프라인 비교(Viewer 조작 없음)')
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--tesseract', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.exists():
            raise ValueError('기존 결과를 덮어쓰지 않습니다.')
        result = replay(args.manifest, args.tesseract)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(text + '\n')
        print(text)
        return int(result['failed'] > 0)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'재판독 실패: {type(error).__name__}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
