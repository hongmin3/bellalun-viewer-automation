import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('storage_dir', [None, '', '   '])
def test_execution_scope_restores_files_and_records_failure(tmp_path, monkeypatch, storage_dir):
    from core import execution_session as module
    monkeypatch.chdir(tmp_path)
    data = tmp_path / 'data'
    (data / 'Image').mkdir(parents=True)
    image = data / 'Image' / 'qc.img'
    image.write_bytes(b'original')
    workspace = tmp_path / 'work'
    ctx = SimpleNamespace(root=str(workspace), cfg={'data_dir': str(data),
                          'preservation': {'storage_dir': storage_dir}},
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
    assert json.loads(next(workspace.glob('preservation/*/restoration.json')).read_text(encoding='utf-8'))['status'] == 'verified'


def test_missing_explicit_choice_blocks_before_product_stop(tmp_path, monkeypatch):
    from core import execution_session as module
    ctx = SimpleNamespace(root=str(tmp_path), cfg={})
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    with pytest.raises(ValueError, match='복원'):
        with module.execution_session(ctx, 'run-regression'):
            pytest.fail('product must not start')


@pytest.mark.parametrize('storage_mode', ['legacy', 'shared-changed', 'shared-unchanged'])
def test_real_cli_dispatch_waits_for_restore_and_updates_report(tmp_path, monkeypatch, storage_mode):
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
    if storage_mode != 'legacy':
        storage = tmp_path / 'nas'
        storage.mkdir()
        ctx.cfg['preservation'] = {'storage_dir': str(storage)}
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
        if storage_mode != 'shared-unchanged':
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
    assert archived.read_bytes() == (b'original' if storage_mode == 'shared-unchanged' else b'changed')
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


@pytest.mark.parametrize('overrides,usb_required', [({}, 768 * 1024 ** 2),
    ({'usb_headroom_bytes': 0, 'usb_generation_bytes': 0}, 0)])
@pytest.mark.parametrize('restore_after', [True, False])
def test_execution_shared_storage_allows_small_usb_and_keeps_local_full_copy_off(
        tmp_path, monkeypatch, overrides, usb_required, restore_after):
    from core import execution_session as module, resource_budget, env_preflight, usb_media
    data, usb, nas = (tmp_path / p for p in ('data', 'usb', 'nas'))
    for folder in (data, usb, nas): folder.mkdir()
    (data / 'one').write_bytes(b'12345')
    (data / 'two').write_bytes(b'12345')
    workspace = tmp_path / 'work'
    options = {'storage_dir': str(nas), **overrides}
    ctx = SimpleNamespace(root=str(workspace), cfg={'data_dir': str(data), 'preservation': options},
                          preservation_choice=restore_after, db=object())
    class Database:
        def __init__(self, ctx): pass
        def estimate_bytes(self): return 13
        def backup(self, dest): return {'scope': 'synthetic'}
        def verify_backup(self, *a): return True
        def restore(self, *a): pass
        def verify_restored(self, *a): return True
    monkeypatch.setattr(module, 'DatabasePreservation', Database)
    monkeypatch.setattr(module, 'stop_product', lambda ctx: None)
    monkeypatch.setattr(module, 'start_services', lambda: None)
    monkeypatch.setattr(module, 'roots_from_config', lambda *a, **k: {'images': data, 'usb': usb})
    monkeypatch.setattr(usb_media, 'find_usb_drive', lambda: str(usb))
    monkeypatch.setattr(env_preflight, 'real_memory', lambda: {'avail': 4 * resource_budget.GIB})
    def probe(path):
        identity = 'nas' if path == nas else 'usb' if path == usb else 'local'
        return {'id': identity, 'free': usb_required if identity == 'usb' else 100 * resource_budget.GIB}
    monkeypatch.setattr(resource_budget, 'volume_info', probe)
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    with module.execution_session(ctx, 'run-winupdate'):
        assert (nas / ctx.run_id).exists()
        assert not (workspace / 'preservation' / ctx.run_id / 'before').exists()
    volumes = {v['id']: v for v in ctx.resource_budget['volumes']}
    assert volumes['usb']['required'] == usb_required
    # Local: generation + headroom + reports/screenshots + single-file restore + SQL stages.
    assert volumes['local']['required'] == (5 * resource_budget.GIB + 768 * 1024 ** 2
                                            + (44 if restore_after else 26))
    # NAS: before10 + DB13 + after(10 + root generation + DB13), even without restoration.
    assert volumes['nas']['required'] == 3 * resource_budget.GIB + options.get(
        'usb_generation_bytes', 512 * 1024 ** 2) + 46


@pytest.mark.parametrize('command,full,exit_code,services,expected', [
    ('run-regression', True, 0, True, 'completed'),
    ('run-regression', True, 1, True, 'completed'),
    ('run-winupdate', True, 0, True, 'completed'),
    ('run-regression', False, 0, True, 'skipped'),
    ('run-wu09', True, 0, True, 'skipped'),
    ('run-regression', True, 3, True, 'skipped'),
    ('run-regression', True, 0, False, 'skipped'),
])
@pytest.mark.parametrize('cleanup_failure', [False, 'returned', 'raised'])
def test_generated_cleanup_waits_for_full_final_report_and_running_services(
        tmp_path, monkeypatch, command, full, exit_code, services, expected, cleanup_failure):
    from contextlib import contextmanager
    import run
    from bellalunauto import runplan
    from core import execution_session, dbreset
    from core.automation_health import FULL_REGRESSION_MARKERS
    from core.result import TCResult, write_reports
    ctx = SimpleNamespace(root=str(tmp_path), resource_root=str(tmp_path),
        reports_root=str(tmp_path / 'Reports'), cfg={}, run_id='synthetic', preservation_roots={})
    report_path = Path(ctx.reports_root) / ('Result_WindowsUpdate_fixture.json'
                    if command == 'run-winupdate' else 'Result_fixture.json')
    class Session:
        run_dir = tmp_path / 'journal'
        def pin_cleanup_completion(self, report_data, command):
            assert report_data['meta']['chain_completed'] is True
            return {'run_id': 'synthetic', 'command': command, 'report': 'synthetic-proof', 'sha256': 'synthetic'}
        def cleanup_generated_images(self, normal_completion=False, services_verified=False):
            # Consumer contract: the final report exists before the destructive API is reached.
            final = json.loads(report_path.read_text(encoding='utf-8'))
            assert final['meta']['restoration']['status'] == 'verified'
            assert final['meta']['performance'] == []
            if cleanup_failure == 'raised' and normal_completion and services_verified:
                raise OSError('cleanup journal unavailable')
            return {'status': ('cleanup_required' if cleanup_failure else 'completed')
                    if normal_completion and services_verified else 'skipped',
                    'reason': 'normal_completion' if normal_completion else 'incomplete_run'}
    session = Session()
    session.run_dir.mkdir()
    @contextmanager
    def preserved(*args):
        yield session
        ctx.restoration = {'status': 'verified', 'services': {
            name: 'RUNNING' if services else 'STOPPED' for name in dbreset.APP_SERVICES}}
    monkeypatch.setattr(execution_session, 'execution_session', preserved)
    monkeypatch.setattr(runplan, 'build_plan', lambda *a: {'plan_id': 'fixed', 'execution_fingerprint': 'fixed'})
    def dispatch(*args):
        ids = ({f'TC_WindowsUpdate_{i:02}' for i in range(1, 14)} if command == 'run-winupdate'
               else FULL_REGRESSION_MARKERS) if full else {'TC_PARTIAL'}
        rows = []
        for tc_id in sorted(ids):
            row = TCResult(tc_id, 'synthetic')
            row.add(1, 'result', 'FAIL' if exit_code == 1 else 'PASS', stop=False)
            rows.append(row)
        write_reports(rows, ctx.reports_root, report_path.stem[len('Result_'):], meta=run._execution_meta(ctx))
        return exit_code
    monkeypatch.setattr(run, '_dispatch', dispatch)
    failed = cleanup_failure and expected == 'completed'
    assert run._execute_preserved(ctx, SimpleNamespace(cmd=command, restore_after=True)) == (3 if failed else exit_code)
    final = json.loads(report_path.read_text(encoding='utf-8'))
    assert final['meta']['restoration']['image_cleanup']['status'] == ('cleanup_required' if failed else expected)
    if failed:
        assert final['meta']['chain_completed'] is False
        assert final['meta']['restoration']['status'] == 'cleanup_required'
        assert json.loads((session.run_dir / 'restoration.json').read_text(encoding='utf-8')) == ctx.restoration


@pytest.mark.parametrize('restore_after', [True, False])
@pytest.mark.parametrize('removal_fails', [False, True])
@pytest.mark.parametrize('cleanup_enabled', [True, False])
def test_full_cli_cleans_only_generated_image_after_evidence_is_preserved(
        tmp_path, monkeypatch, restore_after, removal_fails, cleanup_enabled):
    import run
    from bellalunauto import runplan
    from core import execution_session, dbreset
    from core.automation_health import FULL_REGRESSION_MARKERS
    from core.result import TCResult, write_reports
    images, storage, workspace = (tmp_path / name for name in ('Image', 'nas', 'work'))
    images.mkdir()
    storage.mkdir()
    (images / 'original.img').write_bytes(b'original')
    generated = images / 'generated.img'
    ctx = SimpleNamespace(root=str(workspace), resource_root=str(tmp_path),
        reports_root=str(workspace / 'Reports'), cfg={'data_dir': str(tmp_path),
            'preservation': {'storage_dir': str(storage), 'cleanup_generated_images_after': cleanup_enabled}})
    class Database:
        def __init__(self, ctx): pass
        def estimate_bytes(self): return 0
        def backup(self, dest): return {'scope': 'synthetic'}
        def verify_backup(self, *a): return True
        def restore(self, *a): pass
        def verify_restored(self, *a): return True
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    monkeypatch.setattr(execution_session, 'DatabasePreservation', Database)
    monkeypatch.setattr(execution_session, 'plan_resources', lambda *a, **k: {'blocked': False})
    monkeypatch.setattr(execution_session, 'stop_product', lambda *a: None)
    monkeypatch.setattr(execution_session, 'start_services', lambda: {name: 'RUNNING' for name in dbreset.APP_SERVICES})
    monkeypatch.setattr(execution_session, 'roots_from_config', lambda *a, **k: {'Image': images})
    monkeypatch.setattr(runplan, 'build_plan', lambda *a: {'plan_id': 'fixed', 'execution_fingerprint': 'fixed'})
    def dispatch(*args):
        generated.write_bytes(b'generated')
        rows = []
        for tc_id in sorted(FULL_REGRESSION_MARKERS):
            row = TCResult(tc_id, 'synthetic')
            row.add(1, 'result', 'PASS')
            row.attach(str(generated))
            rows.append(row)
        write_reports(rows, ctx.reports_root, 'fixture', meta=run._execution_meta(ctx))
        return 0
    monkeypatch.setattr(run, '_dispatch', dispatch)
    unlink = Path.unlink
    def only_after_evidence(path, *args, **kwargs):
        if path.is_file() and path.read_bytes() == b'generated':
            report = json.loads((Path(ctx.reports_root) / 'Result_fixture.json').read_text(encoding='utf-8'))
            assert report['meta']['restoration']['status'] == 'verified'
            assert all(Path(row['evidence'][0]).is_relative_to(workspace / 'Evidence')
                       and Path(row['evidence'][0]).read_bytes() == b'generated' for row in report['results'])
            if removal_fails:
                raise PermissionError('synthetic file lock')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', only_after_evidence)
    failed = removal_fails and restore_after and cleanup_enabled
    assert run._execute_preserved(ctx, SimpleNamespace(cmd='run-regression', restore_after=restore_after)) == (3 if failed else 0)
    final = json.loads((Path(ctx.reports_root) / 'Result_fixture.json').read_text(encoding='utf-8'))
    cleanup = final['meta']['restoration']['image_cleanup']
    assert cleanup['status'] == ('cleanup_required' if failed else 'completed' if restore_after and cleanup_enabled else 'skipped')
    if failed:
        from core.run_preservation import RunPreservation
        assert RunPreservation.pending(workspace) == [ctx.run_id]
        assert final['meta']['chain_completed'] is False
    elif restore_after and cleanup_enabled:
        assert cleanup['files_removed'] == 1
        assert not generated.exists()
    else:
        assert cleanup['reason'] == ('restore_not_selected' if cleanup_enabled else 'disabled_by_config')
        if not restore_after:
            assert generated.read_bytes() == b'generated'
    if not failed:
        from core.run_preservation import RunPreservation
        assert RunPreservation.pending(workspace) == []
    assert (images / 'original.img').read_bytes() == b'original'
    assert (storage / ctx.run_id / 'archive' / 'Image' / 'generated.img').read_bytes() == b'generated'
    if restore_after and cleanup_enabled:
        locator = final['meta']['restoration']['normal_completion_before_cleanup']
        proof = json.loads(Path(locator['report']).read_text(encoding='utf-8'))
        assert proof['meta']['run_id'] == ctx.run_id
        assert proof['meta']['chain_completed'] is True
        journal = json.loads((workspace / 'preservation' / ctx.run_id / 'journal.json').read_text(encoding='utf-8'))
        assert journal['normal_completion_before_cleanup'] == locator


@pytest.mark.parametrize('fault', ['proof', 'services', 'cleanup_interrupt', 'final_report'])
def test_finalization_failure_remains_pending_after_verified_restoration(tmp_path, monkeypatch, fault):
    import run
    from bellalunauto import runplan
    from core import execution_session, dbreset
    from core.run_preservation import RunPreservation
    from core.automation_health import FULL_REGRESSION_MARKERS
    from core.result import TCResult, write_reports
    images, storage, workspace = (tmp_path / name for name in ('Image', 'nas', 'work'))
    images.mkdir()
    storage.mkdir()
    (images / 'original.img').write_bytes(b'original')
    ctx = SimpleNamespace(root=str(workspace), resource_root=str(tmp_path),
        reports_root=str(workspace / 'Reports'), cfg={'data_dir': str(tmp_path),
            'preservation': {'storage_dir': str(storage)}})
    class Database:
        def __init__(self, ctx): pass
        def estimate_bytes(self): return 0
        def backup(self, dest): return {'scope': 'synthetic'}
        def verify_backup(self, *a): return True
        def restore(self, *a): pass
        def verify_restored(self, *a): return True
    monkeypatch.delenv('BELLALUN_QA_RUN', raising=False)
    monkeypatch.setattr(execution_session, 'DatabasePreservation', Database)
    monkeypatch.setattr(execution_session, 'plan_resources', lambda *a, **k: {'blocked': False})
    monkeypatch.setattr(execution_session, 'stop_product', lambda *a: None)
    starts = []
    def services():
        starts.append(True)
        if fault == 'services' and len(starts) == 2:
            raise RuntimeError('synthetic service failure after restoration')
        return {name: 'RUNNING' for name in dbreset.APP_SERVICES}
    monkeypatch.setattr(execution_session, 'start_services', services)
    monkeypatch.setattr(execution_session, 'roots_from_config', lambda *a, **k: {'Image': images})
    monkeypatch.setattr(runplan, 'build_plan', lambda *a: {'plan_id': 'fixed', 'execution_fingerprint': 'fixed'})
    def dispatch(*args):
        (images / 'new.img').write_bytes(b'new image')
        rows = []
        for tc in sorted(FULL_REGRESSION_MARKERS):
            row = TCResult(tc, 'synthetic')
            row.add(1, 'result', 'PASS')
            rows.append(row)
        write_reports(rows, ctx.reports_root, 'fixture', meta=run._execution_meta(ctx))
        return 0
    monkeypatch.setattr(run, '_dispatch', dispatch)
    if fault == 'proof':
        monkeypatch.setattr(RunPreservation, 'pin_cleanup_completion',
            lambda *a: (_ for _ in ()).throw(OSError('synthetic proof failure')))
    elif fault == 'cleanup_interrupt':
        monkeypatch.setattr(RunPreservation, 'cleanup_generated_images',
            lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt('synthetic power loss')))
    elif fault == 'final_report':
        def final_report(*a, **k):
            if (k.get('meta', {}).get('restoration', {}).get('image_cleanup', {}).get('status') == 'completed'):
                raise OSError('synthetic final report failure')
            return write_reports(*a, **k)
        monkeypatch.setattr(run, 'write_reports', final_report)
    if fault == 'cleanup_interrupt':
        with pytest.raises(KeyboardInterrupt):
            run._execute_preserved(ctx, SimpleNamespace(cmd='run-regression', restore_after=True))
    else:
        assert run._execute_preserved(ctx, SimpleNamespace(cmd='run-regression', restore_after=True)) == 3
    assert (images / 'original.img').read_bytes() == b'original'
    assert (storage / ctx.run_id / 'archive' / 'Image' / 'new.img').read_bytes() == b'new image'
    assert RunPreservation.pending(workspace) == [ctx.run_id]
    # A generic restore must not consume an unfinished finalization as a successful run.
    recovered = RunPreservation.recover(workspace, ctx.run_id)
    assert recovered['status'] not in {'verified', 'preserved'}


