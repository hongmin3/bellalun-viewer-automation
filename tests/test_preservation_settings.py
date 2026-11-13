"""REQ-FOLLOWUP-004: PC별 보존 경로와 기본 진단 범위. 실제 설정/공유는 쓰지 않는다."""
import copy

import pytest

from bellalunauto import app, gui


def test_storage_directory_merge_preserves_nested_settings_and_original():
    original = {
        'preservation': {'storage_dir': '', 'future_policy': {'keep': [1, 2]}},
        'viewer': {'login': {'id': 'synthetic', 'password': ' synthetic-secret '}},
        'data_dir': 'C:/synthetic-data', 'unknown': {'keep': True},
    }
    before = copy.deepcopy(original)
    updated = gui.merge_form_config(original, {
        'preservation.storage_dir': r'  \\synthetic-host\synthetic-share\archive  ',
    })
    assert updated['preservation'] == {
        'storage_dir': r'\\synthetic-host\synthetic-share\archive',
        'future_policy': {'keep': [1, 2]},
    }
    assert updated['viewer'] == before['viewer']
    assert updated['data_dir'] == before['data_dir']
    assert updated['unknown'] == before['unknown']
    assert original == before


@pytest.mark.parametrize('storage_dir', ['', r'\\synthetic-host\offline-share', 'Z:/synthetic-archive'])
def test_storage_directory_is_optional_and_does_not_probe_network(storage_dir, monkeypatch):
    original_exists = gui.Path.exists
    def forbidden_probe(path, *args, **kwargs):
        if str(path) == str(gui.Path(storage_dir)):
            pytest.fail('폼 검증에서 실제 파일/공유에 접근하면 안 됩니다.')
        return original_exists(path, *args, **kwargs)
    monkeypatch.setattr(gui.Path, 'exists', forbidden_probe)
    updated = gui.merge_form_config({}, {'preservation.storage_dir': storage_dir})
    assert updated['preservation']['storage_dir'] == storage_dir
    assert not any('보존 저장소' in error for error in gui.validate_config(updated))


@pytest.mark.parametrize('storage_dir', [None, 12, {}, [], 'relative/archive', 'C:/bad\x00path', r'\\host-only'])
def test_storage_directory_rejects_invalid_type_or_path_without_echoing_value(storage_dir):
    with pytest.raises(ValueError, match='보존 저장소') as error:
        gui.merge_form_config({}, {'preservation.storage_dir': storage_dir})
    assert 'bad' not in str(error.value)


def test_storage_directory_rejects_malformed_parent_without_destroying_it():
    original = {'preservation': ['keep-unrecognised-data']}
    with pytest.raises(ValueError, match='보존'):
        gui.merge_form_config(original, {'preservation.storage_dir': ''})
    assert original == {'preservation': ['keep-unrecognised-data']}


def test_basic_diagnostic_success_does_not_claim_run_budget_passed(monkeypatch, capsys):
    monkeypatch.setattr(app, 'diagnostics', lambda layout: [
        {'name': '합성 기본 연결', 'ok': True, 'detail': '확인', 'fix': ''},
    ])
    assert app._print_diagnostics(None) == 0
    text = capsys.readouterr().out
    assert '기본 설치·연결 점검을 통과' in text
    assert '보존' in text and '용량' in text and '별도' in text
    assert '시험을 시작할 수 있습니다' not in text
