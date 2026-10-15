"""GUI/CLI 공통 진입점과 컴파일 후에도 동작하는 외부 감시."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import ctypes
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit

from bellalunauto import __version__
from bellalunauto.resources import bundled_config
from bellalunauto.runtime import (AlreadyRunning, RunLock, child_command,
                                 load_config, resolve_layout)


def redact(value):
    if isinstance(value, dict):
        return {key: ('***' if any(word in key.lower() for word in
                                 ('password', 'token', 'secret', 'api_key')) else redact(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def requires_product_control(command):
    return (command.startswith('run-') or command.startswith('setup-') or command in
            {'reset-environment', 'snapshot-baseline', 'verify-install-package', 'probe-preset3d'})


def historical_conversion(arguments):
    return (bool(arguments) and arguments[0] == 'run-winupdate' and
            any(value.startswith('--') and len(value.partition('=')[0]) > 2
                and '--from-regression'.startswith(value.partition('=')[0])
                for value in arguments))


@contextmanager
def legacy_product_lock(arguments):
    """기존 run.py 직접 실행도 설치판과 같은 PC 잠금을 지킨다."""
    prefix = argparse.ArgumentParser(add_help=False)
    prefix.add_argument('--config')
    _, remaining = prefix.parse_known_args(arguments)
    control = (bool(remaining) and requires_product_control(remaining[0]) and
               not historical_conversion(remaining) and
               not any(value in ('-h', '--help') for value in remaining))
    owner = os.environ.get('BELLALUN_PRODUCT_LOCK_OWNER')
    lock = RunLock() if control and owner != str(os.getppid()) else nullcontext()
    with lock:
        yield


def worker_command(layout, arguments, stop_file=None):
    if '--worker' in arguments:
        raise ValueError('worker 모드는 다시 worker를 만들 수 없습니다.')
    options = ['--workspace', str(layout.workspace), '--config', str(layout.config_path)]
    if stop_file:
        options += ['--stop-file', str(stop_file)]
    return child_command(options + ['--worker'] + list(arguments))


def completed_report(reports_dir, command, since):
    from core import automation_health as health
    if command == 'run-regression':
        return health.latest_full_regression(str(reports_dir), since=since)
    if command != 'run-winupdate':
        return None
    expected = {f'TC_WindowsUpdate_{i:02}' for i in range(1, 14)}
    candidates = sorted(Path(reports_dir).glob('Result_WindowsUpdate_*.json'),
                        key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        if path.stat().st_mtime < since:
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        meta = data.get('meta') or {}
        if meta.get('execution_mode') != 'live' or meta.get('chain_completed') is not True:
            continue
        rows = data.get('results', [])
        if not expected <= {row.get('tc_id') for row in rows}:
            continue
        verdicts = {}
        for row in rows:
            verdict = row.get('verdict', 'UNKNOWN')
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
        return {'path': str(path), 'verdicts': verdicts, 'tc_count': len(rows)}
    return None


def diagnostics(layout, check_connections=True):
    """조회만 수행한다. 화면 해상도·서비스·DB·설정을 바꾸지 않는다."""
    items = []

    def add(name, ok, detail, fix):
        items.append({'name': name, 'ok': bool(ok), 'detail': str(detail), 'fix': fix})

    add('설정 파일', layout.config_path.is_file(), layout.config_path,
        '실행 화면의 PC별 설정에서 경로와 시험 계정을 저장하세요.')
    try:
        config = bundled_config(load_config(layout), layout.resource_dir)
    except (OSError, ValueError) as exc:
        add('설정 읽기', False, type(exc).__name__, '설정 파일의 JSON 형식과 접근 권한을 확인하세요.')
        config = {}
    add('실행 자료', (layout.resource_dir/'automation_scope.json').is_file(), layout.resource_dir,
        '승인된 내부 자료가 포함된 설치 패키지를 다시 설치하세요.')
    def section(value):
        return value if isinstance(value, dict) else {}
    viewer, xipl = section(config.get('viewer')), section(config.get('xipl'))
    paths = [('Viewer', viewer.get('exe')),
             ('BellalunData', config.get('data_dir')),
             ('XIPL Studio', xipl.get('studio_exe')),
             ('XIPL Parameter', xipl.get('parameter_dir')),
             ('Tesseract OCR', xipl.get('tesseract_exe')),
             ('기본기능 체크리스트', config.get('checklist_xlsx')),
             ('Windows Update 체크리스트', config.get('winupdate_checklist_xlsx')),
             ('승인 Baseline', config.get('baseline_dir')),
             ('근거 문서', config.get('knowledge_dir'))]
    for name, value in paths:
        add(name, bool(value) and Path(value).exists(), value or '미설정',
            'PC별 설정에서 설치/승인 자료의 실제 위치를 선택하세요.')
    if os.name == 'nt':
        from core import display, sysinfo
        add('화면 해상도', display.screen_size() == (1920, 1080), display.screen_size(),
            'Windows 디스플레이에서 주 모니터를 1920×1080으로 설정하세요.')
        add('Windows 배율', display.system_dpi() == 96, f'{display.system_dpi()} DPI',
            'Windows 배율을 100%로 설정하세요.')
        add('관리자 권한', sysinfo.is_elevated(), sysinfo.is_elevated(),
            '시험 실행 시 나타나는 UAC 요청을 승인하세요.')
        if check_connections:
            from core.db import BellalunDb
            from core import preflight
            service_name = config.get('sql_service_name', 'MSSQL$BELLALUN')
            service = sysinfo.service_state(service_name)
            add('SQL Server 서비스', bool(service) and service.get('status') == 'Running',
                service_name, '시험 PC의 SQL Server 인스턴스와 서비스를 확인하세요.')
            try:
                connected = BellalunDb(config.get('sql_server', r'.\BELLALUN')).ping()
            except Exception:
                connected = False
            add('시험 DB 접속', connected, config.get('sql_server', '미설정'),
                'SQL Server 인스턴스·Windows 인증·승인된 시험 DB를 확인하세요.')
            xipl = preflight.check_xipl()
            add('XIPL 영상 처리', xipl['ok'], xipl['detail'],
                '제품 설치와 XIPL.SERVER의 9784 포트 수신 상태를 확인하세요.')
    if check_connections:
        dicom = section(config.get('dicom'))
        for name, raw in [('MWL 서버', dicom.get('mwl_server_url')),
                          ('Print 서버', dicom.get('print_server_url')),
                          ('Storage 서버', section(dicom.get('storage_scp')).get('api_url'))]:
            try:
                parsed = urlsplit(raw or '')
                if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                    raise ValueError('미설정')
                with socket.create_connection((parsed.hostname, parsed.port or
                                               (443 if parsed.scheme == 'https' else 80)), timeout=3):
                    available = True
            except (OSError, ValueError):
                available = False
            add(name, available, '연결 가능' if available else '미설정 또는 연결 실패',
                'PC별 설정의 서버 주소·포트와 시험망 연결을 확인하세요.')
    return items


def _print_diagnostics(layout):
    rows = diagnostics(layout)
    print(f'BellalunAuto {__version__} 실행 환경 점검 (조회 전용)')
    for row in rows:
        print(f"[{'PASS' if row['ok'] else 'FAIL'}] {row['name']}: {row['detail']}")
        if not row['ok']:
            print(f"  해결 방법: {row['fix']}")
    return 0 if all(row['ok'] for row in rows) else 1


def _engine(layout, arguments):
    # Worker launch carries these absolute paths even across another UAC account.
    os.environ['BELLALUN_WORKSPACE'] = str(layout.workspace)
    os.environ['BELLALUN_RESOURCE_DIR'] = str(layout.resource_dir)
    os.environ['BELLALUN_LAUNCH_COMMAND'] = subprocess.list2cmdline(child_command(
        ['--workspace', str(layout.workspace), '--config', str(layout.config_path)] + list(arguments)))
    import run
    previous = sys.argv
    try:
        sys.argv = [sys.argv[0], '--config', str(layout.config_path)] + list(arguments)
        return run.main()
    finally:
        sys.argv = previous


def _stop_process_tree(process):
    if process.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def validate_log_path(layout, log_path):
    path = Path(log_path).resolve()
    if not path.is_relative_to((layout.workspace/'Log').resolve()):
        raise ValueError('승격 실행 로그는 선택한 작업 폴더의 Log 안에 있어야 합니다.')
    return path


def relay_log(log_path, position=0, output=None, final=False):
    """승격측이 비공개 처리한 UTF-8 로그를 원래 GUI 파이프로 전달한다."""
    path = Path(log_path)
    if not path.exists():
        return position
    with path.open('rb') as source:
        source.seek(position)
        data = source.read()
    length = len(data) if final else data.rfind(b'\n') + 1
    if length:
        target = sys.stdout if output is None else output
        if target is not None:
            target.write(data[:length].decode('utf-8', errors='replace'))
            target.flush()
    return position + length


def wait_worker_ready(path, parent, timeout=15):
    """제품 모듈을 읽기 전에 감시 프로세스의 Job 배정 완료를 기다린다."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            if Path(path).read_text(encoding='utf-8') == parent:
                return
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError('외부 감시 프로세스의 자식 보호 준비를 확인하지 못했습니다.')
        time.sleep(.05)


