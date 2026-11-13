"""UI를 조작하지 않는 호출 비용·저장 완료 Setting 닫기 계약."""
from types import SimpleNamespace

import pytest


def test_ui_lookup_keeps_all_candidates_and_collects_nested_cost(monkeypatch):
    from core import ui, performance
    driver = ui.ViewerUi()
    windows = [SimpleNamespace(hwnd=11), SimpleNamespace(hwnd=12)]
    controls = {
        11: [SimpleNamespace(hwnd=1, ctrl_id=4, visible=True),
             SimpleNamespace(hwnd=2, ctrl_id=4, visible=False)],
        12: [SimpleNamespace(hwnd=1, ctrl_id=4, visible=True),
             SimpleNamespace(hwnd=3, ctrl_id=4, visible=True)],
    }
    monkeypatch.setattr(driver, 'windows', lambda: windows)
    monkeypatch.setattr(ui, 'children', lambda hwnd, depth: controls[hwnd])
    with performance.collect_performance() as collector:
        found = driver.by_id(4)
    assert [control.hwnd for control in found] == [1, 3]
    operations = {row['name']: row for row in collector.snapshot()}
    assert operations['ui.by_id']['calls'] == 1
    assert operations['ui.controls']['calls'] == 1
    assert operations['ui.controls']['errors'] == 0


def test_performance_aggregates_exact_elapsed_and_keeps_original_exception():
    from core import performance
    clock = iter([1.0, 1.25, 2.0, 2.5])
    error = ValueError('private details must not be retained')
    with performance.collect_performance(clock=lambda: next(clock)) as collector:
        with performance.measure('operation'):
            pass
        with pytest.raises(ValueError) as caught:
            with performance.measure('operation'):
                raise error
    assert caught.value is error
    assert collector.snapshot() == [{'kind': 'performance', 'name': 'operation', 'calls': 2,
                                     'duration_seconds': .75, 'max_seconds': .5, 'errors': 1}]


def test_performance_collectors_do_not_leak_between_runs():
    from core import performance
    with performance.collect_performance() as first:
        with performance.measure('first'):
            pass
        with performance.collect_performance() as second:
            with performance.measure('second'):
                pass
        with performance.measure('first'):
            pass
    assert [(r['name'], r['calls']) for r in first.snapshot()] == [('first', 2)]
    assert [(r['name'], r['calls']) for r in second.snapshot()] == [('second', 1)]


@pytest.mark.parametrize('closed', [True, False])
def test_saved_setting_close_uses_shared_verified_close_and_stops_on_failure(closed, monkeypatch):
    from core import flows, ui as ui_module
    from tests import xipl_flows
    # 실제 공통 선택자를 사용한다. 이동한 Setting의 X가 1700 미만이어도 닫혀야 한다.
    state, clicked = {'open': True}, []
    window = SimpleNamespace(hwnd=100, cls='#32770', visible=True, rect=(100, 200, 1200, 1000))
    target = SimpleNamespace(ctrl_id=4, visible=True, rect=(1130, 210, 1170, 250))
    lower = SimpleNamespace(ctrl_id=4, visible=True, rect=(1130, 600, 1170, 640))
    rail = SimpleNamespace(ctrl_id=177, visible=True)
    def click(control, **kwargs):
        clicked.append(control)
        if control is target and closed:
            state['open'] = False
    ui = SimpleNamespace(windows=lambda: [window] if state['open'] else [],
                         main_window=lambda: window, by_id=lambda ctrl_id: [lower, target], click=click)
    monkeypatch.setattr(ui_module, 'children', lambda *args: [rail])
    # 모달이 없는 제품 경계만 대체한다. 저장 동의나 실제 입력은 발생하지 않는다.
    monkeypatch.setattr(flows, 'confirm_config_save', lambda *args, **kwargs: None)
    if closed:
        assert xipl_flows._close_saved_setting(ui) is True
        assert not state['open']
    else:
        with pytest.raises(flows.FlowError, match='Setting'):
            xipl_flows._close_saved_setting(ui)
        assert state['open']
    assert clicked == [target]
