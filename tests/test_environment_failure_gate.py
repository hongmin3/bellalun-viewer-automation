import time
from types import SimpleNamespace

import pytest

import run


def test_explicit_current_log_warning_blocks_automation_exception(tmp_path, monkeypatch):
    log = tmp_path / 'viewer.log'
    from datetime import datetime
    log.write_text('', encoding='utf-8')
    monkeypatch.setattr(run, '_viewer_log_path', lambda ctx: str(log))
    def fail(ctx):
        log.write_text(datetime.now().strftime('[%Y/%m/%d %H:%M:%S]') +
                       ' SQL Server timeout expired\n', encoding='utf-8')
        raise RuntimeError('Unexpected dialog geometry')
    ctx = SimpleNamespace(cfg={}, root=str(tmp_path))
    rows = run.guarded(fail, ctx, 'TC_SYNTHETIC', 'fixture')
    assert rows[0].verdict == 'BLOCKED'
    assert ctx.execution_block['causes'][0]['category'] == 'sql-timeout'
    assert rows[0].as_dict()['cause_evidence'][0]['attribution'] == 'undetermined'


@pytest.mark.parametrize('caught', [False, True, 'cleanup-throw'],
                         ids=['entry', 'module-abort', 'cleanup-throw'])
def test_foreground_error_stops_real_chain_before_next_tc(monkeypatch, caught):
    from core.result import TCResult
    from core.ui import ForegroundError
    from tests.test_wu_chain import ChainResumeTests

    chain = ChainResumeTests()
    chain.setUp()
    original_stage = chain.stage

    def stage(tc_id):
        if tc_id != 'TC_A':
            return original_stage(tc_id)

        def fail(ctx):
            chain.calls.append(tc_id)
            try:
                raise ForegroundError('synthetic focus ownership failure')
            except ForegroundError as error:
                if not caught:
                    raise
                result = TCResult(tc_id, 'fixture')
                result.abort(1, 'input guard', error)
                if caught == 'cleanup-throw':
                    raise RuntimeError('synthetic cleanup escaped the TC')
                result.abort(2, 'cleanup', RuntimeError('synthetic cleanup failure'))
                return result
        return fail

    monkeypatch.setattr(chain, 'stage', stage)
    monkeypatch.setattr(run, '_viewer_log_path', lambda ctx: None)
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    try:
        chain.run_chain(False)
        assert chain.calls == ['AUTOMATION_ENVIRONMENT_RESET', 'DICOM_Server_Setup', 'TC_A']
        assert chain.ctx.execution_incomplete is True
        assert chain.ctx.execution_block['automation_exception'] == 'ForegroundError'
        assert chain.finished[-1]['chain_completed'] is False
    finally:
        chain.tearDown()


@pytest.mark.parametrize('mode', ['sequence', 'basic-prepare', 'wu-prepare'])
def test_nested_xipl_foreground_failure_stops_inner_and_outer_next_tc(monkeypatch, mode):
    from core.result import TCResult
    from core.ui import ForegroundError
    from tests import xipl_flows
    from tests.test_wu_chain import ChainResumeTests

    chain = ChainResumeTests()
    chain.setUp()
    original_stage = chain.stage
    xipl_calls = []

    def prepare(ctx):
        if mode != 'sequence':
            raise ForegroundError('synthetic fixture focus failure')
        return object()

    def xipl(number):
        def execute(ctx, *args):
            xipl_calls.append(number)
            result = TCResult(f'TC_XIPL_compatibility_{number:02}', 'fixture')
            if number == 1:
                result.abort(1, 'input guard', ForegroundError('synthetic nested focus failure'))
            else:
                result.assert_true(1, 'fixture', True)
            return result
        return execute

    monkeypatch.setattr(xipl_flows, '_prepare', prepare)
    for number in range(1, 8):
        monkeypatch.setattr(xipl_flows, f'compatibility_{number:02}', xipl(number))
    entry = xipl_flows.run_xipl
    if mode == 'wu-prepare':
        entry = next(fn for fn, tc_id, title in run._wu_chain_stages()
                     if tc_id == 'TC_XIPL_compatibility_subset')
    monkeypatch.setattr(chain, 'stage', lambda tc_id: entry if tc_id == 'TC_A'
                        else original_stage(tc_id))
    monkeypatch.setattr(run, '_viewer_log_path', lambda ctx: None)
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    try:
        chain.run_chain(False)
        assert xipl_calls == ([1] if mode == 'sequence' else [])
        assert chain.calls == ['AUTOMATION_ENVIRONMENT_RESET', 'DICOM_Server_Setup']
        assert chain.ctx.execution_incomplete is True
        assert chain.ctx.execution_block['automation_exception'] == 'ForegroundError'
        assert chain.finished[-1]['chain_completed'] is False
    finally:
        chain.tearDown()


