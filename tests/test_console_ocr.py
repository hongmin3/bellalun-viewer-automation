"""콘솔 자식 호출 경계만 검사한다. 실제 프로세스·화면·제품은 사용하지 않는다."""
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image, ImageGrab
import pytest


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows 콘솔 생성 계약')


@pytest.fixture
def console_call(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs.get('creationflags') == 0x08000000
        assert kwargs.get('capture_output') is True
        return subprocess.CompletedProcess(command, 0, b'true\r\n', b'')

    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr(subprocess, 'Popen', Mock(side_effect=AssertionError('실제 프로세스 금지')))
    monkeypatch.setattr(ImageGrab, 'grab', Mock(side_effect=AssertionError('실제 화면 캡처 금지')))
    return calls, run


def test_screen_ocr_preserves_arguments_and_decoded_output_without_console(tmp_path, monkeypatch, console_call):
    from core import screen
    executable = tmp_path / 'synthetic-ocr.exe'
    executable.touch()
    monkeypatch.setattr(screen, 'TESSERACT_EXE', str(executable))
    monkeypatch.setattr(screen, 'grab', lambda *args, **kwargs: Image.new('RGB', (2, 2)))
    original_mkstemp = tempfile.mkstemp
    monkeypatch.setattr(screen.tempfile, 'mkstemp',
                        lambda **kwargs: original_mkstemp(dir=tmp_path, **kwargs))
    assert screen.ocr((0, 0, 2, 2), psm=7) == 'true'
    command, kwargs = console_call[0][0]
    assert command[0] == str(executable)
    assert command[2:] == ['stdout', '-l', 'eng', '--psm', '7']
    assert not Path(command[1]).exists()


def test_viewer_pid_query_preserves_lookup_and_result(monkeypatch, console_call):
    from core.ui import ViewerUi
    calls, boundary = console_call

    def run(command, **kwargs):
        boundary(command, **kwargs)
        return subprocess.CompletedProcess(command, 0, b'424242\r\n', b'')

    monkeypatch.setattr(subprocess, 'run', run)
    assert ViewerUi('SYNTHETIC')._find_pid() == 424242
    assert calls[0][0][:3] == ['powershell', '-NoProfile', '-Command']
    assert 'Get-Process SYNTHETIC' in calls[0][0][3]


@pytest.mark.parametrize('method', ['invoke', 'open', 'info', 'field', 'close'])
def test_xipl_powershell_boundaries_keep_results_without_console(method, monkeypatch, console_call):
    from core.xipl import XiplStudio
    studio = object.__new__(XiplStudio)
    studio.ui = SimpleNamespace(pid=424242, key=Mock(),
                                main_window=lambda: SimpleNamespace(rect=(0, 0, 1000, 800)))
    calls, boundary = console_call
    output = {'invoke': b'true', 'open': b'true', 'info': b'{"title":"Synthetic PIM"}',
              'field': b'OK|1|2', 'close': b'true'}[method]

    def run(command, **kwargs):
        boundary(command, **kwargs)
        return subprocess.CompletedProcess(command, 0, output, b'')

    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr('core.xipl.time.sleep', lambda seconds: None)
    if method == 'invoke':
        assert studio._uia_invoke_named('User') is True
    elif method == 'open':
        assert studio._uia_open_process() is True
    elif method == 'info':
        assert studio.process_editor_info() == {'title': 'Synthetic PIM'}
    elif method == 'field':
        studio.ui.main_window = lambda: None
        assert studio.set_pim_field('Synthetic', 2) == {'field': 'Synthetic', 'before': 1., 'after': 2.}
    else:
        studio.process_editor_info = lambda **kwargs: {'title': 'Synthetic PIM'}
        assert studio.close_process_if_open() is True
        studio.ui.key.assert_called_once_with('ESC', settle=.2)
    assert len(calls) == 1
    assert calls[0][0][:3] == ['powershell', '-NoProfile', '-Command']
    assert '424242' in calls[0][0][3]


@pytest.mark.parametrize('code', [0, 1])
def test_xipl_ocr_keeps_png_stdin_timeout_and_error(tmp_path, monkeypatch, console_call, code):
    from core.xipl import XiplStudio
    studio = object.__new__(XiplStudio)
    studio.tesseract = str(tmp_path / 'synthetic.exe')
    Path(studio.tesseract).touch()
    calls, boundary = console_call

    def run(command, **kwargs):
        boundary(command, **kwargs)
        return subprocess.CompletedProcess(command, code, b'synthetic text', b'synthetic error')

    monkeypatch.setattr(subprocess, 'run', run)
    image = Image.new('RGB', (2, 2))
    if code:
        with pytest.raises(RuntimeError, match='synthetic error'):
            studio._ocr_png(image, '--psm', '6')
    else:
        assert studio._ocr_png(image, '--psm', '6') == 'synthetic text'
    command, kwargs = calls[0]
    assert command == [studio.tesseract, 'stdin', 'stdout', '-l', 'eng', '--psm', '6']
    assert kwargs['input'].startswith(b'\x89PNG\r\n\x1a\n')
    assert kwargs['timeout'] == 30


def test_cleanup_taskkill_keeps_exact_arguments(console_call):
    from core.flows import _kill_viewer
    _kill_viewer(424242)
    assert console_call[0][0][0] == ['taskkill', '/PID', '424242', '/F']


def test_hotfix_query_keeps_timeout_and_parsed_data(console_call):
    from core.update_evidence import WindowsProbe
    calls, boundary = console_call

    def run(command, **kwargs):
        boundary(command, **kwargs)
        return subprocess.CompletedProcess(command, 0, b'[{"id":"KB0000001","on":"2026-11-05"}]', b'')

    assert WindowsProbe(runner=run, timeout=17).hotfixes() == [{'id': 'KB0000001', 'installed_on': '2026-11-05'}]
    assert calls[0][0][:4] == ['powershell', '-NoProfile', '-NonInteractive', '-Command']
    assert calls[0][1]['timeout'] == 17
