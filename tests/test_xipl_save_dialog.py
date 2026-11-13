"""Native filename entry must stay inside the Studio-owned Save As dialog."""
from types import SimpleNamespace
import pytest
from core.xipl import XiplStudio


def test_filename_write_uses_native_edit_without_physical_input(monkeypatch, tmp_path):
    from core import xipl
    calls = []
    state = {'text': 'old.pim'}
    native = SimpleNamespace(SendMessageW=lambda hwnd, msg, w, value:
        (calls.append((hwnd, msg)), state.update(text=value.value), 1)[-1])
    monkeypatch.setattr(xipl.ctypes, 'windll', SimpleNamespace(user32=native))
    studio = object.__new__(XiplStudio)
    studio.ui = SimpleNamespace(get_text=lambda edit: state['text'])
    edit = SimpleNamespace(hwnd=11)
    target = str(tmp_path / 'TEST_CHANGED.pim')
    studio._set_save_filename(edit, target)
    assert state['text'] == target
    assert calls == [(11, 0x000C)]


@pytest.mark.parametrize('accepted,text', [(0, 'old.pim'), (0, 'TEST_CHANGED.pim'), (1, 'old.pim'), (1, '')])
def test_filename_write_rejects_failed_or_wrong_readback(monkeypatch, accepted, text):
    from core import xipl
    native = SimpleNamespace(SendMessageW=lambda *args: accepted)
    monkeypatch.setattr(xipl.ctypes, 'windll', SimpleNamespace(user32=native))
    studio = object.__new__(XiplStudio)
    studio.ui = SimpleNamespace(get_text=lambda edit: text)
    with pytest.raises(RuntimeError, match='파일명'):
        studio._set_save_filename(SimpleNamespace(hwnd=11), 'TEST_CHANGED.pim')


def test_dialog_owner_chain_must_reach_studio(monkeypatch):
    from core import xipl
    pids = {10: 500, 20: 500, 30: 42, 90: 999}
    owners = {10: 20, 20: 30, 30: 0, 90: 0}
    def get_pid(hwnd, output):
        output._obj.value = pids[hwnd]
        return 1
    native = SimpleNamespace(GetWindowThreadProcessId=get_pid,
        GetWindow=lambda hwnd, flag: owners[hwnd])
    monkeypatch.setattr(xipl.ctypes, 'windll', SimpleNamespace(user32=native))
    studio = object.__new__(XiplStudio)
    studio.ui = SimpleNamespace(pid=42)
    assert studio._owns_dialog(10)
    assert not studio._owns_dialog(90)
    owners[20] = 10
    assert not studio._owns_dialog(10), 'cyclic foreign ownership must terminate and reject'


@pytest.mark.parametrize('mode', ['owned', 'foreign', 'ambiguous', 'wrong_readback', 'open_dialog'])
def test_save_as_checks_ownership_uniqueness_and_readback_before_saving(monkeypatch, tmp_path, mode):
    from core import xipl
    calls = []
    state = {'text': 'old.pim', 'closed': False}
    def message(hwnd, msg, w, value):
        calls.append((hwnd, msg))
        if msg == 0x000C:
            if mode != 'wrong_readback':
                state['text'] = value.value
            return 1
        if msg == 0x00F5:
            state['closed'] = True
        return 1
    def class_name(hwnd, buf, size):
        buf.value = '#32770'
    native = SimpleNamespace(EnumWindows=lambda callback, arg:
        [callback(h, arg) for h in (10, 90)],
        GetClassNameW=class_name, IsWindowVisible=lambda h: True,
        SendMessageW=message, IsWindow=lambda h: not state['closed'])
    monkeypatch.setattr(xipl.ctypes, 'windll', SimpleNamespace(user32=native))
    monkeypatch.setattr(xipl.time, 'sleep', lambda s: None)
    def nodes(hwnd, depth):
        return [SimpleNamespace(hwnd=hwnd+1,ctrl_id=1001,cls='Edit',visible=True),
                SimpleNamespace(hwnd=hwnd+2,ctrl_id=1,cls='Button',visible=True,
                    text='열기(&O)' if mode == 'open_dialog' else '저장(&S)')]
    monkeypatch.setattr(xipl, 'children', nodes)
    studio = object.__new__(XiplStudio)
    studio.ui = SimpleNamespace(get_text=lambda edit: state['text'])
    monkeypatch.setattr(studio, '_uia_invoke_named', lambda *a: True)
    monkeypatch.setattr(studio, '_owns_dialog', lambda h:
        mode != 'foreign' and (h == 10 or mode == 'ambiguous'))
    target = tmp_path / 'TEST_CHANGED.pim'
    if mode == 'owned':
        studio.save_as(str(target), wait=0, settle=0, dialog_timeout=0)
        assert calls == [(11, 0x000C), (12, 0x00F5)]
        assert state['text'] == str(target)
    else:
        with pytest.raises(RuntimeError):
            studio.save_as(str(target), wait=0, settle=0, dialog_timeout=0)
        assert not any(msg == 0x00F5 for hwnd, msg in calls)
        if mode in ('foreign', 'ambiguous'):
            assert calls == []
