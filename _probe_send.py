# -*- coding: utf-8 -*-
"""Examine 화면 Send(1148) 동작 실측 (임시)."""
import sys, os, time
sys.path.insert(0, ".")
from PIL import ImageGrab
from run import Context
from core import flows
from core import viewer_processing as vp
from core.dicom_settings import ensure_bunny

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
ctx = Context("config.json")
print("bunny:", ensure_bunny(ctx.cfg))

# 기존 2D 픽스처(DATA_FLOW_MWL_01)를 Viewer로 연다
session = vp.open_test_study(ctx)
ui = session["ui"]
print("steps:", len(flows.step_items(ui)))
vp.select_2d(ui, session["step_2d"])

# Tool 레일 펼치고 Send 확인
vp.expand_tools(ui)
send = [c for c in ui.by_id(flows.EXAMINE["tool_send"]) if c.visible]
print("send(1148):", [c.rect for c in send])
if not send:
    sys.exit("Send 버튼 없음")
ui.click(send[0], settle=3)
time.sleep(2)
d = ui.dialog()
print("dialog:", d)
out = os.path.join(OUT, "send_dialog.png")
if d:
    ImageGrab.grab(bbox=d.rect, all_screens=True).save(out)
    from core.ui import children
    for c in children(d.hwnd, 3):
        if c.visible and (c.rect[2]-c.rect[0]) >= 50 and (c.rect[3]-c.rect[1]) >= 20:
            print(f"   id={c.ctrl_id} rect={c.rect} cls={c.cls} text={c.text!r}")
else:
    vp.capture_viewer_window(ui, out)
print("saved", out)
