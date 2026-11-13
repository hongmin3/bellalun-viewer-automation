"""미완료 실행 보존을 조회하거나 명시 승인 후 복구한다."""
import argparse
import json
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.run_preservation import RunPreservation, PreservationError


def _resume_image_cleanup(args):
    from core.automation_health import completed_report_data
    from core.run_preservation import _check_path, _hash, _write_json
    from core.execution_session import start_services
    from core.dbreset import APP_SERVICES
    from core.wu_chain import result_from_dict
    from core.result import write_reports
    from run import Context
    session = RunPreservation.load(args.workspace, args.run_id)
    if (session.journal.get('state') != 'cleanup_required'
            and not session.journal.get('execution_finalization_pending')):
        raise ValueError('생성 이미지 정리 대기 상태인 실행만 재개할 수 있습니다.')
    locator = session.journal.get('normal_completion_before_cleanup') or {}
    if not isinstance(locator, dict):
        raise ValueError('정리 전 정상완주 증거의 형식이 올바르지 않습니다.')
    proof_path = _check_path(session.run_dir / 'cleanup-completion.json')
    command = locator.get('command')
    if (locator.get('run_id') != args.run_id or command not in {'run-regression', 'run-winupdate'}
            or not locator.get('report') or _check_path(locator['report']) != proof_path
            or not locator.get('sha256') or _hash(proof_path) != locator['sha256']):
        raise ValueError('정리 전 정상완주 증거의 위치·실행 번호·해시를 확인하지 못했습니다.')
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    if not completed_report_data(proof, command):
        raise ValueError('원래 실행의 전체 기본기능/WU 정상완주를 확인하지 못했습니다.')
    meta = proof.get('meta') or {}
    if meta.get('run_id') != args.run_id or meta.get('chain_completed') is not True:
        raise ValueError('원래 실행의 전체 기본기능/WU 정상완주를 확인하지 못했습니다.')
    Context(str(args.config))
    # 파일·DB는 이미 복원됐다. DB 복구와 제품 종료를 반복하지 않는다.
    services = start_services()
    if not isinstance(services, dict) or any(services.get(name) != 'RUNNING' for name in APP_SERVICES):
        raise ValueError('제품 서비스의 RUNNING 상태를 확인하지 못했습니다.')
    cleanup = session.cleanup_generated_images(normal_completion=True, services_verified=True)
    result = session.journal['result']
    result.update(image_cleanup=cleanup, services=services, normal_completion_before_cleanup=locator)
    _write_json(session.run_dir / 'restoration.json', result)
    for path in (args.workspace / 'Reports').glob('Result_*.json'):
        report = json.loads(_check_path(path).read_text(encoding='utf-8'))
        report_meta = report.get('meta') or {}
        if report_meta.get('run_id') != args.run_id:
            continue
        report_meta['restoration'] = result
        # 정리 재개로 원래 비정상 종료 기록을 정상 완료로 승격하지 않는다.
        rows = [result_from_dict(row) for row in report.get('results', [])]
        write_reports(rows, str(path.parent), path.stem[len('Result_'):], meta=report_meta)
    receipt = args.workspace / 'Runs' / args.run_id / 'run.json'
    if receipt.exists():
        record = json.loads(_check_path(receipt).read_text(encoding='utf-8'))
        if record.get('run_id') == args.run_id:
            record['restoration'] = result
            _write_json(receipt, record)
    if cleanup.get('status') in {'completed', 'skipped'} and result.get('status') == 'verified':
        session.finish_execution_finalization()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--apply', action='store_true', help='선택한 실행의 실제 제품/DB 복구 승인')
    parser.add_argument('--acknowledge-unstarted', action='store_true',
                        help='백업 실패 뒤 제품 시험이 시작되지 않았음을 사람이 확인')
    parser.add_argument('--resume-image-cleanup', action='store_true',
                        help='고정 정상완주 증거를 확인하고 생성 Image 정리만 재개(DB 재복원 안 함)')
    args = parser.parse_args(argv)
    try:
        if args.resume_image_cleanup and (not args.apply or not args.run_id or not args.config
                                           or args.acknowledge_unstarted):
            raise ValueError('정리 재개는 --apply --run-id --config가 필요하며 미시작 확인과 함께 쓸 수 없습니다.')
        if not args.apply:
            print(json.dumps({'pending': RunPreservation.pending(args.workspace)}, ensure_ascii=False))
            return 0
        if not args.run_id:
            raise ValueError('--apply는 --run-id로 복구 대상을 지정해야 합니다.')
        from bellalunauto.runtime import RunLock
        if args.resume_image_cleanup:
            with RunLock():
                result = _resume_image_cleanup(args)
        elif args.acknowledge_unstarted:
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
