from contextlib import nullcontext
from pathlib import Path
from tools import recover_preservation as cli
from core import run_preservation as preservation
import pytest


def test_inspection_does_not_create_workspace(tmp_path):
    workspace = tmp_path / 'absent'
    assert cli.main(['--workspace', str(workspace)]) == 0
    assert not workspace.exists()


def test_apply_requires_explicit_run_before_any_product_operation(tmp_path):
    assert cli.main(['--workspace', str(tmp_path), '--apply']) == 2


@pytest.mark.parametrize('require_finalization', [False, True])
def test_unstarted_ack_keeps_original_and_backup_without_product_action(tmp_path, monkeypatch, require_finalization):
    from bellalunauto import runtime
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'original').write_bytes(b'original')
    session = preservation.RunPreservation(tmp_path / 'work', 'synthetic', {'data': source},
                                           require_finalization=require_finalization)
    monkeypatch.setattr(preservation, '_copy_tree', lambda *a: (_ for _ in ()).throw(OSError()))
    try:
        session.prepare()
    except preservation.PreservationError:
        pass
    monkeypatch.setattr(runtime, 'RunLock', lambda: nullcontext())
    assert cli.main(['--workspace', str(tmp_path / 'work'), '--run-id', 'synthetic',
                     '--apply', '--acknowledge-unstarted']) == 0
    assert (source / 'original').read_bytes() == b'original'
    assert session.run_dir.exists()
    assert preservation.RunPreservation.pending(tmp_path / 'work') == []


