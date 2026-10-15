"""설치 GUI의 화면 독립 계약. 제품이나 Tk 창을 실행하지 않는다."""
from pathlib import Path
from types import SimpleNamespace
import copy

import pytest


def gui_module():
    from bellalunauto import gui
    return gui


def test_command_keeps_absolute_korean_paths_and_only_live_actions(tmp_path):
    gui = gui_module()
    layout = SimpleNamespace(workspace=tmp_path / "한글 작업", config_path=tmp_path / "설정 파일.json")
    assert gui.command_arguments(layout, "run-winupdate") == [
        "--workspace", str(layout.workspace.resolve()), "--config",
        str(layout.config_path.resolve()), "run-winupdate",
    ]
    with pytest.raises(ValueError):
        gui.command_arguments(layout, "convert-winupdate")


def test_command_passes_stop_file_as_global_absolute_argument(tmp_path):
    gui = gui_module()
    layout = SimpleNamespace(workspace=tmp_path, config_path=tmp_path / "config.json")
    arguments = gui.command_arguments(layout, "selfcheck", stop_file=tmp_path / "stop.json")
    assert arguments[-1] == "selfcheck"
    assert arguments[arguments.index("--stop-file") + 1] == str((tmp_path / "stop.json").resolve())


def test_controller_stop_requests_cooperative_exit_before_killing_tree(tmp_path):
    import sys
    gui = gui_module()
    layout = SimpleNamespace(workspace=tmp_path, config_path=tmp_path / "config.json")
    controller = gui.RunController(layout, {})
    controller.start_argv([sys.executable, "-c",
                           "import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); "
                           "exec('while not p.exists(): time.sleep(.01)')", str(tmp_path / "stop.json")])
    controller.stop_path = tmp_path / "stop.json"
    controller.stop()
    assert controller.process.returncode == 0
    assert controller.stop_path.exists()


def test_form_merge_preserves_unexposed_keys_and_input(tmp_path):
    gui = gui_module()
    original = {"viewer": {"login": {"password": "old", "id": "tester"}, "accounts": {"keep": 1}},
                "dicom": {"storage_scp": {"tls_port": 21116, "port": 11116}}, "extra": [1, 2]}
    before = copy.deepcopy(original)
    result = gui.merge_form_config(original, {"viewer.login.password": "new", "dicom.storage_scp.port": "12345"})
    assert result["viewer"]["login"] == {"id": "tester", "password": "new"}
    assert result["viewer"]["accounts"] == {"keep": 1}
    assert result["dicom"]["storage_scp"] == {"tls_port": 21116, "port": 12345}
    assert result["extra"] == [1, 2]
    assert original == before


def test_form_edits_registered_servers_preserving_kind_and_unknown_keys():
    gui = gui_module()
    original = {"dicom": {"servers_to_register": [{"kind": "MWL", "name": "QA", "ip": "old", "port": 123,
                                                  "ae_title": "TEST", "tls_port": 456}]}}
    result = gui.merge_form_config(original, {"dicom.servers_to_register.0.ip": "192.0.2.1",
                                               "dicom.servers_to_register.0.port": "11112"})
    server = result["dicom"]["servers_to_register"][0]
    assert server == {"kind": "MWL", "name": "QA", "ip": "192.0.2.1", "port": 11112,
                      "ae_title": "TEST", "tls_port": 456}
    assert original["dicom"]["servers_to_register"][0]["ip"] == "old"
    assert any(key == "dicom.servers_to_register.0.ip" for _, key, _, _ in gui.form_fields(original))


def test_validation_checks_registered_server_placeholders():
    gui = gui_module()
    errors = gui.validate_config({"dicom": {"servers_to_register": [
        {"kind": "MWL", "name": "TEST", "ip": "REPLACE_ME", "port": 11112, "ae_title": "TEST"}]}})
    assert any("등록 서버 1 호스트" in error for error in errors)


@pytest.mark.parametrize("port", ["0", "65536", "hello", "1.5"])
def test_form_rejects_invalid_ports_without_echoing_secret(port):
    gui = gui_module()
    with pytest.raises(ValueError) as error:
        gui.merge_form_config({}, {"dicom.storage_scp.port": port, "viewer.login.password": "private-token"})
    assert "private-token" not in str(error.value)


def test_validation_reports_missing_fields_without_secret_values():
    gui = gui_module()
    errors = gui.validate_config({"viewer": {"login": {"password": "private-token"}}})
    assert errors
    assert any("Viewer" in error for error in errors)
    assert "private-token" not in " ".join(errors)


def test_validation_rejects_numeric_zero_port_loaded_from_config():
    gui = gui_module()
    errors = gui.validate_config({"dicom": {"storage_scp": {"port": 0}}})
    assert any("Storage 포트" in error for error in errors)


def test_form_rejects_embedded_url_credentials_without_echoing_them():
    gui = gui_module()
    with pytest.raises(ValueError) as error:
        gui.merge_form_config({}, {"dicom.mwl_server_url": "http://tester:private-token@localhost:5000"})
    assert "private-token" not in str(error.value)


