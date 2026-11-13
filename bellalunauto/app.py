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


def _inherited_stdin():
    """worker에 넘길 표준 입력.

    콘솔 CLI의 입력은 그대로 넘겨 대화형 질문을 유지한다. 콘솔 없는 GUI 실행 파일은 표준 입력이
    잘못된 핸들로 남을 수 있고, 그대로 넘기면 subprocess가 WinError 6으로 실패한다. 그때는 NUL을 준다.
    """
    if os.name != 'nt':
        return None
    import _winapi
    try:
        _winapi.GetStdHandle(_winapi.STD_INPUT_HANDLE)
    except OSError:
        return subprocess.DEVNULL
    return None


def _safe_cwd():
    """승격·worker 프로세스의 현재 폴더.

    설치판의 `작업`은 Users가 쓸 수 있으므로 현재 폴더로 쓰지 않는다. Windows는 확장자 없는
    명령(`powershell`, `net`, `sc`)을 System32보다 현재 폴더에서 먼저 찾기 때문이다.
    설치 폴더(관리자만 쓰기)를 쓴다. 소스 실행은 저장소 폴더를 쓴다.
    """
    from bellalunauto.runtime import _compiled
    if _compiled():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


_WORKSPACE_FOLDERS = ('Log', 'Reports', 'Evidence', 'Cache', 'Temp', 'work', 'Runs', 'preservation')
_EXECUTED_PATHS = ('viewer.exe', 'xipl.studio_exe', 'xipl.tesseract_exe', 'baseline_dir')


def elevated_workspace_problems(workspace, config):
    """승격된 시험이 믿으면 안 되는 작업 폴더 상태. 빈 목록이면 시작해도 된다.

    `작업`은 Users가 쓸 수 있다. 관리자 권한으로 실행·복원할 제품 파일이 그 안에 있거나,
    결과 폴더가 다른 위치를 가리키는 링크로 바뀌었으면 시작하지 않는다(REQ-DIST-006).
    """
    work = Path(workspace).resolve()
    problems = []
    for name in _WORKSPACE_FOLDERS:
        path = Path(workspace) / name
        try:
            attributes = getattr(os.lstat(path), 'st_file_attributes', 0)
        except FileNotFoundError:
            continue
        if path.is_symlink() or attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
            problems.append(f"작업 폴더의 '{name}'이 다른 위치를 가리키는 링크입니다: {path}")
    for key in _EXECUTED_PATHS:
        value = config
        for part in key.split('.'):
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(value, str) and value.strip():
            try:
                inside = Path(value).resolve().is_relative_to(work)
            except (OSError, ValueError):
                inside = False
            if inside:
                problems.append(f"관리자 권한으로 실행·복원할 '{key}'가 작업 폴더 안에 있습니다: {value}")
    return problems


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


#: 작업 폴더 경로 길이 상한(문자 수). Viewer가 쓰는 Export 증거의 상대 경로가 최대
#  117자(2026-10-18 실측)이고 LongPathsEnabled 기본값은 0이라, 260자 한도 안에 여유를 둔다.
WORKSPACE_PATH_LIMIT = 120


WORKSPACE_CHAR_FIX = ('작업 폴더를 %가 없는 경로로 다시 선택하세요. Windows 저장·열기 대화상자는 %이름%을 '
                      '환경 변수로 바꿔 읽으므로 Viewer의 Setting Export·Import가 실패합니다.')


def workspace_path_problem(workspace):
    """Viewer 파일 대화상자가 받아들이지 못하는 작업 폴더 경로면 설명, 아니면 None."""
    if '%' in str(workspace):
        return f"경로에 '%'가 있습니다: {workspace}"
    return None


