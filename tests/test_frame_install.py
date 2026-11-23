# -*- coding: utf-8 -*-
"""설치 폴더 권한과 이전 데이터 옮기기(core/frame_install). VXvue selfcheck/test_frame_install.py와 같은 내용이다.

Validates: REQ-FRAME-003
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from core import frame_install as fi


class MigrateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='frame 설치 '))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.legacy = self.root / 'Program Files' / 'App' / '작업'
        self.app = self.root / 'App'
        (self.legacy / 'Reports').mkdir(parents=True)
        (self.legacy / 'Evidence' / 'Flow').mkdir(parents=True)
        (self.legacy / 'config.json').write_text('{"old": true}', encoding='utf-8')
        (self.legacy / 'Reports' / 'Result_1.html').write_text('결과', encoding='utf-8')
        (self.legacy / 'Evidence' / 'Flow' / '01.png').write_bytes(b'png')
        self.app.mkdir()

    def test_config_goes_to_settings_and_folders_keep_names(self):
        result = fi.migrate(self.legacy, self.app)
        self.assertEqual((3, 0, str(self.legacy)), (result['copied'], result['kept'], result['source']))
        self.assertEqual('{"old": true}', (self.app / 'Settings' / 'config.json').read_text(encoding='utf-8'))
        self.assertTrue((self.app / 'Reports' / 'Result_1.html').is_file())
        self.assertTrue((self.app / 'Evidence' / 'Flow' / '01.png').is_file())
        self.assertFalse((self.app / 'config.json').exists())
        self.assertTrue((self.legacy / 'config.json').is_file(), '이전 폴더는 지우지 않는다')

    def test_existing_files_are_never_overwritten_and_rerun_is_harmless(self):
        (self.app / 'Settings').mkdir()
        (self.app / 'Settings' / 'config.json').write_text('{"new": true}', encoding='utf-8')
        first = fi.migrate(self.legacy, self.app)
        second = fi.migrate(self.legacy, self.app)
        self.assertEqual((2, 1), (first['copied'], first['kept']))
        self.assertEqual((0, 3), (second['copied'], second['kept']))
        self.assertEqual('{"new": true}', (self.app / 'Settings' / 'config.json').read_text(encoding='utf-8'))

    def test_missing_or_same_folder_does_nothing(self):
        self.assertIsNone(fi.migrate(self.root / '없음', self.app)['source'])
        self.assertIsNone(fi.migrate(self.app, self.app)['source'])
        self.assertIsNone(fi.migrate(self.root, self.app)['source'], '새 폴더를 품은 폴더를 복사하지 않는다')

    def test_legacy_candidates_come_from_program_files(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'ProgramW6432': str(self.root / 'Program Files'),
                                          'ProgramFiles': str(self.root / 'Program Files')}):
            self.assertEqual([self.legacy], fi.legacy_program_files('App', '작업'))
            self.assertEqual([], fi.legacy_program_files('Other', '작업'))


class HardenCommandTests(unittest.TestCase):
    def test_commands_cut_inheritance_and_grant_only_data_folders(self):
        commands = fi.harden_commands(Path('C:/App'), ('Settings', 'Reports'))
        self.assertEqual(['icacls', str(Path('C:/App')), '/inheritance:r', '/grant:r',
                          '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-545:(OI)(CI)RX'], commands[0])
        self.assertEqual([['icacls', str(Path('C:/App/Settings')), '/grant', '*S-1-5-32-545:(OI)(CI)M'],
                          ['icacls', str(Path('C:/App/Reports')), '/grant', '*S-1-5-32-545:(OI)(CI)M']], commands[1:])

    def test_failure_is_reported_with_command(self):
        with tempfile.TemporaryDirectory() as folder:
            def runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 5, b'', b'denied')
            with self.assertRaisesRegex(OSError, 'denied'):
                fi.harden(folder, ('Reports',), runner=runner)

    def test_missing_install_folder_is_error(self):
        with self.assertRaises(OSError):
            fi.harden(Path(tempfile.gettempdir()) / 'frame-install-없음-x', ())


@unittest.skipUnless(os.name == 'nt' and shutil.which('icacls'), 'Windows icacls 필요')
class RealAclTests(unittest.TestCase):
    """임시 폴더에 실제 icacls를 실행하고 Windows가 돌려주는 권한을 읽는다."""

    def acl(self, path):
        script = ("(Get-Acl -LiteralPath $env:FRAME_ACL_PATH).Access | ForEach-Object { "
                  "$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value + '|' + "
                  "[int]$_.FileSystemRights + '|' + $_.IsInherited }")
        out = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, env=dict(os.environ, FRAME_ACL_PATH=str(path)), check=True)
        return [line.split('|') for line in out.stdout.splitlines() if line.strip()]

    def test_root_loses_inherited_write_and_data_folder_gains_user_modify(self):
        root = Path(tempfile.mkdtemp(prefix='frame acl '))
        try:
            app = root / 'App'
            app.mkdir()
            (app / 'program.exe').write_bytes(b'x')
            fi.harden(app, ('Reports',))
            write = 0x2 | 0x4 | 0x10000  # WriteData, AppendData, Delete
            users, authenticated = 'S-1-5-32-545', 'S-1-5-11'
            for path in (app, app / 'program.exe'):
                for sid, rights, _ in self.acl(path):
                    if sid in (users, authenticated):
                        self.assertFalse(int(rights) & write, f'{path}: {sid} 쓰기 권한 남음')
            self.assertFalse(any(inherited == 'True' for _, _, inherited in self.acl(app)), '상속이 남음')
            modify = [int(r) for sid, r, _ in self.acl(app / 'Reports') if sid == users]
            self.assertTrue(any(r & 0x2 and r & 0x10000 for r in modify), 'Reports에 사용자 수정 권한 없음')
        finally:
            subprocess.run(['icacls', str(root), '/reset', '/T', '/C', '/Q'], capture_output=True,
                           stdin=subprocess.DEVNULL)
            shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
