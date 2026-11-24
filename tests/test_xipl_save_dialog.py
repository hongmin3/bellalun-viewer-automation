"""Native filename entry must stay inside the Studio-owned Save As dialog.

Validates: REQ-REGRESSION-001, REQ-VERDICT-006
"""
from types import SimpleNamespace
import pytest
from core import xipl
from core.xipl import XiplStudio

WM_SETTEXT, EM_SETSEL, WM_CHAR, BM_CLICK = 0x000C, 0x00B1, 0x0102, 0x00F5
OVERWRITE_TEXT = ("'C:\\XIPL\\PARAMETER\\TEST_2D_FLOW_M.pim'이(가) 이미 있습니다.\n"
                  "바꾸시겠습니까?")   # 2026-11-24 1.0.0.008 WU 회차의 실제 문구


class FakeEdit:
    """파일명 Edit: EM_SETSEL(전체 선택) 뒤 WM_CHAR 로 들어온 글자가 선택을 바꾼다."""

    def __init__(self, text='old.pim', hwnd=11, answer=True, drop_chars=False):
        self.text, self.hwnd, self.answer, self.drop_chars = text, hwnd, answer, drop_chars
        self.selected, self.calls, self.closed, self.flags = False, [], False, None

    def timed(self, hwnd, msg, w, l, flags, timeout, result):
        self.calls.append((hwnd, msg))
        self.flags = (flags, timeout)
        if not self.answer:
            return 0
        if msg == EM_SETSEL and hwnd == self.hwnd:
            self.selected = True
        result._obj.value = 1
        return 1

    def post(self, hwnd, msg, w, l):
        self.calls.append((hwnd, msg))
        if msg == WM_CHAR and hwnd == self.hwnd and not self.drop_chars:
            if self.selected:
                self.text, self.selected = '', False
            self.text += chr(w)
        if msg == BM_CLICK and hwnd == 12:
            self.closed = True
        return 1


def _studio(monkeypatch, fake, **native):
    user32 = SimpleNamespace(SendMessageTimeoutW=fake.timed, PostMessageW=fake.post,
                             SendMessageW=lambda *a: pytest.fail('동기 SendMessageW 를 쓰면 안 된다'),
                             **native)
    monkeypatch.setattr(xipl.ctypes, 'windll', SimpleNamespace(user32=user32))
    monkeypatch.setattr(xipl.time, 'sleep', lambda s: None)
    clock = iter(range(0, 1000000))
    monkeypatch.setattr(xipl.time, 'time', lambda: next(clock))
    studio = object.__new__(XiplStudio)
    studio.ui = SimpleNamespace(get_text=lambda edit: fake.text)
    return studio


def test_filename_is_typed_so_the_dialog_sees_the_change(monkeypatch, tmp_path):
    """WM_SETTEXT 만으로는 저장 대화상자가 처음 이름으로 저장하려 했다(2026-11-24 실측)."""
    fake = FakeEdit()
    studio = _studio(monkeypatch, fake)
    target = str(tmp_path / 'TEST_CHANGED.pim')
    studio._set_save_filename(SimpleNamespace(hwnd=11), target)
    assert fake.text == target
    assert fake.calls[0] == (11, EM_SETSEL)
    assert fake.calls[1:] == [(11, WM_CHAR)] * len(target)
    assert all(msg != WM_SETTEXT for _, msg in fake.calls)
    assert fake.flags == (0x0002, xipl.SEND_TIMEOUT_MS)


@pytest.mark.parametrize('kwargs', [dict(answer=False), dict(drop_chars=True),
                                    dict(text='', drop_chars=True)],
                         ids=['edit-does-not-answer', 'chars-not-accepted', 'empty-and-not-accepted'])
def test_filename_write_rejects_failed_or_wrong_readback(monkeypatch, kwargs):
    fake = FakeEdit(**kwargs)
    studio = _studio(monkeypatch, fake)
    with pytest.raises(RuntimeError, match='파일명'):
        studio._set_save_filename(SimpleNamespace(hwnd=11), 'TEST_CHANGED.pim')


def test_dialog_owner_chain_must_reach_studio(monkeypatch):
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


def _native(fake, handles=(10,), prompt_after_click=None, closes=True):
    def class_name(hwnd, buf, size):
        buf.value = '#32770'

    def windows(callback, arg):
        clicked = any(m == BM_CLICK for _, m in fake.calls)
        for h in handles + ((prompt_after_click,) if prompt_after_click and clicked else ()):
            if callback(h, arg) is False:
                break
    return dict(EnumWindows=windows, GetClassNameW=class_name, IsWindowVisible=lambda h: True,
                GetWindowTextW=lambda h, buf, n: setattr(buf, 'value', '다른 이름으로 저장'),
                IsWindow=(lambda h: not fake.closed) if closes else (lambda h: True))


