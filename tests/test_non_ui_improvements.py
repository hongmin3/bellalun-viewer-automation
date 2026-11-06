"""UI 없는 성능 경로·결과 보존 검증."""
from unittest.mock import Mock, patch
import unittest
from core import flows
from core.result import TCResult, PASS
from tests import workflow14
from core import result


class NonUiImprovementTests(unittest.TestCase):
    def test_checkpoint_roundtrip_preserves_structured_values(self):
        from core.wu_chain import result_from_dict
        r = TCResult('sample', 'sample')
        r.add(1, 'value', PASS, expected={'value': 0}, actual={'value': None})
        restored = result_from_dict(r.as_dict())
        self.assertEqual(restored.checks[0].actual, {'value': None})
        self.assertEqual(restored.checks[0].expected, {'value': 0})

    def test_nested_report_value_is_folded_and_escaped(self):
        rendered = result._report_value({'<field>': {'before': 1, 'after': 2}})
        self.assertIn('<details', rendered)
        self.assertIn('&lt;field&gt;', rendered)
        self.assertNotIn('<field>', rendered)

    def test_structured_actual_preserves_nested_values(self):
        r = TCResult('sample', 'sample')
        r.add(1, 'sample', PASS, actual={'changed': [{'before': 0, 'after': None}]})
        self.assertEqual(r.checks[0].as_dict()['actual_data'],
                         {'changed': [{'before': 0, 'after': None}]})

    def test_timed_collection_records_failure_and_reraises(self):
        r = TCResult('sample', 'sample')
        with self.assertRaisesRegex(ValueError, 'broken'):
            workflow14._timed_collect(r, 'before', Mock(side_effect=ValueError('broken')))
        self.assertEqual(r.timings[0]['outcome'], 'error')

    def test_setting_rail_lookup_avoids_global_tree(self):
        ui = Mock()
        control = Mock(ctrl_id=177, visible=True, rect=(0, 0, 100, 40))
        with patch('core.setting_values.setting_window', return_value=Mock()), \
             patch('core.setting_values.shallow', return_value=[control]), \
             patch.object(flows.time, 'sleep'):
            self.assertIs(flows._click_setting_control(ui, 177, 'group'), control)
        ui.controls.assert_not_called()

    def test_update_button_keeps_deep_lookup(self):
        ui = Mock()
        control = Mock(ctrl_id=2226, visible=True, rect=(0, 0, 100, 40))
        ui.controls.return_value = [control]
        with patch.object(flows.time, 'sleep'):
            self.assertIs(flows._click_setting_control(ui, 2226, 'update'), control)
        ui.controls.assert_called_once_with(max_depth=7)

    def test_completed_collection_preserves_value(self):
        r = TCResult('sample', 'sample')
        value = {'pages': {'sample': {}}}
        self.assertIs(workflow14._timed_collect(r, 'before', lambda: value), value)
        self.assertEqual(r.timings[0]['outcome'], 'completed')
