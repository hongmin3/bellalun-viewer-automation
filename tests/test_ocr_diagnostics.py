"""Validates: REQ-OCR-002 / TEST-OCR-002. 실제 GUI·DB·설치는 실행하지 않는다."""
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from bellalunauto import app, qa_dialogs
from bellalunauto.runtime import Layout


@pytest.fixture(autouse=True)
def no_host_elevation_probe():
    with patch('core.sysinfo.is_elevated', return_value=False):
        yield


def setup_layout(tmp_path):
    exe = tmp_path / 'ocr/tesseract.exe'
    exe.parent.mkdir()
    exe.write_bytes(b'engine')
    data = exe.parent / 'tessdata/eng.traineddata'
    data.parent.mkdir()
    data.write_bytes(b'language')
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'xipl': {'tesseract_exe': str(exe)}}))
    return Layout(tmp_path, tmp_path, config), data


@pytest.mark.parametrize('version,state', [('5.5.3', 'OK'), ('5.4.0', 'WARN')])
def test_diagnostics_uses_engine_and_language_identity_and_keeps_config(tmp_path, version, state):
    layout, _ = setup_layout(tmp_path)
    original = layout.config_path.read_bytes()
    with patch('core.ocr_runtime.subprocess.run', return_value=
               subprocess.CompletedProcess([], 0, 'tesseract ' + version, '')):
        rows = app.diagnostics(layout, check_connections=False)
    matches = [r for r in rows if r['name'] == 'OCR 환경 지문']
    assert len(matches) == 1, '준비 점검에 실행 가능한 OCR의 환경 지문이 필요하다'
    row = matches[0]
    assert qa_dialogs.diagnostic_state(row) == state
    assert row['ok']
    assert version in row['detail'] and '5.5.3' in row['detail']
    assert 'eng SHA-256' in row['detail'] and '실행 SHA-256' in row['detail']
    if state == 'WARN':
        assert '기존 OCR' in row['fix'] and '비교' in row['fix']
    assert rows[rows.index(row) - 1]['name'] == 'Tesseract OCR'
    assert layout.config_path.read_bytes() == original


def test_missing_language_and_unexecutable_engine_are_failures(tmp_path):
    layout, data = setup_layout(tmp_path)
    for missing_language in (True, False):
        if missing_language:
            data.unlink()
        else:
            data.write_bytes(b'language')
        with patch('core.ocr_runtime.subprocess.run', side_effect=
                   None if missing_language else OSError('private failure'), return_value=
                   subprocess.CompletedProcess([], 0, 'tesseract 5.5.3', '')):
            rows = app.diagnostics(layout, check_connections=False)
        matches = [r for r in rows if r['name'] == 'OCR 환경 지문']
        assert matches, '파일 존재와 별개로 실행·언어 준비 상태를 검사해야 한다'
        assert not matches[0]['ok']
        assert qa_dialogs.diagnostic_state(matches[0]) == 'FAIL'
        assert 'PC별 설정' in matches[0]['fix']
        assert 'private failure' not in matches[0]['detail']


def failure(tmp_path, name, wanted='HVL', reason='ambiguous', attempts=4):
    folder = tmp_path / 'Evidence' / 'OCR' / name
    folder.mkdir(parents=True)
    (folder / 'selection.json').write_text(json.dumps({
        'wanted': wanted, 'reason': reason, 'attempts': attempts,
        'reads': [{'text': 'PRIVATE_PATIENT'}]}))
    return folder


def test_recent_failure_flows_through_diagnostics_without_patient_text(tmp_path):
    layout, _ = setup_layout(tmp_path)
    old = failure(tmp_path, 'old')
    recent = failure(tmp_path, 'recent', wanted='PRIVATE_PATIENT', reason='unreadable')
    os.utime(old / 'selection.json', (1, 1))
    with patch('core.ocr_runtime.subprocess.run', return_value=
               subprocess.CompletedProcess([], 0, 'tesseract 5.5.3', '')):
        rows = app.diagnostics(layout, check_connections=False)
    matches = [r for r in rows if r['name'] == '최근 OCR 선택 실패']
    assert matches, '실패 증거가 있으면 준비 점검에서 다음 행동을 안내해야 한다'
    row = matches[0]
    assert qa_dialogs.diagnostic_state(row) == 'WARN'
    assert '읽기 실패' in row['detail'] and '4회' in row['detail']
    assert 'PRIVATE_PATIENT' not in json.dumps(row)
    assert row['evidence_dir'] == str(recent.resolve())
    assert '배율' in row['fix'] and '증거' in row['fix']
    assert (old / 'selection.json').is_file()


