"""Validates: REQ-FOLLOWUP-002. 합성 DOCX에서 명시한 판만 추출한다."""
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from core import release_note_baseline as baseline


def make_docx(path):
    xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
    <w:p><w:r><w:t>1.0.1.101</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Module</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Version (Product Version)</w:t></w:r></w:p></w:tc></w:tr>
    <w:tr><w:tc><w:p><w:r><w:t>Viewer.exe</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1.0.1.101</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    <w:p><w:r><w:t>1.0.1.105</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Module</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Version (Product Version)</w:t></w:r></w:p></w:tc></w:tr>
    <w:tr><w:tc><w:p><w:r><w:t>Viewer.exe</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1.0.1.</w:t></w:r><w:r><w:t>105</w:t></w:r></w:p></w:tc></w:tr>
    <w:tr><w:tc><w:p><w:r><w:t>Child.exe</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>2.0.0.1</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    </w:body></w:document>'''
    with ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', xml)


def test_extract_explicit_release_preserves_unknown_db_and_resolves_unique_paths(tmp_path):
    docx = tmp_path / 'approved.docx'
    make_docx(docx)
    installed = tmp_path / 'installed'
    (installed / 'Child').mkdir(parents=True)
    (installed / 'VIEWER.exe').write_bytes(b'not-a-real-exe')
    (installed / 'Child/Child.exe').write_bytes(b'not-a-real-exe')
    result = baseline.extract_baseline(docx, '1.0.1.105', install_dir=installed, approved=True)
    note = result['release_note']
    assert note['programs'] == {'Bellalun': '1.0.1.105'}
    assert note['files'] == {'VIEWER.exe': '1.0.1.105', 'Child/Child.exe': '2.0.0.1'}
    assert note['db_software_version'] is None
    assert note['_file_version_kind'] == 'product'
    assert note['_approval']['status'] == 'approved_source'
    assert 'db_software_version' in result['missing_baselines']
    assert str(tmp_path) not in json.dumps(result)
    with pytest.raises(baseline.BaselineError, match='버전'):
        baseline.extract_baseline(docx, '9.9.9.9')


def test_ambiguous_file_paths_never_choose_first_candidate(tmp_path):
    docx = tmp_path / 'approved.docx'
    make_docx(docx)
    for folder in ('one', 'two'):
        target = tmp_path / folder
        target.mkdir()
        (target / 'Child.exe').write_bytes(b'fixture')
    result = baseline.extract_baseline(docx, '1.0.1.105', install_dir=tmp_path)
    assert 'Child.exe' not in result['release_note']['files']
    assert result['unresolved_files']['Child.exe']['status'] == 'ambiguous'
    assert result['release_note']['_approval']['status'] == 'pending'


def test_cli_writes_new_runtime_output_but_never_overwrites_config(tmp_path, capsys):
    from tools import collect_release_baseline as cli
    docx = tmp_path / 'approved.docx'
    make_docx(docx)
    installed = tmp_path / 'installed'
    installed.mkdir()
    (installed / 'Viewer.exe').write_bytes(b'fixture')
    args = [str(docx), '--release-version', '1.0.1.105', '--install-dir', str(installed)]
    output = tmp_path / 'baseline.json'
    assert cli.main(args + ['--output', str(output), '--approved-source']) == 0
    assert json.loads(output.read_text())['release_note']['_selected_release'] == '1.0.1.105'
    before = output.read_bytes()
    assert cli.main(args + ['--output', str(output)]) == 1
    assert output.read_bytes() == before
    assert cli.main(args + ['--output', str(tmp_path / 'config.json')]) == 1
    assert not (tmp_path / 'config.json').exists()
    capsys.readouterr()