def test_cleanup_report_rewrite_failure_revokes_json_completion(tmp_path, monkeypatch):
    import run
    from core.result import TCResult, write_reports
    from core.dbreset import APP_SERVICES
    row = TCResult('TC_SYNTHETIC', 'fixture')
    row.add(1, 'result', 'PASS')
    meta = {'run_id': 'synthetic', 'chain_completed': True}
    report = tmp_path / 'Reports' / 'Result_fixture.json'
    write_reports([row], str(report.parent), 'fixture', meta=meta)
    ctx = SimpleNamespace(root=str(tmp_path), reports_root=str(report.parent), cfg={},
                          run_id='synthetic', restoration={'status': 'verified',
                          'services': {name: 'RUNNING' for name in APP_SERVICES}})
    monkeypatch.setattr(run, 'write_reports', lambda *a, **k: (_ for _ in ()).throw(OSError('report denied')))
    assert run._finish_generated_image_cleanup(ctx, SimpleNamespace(cmd='run-wu09'), None,
                                               0, 0, [(report, [row], meta)], True) == 3
    final = json.loads(report.read_text(encoding='utf-8'))
    assert final['meta']['chain_completed'] is False
    emergency = json.loads(next(tmp_path.glob('Runs/emergency/*.json')).read_text(encoding='utf-8'))
    assert emergency['meta']['chain_completed'] is False


