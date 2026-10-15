"""기존 소스 CLI도 같은 제품 잠금과 새 worker 감시를 사용한다."""
import importlib
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class LegacyLaunchTests(unittest.TestCase):
    def wrapper(self):
        # Legacy _paths import is neutralized; never changes CWD or runs a TC.
        root = str(Path(__file__).resolve().parents[1])
        with patch.dict('sys.modules', {'_paths':SimpleNamespace(REPO=root)}):
            return importlib.import_module('tools.run_regression')

    def test_wrapper_delegates_to_explicit_worker_guard_without_python_run_py(self):
        module = self.wrapper()
        self.assertTrue(callable(getattr(module, 'launch_arguments', None)))
        with patch('bellalunauto.app.main', return_value=17) as launch:
            self.assertEqual(module.main([]), 17)
        args = launch.call_args.args[0]
        self.assertEqual(args[-1], 'run-regression')
        self.assertIn('--workspace', args)
        self.assertNotIn('run.py', args)

    def test_wrapper_explicit_config_keeps_old_output_location(self):
        module = self.wrapper()
        self.assertTrue(callable(getattr(module, 'launch_arguments', None)))
        path = Path.cwd()/'한글 설정'/'config.json'
        args = module.launch_arguments(['--config', str(path)])
        self.assertEqual(args[args.index('--workspace')+1], str(path.parent))
        self.assertEqual(args[args.index('--config')+1], str(path))

    def test_source_entry_gate_bypasses_only_actual_parent_owned_lock(self):
        from bellalunauto import app
        self.assertTrue(callable(getattr(app, 'legacy_product_lock', None)))
        with patch.dict(os.environ, {'BELLALUN_PRODUCT_LOCK_OWNER':'123'}), \
             patch.object(os, 'getppid', return_value=123), patch.object(app, 'RunLock') as lock:
            with app.legacy_product_lock(['run-regression']):
                pass
            lock.assert_not_called()
        with patch.dict(os.environ, {'BELLALUN_PRODUCT_LOCK_OWNER':'122'}), \
             patch.object(os, 'getppid', return_value=123), patch.object(app, 'RunLock') as lock:
            with app.legacy_product_lock(['run-regression']):
                pass
            lock.assert_called_once()


if __name__ == '__main__':
    unittest.main()
