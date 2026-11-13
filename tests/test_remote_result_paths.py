"""실제 PowerShell로 수집기의 junction 경계를 시험한다(원격/제품 실행 없음)."""
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from remote.winrm_executor import WinRMExecutor
from remote.coordinator import RemoteError


class LocalPowerShell:
    def run_ps(self, script):
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
        return SimpleNamespace(status_code=result.returncode, std_out=result.stdout, std_err=result.stderr)


@pytest.mark.skipif(os.name != 'nt', reason='Windows junction/PowerShell 전용')
def test_remote_result_collection_refuses_junction_ancestor(tmp_path):
    root = tmp_path / 'job'
    workspace = root / 'workspace'
    workspace.mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'private.txt').write_bytes(b'not-a-job-result')
    target = workspace / 'Evidence'
    quote = lambda path: "'" + str(path).replace("'", "''") + "'"
    created = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        f"New-Item -ItemType Junction -Path {quote(target)} -Target {quote(outside)} | Out-Null"],
        capture_output=True)
    if created.returncode:
        pytest.skip('junction 생성 권한 없음')
    (root / 'receipt.json').write_text('{}')
    output = tmp_path / 'download'
    output.mkdir()
    with pytest.raises(RemoteError):
        WinRMExecutor()._collect(LocalPowerShell(), str(root), output)
    assert not (output / 'workspace' / 'Evidence' / 'private.txt').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell 전용')
def test_remote_result_collection_copies_regular_files_with_verified_content(tmp_path):
    root = tmp_path / 'job'
    evidence = root / 'workspace' / 'Evidence'
    evidence.mkdir(parents=True)
    (evidence / 'sample.bin').write_bytes(b'fixture-evidence')
    (root / 'receipt.json').write_bytes(b'{}')
    output = tmp_path / 'download'
    output.mkdir()
    WinRMExecutor()._collect(LocalPowerShell(), str(root), output)
    assert (output / 'workspace' / 'Evidence' / 'sample.bin').read_bytes() == b'fixture-evidence'
    assert (output / 'receipt.json').read_bytes() == b'{}'