def test_final_evidence_failure_blocks_cleanup_and_revokes_completion(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import run
    from bellalunauto import runplan
    from core import execution_session, run_preservation, dbreset
    from core.automation_health import FULL_REGRESSION_MARKERS
    from core.result import TCResult, write_reports
    image = tmp_path / 'Image' / 'evidence.img'
    image.parent.mkdir()
    image.write_bytes(b'evidence')
    ctx = SimpleNamespace(root=str(tmp_path), resource_root=str(tmp_path), cfg={},
        reports_root=str(tmp_path / 'Reports'), run_id='synthetic', preservation_roots={'Image': image.parent})
    @contextmanager
    def preserved(*a):
        yield SimpleNamespace(run_dir=tmp_path / 'journal')
        ctx.restoration = {'status': 'verified', 'services': {name: 'RUNNING' for name in dbreset.APP_SERVICES}}
    monkeypatch.setattr(execution_session, 'execution_session', preserved)
    monkeypatch.setattr(runplan, 'build_plan', lambda *a: {'plan_id': 'fixed', 'execution_fingerprint': 'fixed'})
    monkeypatch.setattr(run_preservation, 'preserved_path', lambda *a: (_ for _ in ()).throw(OSError('archive unavailable')))
    def dispatch(*a):
        rows = []
        for tc in sorted(FULL_REGRESSION_MARKERS):
            row = TCResult(tc, 'fixture')
            row.add(1, 'result', 'PASS')
            row.attach(str(image))
            rows.append(row)
        write_reports(rows, ctx.reports_root, 'fixture', meta=run._execution_meta(ctx))
        return 0
    monkeypatch.setattr(run, '_dispatch', dispatch)
    assert run._execute_preserved(ctx, SimpleNamespace(cmd='run-regression', restore_after=True)) == 3
    final = json.loads((Path(ctx.reports_root) / 'Result_fixture.json').read_text(encoding='utf-8'))
    assert final['meta']['chain_completed'] is False
    assert final['meta']['restoration']['image_cleanup']['reason'] == 'final_evidence_or_report_failed'
