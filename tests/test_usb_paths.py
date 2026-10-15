"""USB export folder safety using temporary directories only."""
import importlib
import os
from pathlib import Path, PureWindowsPath
import subprocess
import tempfile
import unittest
from unittest.mock import patch


class USBExportPathTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'core/usb_paths.py'
        self.assertTrue(source.is_file(), 'USB owned-folder safety helper is required')
        self.module = importlib.import_module('core.usb_paths')
        self.temporary = tempfile.TemporaryDirectory(prefix='usb path safety ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / 'BellalunWU09'
        self.external = self.root / 'outside'
        self.external.mkdir()
        self.sentinel = self.external / 'keep.txt'
        self.sentinel.write_bytes(b'outside sentinel')

    def test_windows_drive_validation_is_pure_and_requires_drive_letter_absolute_root(self):
        for drive in ['E:\\', 'E:/']:
            with self.subTest(drive=drive):
                self.assertTrue(PureWindowsPath(self.module.validate_drive_root(drive)).is_absolute())
        for drive in ['', 'E:', 'relative', 'E:/nested', 'E:/nested/..', '//server/share/', str(self.root)]:
            with self.subTest(drive=drive), self.assertRaises(ValueError):
                self.module.prepare_export_folder(drive)
        self.assertFalse(self.target.exists())

    def test_normal_owned_folder_is_cleared_and_external_sentinel_is_preserved(self):
        nested = self.target / 'nested'
        nested.mkdir(parents=True)
        first, second = self.target / 'one.img', nested / 'two.img'
        first.write_bytes(b'old one')
        second.write_bytes(b'old two')
        target, cleared = self.module._prepare_owned_folder(self.root)
        self.assertEqual(Path(target), self.target.resolve())
        self.assertEqual(set(cleared), {str(first.resolve()), str(second.resolve())})
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(self.sentinel.read_bytes(), b'outside sentinel')

    def test_missing_owned_folder_is_created_without_removing_other_folders(self):
        target, cleared = self.module._prepare_owned_folder(self.root)
        self.assertTrue(Path(target).is_dir())
        self.assertEqual(cleared, [])
        self.assertEqual(self.sentinel.read_bytes(), b'outside sentinel')

    def test_only_fixed_single_owned_component_can_be_used(self):
        for folder in ['', '.', '..', '../outside', 'outside', 'sub/BellalunWU09',
                       'sub\\BellalunWU09', 'C:/BellalunWU09', 'BellalunWU09:stream',
                       'BellalunWU09.', 'BellalunWU09 ']:
            with self.subTest(folder=folder), self.assertRaises(ValueError):
                self.module._prepare_owned_folder(self.root, folder)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.sentinel.is_file())

    def test_symlink_escape_is_rejected_before_any_existing_file_is_deleted(self):
        self.target.mkdir()
        own = self.target / 'owned.img'
        own.write_bytes(b'owned fixture')
        try:
            (self.target / 'escape').symlink_to(self.external, target_is_directory=True)
        except OSError:
            self.skipTest('symlink creation unavailable')
        with self.assertRaises(ValueError):
            self.module._prepare_owned_folder(self.root)
        self.assertEqual(own.read_bytes(), b'owned fixture')
        self.assertEqual(self.sentinel.read_bytes(), b'outside sentinel')

    def test_target_symlink_is_rejected_and_external_sentinel_is_untouched(self):
        try:
            self.target.symlink_to(self.external, target_is_directory=True)
        except OSError:
            self.skipTest('symlink creation unavailable')
        with self.assertRaises(ValueError):
            self.module._prepare_owned_folder(self.root)
        self.assertEqual(self.sentinel.read_bytes(), b'outside sentinel')

    @unittest.skipUnless(os.name == 'nt', 'Windows junction regression')
    def test_nested_junction_escape_is_rejected_before_any_deletion(self):
        self.target.mkdir()
        own = self.target / 'owned.img'
        own.write_bytes(b'owned fixture')
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(self.target / 'escape'), str(self.external)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.assertRaises(ValueError):
            self.module._prepare_owned_folder(self.root)
        self.assertEqual(own.read_bytes(), b'owned fixture')
        self.assertEqual(self.sentinel.read_bytes(), b'outside sentinel')

    def test_deletion_failure_is_propagated_and_never_ignored(self):
        self.target.mkdir()
        own = self.target / 'locked.img'
        own.write_bytes(b'owned fixture')
        unlink = Path.unlink
        def denied(path, *args, **kwargs):
            if path == own:
                raise PermissionError('synthetic permission failure')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', denied), self.assertRaises(PermissionError):
            self.module._prepare_owned_folder(self.root)
        self.assertEqual(own.read_bytes(), b'owned fixture')
        self.assertEqual(self.sentinel.read_bytes(), b'outside sentinel')


if __name__ == '__main__':
    unittest.main()
