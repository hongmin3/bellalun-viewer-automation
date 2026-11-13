"""GUI/CLI 공통의 실행 전 보존과 실행 후 선택적 복원 경계."""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

from core.run_preservation import RunPreservation, roots_from_config
from core.resource_budget import plan_resources, GIB


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def stop_product(ctx):
    from core import dbreset
    dbreset.stop_app_processes()


def start_services():
    from core import dbreset
    states = dbreset.start_app_services()
    if not isinstance(states, dict) or any(states.get(name) != 'RUNNING' for name in dbreset.APP_SERVICES):
        raise RuntimeError('제품 서비스가 RUNNING으로 복구되지 않았습니다.')
    return states


def restoration_generation(workspace):
    """별도 세대 파일 대신 완료된 복원 journal 자체를 재개 신원으로 쓴다."""
    from core.run_preservation import _check_path
    parent = _check_path(Path(workspace) / 'preservation')
    generations = []
    if parent.exists():
        for folder in sorted(parent.iterdir()):
            journal_path = _check_path(folder / 'journal.json')
            journal = json.loads(journal_path.read_text(encoding='utf-8'))
            if journal.get('state') == 'verified':
                generations.append({'run_id': journal['run_id'], 'journal_sha256': _sha(journal_path)})
    return generations


class DatabasePreservation:
    def __init__(self, ctx):
        self.ctx = ctx

    def estimate_bytes(self):
        from core.dbreset import DATABASES, _quote
        names = ','.join("N'" + _quote(name) + "'" for name in DATABASES)
        value = self.ctx.db.scalar('master',
            f'SELECT SUM(CAST(size AS bigint))*8192 FROM sys.master_files '
            f'WHERE DB_NAME(database_id) IN ({names})')
        if value is None or int(value) <= 0:
            raise ValueError('DB 사전 크기를 확인하지 못했습니다.')
        return int(value)

    def _snapshot(self):
        from core import snapshot
        value = json.loads(json.dumps(snapshot.take(self.ctx.db), default=str))
        def has_error(item):
            if isinstance(item, dict):
                return '_error' in item or any(has_error(v) for v in item.values())
            return isinstance(item, list) and any(has_error(v) for v in item)
        if has_error(value) or not value.get('_sections'):
            raise ValueError('DB 비교 범위를 조회하지 못했습니다. 복원 확인을 할 수 없습니다.')
        return value

    def backup(self, destination):
        from core import dbreset, snapshot
        stage = Path(dbreset.staging_dir(self.ctx)) / ('preserve-' + uuid.uuid4().hex)
        stage.mkdir()
        before = self._snapshot()
        files = {}
        for name in dbreset.DATABASES:
            path = stage / (name + '.bak')
            self.ctx.db.query('master', dbreset._backup_sql(name, str(path)))
            self.ctx.db.query('master', f"RESTORE VERIFYONLY FROM DISK=N'{dbreset._quote(str(path))}'")
            shutil.copy2(path, destination / path.name)
            files[name] = _sha(destination / path.name)
            if files[name] != _sha(path):
                raise OSError('DB 사전 사본 해시가 일치하지 않습니다.')
        return {'scope': 'core.snapshot 선언 테이블/열 및 DB BACKUP VERIFYONLY',
                'snapshot': before, 'files': files}

    def verify_backup(self, destination, metadata):
        return all(_sha(destination / (name + '.bak')) == digest
                   for name, digest in metadata['files'].items())

    def restore(self, destination, metadata):
        from core import dbreset
        stage = Path(dbreset.staging_dir(self.ctx)) / ('restore-' + uuid.uuid4().hex)
        stage.mkdir()
        for name in dbreset.DATABASES:
            source = destination / (name + '.bak')
            path = stage / source.name
            shutil.copy2(source, path)
            if _sha(path) != metadata['files'][name]:
                raise OSError('DB 복원 사본 무결성 실패')
            clauses = dbreset._move_clauses(self.ctx, name, str(path))
            db = dbreset._bracket(name)
            self.ctx.db.query('master', f'ALTER DATABASE {db} SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
            try:
                self.ctx.db.query('master', dbreset._restore_sql(name, str(path), clauses))
            finally:
                self.ctx.db.query('master', f'ALTER DATABASE {db} SET MULTI_USER')

    def verify_restored(self, destination, metadata):
        from core import snapshot
        return not snapshot.diff(metadata['snapshot'], self._snapshot())


@contextmanager
def execution_session(ctx, action):
    """제품 동작 전에 준비를 끝내고, 모든 종료 경로에서 선택한 복원을 수행한다."""
    from core.env_preflight import real_memory
    run_id = os.environ.get('BELLALUN_QA_RUN')
    plan = {}
    if run_id:
        import re
        if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{8}', run_id):
            raise ValueError('실행 번호 형식이 올바르지 않습니다.')
        path = Path(ctx.root) / 'Runs' / run_id / 'run.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        plan = record.get('plan') or {}
        current_plan = getattr(ctx, 'execution_plan', {})
        if plan.get('plan_id') and plan['plan_id'] != current_plan.get('plan_id'):
            raise ValueError('동의 후 실행 계획이 변경되었습니다. 다시 확인하고 시작하세요.')
    choice = getattr(ctx, 'preservation_choice', plan.get('restore_after'))
    if not isinstance(choice, bool):
        raise ValueError('이번 실행의 원상복원 여부를 선택하세요: --restore-after 또는 --no-restore-after')
    run_id = run_id or datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    roots = roots_from_config(ctx.cfg)
    if action in {'run-winupdate', 'run-wu09'}:
        from core.usb_media import find_usb_drive
        usb = find_usb_drive()
        if not usb:
            raise ValueError('시험용 USB가 없어 실행을 시작하지 않습니다.')
        roots = roots_from_config(ctx.cfg, usb_drive=usb)
    adapter = DatabasePreservation(ctx)
    options = ctx.cfg.get('preservation') or {}
    # 12 GiB는 보수적 운영 여유 제안이며 제품 사양 상수라고 취급하지 않는다.
    headroom = options.get('headroom_bytes', 12 * GIB)
    reserve = options.get('generation_bytes_per_root', 3 * GIB)
    memory = real_memory() or {}
    db_bytes = adapter.estimate_bytes()
    reserves = {path: reserve for path in roots.values()}
    # SQL이 쓰는 원본 staging과 복원 staging은 작업 폴더와 다른 볼륨일 수 있다.
    reserves[Path(ctx.cfg['data_dir']) / 'Backup' / 'Baseline'] = db_bytes * (2 if choice else 1)
    reserves[Path(ctx.root)] = (options.get('report_generation_bytes', GIB)
                                + options.get('evidence_generation_bytes', 3 * GIB))
    budget = plan_resources(roots, Path(ctx.root) / 'preservation',
                            reserves, headroom,
                            memory_available_bytes=memory.get('avail'),
                            db_backup_bytes=db_bytes, restore_after=choice)
    ctx.resource_budget = budget
    if budget['blocked']:
        raise ValueError('보존/시험 예상량을 위한 디스크·USB·메모리가 부족하거나 조회되지 않았습니다.')
    if RunPreservation.pending(ctx.root):
        raise ValueError('미완료 보존 기록을 복구한 뒤 새 시험을 시작하세요.')
    session = RunPreservation(ctx.root, run_id, roots, restore_after=choice, db_adapter=adapter)
    generation = restoration_generation(ctx.root)
    from core.source_identity import execution_fingerprint
    ctx.execution_fingerprint = execution_fingerprint(
        getattr(ctx, 'execution_plan', {}).get('plan_id'), generation)
    ctx.run_id = run_id
    ctx.preservation_roots = roots
    stop_product(ctx)
    prepared = False
    try:
        ctx.preservation = session.prepare()
        prepared = True
        start_services()
        yield session
    finally:
        ctx.restoration = {'status': 'error', 'run_id': run_id,
                           'note': '복원/서비스 마무리를 아직 확인하지 못했습니다.'}
        try:
            if prepared:
                stop_product(ctx)
                ctx.restoration = session.finalize()
        finally:
            try:
                ctx.restoration['services'] = start_services()
            except Exception as error:
                ctx.restoration['status'] = 'error'
                ctx.restoration['service_error'] = type(error).__name__
                raise
            finally:
                if prepared:
                    result_path = session.run_dir / 'restoration.json'
                    try:
                        result_path.write_text(json.dumps(ctx.restoration, ensure_ascii=False, indent=2), encoding='utf-8')
                    except OSError:
                        ctx.restoration['status'] = 'error'
                        raise
        if prepared and ctx.restoration.get('status') not in {'verified', 'preserved'}:
            raise RuntimeError('원상복원 검증에 실패했습니다. 보존 기록과 원본을 유지했습니다.')
