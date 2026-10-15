"""Exact fixture selection through fresh card logs; all UI/DB calls simulated."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core import usb_evidence, viewer_processing as vp


def control(identifier, text='', y=100, **attributes):
    return SimpleNamespace(hwnd=identifier, ctrl_id=identifier, visible=True,
                           text=text, rect=(100, y, 400, y+50), **attributes)


class XiplStudySelectionTests(unittest.TestCase):
    def simulate(self, card_keys=(50, 48), *, steps=2, log_error=None, types=(0,1,2,3)):
        ui = Mock()
        cards = [control(1000+key, 'StudyListItem', y=100+index*100, fixture_key=key)
                 for index, key in enumerate(card_keys)]
        ui.selected_key = None
        events = []

        def click(item, **kwargs):
            if hasattr(item, 'fixture_key'):
                ui.selected_key = item.fixture_key
                events.append(('card', item.fixture_key))
            elif item.ctrl_id == 2182:
                events.append(('open', ui.selected_key))

        ui.click.side_effect = click
        ui.by_id.side_effect = lambda identifier: [control(identifier)]
        ui.windows.return_value = [control(600, 'ItemList')]
        db = Mock()
        db.one.return_value = {'Key':50}
        db.query.return_value = [{'InstanceType':kind} for kind in types]
        ctx = SimpleNamespace(cfg={'xipl':{'test_patient_id':'synthetic patient'},
                                   'data_dir':'synthetic data'}, db=db)

        def cursor(data_dir):
            events.append(('cursor', data_dir))
            return SimpleNamespace(path=Path('synthetic Viewer log'), offset=100)

        def selected(mark):
            events.append(('fresh-key', ui.selected_key))
            if log_error:
                raise log_error
            return ui.selected_key

        stack = ExitStack()
        stack.enter_context(patch.object(vp.flows, 'cold_start', return_value=(ui, None)))
        stack.enter_context(patch.object(vp.flows, 'ensure_patient_screen', return_value=True))
        stack.enter_context(patch.object(vp, 'ensure_tc01_overlay', return_value={}))
        stack.enter_context(patch.object(vp.flows, 'open_main_menu', return_value=True))
        stack.enter_context(patch.object(vp.flows, 'wait_controls'))
        stack.enter_context(patch.object(vp.flows, 'step_items', side_effect=lambda _: list(range(steps)) if ui.selected_key==50 else []))
        stack.enter_context(patch.object(vp, 'children', side_effect=lambda hwnd, depth: cards if hwnd==2199 else [control(2,'TextButton')]))
        stack.enter_context(patch.object(usb_evidence, 'log_cursor', side_effect=cursor))
        stack.enter_context(patch.object(usb_evidence, 'selected_study_key', side_effect=selected))
        return stack, ctx, ui, events

    def test_exact_database_key_wins_over_oldest_card_position(self):
        for order in ((50,48), (48,50)):
            with self.subTest(order=order):
                stack, ctx, ui, events = self.simulate(order)
                with stack:
                    session = vp.open_test_study(ctx)
                self.assertEqual(session['study_key'], 50)
                self.assertEqual(session['study_selection']['study_key'], 50)
                self.assertEqual(session['study_selection']['log_offset'], 100)
                self.assertEqual(ctx.db.one.call_args.args[-1], {'pid':'synthetic patient'})
                self.assertEqual(ctx.db.query.call_args.args[-1], {'study':50})
                self.assertEqual([event for event in events if event[0]=='open'], [('open',50)])
                for index, event in enumerate(events):
                    if event[0] == 'card':
                        self.assertEqual(events[index-1][0], 'cursor')
                        self.assertEqual(events[index+1], ('fresh-key',event[1]))

    def test_no_exact_key_never_opens_a_different_study(self):
        stack, ctx, ui, events = self.simulate((49,48))
        with stack, self.assertRaises(RuntimeError):
            vp.open_test_study(ctx)
        self.assertFalse(any(event[0]=='open' for event in events))

    def test_missing_or_ambiguous_fresh_log_never_opens_view(self):
        for error in ('missing fresh event', 'ambiguous multiple events'):
            stack, ctx, ui, events = self.simulate(log_error=usb_evidence.ObservationError(error))
            with self.subTest(error=error), stack, self.assertRaises(usb_evidence.ObservationError):
                vp.open_test_study(ctx)
            self.assertFalse(any(event[0]=='open' for event in events))

    def test_original_two_or_three_step_requirement_is_preserved(self):
        for count in (0,1,2,3,4):
            stack, ctx, ui, events = self.simulate(steps=count)
            with self.subTest(count=count), stack:
                if count in (2,3):
                    self.assertEqual(vp.open_test_study(ctx)['initial_steps'], count)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'acquired steps'):
                        vp.open_test_study(ctx)

    def test_incomplete_database_fixture_is_rejected_before_any_ui_input(self):
        stack, ctx, ui, events = self.simulate(types=(0,1,2))
        with stack, self.assertRaisesRegex(RuntimeError, 'InstanceType 0/1/2/3'):
            vp.open_test_study(ctx)
        ui.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
