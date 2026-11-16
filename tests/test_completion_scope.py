"""단독 결과를 전체 회귀 완료로 오인하지 않도록 표시 범위를 검사한다."""
import run


def test_single_completion_uses_its_own_scope(capsys,monkeypatch):
    monkeypatch.setenv('BELLALUN_EXTERNAL_GUARD','1')
    run.announce_done([],0,{},label='단독 시험')
    output=capsys.readouterr().out
    assert '단독 시험 완료' in output
    assert '전체 회귀 완료' not in output


def test_selected_regression_console_line_is_selected_run(capsys, monkeypatch):
    """REQ-SPEEDUP-002 표시: 선택 실행의 콘솔 요약 줄은 '선택 실행 완료'다."""
    from types import SimpleNamespace
    monkeypatch.setenv('BELLALUN_EXTERNAL_GUARD', '1')
    run.announce_done([], 0, {}, label=run.regression_label(SimpleNamespace(run_scope='selected')))
    output = capsys.readouterr().out
    assert '선택 실행 완료' in output
    assert '전체 회귀 완료' not in output
    assert run.regression_label(SimpleNamespace()) == '전체 회귀'
    assert run.regression_label(SimpleNamespace(run_scope='combined')) == '전체 회귀'


def test_gui_supervisor_finish_line_follows_scope():
    from bellalunauto import app
    assert app.finish_label('selected') == '선택 실행 종료'
    assert app.finish_label(None) == '전체 실행 종료'


def test_regression_chain_uses_scope_label_not_fixed_full_label():
    """run-regression 완료 알림 호출이 범위 라벨을 쓰는지 소스로 확인한다."""
    import inspect
    source = inspect.getsource(run)
    assert 'announce_done(results, elapsed, LAST_REPORT_PATHS)\n' not in source
    assert source.count('label=regression_label(ctx)') >= 2
    import bellalunauto.app as app
    app_source = inspect.getsource(app)
    assert "'BellalunAuto 전체 실행 종료'" not in app_source
    assert '전체 실행 종료: ' not in app_source
