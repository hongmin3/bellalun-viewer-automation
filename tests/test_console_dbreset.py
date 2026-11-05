"""서비스 제어의 외부 호출은 mock으로 대체하고 콘솔 생성 플래그만 검사한다."""
from types import SimpleNamespace

import pytest

from core import dbreset


@pytest.fixture
def service_commands(monkeypatch):
    calls = []
    started = set()
    modes = {}

    def run_command(command, **kwargs):
        assert kwargs.get('creationflags') == 0x08000000
        calls.append(command)
        if command[:2] == ['sc', 'query']:
            output = 'RUNNING' if command[2] in started else 'STOPPED'
        elif command[:2] == ['sc', 'qc']:
            output = modes.get(command[2], 'AUTO_START')
        else:
            output = ''
            if command[:2] == ['sc', 'config']:
                modes[command[2]] = 'AUTO_START'
            elif command[:2] == ['net', 'start']:
                started.add(command[2])
        return SimpleNamespace(returncode=0, stdout=output, stderr='')

    monkeypatch.setattr(dbreset.subprocess, 'run', run_command)
    monkeypatch.setattr(dbreset.subprocess, 'CREATE_NO_WINDOW', 0x08000000, raising=False)
    monkeypatch.setattr(dbreset.time, 'sleep', lambda seconds: pytest.fail('합성 서비스가 즉시 시작되어야 합니다.'))
    return calls, modes


@pytest.mark.parametrize('mode', ['DEMAND_START', 'DISABLED'])
def test_database_service_console_children_are_hidden(service_commands, mode):
    calls, modes = service_commands
    name = 'MSSQL$SYNTHETIC'
    modes[name] = mode
    result = dbreset.ensure_database_service(SimpleNamespace(cfg={'sql_service_name': name}))
    assert result['after'] == 'RUNNING'
    assert result['start_mode_after'] == 'AUTO_START'
    assert ['sc', 'config', name, 'start=', 'auto'] in calls
    assert ['net', 'start', name] in calls


def test_product_stop_console_children_are_hidden(service_commands):
    calls, _ = service_commands
    dbreset.stop_app_processes()
    assert calls == ([['net', 'stop', name] for name in dbreset.APP_SERVICES]
                     + [['taskkill', '/IM', name + '.exe', '/F', '/T']
                        for name in dbreset.APP_PROCESSES])


def test_product_service_start_console_children_are_hidden(service_commands):
    calls, _ = service_commands
    result = dbreset.start_app_services()
    assert result == {name: 'RUNNING' for name in dbreset.APP_SERVICES}
    for name in dbreset.APP_SERVICES:
        assert ['net', 'start', name] in calls