def test_evidence_open_accepts_only_existing_local_evidence_folder(tmp_path):
    allowed = failure(tmp_path, 'local')
    opener = getattr(qa_dialogs, 'open_ocr_evidence', None)
    assert callable(opener), 'GUI에서 제한된 증거 폴더 열기 경로가 필요하다'
    with patch.object(qa_dialogs.os, 'startfile', create=True) as opened:
        opener(tmp_path, {'evidence_dir': str(allowed)})
        opened.assert_called_once_with(str(allowed.resolve()))
        with pytest.raises(ValueError):
            opener(tmp_path, {'evidence_dir': str(tmp_path)})
        with pytest.raises(ValueError):
            opener(tmp_path, {'evidence_dir': str(allowed / 'missing')})


def test_malformed_failure_is_safe_and_does_not_hide_valid_older_failure(tmp_path):
    layout, _ = setup_layout(tmp_path)
    valid = failure(tmp_path, 'valid')
    invalid = failure(tmp_path, 'invalid')
    (invalid / 'selection.json').write_text('{not-json')
    os.utime(valid / 'selection.json', (1, 1))
    with patch('core.ocr_runtime.subprocess.run', return_value=
               subprocess.CompletedProcess([], 0, 'tesseract 5.5.3', '')):
        rows = app.diagnostics(layout, check_connections=False)
    found = [r for r in rows if r['name'] == '최근 OCR 선택 실패']
    assert found, '읽을 수 있는 최근 실패는 손상된 파일과 독립적으로 안내해야 한다'
    assert 'HVL' in found[0]['detail']
    assert found[0]['evidence_dir'] == str(valid.resolve())


def test_existing_diagnostics_dialog_renders_warning_and_opens_selected_evidence(tmp_path, monkeypatch):
    """Tk 위젯 경계만 대체해 기존 창의 상태 표시·버튼 callback 연결을 실행한다."""
    import tkinter as tk
    from tkinter import ttk
    from types import SimpleNamespace
    layout, _ = setup_layout(tmp_path)
    folder = failure(tmp_path, 'selected')
    buttons, rendered = {}, []

    class Widget:
        def __init__(self, *args, **kwargs):
            self.choice = ()
            if 'command' in kwargs:
                buttons[kwargs.get('text')] = kwargs['command']

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

        def get_children(self):
            return ()

        def insert(self, *args, **kwargs):
            rendered.append(kwargs['values'])
            return str(len(rendered))

        def selection_set(self, key):
            self.choice = (key,)

        def selection(self):
            return self.choice

    monkeypatch.setattr(tk, 'Toplevel', Widget)
    monkeypatch.setattr(tk, 'StringVar', lambda **kwargs: SimpleNamespace(set=lambda value: None))
    for name in ('Frame', 'Treeview', 'Label', 'Button'):
        monkeypatch.setattr(ttk, name, Widget)
    # Feed the real diagnostic producer's rows into the existing GUI flow.
    with patch('core.ocr_runtime.subprocess.run', return_value=
               subprocess.CompletedProcess([], 0, 'tesseract 5.5.3', '')):
        produced = app.diagnostics(layout, check_connections=False)
    rows = [row for row in produced if row['name'] == '최근 OCR 선택 실패']
    assert rows
    with patch.object(app, 'diagnostics', return_value=rows), \
         patch.object(qa_dialogs.os, 'startfile', create=True) as opened:
        qa_dialogs.show_diagnostics(None, layout, lambda: None)
        assert rendered[0][0] == 'WARN'
        buttons['OCR 실패 증거 폴더 열기']()
        opened.assert_called_once_with(str(folder.resolve()))
