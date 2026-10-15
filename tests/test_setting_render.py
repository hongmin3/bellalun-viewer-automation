"""Setting 렌더 증거: 값이 없는 버튼 페이지도 실제 콘텐츠가 있어야 한다."""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import setting_values as sv
from core.ui import Control


def control(hwnd, text, rect=(410, 110, 520, 145), *, visible=True,
            cls='AfxWnd140u', ctrl_id=1200):
    return Control(hwnd, ctrl_id, cls, text, rect, visible, 1)


class SettingRenderTests(unittest.TestCase):
    def sweep(self, descendants, *, settled=True, pane_visible=True):
        pane = control(20, '', (400, 100, 1800, 900), cls='#32770',
                       visible=pane_visible)
        rail = control(10, 'SettingMenuItem', (150, 100, 350, 140))
        # Product input, live enumeration and screen capture are all bounded.
        with ExitStack() as stack:
            for name, value in (('_viewer_gone', False), ('setting_window', object()),
                                ('_open_page', rail), ('pane_control', pane)):
                stack.enter_context(patch.object(sv, name, return_value=value))
            stack.enter_context(patch.object(sv, 'children', return_value=descendants))
            stack.enter_context(patch.object(sv, '_wait_page_settled',
                                              return_value=(descendants, settled)))
            stack.enter_context(patch.object(sv.screen, 'grab', return_value=object()))
            stack.enter_context(patch.object(sv.flows, 'open_setting'))
            stack.enter_context(patch.object(sv.flows, 'open_setting_group'))
            stack.enter_context(patch.object(sv.flows, 'setting_pages',
                                              return_value={'synthetic': 100}))
            return sv.read_all(SimpleNamespace(pid=10, get_text=lambda c: c.text),
                               groups=['system'])

    def render(self, *args, **kwargs):
        result = self.sweep(*args, **kwargs)
        self.assertIn('page_render', result)
        return result['page_render']['system.synthetic']

    def test_button_only_page_has_render_evidence_without_value_or_compare_changes(self):
        result = self.sweep([control(31, 'TextButton'),
                             control(32, 'TextButton', (600, 110, 720, 145))])
        self.assertEqual(result['pages'], {'system.synthetic': {}})
        self.assertIn('page_render', result)
        render = result['page_render']['system.synthetic']
        self.assertEqual([c['hwnd'] for c in render['controls']], [31, 32])
        self.assertEqual(render['pane']['hwnd'], 20)
        self.assertTrue(render['settled'])
        comparison = sv.compare(result, result)
        self.assertEqual(comparison['compared_items'], 0)
        self.assertEqual(comparison['changed'], [])

    def test_hidden_outside_zero_area_and_decorations_do_not_prove_content(self):
        controls = [control(30, 'TextButton', visible=False),
                    control(31, 'TextButton', (200, 110, 350, 150)),
                    control(32, 'TextButton', (410, 110, 410, 145)),
                    control(33, 'StaticText'), control(34, 'GroupBox'),
                    control(35, 'PngViewer'), control(36, 'FrameTransparent'),
                    control(37, 'SettingMenuItem'),
                    control(38, 'TextButton', ctrl_id=2226),
                    control(39, 'Collect logs', cls='Static')]
        self.assertEqual(self.render(controls)['controls'], [])

    def test_empty_pane_is_not_content(self):
        self.assertEqual(self.render([])['controls'], [])

    def test_hidden_pane_or_unsettled_state_is_retained_as_failed_observation(self):
        render = self.render([control(31, 'TextButton')], pane_visible=False,
                             settled=False)
        self.assertFalse(render['pane']['visible'])
        self.assertFalse(render['settled'])
        self.assertEqual(render['controls'], [])

    def test_native_input_and_custom_lists_count_but_metadata_does_not_leak_values(self):
        render = self.render([control(31, 'synthetic-secret', cls='Edit'),
                              control(32, 'ListCtrl')])
        self.assertEqual([c['hwnd'] for c in render['controls']], [31, 32])
        self.assertNotIn('synthetic-secret', repr(render))

    def test_collector_rejects_thin_decoration_and_keeps_minimum_and_real_buttons(self):
        pane = control(20, '', (400, 100, 1840, 905), cls='#32770')
        cases = [((418, 227, 1804, 228), False),  # actual CS separator geometry
                 ((418, 227, 419, 800), False),
                 ((418, 227, 418, 269), False),
                 ((418, 227, 417, 269), False),
                 ((418, 227, 558, 226), False),
                 ((418, 227, 425, 800), False),
                 ((418, 227, 1804, 234), False),
                 ((418, 227, 426, 235), True),
                 ((418, 227, 558, 269), True)]
        for rect, expected in cases:
            with self.subTest(rect=rect):
                # A custom nongeneric-text separator currently takes value_text.
                c = control(31, 'synthetic-widget', rect, ctrl_id=1000)
                observation = sv.page_render(pane, [c], True)
                self.assertEqual(bool(observation['controls']), expected)

    def test_consumer_rejects_old_thin_observations_even_before_collection_filter(self):
        cases = [((418, 227, 1804, 228), False),
                 ((418, 227, 419, 800), False),
                 ((418, 227, 418, 269), False),
                 ((418, 227, 417, 269), False),
                 ((418, 227, 558, 226), False),
                 ((418, 227, 425, 800), False),
                 ((418, 227, 1804, 234), False),
                 ((418, 227, 426, 235), True),
                 ((418, 227, 558, 269), True)]
        for rect, expected in cases:
            with self.subTest(rect=rect):
                observation = {'pane': {'hwnd': 20, 'visible': True,
                                        'rect': [400, 100, 1840, 905]},
                               'settled': True,
                               'controls': [{'hwnd': 31, 'ctrl_id': 1000,
                                             'cls': 'AfxWnd140u', 'kind': 'value_text',
                                             'rect': list(rect)}]}
                self.assertEqual(sv.page_rendered(observation), expected)


if __name__ == '__main__':
    unittest.main()
