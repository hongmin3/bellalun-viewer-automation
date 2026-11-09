import json
from datetime import datetime
from types import SimpleNamespace
from unittest import mock
import pytest
from tests import xipl_flows as xf


def test_qc_timeout_preserves_phase_without_treating_log_as_pass(tmp_path):
    ctx = SimpleNamespace(evidence_root=str(tmp_path))
    ui = mock.Mock()
    ui.by_id.return_value = [SimpleNamespace(visible=True)]
    win = SimpleNamespace(rect=(0, 0, 100, 100))
    ticks = iter(range(100))
    with mock.patch.object(xf, '_qc_window', return_value=win), \
         mock.patch.object(xf, '_viewer_log_since', return_value='unrelated buffered line'), \
         mock.patch.object(xf.time, 'time', side_effect=lambda: next(ticks)), \
         mock.patch.object(xf.time, 'sleep'), \
         mock.patch.object(xf.vp, 'capture_viewer_window'):
        with pytest.raises(xf.flows.FlowError, match='F8'):
            xf._qc_launch_and_expose(ctx, ui, (1, 1), 'synthetic', object(),
                                     datetime(2026, 1, 1), lambda text: False)
    path = tmp_path / 'Viewer_XIPL' / 'TC_XIPL_compatibility_05_synthetic_wait.json'
    detail = json.loads(path.read_text(encoding='utf-8'))
    assert detail['phase'] == 'waiting-parameter-log'
    assert detail['f8_sent'] is True
    assert detail['filtered_lines'] == 0
    assert detail['log_bytes'] > 0
    assert 'unrelated buffered line' not in path.read_text(encoding='utf-8')
