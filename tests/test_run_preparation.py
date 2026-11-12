"""Validates: REQ-TCUP-004. USB와 사람 확인의 독립적인 차단."""
import pytest
from unittest.mock import patch


def test_wu_requires_all_checks_and_real_usb_even_when_prepared():
    from core import run_preparation as prep
    keys = [r['key'] for r in prep.preparation_items('run-winupdate')]
    assert {'desktop_free','backup','usb_ready','usb_folder'} == set(keys)
    assert not prep.preparation_complete('run-winupdate', keys[:-1])
    assert prep.preparation_complete('run-winupdate', keys)
    with patch('core.usb_media.find_usb_drive', return_value=None):
        with pytest.raises(ValueError, match='USB'):
            prep.confirm_cli('run-winupdate', prepared=True)


def test_cli_rejection_and_noninteractive_eof_do_not_start():
    from core import run_preparation as prep
    with patch('core.usb_media.find_usb_drive', return_value='D:\\'):
        assert not prep.confirm_cli('run-wu09', input_fn=lambda prompt:'n')
        def eof(_): raise EOFError
        assert not prep.confirm_cli('run-wu09', input_fn=eof)
        assert prep.confirm_cli('run-wu09', input_fn=lambda prompt:'y')


def test_basic_does_not_require_usb_and_checks_do_not_accept_count_only():
    from core import run_preparation as prep
    assert {r['key'] for r in prep.preparation_items('run-regression')} == {'desktop_free','backup'}
    assert prep.preparation_complete('run-regression', ['desktop_free','backup'])
    assert not prep.preparation_complete('run-winupdate', ['desktop_free','backup','x','x'])
    assert prep.validate_preparation('run-regression', ['desktop_free','backup']) is None


def test_cancelled_cli_never_reaches_display_or_service_gate():
    import run
    from unittest.mock import Mock
    from core.result import TCResult
    ctx = Mock(cfg={})
    with patch('sys.argv', ['run.py','run-wu09']), patch.object(run, 'Context', return_value=ctx), \
         patch.object(run, '_source_identity_meta', return_value={}), \
         patch('core.run_preparation.confirm_cli', return_value=False), \
         patch('core.display.normalize', side_effect=AssertionError('UI gate must not run')), \
         patch.object(TCResult, 'stop_on_fail', False):
        assert run.main() == 2


def test_gui_controller_rejects_missing_checks_before_creating_run(tmp_path):
    from bellalunauto.gui import RunController
    from bellalunauto.runtime import Layout
    controller = RunController(Layout(tmp_path,tmp_path,tmp_path/'config.json'), {})
    with pytest.raises(ValueError, match='체크리스트'):
        controller.start('run-winupdate',consent=True,plan={})
    assert controller.record is None


def test_wu09_single_passes_workflow_list_to_real_wu_mapping():
    import run
    from core.result import TCResult
    wf = TCResult('TC_Basic_WorkFlow_09', 'Export')
    wf.add(1, 'Normal Export', 'PASS')
    # USB 없음은 기존 판정 정책에 따라 MANUAL, WF09 PASS는 그대로 복사되어야 한다.
    with patch('tests.workflow09.run', return_value=[wf]), \
         patch('core.flows.cold_start', return_value=(object(), {})), \
         patch('tests.winupdate.run_usb_export_import', return_value={'drive':None}), \
         patch.object(run, '_finish_winupdate', side_effect=lambda ctx,rows,**kw: rows):
        from types import SimpleNamespace
        rows = run._run_wu09_single(SimpleNamespace(cfg={}, db=None))
    assert len(rows) == 1
    assert rows[0].tc_id == 'TC_WindowsUpdate_09'
    assert any(c.title.endswith('Normal Export') and c.status == 'PASS' for c in rows[0].checks)
    assert rows[0].verdict == 'MANUAL'
