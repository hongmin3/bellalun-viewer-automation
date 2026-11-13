"""Validates: REQ-QA-001. 합성 자료만 조회하고 제품을 조작하지 않는다."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bellalunauto.runtime import Layout
from bellalunauto.runplan import build_plan, format_plan


class RunPlanTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / 'work/qa-runplan'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.layout = Layout(root / 'resources', root / 'workspace', root / 'workspace/config.json')
        assets = self.layout.resource_dir / 'assets/Baseline'
        assets.mkdir(parents=True)
        self.layout.resource_dir.joinpath('assets-manifest.json').write_text(
            json.dumps({'asset_version': 'approved-v7'}), encoding='utf-8')
        for name in ('DATA', 'ACCOUNT', 'CONFIGURATION', 'PROCEDURE'):
            (assets / (name + '.bak')).write_bytes(name.encode())
        self.config = {'viewer': {'exe': str(root / 'VIEWER.exe'),
                                  'login': {'password': 'never-include-me'}},
                       'sql_server': '.\\TEST', 'sql_service_name': 'MSSQL$TEST'}

    def plan(self, action='run-regression'):
        with patch('core.sysinfo.file_version', return_value='1.2.3.4'), \
                patch('subprocess.run', side_effect=AssertionError('제품 명령 금지')):
            return build_plan(self.layout, self.config, action)

    def test_targets_baseline_identity_and_no_files_written(self):
        before = sorted(str(p) for p in self.layout.resource_dir.rglob('*'))
        plan = self.plan()
        self.assertEqual(plan['viewer']['version'], '1.2.3.4')
        self.assertEqual(plan['sql']['instance'], '.\\TEST')
        self.assertEqual(plan['sql']['service'], 'MSSQL$TEST')
        self.assertEqual(plan['databases'], ['DATA', 'ACCOUNT', 'CONFIGURATION', 'PROCEDURE'])
        self.assertEqual(plan['baseline']['asset_version'], 'approved-v7')
        backups = plan['baseline']['files']
        self.assertEqual(len(backups), 4)
        self.assertEqual(backups[0]['sha256'], hashlib.sha256(b'DATA').hexdigest())
        self.assertTrue(backups[0]['modified_at'])
        self.assertFalse(self.layout.workspace.exists())
        self.assertEqual(before, sorted(str(p) for p in self.layout.resource_dir.rglob('*')))
        self.assertNotIn('never-include-me', json.dumps(plan))

    def test_confirmation_contains_every_change_and_restore_policy(self):
        text = format_plan(self.plan('run-winupdate'))
        for value in ('VIEWER.exe', '1.2.3.4', 'approved-v7', 'DATA', 'ACCOUNT',
                      'CONFIGURATION', 'PROCEDURE', 'MSSQL$TEST', 'Bellalun Service',
                      'AUTO_START', '1920', '1080', 'TEST_*', 'DICOM', 'BellalunWU09',
                      '기존 파일', '다음 실행', '되돌리지', 'TC 끝'):
            self.assertIn(value, text)
        self.assertIn(hashlib.sha256(b'DATA').hexdigest()[:12], text)

    def test_usb_applies_only_to_wu_and_explicit_baseline_overrides_bundle(self):
        override = self.layout.resource_dir / 'selected'
        override.mkdir()
        self.config['baseline_dir'] = str(override)
        plan = self.plan()
        self.assertEqual(plan['baseline']['path'], str(override))
        self.assertFalse(plan['changes']['usb']['enabled'])
        self.assertTrue(all(row['status'] == 'missing' for row in plan['baseline']['files']))
        self.assertIn('없음', format_plan(plan))

    def test_unavailable_version_manifest_and_hash_are_visible(self):
        self.layout.resource_dir.joinpath('assets-manifest.json').write_text('{', encoding='utf-8')
        with patch('core.sysinfo.file_version', side_effect=OSError('query unavailable')):
            plan = build_plan(self.layout, self.config, 'run-regression')
        self.assertIsNone(plan['viewer']['version'])
        self.assertIsNone(plan['baseline']['asset_version'])
        self.assertIn('확인 불가', format_plan(plan))

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            build_plan(self.layout, self.config, 'snapshot-baseline')

    def test_plan_identity_changes_for_execution_inputs_but_redacts_secrets(self):
        first = self.plan()
        self.assertTrue(first.get('plan_id'))
        self.assertEqual(first['plan_id'], self.plan()['plan_id'])
        self.config['viewer']['login']['password'] = 'another-secret'
        self.assertEqual(first['plan_id'], self.plan()['plan_id'])
        self.config['display'] = {'width': 1600}
        self.assertNotEqual(first['plan_id'], self.plan()['plan_id'])
        self.config.pop('display')
        viewer = Path(self.config['viewer']['exe'])
        viewer.write_bytes(b'viewer-one')
        next_plan = self.plan()
        self.assertNotEqual(first['plan_id'], next_plan['plan_id'])
        viewer.write_bytes(b'viewer-two')
        self.assertNotEqual(next_plan['plan_id'], self.plan()['plan_id'])
        viewer.unlink()
        (self.layout.resource_dir / 'assets/Baseline/DATA.bak').write_bytes(b'changed')
        self.assertNotEqual(first['plan_id'], self.plan()['plan_id'])
        self.assertNotIn('another-secret', json.dumps(self.plan()))

    def test_plan_uses_resource_source_and_detects_changes_inside_same_dirty_state(self):
        self.layout.resource_dir.joinpath('build-info.json').write_text(json.dumps({
            'source_commit': 'a' * 40, 'source_dirty': True}), encoding='utf-8')
        source = self.layout.resource_dir / 'core'
        source.mkdir()
        module = source / 'example.py'
        module.write_text('x = 1', encoding='utf-8')
        before = self.plan()
        self.assertEqual(before['source_identity']['source_commit'], 'a' * 40)
        module.write_text('x = 2', encoding='utf-8')
        after = self.plan()
        self.assertNotEqual(before['plan_id'], after['plan_id'])
        self.assertNotEqual(before['source_fingerprint'], after['source_fingerprint'])
        self.assertEqual(before['source_identity'], after['source_identity'])


if __name__ == '__main__':
    unittest.main()
