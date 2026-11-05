"""REQ-DIST-006: 사내 배포본의 팀 공통 서버 설정(사용자 결정 2026-11-05)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bellalunauto import resources


SAMPLE = {
    "viewer": {"exe": "C:/x/VIEWER.exe", "login": {"id": "qa", "password": "secret"}},
    "dicom": {
        "mwl_server_url": "http://mwl.example:8080",
        "print_scp": {"host": "10.0.0.5", "ae_title": "PRINT_SCP", "port": 11113, "password": "x"},
        "storage_scp": {"api_url": "http://st.example:5003", "token": "t"},
        "servers_to_register": [{"kind": "MWL", "name": "MWL_TEST", "ip": "10.0.0.6", "port": 11112}],
        "_comment": "lab note",
    },
}


class TeamSettingsTests(unittest.TestCase):
    def test_payload_keeps_servers_and_test_account_only(self):
        """사용자 결정: 사내 전용 배포본에는 시험 계정도 넣는다. 그 밖의 비밀 값과 경로는 넣지 않는다."""
        payload = resources.team_settings_payload(SAMPLE)
        self.assertEqual(set(payload), {"dicom", "viewer"})
        self.assertEqual(payload["viewer"], {"login": {"id": "qa", "password": "secret"}})
        dicom = payload["dicom"]
        self.assertEqual(dicom["mwl_server_url"], "http://mwl.example:8080")
        self.assertEqual(dicom["print_scp"], {"host": "10.0.0.5", "ae_title": "PRINT_SCP", "port": 11113})
        self.assertEqual(dicom["storage_scp"], {"api_url": "http://st.example:5003"})
        self.assertEqual(dicom["servers_to_register"][0]["ip"], "10.0.0.6")
        self.assertNotIn("_comment", dicom)
        self.assertNotIn('"t"', json.dumps(dicom))

    def test_payload_without_server_values_is_rejected(self):
        for config in ({}, {"dicom": {}}, {"dicom": {"mwl_server_url": "", "print_scp": {"host": "REPLACE_ME"}}}):
            with self.assertRaises(ValueError):
                resources.team_settings_payload(config)

    def test_bundled_file_is_read_and_sanitized_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(resources.load_team_settings(tmp))
            (Path(tmp)/resources.TEAM_SETTINGS).write_text(json.dumps(SAMPLE), encoding="utf-8")
            loaded = resources.load_team_settings(tmp)
            self.assertEqual(set(loaded), {"dicom", "viewer"})
            self.assertNotIn("VIEWER.exe", json.dumps(loaded))

    def test_first_run_uses_team_servers_and_previous_pc_values_win(self):
        from bellalunauto import gui
        team = resources.team_settings_payload(SAMPLE)
        base = {"dicom": {"mwl_server_url": "", "print_scp": {"host": "REPLACE_ME", "port": ""}}}
        with patch.object(gui, "registered_viewer_locations", return_value=[]), \
                patch.object(gui, "_fixed_drive_roots", return_value=[]), \
                patch.object(gui, "_sql_instances", return_value=[]), \
                patch.object(gui, "team_settings", return_value=team):
            with patch.object(gui, "previous_config", return_value=None):
                only_team = gui.first_run_config(base)
            with patch.object(gui, "previous_config",
                              return_value={"dicom": {"mwl_server_url": "http://mine.example:1"}}):
                mixed = gui.first_run_config(base)
        self.assertEqual(only_team["dicom"]["mwl_server_url"], "http://mwl.example:8080")
        self.assertEqual(only_team["dicom"]["print_scp"]["host"], "10.0.0.5")
        self.assertEqual(only_team["dicom"]["servers_to_register"][0]["ip"], "10.0.0.6")
        self.assertEqual(mixed["dicom"]["mwl_server_url"], "http://mine.example:1")
        self.assertEqual(mixed["dicom"]["print_scp"]["host"], "10.0.0.5")
        self.assertEqual(only_team["viewer"]["login"], {"id": "qa", "password": "secret"})


class InvalidPreviousValueTests(unittest.TestCase):
    def test_one_malformed_previous_value_is_skipped_not_blocking_first_run(self):
        """리뷰 지적: 가져온 값 하나가 형식 오류면 첫 실행이 매번 막히고 빠져나갈 길이 없었다."""
        from bellalunauto import gui
        previous = {"dicom": {"mwl_server_url": "10.0.0.5:8080", "print_server_url": "http://ok.example:1"}}
        with patch.object(gui, "registered_viewer_locations", return_value=[]), \
                patch.object(gui, "_fixed_drive_roots", return_value=[]), \
                patch.object(gui, "_sql_instances", return_value=[]), \
                patch.object(gui, "team_settings", return_value=None), \
                patch.object(gui, "previous_config", return_value=previous):
            config = gui.first_run_config({"dicom": {"mwl_server_url": "", "print_server_url": ""}})
        self.assertEqual(config["dicom"]["mwl_server_url"], "")
        self.assertEqual(config["dicom"]["print_server_url"], "http://ok.example:1")


class BuildTeamSettingsTests(unittest.TestCase):
    def test_build_stages_sanitized_file_and_records_only_hash_and_keys(self):
        import importlib.util, hashlib
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("build_distribution", root/"tools"/"build_distribution.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/"local-config.json"
            source.write_text(json.dumps(SAMPLE), encoding="utf-8")
            res = Path(tmp)/"resources"
            res.mkdir()
            info = build.stage_team_settings(source, res)
            staged = res/resources.TEAM_SETTINGS
            self.assertEqual(json.loads(staged.read_text(encoding="utf-8")), resources.team_settings_payload(SAMPLE))
            self.assertEqual(info["sha256"], hashlib.sha256(staged.read_bytes()).hexdigest())
            self.assertEqual(info["included"], True)
            text = json.dumps(info)
            self.assertNotIn("10.0.0.5", text)
            self.assertNotIn("secret", text)
            self.assertIsNone(build.stage_team_settings(None, res))


if __name__ == "__main__":
    unittest.main()
