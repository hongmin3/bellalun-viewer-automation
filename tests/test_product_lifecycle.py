"""Validates: REQ-FOLLOWUP-002. 실제 제품 대신 hash 고정 Python stub만 실행한다."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

from core import product_lifecycle as lifecycle
from core.run_preservation import RunPreservation


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture(tmp_path, exit_code=0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = tmp_path / 'stub.py'
    payload.write_text(f'from pathlib import Path\nPath(__file__).with_suffix(".ran").write_text("ran")\nraise SystemExit({exit_code})\n', encoding='utf-8')
    evidence = tmp_path / 'argv-verified.txt'
    evidence.write_text('Synthetic fixture verification only', encoding='utf-8')
    profile = {'schema': 1, 'profile_id': 'fixture', 'action': 'upgrade',
               'package': {'path': str(payload), 'sha256': digest(payload), 'kind': 'script'},
               'command': {'argv': [sys.executable, str(payload)], 'launcher_sha256': digest(sys.executable)},
               'unattended': {'verified': True, 'reviewed_by': 'fixture-only',
                              'evidence': {'path': str(evidence), 'sha256': digest(evidence)}},
               'recovery': {'steps': ['Restore the retained synthetic backup'],
                            'required_roots': ['sample'], 'database_required': False},
               'success_codes': [0], 'reboot_codes': [23], 'timeout_sec': 10}
    source = tmp_path / 'sample'
    source.mkdir()
    (source / 'data.txt').write_text('before', encoding='utf-8')
    preservation = RunPreservation(tmp_path / 'workspace', 'fixture-run', {'sample': source})
    receipt = preservation.prepare()
    return profile, receipt, payload


def test_apply_requires_concrete_approval_verified_arguments_and_valid_backup(tmp_path):
    profile, receipt, payload = fixture(tmp_path)
    plan = lifecycle.build_plan(profile)
    record = tmp_path / 'execution.json'
    with pytest.raises(lifecycle.LifecycleError, match='승인'):
        lifecycle.apply_plan(plan, approved=False, backup_receipt=receipt, record_path=record)
    assert not payload.with_suffix('.ran').exists()
    profile['unattended']['verified'] = False
    with pytest.raises(lifecycle.LifecycleError, match='무인'):
        lifecycle.build_plan(profile)
    profile['unattended']['verified'] = True
    (Path(receipt['backup']) / 'before/sample/data.txt').write_text('tampered', encoding='utf-8')
    with pytest.raises(lifecycle.LifecycleError, match='백업'):
        lifecycle.apply_plan(plan, approved=True, backup_receipt=receipt, record_path=record)
    assert not payload.with_suffix('.ran').exists()


def test_hash_change_blocks_launch_and_success_records_postcheck_before_finalize(tmp_path):
    profile, receipt, payload = fixture(tmp_path)
    plan = lifecycle.build_plan(profile)
    original = payload.read_bytes()
    payload.write_bytes(original + b'# changed')
    with pytest.raises(lifecycle.LifecycleError, match='해시'):
        lifecycle.apply_plan(plan, approved=True, backup_receipt=receipt,
                             record_path=tmp_path / 'blocked.json')
    assert not payload.with_suffix('.ran').exists()
    payload.write_bytes(original)
    order = []
    result = lifecycle.apply_plan(plan, approved=True, backup_receipt=receipt,
                  record_path=tmp_path / 'execution.json', boot_id='boot-one',
                  verify_after=lambda record: order.append('verify') or {'status': 'verified'},
                  finalize=lambda: order.append('finalize') or {'status': 'retained'})
    assert payload.with_suffix('.ran').read_text() == 'ran'
    assert result['status'] == 'completed'
    assert result['returncode'] == 0
    assert order == ['verify', 'finalize']
    assert json.loads((tmp_path / 'execution.json').read_text()) == result
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.apply_plan(plan, approved=True, backup_receipt=receipt,
                             record_path=tmp_path / 'execution.json')


def test_reboot_required_never_auto_reboots_or_repeats_installer(tmp_path):
    profile, receipt, payload = fixture(tmp_path, 23)
    plan = lifecycle.build_plan(profile)
    record = tmp_path / 'execution.json'
    calls = []
    result = lifecycle.apply_plan(plan, approved=True, backup_receipt=receipt,
                                 record_path=record, boot_id='before',
                                 finalize=lambda: calls.append('finalize'))
    assert result['status'] == 'reboot_required'
    assert calls == []
    with pytest.raises(lifecycle.LifecycleError, match='재부팅'):
        lifecycle.resume_after_reboot(record, boot_id='before', verify_after=lambda r: {'status': 'verified'})
    payload.with_suffix('.ran').unlink()
    result = lifecycle.resume_after_reboot(record, boot_id='after',
                      verify_after=lambda r: {'status': 'verified'},
                      finalize=lambda: {'status': 'retained'})
    assert result['status'] == 'completed'
    assert not payload.with_suffix('.ran').exists()


def test_unverified_postcheck_and_failed_restore_cannot_complete(tmp_path):
    profile, receipt, _ = fixture(tmp_path)
    plan = lifecycle.build_plan(profile)
    result = lifecycle.apply_plan(plan, approved=True, backup_receipt=receipt,
        record_path=tmp_path / 'execution.json', boot_id='one')
    assert result['status'] == 'verification_required'
    result = lifecycle.apply_plan(plan, approved=True, backup_receipt=receipt,
        record_path=tmp_path / 'second.json', boot_id='one',
        verify_after=lambda record: {'status': 'verified'}, finalize=lambda: {'status': 'mismatch'})
    assert result['status'] == 'recovery_required'


def test_completion_is_saved_only_after_finalizer_finishes(tmp_path):
    profile, receipt, _ = fixture(tmp_path)
    record_path = tmp_path / 'execution.json'
    during = []
    def finalize():
        during.append(json.loads(record_path.read_text(encoding='utf-8'))['status'])
        return {'status': 'verified'}
    result = lifecycle.apply_plan(lifecycle.build_plan(profile), approved=True,
        backup_receipt=receipt, record_path=record_path, boot_id='one',
        verify_after=lambda record: {'status': 'verified'}, finalize=finalize)
    assert during == ['finalizing']
    assert result['status'] == 'completed'


def test_missing_profile_evidence_or_wrong_package_type_blocks_plan(tmp_path):
    profile, _, _ = fixture(tmp_path)
    profile['package']['kind'] = 'msi'
    with pytest.raises(lifecycle.LifecycleError, match='방식'):
        lifecycle.build_plan(profile)
    profile['package']['kind'] = 'script'
    profile['unattended']['evidence']['sha256'] = '0' * 64
    with pytest.raises(lifecycle.LifecycleError, match='증거.*해시'):
        lifecycle.build_plan(profile)


def test_timeout_preserves_outcome_and_finalizes_once(tmp_path):
    import subprocess
    profile, receipt, payload = fixture(tmp_path)
    calls = []
    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
    result = lifecycle.apply_plan(lifecycle.build_plan(profile), approved=True,
        backup_receipt=receipt, record_path=tmp_path / 'execution.json', boot_id='one',
        runner=timeout, quiesce=lambda record: True,
        finalize=lambda: calls.append('finalize') or {'status': 'preserved'})
    assert result['status'] == 'timed_out'
    assert calls == ['finalize']
    assert not payload.with_suffix('.ran').exists()


def test_timeout_without_confirmed_stop_defers_restoration(tmp_path):
    import subprocess
    profile, receipt, _ = fixture(tmp_path)
    calls = []
    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
    result = lifecycle.apply_plan(lifecycle.build_plan(profile), approved=True,
        backup_receipt=receipt, record_path=tmp_path / 'execution.json', boot_id='one',
        runner=timeout, finalize=lambda: calls.append('unsafe-restore') or {'status': 'verified'})
    assert calls == []
    assert result['status'] == 'recovery_required'
    assert result['process_outcome'] == 'timed_out'


def test_cli_plan_and_explicit_apply_use_same_pinned_stub(tmp_path, capsys):
    from tools import product_lifecycle as cli
    profile, receipt, payload = fixture(tmp_path)
    profile_file, receipt_file = tmp_path / 'profile.json', tmp_path / 'receipt.json'
    profile_file.write_text(json.dumps(profile), encoding='utf-8')
    receipt_file.write_text(json.dumps(receipt), encoding='utf-8')
    plan_file = tmp_path / 'plan.json'
    assert cli.main(['plan', '--profile', str(profile_file), '--output', str(plan_file)]) == 0
    assert json.loads(plan_file.read_text())['package']['sha256'] == digest(payload)
    arguments = ['apply', '--plan', str(plan_file), '--backup-receipt', str(receipt_file),
                 '--record', str(tmp_path / 'execution.json')]
    assert cli.main(arguments) == 1
    assert not payload.with_suffix('.ran').exists()
    assert cli.main(arguments + ['--approved']) == 1
    assert payload.with_suffix('.ran').read_text() == 'ran'
    assert json.loads((tmp_path / 'execution.json').read_text(encoding='utf-8'))['status'] == 'verification_required'
    capsys.readouterr()


def cli_environment(tmp_path, monkeypatch):
    """DB·서비스·실행 잠금만 가짜. backup manifest/사본/CLI/TC 판정은 실제 경로."""
    from types import SimpleNamespace
    import run
    from core import execution_session, env_preflight
    from tests import install
    from bellalunauto import runtime
    events = []
    state = {'locked': False}
    class Lock:
        def __enter__(self):
            assert not state['locked']
            state['locked'] = True
            events.append('lock')
        def __exit__(self, *args):
            events.append('unlock')
            state['locked'] = False
    def event(name):
        assert state['locked']
        events.append(name)
    data = tmp_path / 'data'
    (data / 'Config').mkdir(parents=True)
    (data / 'Config/settings.txt').write_text('settings-before', encoding='utf-8')
    (data / 'Database').mkdir()
    (data / 'Database/state.txt').write_text('db-before', encoding='utf-8')
    (data / 'Image').mkdir()
    parameters = tmp_path / 'parameters'
    parameters.mkdir()
    installed = tmp_path / 'installed'
    installed.mkdir()
    config = {'data_dir': str(data), 'install_dir': str(installed),
              'xipl': {'parameter_dir': str(parameters)},
              'preservation': {'headroom_bytes': 0, 'generation_bytes_per_root': 0}}
    config_file = tmp_path / 'local-config.json'
    config_file.write_text(json.dumps(config), encoding='utf-8')
    class Adapter:
        def __init__(self, ctx):
            self.ctx = ctx
        def estimate_bytes(self):
            return 1024
        def backup(self, directory):
            event('db-backup')
            (directory / 'DATA.bak').write_bytes((data / 'Database/state.txt').read_bytes())
            return {'scope': 'synthetic DATA only', 'sha256': digest(directory / 'DATA.bak')}
        def verify_backup(self, directory, metadata):
            event('db-verify-backup')
            return digest(directory / 'DATA.bak') == metadata['sha256']
        def restore(self, directory, metadata):
            event('db-restore')
            (data / 'Database/state.txt').write_bytes((directory / 'DATA.bak').read_bytes())
        def verify_restored(self, directory, metadata):
            event('db-verify-restored')
            return (data / 'Database/state.txt').read_bytes() == (directory / 'DATA.bak').read_bytes()
    monkeypatch.setattr(runtime, 'RunLock', Lock)
    monkeypatch.setattr(run, 'Context', lambda path: SimpleNamespace(
        cfg=json.loads(Path(path).read_text(encoding='utf-8')), root=str(tmp_path), db=SimpleNamespace()))
    monkeypatch.setattr(execution_session, 'DatabasePreservation', Adapter)
    monkeypatch.setattr(execution_session, 'stop_product', lambda ctx: event('stop-product'))
    monkeypatch.setattr(execution_session, 'start_services', lambda: event('start-services'))
    monkeypatch.setattr(env_preflight, 'real_memory', lambda: {'avail': 4 * 1024 ** 3})
    monkeypatch.setattr(install.sysinfo, 'is_elevated', lambda: True)
    monkeypatch.setattr(install.sysinfo, 'installed_programs', lambda: {})
    monkeypatch.setattr(install.sysinfo, 'registry_value', lambda *args: 'explorer.exe')
    return config_file, data, events


@pytest.mark.parametrize('restore_after', [True, False])
def test_cli_prepare_apply_reaches_completed_with_selected_restore_policy(tmp_path, monkeypatch, capsys, restore_after):
    from tools import product_lifecycle as cli
    config, data, events = cli_environment(tmp_path, monkeypatch)
    receipt_file = tmp_path / 'receipt.json'
    workspace = tmp_path / 'workspace'
    args = ['prepare', '--config', str(config), '--workspace', str(workspace),
            '--output', str(receipt_file), '--restore-after' if restore_after else '--no-restore-after']
    assert cli.main(args) == 1
    assert events == []
    assert not receipt_file.exists()
    assert cli.main(args + ['--approved']) == 0
    receipt = json.loads(receipt_file.read_text(encoding='utf-8'))
    assert receipt['status'] == 'prepared'
    assert json.loads((Path(receipt['backup']) / 'journal.json').read_text(encoding='utf-8'))['restore_after'] is restore_after
    profile, _, payload = fixture(tmp_path / 'profile-fixture')
    profile['action'] = 'uninstall'
    profile['recovery'].update(required_roots=['Config', 'Image', 'xipl'], database_required=True)
    payload.write_text('from pathlib import Path\n'
                      f'Path({str(data / "Config/settings.txt")!r}).write_text("settings-during")\n'
                      f'Path({str(data / "Database/state.txt")!r}).write_text("db-during")\n', encoding='utf-8')
    profile['package']['sha256'] = digest(payload)
    plan_file = tmp_path / 'plan.json'
    plan_file.write_text(json.dumps(lifecycle.build_plan(profile)), encoding='utf-8')
    record_path = tmp_path / 'execution.json'
    assert cli.main(['apply', '--plan', str(plan_file), '--backup-receipt', str(receipt_file),
                     '--record', str(record_path), '--config', str(config), '--approved']) == 0
    record = json.loads(record_path.read_text(encoding='utf-8'))
    assert record['status'] == 'completed'
    assert record['post_verification']['results'][0]['verdict'] == 'PASS'
    assert record['restoration']['status'] == ('verified' if restore_after else 'preserved')
    assert (data / 'Config/settings.txt').read_text() == ('settings-before' if restore_after else 'settings-during')
    assert (data / 'Database/state.txt').read_text() == ('db-before' if restore_after else 'db-during')
    assert events.count('lock') == events.count('unlock') == 2
    assert events.count('stop-product') == events.count('start-services') == 2
    assert events.count('db-restore') == int(restore_after)
    from core.execution_session import restoration_generation
    assert not (workspace / 'work/preservation_generation.json').exists()
    generation = restoration_generation(workspace)
    assert generation == ([{'run_id': receipt['run_id'], 'journal_sha256':
                            digest(Path(receipt['backup']) / 'journal.json')}]
                          if restore_after else [])
    capsys.readouterr()


def test_cli_reboot_resume_runs_selected_finalizer_without_rerunning_package(tmp_path, monkeypatch, capsys):
    from tools import product_lifecycle as cli
    config, data, events = cli_environment(tmp_path, monkeypatch)
    receipt_file = tmp_path / 'receipt.json'
    assert cli.main(['prepare', '--config', str(config), '--workspace', str(tmp_path / 'workspace'),
                     '--output', str(receipt_file), '--restore-after', '--approved']) == 0
    profile, _, payload = fixture(tmp_path / 'profile-fixture', 23)
    profile['action'] = 'uninstall'
    profile['recovery'].update(required_roots=['Config', 'Image', 'xipl'], database_required=True)
    plan_file = tmp_path / 'plan.json'
    plan_file.write_text(json.dumps(lifecycle.build_plan(profile)), encoding='utf-8')
    record_file = tmp_path / 'execution.json'
    monkeypatch.setattr(lifecycle, 'system_boot_identity', lambda: 'before')
    assert cli.main(['apply', '--plan', str(plan_file), '--backup-receipt', str(receipt_file),
                     '--record', str(record_file), '--config', str(config), '--approved']) == 3
    assert events.count('stop-product') == 1
    payload.with_suffix('.ran').unlink()
    payload.unlink()
    args = ['resume', '--record', str(record_file), '--config', str(config)]
    assert cli.main(args) == 1
    assert events.count('stop-product') == 1
    monkeypatch.setattr(lifecycle, 'system_boot_identity', lambda: 'after')
    assert cli.main(args) == 0
    record = json.loads(record_file.read_text(encoding='utf-8'))
    assert record['status'] == 'completed'
    assert record['restoration']['status'] == 'verified'
    assert not payload.with_suffix('.ran').exists()
    assert events.count('stop-product') == events.count('start-services') == 2
    capsys.readouterr()


def test_cli_timeout_with_config_defers_restore_until_children_are_confirmed_stopped(tmp_path, monkeypatch, capsys):
    import subprocess
    from tools import product_lifecycle as cli
    config, _, events = cli_environment(tmp_path, monkeypatch)
    receipt_file = tmp_path / 'receipt.json'
    assert cli.main(['prepare', '--config', str(config), '--workspace', str(tmp_path / 'workspace'),
                     '--output', str(receipt_file), '--restore-after', '--approved']) == 0
    profile, _, payload = fixture(tmp_path / 'profile-fixture')
    profile['action'] = 'uninstall'
    profile['recovery'].update(required_roots=['Config', 'Image', 'xipl'], database_required=True)
    plan_file = tmp_path / 'plan.json'
    plan_file.write_text(json.dumps(lifecycle.build_plan(profile)), encoding='utf-8')
    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
    monkeypatch.setattr(lifecycle, 'system_boot_identity', lambda: 'boot-before')
    monkeypatch.setattr(lifecycle.subprocess, 'run', timeout)
    record_file = tmp_path / 'execution.json'
    assert cli.main(['apply', '--plan', str(plan_file), '--backup-receipt', str(receipt_file),
                     '--record', str(record_file), '--config', str(config), '--approved']) == 1
    record = json.loads(record_file.read_text(encoding='utf-8'))
    assert record['status'] == 'recovery_required'
    assert record['process_outcome'] == 'timed_out'
    assert record['restoration']['status'] == 'deferred'
    assert events.count('stop-product') == events.count('start-services') == 1
    assert not payload.with_suffix('.ran').exists()
    capsys.readouterr()
