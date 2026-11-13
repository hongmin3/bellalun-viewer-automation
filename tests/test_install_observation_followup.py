from types import SimpleNamespace
from tests import install


def test_missing_baseline_still_collects_actual_installation(tmp_path, monkeypatch):
    (tmp_path / 'viewer.exe').write_bytes(b'fixture')
    monkeypatch.setattr(install.sysinfo, 'installed_programs', lambda: {'Bellalun': '1.2'})
    monkeypatch.setattr(install.sysinfo, 'file_version', lambda path: '2.3')
    ctx = SimpleNamespace(cfg={'release_note': {}, 'install_dir': str(tmp_path)},
                          db=SimpleNamespace(scalar=lambda *a: 'db-version'))
    result = install.install_01(ctx)
    actual = result.as_dict()['checks'][0]['actual_data']
    assert actual['installed_programs'] == {'Bellalun': '1.2'}
    assert actual['installed_files'] == {'viewer.exe': '2.3'}
    assert result.verdict == 'MANUAL'


def test_approved_known_values_are_compared_even_when_db_baseline_missing(tmp_path, monkeypatch):
    (tmp_path / 'viewer.exe').write_bytes(b'fixture')
    monkeypatch.setattr(install.sysinfo, 'installed_programs', lambda: {'Bellalun': '1.2'})
    monkeypatch.setattr(install.sysinfo, 'file_version', lambda path: '2.3')
    ctx = SimpleNamespace(cfg={'release_note': {'_source': 'approved.docx',
        'programs': {'Bellalun': '1.2'}, 'files': {'viewer.exe': '2.3'},
        'db_software_version': None}, 'install_dir': str(tmp_path)},
        db=SimpleNamespace(scalar=lambda *a: 'observed-only'))
    result = install.install_01(ctx)
    assert len([check for check in result.checks if check.status == 'PASS']) == 3
    assert result.checks[-1].status == 'MANUAL'
    assert result.checks[-1].actual == 'observed-only'


def test_release_note_product_version_never_uses_file_version(tmp_path, monkeypatch):
    from core import release_note_baseline
    monkeypatch.setattr(install.sysinfo, 'installed_programs', lambda: {'Bellalun': '1.2'})
    monkeypatch.setattr(install.sysinfo, 'file_version', lambda path: 'wrong-file-version')
    monkeypatch.setattr(release_note_baseline, 'product_version', lambda path: 'product-version')
    ctx = SimpleNamespace(cfg={'release_note': {'_source': 'approved.docx',
        'programs': {'Bellalun': '1.2'}, 'files': {'viewer.exe': 'product-version'},
        '_file_version_kind': 'product', 'db_software_version': 'db-version'},
        'install_dir': str(tmp_path)}, db=SimpleNamespace(scalar=lambda *a: 'db-version'))
    assert install.install_01(ctx).verdict == 'PASS'


def test_lifecycle_registry_refuses_reboot_wait_or_missing_prepost():
    for action, status in (('install', 'reboot_required'), ('upgrade', 'process_completed')):
        result = install.evaluate_lifecycle(SimpleNamespace(), {'action': action, 'status': status})
        assert result.verdict == 'BLOCKED'
    assert {row['lifecycle_action'] for row in install.REGISTRY if 'lifecycle_action' in row} == {
        'install', 'upgrade', 'uninstall'}


def test_lifecycle_manual_or_unperformed_verdicts_never_verify(monkeypatch):
    from core.result import TCResult
    for status in ('MANUAL', 'BLOCKED', 'SKIP', 'PASS', 'FAIL'):
        result = TCResult('TC_Basic_Install_07', '합성 후속 검증')
        result.stop_on_fail = False
        result.add(1, '합성 판정', status)
        monkeypatch.setattr(install, 'evaluate_lifecycle', lambda *args, _result=result: _result)
        payload = install.lifecycle_verifier(SimpleNamespace())({'action': 'install'})
        assert payload['status'] == ('verified' if status in {'PASS', 'FAIL'} else 'verification_required')
        assert payload['results'][0]['verdict'] == status
        assert payload['product_verdict'] == status


def test_lifecycle_preserves_real_failed_uninstall_checks_without_losing_result(tmp_path, monkeypatch):
    (tmp_path / 'leftover.dll').write_bytes(b'fixture')
    data = tmp_path / 'data'
    (data / 'Database').mkdir(parents=True)
    (data / 'Database/fixture.bak').write_bytes(b'fixture')
    (data / 'Image').mkdir()
    monkeypatch.setattr(install.sysinfo, 'is_elevated', lambda: True)
    monkeypatch.setattr(install.sysinfo, 'installed_programs', lambda: {})
    monkeypatch.setattr(install.sysinfo, 'registry_value', lambda *args: 'explorer.exe')
    ctx = SimpleNamespace(cfg={'install_dir': str(tmp_path), 'data_dir': str(data)})
    result = install.lifecycle_verifier(ctx)({'action': 'uninstall', 'status': 'process_completed'})
    assert result['status'] == 'verified'
    assert result['product_verdict'] == 'FAIL'
    assert any(check['status'] == 'FAIL' for check in result['results'][0]['checks'])
