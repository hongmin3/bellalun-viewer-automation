# -*- coding: utf-8 -*-
"""`flows.require_primary_monitor` 와 그 호출 지점을 고정한다.

2026-08-31 실측: 이 검사가 `cold_start` 의 **기동/로그인 경로에만** 있어서,
이미 떠 있는 Viewer 를 재사용하는 경로(`force_restart=False`, `config.json` 기본값)
에서는 아예 평가되지 않았다. 창을 (-600, 100)으로 옮긴 뒤
`cold_start(force_restart=False)` 를 호출했더니 중단 없이 정상 반환했다.
재사용 경로를 쓰는 TC(`WF_01`/`WF_05`/`run-ui`)가 어긋난 창에서 그대로 진행하는
것을 막기 위해 두 경로가 같은 검사를 쓰게 했고, 그 구조를 여기서 고정한다.
"""
import unittest
from unittest import mock

from core import flows


class _Win:
    def __init__(self, rect):
        self.rect = rect


class _Ui:
    """`cold_start` 재사용 분기가 쓰는 최소 인터페이스."""

    def __init__(self, rect, pid=1234):
        self._win = _Win(rect) if rect is not None else None
        self.pid = pid
        self.swept = False

    def main_window(self):
        return self._win

    def at_login_screen(self):
        return False


class _Db:
    def ping(self):
        return True


class RequirePrimaryMonitorTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("core.display.screen_size", lambda: (1920, 1080))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_inside_primary_monitor_passes(self):
        flows.require_primary_monitor(_Ui((0, 0, 1920, 1080)))

    def test_negative_left_aborts(self):
        with self.assertRaises(flows.FlowError) as caught:
            flows.require_primary_monitor(_Ui((-600, 100, 1320, 1180)))
        self.assertIn("주 모니터", str(caught.exception))

    def test_beyond_right_edge_aborts(self):
        with self.assertRaises(flows.FlowError):
            flows.require_primary_monitor(_Ui((1920, 0, 3840, 1080)))

    def test_missing_window_is_not_an_abort(self):
        """창을 아직 못 찾은 상태를 '어긋났다'고 단정하지 않는다."""
        flows.require_primary_monitor(_Ui(None))


class ColdStartReusePathTests(unittest.TestCase):
    """**재사용 경로도** 창 위치 검사를 거치는지 고정한다(이번 결함의 본질)."""

    def setUp(self):
        patcher = mock.patch("core.display.screen_size", lambda: (1920, 1080))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = {"viewer": {"force_restart": False, "login": {}},
                    "evidence_ui_dir": "Evidence/ui"}

    def _cold_start(self, rect):
        ui = _Ui(rect)
        with mock.patch.object(flows, "ViewerUi", lambda *a, **k: ui), \
                mock.patch("core.watchdog.DialogGuard") as guard:
            guard.return_value.sweep.return_value = []
            out = flows.cold_start(self.cfg, _Db(), force_restart=False)
        return ui, out, guard

    def test_reuse_of_offscreen_window_aborts(self):
        with self.assertRaises(flows.FlowError) as caught:
            self._cold_start((-600, 100, 1320, 1180))
        self.assertIn("주 모니터", str(caught.exception))

    def test_reuse_aborts_before_any_click(self):
        """팝업 정리(클릭)보다 **먼저** 막아야 한다."""
        try:
            _ui, _out, guard = self._cold_start((-600, 100, 1320, 1180))
        except flows.FlowError:
            pass
        else:  # pragma: no cover - 위 시험이 이미 잡는다
            self.fail("어긋난 창에서 중단하지 않았다")

    def test_reuse_inside_primary_monitor_still_reuses(self):
        ui, out, _guard = self._cold_start((0, 0, 1920, 1080))
        self.assertIs(ui, out[0])
        self.assertTrue(any("재사용" in line for line in out[1]))


if __name__ == "__main__":
    unittest.main()
