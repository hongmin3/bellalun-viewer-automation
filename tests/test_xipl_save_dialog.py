"""Native filename entry must stay inside the Studio-owned Save As dialog."""
from types import SimpleNamespace
import pytest
from core.xipl import XiplStudio


def test_filename_write_uses_native_edit_without_physical_input(monkeypatch, tmp_path):
    from core import xipl
    calls = []
    state = {'text': 'old.pim'}
    def timed(hwnd, msg, w, value, flags, timeout, result):
        calls.append((hwnd, msg))
        state.update(text=value.value)
        result._obj.value = 1
        return 1
    native = SimpleNamespace(SendMessageTimeoutW=timed)
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
    def timed(hwnd, msg, w, value, flags, timeout, result):
        result._obj.value = accepted
        return 1
    native = SimpleNamespace(SendMessageTimeoutW=timed)
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
        SendMessageTimeoutW=lambda h, m, w, v, flags, timeout, result:
            setattr(result._obj, 'value', message(h, m, w, v)) or 1,
        PostMessageW=message, IsWindow=lambda h: not state['closed'])
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


def test_filename_write_gives_up_when_dialog_does_not_answer(monkeypatch):
    """REQ-VERDICT-006: 응답 없는 창에 보낸 WM_SETTEXT 는 시간 상한 뒤 실패로 돌아온다."""
    from core import xipl
    seen = {}
    def timed(hwnd, msg, w, value, flags, timeout, result):
        seen.update(flags=flags, timeout=timeout)
        return 0          # 시간 초과 또는 응답 없음
    monkeypatch.setattr(xipl.ctypes, 'windll', SimpleNamespace(user32=SimpleNamespace(SendMessageTimeoutW=timed)))
    studio = object.__new__(XiplStudio)
    studio.ui = SimpleNamespace(get_text=lambda edit: 'old.pim')
    with pytest.raises(RuntimeError, match='파일명'):
        studio._set_save_filename(SimpleNamespace(hwnd=11), 'TEST_CHANGED.pim')
    assert seen == {'flags': 0x0002, 'timeout': xipl.SEND_TIMEOUT_MS}


def test_save_click_is_posted_and_unclosed_dialog_is_reported(monkeypatch, tmp_path):
    """REQ-VERDICT-006: 저장 누름은 기다리지 않고 보내고, 닫히지 않으면 남은 창 문구와 함께 실패한다.

    1.0.0.007 회귀에서 SendMessageW(BM_CLICK)이 저장 뒤 뜬 창 때문에 12.3시간 돌아오지 않았다.
    """
    from core import xipl
    posted, sent = [], []
    state = {'text': 'old.pim'}
    def class_name(hwnd, buf, size):
        buf.value = '#32770'
    def timed(h, m, w, v, flags, timeout, result):
        sent.append((h, m))
        state['text'] = v.value
        result._obj.value = 1
        return 1
    native = SimpleNamespace(EnumWindows=lambda callback, arg: [callback(h, arg) for h in (10,)],
        GetClassNameW=class_name, IsWindowVisible=lambda h: True,
        GetWindowTextW=lambda h, buf, n: setattr(buf, 'value', 'Confirm Save As'),
        SendMessageTimeoutW=timed,
        SendMessageW=lambda *a: pytest.fail('동기 SendMessageW 를 쓰면 안 된다'),
        PostMessageW=lambda h, m, w, l: posted.append((h, m)) or 1,
        IsWindow=lambda h: True)
    monkeypatch.setattr(xipl.ctypes, 'windll', SimpleNamespace(user32=native))
    monkeypatch.setattr(xipl.time, 'sleep', lambda s: None)
    clock = iter(range(0, 10000, 5))
    monkeypatch.setattr(xipl.time, 'time', lambda: next(clock))
    monkeypatch.setattr(xipl, 'children', lambda hwnd, depth: [
        SimpleNamespace(hwnd=hwnd + 1, ctrl_id=1001, cls='Edit', visible=True, text=''),
        SimpleNamespace(hwnd=hwnd + 2, ctrl_id=1, cls='Button', visible=True, text='저장(&S)'),
        SimpleNamespace(hwnd=hwnd + 3, ctrl_id=65535, cls='Static', visible=True, text='이미 있습니다. 바꾸시겠습니까?')])
    studio = object.__new__(XiplStudio)
    studio.ui = SimpleNamespace(get_text=lambda edit: state['text'])
    monkeypatch.setattr(studio, '_uia_invoke_named', lambda *a: True)
    monkeypatch.setattr(studio, '_owns_dialog', lambda h: h == 10)
    with pytest.raises(RuntimeError, match='닫히지 않았습니다.*Confirm Save As.*바꾸시겠습니까'):
        studio.save_as(str(tmp_path / 'X.pim'), wait=0, settle=0, dialog_timeout=0, close_timeout=1)
    assert posted == [(12, 0x00F5)]
    assert sent == [(11, 0x000C)]
