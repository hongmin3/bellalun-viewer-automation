"""Windows 콘솔 자식을 띄우는 실제 호출 경계의 무창 플래그 계약."""
import json
import os
from pathlib import Path
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows 프로세스 생성 계약')


def test_startup_system_query_does_not_allocate_console(monkeypatch):
    from core import sysinfo
    flags = []
    def run(command, **kwargs):
        flags.append(kwargs.get('creationflags', 0))
        return subprocess.CompletedProcess(command, 0, b'True\r\n', b'')
    monkeypatch.setattr(sysinfo.subprocess, 'run', run)
    assert sysinfo.is_elevated() is True
    assert flags == [0x08000000]


def test_startup_database_ping_does_not_allocate_console(monkeypatch):
    from core.db import BellalunDb
    flags = []
    def run(command, **kwargs):
        flags.append(kwargs.get('creationflags', 0))
        return subprocess.CompletedProcess(command, 0, b'[{"ok":1}]', b'')
    monkeypatch.setattr('core.db.subprocess.run', run)
    assert BellalunDb('synthetic').query('DATA', 'SELECT 1') == [{'ok': 1}]
    assert flags == [0x08000000]


def test_database_batch_keeps_output_without_console(monkeypatch):
    from core.db import BellalunDb
    flags = []
    def run(command, **kwargs):
        flags.append(kwargs.get('creationflags', 0))
        Path(kwargs['env']['BLN_OUT_FILE']).write_text(json.dumps({'probe': [{'ok': 1}]}), encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, b'', b'')
    monkeypatch.setattr('core.db.subprocess.run', run)
    assert BellalunDb('synthetic').query_many([{'name':'probe', 'db':'DATA', 'sql':'SELECT 1'}]) == {'probe':[{'ok':1}]}
    assert flags == [0x08000000]


def test_report_version_queries_do_not_allocate_console(tmp_path, monkeypatch):
    import run as runner
    flags = []
    def run(command, **kwargs):
        flags.append(kwargs.get('creationflags', 0))
        return subprocess.CompletedProcess(command, 0, b'1.0\r\n', b'')
    monkeypatch.setattr(runner.subprocess, 'run', run)
    executable = tmp_path / 'synthetic.exe'
    executable.touch()
    runner._file_version(str(executable))
    runner._tesseract_version(str(executable))
    assert flags == [0x08000000, 0x08000000]


def test_report_git_query_keeps_output_without_console(tmp_path, monkeypatch):
    from core import source_identity
    calls = []
    monkeypatch.setattr(source_identity.shutil, 'which', lambda name: 'synthetic-git.exe')
    def run(command, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(command, 0, 'synthetic-commit\n', '')
    monkeypatch.setattr(source_identity.subprocess, 'run', run)
    assert source_identity._git(tmp_path, 'rev-parse', 'HEAD') == 'synthetic-commit'
    assert calls[0].get('creationflags') == 0x08000000
    assert calls[0]['capture_output'] is True


@pytest.mark.parametrize('prepare', [True, False])
def test_xipl_scenario_cleanup_does_not_allocate_console(monkeypatch, prepare):
    from types import SimpleNamespace
    from tests import xipl_flows
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, b'', b'')
    monkeypatch.setattr(xipl_flows.subprocess, 'run', run)
    if prepare:
        monkeypatch.setattr(xipl_flows.vp, 'ensure_parameter_copies', lambda root: None)
        monkeypatch.setattr(xipl_flows.vp, 'fixture_is_fresh', lambda *args: True)
        monkeypatch.setattr(xipl_flows.vp, 'open_test_study', lambda ctx: 'synthetic-study')
        assert xipl_flows._prepare(SimpleNamespace(cfg={})) == 'synthetic-study'
    else:
        xipl_flows._stop_xipl()
    assert len(calls) == 1
    assert calls[0][1].get('creationflags') == 0x08000000
    assert calls[0][1]['capture_output'] is True
    assert 'Get-Process XIPL.STUDIO' in calls[0][0][3]
