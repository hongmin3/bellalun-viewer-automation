"""제품 설치 수명주기 inspect/plan/apply. 승인 프로필 없이는 설치하지 않는다."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import uuid

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import product_lifecycle as lifecycle
from core.run_preservation import RunPreservation, roots_from_config, _check_path


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _validate_output(path):
    root = Path(__file__).resolve().parents[1]
    destination = Path(path).resolve()
    if destination.name.lower() == 'config.json' or (
            destination.is_relative_to(root) and not destination.is_relative_to(root / 'work')):
        raise lifecycle.LifecycleError('저장소 안의 runtime 출력은 work 아래 새 파일만 허용합니다')
    _check_path(destination)
    if destination.exists() or not destination.parent.is_dir():
        raise lifecycle.LifecycleError('runtime 출력은 존재하는 상위 폴더의 새 파일이어야 합니다')
    return destination


def _write_output(path, payload):
    destination = _validate_output(path)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def _context(options, workspace=None):
    if not options.config:
        return None
    from run import Context
    context = Context(options.config)
    if workspace is not None:
        context.root = str(_check_path(workspace))
    return context


def _tc_verifier(options, context, receipt):
    if context is None:
        return None
    from core import snapshot
    from tests.install import lifecycle_verifier
    manifest = _read(receipt['manifest'])
    before = (_read(options.pre) if options.pre else
              ((manifest.get('db') or {}).get('metadata') or {}).get('snapshot'))
    def verify(record):
        after = snapshot.take(context.db) if record['action'] != 'uninstall' and before is not None else None
        return lifecycle_verifier(context, before, after)(record)
    return verify


def _finalizer(context, receipt):
    if context is None:
        return None
    from core import execution_session
    backup = _check_path(receipt['backup'])
    journal = _read(backup / 'journal.json')
    if (backup.name != receipt.get('run_id') or backup.parent.name != 'preservation'
            or journal.get('run_id') != receipt['run_id']
            or journal.get('state') != 'prepared' or not journal.get('backup_complete')
            or not isinstance(journal.get('restore_after'), bool)):
        raise lifecycle.LifecycleError('prepared 상태의 검증된 보존 receipt와 복원 선택이 필요합니다')
    workspace = backup.parent.parent
    context.root = str(workspace)
    adapter = execution_session.DatabasePreservation(context)
    restore_after = journal['restore_after']
    def finalize():
        try:
            execution_session.stop_product(context)
            return RunPreservation.recover(workspace, receipt['run_id'], db_adapter=adapter,
                                           restore_after=restore_after)
        finally:
            execution_session.start_services()
    return finalize


def _prepare(options):
    """명시 승인·잠금 안에서 자원 확인→실제 사전 사본→receipt 저장."""
    from core import execution_session
    from core.env_preflight import real_memory
    from core.resource_budget import plan_resources, GIB
    _validate_output(options.output)
    context = _context(options, options.workspace)
    roots = roots_from_config(context.cfg)
    adapter = execution_session.DatabasePreservation(context)
    settings = context.cfg.get('preservation') or {}
    reserve = settings.get('generation_bytes_per_root', 3 * GIB)
    db_bytes = adapter.estimate_bytes()
    reservations = {path: reserve for path in roots.values()}
    reservations[Path(context.cfg['data_dir']) / 'Backup' / 'Baseline'] = db_bytes * (2 if options.restore_after else 1)
    reservations[Path(context.root)] = settings.get('report_generation_bytes', GIB) + settings.get('evidence_generation_bytes', 3 * GIB)
    budget = plan_resources(roots, Path(context.root) / 'preservation',
        reservations, settings.get('headroom_bytes', 12 * GIB),
        memory_available_bytes=(real_memory() or {}).get('avail'),
        db_backup_bytes=db_bytes, restore_after=options.restore_after)
    if budget['blocked']:
        raise lifecycle.LifecycleError('백업·시험 예상량의 디스크/메모리 여유를 확인하지 못했습니다')
    if RunPreservation.pending(context.root):
        raise lifecycle.LifecycleError('미완료 보존 실행을 먼저 명시적으로 복구해야 합니다')
    run_id = datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    preservation = RunPreservation(context.root, run_id, roots, restore_after=options.restore_after,
                                   db_adapter=adapter)
    try:
        execution_session.stop_product(context)
        result = preservation.prepare()
    finally:
        execution_session.start_services()
    _write_output(options.output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='제품 설치/Upgrade/Uninstall을 읽기 조사·계획·명시 승인 실행으로 나눕니다. 무인 인자를 추측하지 않습니다.')
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='패키지 또는 프로필을 읽기 조사(실행 안 함)')
    inspect.add_argument('--package', action='append', default=[], type=Path)
    inspect.add_argument('--profile', type=Path)
    plan = commands.add_parser('plan', help='검증된 프로필의 파일·argv 해시와 복구 범위를 고정')
    plan.add_argument('--profile', required=True, type=Path)
    plan.add_argument('--output', type=Path, help='새 runtime 계획 JSON')
    prepare = commands.add_parser('prepare', help='명시 승인한 DB/파일 사전 사본과 receipt 생성')
    prepare.add_argument('--config', required=True, type=Path)
    prepare.add_argument('--workspace', required=True, type=Path, help='보존 사본을 둘 작업 폴더')
    prepare.add_argument('--output', required=True, type=Path, help='새 runtime receipt JSON')
    prepare.add_argument('--approved', action='store_true', help='제품 중지·DB/파일 백업과 선택한 복구 정책 명시 승인')
    restoration = prepare.add_mutually_exclusive_group(required=True)
    restoration.add_argument('--restore-after', dest='restore_after', action='store_true')
    restoration.add_argument('--no-restore-after', dest='restore_after', action='store_false')
    apply = commands.add_parser('apply', help='승인된 계획과 검증 백업이 있을 때만 한 번 실행')
    apply.add_argument('--plan', required=True, type=Path)
    apply.add_argument('--backup-receipt', required=True, type=Path)
    apply.add_argument('--record', required=True, type=Path)
    apply.add_argument('--approved', action='store_true', help='해당 계획의 실제 제품 변경·복구 범위에 대한 명시 승인')
    resume = commands.add_parser('resume', help='재부팅 뒤 후속 TC 검증만 재개(설치기 재실행 안 함)')
    resume.add_argument('--record', required=True, type=Path)
    for subcommand in (apply, resume):
        subcommand.add_argument('--config', type=Path, help='Install_07/08/09 후속 판정용 로컬 설정(미지정 시 검증 미완료)')
        subcommand.add_argument('--pre', type=Path, help='실제 설치 전 수집한 snapshot. install/upgrade 후속 판정에 필요')
    options = parser.parse_args(argv)
    try:
        if options.command == 'inspect':
            result = {'packages': [lifecycle.inspect_package(path) for path in options.package]}
            result['profile'] = lifecycle.inspect_profile(_read(options.profile)) if options.profile else {
                'status': 'blocked', 'reason': '검증된 무인 인자 프로필이 없습니다. 설치기를 실행하지 않습니다.'}
        elif options.command == 'plan':
            result = lifecycle.build_plan(_read(options.profile))
            if options.output:
                _write_output(options.output, result)
        elif options.command == 'prepare':
            if not options.approved:
                raise lifecycle.LifecycleError('제품 중지·사전 백업에는 --approved 명시 승인이 필요합니다')
            from bellalunauto.runtime import RunLock
            with RunLock():
                result = _prepare(options)
        elif options.command == 'apply':
            if not options.approved:
                raise lifecycle.LifecycleError('이 계획에 대한 --approved 명시 승인이 필요합니다')
            from bellalunauto.runtime import RunLock
            with RunLock():
                receipt = _read(options.backup_receipt)
                context = _context(options)
                result = lifecycle.apply_plan(_read(options.plan), approved=True,
                           backup_receipt=receipt, record_path=options.record,
                           verify_after=_tc_verifier(options, context, receipt),
                           finalize=_finalizer(context, receipt))
        else:
            from bellalunauto.runtime import RunLock
            with RunLock():
                receipt = _read(options.record)['backup_receipt']
                context = _context(options)
                verifier = _tc_verifier(options, context, receipt)
                if verifier is None:
                    raise lifecycle.LifecycleError('재부팅 후속 판정을 위한 --config와 실제 snapshot이 필요합니다')
                result = lifecycle.resume_after_reboot(options.record, verify_after=verifier,
                                                       finalize=_finalizer(context, receipt))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if options.command in {'apply', 'resume'}:
            if result['status'] == 'reboot_required':
                return 3
            return 0 if result['status'] == 'completed' else 1
        return 0
    except (lifecycle.LifecycleError, OSError, ValueError, KeyError, RuntimeError) as error:
        print(f'제품 수명주기 차단: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
