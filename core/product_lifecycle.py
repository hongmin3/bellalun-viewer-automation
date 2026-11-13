"""명시 승인·고정 package/argv·검증 백업을 요구하는 제품 수명주기 실행기.

무인 인자를 생성하거나 등록된 UninstallString을 실행하지 않는다. 호출자가
검증한 프로필만 사용하며 reboot_required 이후에는 설치기를 다시 실행하지 않는다.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from core.run_preservation import snapshot, _check_path

ACTIONS = {'install', 'upgrade', 'uninstall'}


class LifecycleError(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def _file_hash(path):
    try:
        path = _check_path(path)
        with path.open('rb') as source:
            return hashlib.file_digest(source, 'sha256').hexdigest()
    except (OSError, RuntimeError) as error:
        raise LifecycleError('프로필 파일을 읽을 수 없습니다') from error


def _pinned_file(item, label):
    if not isinstance(item, dict) or not isinstance(item.get('path'), str):
        raise LifecycleError(f'{label} 파일 프로필이 없습니다')
    path = Path(item['path'])
    if not path.is_absolute() or not re.fullmatch(r'[a-fA-F0-9]{64}', str(item.get('sha256', ''))):
        raise LifecycleError(f'{label}의 절대 경로와 SHA-256 해시가 필요합니다')
    if _file_hash(path).lower() != item['sha256'].lower():
        raise LifecycleError(f'{label} 해시가 승인 프로필과 다릅니다')
    return path


def inspect_package(path):
    """서명·내용·설정에 대한 읽기 조사. 어떤 실행 파일도 기동하지 않는다."""
    path = _check_path(path)
    try:
        with path.open('rb') as source:
            head = source.read(2 * 1024 * 1024)
        kind = 'unknown'
        if head.startswith(bytes.fromhex('d0cf11e0a1b11ae1')) and path.suffix.lower() == '.msi':
            kind = 'msi'
        elif head.startswith(b'MZ'):
            markers = (b'InstallShield', 'InstallShield'.encode('utf-16le'), b'ISSetupStream')
            kind = 'installshield' if any(marker in head for marker in markers) else 'executable'
        elif path.suffix.lower() == '.py':
            # 검증된 wrapper 및 합성 실행기에만 사용한다. 설치 패키지라고 추정하지 않는다.
            kind = 'script'
        return {'path': str(path), 'sha256': _file_hash(path), 'size': path.stat().st_size,
                'kind': kind, 'unattended_verified': False}
    except OSError as error:
        raise LifecycleError('패키지 파일을 읽을 수 없습니다') from error


def inspect_profile(profile):
    try:
        plan = build_plan(profile)
        return {'status': 'ready', 'plan_id': plan['plan_id'], 'package': plan['package'],
                'requires_explicit_apply_approval': True}
    except (LifecycleError, TypeError, ValueError) as error:
        return {'status': 'blocked', 'reason': str(error)}


def build_plan(profile):
    """증거로 검증한 정확한 argv와 package/launcher/evidence 해시를 고정한다."""
    if not isinstance(profile, dict) or profile.get('schema') != 1 or profile.get('action') not in ACTIONS:
        raise LifecycleError('schema=1 및 install/upgrade/uninstall 프로필이 필요합니다')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', str(profile.get('profile_id', ''))):
        raise LifecycleError('프로필 식별자가 없습니다')
    unattended = profile.get('unattended') or {}
    if unattended.get('verified') is not True or not unattended.get('reviewed_by'):
        raise LifecycleError('검증된 무인 인자와 검토자·증거 프로필이 필요합니다. 인자를 추측하지 않습니다')
    package_path = _pinned_file(profile.get('package'), '패키지')
    _pinned_file(unattended.get('evidence'), '무인 인자 검증 증거')
    package = inspect_package(package_path)
    if package['kind'] == 'unknown' or profile['package'].get('kind') != package['kind']:
        raise LifecycleError('패키지 방식이 프로필과 다르거나 확인되지 않았습니다')
    command = profile.get('command') or {}
    argv = command.get('argv')
    if (not isinstance(argv, list) or not argv
            or any(not isinstance(arg, str) or '\0' in arg for arg in argv)):
        raise LifecycleError('shell 없이 실행할 문자열 argv 배열이 필요합니다')
    _pinned_file({'path': argv[0], 'sha256': command.get('launcher_sha256')}, '실행기')
    if Path(argv[0]).name.lower() in {'cmd.exe', 'powershell.exe', 'pwsh.exe', 'sh', 'bash'}:
        raise LifecycleError('shell 실행기는 제품 프로필로 허용하지 않습니다')
    if str(package_path) not in argv and profile['action'] != 'uninstall':
        raise LifecycleError('설치/Upgrade argv가 해시 고정 패키지를 직접 지정하지 않습니다')
    for item in profile.get('artifacts', []):
        _pinned_file(item, '추가 실행 자료')
    recovery = profile.get('recovery') or {}
    if (not isinstance(recovery.get('steps'), list) or not recovery['steps']
            or not all(isinstance(step, str) and step.strip() for step in recovery['steps'])
            or not isinstance(recovery.get('required_roots'), list) or not recovery['required_roots']
            or not isinstance(recovery.get('database_required'), bool)):
        raise LifecycleError('복구 절차와 사전 보존 범위·DB 보존 여부가 필요합니다')
    for key, default in (('success_codes', [0]), ('reboot_codes', [3010, 1641])):
        codes = profile.get(key, default)
        if not isinstance(codes, list) or not codes or not all(type(code) is int for code in codes):
            raise LifecycleError('종료 코드 프로필이 잘못되었습니다')
    if set(profile.get('success_codes', [0])) & set(profile.get('reboot_codes', [3010, 1641])):
        raise LifecycleError('성공과 재부팅 종료 코드가 겹칩니다')
    timeout = profile.get('timeout_sec', 1800)
    if type(timeout) not in (float, int) or not 0 < timeout <= 14400:
        raise LifecycleError('설치 시간 상한은 0초 초과 4시간 이하여야 합니다')
    plan = {'schema': 1, 'action': profile['action'], 'profile': deepcopy(profile),
            'package': package, 'argv_sha256': _digest(argv),
            'recovery': deepcopy(recovery)}
    plan['plan_id'] = _digest(plan)
    return plan


def verify_preservation_receipt(receipt, recovery):
    """RunPreservation.prepare receipt의 사본·DB 파일을 재검증한다. 복원하지 않는다."""
    try:
        if not isinstance(receipt, dict) or receipt.get('status') != 'prepared' or not receipt.get('run_id'):
            return False
        backup = _check_path(receipt['backup'])
        manifest_path = _check_path(receipt['manifest'])
        if manifest_path != backup / 'manifest.json':
            return False
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        journal = json.loads(_check_path(backup / 'journal.json').read_text(encoding='utf-8'))
        if (manifest.get('run_id') != receipt['run_id'] or journal.get('run_id') != receipt['run_id']
                or journal.get('state') != 'prepared'):
            return False
        roots = manifest.get('roots') or {}
        if not set(recovery['required_roots']) <= set(roots):
            return False
        if not all(snapshot(backup / 'before' / name) == expected for name, expected in roots.items()):
            return False
        database = manifest.get('db')
        if recovery['database_required'] and not database:
            return False
        if database and (not (database.get('metadata') or {}).get('scope')
                         or snapshot(backup / 'database') != database.get('files')):
            return False
        return True
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return False


def _write_record(path, record, *, create=False):
    path = _check_path(path)
    if not path.parent.is_dir():
        raise LifecycleError('실행 기록의 상위 폴더를 먼저 준비하십시오')
    record['updated'] = _now()
    if create:
        try:
            with path.open('x', encoding='utf-8') as stream:
                json.dump(record, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise LifecycleError('기존 실행 기록을 덮어쓰거나 설치기를 반복 실행하지 않습니다') from error
        return
    descriptor, temporary = tempfile.mkstemp(prefix='lifecycle_', suffix='.json', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def system_boot_identity():
    """재부팅 전/후 구별용 읽기 조회. 확인 실패 시 재개를 허용하지 않는다."""
    if os.name != 'nt':
        try:
            return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        except OSError:
            return None
    try:
        command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                   '(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString("o")']
        return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, check=True, timeout=20,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _complete_record(record, path, verify_after, finalize, quiesce=None):
    if record['status'] in {'timed_out', 'interrupted'} and finalize is not None:
        try:
            stopped = quiesce(deepcopy(record)) is True if quiesce is not None else False
        except Exception:
            stopped = False
        if not stopped:
            record.update(process_outcome=record['status'], status='recovery_required',
                          restoration={'status': 'deferred',
                                       'reason': '설치기/자식 프로세스의 완전 중지가 확인되지 않아 복원을 보류합니다'})
            _write_record(path, record)
            return record
    if record['status'] == 'process_completed':
        if verify_after is None:
            record['status'] = 'verification_required'
        else:
            try:
                record['post_verification'] = verify_after(deepcopy(record))
                if isinstance(record['post_verification'], dict) and 'product_verdict' in record['post_verification']:
                    record['product_verdict'] = record['post_verification']['product_verdict']
                if not isinstance(record['post_verification'], dict) or record['post_verification'].get('status') != 'verified':
                    record['status'] = 'verification_required'
                else:
                    record['status'] = 'finalizing'
            except Exception as error:
                record.update(status='verification_failed', error_type=type(error).__name__)
    _write_record(path, record)
    if finalize is not None:
        try:
            record['restoration'] = finalize()
            if (not isinstance(record['restoration'], dict)
                    or record['restoration'].get('status') not in {'verified', 'preserved', 'retained'}):
                record['status'] = 'recovery_required'
            elif record['status'] == 'finalizing':
                record['status'] = 'completed'
        except Exception as error:
            record.update(status='recovery_required', recovery_error_type=type(error).__name__)
    else:
        record['restoration'] = {'status': 'pending', 'next_action': '보존 실행의 finalize callback으로 복구 경계를 마무리하십시오'}
        if record['status'] == 'finalizing':
            record['status'] = 'finalization_required'
    record['completed'] = _now()
    _write_record(path, record)
    return record


def apply_plan(plan, *, approved=False, backup_receipt, record_path, verify_backup=None,
               verify_after=None, finalize=None, runner=None, boot_id=None, quiesce=None):
    """프로필·백업 재검증 뒤 shell=False로 정확히 한 번 실행한다.

    callback 계약: verify_backup(receipt, recovery)->bool,
    verify_after(record)->{'status': 'verified', ...}, finalize()->복원 결과.
    timeout/interrupt 뒤 복원에는 quiesce(record)->True 중지 확인이 필요하다.
    RunPreservation.prepare() 결과를 backup_receipt로, finalize 메서드를
    finalize callback으로 넘긴다. 재부팅 대기 중에는 finalize하지 않는다.
    """
    if approved is not True:
        raise LifecycleError('이 구체적인 설치 계획에 대한 명시적 실행 승인이 필요합니다')
    current = build_plan(plan.get('profile'))
    if current != plan:
        raise LifecycleError('실행 계획 또는 파일 해시가 승인 시점과 다릅니다')
    verifier = verify_backup or verify_preservation_receipt
    if not verifier(backup_receipt, plan['recovery']):
        raise LifecycleError('백업 receipt·사전 사본·복구 계획 검증에 실패했습니다')
    record = {'schema': 1, 'plan': deepcopy(plan), 'plan_id': plan['plan_id'],
              'action': plan['action'], 'run_id': backup_receipt['run_id'],
              'backup_receipt': deepcopy(backup_receipt), 'status': 'launching',
              'approved_at': _now(), 'started': _now(),
              'boot_id_before': boot_id if boot_id is not None else system_boot_identity()}
    _write_record(record_path, record, create=True)
    try:
        # 사본 검증·boot 조회 중 바뀐 패키지도 기동 직전에 다시 거부한다.
        if build_plan(plan['profile']) != plan:
            raise LifecycleError('기동 직전 패키지 해시 또는 실행 계획이 달라졌습니다')
        outcome = (runner or subprocess.run)(plan['profile']['command']['argv'], shell=False,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=plan['profile'].get('timeout_sec', 1800), check=False,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        record['returncode'] = outcome.returncode
        if outcome.returncode in plan['profile'].get('reboot_codes', [3010, 1641]):
            record['status'] = 'reboot_required'
            record['next_action'] = '설치기를 다시 실행하지 말고 재부팅 후 같은 기록으로 후속 검증·복원을 재개하십시오'
            _write_record(record_path, record)
            return record
        record['status'] = ('process_completed' if outcome.returncode in
                            plan['profile'].get('success_codes', [0]) else 'process_failed')
    except subprocess.TimeoutExpired:
        record.update(status='timed_out', error_type='TimeoutExpired')
    except (OSError, subprocess.SubprocessError) as error:
        record.update(status='launch_failed', error_type=type(error).__name__)
    except BaseException as error:
        record.update(status='interrupted', error_type=type(error).__name__)
        _complete_record(record, record_path, None, finalize, quiesce)
        raise
    return _complete_record(record, record_path, verify_after, finalize, quiesce)


def resume_after_reboot(record_path, *, boot_id=None, verify_after, finalize=None):
    """재부팅 뒤 후속 검증·복원만 재개한다. 설치기 재호출 경로가 없다."""
    try:
        record = json.loads(_check_path(record_path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise LifecycleError('재부팅 재개 기록을 읽을 수 없습니다') from error
    if record.get('status') != 'reboot_required':
        raise LifecycleError('재부팅 대기 상태의 실행만 재개할 수 있습니다')
    current_boot = boot_id if boot_id is not None else system_boot_identity()
    if not current_boot or not record.get('boot_id_before') or current_boot == record['boot_id_before']:
        raise LifecycleError('실제 재부팅 전후를 확인할 수 없습니다')
    plan = deepcopy(record['plan'])
    fingerprint = plan.pop('plan_id', None)
    if fingerprint != _digest(plan) or fingerprint != record.get('plan_id'):
        raise LifecycleError('재개할 실행 계획의 해시가 다릅니다')
    if not verify_preservation_receipt(record['backup_receipt'], record['plan']['recovery']):
        raise LifecycleError('재부팅 뒤 백업 receipt를 검증하지 못했습니다')
    record.update(status='process_completed', boot_id_after=current_boot)
    return _complete_record(record, record_path, verify_after, finalize)
