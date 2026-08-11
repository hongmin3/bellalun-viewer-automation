# -*- coding: utf-8 -*-
"""Setting > DICOM 페이지 구조 확인 (임시 점검용)."""
import sys
import time

sys.path.insert(0, ".")
from core import flows
from core.ui import ViewerUi

page = sys.argv[1] if len(sys.argv) > 1 else "mwl"
ui = ViewerUi()
ui.activate()
flows.open_dicom_setting(ui, page, wait=3.0)
time.sleep(2)

print(f"--- Setting > DICOM > {page} 컨트롤 ---")
for c in ui.controls(max_depth=8):
    l, t, r, b = c.rect
    if l > 380 and r - l > 30 and b - t > 18:
        val = ""
        if c.cls.startswith("AfxWnd"):
            v = ui.combo_value(c)
            if v and v != c.text:
                val = f"  value={v!r}"
        print("   ", c, val)
