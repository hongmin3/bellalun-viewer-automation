"""ui.children 는 하위 창을 한 번씩만 조회한다.

EnumChildWindows 는 손자 창까지 이미 열거한다. 하위 창마다 다시 열거하면 깊이만큼
같은 창에 WM_GETTEXT 를 다시 보내 Viewer UI 스레드를 기다리게 된다.
"""
from unittest import mock

from core import ui

# 1 -> 2 -> 3 -> 4, 1 -> 5
PARENT = {2: 1, 3: 2, 4: 3, 5: 1}


def descendants(hwnd):
    found = []
    for child in sorted(PARENT):
        node = PARENT[child]
        while node is not None and node != hwnd:
            node = PARENT.get(node)
        if node == hwnd:
            found.append(child)
    return found


class FakeUser32:
    def __init__(self):
        self.texts = []

    def EnumChildWindows(self, hwnd, proc, _):
        for child in descendants(hwnd):
            proc(child, 0)
        return True

    def GetParent(self, hwnd):
        return PARENT.get(hwnd, 0)

    def GetDlgCtrlID(self, hwnd):
        return hwnd * 10

    def IsWindowVisible(self, hwnd):
        return True


def test_children_reads_each_descendant_once_with_its_real_depth():
    fake = FakeUser32()
    reads = []
    with mock.patch.object(ui, 'u32', fake), \
         mock.patch.object(ui, '_EnumProc', lambda f: f), \
         mock.patch.object(ui, '_class_of', lambda h: 'C'), \
         mock.patch.object(ui, '_text_of', lambda h: reads.append(h) or f't{h}'), \
         mock.patch.object(ui, '_rect_of', lambda h: (0, 0, h, h)):
        found = ui.children(1, 5)
    assert [c.hwnd for c in found] == [2, 3, 4, 5]
    assert sorted(reads) == [2, 3, 4, 5]
    assert {c.hwnd: c.depth for c in found} == {2: 1, 3: 2, 4: 3, 5: 1}
    assert [c.ctrl_id for c in found] == [20, 30, 40, 50]