def test_abort_observer_restores_outer_scope_and_resets_after_exception(tmp_path, monkeypatch):
    from core.result import TCResult
    from core.ui import ForegroundError

    outer = SimpleNamespace(cfg={}, root=str(tmp_path))
    inner = SimpleNamespace(cfg={}, root=str(tmp_path))
    monkeypatch.setattr(run, '_viewer_log_path', lambda ctx: None)

    def ordinary(ctx):
        raise RuntimeError('synthetic inner failure')

    def nested(ctx):
        run.guarded(ordinary, inner, 'INNER', 'fixture')
        result = TCResult('OUTER', 'fixture')
        result.abort(1, 'outer input guard', ForegroundError('synthetic outer focus failure'))
        raise RuntimeError('synthetic outer cleanup failure')

    run.guarded(nested, outer, 'OUTER', 'fixture')
    assert outer.execution_block['automation_exception'] == 'ForegroundError'
    assert not getattr(inner, 'execution_block', None)
    block = dict(outer.execution_block)
    clean = SimpleNamespace(cfg={}, root=str(tmp_path))
    run.guarded(ordinary, clean, 'CLEAN', 'fixture')
    TCResult('AFTER', 'fixture').abort(1, 'outside guard', ForegroundError('unscoped fixture'))
    assert outer.execution_block == block
    assert not getattr(inner, 'execution_block', None)
    assert not getattr(clean, 'execution_block', None)


@pytest.mark.parametrize('subset', [False, True], ids=['basic', 'wu-subset'])
def test_ordinary_prepare_failure_keeps_independent_xipl_tcs(tmp_path, monkeypatch, subset):
    from core.result import TCResult
    from tests import xipl_flows

    ctx = SimpleNamespace(cfg={}, root=str(tmp_path))
    calls = []
    def prepare(ctx):
        raise RuntimeError('ordinary fixture preparation failure')
    def independent(number):
        def execute(ctx):
            calls.append(number)
            result = TCResult(f'TC_XIPL_compatibility_{number:02}', 'fixture')
            result.assert_true(1, 'fixture', True)
            return result
        return execute
    monkeypatch.setattr(xipl_flows, '_prepare', prepare)
    for number in (4, 5, 7):
        monkeypatch.setattr(xipl_flows, f'compatibility_{number:02}', independent(number))
    monkeypatch.setattr(run, '_viewer_log_path', lambda ctx: None)
    entry = xipl_flows.run_xipl
    if subset:
        entry = next(fn for fn, tc_id, title in run._wu_chain_stages()
                     if tc_id == 'TC_XIPL_compatibility_subset')
    run.guarded(entry, ctx, 'XIPL', 'fixture')
    assert calls == ([4, 7] if subset else [4, 5, 7])
    assert not getattr(ctx, 'execution_block', None)