def diagnostics(layout, check_connections=True):
    """조회만 수행한다. 화면 해상도·서비스·DB·설정을 바꾸지 않는다."""
    items = []

    def add(name, ok, detail, fix, notice=False):
        row = {'name': name, 'ok': bool(ok), 'detail': str(detail), 'fix': fix}
        if notice:
            row['notice'] = True
        items.append(row)

    add('설정 파일', layout.config_path.is_file(), layout.config_path,
        '실행 화면의 PC별 설정에서 경로와 시험 계정을 저장하세요.')
    try:
        config = bundled_config(load_config(layout), layout.resource_dir)
    except (OSError, ValueError) as exc:
        add('설정 읽기', False, type(exc).__name__, '설정 파일의 JSON 형식과 접근 권한을 확인하세요.')
        config = {}
    add('실행 자료', (layout.resource_dir/'automation_scope.json').is_file(), layout.resource_dir,
        '승인된 내부 자료가 포함된 설치 패키지를 다시 설치하세요.')
    length = len(str(layout.workspace))
    add('작업 폴더 경로 길이', length <= WORKSPACE_PATH_LIMIT,
        f'{length}자 (최대 {WORKSPACE_PATH_LIMIT}자): {layout.workspace}',
        '작업 폴더를 더 짧은 경로(예: D:\\BellalunAuto 작업)로 다시 선택하세요. '
        'Viewer가 저장하는 Export 증거 경로가 Windows 260자 한도를 넘으면 시험이 중간에 실패합니다.')
    from core import product_env
    launch_env = product_env.product_environment()
    xipl_problem = product_env.xipl_problem(launch_env)
    add('XIPL 설치 경로(XIPL_PATH)', xipl_problem is None,
        xipl_problem or product_env.lookup(launch_env, 'XIPL_PATH'), product_env.XIPL_FIX)
    char_problem = workspace_path_problem(layout.workspace)
    add('작업 폴더 경로 문자', char_problem is None, char_problem or layout.workspace, WORKSPACE_CHAR_FIX)
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
    xipl_cause = (f"먼저 'XIPL 설치 경로(XIPL_PATH)' 문제를 해결하세요. "
                  if xipl_problem else '')
    for name, value in paths:
        found = bool(value) and Path(value).exists()
        if not value:
            detail = '미설정'
        else:
            detail = value if found else f'위치에 없음: {value}'
        if name == 'Tesseract OCR':
            fix = ('Tesseract OCR을 설치한 뒤 PC별 설정에서 tesseract.exe 위치를 선택하세요. '
                   '설치돼 있으면 자동 탐지를 누르세요.')
        elif name == 'Viewer':
            fix = 'Bellalun Viewer가 설치된 PC인지 확인하고 PC별 설정의 자동 탐지 또는 VIEWER.exe 선택을 사용하세요.'
        else:
            fix = 'PC별 설정에서 설치/승인 자료의 실제 위치를 선택하세요.'
        if name.startswith('XIPL ') and not found:
            fix = xipl_cause + fix
        add(name, found, detail, fix)
        if name == 'Tesseract OCR':
            from core.ocr_runtime import inspect_runtime
            identity = inspect_runtime(value)
            errors = identity['errors']
            healthy = not errors
            version = identity['version'] or '확인 불가'
            reference = identity['reference_version']
            difference = '일치' if identity['reference_match'] else '차이 있음'
            detail = (f'버전 {version} · 기준 {reference}: {difference} · '
                      f"실행 SHA-256: {identity['executable_sha256'] or '확인 불가'} · "
                      f"eng SHA-256: {identity['eng_traineddata_sha256'] or '확인 불가'}")
            if errors:
                detail += ' · 실행/영어 언어 파일 확인 실패'
            add('OCR 환경 지문', healthy, detail,
                'PC별 설정에서 실행 가능한 tesseract.exe와 같은 설치의 tessdata/eng.traineddata를 확인하세요. '
                '기존 OCR은 보존하고 정상 PC의 버전·SHA-256과 비교하세요. '
                '새 PC는 Setup의 기준 5.5.3을 사용하세요. 변경 후 준비 점검을 다시 실행하세요.')
            if healthy and not identity['reference_match']:
                items[-1]['warning'] = True
    from .qa_dialogs import recent_ocr_failure
    failure = recent_ocr_failure(layout.workspace)
    if failure:
        items.append(failure)
    if os.name == 'nt':
        from core import display, sysinfo
        add('화면 해상도', display.screen_size() == (1920, 1080), display.screen_size(),
            'Windows 디스플레이에서 주 모니터를 1920×1080으로 설정하세요.')
        add('Windows 배율', display.system_dpi() == 96, f'{display.system_dpi()} DPI',
            'Windows 배율을 100%로 설정하세요.')
        if sysinfo.is_elevated():
            add('관리자 권한', True, '관리자 권한으로 실행 중', '')
        else:
            # 화면과 점검은 일반 권한이 정상이다. 시험만 시작할 때 승격한다(REQ-DIST-006).
            add('관리자 권한', True, '일반 권한 화면 · 시험을 시작할 때 UAC로 관리자 권한을 요청합니다',
                '', notice=True)
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
                ('' if xipl['ok'] else xipl_cause) +
                '제품 설치와 XIPL.SERVER의 9784 포트 수신 상태를 확인하세요.')
    if check_connections:
        dicom = section(config.get('dicom'))
        for name, raw in [('MWL 서버', dicom.get('mwl_server_url')),
                          ('Print 서버', dicom.get('print_server_url')),
                          ('Storage 서버', section(dicom.get('storage_scp')).get('api_url'))]:
            configured = False
            try:
                parsed = urlsplit(raw or '')
                if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                    raise ValueError('미설정')
                configured = True
                with socket.create_connection((parsed.hostname, parsed.port or
                                               (443 if parsed.scheme == 'https' else 80)), timeout=3):
                    available = True
            except (OSError, ValueError):
                available = False
            add(name, available, '연결 가능' if available else ('연결 실패' if configured else '주소 미설정'),
                '서버 가동·포트와 시험망 연결을 확인하세요.' if configured else
                'PC별 설정에 서버 주소와 포트를 입력하세요.')
    return items


