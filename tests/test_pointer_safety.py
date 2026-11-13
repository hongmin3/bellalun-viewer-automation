"""모든 물리 포인터 경로가 실제 대상 창을 검증한다."""
from contextlib import ExitStack
from unittest import mock
import pytest
from core import ui


METHODS = ['click', 'double_click', 'right_click', 'hover', 'wheel', 'drag']


def invoke(driver, method, target):
    if method == 'drag':
        return driver.drag(target, (30, 10), duration=.12, settle=0)
    if method == 'wheel':
        return driver.wheel(target, 1, settle=0)
    return getattr(driver, method)(target, settle=0)


@pytest.fixture
def native():
    driver = ui.ViewerUi.__new__(ui.ViewerUi)
    # pid 속성을 통한 실제 프로세스 조회를 막는다.
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(ui.ViewerUi, 'pid', new_callable=mock.PropertyMock, return_value=42))
        for name, value in [('IsWindow', True), ('IsWindowVisible', True), ('GetDlgCtrlID', 1)]:
            stack.enter_context(mock.patch.object(ui.u32, name, return_value=value))
        stack.enter_context(mock.patch.object(ui._u32p, 'GetAncestor', return_value=100))
        stack.enter_context(mock.patch.object(ui, '_class_of', return_value='Button'))
        stack.enter_context(mock.patch.object(ui, '_rect_of', return_value=(0, 0, 20, 20)))
        stack.enter_context(mock.patch.object(ui, '_pid_of', return_value=42))
        stack.enter_context(mock.patch.object(ui, '_window_at_point', return_value=100))
        stack.enter_context(mock.patch.object(ui.time, 'sleep'))
        driver.require_front_for_pointer = mock.Mock(return_value=True)
        mouse = stack.enter_context(mock.patch.object(ui.u32, 'mouse_event'))
        cursor = stack.enter_context(mock.patch.object(ui.u32, 'SetCursorPos'))
        yield driver, mouse, cursor


@pytest.mark.parametrize('method', METHODS)
def test_same_pid_other_root_covering_control_never_receives_input(native, method):
    driver, mouse, cursor = native
    target = ui.Control(11, 1, 'Button', 'Go', (0, 0, 20, 20), True, 1)
    with mock.patch.object(ui, '_window_at_point', return_value=200):
        with pytest.raises(ui.ForegroundError):
            invoke(driver, method, target)
    mouse.assert_not_called()
    cursor.assert_not_called()


@pytest.mark.parametrize('method', METHODS)
def test_foreign_point_never_receives_input_even_if_viewer_foreground(native, method):
    driver, mouse, cursor = native
    with mock.patch.object(ui, '_pid_of', side_effect=lambda h: 99 if h == 200 else 42), \
         mock.patch.object(ui, '_window_at_point', return_value=200):
        with pytest.raises(ui.ForegroundError):
            invoke(driver, method, (10, 10))
    mouse.assert_not_called()
    cursor.assert_not_called()


@pytest.mark.parametrize('method', METHODS)
@pytest.mark.parametrize('changed', ['lost', 'hidden', 'pid', 'rect', 'class', 'id'])
def test_lost_or_replaced_control_is_rejected_before_cursor_moves(native, method, changed):
    driver, mouse, cursor = native
    target = ui.Control(11, 1, 'Button', 'Go', (0, 0, 20, 20), True, 1)
    owner, name, value = {
        'lost': (ui.u32, 'IsWindow', False),
        'hidden': (ui.u32, 'IsWindowVisible', False),
        'pid': (ui, '_pid_of', 99),
        'rect': (ui, '_rect_of', (1, 0, 21, 20)),
        'class': (ui, '_class_of', 'Edit'),
        'id': (ui.u32, 'GetDlgCtrlID', 2),
    }[changed]
    with mock.patch.object(owner, name, return_value=value):
        with pytest.raises(ui.ForegroundError):
            invoke(driver, method, target)
    mouse.assert_not_called()
    cursor.assert_not_called()


@pytest.mark.parametrize('method', METHODS)
def test_control_move_after_cursor_positioning_never_sends_action(native, method):
    driver, mouse, cursor = native
    target = ui.Control(11, 1, 'Button', 'Go', (0, 0, 20, 20), True, 1)
    moved = False
    def position(*args):
        nonlocal moved
        moved = True
    cursor.side_effect = position
    with mock.patch.object(ui, '_rect_of', side_effect=lambda h: (1, 0, 21, 20) if moved else target.rect):
        with pytest.raises(ui.ForegroundError):
            invoke(driver, method, target)
    mouse.assert_not_called()


def test_control_root_change_during_recovery_is_rejected(native):
    driver, mouse, cursor = native
    target = ui.Control(11, 1, 'Button', 'Go', (0, 0, 20, 20), True, 1)
    with mock.patch.object(ui._u32p, 'GetAncestor', side_effect=[100, 200]):
        with pytest.raises(ui.ForegroundError, match='최상위 창'):
            driver.click(target)
    mouse.assert_not_called()
    cursor.assert_not_called()


