"""Metadata 교체만 읽기 핸들 충돌을 제한 시간 안에서 재시도한다."""
import ctypes
from ctypes import wintypes
import errno
import json
import os
from pathlib import Path
import threading
import time

import pytest

from bellalunauto.runs import _write
from core.run_preservation import _write_json


def shared_reader(path):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(path), 0x80000000, 1 | 2 | 4, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return lambda: kernel.CloseHandle(handle)


@pytest.mark.skipif(os.name != 'nt', reason='실제 Windows 읽기 핸들 공유 계약')
@pytest.mark.parametrize('writer', [_write_json, _write], ids=['preservation', 'run-record'])
@pytest.mark.parametrize('reader_kind', ['ordinary', 'shared-delete'])
def test_real_metadata_writer_waits_for_reader_close(tmp_path, monkeypatch, writer, reader_kind):
    path = tmp_path / 'journal.json'
    before, after = {'state': 'before'}, {'state': 'after'}
    writer(path, before)
    if reader_kind == 'ordinary':
        reader = path.open('rb')
        close = reader.close
    else:
        close = shared_reader(path)
    conflict = threading.Event()
    replaced = []
    replace = os.replace
    def observed_replace(source, destination):
        replaced.append((Path(source), Path(destination)))
        try:
            return replace(source, destination)
        except OSError:
            conflict.set()
            raise
    monkeypatch.setattr(os, 'replace', observed_replace)
    def release_reader():
        conflict.wait(1)
        time.sleep(.05)
        close()
    release = threading.Thread(target=release_reader)
    release.start()
    try:
        writer(path, after)
    finally:
        release.join(2)
    assert not release.is_alive()
    if reader_kind == 'ordinary':
        assert conflict.is_set(), '실제 열린 읽기 핸들이 교체를 막는 경로를 실행해야 한다'
        assert len(replaced) >= 2
    assert len(set(replaced)) == 1
    assert json.loads(path.read_text(encoding='utf-8')) == after


@pytest.mark.skipif(os.name != 'nt', reason='실제 Windows 읽기 핸들 공유 계약')
@pytest.mark.parametrize('writer', [_write_json, _write], ids=['preservation', 'run-record'])
def test_real_metadata_writer_keeps_original_when_reader_stays_open(tmp_path, writer):
    path = tmp_path / 'journal.json'
    before = {'state': 'before'}
    writer(path, before)
    started = time.monotonic()
    with path.open('rb'):
        with pytest.raises(PermissionError) as caught:
            writer(path, {'state': 'after'})
        assert caught.value.winerror in {5, 32, 33}
        assert json.loads(path.read_text(encoding='utf-8')) == before
    assert 1.8 <= time.monotonic() - started < 4


@pytest.mark.parametrize('writer', [_write_json, _write], ids=['preservation', 'run-record'])
@pytest.mark.parametrize('winerror', [None, 2, 112])
def test_metadata_writer_does_not_retry_unrelated_error(tmp_path, monkeypatch, writer, winerror):
    path = tmp_path / 'journal.json'
    before = {'state': 'before'}
    writer(path, before)
    error = OSError(errno.EIO, 'synthetic unrelated failure')
    if winerror is not None:
        error.winerror = winerror
    calls = []
    def denied(*args):
        calls.append(args)
        raise error
    monkeypatch.setattr(os, 'replace', denied)
    with pytest.raises(OSError) as caught:
        writer(path, {'state': 'after'})
    assert caught.value is error
    assert len(calls) == 1
    assert json.loads(path.read_text(encoding='utf-8')) == before


@pytest.mark.skipif(os.name != 'nt', reason='Windows 오류만 재시도한다')
@pytest.mark.parametrize('winerror', [5, 32, 33])
def test_metadata_retry_uses_one_deadline_and_preserves_permanent_error(tmp_path, monkeypatch, winerror):
    from core import atomic_metadata
    source, destination = tmp_path / 'prepared.tmp', tmp_path / 'journal.json'
    source.write_text('prepared')
    destination.write_text('original')
    clock, pauses, replacements = [0.0], [], []
    error = PermissionError(errno.EACCES, 'synthetic permanent denial')
    error.winerror = winerror
    def denied(*args):
        replacements.append(args)
        raise error
    def sleep(seconds):
        pauses.append(seconds)
        clock[0] += seconds
    monkeypatch.setattr(atomic_metadata.os, 'replace', denied)
    monkeypatch.setattr(atomic_metadata.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(atomic_metadata.time, 'sleep', sleep)

    with pytest.raises(PermissionError) as caught:
        atomic_metadata.replace_metadata(source, destination)

    assert caught.value is error
    assert clock[0] == pytest.approx(2.0)
    assert all(0 < pause <= .05 for pause in pauses)
    assert set(replacements) == {(source, destination)}
    assert source.read_text() == 'prepared' and destination.read_text() == 'original'
