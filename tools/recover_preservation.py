"""미완료 실행 보존을 조회하거나 명시 승인 후 복구한다."""
import argparse
import json
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.run_preservation import RunPreservation, PreservationError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--apply', action='store_true', help='선택한 실행의 실제 제품/DB 복구 승인')
    parser.add_argument('--acknowledge-unstarted', action='store_true',
                        help='백업 실패 뒤 제품 시험이 시작되지 않았음을 사람이 확인')
    args = parser.parse_args(argv)
    try:
        if not args.apply:
            print(json.dumps({'pending': RunPreservation.pending(args.workspace)}, ensure_ascii=False))
            return 0
        if not args.run_id:
            raise ValueError('--apply는 --run-id로 복구 대상을 지정해야 합니다.')
        from bellalunauto.runtime import RunLock
        if args.acknowledge_unstarted:
            with RunLock():
                result = RunPreservation.recover(args.workspace, args.run_id, acknowledge_unstarted=True)
        else:
            if not args.config:
                raise ValueError('실제 복원에는 --config가 필요합니다.')
            from run import Context
            from core.execution_session import DatabasePreservation, stop_product, start_services
            ctx = Context(str(args.config))
            with RunLock():
                stop_product(ctx)
                try:
                    result = RunPreservation.recover(args.workspace, args.run_id,
                                                    db_adapter=DatabasePreservation(ctx))
                finally:
                    start_services()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('status') in {'verified', 'preserved', 'unstarted_acknowledged'} else 1
    except (OSError, ValueError, PreservationError, RuntimeError) as error:
        print(f'보존 복구 중단: {type(error).__name__} — 원본과 사본을 유지합니다.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