def test_log_redaction_recurses_accounts_and_handles_password_assignments():
    gui = gui_module()
    config = {"viewer": {"login": {"password": "private-token"},
                         "accounts": {"staff": {"password": "other-secret"}}}}
    scrub = gui.secret_redactor(config)
    assert scrub("private-token other-secret password=unconfigured") == "[비공개] [비공개] password=[비공개]"


def test_log_redaction_hides_api_keys_in_ordinary_messages():
    gui = gui_module()
    scrub = gui.secret_redactor({"services": [{"api_key": "synthetic-private-api-value"}]})
    assert scrub("Retrying synthetic-private-api-value now") == "Retrying [비공개] now"
    assert scrub('api_key="unconfigured-value"') == "api_key=[비공개]"


def test_first_run_gui_config_uses_shipped_asset_defaults_without_saving(tmp_path):
    gui = gui_module()
    from bellalunauto.runtime import Layout
    resource_dir = tmp_path / "설치 자료"
    checklist_dir = resource_dir / "assets" / "checklists"
    checklist_dir.mkdir(parents=True)
    (resource_dir / "config.example.json").write_text("{}", encoding="utf-8")
    basic = checklist_dir / "Bellalun_Viewer_기본기능_Checklist_개정본.xlsx"
    winupdate = checklist_dir / "Windows Update 호환성 검증 Checklist_Bellalun Viewer_R-25-782.xlsx"
    basic.touch()
    winupdate.touch()
    baseline = resource_dir / "assets" / "Baseline"
    knowledge = resource_dir / "assets" / "지식"
    baseline.mkdir()
    knowledge.mkdir()
    layout = Layout(resource_dir, tmp_path / "새 작업", tmp_path / "새 작업" / "config.json")
    config = gui.load_gui_config(layout)
    assert config["checklist_xlsx"] == str(basic)
    assert config["winupdate_checklist_xlsx"] == str(winupdate)
    assert config["baseline_dir"] == str(baseline)
    assert config["knowledge_dir"] == str(knowledge)
    detected = gui.detect_settings(config)
    assert detected["checklist_xlsx"] == str(basic)
    assert detected["winupdate_checklist_xlsx"] == str(winupdate)
    errors = gui.validate_config(config)
    assert not any(label in error for label in ("기본기능 체크리스트", "Windows Update 체크리스트", "Baseline", "사양 / 매뉴얼") for error in errors)
    assert not layout.config_path.exists()


def test_first_run_invalid_workspace_shows_korean_error_without_writing_config(tmp_path, monkeypatch):
    import sys
    from bellalunauto import runtime
    gui = gui_module()
    destroyed = []
    errors = []

    class Root:
        def withdraw(self):
            pass

        def title(self, value):
            pass

        def geometry(self, value):
            pass

        def destroy(self):
            destroyed.append(True)

    tk = SimpleNamespace(Tk=Root,
                         filedialog=SimpleNamespace(askdirectory=lambda **kwargs: str(tmp_path / "설치 위치")),
                         messagebox=SimpleNamespace(showerror=lambda title, message, **kwargs: errors.append((title, message))),
                         scrolledtext=SimpleNamespace(), ttk=SimpleNamespace())
    monkeypatch.setitem(sys.modules, "tkinter", tk)

    def reject_workspace(**kwargs):
        raise ValueError("설치 폴더를 작업 폴더로 사용할 수 없습니다. 다른 폴더를 선택하세요.")

    monkeypatch.setattr(runtime, "resolve_layout", reject_workspace)
    config_path = tmp_path / "작업" / "config.json"
    layout = SimpleNamespace(config_path=config_path, workspace=config_path.parent, resource_dir=tmp_path / "설치 위치")
    assert gui.launch(layout) == 1
    assert destroyed == [True]
    assert len(errors) == 1 and "설치 폴더" in errors[0][1]
    assert not config_path.exists()


def test_detection_does_not_write_config_or_overwrite_manual_values(tmp_path):
    gui = gui_module()
    original = {"install_dir": str(tmp_path), "viewer": {"exe": "manual.exe"}}
    (tmp_path / "VIEWER.exe").touch()
    assert gui.detect_settings(original)["viewer.exe"] == "manual.exe"
    assert original == {"install_dir": str(tmp_path), "viewer": {"exe": "manual.exe"}}


def test_controller_rejects_overlap_and_logs_sanitized_output(tmp_path):
    import sys
    gui = gui_module()
    layout = SimpleNamespace(workspace=tmp_path, config_path=tmp_path / "config.json")
    process = gui.RunController(layout, {"viewer": {"login": {"password": "private-token"}}})
    process.start_argv([sys.executable, "-c", "import time; print('private-token', flush=True); time.sleep(.3)"])
    with pytest.raises(RuntimeError):
        process.start_argv([sys.executable, "-c", "pass"])
    process.process.wait(timeout=5)
    process.reader.join(timeout=5)
    assert process.log_path.read_text(encoding="utf-8") == "[비공개]\n"
    assert process.drain() == ["[비공개]\n"]
