"""WU_09 실패 뒤에도 새 Viewer에서 WU_10을 수행한다."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run
from core import flows


class WindowsUpdateIsolationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = SimpleNamespace(cfg={}, db=object())
        self.original_ui = object()
        self.fresh_ui = object()

    def prepare(self, outcome):
        self.assertTrue(callable(getattr(run, '_prepare_wu_setting_ui', None)))
        return run._prepare_wu_setting_ui(self.ctx, self.original_ui, outcome)

    def test_absent_usb_or_closed_success_does_not_restart(self):
        for outcome in ({'drive':None}, {'drive':'SYNTHETIC_USB', 'import':{'closed':True}}):
            with self.subTest(outcome=outcome), patch.object(flows,'cold_start') as start:
                self.assertIs(self.prepare(outcome), self.original_ui)
                start.assert_not_called()

    def test_failed_or_unclosed_usb_recovers_without_erasing_failure(self):
        for outcome in ({'drive':None,'error':'synthetic export exception'},
                        {'drive':'SYNTHETIC_USB','import':{'error':'synthetic import error','closed':True}},
                        {'drive':'SYNTHETIC_USB','import':{'closed':False}},
                        {'drive':'SYNTHETIC_USB','import':None},
                        {'drive':'SYNTHETIC_USB','import':{'closed':True},'cleanup':{'ok':False}}):
            original = deepcopy(outcome)
            with self.subTest(outcome=outcome), patch.object(flows,'cold_start',return_value=(self.fresh_ui,{})) as start:
                self.assertIs(self.prepare(outcome), self.fresh_ui)
                start.assert_called_once_with(self.ctx.cfg,self.ctx.db,force_restart=True)
                self.assertEqual(outcome,original)


if __name__=='__main__':
    unittest.main()
