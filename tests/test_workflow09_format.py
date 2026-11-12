"""WF09 must replace persisted WU09 IMG settings before DICOM validation."""
from types import SimpleNamespace

import pytest

from core import export_manager as em, screen
from core.result import TCResult
from tests import workflow09


@pytest.fixture
def export_session(tmp_path, monkeypatch):
    # run648 produced three IMG/TXT pairs and zero parsed DICOM objects.
    # Keep the real format/toggle/path helpers; replace only desktop boundaries.
    states = {key: key == em.FORMAT_IMG for key in em.ALL_FORMATS}
    states[em.ANONYMOUS] = False
    blocked = set()
    observations = []
    controls = {key: SimpleNamespace(ctrl_id=key, visible=True, cls="TextButton")
                for key in states}
    controls[em.PATH_EDIT] = SimpleNamespace(ctrl_id=em.PATH_EDIT, visible=True,
                                           cls="Edit", value="")

    class Manager:
        def by_id(self, key):
            return [controls[key]] if key in controls else []

        def click(self, control, settle):
            if control.ctrl_id not in blocked:
                states[control.ctrl_id] = not states[control.ctrl_id]

        def set_text(self, control, value):
            control.value = value

        def get_text(self, control):
            return control.value

    manager = Manager()

    def export(manager_arg, wait):
        observations.append(dict(states))
        return {"files": [], "closed": True, "done_confirmed": True}

    monkeypatch.setattr(workflow09, "_open_export_manager", lambda *args: manager)
    monkeypatch.setattr(em, "ViewerUi", lambda *args: manager)
    monkeypatch.setattr(em, "cancel", lambda *args, **kwargs: True)
    monkeypatch.setattr(em, "export", export)
    monkeypatch.setattr(screen, "radio_selected", lambda control: states[control.ctrl_id])
    ctx = SimpleNamespace(evidence_root=str(tmp_path))

    def run(kind="Normal", anonymous=False):
        result = TCResult("TC_Basic_WorkFlow_09", "format regression")
        result.stop_on_fail = False
        return workflow09._run_one(ctx, None, result, "SYNTHETIC_ID", kind,
                                   anonymous, 3, 4)

    return SimpleNamespace(run=run, states=states, blocked=blocked,
                           observations=observations)


@pytest.mark.parametrize("kind,anonymous", [("Normal", False), ("Anonymous", True)])
def test_export_replaces_persisted_img_with_dicom_only(export_session, kind, anonymous):
    export_session.run(kind, anonymous)
    assert len(export_session.observations) == 1
    observed = export_session.observations[0]
    assert observed[em.FORMAT_DICOM] is True
    assert all(observed[key] is False for key in em.ALL_FORMATS if key != em.FORMAT_DICOM)
    assert observed[em.ANONYMOUS] is anonymous


@pytest.mark.parametrize("blocked_format", [em.FORMAT_DICOM, em.FORMAT_IMG])
def test_unconfirmed_dicom_only_state_prevents_export(export_session, blocked_format):
    export_session.blocked.add(blocked_format)
    with pytest.raises(em.ExportManagerError, match="DICOM"):
        export_session.run()
    assert export_session.observations == []