@pytest.mark.parametrize('initial_hit', [900, 100])
@pytest.mark.parametrize('method', METHODS)
def test_real_click_guard_and_recovery_activate_control_popup_root_only(native, method, initial_hit):
    """메인 프레임 뒤의 팝업도 실제 세 메서드 연결로 회복한다."""
    driver, mouse, cursor = native
    del driver.require_front_for_pointer  # 실제 require_front → bring_to_front 사용
    driver.main_window = mock.Mock(return_value=mock.Mock(hwnd=100))
    driver.blocking_window = mock.Mock(return_value={'hwnd': 900, 'pid': 99})
    driver.is_foreground = mock.Mock(return_value=False)
    target = ui.Control(11, 1, 'Button', 'Popup action', (0, 0, 20, 20), True, 1)
    hit = initial_hit
    activated = []
    def activate(hwnd):
        nonlocal hit
        activated.append(hwnd)
        hit = hwnd
    with mock.patch.object(ui._u32p, 'GetAncestor', return_value=200), \
         mock.patch.object(ui, '_window_at_point', side_effect=lambda p: hit), \
         mock.patch.object(ui, '_pid_of', side_effect=lambda h: 99 if h == 900 else 42), \
         mock.patch.object(ui, 'force_foreground', side_effect=activate), \
         mock.patch.object(ui, 'switch_to_window', side_effect=activate), \
         mock.patch.object(ui, 'push_window_back') as foreign_move, \
         mock.patch.object(ui, 'nudge_foreground_input') as foreign_key:
        invoke(driver, method, target)
    assert activated == [200]
    driver.main_window.assert_not_called()
    foreign_move.assert_not_called()
    foreign_key.assert_not_called()


def test_real_recovery_rejects_expected_root_from_foreign_pid(native):
    driver, mouse, cursor = native
    del driver.require_front_for_pointer
    driver.main_window = mock.Mock(return_value=mock.Mock(hwnd=100))
    driver.blocking_window = mock.Mock(return_value={'hwnd': 900, 'pid': 99})
    with mock.patch.object(ui, '_window_at_point', return_value=900), \
         mock.patch.object(ui, '_pid_of', side_effect=lambda h: 99 if h in (200, 900) else 42), \
         mock.patch.object(ui, 'force_foreground') as activate, \
         mock.patch.object(ui, 'switch_to_window') as switch:
        with pytest.raises(ui.ForegroundError):
            driver.require_front_for_pointer(point=(10, 10), expected_root=200)
    activate.assert_not_called()
    switch.assert_not_called()
    driver.main_window.assert_not_called()
    mouse.assert_not_called()
    cursor.assert_not_called()


def test_drag_checks_destination_before_pressing(native):
    driver, mouse, cursor = native
    with mock.patch.object(ui, '_window_at_point', side_effect=lambda p: 200 if p == (30, 10) else 100), \
         mock.patch.object(ui, '_pid_of', side_effect=lambda h: 99 if h == 200 else 42):
        with pytest.raises(ui.ForegroundError):
            driver.drag((10, 10), (30, 10))
    mouse.assert_not_called()


def test_drag_releases_button_after_mid_drag_blocker_and_preserves_error(native):
    driver, mouse, cursor = native
    down = False
    def event(flags, *args):
        nonlocal down
        down = flags == ui.MOUSEEVENTF_LEFTDOWN
    mouse.side_effect = event
    with mock.patch.object(ui, '_window_at_point', side_effect=lambda p: 200 if down else 100), \
         mock.patch.object(ui, '_pid_of', side_effect=lambda h: 99 if h == 200 else 42):
        with pytest.raises(ui.ForegroundError):
            driver.drag((10, 10), (30, 10), duration=.12)
    assert [c.args[0] for c in mouse.call_args_list] == [ui.MOUSEEVENTF_LEFTDOWN, ui.MOUSEEVENTF_LEFTUP]


def test_drag_release_failure_does_not_replace_original_focus_error(native):
    driver, mouse, cursor = native
    down = False
    def event(flags, *args):
        nonlocal down
        if flags == ui.MOUSEEVENTF_LEFTUP:
            raise OSError('release failed')
        down = True
    mouse.side_effect = event
    with mock.patch.object(ui, '_window_at_point', side_effect=lambda p: 200 if down else 100), \
         mock.patch.object(ui, '_pid_of', side_effect=lambda h: 99 if h == 200 else 42):
        with pytest.raises(ui.ForegroundError, match='대상 창'):
            driver.drag((10, 10), (30, 10), duration=.12)
    assert mouse.call_args_list[-1].args[0] == ui.MOUSEEVENTF_LEFTUP


@pytest.mark.parametrize('control', [False, True])
@pytest.mark.parametrize('method,count', [('click', 2), ('double_click', 4), ('right_click', 2), ('wheel', 1), ('hover', 0), ('drag', 2)])
def test_safe_path_keeps_event_count(native, method, count, control):
    driver, mouse, cursor = native
    target = ui.Control(11, 1, 'Button', 'Go', (0, 0, 20, 20), True, 1) if control else (10, 10)
    invoke(driver, method, target)
    assert mouse.call_count == count