def _print_diagnostics(layout):
    rows = diagnostics(layout)
    problems = [row for row in rows if not row['ok']]
    print(f'BellalunAuto {__version__} 실행 환경 점검 (조회 전용)')
    if problems:
        print(f'결론: 시작 전에 해결할 문제 {len(problems)}개 — 아래 [FAIL] 행의 해결 방법을 따르세요.')
    else:
        print('결론: 시험을 시작할 수 있습니다.')
    for row in rows:
        tag = 'WARN' if row.get('warning') else '안내' if row.get('notice') else ('PASS' if row['ok'] else 'FAIL')
        print(f"[{tag}] {row['name']}: {row['detail']}")
        if not row['ok'] or row.get('warning'):
            print(f"  해결 방법: {row['fix']}")
    return 1 if problems else 0


def elevation_failure_message(error_code):
    """ShellExecuteEx runas 실패를 실제 원인에 맞게 알린다."""
    if error_code == 1223:
        return ('[FAIL] UAC 요청을 취소해 시험을 시작하지 않았습니다. 제품·DB·설정은 바뀌지 않았습니다. '
                '다시 실행하고 UAC 창에서 [예]를 누르세요.')
    return (f'[FAIL] 관리자 권한으로 시험을 시작하지 못했습니다(Windows 오류 {error_code}). '
            '제품·DB·설정은 바뀌지 않았습니다. 관리자 계정 사용 가능 여부를 확인하세요.')


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
                           stdin=subprocess.DEVNULL, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
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
    """GUI 콜백 없이도 감독 프로세스가 최종 실행 상태를 남긴다."""
    code = 3
    try:
        code = _run_guarded_impl(layout, arguments, stop_file)
        return code
    finally:
        run_id = os.environ.get('BELLALUN_QA_RUN')
        if run_id:
            from bellalunauto.runs import RunRecord
            path = Path(layout.workspace) / 'Runs' / run_id / 'run.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            RunRecord(layout.workspace, path, data).finish(code)


