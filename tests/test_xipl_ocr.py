"""Unicode-safe OCR transport only; no real OCR, product, UI, or DB calls."""
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from core.xipl import XiplStudio


class XiplOcrTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='XIPL 한글 ')
        self.addCleanup(self.folder.cleanup)
        self.image = Path(self.folder.name)/'저장 영상.png'
        Image.new('RGB', (200, 200), 'white').save(self.image)
        self.studio = object.__new__(XiplStudio)
        self.studio.tesseract = str(Path(self.folder.name)/'설정 OCR.exe')
        Path(self.studio.tesseract).touch()

    def response(self, output=b'actual text', code=0, error=b''):
        return SimpleNamespace(stdout=output, returncode=code, stderr=error)

    def assert_stdin_png(self, call):
        args, options = call.args[0], call.kwargs
        self.assertEqual(args[:5], [self.studio.tesseract, 'stdin', 'stdout', '-l', 'eng'])
        self.assertTrue(options['input'].startswith(b'\x89PNG\r\n\x1a\n'))
        with Image.open(BytesIO(options['input'])) as image:
            self.assertGreater(image.width, 0)
        self.assertEqual(options['timeout'], 30)
        self.assertTrue(options['capture_output'])
        self.assertNotIn(str(self.image), args)

    def test_unicode_image_path_is_decoded_by_pillow_and_sent_as_png_stdin(self):
        with patch('core.xipl.subprocess.run', return_value=self.response()) as run:
            self.assertEqual(self.studio.ocr(self.image), 'actual text')
        self.assert_stdin_png(run.call_args)
        self.assertEqual(run.call_args.args[0][5:], [])

    def test_region_and_tsv_keep_original_options_and_use_same_transport(self):
        tsv = b'header\n5\t1\t1\t1\t1\t1\t10\t20\t30\t40\t95\tTarget\n'
        with patch('core.xipl.subprocess.run', side_effect=[self.response(), self.response(tsv)]) as run:
            self.assertEqual(self.studio.ocr_region(self.image, (0, 0, 20, 20)), 'actual text')
            self.assertEqual(self.studio.find_text(self.image, 'Target'), [(10, 20, 30, 40, 95.)])
        for call in run.call_args_list:
            self.assert_stdin_png(call)
        self.assertEqual(run.call_args_list[0].args[0][5:], ['--psm', '6'])
        self.assertEqual(run.call_args_list[1].args[0][5:], ['tsv'])

    def test_overlay_criteria_psm_and_whitelist_are_unchanged(self):
        with patch('core.xipl.subprocess.run', side_effect=[
                self.response(b'2304 x 3072 / UInt16'), self.response(b'1: 20060 W2: 65628')]) as run:
            values = self.studio.read_overlay_values(self.image)
        self.assertEqual({key:values[key] for key in ('width','height','w1','w2')},
                         {'width':2304,'height':3072,'w1':20060,'w2':65628})
        for call in run.call_args_list:
            self.assert_stdin_png(call)
        self.assertEqual(run.call_args_list[0].args[0][5:], ['--psm', '6'])
        self.assertEqual(run.call_args_list[1].args[0][5:],
                         ['--psm','6','-c','tessedit_char_whitelist=Ww0123456789: '])

    def test_nonzero_exit_cannot_hide_stderr_as_empty_ocr(self):
        with patch('core.xipl.subprocess.run', return_value=self.response(b'', 1, b'cannot read input: Invalid argument')):
            with self.assertRaisesRegex(RuntimeError, 'Invalid argument'):
                self.studio.ocr(self.image)

    def test_timeout_is_explicit_and_keeps_stderr(self):
        failure = subprocess.TimeoutExpired(['synthetic OCR'], 30, stderr=b'synthetic stall')
        with patch('core.xipl.subprocess.run', side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, 'synthetic stall'):
                self.studio.ocr(self.image)


if __name__ == '__main__':
    unittest.main()