def test_shared_recovery_uses_original_journal_store_when_config_store_changed(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import run
    from bellalunauto import runtime
    from core import execution_session
    source, storage, other = (tmp_path / name for name in ('source', 'nas', 'other-nas'))
    for folder in (source, storage, other): folder.mkdir()
    image = source / 'image'
    image.write_bytes(b'original')
    workspace = tmp_path / 'work'
    session = preservation.RunPreservation(workspace, 'synthetic', {'images': source}, storage_dir=storage)
    session.prepare()
    image.write_bytes(b'after-run')
    ctx = SimpleNamespace(cfg={'preservation': {'storage_dir': str(other)}})
    monkeypatch.setattr(run, 'Context', lambda *a: ctx)
    monkeypatch.setattr(execution_session, 'DatabasePreservation', lambda *a: None)
    monkeypatch.setattr(execution_session, 'stop_product', lambda *a: None)
    monkeypatch.setattr(execution_session, 'start_services', lambda: None)
    monkeypatch.setattr(runtime, 'RunLock', lambda: nullcontext())
    assert cli.main(['--workspace', str(workspace), '--run-id', 'synthetic', '--apply',
                     '--config', str(tmp_path / 'not-read.json')]) == 0
    assert image.read_bytes() == b'original'
    assert (storage / 'synthetic' / 'archive' / 'images' / 'image').read_bytes() == b'after-run'
    assert list(other.iterdir()) == []
    journal = json.loads((session.run_dir / 'journal.json').read_text(encoding='utf-8'))
    assert journal['state'] == 'verified'


def test_shared_offline_storage_is_still_listed_by_local_inspection(tmp_path, capsys):
    import json
    source, storage = tmp_path / 'source', tmp_path / 'nas'
    source.mkdir()
    storage.mkdir()
    session = preservation.RunPreservation(tmp_path / 'work', 'synthetic', {'images': source},
                                           storage_dir=storage)
    session.prepare()
    storage.rename(tmp_path / 'offline-nas')
    assert cli.main(['--workspace', str(tmp_path / 'work')]) == 0
    assert json.loads(capsys.readouterr().out)['pending'] == ['synthetic']
    assert session.run_dir.exists()


@pytest.mark.parametrize('fault', [None, 'proof_tamper', 'wrong_markers', 'services_stopped'])
@pytest.mark.parametrize('before_cleanup', [False, True])
def test_cleanup_resume_uses_pinned_completion_without_database_restore(tmp_path, monkeypatch, fault, before_cleanup):
    import json
    from types import SimpleNamespace
    from unittest import mock
    import run as entry
    from bellalunauto import runtime
    from core import execution_session, dbreset
    from core.automation_health import FULL_REGRESSION_MARKERS
    from tests.test_image_cleanup import finished_run, quarantine_file
    image, storage, session = finished_run(tmp_path)
    proof = {'meta': {'run_id': session.run_id, 'chain_completed': True, 'execution_mode': 'live'},
             'results': [{'tc_id': tc, 'verdict': 'PASS'} for tc in sorted(
                 FULL_REGRESSION_MARKERS if fault != 'wrong_markers' else {'TC_PARTIAL'})]}
    locator = session.pin_cleanup_completion(proof, 'run-regression')
    one = quarantine_file(session, 'one.dcm')
    real_unlink = Path.unlink
    def locked(path, *args, **kwargs):
        if path == one: raise PermissionError('synthetic lock')
        return real_unlink(path, *args, **kwargs)
    if before_cleanup:
        session._save('verified', execution_finalization_pending=True)
    else:
        with mock.patch.object(Path, 'unlink', locked):
            assert session.cleanup_generated_images(normal_completion=True, services_verified=True)['status'] == 'cleanup_required'
    reports = session.workspace / 'Reports'
    reports.mkdir()
    final_report = reports / 'Result_fixture.json'
    final_report.write_text(json.dumps({'meta': {**proof['meta'], 'chain_completed': False,
        'restoration': session.journal['result']}, 'results': proof['results']}), encoding='utf-8')
    receipt = session.workspace / 'Runs' / session.run_id / 'run.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'run_id': session.run_id, 'status': 'abnormal', 'exit_code': 3}), encoding='utf-8')
    if fault == 'proof_tamper':
        Path(locator['report']).write_text('{}', encoding='utf-8')
    ctx = SimpleNamespace(root=str(session.workspace), cfg={})
    monkeypatch.setattr(entry, 'Context', lambda *a: ctx)
    monkeypatch.setattr(runtime, 'RunLock', lambda: nullcontext())
    def forbidden(*a, **k): raise AssertionError('cleanup must not stop product or restore database')
    monkeypatch.setattr(execution_session, 'stop_product', forbidden)
    monkeypatch.setattr(execution_session, 'DatabasePreservation', forbidden)
    monkeypatch.setattr(preservation.RunPreservation, 'recover', forbidden)
    monkeypatch.setattr(execution_session, 'start_services', lambda: {
        name: 'STOPPED' if fault == 'services_stopped' else 'RUNNING' for name in dbreset.APP_SERVICES})
    code = cli.main(['--workspace', str(session.workspace), '--run-id', session.run_id,
        '--config', str(tmp_path / 'not-read.json'), '--apply', '--resume-image-cleanup'])
    assert code == (0 if fault is None else 2)
    assert one.exists() is (fault is not None)
    assert (image / 'existing').read_bytes() == b'original'
    assert (storage / session.run_id / 'archive' / 'Image' / 'generated' / 'one.dcm').read_bytes() == b'new1'
    final = json.loads(final_report.read_text(encoding='utf-8'))
    assert final['meta']['chain_completed'] is False
    record = json.loads(receipt.read_text(encoding='utf-8'))
    assert record['status'] == 'abnormal' and record['exit_code'] == 3
    if fault is None:
        assert final['meta']['restoration']['image_cleanup']['status'] == 'completed'
        assert record['restoration']['image_cleanup']['status'] == 'completed'
        assert preservation.RunPreservation.pending(session.workspace) == []
    else:
        assert preservation.RunPreservation.pending(session.workspace) == [session.run_id]


@pytest.mark.parametrize('flags', [[], ['--apply'], ['--apply', '--run-id', 'synthetic'],
    ['--apply', '--run-id', 'synthetic', '--config', 'unused', '--acknowledge-unstarted']])
def test_cleanup_resume_requires_explicit_apply_run_config_and_no_unstarted_mode(tmp_path, monkeypatch, flags):
    monkeypatch.setattr(preservation.RunPreservation, 'load', lambda *a, **k: pytest.fail('must validate flags first'))
    assert cli.main(['--workspace', str(tmp_path), '--resume-image-cleanup', *flags]) == 2
