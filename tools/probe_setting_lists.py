# -*- coding: utf-8 -*-
r"""Setting 각 페이지의 **목록 컨트롤**을 조회 전용으로 실측한다.

TC 가 아니다. `TC_Basic_WorkFlow_14` 의 남은 수동 항목("스크롤 아래 숨은 목록
행의 상세값")을 자동화하기 전에, 어떤 페이지에 목록이 있고 그 목록이 어떤
구조인지 **눈으로 확인**하기 위한 도구다.

## 왜 필요한가

2026-08-25 에 목록 스크롤을 시도했다가 제거했다. 이유는 **가상 `ListItem` 이
같은 HWND/ID 를 재사용**해서, 조금 내린 뒤 일부 행만 읽고도 끝으로 오인할 수
있었기 때문이다. 다시 만들려면 먼저 알아야 한다.

  1. 목록이 있는 페이지가 어디인가 (전 페이지를 도는 비용을 줄이려면 필요)
  2. 한 행의 **문구**를 읽을 수 있는가 (읽을 수 있으면 HWND 대신 그것으로 식별)
  3. 화면에 보이는 행 수와 **DB 원천 테이블 행 수**가 얼마나 차이나는가
     (숨은 행이 실제로 있는 목록만 스크롤하면 된다)
  4. 스크롤바 컨트롤이 별도로 존재하는가

## 안전

레일 컨트롤(검증된 `flows.open_group_page`)만 누르고 목록은 **읽기만** 한다.
행을 클릭하지도, Update 를 누르지도 않는다. 그래도 "누르지 않아도 즉시 저장되는"
화면이 있었으므로(AGENTS.md 3절) 전후로 설정 스냅샷을 떠서 무변경을 확인해
출력한다.

    python tools/probe_setting_lists.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import flows, setting_values, snapshot          # noqa: E402
from core.ui import ViewerUi, children                    # noqa: E402
from run import Context                                   # noqa: E402

#: 목록 행으로 볼 컨트롤의 `WM_GETTEXT` 이름. `setting_values.GENERIC_TEXTS` 에
#  들어 있는 일반 이름들이라 값이 아니라 **종류**다.
ROW_TEXTS = {"ListItem", "SystemThumbnailItem"}


def row_signature(row):
    """행 하나의 식별 문구. 자식들의 텍스트를 이어 붙인다."""
    parts = []
    for c in children(row.hwnd, 3):
        if not c.visible:
            continue
        text = (c.text or "").strip()
        if text and text not in setting_values.GENERIC_TEXTS:
            parts.append(text)
    return " | ".join(parts)


def list_rows(pane):
    """패널 안의 목록 행 후보(위->아래)."""
    rows, seen = [], set()
    for c in setting_values.pane_controls(pane, depth=6):
        if (c.text or "") in ROW_TEXTS and c.hwnd not in seen:
            seen.add(c.hwnd)
            rows.append(c)
    return sorted(rows, key=lambda c: (c.rect[1], c.rect[0]))


def main():
    ctx = Context(os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))), "config.json"))
    before = snapshot.take(ctx.db)

    cfg = ctx.cfg["viewer"]
    ui = ViewerUi()
    ui.ensure_ready(cfg["exe"], cfg["login"]["id"], cfg["login"]["password"])
    flows.ensure_patient_screen(ui)

    found = []
    for group in flows.SETTING_GROUPS:
        for page in flows.setting_pages(group):
            key = f"{group}.{page}"
            try:
                rail = flows.open_group_page(ui, group, page, wait=1.2)
                window = setting_values.setting_window(ui)
                pane = setting_values.pane_control(ui, rail, window=window)
                if pane is None:
                    print(f"[skip] {key}: 콘텐츠 패널 없음")
                    continue
                rows = list_rows(pane)
            except Exception as exc:                       # noqa: BLE001
                print(f"[err ] {key}: {type(exc).__name__}: {exc}")
                continue
            if not rows:
                continue
            sigs = [row_signature(r) for r in rows]
            readable = sum(1 for s in sigs if s)
            found.append(key)
            print(f"\n=== {key} — 행 {len(rows)}개 (문구 읽힘 {readable}개) ===")
            print(f"    패널 rect={pane.rect}")
            for r_, s in zip(rows, sigs):
                pl, pt = pane.rect[0], pane.rect[1]
                rel = (r_.rect[0] - pl, r_.rect[1] - pt,
                       r_.rect[2] - pl, r_.rect[3] - pt)
                print(f"    id={r_.ctrl_id:<6} hwnd={r_.hwnd:<10} rel={rel} "
                      f"text={s!r}")
            # 스크롤 후보: 같은 패널 안의 Scroll 컨트롤
            scrolls = [c for c in setting_values.pane_controls(pane, depth=6)
                       if (c.text or "") == "Scroll"]
            for s_ in scrolls:
                print(f"    [scroll] id={s_.ctrl_id} rect={s_.rect} "
                      f"class={s_.cls}")

    print(f"\n목록이 있는 페이지 {len(found)}개: {found}")

    after = snapshot.take(ctx.db)
    same, diff = snapshot.config_identical(before, after)
    print(f"\n설정 DB 무변경: {same}" + ("" if same else f" — 차이 {sorted(diff)}"))


if __name__ == "__main__":
    main()
