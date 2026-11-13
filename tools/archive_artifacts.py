"""원본을 유지하는 생성물 분리 보관. 기본 조회, --apply에서만 기록한다."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.artifact_archive import archive_artifacts, verify_archive
from core.run_preservation import PreservationError


def main(argv=None):
    parser = argparse.ArgumentParser(description='생성물을 새 폴더에 검증 보관합니다. 원본 이동·삭제는 하지 않습니다.')
    parser.add_argument('--source', type=Path, help='보관할 기존 생성물 폴더')
    parser.add_argument('--destination', type=Path, help='사용자가 고른 아직 존재하지 않는 목적지 폴더')
    parser.add_argument('--compress', action='store_true', help='SHA-256을 대조하는 ZIP 압축 보관')
    parser.add_argument('--apply', action='store_true', help='계획을 실행해 새 목적지에 기록 (기본은 조회만)')
    parser.add_argument('--verify', type=Path, metavar='ARCHIVE_FOLDER', help='기존 보관본과 영수증을 읽어 검증만 수행')
    args = parser.parse_args(argv)
    if args.verify is not None:
        if args.source is not None or args.destination is not None or args.apply or args.compress:
            parser.error('--verify는 다른 실행 인자와 함께 사용할 수 없습니다.')
    elif args.source is None or args.destination is None:
        parser.error('--source와 --destination을 모두 명시하세요.')
    try:
        if args.verify is not None:
            result = verify_archive(args.verify)
            print(f"보관본 검증 완료 · 원문 {result['source_bytes']}바이트")
        else:
            result = archive_artifacts(args.source, args.destination, compress=args.compress, apply=args.apply)
            if args.apply:
                print(f"보관·해시 검증 완료 · 원본 유지 · 영수증: {result['receipt']}")
            else:
                print(f"조회만 완료 · 원문 {result['source_bytes']}바이트 · 필요 예약 {result['required_bytes']}바이트 · "
                      f"목적지 여유 {result['available_bytes']}바이트\n새 목적지: {result['destination']}\n"
                      '기록하려면 같은 명령에 --apply를 추가하세요. 원본은 이동하거나 삭제하지 않습니다.')
        return 0
    except (OSError, PreservationError) as error:
        print(f'보관/검증 실패: {error}')
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
