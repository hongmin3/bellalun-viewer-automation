"""콘솔 없는 GUI 부모의 잘못된 표준 입력 핸들을 자식 호출이 상속하지 않는 계약.

Validates: REQ-DIST-002, REQ-QA-005
"""
import ast
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_SOURCES = [
    *sorted((ROOT / 'bellalunauto').glob('*.py')),
    *sorted((ROOT / 'core').glob('*.py')),
    ROOT / 'run.py',
    *sorted(p for p in (ROOT / 'tests').glob('*.py') if not p.name.startswith('test_')),
    ROOT / 'tools' / 'run_installed_suites.py',
]
SPAWNERS = {'run', 'Popen', 'check_output', 'call', 'check_call'}
REDIRECTS = {'capture_output', 'stdout', 'stderr'}


def _subprocess_calls(path):
    """`subprocess.run(...)` 같은 직접 호출과 `self.runner(...)`처럼 주입한 실행기 호출."""
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr in SPAWNERS
                and isinstance(func.value, ast.Name) and func.value.id == 'subprocess'):
            yield node
        elif (isinstance(func, ast.Attribute) and func.attr == 'runner') or (
                isinstance(func, ast.Name) and func.id == 'runner'):
            yield node


def test_redirected_children_do_not_inherit_parent_stdio():
    """출력을 받는 자식은 세 표준 핸들을 모두 정해야 한다(WinError 6 방지).

    하나라도 바꾸면 subprocess가 나머지 핸들을 부모에서 읽는다. 콘솔 없는 GUI 실행 파일에서는
    그 핸들이 잘못된 값일 수 있다.
    """
    missing = []
    seen = 0
    for path in PRODUCT_SOURCES:
        for call in _subprocess_calls(path):
            names = {k.arg for k in call.keywords}
            seen += 1
            if not names & (REDIRECTS | {'stdin', 'input'}):
                continue
            has_in = bool(names & {'stdin', 'input'})
            has_out = 'capture_output' in names or {'stdout', 'stderr'} <= names
            if not (has_in and has_out):
                missing.append(f'{path.relative_to(ROOT).as_posix()}:{call.lineno}')
    assert seen > 30, f'검사 대상 호출이 너무 적습니다: {seen}'
    assert missing == []


@pytest.mark.skipif(os.name != 'nt', reason='Windows 표준 핸들 계약')
def test_invalid_stdin_handle_breaks_bare_call_but_not_product_query():
    """Nuitka attach GUI처럼 STD_INPUT이 INVALID_HANDLE_VALUE인 부모를 실제로 만든다."""
    script = textwrap.dedent(r'''
        import ctypes, json, subprocess, sys
        sys.path.insert(0, sys.argv[1])
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.SetStdHandle.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
        assert k.SetStdHandle(ctypes.c_ulong(-10).value, ctypes.c_void_p(-1)), ctypes.get_last_error()
        result = {}
        try:
            subprocess.run(['cmd', '/c', 'echo bare'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            result['bare'] = 'ok'
        except OSError as error:
            result['bare'] = error.winerror
        from core import sysinfo
        result['product'] = sysinfo._ps('Write-Output synthetic-probe')
        from bellalunauto import app
        result['worker_stdin'] = app._inherited_stdin() == subprocess.DEVNULL
        print(json.dumps(result))
    ''')
    out = subprocess.run([sys.executable, '-c', script, str(ROOT)], capture_output=True,
                         stdin=subprocess.DEVNULL, text=True, timeout=120,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == '{"bare": 6, "product": "synthetic-probe", "worker_stdin": true}'


def _raise_invalid_handle(secret):
    raise OSError(9, '핸들이 잘못되었습니다', secret, 6)


def test_diagnostics_error_names_cause_location_and_log(tmp_path):
    from bellalunauto.qa_dialogs import diagnostics_error_report
    try:
        _raise_invalid_handle('password=synthetic-secret')
    except OSError as error:
        message = diagnostics_error_report(error, tmp_path)
    log = (tmp_path / 'Log' / 'diagnostics-error.log').read_text(encoding='utf-8')
    assert '원인: OSError · 코드 6 · 핸들이 잘못되었습니다' in message
    assert '실패 위치: tests/test_console_stdin.py:' in message and '_raise_invalid_handle' in message
    assert str(tmp_path / 'Log' / 'diagnostics-error.log') in message
    assert 'selfcheck' in message
    assert '_raise_invalid_handle' in log and '코드 6' in log
    assert 'synthetic-secret' not in message + log


def test_diagnostics_error_reports_unwritable_log_once(tmp_path):
    from bellalunauto.qa_dialogs import diagnostics_error_report
    blocked = tmp_path / 'blocked'
    blocked.write_text('', encoding='utf-8')
    try:
        raise ValueError('config value synthetic-secret')
    except ValueError as error:
        message = diagnostics_error_report(error, blocked)
    assert '원인: ValueError' in message
    assert '기록을 남기지 못했습니다' in message and '쓰기 권한' in message
    assert 'synthetic-secret' not in message
