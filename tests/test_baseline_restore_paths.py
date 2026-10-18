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


class BaselineSqlQuotingTests(unittest.TestCase):
    """경로의 작은따옴표가 SQL 문자열을 끊지 않아야 한다(2026-10-18 경로 독립성 점검).

    `RESTORE FILELISTONLY`와 MOVE 절은 이미 `_quote`를 쓰는데, 실제 RESTORE/BACKUP
    문장만 쓰지 않아 `data_dir`에 `'`가 있으면 서비스를 멈춘 뒤 복원이 문법 오류로 실패했다.
    """
    PATH = r"Q:\O'Brien QA\BellalunData\Backup\Baseline\ACCOUNT.bak"

    def test_restore_statement_escapes_quotes_in_path(self):
        sql = dbreset._restore_sql('ACCOUNT', self.PATH, ["MOVE N'a' TO N'b'"])
        self.assertIn(r"FROM DISK = N'Q:\O''Brien QA\BellalunData", sql)
        self.assertTrue(sql.startswith('RESTORE DATABASE [ACCOUNT] '))
        self.assertTrue(sql.endswith("WITH REPLACE, MOVE N'a' TO N'b'"))

    def test_backup_statement_escapes_quotes_in_path(self):
        sql = dbreset._backup_sql('ACCOUNT', self.PATH)
        self.assertIn(r"TO DISK = N'Q:\O''Brien QA\BellalunData", sql)
        self.assertTrue(sql.endswith('WITH INIT, FORMAT, STATS=10'))


if __name__ == '__main__':
    unittest.main()
