"""실제 임시 파일의 보관·ZIP·해시 검증. 운영 자료는 사용하지 않는다."""
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest


def source_tree(tmp_path):
    source = tmp_path / 'source'
    (source / 'empty').mkdir(parents=True)
    (source / 'nested').mkdir()
    (source / 'nested' / '결과.txt').write_bytes(b'original data' * 300)
    return source


@pytest.mark.parametrize('compress', [False, True])
def test_apply_archive_verifies_real_content_and_preserves_source(tmp_path, compress):
    from core.artifact_archive import archive_artifacts, verify_archive
    from core.run_preservation import snapshot
    source = source_tree(tmp_path)
    before = snapshot(source)
    destination = tmp_path / 'selected' / 'archive'
    result = archive_artifacts(source, destination, compress=compress, apply=True)
    assert result['state'] == 'complete'
    assert snapshot(source) == before
    assert verify_archive(destination)['state'] == 'verified'
    manifest = json.loads((destination / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['snapshot'] == before
    assert json.loads((destination / 'receipt.json').read_text(encoding='utf-8'))['state'] == 'complete'
    if compress:
        with zipfile.ZipFile(destination / 'archive.zip') as bundle:
            assert bundle.read('nested/결과.txt') == b'original data' * 300
            assert 'empty/' in bundle.namelist()
            assert bundle.getinfo('nested/결과.txt').compress_type == zipfile.ZIP_DEFLATED
    else:
        assert snapshot(destination / 'content') == before


def test_default_inspection_does_not_create_destination_or_change_source(tmp_path):
    from core.artifact_archive import archive_artifacts
    from core.run_preservation import snapshot
    source = source_tree(tmp_path)
    before = snapshot(source)
    destination = tmp_path / 'not-created' / 'archive'
    plan = archive_artifacts(source, destination)
    assert plan['state'] == 'planned'
    assert plan['source_bytes'] == 3900
    assert plan['required_bytes'] >= plan['source_bytes']
    assert not destination.parent.exists()
    assert snapshot(source) == before


@pytest.mark.parametrize('relation', ['inside-source', 'contains-source', 'existing', 'same'])
def test_overlapping_or_existing_destination_refused_before_write(tmp_path, relation):
    from core.artifact_archive import archive_artifacts
    from core.run_preservation import PreservationError
    source = source_tree(tmp_path)
    destination = {'inside-source': source / 'archive', 'contains-source': tmp_path,
                   'existing': source / 'empty', 'same': source}[relation]
    with pytest.raises(PreservationError):
        archive_artifacts(source, destination, apply=True)
    assert not (source / 'archive').exists()


@pytest.mark.parametrize('git_kind', ['file', 'directory'])
def test_nested_git_is_never_archived(tmp_path, git_kind):
    from core.artifact_archive import archive_artifacts
    from core.run_preservation import PreservationError
    source = source_tree(tmp_path)
    path = source / 'nested' / '.git'
    path.mkdir() if git_kind == 'directory' else path.write_text('gitdir: elsewhere', encoding='utf-8')
    with pytest.raises(PreservationError, match='git'):
        archive_artifacts(source, tmp_path / 'archive', apply=True)
    assert not (tmp_path / 'archive').exists()


def test_capacity_uses_actual_bytes_and_blocks_before_destination_creation(tmp_path, monkeypatch):
    from core import artifact_archive as archive
    from core.run_preservation import PreservationError
    source = source_tree(tmp_path)
    monkeypatch.setattr(archive.shutil, 'disk_usage', lambda path: SimpleNamespace(free=3899))
    with pytest.raises(PreservationError, match='공간'):
        archive.archive_artifacts(source, tmp_path / 'archive', apply=True)
    assert not (tmp_path / 'archive').exists()


@pytest.mark.parametrize('compress', [False, True])
def test_tampered_payload_cannot_pass_receipt_verification(tmp_path, compress):
    from core.artifact_archive import archive_artifacts, verify_archive
    from core.run_preservation import PreservationError
    source = source_tree(tmp_path)
    destination = tmp_path / 'archive'
    archive_artifacts(source, destination, compress=compress, apply=True)
    if compress:
        with zipfile.ZipFile(destination / 'archive.zip', 'a') as bundle:
            bundle.writestr('unexpected.txt', 'tamper')
    else:
        (destination / 'content' / 'nested' / '결과.txt').write_bytes(b'tamper')
    with pytest.raises(PreservationError):
        verify_archive(destination)


@pytest.mark.parametrize('compress', [False, True])
def test_source_changes_during_copy_do_not_leave_success_receipt(tmp_path, monkeypatch, compress):
    from core import artifact_archive as archive
    from core.run_preservation import PreservationError
    source = source_tree(tmp_path)
    destination = tmp_path / 'archive'
    original_check = archive.snapshot
    reads = []
    def changing_snapshot(path):
        if Path(path) == source:
            reads.append(True)
            if len(reads) == 2:
                (source / 'late.txt').write_bytes(b'new data during copy')
        return original_check(path)
    monkeypatch.setattr(archive, 'snapshot', changing_snapshot)
    with pytest.raises(PreservationError):
        archive.archive_artifacts(source, destination, compress=compress, apply=True)
    assert (source / 'late.txt').read_bytes() == b'new data during copy'
    if (destination / 'receipt.json').exists():
        assert json.loads((destination / 'receipt.json').read_text(encoding='utf-8'))['state'] != 'complete'


def test_cli_dry_run_apply_and_verify_use_real_selected_paths(tmp_path):
    from tools.archive_artifacts import main
    source = source_tree(tmp_path)
    destination = tmp_path / 'selected-archive'
    argv = ['--source', str(source), '--destination', str(destination), '--compress']
    assert main(argv) == 0
    assert not destination.exists()
    assert main(argv + ['--apply']) == 0
    assert main(['--verify', str(destination)]) == 0
    assert source.exists()


def test_source_link_and_destination_link_parent_are_refused(tmp_path):
    from core.artifact_archive import archive_artifacts
    from core.run_preservation import PreservationError
    source = source_tree(tmp_path)
    alias = tmp_path / 'alias'
    try:
        alias.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip('symlink 권한 없음')
    with pytest.raises(PreservationError):
        archive_artifacts(alias, tmp_path / 'archive', apply=True)
    with pytest.raises(PreservationError):
        archive_artifacts(source, alias / 'archive', apply=True)


@pytest.mark.parametrize('location', ['source-root', 'source-ancestor', 'destination-ancestor'])
def test_git_component_cannot_be_source_or_destination(location, tmp_path):
    from core.artifact_archive import archive_artifacts
    from core.run_preservation import PreservationError
    source = source_tree(tmp_path)
    git = tmp_path / 'repository' / '.git'
    (git / 'objects').mkdir(parents=True)
    (git / 'objects' / 'object').write_bytes(b'git data')
    selected_source = git if location == 'source-root' else git / 'objects' if location == 'source-ancestor' else source
    destination = git / 'archive' if location == 'destination-ancestor' else tmp_path / 'archive'
    with pytest.raises(PreservationError, match='git'):
        archive_artifacts(selected_source, destination, apply=True)
    assert not destination.exists()


def test_modified_manifest_is_rejected_by_receipt_readback(tmp_path):
    from core.artifact_archive import archive_artifacts, verify_archive
    from core.run_preservation import PreservationError
    source = source_tree(tmp_path)
    destination = tmp_path / 'archive'
    archive_artifacts(source, destination, apply=True)
    manifest = destination / 'manifest.json'
    manifest.write_text(manifest.read_text(encoding='utf-8') + ' ', encoding='utf-8')
    with pytest.raises(PreservationError):
        verify_archive(destination)


def test_copy_error_keeps_original_and_incomplete_destination(tmp_path, monkeypatch):
    from core import artifact_archive as archive
    from core.run_preservation import PreservationError
    source = source_tree(tmp_path)
    destination = tmp_path / 'archive'
    def fail_copy(*args, **kwargs):
        raise OSError('synthetic copy failure')
    monkeypatch.setattr(archive.shutil, 'copy2', fail_copy)
    with pytest.raises(PreservationError):
        archive.archive_artifacts(source, destination, apply=True)
    assert (source / 'nested' / '결과.txt').read_bytes() == b'original data' * 300
    assert destination.exists()
    assert json.loads((destination / 'receipt.json').read_text(encoding='utf-8'))['state'] == 'error'


def test_junction_source_is_refused_on_windows(tmp_path):
    import os
    import subprocess
    from core.artifact_archive import archive_artifacts
    from core.run_preservation import PreservationError
    if os.name != 'nt':
        pytest.skip('Windows junction 시험')
    source = source_tree(tmp_path)
    junction = tmp_path / 'junction'
    result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(junction), str(source)],
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, '임시 junction을 만들지 못했습니다.'
    with pytest.raises(PreservationError):
        archive_artifacts(junction, tmp_path / 'archive', apply=True)
