"""REQ-DIST-001: 묶음 자료 기본값과 명시한 승인 자료 경로를 구별한다."""

from pathlib import Path
import tempfile
import unittest

from bellalunauto.resources import bundled_config


class BundledResourceTests(unittest.TestCase):
    def test_operator_paths_under_qa_are_preserved(self):
        configured = {
            'checklist_xlsx': r'C:\QA\my-approved-checklist.xlsx',
            'winupdate_checklist_xlsx': r'C:\QA\my-approved-winupdate.xlsx',
            'baseline_dir': r'C:\QA\my-approved-baseline',
            'knowledge_dir': r'C:\QA\my-approved-manuals',
        }
        with tempfile.TemporaryDirectory() as folder:
            resources = Path(folder)
            (resources/'assets').mkdir()
            self.assertEqual(bundled_config(configured, resources), configured)

    def test_exact_example_path_and_missing_paths_use_bundled_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            resources = Path(folder)
            (resources/'assets').mkdir()
            configured = {'checklist_xlsx': r'C:\QA\Bellalun_Viewer_Checklist.xlsx'}
            result = bundled_config(configured, resources)
            self.assertEqual(Path(result['checklist_xlsx']).parent,
                             resources/'assets/checklists')
            self.assertEqual(Path(result['baseline_dir']), resources/'assets/Baseline')
            self.assertEqual(Path(result['knowledge_dir']), resources/'assets/지식')
            self.assertEqual(configured,
                             {'checklist_xlsx': r'C:\QA\Bellalun_Viewer_Checklist.xlsx'})


if __name__ == '__main__':
    unittest.main()
