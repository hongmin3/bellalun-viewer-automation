# -*- coding: utf-8 -*-
"""PowerShell 명령에 넣는 경로의 작은따옴표 처리를 고정한다.

2026-10-18 경로 독립성 점검: Viewer 버전·설치 패키지 서명 확인이 경로를
`'...'` 안에 그대로 넣어, 경로에 `'`가 있으면 PowerShell 문법 오류로 값을 읽지
못했다(버전 None → 설치 정보 판정이 틀어진다). PowerShell 작은따옴표 문자열은
`'`를 `''`로 써야 한다.
"""
import unittest
from unittest import mock

from core import sysinfo

PATH = r"D:\O'Brien QA\Bellalun\VIEWER.exe"
QUOTED = r"'D:\O''Brien QA\Bellalun\VIEWER.exe'"


class PowerShellLiteralTests(unittest.TestCase):
    def test_literal_doubles_single_quotes(self):
        self.assertEqual(QUOTED, sysinfo.ps_literal(PATH))
        self.assertEqual("'C:\\한글 경로\\a.exe'", sysinfo.ps_literal("C:\\한글 경로\\a.exe"))

    def test_sysinfo_file_version_quotes_path(self):
        with mock.patch.object(sysinfo.os.path, "exists", return_value=True), \
                mock.patch.object(sysinfo, "_ps", return_value="1.0.12.105") as ps:
            self.assertEqual("1.0.12.105", sysinfo.file_version(PATH))
        self.assertIn(f"-LiteralPath {QUOTED}", ps.call_args[0][0])

    def test_run_file_version_quotes_path(self):
        import run
        done = mock.Mock(stdout=b"1.0.12.105\r\n")
        with mock.patch.object(run.os.path, "exists", return_value=True), \
                mock.patch.object(run.subprocess, "run", return_value=done) as call:
            self.assertEqual("1.0.12.105", run._file_version(PATH))
        self.assertIn(f"-LiteralPath {QUOTED}", call.call_args[0][0][-1])

    def test_install_package_signature_quotes_path(self):
        from tests import install_package
        done = mock.Mock(stdout=b"Valid|CN=Vendor\r\n", returncode=0)
        with mock.patch.object(install_package.subprocess, "run", return_value=done) as call:
            install_package._authenticode(PATH)
        self.assertIn(f"-LiteralPath {QUOTED}", call.call_args[0][0][-1])


if __name__ == "__main__":
    unittest.main()
