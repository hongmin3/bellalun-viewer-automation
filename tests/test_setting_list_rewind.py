"""Validates: REQ-TCUP-002. 중간 위치와 가상 슬롯 재사용을 재현한다."""
from types import SimpleNamespace
from unittest.mock import patch
from core import setting_lists as lists


class Scroller:
    def __init__(self, position=2, movable=True):
        self.position = position
        self.movable = movable
        self.up = 0

    def wheel(self, point, notches, settle=0):
        if notches > 0:
            self.up += 1
        if self.movable:
            self.position = max(0, min(2, self.position + (-1 if notches > 0 else 1)))

    def screen(self, pane, tess=None):
        # 모든 화면에서 동일한 HWND 세 개를 재사용한다.
        rows = [SimpleNamespace(hwnd=i, rect=(0, i*30, 300, i*30+30)) for i in range(3)]
        return rows, ['ABCDE'[self.position+i] for i in range(3)], False


def test_middle_start_rewinds_and_reads_every_row_once():
    ui = Scroller()
    read = []
    with patch.object(lists, '_screen', side_effect=ui.screen):
        result = lists.walk(ui, SimpleNamespace(center=(150,45)),
                            on_row=lambda row, text, index: read.append((index,text)),
                            expected_count=5, notches=1, settle=0)
    assert result['complete'], result['reasons']
    assert result['signatures'] == list('ABCDE')
    assert read == list(enumerate('ABCDE'))
    assert ui.up >= 2


def test_stuck_middle_does_not_claim_complete():
    ui = Scroller(movable=False)
    with patch.object(lists, '_screen', side_effect=ui.screen):
        result = lists.walk(ui, SimpleNamespace(center=(150,45)), expected_count=5, settle=0)
    assert result['complete'] is False
    assert result['reasons']