def _run_guarded_impl(layout, arguments, stop_file=None):
    from core import automation_health as health
    from core.ui import foreground_unlocked, taskbar_autohidden
    from bellalunauto.processes import WindowsJob
    command = arguments[0]
    problems = elevated_workspace_problems(layout.workspace,
                                           bundled_config(load_config(layout), layout.resource_dir))
    if problems:
        raise PermissionError('관리자 권한 시험을 시작하지 않았습니다. ' + ' / '.join(problems))
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
                                     stdin=_inherited_stdin(), cwd=_safe_cwd(), env=environment,
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
                            (['--run-id', os.environ['BELLALUN_QA_RUN']] if os.environ.get('BELLALUN_QA_RUN') else []) +
                            (['--stop-file', str(stop_file)] if stop_file else []) + list(arguments))
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb, info.lpFile = 'runas', command[0]
    info.lpParameters = subprocess.list2cmdline(command[1:])
    info.lpDirectory, info.nShow = str(_safe_cwd()), 0
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell.ShellExecuteExW.restype = w.BOOL
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        error_code = ctypes.get_last_error()
        print(elevation_failure_message(error_code))
        return error_code or 1
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
    parser.add_argument('--run-id', help=argparse.SUPPRESS)
    options, arguments = parser.parse_known_args(argv)
    if options.run_id:
        import re
        if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{8}', options.run_id):
            print('[FAIL] 실행 번호 형식이 올바르지 않습니다.')
            return 2
        os.environ['BELLALUN_QA_RUN'] = options.run_id
    if options.version:
        print(f'BellalunAuto {__version__}')
        return 0
    if arguments in (['--help'], ['-h']):
        parser.print_help()
        return 0
    try:
        try:
            layout = resolve_layout(config_path=options.config, workspace=options.workspace)
        except (OSError, ValueError) as exc:
            if arguments or options.worker or options.elevation_log:
                raise
            # 숨김 콘솔 EXE의 화면 실행은 print가 보이지 않는다. 창으로 원인과 복구를 보인다.
            from bellalunauto.gui import recover_start
            return recover_start(exc)
        if options.elevation_log:
            if not options.elevated or not ctypes.windll.shell32.IsUserAnAdmin():
                raise PermissionError('승격 실행 로그는 관리자 프로세스에서만 사용할 수 있습니다.')
            log_path = validate_log_path(layout, options.elevation_log)
            # Unique file opened exclusively; the caller chose the workspace.
            with log_path.open('x', encoding='utf-8', buffering=1) as log:
                from contextlib import redirect_stdout, redirect_stderr
                forwarded = ['--workspace', str(layout.workspace), '--config', str(layout.config_path),
                             '--elevated'] + (['--run-id', options.run_id] if options.run_id else []) + (['--stop-file', options.stop_file] if options.stop_file else []) + arguments
                with redirect_stdout(log), redirect_stderr(log):
                    return main(forwarded)
        if not arguments:
            from bellalunauto.gui import launch
            return launch(layout)
        if arguments == ['prepare-install']:
            from bellalunauto.prerequisites import prepare_install
            return prepare_install(layout)
        if arguments[0] == 'verify-share':
            from bellalunauto.share import verify_package
            if len(arguments) != 2:
                raise ValueError('verify-share <공유 ZIP 경로>를 지정하세요.')
            problems = verify_package(arguments[1])
            for problem in problems:
                print(f'[FAIL] {problem}')
            if not problems:
                print('[OK] 공유 ZIP의 파일 목록·SHA-256·상대 링크를 확인했습니다.')
            return 1 if problems else 0
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
            char_problem = workspace_path_problem(layout.workspace)
            if char_problem:
                print(f'[FAIL] 작업 폴더 경로 문자: {char_problem}')
                print(f'해결 방법: {WORKSPACE_CHAR_FIX}')
                return 2
            record = None
            previous_run = os.environ.get('BELLALUN_QA_RUN')
            if (arguments[0] in {'run-regression', 'run-winupdate'} and not previous_run
                    and not options.elevated):
                from bellalunauto.runs import RunRecord
                from bellalunauto.runplan import build_plan
                config = bundled_config(load_config(layout), layout.resource_dir)
                record = RunRecord.create(layout.workspace, arguments[0], build_plan(layout, config, arguments[0]))
                os.environ['BELLALUN_QA_RUN'] = record.data['run_id']
                print(f"실행 번호: {record.data['run_id']} · 화면 동의 없음(CLI)")
            code = -1
            try:
                if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
                    if options.elevated:
                        raise PermissionError('관리자 권한으로 실행하지 못했습니다.')
                    code = _elevate(layout, arguments, options.stop_file)
                else:
                    code = run_guarded(layout, arguments, options.stop_file)
                return code
            finally:
                if record:
                    record.finish(code)
                    print(f"실행 결과: {record.data['status']} · 다음 행동: {record.data['next_action']}")
                    os.environ.pop('BELLALUN_QA_RUN', None)
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
