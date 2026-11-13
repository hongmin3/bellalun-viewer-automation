"""승인 Release Note에서 로컬 config 병합용 기준만 추출한다. config는 쓰지 않는다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.release_note_baseline import BaselineError, extract_baseline


def main(argv=None):
    parser = argparse.ArgumentParser(description='승인 DOCX의 명시한 판을 로컬 기준 JSON으로 추출합니다. DB 버전은 추정하지 않습니다.')
    parser.add_argument('document', type=Path, help='로컬 Release Note DOCX')
    parser.add_argument('--release-version', required=True, help='문서 안의 정확한 release 버전')
    parser.add_argument('--install-dir', required=True, type=Path, help='구성 파일 위치를 연결할 실제 설치 폴더(읽기만 함)')
    parser.add_argument('--approved-source', action='store_true', help='사용자가 승인한 원문임을 명시(없으면 pending)')
    parser.add_argument('--output', type=Path, help='새 runtime JSON 파일. 생략하면 표준 출력. config.json 직접 쓰기 금지')
    options = parser.parse_args(argv)
    try:
        result = extract_baseline(options.document, options.release_version,
                                  install_dir=options.install_dir, approved=options.approved_source)
        if options.output:
            root = Path(__file__).resolve().parents[1]
            output = options.output.resolve()
            if output.name.lower() == 'config.json' or (
                    output.is_relative_to(root) and not output.is_relative_to(root / 'work')):
                raise BaselineError('저장소 안의 출력은 work 아래 새 파일만 허용하며 config.json은 쓰지 않습니다')
            with output.open('x', encoding='utf-8') as target:
                json.dump(result, target, ensure_ascii=False, indent=2)
            print(f'기준 추출: {output.name} · DB 기준과 미확인 파일 위치는 별도 확인이 필요합니다.')
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BaselineError, OSError) as error:
        print(f'기준 추출 차단: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
