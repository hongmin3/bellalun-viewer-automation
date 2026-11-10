"""클릭한 콤보와 인접한 유일한 제품 팝업의 준비를 기다린다."""
import time

# 팝업 테두리와 항목 창 경계의 오차 허용(px).
EDGE = 2


def wait_items(ui, combo, children, timeout=3, required_id=None):
    # ViewerUi.windows()는 해당 Viewer PID의 창만 반환한다.
    end = time.monotonic() + timeout
    while True:
        l, t, r, b = combo.rect
        popups = []
        for popup in ui.windows():
            if popup.text != 'ItemList' or not popup.visible:
                continue
            pl, pt, pr, pb = popup.rect
            adjacent = pt <= b <= pb or pt <= t <= pb or min(abs(pt-b), abs(pb-t)) <= 8
            if max(l, pl) < min(r, pr) and adjacent:
                popups.append(popup)
        if len(popups) > 1:
            raise RuntimeError('콤보에 인접한 ItemList 팝업이 여러 개입니다.')
        if popups:
            # 팝업은 고정 개수의 항목 창을 만들고 보이는 높이만큼만 그린다.
            # 팝업 밖에 놓인 항목 창은 화면에서 다른 UI 위치라 후보가 아니다(Header Layout 실측).
            _, top, _, bottom = popups[0].rect
            items = sorted({c.hwnd: c for c in children(popups[0].hwnd, 4)
                            if c.visible and c.text == 'TextButton'
                            and top - EDGE <= c.rect[1] < c.rect[3] <= bottom + EDGE}.values(),
                           key=lambda c: c.rect[1])
            if items and (required_id is None or any(c.ctrl_id == required_id for c in items)):
                return items
        if time.monotonic() >= end:
            raise RuntimeError('콤보 ItemList 준비 시간 초과; '
                               f'adjacent_popups={len(popups)}')
        time.sleep(.1)