def test_cleanup_log_warning_keeps_prior_foreground_cause(tmp_path, monkeypatch):
    from datetime import datetime
    from core.result import TCResult
    from core.ui import ForegroundError

    log = tmp_path / 'viewer.log'
    log.write_text('', encoding='utf-8')
    monkeypatch.setattr(run, '_viewer_log_path', lambda ctx: str(log))
    ctx = SimpleNamespace(cfg={}, root=str(tmp_path))
    def fail(ctx):
        result = TCResult('INNER', 'fixture')
        result.abort(1, 'input guard', ForegroundError('synthetic focus ownership failure'))
        log.write_text(datetime.now().strftime('[%Y/%m/%d %H:%M:%S]') +
                       ' SQL Server timeout expired\n', encoding='utf-8')
        raise RuntimeError('synthetic cleanup failure')
    run.guarded(fail, ctx, 'OUTER', 'fixture')
    assert ctx.execution_block['tc_id'] == 'INNER'
    assert ctx.execution_block['automation_exception'] == 'ForegroundError'
    assert ctx.execution_block['causes'][0]['category'] == 'sql-timeout'


@pytest.mark.parametrize('product_failure', [False, True], ids=['runtime-error', 'product-fail'])
def test_non_input_failure_keeps_real_chain_running(monkeypatch, product_failure):
    from core.result import TCResult, StepFailed
    from tests.test_wu_chain import ChainResumeTests

    chain = ChainResumeTests()
    chain.setUp()
    original_stage = chain.stage

    def stage(tc_id):
        if tc_id != 'TC_A':
            return original_stage(tc_id)

        def fail(ctx):
            chain.calls.append(tc_id)
            if not product_failure:
                raise RuntimeError('ForegroundError: synthetic text is not an input exception')
            result = TCResult(tc_id, 'fixture')
            try:
                result.assert_true(1, 'product expectation', False)
            except StepFailed as error:
                result.abort(1, 'product assertion', error)
            return result
        return fail

    monkeypatch.setattr(chain, 'stage', stage)
    monkeypatch.setattr(run, '_viewer_log_path', lambda ctx: None)
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    try:
        chain.run_chain(False)
        assert chain.calls == ['AUTOMATION_ENVIRONMENT_RESET', 'DICOM_Server_Setup',
                               'TC_A', 'TC_B', 'WU09_USB', 'TC_WindowsUpdate_10']
        assert not getattr(chain.ctx, 'execution_block', None)
        assert chain.finished[-1]['chain_completed'] is True
    finally:
        chain.tearDown()


def test_unrelated_or_old_log_does_not_reclassify_exception(tmp_path, monkeypatch):
    log = tmp_path / 'viewer.log'
    log.write_text('[2020/01/01 12:00:00] SQL Server timeout expired\n', encoding='utf-8')
    monkeypatch.setattr(run, '_viewer_log_path', lambda ctx: str(log))
    ctx = SimpleNamespace(cfg={}, root=str(tmp_path))
    def fail(ctx): raise RuntimeError('fixture')
    assert run.guarded(fail, ctx, 'TC_SYNTHETIC', 'fixture')[0].verdict == 'FAIL'
    assert not getattr(ctx, 'execution_block', None)


def test_module_caught_failure_keeps_verdict_and_blocks_cascade_on_new_warning(tmp_path, monkeypatch):
    from datetime import datetime
    from core.result import TCResult
    log = tmp_path / 'viewer.log'
    log.write_text('', encoding='utf-8')
    monkeypatch.setattr(run, '_viewer_log_path', lambda ctx: str(log))
    ctx = SimpleNamespace(cfg={}, root=str(tmp_path))
    def caught(ctx):
        log.write_text(datetime.now().strftime('[%Y/%m/%d %H:%M:%S]') +
                       ' SQL Server timeout expired\n', encoding='utf-8')
        result = TCResult('TC_SYNTHETIC', 'fixture')
        result.abort(1, 'module caught', RuntimeError('Unexpected geometry'))
        return result
    rows = run.guarded(caught, ctx, 'TC_SYNTHETIC', 'fixture')
    assert rows[0].verdict == 'FAIL'
    assert ctx.execution_block['causes'][0]['category'] == 'sql-timeout'
    assert rows[0].as_dict()['cause_evidence'][0]['attribution'] == 'undetermined'
