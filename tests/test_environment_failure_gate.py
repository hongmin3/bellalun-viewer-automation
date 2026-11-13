import time
from types import SimpleNamespace

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
