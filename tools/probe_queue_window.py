# -*- coding: utf-8 -*-
r"""DICOM 창 Queue 화면을 조회 전용으로 실측한다. TC가 아니다.

SRS 06-10-10 Queue List의 Retry 시험(REQ-OFFICIAL-007)을 만들기 전에
Queue 목록·State 열·Retry/Delete 아이콘의 컨트롤 ID와 화면 위치를 확인한다.
Retry 버튼은 Operation Manual에서도 아이콘으로만 표시되므로 모양으로 추정하지 않고
툴팁으로 기능을 확인한다.

## 안전

메인 메뉴의 DICOM 항목(검증된 `flows.open_dicom_window`)만 누른다. 그 밖의 컨트롤은
커서만 올려 툴팁을 읽고 누르지 않는다. 실행 전후 Queue·Storage 설정 DB 행 수를 비교해
무변경을 출력한다.

    python tools/probe_queue_window.py
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import flows, screen                             # noqa: E402
from core.queue_ui import tooltips as _tooltips            # noqa: E402
from run import Context                                    # noqa: E402

SMALL = 90          # 아이콘 버튼으로 볼 최대 한 변(px)


def _db_counts(db):
    return {
        "queue_rows": db.scalar("DATA", "SELECT COUNT(*) FROM DICOM_STORAGE_QUEUE"),
        "storage_rows": db.scalar("CONFIGURATION", "SELECT COUNT(*) FROM DICOM_STORAGE"),
    }


def _describe(c):
    l, t, r, b = c.rect
    return {"id": c.ctrl_id, "cls": c.cls, "text": c.text, "rect": [l, t, r - l, b - t],
            "depth": c.depth, "enabled": c.enabled}


def main():
    ctx = Context(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "config.json"))
    out_dir = os.path.join(ctx.evidence_root, "ui", "probe_queue_window")
    os.makedirs(out_dir, exist_ok=True)
    before = _db_counts(ctx.db)
    ui = flows.cold_start(ctx.cfg, ctx.db)[0]
    if not flows.ensure_patient_screen(ui):
        raise SystemExit(f"Patient 화면이 아닙니다: {flows.known_screen(ui)}")
    base_ids = {c.hwnd for c in ui.controls(max_depth=9)}
    flows.open_dicom_window(ui)
    time.sleep(2)

    win = ui.main_window()
    screen.grab(win.rect, path=os.path.join(out_dir, "dicom_window.png"))
    controls = ui.controls(max_depth=9)
    new = [c for c in controls if c.hwnd not in base_ids]
    report = {"window": list(win.rect), "db_before": before,
              "top_windows": [{"cls": w.cls, "text": w.text, "rect": list(w.rect)}
                              for w in ui.windows()],
              "new_controls": [_describe(c) for c in new],
              "all_controls": [_describe(c) for c in controls]}
    try:
        report["window_ocr"] = screen.ocr(win.rect, scale=2, psm=11)
    except Exception as exc:                                   # noqa: BLE001
        report["window_ocr"] = f"(OCR 실패: {exc})"

    hovers = []
    candidates = [c for c in controls
                  if c.rect[2] - c.rect[0] <= SMALL and c.rect[3] - c.rect[1] <= SMALL
                  and c.rect[2] - c.rect[0] >= 12 and c.rect[3] - c.rect[1] >= 12
                  and c.text in ("IconButton", "TextButton", "")]
    for index, c in enumerate(candidates):
        try:
            ui.hover(c, settle=1.2)
        except Exception as exc:                               # noqa: BLE001
            hovers.append({**_describe(c), "error": str(exc)})
            continue
        shot = os.path.join(out_dir, f"hover_{index:02}_{c.ctrl_id}.png")
        l, t, r, b = c.rect
        screen.grab((max(0, l - 120), max(0, t - 60), r + 220, b + 60), path=shot)
        hovers.append({**_describe(c), "tooltips": _tooltips(ui), "shot": shot})
    report["hovers"] = hovers
    report["db_after"] = _db_counts(ctx.db)
    report["db_unchanged"] = report["db_before"] == report["db_after"]
    path = os.path.join(out_dir, "probe.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    print(f"[probe-queue] 새 컨트롤 {len(new)}개, 아이콘 후보 {len(candidates)}개, "
          f"DB 무변경 {report['db_unchanged']} -> {path}")


if __name__ == "__main__":
    main()
