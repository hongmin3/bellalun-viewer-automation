"""Observed USB completion protocol, with no real UI/OCR/process operations."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import screen, usb_media as media
from core.flows import FlowError


POSITIVE = 'Import completed. (Imported: 1 / Skipped: 0)'


def control(hwnd, identifier, rect, cls='#32770'):
    return SimpleNamespace(hwnd=hwnd, ctrl_id=identifier, rect=rect, cls=cls, visible=True)


class FakeImportUi:
    MAIN_WINDOW_MIN_AREA = 1_000_000

    def __init__(self, text=POSITIVE):
        self.container = control(100, 0, (592, 267, 1328, 813))
        self.popup = control(200, 0, (731, 440, 1190, 641))
        self.ok = control(201, 500, (1040, 580, 1150, 620), 'Button')
        self.import_button = control(101, 2064, (1100, 710, 1200, 750), 'Button')
        self.close_button = control(102, 1102, (1210, 710, 1310, 750), 'Button')
        self.text = text
        self.popup_visible = True
        self.buttons = [self.ok]
        self.remove_on_ack = True
        self.events = []
        self.after_capture = None

    def windows(self):
        return [self.container] + ([self.popup] if self.popup_visible else [])

    def dialog_buttons(self, window):
        return self.buttons if window.hwnd == self.popup.hwnd else []

    def dialog_text(self, window):
        if window.hwnd != self.popup.hwnd:
            raise AssertionError('text read from wrong dialog')
        return self.text

    def by_id(self, identifier, window=None):
        if identifier == media.DIALOG_IMPORT_BUTTON:
            if window is not self.container:
                raise AssertionError('Import lookup was not scoped')
            return [self.import_button]
        if identifier == media.DIALOG_CLOSE_BUTTON and window is self.container:
            return [self.close_button]
        return [item for item in self.dialog_buttons(window) if item.ctrl_id == identifier]

    def capture_dialog(self, window, path):
        self.events.append(('capture', window.hwnd))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b'synthetic screenshot evidence')
        if self.after_capture:
            self.after_capture()
        return str(path)

    def click(self, button, settle=0):
        self.events.append(('input', button.hwnd))
        if button.hwnd == self.ok.hwnd and self.remove_on_ack:
            self.popup_visible = False


class CompletionParserTests(unittest.TestCase):
    def parse(self, text, expected=1):
        parser = getattr(media, 'parse_import_completion', None)
        self.assertTrue(callable(parser), 'observed completion parser is required')
        return parser(text, expected=expected)

    def test_exact_positive_counts_are_required(self):
        result = self.parse(POSITIVE)
        self.assertTrue(result['observed'])
        self.assertEqual((result['imported'], result['skipped']), (1, 0))
        self.assertNotIn('click', result['signal'].casefold())

    def test_ocr_line_breaks_and_single_ok_label_preserve_same_message(self):
        self.assertTrue(self.parse('Import completed.\n(Imported: 1 / Skipped: 0)\nOK')['observed'])

    def test_empty_actions_zero_skipped_unknown_and_errors_are_rejected(self):
        for text in ('', None, 'clicked Import', 'Import failed.', 'Unknown',
                     'Import completed. (Imported: 0 / Skipped: 1)',
                     'Import completed. (Imported: 1 / Skipped: 1)',
                     'Import completed. (Imported: 2 / Skipped: 0)',
                     'Error: ' + POSITIVE, POSITIVE + ' Error',
                     'Please click Import. ' + POSITIVE):
            with self.subTest(text=text):
                self.assertFalse(self.parse(text)['observed'])

    def test_nonpositive_or_boolean_expected_count_is_rejected(self):
        for expected in (0, -1, True, '1'):
            with self.subTest(expected=expected):
                self.assertFalse(self.parse(POSITIVE, expected)['observed'])


class CompletionObserverTests(unittest.TestCase):
    def observe(self, ui, **kwargs):
        observer = getattr(media, 'wait_import_completion', None)
        self.assertTrue(callable(observer), 'actual completion observer is required')
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(media, 'import_window', return_value=ui.container), \
             patch.object(media, 'duplicate_patient_popup', return_value=None):
            kwargs.setdefault('evidence_path', str(Path(folder)/'completion.png'))
            return observer(ui, timeout=0, **kwargs)

    def test_native_success_is_captured_before_scoped_ack_and_waited_until_gone(self):
        ui = FakeImportUi()
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(screen, 'ocr', side_effect=AssertionError('unnecessary OCR')):
            path = Path(folder)/'completion.png'
            result = self.observe(ui, evidence_path=str(path))
            self.assertEqual(Path(result['evidence']), path)
            self.assertTrue(path.is_file())
        self.assertTrue(result['observed'])
        self.assertTrue(result['dismissed'])
        self.assertIsNone(result['error'])
        self.assertEqual(ui.events, [('capture', 200), ('input', 201)])
        self.assertFalse(ui.popup_visible)

    def test_ownerdraw_popup_uses_only_popup_rectangle_for_ocr(self):
        ui = FakeImportUi(text='')
        with patch.object(screen, 'ocr', return_value=POSITIVE + '\nOK') as ocr:
            result = self.observe(ui)
        self.assertTrue(result['observed'])
        self.assertEqual(result['source'], 'ocr')
        self.assertEqual(ocr.call_args.args[0], ui.popup.rect)
        self.assertEqual(result['raw_text'], POSITIVE + '\nOK')

    def test_unknown_negative_or_empty_popup_is_preserved_without_input(self):
        for text in ('Unknown message', '', 'Import completed. (Imported: 0 / Skipped: 1)', 'Import failed.'):
            ui = FakeImportUi(text=text)
            with self.subTest(text=text), patch.object(screen, 'ocr', return_value=''):
                result = self.observe(ui)
                self.assertFalse(result['observed'])
                self.assertTrue(result['error'])
                self.assertTrue(ui.popup_visible)
                self.assertEqual(ui.events, [])

    def test_popup_outside_import_window_or_with_extra_buttons_is_ignored(self):
        for variant in ('outside', 'extra button', 'wrong button'):
            ui = FakeImportUi()
            if variant == 'outside':
                ui.popup.rect = (0, 0, 400, 200)
            elif variant == 'extra button':
                ui.buttons.append(control(202, 1, (900, 580, 1000, 620), 'Button'))
            else:
                ui.ok.ctrl_id = 1
            with self.subTest(variant=variant), patch.object(screen, 'ocr', side_effect=AssertionError('wrong OCR')):
                result = self.observe(ui)
                self.assertFalse(result['observed'])
                self.assertEqual(ui.events, [])

    def test_positive_popup_remaining_after_ack_is_error(self):
        ui = FakeImportUi()
        ui.remove_on_ack = False
        result = self.observe(ui)
        self.assertTrue(result['observed'])
        self.assertFalse(result['dismissed'])
        self.assertTrue(result['error'])

    def test_changed_popup_controls_after_capture_are_not_acknowledged(self):
        ui = FakeImportUi()
        ui.after_capture = lambda: ui.buttons.append(control(202, 1, (900, 580, 1000, 620), 'Button'))
        with tempfile.TemporaryDirectory() as folder:
            result = self.observe(ui, evidence_path=str(Path(folder)/'completion.png'))
        self.assertTrue(result['error'])
        self.assertEqual(ui.events, [('capture', 200)])

    def test_late_duplicate_is_handled_during_bounded_completion_wait(self):
        ui = FakeImportUi()
        clock = [0.]
        resolved = [False]
        duplicate = control(300, 0, (731, 440, 1190, 641))
        ui.windows = lambda: ([ui.container] + ([ui.popup] if ui.popup_visible else []) if resolved[0] else
                              [ui.container, duplicate] if clock[0] >= 3 else [ui.container])

        def resolve(*args, **kwargs):
            self.assertGreaterEqual(clock[0], 3)
            resolved[0] = True
            return True

        with tempfile.TemporaryDirectory() as folder, \
             patch.object(media, 'import_window', return_value=ui.container), \
             patch.object(media, 'duplicate_patient_popup', side_effect=lambda _: duplicate if clock[0] >= 3 and not resolved[0] else None), \
             patch.object(media, 'resolve_duplicate_patient', side_effect=resolve) as resolver, \
             patch.object(media.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(media.time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0]+seconds)):
            result = media.wait_import_completion(ui, timeout=10,
                                                 evidence_path=str(Path(folder)/'completion.png'))
        self.assertTrue(result['observed'])
        self.assertTrue(result['dismissed'])
        self.assertTrue(result['duplicate_popup'])
        self.assertIsNone(result['error'])
        resolver.assert_called_once()

    def test_duplicate_popup_that_remains_after_selection_raises(self):
        ui = FakeImportUi()
        with patch.object(media, 'duplicate_patient_popup', return_value=ui.popup):
            ui.buttons = [control(210, 1101, (900, 580, 1000, 620), 'Button')]
            with self.assertRaisesRegex(FlowError, '중복.*닫히지'):
                media.resolve_duplicate_patient(ui, timeout=0)

    def test_duplicate_with_an_unexpected_modal_is_preserved(self):
        ui = FakeImportUi()
        duplicate = control(300, 0, (731, 440, 1190, 641))
        ui.windows = lambda: [ui.container, ui.popup, duplicate]
        with patch.object(media, 'import_window', return_value=ui.container), \
             patch.object(media, 'duplicate_patient_popup', return_value=duplicate), \
             patch.object(media, 'resolve_duplicate_patient') as resolver:
            result = media.wait_import_completion(ui, timeout=0)
        self.assertFalse(result['observed'])
        self.assertTrue(result['error'])
        resolver.assert_not_called()
        self.assertEqual(ui.events, [])


class AttemptImportCompletionTests(unittest.TestCase):
    def attempt(self, completion):
        ui = FakeImportUi()
        with patch.object(media, 'open_import_dialog'), \
             patch.object(media, 'import_window', return_value=ui.container), \
             patch.object(media, 'select_import_folder', return_value='synthetic folder'), \
             patch.object(media, 'wait_for_rows', return_value=1), \
             patch.object(media, 'select_row'), \
             patch.object(media, 'resolve_duplicate_patient', return_value=True), \
             patch.object(media, 'wait_import_completion', return_value=completion, create=True) as observe, \
             patch.object(media, 'cancel_browse_dialog'), \
             patch.object(media, 'close_import_dialog', return_value=True) as close:
            outcome = media.attempt_import(ui, 'synthetic folder', evidence_path='synthetic-evidence.png')
        return outcome, observe, close

    def test_attempt_waits_for_observed_counts_and_closes_only_after_popup_handled(self):
        completion = {'observed':True, 'signal':'import-completed-counts', 'dismissed':True, 'error':None}
        result, observe, close = self.attempt(completion)
        self.assertEqual(result['completion'], completion)
        self.assertTrue(result['closed'])
        self.assertEqual(observe.call_args.kwargs['expected'], 1)
        self.assertEqual(observe.call_args.kwargs['evidence_path'], 'synthetic-evidence.png')
        close.assert_called_once()

    def test_attempt_preserves_unknown_completion_and_underlying_import_window(self):
        completion = {'observed':False, 'signal':'', 'dismissed':False, 'error':'Unknown completion popup'}
        result, _, close = self.attempt(completion)
        self.assertFalse(result['closed'])
        self.assertIn('Unknown completion popup', result['error'])
        close.assert_not_called()

    def test_direct_close_preserves_unknown_modal_instead_of_clicking_behind_it(self):
        ui = FakeImportUi(text='Unknown')
        with patch.object(media, 'import_window', return_value=ui.container):
            self.assertFalse(media.close_import_dialog(ui, timeout=0))
        self.assertEqual(ui.events, [])


if __name__ == '__main__':
    unittest.main()
