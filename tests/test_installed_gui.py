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


def test_run_record_is_bound_to_exact_run_and_gui_process(tmp_path):
    run_id = '20261125-091000-012345ab'
    def record(name, action, pid):
        folder = tmp_path / 'Runs' / name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'run.json'
        path.write_text(json.dumps({'run_id': name, 'action': action, 'supervisor_pid': pid}),
                        encoding='utf-8')
        return path

    record('20261125-091101-11111111', 'run-winupdate', 51)
    assert gui.find_run_record(tmp_path, 'run-winupdate', run_id, 51) is None
    record(run_id, 'run-winupdate', 52)
    with pytest.raises(RuntimeError, match='실행 기록'):
        gui.find_run_record(tmp_path, 'run-winupdate', run_id, 51)
    owned = record(run_id, 'run-winupdate', 51)
    assert gui.find_run_record(tmp_path, 'run-winupdate', run_id, 51) == owned


def test_run_record_rejects_a_path_in_place_of_the_generated_id(tmp_path):
    with pytest.raises(ValueError, match='실행 번호'):
        gui.find_run_record(tmp_path, 'run-winupdate', '../another-run', 51)


def test_run_record_waits_through_temporary_share_and_parse_errors(tmp_path, monkeypatch):
    from pathlib import Path
    run_id = '20261125-091000-012345ab'
    path = tmp_path / 'Runs' / run_id / 'run.json'
    reads = iter([PermissionError('temporary sharing violation'), '{',
                  json.dumps({'run_id': run_id, 'action': 'run-winupdate', 'supervisor_pid': 51})])
    real_read = Path.read_text

    def read(candidate, *args, **kwargs):
        if candidate != path:
            return real_read(candidate, *args, **kwargs)
        attempt = next(reads)
        if isinstance(attempt, Exception):
            raise attempt
        return attempt

    monkeypatch.setattr(Path, 'read_text', read)
    assert gui.find_run_record(tmp_path, 'run-winupdate', run_id, 51) is None
    assert gui.find_run_record(tmp_path, 'run-winupdate', run_id, 51) is None
    assert gui.find_run_record(tmp_path, 'run-winupdate', run_id, 51) == path


def test_gui_collects_only_report_log_and_checkpoint_evidence_from_its_run(tmp_path):
    from bellalunauto.runs import RunRecord, engine_log_path

    run_id = '20261125-091000-012345ab'
    run = RunRecord.create(tmp_path, 'run-winupdate', {}, consent=True, run_id=run_id)
    reports = tmp_path / 'Reports'
    reports.mkdir()
    rows = [{'tc_id': f'TC_WindowsUpdate_{i:02}', 'verdict': 'PASS'} for i in range(1, 14)]
    meta = {'run_id': run_id, 'execution_mode': 'live', 'chain_completed': True,
            'command': 'exe run-winupdate --prepared', 'preflight': {'summary': 'synthetic'},
            'restoration': {'status': 'verified', 'run_id': run_id},
            'checkpoint': str(tmp_path / 'work/winupdate_checkpoint.json'), 'reused_stages': ['a']}
    own = reports / 'Result_WindowsUpdate_own.json'
    own.write_text(json.dumps({'meta': meta, 'results': rows}), encoding='utf-8')
    newer = reports / 'Result_WindowsUpdate_foreign.json'
    newer.write_text(json.dumps({'meta': dict(meta, run_id='foreign'), 'results': rows}), encoding='utf-8')
    run.finish(0)
    log = engine_log_path(tmp_path, run_id)
    log.parent.mkdir()
    log.write_text('owned engine', encoding='utf-8')
    (log.parent / 'BellalunAuto-newest.log').write_text('foreign engine', encoding='utf-8')
    result = gui.collect_gui_result({}, tmp_path, 'run-winupdate', tmp_path / 'capture', run.path)
    assert result['completed'] and result['report']['path'] == str(own)
    assert result['log'] == str(log)
    assert result['meta']['preflight'] == meta['preflight']
    assert result['meta']['restoration'] == meta['restoration']
    assert result['meta']['reused_stages'] == ['a']
    paths = {item['path'] for item in result['snapshot']['files']}
    assert 'Reports/Result_WindowsUpdate_own.json' in paths
    assert 'Reports/Result_WindowsUpdate_foreign.json' not in paths
    assert 'Log/BellalunAuto-newest.log' not in paths
    own.unlink()
    missing = gui.collect_gui_result({}, tmp_path, 'run-winupdate', tmp_path / 'missing', run.path)
    assert missing['completed'] is False


def test_drive_launches_exe_without_flags_and_passes_identity_to_only_this_process(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    from bellalunauto.runs import RunRecord, engine_log_path

    run_id = '20261125-091000-012345ab'
    exe = tmp_path / 'BellalunAuto.exe'
    captured = {}
    monkeypatch.setattr(gui, 'new_run_id', lambda: run_id)
    monkeypatch.setenv('QA_AUTOMATION_UNATTENDED', '1')
    monkeypatch.setenv('BELLALUN_QA_RUN', 'unrelated')
    def popen(args, **kwargs):
        captured.update(args=args, env=kwargs['env'])
        return SimpleNamespace(pid=os.getpid(), poll=lambda: None, wait=lambda _: 0)
    monkeypatch.setattr(gui.subprocess, 'Popen', popen)
    def click(_hwnd, label, **_):
        if label == gui.CONSENT_LABEL:
            record = RunRecord.create(tmp_path, 'run-winupdate', {}, consent=True,
                                      run_id=captured['env'][gui.GUI_VERIFICATION_RUN_ID])
            log = engine_log_path(tmp_path, run_id)
            log.parent.mkdir()
            log.write_text('synthetic empty report failure', encoding='utf-8')
            record.finish(3)
    drive = SimpleNamespace(frame_windows=lambda _: [], wait_screen=lambda _, labels, __: (1, labels[0]),
                            texts=lambda _: [], check_all=lambda _: [], click=click)

    result = gui.drive_one(exe, 'BellalunAuto synthetic', tmp_path, 'run-winupdate',
                           tmp_path / 'capture', drive=drive, max_hours=1, poll=1, log=lambda _: None)
    assert captured['args'] == [str(exe)]
    assert 'QA_AUTOMATION_UNATTENDED' not in captured['env']
    assert 'BELLALUN_QA_RUN' not in captured['env']
    assert gui.GUI_VERIFICATION_RUN_ID not in os.environ
    assert result['gui']['run_id'] == run_id
    assert result['gui']['status'] == 'abnormal'
    assert not result['completed']
