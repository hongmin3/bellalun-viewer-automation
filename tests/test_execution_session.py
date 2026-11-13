import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_execution_scope_restores_files_and_records_failure(tmp_path, monkeypatch):
    from core import execution_session as module
    data = tmp_path / 'data'
    (data / 'Image').mkdir(parents=True)
    image = data / 'Image' / 'qc.img'
    image.write_bytes(b'original')
    workspace = tmp_path / 'work'
    ctx = SimpleNamespace(root=str(workspace), cfg={'data_dir': str(data)},
                          preservation_choice=True, db=object())
    class Database:
        def __init__(self, ctx): pass
        def estimate_bytes(self): return 0
        def backup(self, dest): return {'scope': 'synthetic'}
        def verify_backup(self, *args): return True
        def restore(self, *args): pass
        def verify_restored(self, *args): return True
    monkeypatch.setattr(module, 'DatabasePreservation', Database)
    monkeypatch.setattr(module, 'plan_resources', lambda *a, **k: {'blocked': False})
    monkeypatch.setattr(module, 'stop_product', lambda ctx: None)
    monkeypatch.setattr(module, 'start_services', lambda: None)
    monkeypatch.setattr(module, 'roots_from_config', lambda cfg, **k: {'images': data / 'Image'})
    with pytest.raises(RuntimeError, match='synthetic'):
        with module.execution_session(ctx, 'run-regression'):
            image.write_bytes(b'overwritten')
            raise RuntimeError('synthetic')
    assert image.read_bytes() == b'original'
    assert ctx.restoration['status'] == 'verified'
    assert json.loads(next(workspace.glob('preservation/*/restoration.json')).read_text())['status'] == 'verified'


def test_missing_explicit_choice_blocks_before_product_stop(tmp_path, monkeypatch):
    from core import execution_session as module
    ctx = SimpleNamespace(root=str(tmp_path), cfg={})
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    with pytest.raises(ValueError, match='복원'):
        with module.execution_session(ctx, 'run-regression'):
            pytest.fail('product must not start')


def test_real_cli_dispatch_waits_for_restore_and_updates_report(tmp_path, monkeypatch):
    import sys
    import run
    from core import execution_session as module
    from core.result import TCResult, write_reports
    from bellalunauto import runplan
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    image_root = tmp_path / 'data'
    image_root.mkdir()
    image = image_root / 'qc.img'
    image.write_bytes(b'original')
    ctx = SimpleNamespace(root=str(tmp_path / 'work'), resource_root=str(tmp_path),
                          reports_root=str(tmp_path / 'work' / 'Reports'), cfg={'data_dir': str(image_root)})
    class Database:
        def __init__(self, ctx): pass
        def estimate_bytes(self): return 0
        def backup(self, dest): return {'scope': 'synthetic'}
        def verify_backup(self, *a): return True
        def restore(self, *a): pass
        def verify_restored(self, *a): return True
    monkeypatch.setattr(module, 'DatabasePreservation', Database)
    monkeypatch.setattr(module, 'plan_resources', lambda *a, **k: {'blocked': False})
    monkeypatch.setattr(module, 'stop_product', lambda ctx: None)
    monkeypatch.setattr(module, 'start_services', lambda: None)
    monkeypatch.setattr(module, 'roots_from_config', lambda *a, **k: {'images': image_root})
    monkeypatch.setattr(run, 'Context', lambda path: ctx)
    monkeypatch.setattr(runplan, 'build_plan', lambda *a: {'plan_id': 'fixed', 'execution_fingerprint': 'fixed'})
    def body(ctx, args):
        image.write_bytes(b'changed')
        result = TCResult('TC_SYNTHETIC', 'fixture')
        result.add(1, 'done', 'PASS')
        result.attach(str(image))
        write_reports([result], ctx.reports_root, 'fixture', meta=run._execution_meta(ctx))
        return 0
    monkeypatch.setattr(run, '_dispatch', body)
    monkeypatch.setattr(sys, 'argv', ['run.py', 'run-regression', '--restore-after'])
    assert run._main() == 0
    assert image.read_bytes() == b'original'
    report = json.loads((Path(ctx.reports_root) / 'Result_fixture.json').read_text(encoding='utf-8'))
    assert report['meta']['restoration']['status'] == 'verified'
    archived = Path(report['results'][0]['evidence'][0])
    assert archived.read_bytes() == b'changed'
    assert archived.is_relative_to(Path(ctx.root) / 'Evidence')
    assert report['results'][0].get('reused_from_checkpoint') is not True


def test_stopped_service_is_not_successful_finalization(monkeypatch):
    from core import execution_session as module, dbreset
    monkeypatch.setattr(dbreset, 'start_app_services', lambda: {'Bellalun Service': 'STOPPED'})
    with pytest.raises(RuntimeError, match='RUNNING'):
        module.start_services()


def test_recovery_journal_changes_resume_identity_without_separate_generation_file(tmp_path):
    from core.execution_session import restoration_generation
    before = restoration_generation(tmp_path)
    folder = tmp_path / 'preservation' / 'recovered-run'
    folder.mkdir(parents=True)
    (folder / 'journal.json').write_text(json.dumps({'state': 'verified', 'run_id': 'recovered-run'}))
    after = restoration_generation(tmp_path)
    assert before == [] and after[0]['run_id'] == 'recovered-run'
    assert after != before
    assert not (tmp_path / 'work' / 'preservation_generation.json').exists()


def test_persistent_basic_report_failure_writes_separate_emergency_result(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import run
    from core import execution_session as module
    from core.result import TCResult
    from bellalunauto import runplan
    ctx = SimpleNamespace(root=str(tmp_path), resource_root=str(tmp_path), cfg={},
                          reports_root=str(tmp_path / 'Reports'), run_id='synthetic')
    @contextmanager
    def preserved(*args):
        try: yield
        finally: ctx.restoration = {'status': 'verified'}
    monkeypatch.setattr(module, 'execution_session', preserved)
    monkeypatch.setattr(runplan, 'build_plan', lambda *a: {'plan_id': 'fixed', 'execution_fingerprint': 'fixed'})
    def fail(ctx, args):
        result = TCResult('TC_FINISHED', 'fixture')
        result.add(1, 'finished', 'PASS')
        ctx.partial_results = [result]
        raise PermissionError('reports unavailable')
    monkeypatch.setattr(run, '_dispatch', fail)
    monkeypatch.setattr(run, 'shutdown_viewer', lambda *a: None)
    monkeypatch.setattr(run, 'finish', lambda *a: (_ for _ in ()).throw(PermissionError()))
    assert run._execute_preserved(ctx, SimpleNamespace(cmd='run-regression', restore_after=False)) == 3
    saved = json.loads(next(tmp_path.glob('Runs/emergency/*.json')).read_text(encoding='utf-8'))
    assert saved['meta']['chain_completed'] is False
    assert saved['results'][0]['tc_id'] == 'TC_FINISHED'
