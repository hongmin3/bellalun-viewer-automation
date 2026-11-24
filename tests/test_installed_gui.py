"""설치판 GUI 전체 회귀 도구의 범위 제한과 실행 기록 찾기.

Validates: REQ-DIST-009
화면을 열거나 제품을 실행하지 않는다.
"""
import json

import pytest

from tools import run_installed_gui as gui


def test_only_full_suites_in_given_order():
    assert gui.validate_commands('run-winupdate,run-regression') == ['run-winupdate', 'run-regression']
    for bad in ('', 'run-wf14', 'run-winupdate,run-winupdate', 'run-combined', 'run-selected'):
        with pytest.raises(ValueError):
            gui.validate_commands(bad)


def test_approval_is_required_before_any_screen(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, 'verify_install', lambda *a: pytest.fail('화면·설치 대조 전에 거부해야 한다'))
    with pytest.raises(SystemExit):
        gui.main(['--exe', str(tmp_path / 'a.exe'), '--build-info', str(tmp_path / 'b.json'),
                  '--workspace', str(tmp_path), '--out', str(tmp_path / 'out'),
                  '--suites', 'run-winupdate', '--approval', '  '])


def test_run_record_is_the_newest_for_the_command_after_start(tmp_path):
    def record(name, action, epoch):
        folder = tmp_path / 'Runs' / name
        folder.mkdir(parents=True)
        (folder / 'run.json').write_text(json.dumps({'action': action, 'started_epoch': epoch}), encoding='utf-8')
        return folder / 'run.json'

    record('old', 'run-winupdate', 100)
    record('other', 'run-regression', 210)
    newest = record('new', 'run-winupdate', 205)
    assert gui.find_run_record(tmp_path, 'run-winupdate', 200) == newest
    assert gui.find_run_record(tmp_path, 'run-winupdate', 300) is None
