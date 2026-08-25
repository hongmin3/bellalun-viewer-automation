import unittest
import time
from unittest.mock import patch

from PIL import Image

from core import flows


class _Control:
    def __init__(self, hwnd, ctrl_id, *, visible=True, rect=(0, 0, 30, 20)):
        self.hwnd = hwnd
        self.ctrl_id = ctrl_id
        self.visible = visible
        self.rect = rect


class _FakeUi:
    """팝업 범위 선택과 클릭 후 종료 확인만 검증하는 최소 가짜 UI."""

    def __init__(self, *, close_on_click=True, buttons=None):
        self._dialog = _Control(100, -1, rect=(100, 100, 500, 300))
        self._buttons = buttons or [_Control(200, flows.SETTING_CONFIRM_OK)]
        self.close_on_click = close_on_click
        self.clicked = []

    def dialog(self):
        return self._dialog

    def dialog_buttons(self, dialog):
        self.asserted_dialog = dialog
        return list(self._buttons)

    def click(self, control, settle=0):
        del settle
        self.clicked.append(control)
        if self.close_on_click:
            self._dialog = None

    def by_id(self, _ctrl_id):
        raise AssertionError("Viewer 전체 by_id를 쓰면 팝업 밖의 ID 500을 누를 수 있다")


class SettingDialogTests(unittest.TestCase):
    def test_inline_result_text_requires_known_update_message(self):
        self.assertTrue(flows._setting_result_text(
            "You need to restart the program to apply these changes. OK"))
        self.assertTrue(flows._setting_result_text(
            "Device - UPS Update successfully."))
        self.assertFalse(flows._setting_result_text("Update"))

    def test_pink_button_point_ignores_thin_border(self):
        image = Image.new("RGB", (1000, 700), "white")
        pixels = image.load()
        pink = (244, 101, 123)
        # 팝업 테두리는 길지만 1px뿐이다.
        for x in range(300, 700):
            pixels[x, 250] = pink
        # 중앙의 채워진 OK 버튼.
        for y in range(390, 430):
            for x in range(455, 545):
                pixels[x, y] = pink
        point = flows._pink_button_point(image)
        self.assertIsNotNone(point)
        self.assertTrue(455 <= point[0] <= 544)
        self.assertTrue(390 <= point[1] <= 429)

    def test_pink_button_point_does_not_merge_same_row_controls(self):
        image = Image.new("RGB", (1000, 700), "white")
        pixels = image.load()
        pink = (244, 101, 123)
        # 실제 Setting 화면처럼 OK 왼쪽 같은 높이에 라디오 표시가 있어도
        # 두 도형의 min/max 중간점을 클릭해서는 안 된다.
        for y in range(390, 430):
            for x in range(455, 545):
                pixels[x, y] = pink
        for y in range(395, 425):
            for x in range(350, 370):
                pixels[x, y] = pink
        point = flows._pink_button_point(image)
        self.assertIsNotNone(point)
        self.assertTrue(455 <= point[0] <= 544)
        self.assertTrue(390 <= point[1] <= 429)

    def test_closes_two_consecutive_inline_results(self):
        ui = _FakeUi()
        ui._dialog = None
        first = {"point": (10, 10), "text": "restart"}
        second = {"point": (20, 20), "text": "success"}
        with patch.object(flows, "_setting_inline_result",
                          side_effect=[first, second, second, None, None]):
            self.assertTrue(flows.confirm_setting_dialog(
                ui, timeout=.2, wait=.01, required=True))
        self.assertEqual([(10, 10), (20, 20)], ui.clicked)

    def test_keeps_success_when_ocr_uses_original_timeout(self):
        ui = _FakeUi()
        ui._dialog = None
        result = {"point": (10, 10), "text": "success"}

        def slow_result(*_args):
            time.sleep(.02)
            return slow_result.results.pop(0)

        slow_result.results = [result, None, None]
        with patch.object(flows, "_setting_inline_result",
                          side_effect=slow_result):
            self.assertTrue(flows.confirm_setting_dialog(
                ui, timeout=.01, wait=.01, required=True))

    def test_scopes_ok_to_dialog_and_waits_for_close(self):
        ui = _FakeUi()
        self.assertTrue(flows.confirm_setting_dialog(ui, timeout=.1,
                                                     wait=.01,
                                                     required=True))
        self.assertEqual([200], [c.hwnd for c in ui.clicked])
        self.assertIsNone(ui.dialog())

    def test_rejects_ambiguous_dialog_buttons(self):
        ui = _FakeUi(buttons=[_Control(200, 500), _Control(201, 500)])
        with self.assertRaisesRegex(flows.FlowError, "OK 버튼 구성"):
            flows.confirm_setting_dialog(ui, timeout=.1, wait=.01,
                                         required=True)
        self.assertEqual([], ui.clicked)

    def test_does_not_continue_when_popup_stays_open(self):
        ui = _FakeUi(close_on_click=False)
        with self.assertRaisesRegex(flows.FlowError, "팝업이 닫히지 않았습니다"):
            flows.confirm_setting_dialog(ui, timeout=.1, wait=.01,
                                         required=True)

    def test_required_update_rejects_missing_popup(self):
        ui = _FakeUi()
        ui._dialog = None
        with self.assertRaisesRegex(flows.FlowError, "결과 팝업이 나타나지 않았습니다"):
            flows.confirm_setting_dialog(ui, timeout=.01, wait=.01,
                                         required=True)


if __name__ == "__main__":
    unittest.main()
