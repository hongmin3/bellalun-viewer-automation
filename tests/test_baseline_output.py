"""Safe snapshot destination tests; every DB/service operation is mocked."""
from pathlib import Path
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core import dbreset


class BaselineOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='baseline 한글 ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.resources = self.root/'install/resources'
        self.approved = self.resources/'assets/Baseline'
        self.workspace = self.root/'workspace'
        self.staging = self.root/'data/Backup/Baseline'
        for folder in (self.approved, self.staging):
            folder.mkdir(parents=True)
        for database in ('DATA', 'ACCOUNT', 'CONFIGURATION', 'PROCEDURE'):
            (self.approved/f'{database}.bak').write_bytes(f'approved {database}'.encode())
            (self.staging/f'{database}.bak').write_bytes(f'new snapshot {database}'.encode())
        self.ctx = SimpleNamespace(root=str(self.workspace), resource_root=str(self.resources),
                                   cfg={'baseline_dir':str(self.approved),
                                        'data_dir':str(self.root/'data')},
                                   db=SimpleNamespace(query=Mock(return_value=[])))

    def backup(self):
        with patch.object(dbreset, 'staging_dir', return_value=str(self.staging)), \
             patch.object(dbreset, 'stop_app_processes'), \
             patch.object(dbreset, 'start_app_services', return_value={'service':'RUNNING'}), \
             patch.object(dbreset.subprocess, 'run', side_effect=AssertionError('real process call')):
            return dbreset.backup_baseline(self.ctx)

    def test_installed_approved_baselines_are_preserved_and_snapshot_goes_to_workspace(self):
        saved = self.backup()
        for database in ('DATA', 'ACCOUNT', 'CONFIGURATION', 'PROCEDURE'):
            self.assertEqual((self.approved/f'{database}.bak').read_bytes(), f'approved {database}'.encode())
            self.assertEqual((self.workspace/'Baseline'/f'{database}.bak').read_bytes(),
                             f'new snapshot {database}'.encode())
        self.assertEqual(Path(saved['_copied_to']), self.workspace/'Baseline')
        self.assertEqual(Path(dbreset.source_dir(self.ctx)), self.approved)

    def test_external_operator_baseline_location_remains_the_output_destination(self):
        operator = self.root/'operator snapshots'
        self.ctx.cfg['baseline_dir'] = str(operator)
        saved = self.backup()
        self.assertEqual(saved['_copied_to'], str(operator))
        self.assertEqual((operator/'DATA.bak').read_bytes(), b'new snapshot DATA')
        self.assertFalse((self.workspace/'Baseline').exists())

    def test_resource_path_with_parent_segments_still_redirects_to_workspace(self):
        self.ctx.cfg['baseline_dir'] = str(self.resources/'assets/../assets/Baseline')
        saved = self.backup()
        self.assertEqual(Path(saved['_copied_to']), self.workspace/'Baseline')
        self.assertEqual((self.approved/'DATA.bak').read_bytes(), b'approved DATA')

    def test_similarly_named_external_folder_is_not_treated_as_installed_resources(self):
        operator = self.resources.parent/'resources-other/Baseline'
        self.ctx.cfg['baseline_dir'] = str(operator)
        saved = self.backup()
        self.assertEqual(saved['_copied_to'], str(operator))
        self.assertEqual((operator/'DATA.bak').read_bytes(), b'new snapshot DATA')

    def test_workspace_inside_resources_is_rejected_before_database_or_service_work(self):
        self.ctx.root = str(self.resources/'bad workspace')
        with patch.object(dbreset, 'staging_dir', side_effect=AssertionError('created staging folder')), \
             patch.object(dbreset, 'stop_app_processes', side_effect=AssertionError('stopped services')), \
             patch.object(dbreset, 'start_app_services', side_effect=AssertionError('started services')):
            with self.assertRaises(ValueError):
                dbreset.backup_baseline(self.ctx)
        self.ctx.db.query.assert_not_called()
        self.assertFalse(Path(self.ctx.root).exists())

    def test_staging_inside_resources_is_rejected_before_database_or_service_work(self):
        data = self.resources/'wrong data folder'
        self.ctx.cfg['data_dir'] = str(data)
        with patch.object(dbreset, 'staging_dir', side_effect=AssertionError('created staging folder')), \
             patch.object(dbreset, 'stop_app_processes', side_effect=AssertionError('stopped services')), \
             patch.object(dbreset, 'start_app_services', side_effect=AssertionError('started services')):
            with self.assertRaises(ValueError):
                dbreset.backup_baseline(self.ctx)
        self.ctx.db.query.assert_not_called()
        self.assertFalse(data.exists())

    def assert_leaf_links_rejected(self, staging=False, hardlink=False, directory_link=False):
        output = self.staging if staging else self.root/'operator snapshots'
        output.mkdir(parents=True, exist_ok=True)
        if not staging:
            self.ctx.cfg['baseline_dir'] = str(output)
        for database in ('DATA', 'ACCOUNT', 'CONFIGURATION', 'PROCEDURE'):
            with self.subTest(database=database, staging=staging, hardlink=hardlink):
                leaf = output/f'{database}.bak'
                if leaf.exists():
                    leaf.unlink()
                approved = self.approved/f'{database}.bak'
                original = approved.read_bytes()
                try:
                    if hardlink:
                        os.link(approved, leaf)
                    else:
                        leaf.symlink_to(self.approved if directory_link else approved,
                                        target_is_directory=directory_link)
                except OSError:
                    self.skipTest('temporary filesystem does not support the requested links')
                try:
                    self.ctx.db.query.reset_mock()
                    with patch.object(dbreset, 'staging_dir', return_value=str(self.staging)) as stage, \
                         patch.object(dbreset, 'stop_app_processes') as stop, \
                         patch.object(dbreset, 'start_app_services', return_value={}) as start, \
                         patch.object(dbreset.subprocess, 'run', side_effect=AssertionError('real process')):
                        with self.assertRaisesRegex(ValueError, '링크'):
                            dbreset.backup_baseline(self.ctx)
                    stage.assert_not_called()
                    stop.assert_not_called()
                    start.assert_not_called()
                    self.ctx.db.query.assert_not_called()
                    self.assertEqual(approved.read_bytes(), original)
                finally:
                    leaf.unlink(missing_ok=True)
                    if staging:
                        leaf.write_bytes(f'new snapshot {database}'.encode())

    def test_output_backup_leaf_symlinks_are_rejected_before_product_work(self):
        self.assert_leaf_links_rejected()

    def test_sql_staging_backup_leaf_symlinks_are_rejected_before_product_work(self):
        self.assert_leaf_links_rejected(staging=True)

    def test_output_backup_leaf_hardlinks_are_rejected_before_product_work(self):
        self.assert_leaf_links_rejected(hardlink=True)

    def test_sql_staging_backup_leaf_hardlinks_are_rejected_before_product_work(self):
        self.assert_leaf_links_rejected(staging=True, hardlink=True)

    def test_output_backup_leaf_directory_links_are_rejected_before_product_work(self):
        self.assert_leaf_links_rejected(directory_link=True)


if __name__ == '__main__':
    unittest.main()
