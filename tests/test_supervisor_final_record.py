from pathlib import Path
from types import SimpleNamespace
import json

from bellalunauto import app
from bellalunauto.runs import RunRecord


def test_supervisor_finishes_gui_record_without_gui_poll(tmp_path, monkeypatch):
    record = RunRecord.create(tmp_path, 'run-winupdate', {}, consent=True)
    monkeypatch.setenv('BELLALUN_QA_RUN', record.data['run_id'])
    folder = tmp_path / 'Reports'
    folder.mkdir()
    report = {'meta': {'execution_mode': 'live', 'chain_completed': True},
              'results': [{'tc_id': f'TC_WindowsUpdate_{i:02}', 'verdict': 'PASS'} for i in range(1, 14)]}
    (folder / 'Result_WindowsUpdate_current.json').write_text(json.dumps(report), encoding='utf-8')
    monkeypatch.setattr(app, '_run_guarded_impl', lambda *a: 0, raising=False)
    assert app.run_guarded(SimpleNamespace(workspace=tmp_path), ['run-winupdate']) == 0
    assert json.loads(record.path.read_text(encoding='utf-8'))['status'] == 'completed'
