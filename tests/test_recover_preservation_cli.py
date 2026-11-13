from contextlib import nullcontext
from tools import recover_preservation as cli
from core import run_preservation as preservation


def test_inspection_does_not_create_workspace(tmp_path):
    workspace = tmp_path / 'absent'
    assert cli.main(['--workspace', str(workspace)]) == 0
    assert not workspace.exists()


def test_apply_requires_explicit_run_before_any_product_operation(tmp_path):
    assert cli.main(['--workspace', str(tmp_path), '--apply']) == 2


def test_unstarted_ack_keeps_original_and_backup_without_product_action(tmp_path, monkeypatch):
    from bellalunauto import runtime
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'original').write_bytes(b'original')
    session = preservation.RunPreservation(tmp_path / 'work', 'synthetic', {'data': source})
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