def run_guarded(layout, arguments, stop_file=None):
    from core import automation_health as health
    from core.ui import foreground_unlocked, taskbar_autohidden
    from bellalunauto.processes import WindowsJob
    command = arguments[0]
    started = time.time()
    child = None
    with RunLock(), foreground_unlocked(), taskbar_autohidden(), WindowsJob() as job:
        layout.workspace.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        ready_path = layout.workspace/'work'/f'worker-ready-{uuid.uuid4().hex}.txt'
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        environment.update(BELLALUN_EXTERNAL_GUARD='1', BELLALUN_AUTO_PARENT=str(os.getpid()),
                           BELLALUN_PRODUCT_LOCK_OWNER=str(os.getpid()),
                           BELLALUN_AUTO_READY=str(ready_path),
                           PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
        try:
            from bellalunauto.gui import secret_redactor
            scrub = secret_redactor(load_config(layout))
            child = subprocess.Popen(worker_command(layout, arguments, stop_file),
                                     cwd=layout.workspace, env=environment,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding='utf-8', errors='replace', bufsize=1)
            job.assign(child)
            ready_path.write_text(str(os.getpid()), encoding='utf-8')

            def forward():
                for line in child.stdout:
                    if sys.stdout is not None:
                        sys.stdout.write(scrub(line))
                        sys.stdout.flush()

            reader = threading.Thread(target=forward, daemon=True)
            reader.start()
            health.write_state(str(layout.workspace), 'running', wrapper_pid=os.getpid(),
                               regression_pid=child.pid, mode=command)
            while child.poll() is None:
                if stop_file and Path(stop_file).exists():
                    _stop_process_tree(child)
                    from run import shutdown_viewer
                    cleanup = shutdown_viewer('BellalunAuto 사용자 중지')
                    health.write_state(str(layout.workspace), 'cancelled', cleanup=cleanup, mode=command)
                    return 130
                time.sleep(.5)
            code = child.returncode
            reader.join(timeout=10)
            if command in {'run-regression', 'run-winupdate'} and not historical_conversion(arguments):
                report = completed_report(layout.workspace/'Reports', command, started - 1)
                if not report:
                    from run import shutdown_viewer
                    cleanup = shutdown_viewer('BellalunAuto 리포트 없는 종료')
                    health.write_state(str(layout.workspace), 'abnormal_exit', exit_code=code,
                                       cleanup=cleanup, mode=command,
                                       process=health.process_exit_message('VIEWER', started),
                                       message='새 전체 리포트가 없어 완료로 판단할 수 없습니다.')
                    health.notify_windows('BellalunAuto 비정상 종료',
                                          '새 전체 리포트가 생성되지 않았습니다. 작업 폴더의 로그를 확인하세요.',
                                          'error', 12)
                    print('[FAIL] 새 전체 리포트가 생성되지 않았습니다.')
                    return code or 3
                health.write_state(str(layout.workspace), 'completed', exit_code=code, report=report,
                                   mode=command)
                health.notify_windows('BellalunAuto 전체 실행 종료', str(report['verdicts']),
                                      'warning' if code else 'info')
                print(f"[{command}] 전체 실행 종료: {report['verdicts']} / {report['path']}")
            else:
                cleanup = None
                if code:
                    from run import shutdown_viewer
                    cleanup = shutdown_viewer('BellalunAuto 명령 실패 후 정리')
                health.write_state(str(layout.workspace), 'failed' if code else 'completed',
                                   exit_code=code, mode=command, cleanup=cleanup)
            return code
        except BaseException:
            if child is not None:
                _stop_process_tree(child)
                from run import shutdown_viewer
                shutdown_viewer('BellalunAuto 감시 프로세스 종료')
            raise
        finally:
            ready_path.unlink(missing_ok=True)


def _elevate(layout, arguments, stop_file=None):
    """원래 사용자의 경로를 명시해 승격하고 완료/종료 코드를 기다린다."""
    from ctypes import wintypes as w

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [('cbSize', w.DWORD), ('fMask', w.ULONG), ('hwnd', w.HWND),
                    ('lpVerb', w.LPCWSTR), ('lpFile', w.LPCWSTR), ('lpParameters', w.LPCWSTR),
                    ('lpDirectory', w.LPCWSTR), ('nShow', ctypes.c_int), ('hInstApp', w.HINSTANCE),
                    ('lpIDList', w.LPVOID), ('lpClass', w.LPCWSTR), ('hkeyClass', w.HKEY),
                    ('dwHotKey', w.DWORD), ('hIcon', w.HANDLE), ('hProcess', w.HANDLE)]
    log_path = layout.workspace/'Log'/f'elevated-{uuid.uuid4().hex}.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = child_command(['--workspace', str(layout.workspace), '--config', str(layout.config_path),
                             '--elevated', '--elevation-log', str(log_path)] +
                            (['--stop-file', str(stop_file)] if stop_file else []) + list(arguments))
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb, info.lpFile = 'runas', command[0]
    info.lpParameters = subprocess.list2cmdline(command[1:])
    info.lpDirectory, info.nShow = str(layout.workspace), 0
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell.ShellExecuteExW.restype = w.BOOL
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        print('[FAIL] 관리자 권한 요청이 거부됐거나 실행하지 못했습니다.')
        return 1223
    try:
        position = 0
        while kernel.WaitForSingleObject(info.hProcess, 250) == 0x102:
            position = relay_log(log_path, position)
        relay_log(log_path, position, final=True)
        code = w.DWORD()
        if not kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value
    finally:
        kernel.CloseHandle(info.hProcess)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(add_help=False, description='BellalunAuto: 기본기능·Windows Update 자동화',
                                     epilog='명령: selfcheck, portability-check, run-regression, run-winupdate 및 기존 run.py 명령')
    parser.add_argument('--version', action='store_true')
    parser.add_argument('--workspace')
    parser.add_argument('--config')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--elevated', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--stop-file', help=argparse.SUPPRESS)
    parser.add_argument('--elevation-log', help=argparse.SUPPRESS)
    options, arguments = parser.parse_known_args(argv)
    if options.version:
        print(f'BellalunAuto {__version__}')
        return 0
    if arguments in (['--help'], ['-h']):
        parser.print_help()
        return 0
    try:
        layout = resolve_layout(config_path=options.config, workspace=options.workspace)
        if options.elevation_log:
            if not options.elevated or not ctypes.windll.shell32.IsUserAnAdmin():
                raise PermissionError('승격 실행 로그는 관리자 프로세스에서만 사용할 수 있습니다.')
            log_path = validate_log_path(layout, options.elevation_log)
            # Unique file opened exclusively; the caller chose the workspace.
            with log_path.open('x', encoding='utf-8', buffering=1) as log:
                from contextlib import redirect_stdout, redirect_stderr
                forwarded = ['--workspace', str(layout.workspace), '--config', str(layout.config_path),
                             '--elevated'] + (['--stop-file', options.stop_file] if options.stop_file else []) + arguments
                with redirect_stdout(log), redirect_stderr(log):
                    return main(forwarded)
        if not arguments:
            from bellalunauto.gui import launch
            return launch(layout)
        if any(value in ('-h', '--help') for value in arguments):
            return _engine(layout, arguments)
        if arguments[0] in {'selfcheck', 'portability-check'}:
            return _print_diagnostics(layout)
        if options.worker:
            if not os.environ.get('BELLALUN_AUTO_PARENT'):
                raise ValueError('worker는 외부 감시 프로세스에서만 실행할 수 있습니다.')
            ready = os.environ.get('BELLALUN_AUTO_READY')
            if not ready:
                raise ValueError('worker 보호 준비 경로가 없습니다.')
            wait_worker_ready(ready, os.environ['BELLALUN_AUTO_PARENT'])
            return _engine(layout, arguments)
        control = requires_product_control(arguments[0]) and not historical_conversion(arguments)
        if control:
            if not layout.config_path.is_file():
                raise FileNotFoundError('실행 화면의 PC별 설정을 먼저 저장하세요.')
            if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
                if options.elevated:
                    raise PermissionError('관리자 권한으로 실행하지 못했습니다.')
                return _elevate(layout, arguments, options.stop_file)
            return run_guarded(layout, arguments, options.stop_file)
        return _engine(layout, arguments)
    except AlreadyRunning:
        print('[FAIL] 다른 BellalunAuto가 제품을 사용 중입니다. 실행이 끝난 뒤 다시 시도하세요.')
        return 4
    except (OSError, ValueError) as exc:
        print(f'[FAIL] {exc}')
        print('해결 방법: PC별 설정의 파일 위치와 접근 권한, JSON 형식을 확인하세요.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
