"""A standalone XIPL preparation failure must produce a real FAIL report."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run
from core import checklist, dbreset, display, sysinfo
from core.result import TCResult
from tests import xipl_flows


class XiplPreparationReportTests(unittest.TestCase):
    def test_each_standalone_preparation_exception_writes_fresh_fail_report(self):
        for number in ('01', '02', '03', '06'):
            with self.subTest(number=number), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                ctx = SimpleNamespace(root=str(root), resource_root=str(root),
                    reports_root=str(root/'Reports'), cfg={'viewer':{'exe':str(root)},
                        'xipl':{'studio_exe':str(root),'parameter_dir':str(root),
                                'tesseract_exe':str(root)}})
                error = RuntimeError('synthetic fixture selection failure')
                with patch.object(run.sys, 'argv', ['run.py', f'run-xipl-{number}']), \
                     patch.object(run, 'Context', return_value=ctx), \
                     patch.object(display, 'normalize', return_value={'actual':(1920,1080),'dpi_ok':True,'dpi':96}), \
                     patch.object(sysinfo, 'is_elevated', return_value=True), \
                     patch.object(dbreset, 'ensure_database_service', return_value={'after':'RUNNING','changed':[]}), \
                     patch.object(xipl_flows, '_prepare', side_effect=error), \
                     patch.object(xipl_flows, f'compatibility_{number}') as scenario, \
                     patch.object(run, '_report_meta', return_value={}), \
                     patch.object(run, 'pad_aborted_steps'), \
                     patch.object(run, 'LAST_REPORT_PATHS', {}), \
                     patch.object(TCResult, 'stop_on_fail', True), \
                     patch.object(checklist, 'source_path', return_value=None), \
                     redirect_stdout(io.StringIO()):
                    code = run._main()
                self.assertEqual(code, 1)
                scenario.assert_not_called()
                reports = list((root/'Reports').glob('Result_*.json'))
                self.assertEqual(len(reports), 1)
                rows = json.loads(reports[0].read_text(encoding='utf-8'))['results']
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['tc_id'], f'TC_XIPL_compatibility_{number}')
                self.assertEqual(rows[0]['verdict'], 'FAIL')
                self.assertEqual(rows[0]['checks'][0]['actual'], str(error))


if __name__ == '__main__':
    unittest.main()
