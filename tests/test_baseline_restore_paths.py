"""DB 미등록 시 복원 경로. SQL은 대역이며 실제 복원을 실행하지 않는다."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from core import dbreset


class BaselineRestorePathTests(unittest.TestCase):
    def context(self, current):
        listing = [{'LogicalName': 'ACCOUNT_dat', 'Type': 'D'},
                   {'LogicalName': 'ACCOUNT_log', 'Type': 'L'}]
        return SimpleNamespace(cfg={'data_dir': r'Q:\Synthetic QA\BellalunData'},
                               db=SimpleNamespace(query=Mock(side_effect=[listing, current])))

    def test_missing_master_files_use_product_standard_names_not_logical_names(self):
        context = self.context([])
        clauses = dbreset._move_clauses(context, 'ACCOUNT', r'Q:\Synthetic\ACCOUNT.bak')
        folder = os.path.join(context.cfg['data_dir'], 'Database')
        self.assertEqual(clauses,
                         [f"MOVE N'ACCOUNT_dat' TO N'{os.path.join(folder, 'ACCOUNT.mdf')}'",
                          f"MOVE N'ACCOUNT_log' TO N'{os.path.join(folder, 'ACCOUNT.ldf')}'"])

    def test_current_master_file_mapping_is_preserved(self):
        context = self.context([{'name': 'ACCOUNT_dat', 'physical_name': r'R:\Existing\custom-account.mdf'},
                                {'name': 'ACCOUNT_log', 'physical_name': r'R:\Existing\custom-account.ldf'}])
        self.assertEqual(dbreset._move_clauses(context, 'ACCOUNT', r'Q:\Synthetic\ACCOUNT.bak'),
                         ["MOVE N'ACCOUNT_dat' TO N'R:\\Existing\\custom-account.mdf'",
                          "MOVE N'ACCOUNT_log' TO N'R:\\Existing\\custom-account.ldf'"])


if __name__ == '__main__':
    unittest.main()