def _nodes(mode='owned', static=None):
    def nodes(hwnd, depth):
        if hwnd == 50:   # 덮어쓰기 확인 창
            return [SimpleNamespace(hwnd=51, ctrl_id=6, cls='Button', visible=True, text='예(&Y)'),
                    SimpleNamespace(hwnd=52, ctrl_id=7, cls='Button', visible=True, text='아니요(&N)'),
                    SimpleNamespace(hwnd=53, ctrl_id=65535, cls='Static', visible=True, text=OVERWRITE_TEXT)]
        rows = [SimpleNamespace(hwnd=hwnd + 1, ctrl_id=1001, cls='Edit', visible=True, text=''),
                SimpleNamespace(hwnd=hwnd + 2, ctrl_id=1, cls='Button', visible=True,
                                text='열기(&O)' if mode == 'open_dialog' else '저장(&S)')]
        if static:
            rows.append(SimpleNamespace(hwnd=hwnd + 3, ctrl_id=65535, cls='Static', visible=True, text=static))
        return rows
    return nodes


@pytest.mark.parametrize('mode', ['owned', 'foreign', 'ambiguous', 'wrong_readback', 'open_dialog'])
def test_save_as_checks_ownership_uniqueness_and_readback_before_saving(monkeypatch, tmp_path, mode):
    fake = FakeEdit(drop_chars=mode == 'wrong_readback')
    studio = _studio(monkeypatch, fake, **_native(fake, handles=(10, 90)))
    monkeypatch.setattr(xipl, 'children', _nodes(mode))
    monkeypatch.setattr(studio, '_uia_invoke_named', lambda *a: True)
    monkeypatch.setattr(studio, '_owns_dialog', lambda h:
        mode != 'foreign' and (h == 10 or mode == 'ambiguous'))
    target = tmp_path / 'TEST_CHANGED.pim'
    if mode == 'owned':
        studio.save_as(str(target), wait=0, settle=0, dialog_timeout=0)
        assert fake.calls[-1] == (12, BM_CLICK)
        assert fake.text == str(target)
    else:
        with pytest.raises(RuntimeError):
            studio.save_as(str(target), wait=0, settle=0, dialog_timeout=0)
        assert not any(msg == BM_CLICK for _, msg in fake.calls)
        if mode in ('foreign', 'ambiguous'):
            assert fake.calls == []


def test_unexpected_overwrite_prompt_is_answered_no_and_reported(monkeypatch, tmp_path):
    """실행 전에 지운 파일 대신 다른 파일 덮어쓰기를 물으면 [아니요]로 닫고 실패한다.

    1.0.0.007 은 이 확인 창 때문에 12.3시간 멈췄다.
    """
    fake = FakeEdit()
    studio = _studio(monkeypatch, fake, **_native(fake, prompt_after_click=50, closes=False))
    monkeypatch.setattr(xipl, 'children', _nodes())
    monkeypatch.setattr(studio, '_uia_invoke_named', lambda *a: True)
    monkeypatch.setattr(studio, '_owns_dialog', lambda h: h in (10, 50))
    with pytest.raises(RuntimeError, match='덮어쓰기 확인.*아니요.*TEST_2D_FLOW_M'):
        studio.save_as(str(tmp_path / 'TEST_XIPL_SAVED_M.pim'), wait=0, settle=0, dialog_timeout=0)
    assert (52, BM_CLICK) in fake.calls and (51, BM_CLICK) not in fake.calls


def test_save_click_is_posted_and_unclosed_dialog_is_reported(monkeypatch, tmp_path):
    """저장 누름은 기다리지 않고 보내고, 닫히지 않으면 남은 창 문구와 함께 실패한다."""
    fake = FakeEdit()
    studio = _studio(monkeypatch, fake, **_native(fake, closes=False))
    monkeypatch.setattr(xipl, 'children', _nodes(static='경로를 찾을 수 없습니다.'))
    monkeypatch.setattr(studio, '_uia_invoke_named', lambda *a: True)
    monkeypatch.setattr(studio, '_owns_dialog', lambda h: h == 10)
    with pytest.raises(RuntimeError, match='닫히지 않았습니다.*다른 이름으로 저장.*경로를 찾을 수 없습니다'):
        studio.save_as(str(tmp_path / 'X.pim'), wait=0, settle=0, dialog_timeout=0, close_timeout=1)
    assert [c for c in fake.calls if c[1] == BM_CLICK] == [(12, BM_CLICK)]
