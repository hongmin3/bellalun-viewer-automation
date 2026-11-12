"""REQ-WU-002: 원자적 저장점 교체의 Windows 공유 충돌만 제한 재시도한다."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from core import wu_chain


def checkpoint(tmp_path):
    cp = wu_chain.Checkpoint(str(tmp_path/'checkpoint.json'), 'synthetic-chain')
    cp.save()
    return cp


def windows_error(code):
    error = PermissionError(13, 'synthetic Windows lock')
    error.winerror = code
    return error


@pytest.mark.parametrize('code', [5, 32, 33])
def test_temporary_windows_lock_retries_same_complete_payload(tmp_path, code):
    cp = checkpoint(tmp_path)
    cp.payload['extras']['synthetic'] = {'result': 'new complete value'}
    replace = os.replace
    calls = []
    def locked_twice(source, target):
        calls.append((source, target))
        if len(calls) < 3:
            raise windows_error(code)
        replace(source, target)
    with patch.object(wu_chain.os, 'replace', side_effect=locked_twice), patch.object(wu_chain.time, 'sleep') as sleep:
        cp.save()
    assert len(calls) == 3 and len({x[0] for x in calls}) == 1
    assert [x.args[0] for x in sleep.call_args_list] == [.05, .1]
    assert wu_chain.Checkpoint.load(cp.path, cp.identity).payload['extras']['synthetic']['result'] == 'new complete value'
    assert not list(tmp_path.glob('*.tmp'))


def test_persistent_lock_is_bounded_and_keeps_old_checkpoint(tmp_path):
    cp = checkpoint(tmp_path)
    before = Path(cp.path).read_bytes()
    cp.payload['extras']['unsaved'] = True
    with patch.object(wu_chain.os, 'replace', side_effect=windows_error(5)) as replace, patch.object(wu_chain.time, 'sleep') as sleep:
        with pytest.raises(PermissionError):
            cp.save()
    assert replace.call_count == 8
    assert len(sleep.call_args_list) == 7
    assert max(x.args[0] for x in sleep.call_args_list) <= .4
    assert sum(x.args[0] for x in sleep.call_args_list) < 2
    assert Path(cp.path).read_bytes() == before
    assert not list(tmp_path.glob('*.tmp'))


def test_other_file_errors_are_not_retried(tmp_path):
    cp = checkpoint(tmp_path)
    with patch.object(wu_chain.os, 'replace', side_effect=FileNotFoundError('synthetic missing')) as replace, patch.object(wu_chain.time, 'sleep') as sleep:
        with pytest.raises(FileNotFoundError):
            cp.save()
    assert replace.call_count == 1
    sleep.assert_not_called()


@pytest.mark.skipif(os.name != 'nt', reason='Windows 파일 공유 계약')
def test_real_windows_reader_blocks_replace_then_release_allows_save(tmp_path):
    import ctypes
    import threading
    from ctypes import wintypes
    cp = checkpoint(tmp_path)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(cp.path, 0x80000000, 1, None, 3, 0, None)
    assert handle not in (None, ctypes.c_void_p(-1).value)
    released = threading.Event()
    def release():
        kernel.CloseHandle(handle)
        released.set()
    timer = threading.Timer(.12, release)
    try:
        probe = tmp_path/'probe.tmp'
        probe.write_text('synthetic', encoding='utf-8')
        with pytest.raises(OSError) as blocked:
            os.replace(probe, cp.path)
        assert blocked.value.winerror in (5, 32, 33)
        probe.unlink()
        cp.payload['extras']['real_reader_released'] = True
        timer.start()
        cp.save()
    finally:
        if timer.ident is None:
            release()
        else:
            timer.join()
    assert released.is_set()
    assert wu_chain.Checkpoint.load(cp.path, cp.identity).payload['extras']['real_reader_released']
