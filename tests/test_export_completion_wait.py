"""Export wait protocol with fake clocks, controls, processes, and files."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core import export_manager as em, screen, ui as ui_module


SUCCESS = 'Export was successful. The Export Manager closes.'


class ExportFixture:
    MAIN_WINDOW_MIN_AREA = 1_000_000

    def __init__(self, folder, popup_at=50, close_delay=23.3, text=SUCCESS):
        self.now = 0.
        self.folder = Path(folder)
        self.popup_at, self.close_delay, self.text = popup_at, close_delay, text
        self.started = False
        self.ack_at = None
        self.cancelled = False
        self.events = []
        self.manager = self.control(10, 0, (300, 100, 1500, 900))
        self.popup = self.control(20, 0, (600, 350, 1200, 600))
        self.ok = self.control(21, 500, (800, 520, 1000, 560))
        self.buttons = [self.ok]

    def control(self, hwnd, identifier, rect):
        return SimpleNamespace(hwnd=hwnd, ctrl_id=identifier, rect=rect, visible=True,
                               cls='#32770', text='TextButton')

    @property
    def alive(self):
        return not self.cancelled and not (self.ack_at is not None and self.now >= self.ack_at + self.close_delay)

    @property
    def pid(self):
        return 77 if self.alive else None

    def windows(self):
        if not self.alive:
            return []
        return [self.manager] + ([self.popup] if self.started and self.now >= self.popup_at and self.ack_at is None else [])

    def dialog(self):
        return self.popup if self.popup in self.windows() else None

    def dialog_buttons(self, window):
        return self.buttons if window.hwnd == self.popup.hwnd else []

    def dialog_text(self, window):
        return self.text

    def by_id(self, identifier, window=None):
        if not self.alive:
            return []
        if identifier == em.PATH_EDIT:
            return [self.control(30, identifier, (350, 700, 1000, 730))] if window in (None, self.manager) else []
        if identifier in (em.START, em.CANCEL):
            return [self.control(identifier, identifier, (1100, 700, 1250, 740))]
        return []

    def click(self, button, settle=0):
        self.events.append((self.now, button.ctrl_id))
        if button.ctrl_id == em.START:
            self.started = True
        elif button.hwnd == self.ok.hwnd:
            self.ack_at = self.now
        elif button.ctrl_id == em.CANCEL:
            self.cancelled = True
        self.now += settle

    def capture_dialog(self, window, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b'synthetic evidence')
        return path

    def snapshot(self, path):
        if not self.started or self.now < 1:
            return {}
        count = 3 if self.now >= self.popup_at else 1
        return {str(self.folder/f'image{index}.img'): (100, index) for index in range(count)}


class ExportCompletionWaitTests(unittest.TestCase):
    def setUp(self):
        em._PENDING_EXPORTS.clear()
        em._CONFIRMED_EXPORTS.clear()

    def fixture(self, case):
        factory = Mock(return_value=case)
        factory._alive.side_effect = lambda pid: case.alive
        return (patch.object(em, '_completion_evidence_path', return_value=str(case.folder/'completion.png')),
                patch.object(em, 'ViewerUi', factory),
                patch.object(em, 'read_path', return_value=str(case.folder)),
                patch.object(em, '_snapshot', side_effect=case.snapshot),
                patch.object(em.time, 'time', side_effect=lambda:case.now),
                patch.object(em.time, 'monotonic', side_effect=lambda:case.now),
                patch.object(em.time, 'sleep', side_effect=lambda seconds:setattr(case, 'now', case.now+seconds)),
                patch.object(ui_module, 'children', side_effect=lambda hwnd, depth:case.buttons if hwnd==20 else []))

    def run_export(self, case, wait=180):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patcher in self.fixture(case):
                stack.enter_context(patcher)
            return em.export(case, wait=wait, poll=.5, evidence_path=str(case.folder/'completion.png'))

    def test_first_file_never_shortens_wait_for_actual_completion_and_complete_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=50)
            result = self.run_export(case)
        self.assertTrue(result['done_confirmed'])
        self.assertTrue(result['closed'])
        self.assertEqual(len(result['files']), 3)
        self.assertTrue(all(at >= 50 for at, identifier in case.events if identifier == 500))
        self.assertFalse(any(identifier == em.CANCEL for _, identifier in case.events))

    def test_measured_twenty_three_second_exit_delay_gets_bounded_grace(self):
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=3, close_delay=23.3)
            result = self.run_export(case)
        self.assertTrue(result['closed'])
        self.assertFalse(any(identifier == em.CANCEL for _, identifier in case.events))

    def test_observed_single_ok_id_800_confirms_exact_success(self):
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=1)
            case.manager.rect = (417, 101, 1504, 980)
            case.popup.rect = (707, 440, 1213, 641)
            case.ok.ctrl_id = 800
            case.ok.rect = (900, 577, 1020, 621)
            result = self.run_export(case)
        self.assertTrue(result['done_confirmed'])
        self.assertTrue(result['closed'])
        self.assertEqual([identifier for _, identifier in case.events], [em.START, 800])

    def test_observed_ok_id_800_still_rejects_unknown_message(self):
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=1, text='Unknown Export message.')
            case.ok.ctrl_id = 800
            with self.assertRaises(em.ExportManagerError):
                self.run_export(case)
        self.assertEqual([identifier for _, identifier in case.events], [em.START])

    def test_unknown_popup_is_preserved_and_cannot_confirm_export(self):
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=1, text='Export failed. Unknown error.')
            with self.assertRaises(em.ExportManagerError):
                self.run_export(case, wait=5)
        self.assertEqual([identifier for _, identifier in case.events], [em.START])

    def test_partial_files_without_success_popup_fail_without_cancel_input(self):
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=1000)
            with self.assertRaises(em.ExportManagerError):
                self.run_export(case, wait=5)
        self.assertEqual([identifier for _, identifier in case.events], [em.START])
        self.assertLess(case.now, 10)

    def test_multiple_buttons_never_acknowledge_even_positive_text(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=0)
            case.started = True
            case.buttons.append(case.control(22, 2, (600, 520, 750, 560)))
            with ExitStack() as stack:
                for patcher in self.fixture(case):
                    stack.enter_context(patcher)
                self.assertFalse(em._confirm_done(case, timeout=1))
        self.assertEqual(case.events, [])

    def test_cancel_after_timeout_preserves_partial_export_and_unknown_popup(self):
        from contextlib import ExitStack
        for popup_at, text in ((1000, SUCCESS), (1, 'Unexpected export error.')):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as folder:
                case = ExportFixture(folder, popup_at=popup_at, text=text)
                with ExitStack() as stack:
                    for patcher in self.fixture(case):
                        stack.enter_context(patcher)
                    with self.assertRaises(em.ExportManagerError) as caught:
                        em.export(case, wait=2, poll=.5)
                    self.assertFalse(em.cancel(case, timeout=1))
                    self.assertEqual([identifier for _, identifier in case.events], [em.START])
                    self.assertTrue(caught.exception.completion['error'])
                    if popup_at == 1:
                        self.assertEqual(caught.exception.completion['raw_text'], text)
                        self.assertTrue(Path(caught.exception.completion['evidence']).is_file())
                        self.assertIn('증거=', str(caught.exception))

    def test_success_ocr_is_scoped_and_saved_before_ack(self):
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=1, text='')
            with patch.object(screen, 'ocr', return_value=SUCCESS) as ocr:
                result = self.run_export(case)
            self.assertEqual(result['completion']['source'], 'ocr')
            self.assertTrue(Path(result['completion']['evidence']).is_file())
            self.assertEqual(ocr.call_args.args[0], case.popup.rect)

    def test_ocr_exception_preserves_popup_and_captured_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=1, text='')
            with patch.object(screen, 'ocr', side_effect=RuntimeError('synthetic OCR failure')):
                with self.assertRaises(em.ExportManagerError) as caught:
                    self.run_export(case)
            completion = caught.exception.completion
            self.assertIn('synthetic OCR failure', completion['error'])
            self.assertTrue(Path(completion['evidence']).is_file())
            self.assertEqual([identifier for _, identifier in case.events], [em.START])

    def test_acknowledged_export_cannot_be_cancelled_during_exit_grace(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as folder:
            case = ExportFixture(folder, popup_at=1, close_delay=1000)
            with ExitStack() as stack:
                for patcher in self.fixture(case):
                    stack.enter_context(patcher)
                with self.assertRaises(em.ExportManagerError):
                    em.export(case, wait=5, close_wait=1)
                self.assertFalse(em.cancel(case, timeout=1))
            self.assertEqual([identifier for _, identifier in case.events], [em.START, 500])

    def test_success_parser_rejects_actions_unknown_errors_and_partial_phrases(self):
        parser = getattr(em, 'parse_export_completion', None)
        self.assertTrue(callable(parser), 'actual export completion parser is required')
        self.assertTrue(parser(SUCCESS)['observed'])
        for text in ('', 'Done', 'Export started', 'click OK', SUCCESS+' Error',
                     'Export was successful.', 'Error: '+SUCCESS):
            with self.subTest(text=text):
                self.assertFalse(parser(text)['observed'])


if __name__ == '__main__':
    unittest.main()
