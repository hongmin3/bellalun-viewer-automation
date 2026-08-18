# -*- coding: utf-8 -*-
"""Examined 목록 띄우기 실측 (임시). 삭제/잠금(2185/2186/2193)은 절대 누르지 않는다."""
import sys, os, time
sys.path.insert(0, ".")
from run import Context
from core import flows
from core import viewer_processing as vp

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
ctx = Context("config.json")
ui, _ = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
    flows.close_examine(ui, option="close", wait=10)
flows.ensure_patient_screen(ui, wait=3)

flows.open_main_menu(ui)
view = [c for c in ui.by_id(flows.MAIN_MENU["item_view"])
        if c.visible and c.rect[2]-c.rect[0] > 20]
ui.click(view[0], settle=6)
time.sleep(2)
vp.capture_viewer_window(ui, os.path.join(OUT, "a_open.png"))
print("opened; range/search controls:")
for cid in (1106, 1107, 1108, 1109, 2180):
    hits = [c for c in ui.by_id(cid) if c.visible]
    print(f"  {cid}: {[c.rect for c in hits]}")
# 검색만 눌러 본다 (기본 Today 유지)
srch = [c for c in ui.by_id(2180) if c.visible]
if srch:
    ui.click(srch[0], settle=3)
time.sleep(2)
vp.capture_viewer_window(ui, os.path.join(OUT, "b_searched.png"))
print("saved b_searched.png")
# 목록 행 컨트롤 후보
rows = [c for c in ui.controls(max_depth=8)
        if 310 < c.rect[1] < 890 and (c.rect[2]-c.rect[0]) > 400]
print("list-area controls:", [(c.ctrl_id, c.rect, c.text) for c in rows][:8])
