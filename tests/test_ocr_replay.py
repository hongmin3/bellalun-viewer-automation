import json
from unittest import mock

from PIL import Image

from tools import ocr_replay


def manifest(tmp_path):
    Image.new('RGB', (100, 30), 'white').save(tmp_path / 'row.png')
    path = tmp_path / 'corpus.json'
    path.write_text(json.dumps({'cases': [{'name': 'HVL', 'wanted': 'HVL',
        'images': ['row.png'], 'expected': 0}]}), encoding='utf-8')
    return path


def test_replay_uses_same_selection_rules(tmp_path):
    path = manifest(tmp_path)
    with mock.patch('core.ocr_selection.read_image', return_value={
            'text':'HVL', 'confidence':90, 'error':None}):
        result = ocr_replay.replay(path)
    assert result['passed'] == 1
    assert result['failed'] == 0


def test_replay_rejects_wrong_result(tmp_path):
    path = manifest(tmp_path)
    with mock.patch('core.ocr_selection.read_image', return_value={
            'text':'HVI', 'confidence':90, 'error':None}):
        result = ocr_replay.replay(path)
    assert result['failed'] == 1


def test_replay_cli_exit_code_reflects_result(tmp_path):
    path = manifest(tmp_path)
    with mock.patch('core.ocr_selection.read_image', return_value={
            'text':'', 'confidence':0, 'error':None}):
        assert ocr_replay.main([str(path), '--output', str(tmp_path/'result.json')]) == 1
    assert json.loads((tmp_path/'result.json').read_text())['failed'] == 1
