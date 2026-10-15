"""REQ-DIST-001/003: 설정 위치와 실행/읽기 전용 자료를 분리한다."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import specs
import run


class DistributionEngineTests(unittest.TestCase):
    def test_context_uses_workspace_and_bundled_assets_independent_of_config(self):
        with tempfile.TemporaryDirectory(prefix='한글 배포 ') as tmp:
            root = Path(tmp)
            config_dir = root/'config elsewhere'
            workspace = root/'workspace'
            resources = root/'installed/resources'
            data = root/'data'
            for folder in (config_dir, workspace, resources/'assets/Baseline', data):
                folder.mkdir(parents=True)
            config = config_dir/'qa.json'
            config.write_text(json.dumps({'data_dir':str(data)}), encoding='utf-8')
            with patch.dict(os.environ, {'BELLALUN_WORKSPACE':str(workspace),
                                         'BELLALUN_RESOURCE_DIR':str(resources)}):
                ctx = run.Context(str(config))
            self.assertEqual(Path(ctx.root), workspace)
            self.assertEqual(Path(ctx.resource_root), resources)
            self.assertEqual(Path(ctx.evidence_root), workspace/'Evidence')
            self.assertEqual(Path(ctx.cfg['baseline_dir']), resources/'assets/Baseline')

    def test_knowledge_uses_configured_readonly_document_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge = root/'installed/resources/assets/지식'
            knowledge.mkdir(parents=True)
            ctx = SimpleNamespace(root=str(root/'workspace'), cfg={'knowledge_dir':str(knowledge)})
            self.assertEqual(Path(specs.knowledge_dir(ctx)), knowledge)

    def test_replay_command_preserves_workspace_and_spaces(self):
        expected = '"E:\\한글 설치\\BellalunAuto.exe" --workspace "D:\\시험 작업" run-regression'
        with patch.dict(os.environ, {'BELLALUN_LAUNCH_COMMAND':expected}):
            self.assertEqual(run._command_line(), expected)

    def test_pdf_cache_is_written_to_workspace_not_installed_assets(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = root/'installed/resources/assets/지식'
            installed.mkdir(parents=True)
            pdf = installed/'사양서1.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.write(pdf)
            cache = root/'workspace/Cache/Specs'
            pages = specs.extract(str(pdf), cache_dir=str(cache))
            self.assertEqual(len(pages), 1)
            self.assertTrue(list(cache.glob('*.txt')))
            self.assertEqual(list(installed.glob('*.txt')), [])

    def test_wu_report_marks_historical_and_aborted_live_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = SimpleNamespace(reports_root=tmp)
            for mode in ('historical', 'live'):
                with self.subTest(mode=mode), \
                     patch.object(run, '_winupdate_source_path', return_value=''), \
                     patch.object(run, '_winupdate_env', return_value={}), \
                     patch.object(run, 'write_reports', return_value={}) as write, \
                     patch.object(run, 'announce_done'):
                    run._finish_winupdate(ctx, [], execution_mode=mode, chain_completed=False)
                    meta = write.call_args.kwargs['meta']
                    self.assertEqual(meta['execution_mode'], mode)
                    self.assertIs(meta['chain_completed'], False)


if __name__ == '__main__':
    unittest.main()
