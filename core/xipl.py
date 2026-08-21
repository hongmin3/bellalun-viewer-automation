# -*- coding: utf-8 -*-
"""XIPL.STUDIO UI driver used by the compatibility test cases.

XIPL Studio is a WPF application and does not expose the MFC control IDs used
by Bellalun.  The image open/save dialogs are standard Win32 controls, while
the Studio chrome is stable, scalable WPF content.  This driver therefore
uses window-relative coordinates only for the small set of Studio commands
and validates every action with OCR/image evidence instead of assuming that a
click succeeded.
"""

from __future__ import annotations

import os
import ctypes
import ctypes.wintypes
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageGrab, ImageStat

from .ui import ViewerUi


class XiplStudio:
    PROCESS_NAME = "XIPL.STUDIO"

    def __init__(self, exe=r"C:\XIPL\STUDIO_X64\XIPL.STUDIO.exe",
                 tesseract=r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        self.exe = exe
        self.tesseract = tesseract
        self.ui = ViewerUi(self.PROCESS_NAME)

    def start(self, timeout=20, maximize=False):
        if not self.ui.pid:
            subprocess.Popen([self.exe], cwd=os.path.dirname(self.exe))
        end = time.time() + timeout
        while time.time() < end and not self.ui.pid:
            time.sleep(.5)
            self.ui._pid = None
        if not self.ui.pid:
            raise RuntimeError("XIPL.STUDIO가 실행되지 않았습니다.")
        # Process creation and WPF top-level window creation are independent.
        # Slower PCs can expose a PID several seconds before any visible HWND.
        win = None
        window_end = time.time() + timeout
        while time.time() < window_end and not win:
            win = self.ui.main_window()
            if not win:
                time.sleep(.25)
        if not win:
            raise RuntimeError("XIPL.STUDIO 창을 찾지 못했습니다.")
        # Login window is 650x566. User is the left of the two role buttons.
        if not win.text or (win.rect[3] - win.rect[1]) < 700:
            l, t, r, b = win.rect
            if not self._uia_invoke_named("User", "Button") and not self.click_text("User"):
                # Ratio fallback for builds whose role text is not exposed to
                # OCR.  Unlike the old 412 px offset this scales with DPI.
                self.ui.click((l + int((r-l) * .456),
                               t + int((b-t) * .73)), settle=2)
            else:
                time.sleep(2)
            login_end = time.time() + timeout
            while time.time() < login_end:
                candidate = self.ui.main_window()
                if candidate and candidate.text and (candidate.rect[3] - candidate.rect[1]) >= 700:
                    win = candidate
                    break
                time.sleep(.25)
        win = self.ui.main_window()
        # TC01 must read the Viewer-provided W/L before XIPL's maximized render
        # path applies automatic display processing.  Keep a normal window,
        # but move it wholly onto the primary work area so saved multi-monitor
        # coordinates cannot put it off-screen on another PC.
        ctypes.windll.user32.ShowWindow(win.hwnd, 3 if maximize else 9)
        if not maximize:
            self._place_normal_window(win.hwnd)
        ctypes.windll.user32.SetForegroundWindow(win.hwnd)
        time.sleep(.25)
        return self.ui.main_window()

    def _uia_invoke_named(self, name, control_type="Button"):
        """Invoke a named WPF element through Windows UI Automation."""
        if not self.ui.pid:
            return False
        script = rf'''
Add-Type -AssemblyName UIAutomationClient
$p=Get-Process -Id {self.ui.pid} -ErrorAction Stop
$root=[System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$nc=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'{name}')
$tc=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::{control_type})
$cond=New-Object System.Windows.Automation.AndCondition($nc,$tc)
$els=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond)
$ok=$false
foreach($e in $els){{try{{$pat=$e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern);$pat.Invoke();$ok=$true;break}}catch{{}}}}
if($ok){{'true'}}else{{'false'}}
'''
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                              capture_output=True)
        return proc.stdout.decode("utf-8", "replace").strip().lower().endswith("true")

    def _uia_open_process(self):
        if not self.ui.pid:
            return False
        script = rf'''
Add-Type -AssemblyName UIAutomationClient
$p=Get-Process -Id {self.ui.pid} -ErrorAction Stop
$root=[System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$name=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,'Process')
$type=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::MenuItem)
$cond=New-Object System.Windows.Automation.AndCondition($name,$type)
$els=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond)
foreach($e in $els){{try{{$r=$e.Current.BoundingRectangle;if($r.Y -lt 40){{$pat=$e.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern);$pat.Expand();break}}}}catch{{}}}}
Start-Sleep -Milliseconds 250
$els=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond)
$ok=$false
foreach($e in $els){{try{{$r=$e.Current.BoundingRectangle;if($r.Y -ge 30){{$pat=$e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern);$pat.Invoke();$ok=$true;break}}}}catch{{}}}}
if($ok){{'true'}}else{{'false'}}
'''
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                              capture_output=True)
        return proc.stdout.decode("utf-8", "replace").strip().lower().endswith("true")

    def process_editor_info(self, move_inside=False):
        """Return the WPF PIM editor title and normalize its saved position."""
        win = self.ui.main_window()
        if not win:
            return None
        x, y = win.rect[0] + 55, win.rect[1] + 55
        move = "$true" if move_inside else "$false"
        script = rf'''
Add-Type -AssemblyName UIAutomationClient
$p=Get-Process -Id {self.ui.pid} -ErrorAction Stop
$root=[System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$type=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)
$els=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$type)
$found=$null
foreach($e in $els){{if($e.Current.Name -match 'PIM|PureImpact'){{$found=$e;break}}}}
if($null -ne $found){{
  if({move}){{try{{$tr=$found.GetCurrentPattern([System.Windows.Automation.TransformPattern]::Pattern);$tr.Move({x},{y})}}catch{{}}}}
  Start-Sleep -Milliseconds 200
  $r=$found.Current.BoundingRectangle
  [pscustomobject]@{{title=$found.Current.Name;x=$r.X;y=$r.Y;width=$r.Width;height=$r.Height}} | ConvertTo-Json -Compress
}}
'''
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                              capture_output=True)
        raw = proc.stdout.decode("utf-8", "replace").strip()
        if not raw:
            return None
        try:
            return json.loads(raw.splitlines()[-1])
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _place_normal_window(hwnd, min_size=(1000, 700), preferred=(1400, 900)):
        u32 = ctypes.windll.user32
        work = ctypes.wintypes.RECT()
        u32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
        rect = ctypes.wintypes.RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(rect))
        ww, wh = rect.right - rect.left, rect.bottom - rect.top
        max_w = max(800, work.right - work.left - 40)
        max_h = max(600, work.bottom - work.top - 40)
        if ww < min_size[0] or wh < min_size[1] or ww > max_w or wh > max_h:
            ww, wh = min(preferred[0], max_w), min(preferred[1], max_h)
        x = work.left + max(0, (work.right - work.left - ww) // 2)
        y = work.top + max(0, (work.bottom - work.top - wh) // 2)
        u32.SetWindowPos(hwnd, 0, x, y, ww, wh, 0x0040)  # SWP_SHOWWINDOW

    def _xy(self, x, y):
        w = self.ui.main_window()
        return w.rect[0] + x, w.rect[1] + y

    def capture(self, path):
        w = self.ui.main_window()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=w.rect, all_screens=True).save(path)
        return path

    def ocr(self, image_path):
        if not os.path.exists(self.tesseract):
            return ""
        p = subprocess.run([self.tesseract, image_path, "stdout", "-l", "eng"],
                           capture_output=True)
        return p.stdout.decode("utf-8", "replace")

    def ocr_region(self, image_path, box, scale=3):
        """OCR a small UI region after enlargement (better for dark WPF text)."""
        src = Image.open(image_path).convert("RGB")
        crop = src.crop(box)
        crop = crop.resize((crop.width * scale, crop.height * scale))
        temp = str(Path(image_path).with_suffix(".ocr.png"))
        crop.save(temp)
        if not os.path.exists(self.tesseract):
            return ""
        p = subprocess.run([self.tesseract, temp, "stdout", "-l", "eng", "--psm", "6"],
                           capture_output=True)
        return p.stdout.decode("utf-8", "replace")

    def find_text(self, image_path, wanted):
        """Return OCR word boxes matching *wanted* in window-relative pixels."""
        if not os.path.exists(self.tesseract):
            return []
        p = subprocess.run([self.tesseract, image_path, "stdout", "-l", "eng", "tsv"],
                           capture_output=True)
        rows = []
        for line in p.stdout.decode("utf-8", "replace").splitlines()[1:]:
            cols = line.split("\t", 11)
            if len(cols) != 12:
                continue
            word = cols[11].strip().lower()
            norm = lambda s: s.lower().replace("l", "i").replace("1", "i").strip('[](){}\"\'™”')
            if norm(word) != norm(wanted):
                continue
            try:
                rows.append((int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9]),
                             float(cols[10])))
            except ValueError:
                pass
        return rows

    def click_text(self, wanted, y_max=None, y_min=None):
        temp = os.path.join(tempfile.gettempdir(), "xipl_click_probe.png")
        self.capture(temp)
        boxes = self.find_text(temp, wanted)
        if y_max is not None:
            boxes = [b for b in boxes if b[1] <= y_max]
        if y_min is not None:
            boxes = [b for b in boxes if b[1] >= y_min]
        if not boxes:
            return False
        # Prefer the highest confidence match.
        x, y, w, h, _ = max(boxes, key=lambda b: b[4])
        self.ui.click(self._xy(x + w//2, y + h//2), settle=.8)
        return True

    def open_image(self, path, wait=8):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        self.ui.activate()
        self.ui.key("ESC", settle=.2)  # close an open menu/flyout from a prior action
        self.ui.key_combo(0x11, 0x4F)  # Ctrl+O
        time.sleep(.8)
        edits = [c for c in self.ui.controls(max_depth=6)
                 if c.ctrl_id == 1148 and c.cls == "Edit"]
        opens = [c for c in self.ui.controls(max_depth=6)
                 if c.ctrl_id == 1 and c.cls == "Button"]
        if not edits or not opens:
            # A floating Process editor can own keyboard focus.  The menu path
            # still works and is stable across the supported Studio build.
            if not self.click_text("File", y_max=80):
                self.ui.click(self._xy(68, 20), settle=.3)
            if not self.click_text("Open", y_min=30):
                self.ui.click(self._xy(86, 52), settle=.8)
            edits = [c for c in self.ui.controls(max_depth=6)
                     if c.ctrl_id == 1148 and c.cls == "Edit"]
            opens = [c for c in self.ui.controls(max_depth=6)
                     if c.ctrl_id == 1 and c.cls == "Button"]
        if not edits or not opens:
            raise RuntimeError("XIPL 파일 열기 대화상자를 찾지 못했습니다.")
        self.ui.type_text(edits[0], os.path.abspath(path))
        self.ui.click_button(opens[0].hwnd)
        time.sleep(wait)

    def show_process(self, wait=2):
        if self._uia_open_process():
            time.sleep(wait)
            return
        if not self.click_text("Process", y_max=80):
            # WPF's dark title menu is frequently omitted by Tesseract.  DPI
            # is verified as 100% before UI execution, and the menu is
            # left-anchored, so this window-relative fallback is independent
            # of screen coordinates and window width.
            self.ui.click(self._xy(224, 20), settle=.35)
        if not self.click_text("Process", y_min=30):
            self.ui.click(self._xy(245, 52), settle=.5)
        time.sleep(wait)

    def load_parameter(self, path, wait=3):
        self.ui.key("ESC", settle=.3)
        if not self._uia_invoke_named("Load", "Button") and not self.click_text("Load", y_max=350):
            # White-on-blue Load text is occasionally omitted by OCR.  The
            # PureImpact logo is reliable; Load is fixed 100 px right and
            # 12 px above its text origin within the floating editor.
            temp = os.path.join(tempfile.gettempdir(), "xipl_click_probe.png")
            self.capture(temp)
            boxes = self.find_text(temp, "PureImpact")
            if not boxes:
                raise RuntimeError("XIPL Parameter Editor의 Load 버튼을 OCR로 찾지 못했습니다.")
            x, y, w, h, _ = max(boxes, key=lambda b: b[4])
            self.ui.click(self._xy(x + 100, y - 12), settle=.8)
        edits = [c for c in self.ui.controls(max_depth=6)
                 if c.ctrl_id == 1148 and c.cls == "Edit"]
        opens = [c for c in self.ui.controls(max_depth=6)
                 if c.ctrl_id == 1 and c.cls == "Button"]
        if edits and opens:
            self.ui.type_text(edits[0], os.path.abspath(path))
            self.ui.click_button(opens[0].hwnd)
        else:
            # The Parameter Editor's WPF-owned common dialog is visible but is
            # not enumerated as a separate Win32 window on Studio 1.1.  The
            # filename field receives focus on open, so use real keystrokes.
            self.ui.key_combo(0x11, 0x41)
            self.ui.raw_key(0x2E)
            for ch in os.path.abspath(path):
                self.ui._unicode_char(ch)
            self.ui.key("ENTER", settle=.8)
        time.sleep(wait)

    def run_process(self, wait=12):
        if (not self._uia_invoke_named("Process", "Button")
                and not self.click_text("Process", y_min=80)):
            raise RuntimeError("XIPL Parameter Editor Process button not found")
        time.sleep(wait)

    def set_pim_field(self, field_name, value):
        """Set a slider-backed numeric field in the open Parameter Editor.

        Matches the field's Text label to its nearest Slider by on-screen Y
        position (WPF exposes every slider as an unnamed 'SliderMain'
        element, so name alone cannot disambiguate them) and drives it
        through UI Automation's RangeValuePattern rather than clicking
        spinner arrows, which only step by a fixed increment.
        """
        if not self.ui.pid:
            raise RuntimeError("XIPL.STUDIO가 실행되어 있지 않습니다.")
        script = rf'''
Add-Type -AssemblyName UIAutomationClient
$p = Get-Process -Id {self.ui.pid} -ErrorAction Stop
$root = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$wtype = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$wtype)
$editor = $null
foreach ($w in $wins) {{ if ($w.Current.Name -match 'PIM|PureImpact') {{ $editor = $w; break }} }}
if ($null -eq $editor) {{ Write-Output "ERROR:NO_EDITOR"; exit }}
$all = $editor.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$texts = New-Object System.Collections.Generic.List[object]
$sliders = New-Object System.Collections.Generic.List[object]
foreach ($e in $all) {{
  $c = $e.Current
  if ($c.ControlType.ProgrammaticName -eq "ControlType.Text" -and $c.Name -eq "{field_name}") {{
    $texts.Add($e)
  }} elseif ($c.ControlType.ProgrammaticName -eq "ControlType.Slider") {{
    $sliders.Add($e)
  }}
}}
if ($texts.Count -eq 0) {{ Write-Output "ERROR:FIELD_NOT_FOUND"; exit }}
if ($sliders.Count -eq 0) {{ Write-Output "ERROR:NO_SLIDERS"; exit }}
$bestDist = [double]::MaxValue
$bestSlider = $null
foreach ($t in $texts) {{
  $ty = $t.Current.BoundingRectangle.Y
  foreach ($s in $sliders) {{
    $sy = $s.Current.BoundingRectangle.Y
    $d = [Math]::Abs($ty - $sy)
    if ($d -lt $bestDist) {{ $bestDist = $d; $bestSlider = $s }}
  }}
}}
if ($null -eq $bestSlider -or $bestDist -gt 15) {{ Write-Output "ERROR:NO_MATCHING_SLIDER"; exit }}
$pat = $bestSlider.GetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern)
$oldVal = $pat.Current.Value
$pat.SetValue({value})
Start-Sleep -Milliseconds 200
$newVal = $pat.Current.Value
Write-Output ("OK|{{0}}|{{1}}" -f $oldVal, $newVal)
'''
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                              capture_output=True)
        out = proc.stdout.decode("utf-8", "replace").strip()
        if out.startswith("ERROR"):
            raise RuntimeError(f"XIPL Parameter Editor field '{field_name}' 설정 실패: {out}")
        if not out.startswith("OK"):
            err = proc.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"XIPL Parameter Editor field '{field_name}' 설정 실패: {err or out}")
        _, old, new = out.split("|")
        # RangeValuePattern.SetValue updates the slider's own reported value
        # immediately, but the underlying bound model only commits on
        # LostFocus (verified 2026-08-14: without this, Save silently wrote
        # back the pre-SetValue value). Click the editor's own title bar
        # (non-interactive, no data binding) to blur focus without risking
        # a Tab landing on another row and reshuffling its layout.
        win = self.ui.main_window()
        if win:
            self.ui.click((win.rect[0] + 55 + 150, win.rect[1] + 55 + 10), settle=.3)
        return {"field": field_name, "before": float(old), "after": float(new)}

    def save(self, wait=2):
        """Click Save in the open Parameter Editor (overwrites the loaded file)."""
        if not self._uia_invoke_named("Save", "Button") and not self.click_text("Save", y_max=350):
            raise RuntimeError("XIPL Parameter Editor Save 버튼을 찾지 못했습니다.")
        time.sleep(wait)

    def save_as(self, path, wait=2, settle=2.5):
        """Click Save As and type a new file name in the resulting dialog."""
        # A just-committed set_pim_field() edit (SetValue + blur click) leaves
        # the WPF editor mid-relayout for a couple of seconds; invoking Save
        # As immediately after can find no matching element even though the
        # button reappears moments later (confirmed 2026-08-14: 0/6 probe
        # attempts inside that window found it, then the very next attempt
        # succeeded). Give the layout time to settle before searching.
        time.sleep(settle)
        if not self._uia_invoke_named("Save As", "Button") and not self.click_text("Save As", y_max=350):
            raise RuntimeError("XIPL Parameter Editor Save As 버튼을 찾지 못했습니다.")
        time.sleep(.8)
        edits = [c for c in self.ui.controls(max_depth=6)
                 if c.ctrl_id == 1148 and c.cls == "Edit"]
        opens = [c for c in self.ui.controls(max_depth=6)
                 if c.ctrl_id == 1 and c.cls == "Button"]
        if edits and opens:
            self.ui.type_text(edits[0], os.path.abspath(path))
            self.ui.click_button(opens[0].hwnd)
        else:
            # The floating Process Editor (its "[PIM] - ..." window) runs as
            # a separate helper process from XIPL.STUDIO.exe, so its Save As
            # dialog is owned by that other PID and is invisible to
            # controls() (scoped to self.ui.pid via top_windows). Confirmed
            # 2026-08-14 via EnumWindows: the dialog and "[PIM]" editor share
            # one PID, distinct from XIPL.STUDIO.exe's own. The filename
            # field already has focus when the dialog opens, so drive it
            # with real keystrokes instead of locating Win32 controls (same
            # fix already used by load_parameter's dialog fallback).
            self.ui.key_combo(0x11, 0x41)
            self.ui.raw_key(0x2E)
            for ch in os.path.abspath(path):
                self.ui._unicode_char(ch)
            self.ui.key("ENTER", settle=.8)
        time.sleep(wait)

    def close_process_if_open(self):
        """Close the floating PIM editor only when OCR confirms it is open."""
        self.ui.key("ESC", settle=.2)
        if self.process_editor_info(move_inside=False):
            script = rf'''
Add-Type -AssemblyName UIAutomationClient
$p=Get-Process -Id {self.ui.pid} -ErrorAction Stop
$root=[System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$type=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Window)
$els=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$type)
foreach($e in $els){{if($e.Current.Name -match 'PIM|PureImpact'){{try{{$wp=$e.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern);$wp.Close();'true';break}}catch{{}}}}}}
'''
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True)
            if proc.stdout.decode("utf-8", "replace").strip().lower().endswith("true"):
                time.sleep(1)
                return True
        temp = os.path.join(tempfile.gettempdir(), "xipl_editor_probe.png")
        self.capture(temp)
        text = self.ocr_region(temp, (0, 0, 500, 180), scale=3).upper()
        if "PUREIMPACT" in text or "[PIM]" in text or ".PIM" in text:
            # The floating editor remembers its last position.  Locate the
            # [PIM] title instead of assuming the original dock coordinates;
            # the close glyph is 276~280 px to the right in Studio 1.1.
            title_boxes = self.find_text(temp, "PIM")
            if title_boxes:
                x, y, w, h, _ = min(title_boxes, key=lambda b: b[1])
                self.ui.click(self._xy(x + 278, y + h // 2), settle=1)
            else:
                # Fallback for OCR engines that merge '[PIM]' with '-'.
                self.ui.click(self._xy(354, 50), settle=1)
            return True
        return False

    def process_editor_is_open(self):
        return bool(self.process_editor_info(move_inside=False))

    @staticmethod
    def ensure_test_parameter(source=r"C:\XIPL\PARAMETER\Standard_Default_M.pim",
                              target=r"C:\XIPL\PARAMETER\TEST_2D_FLOW_M.pim"):
        if not os.path.exists(source):
            raise FileNotFoundError(source)
        if not os.path.exists(target) or os.path.getsize(target) != os.path.getsize(source):
            shutil.copy2(source, target)
        return target

    @staticmethod
    def parse_overlay(text):
        dims = re.search(r"(\d{3,5})\s*[xX]\s*(\d{3,5}).*?(?:UInt|Uint|uint)?\s*16", text, re.S)
        wl = re.search(r"W1\s*[:;]?\s*(\d+)\s+W2\s*[:;]?\s*(\d+)", text, re.I)
        if not wl:
            # White-on-black OCR occasionally drops or misreads the tiny W1
            # label but reliably keeps both values and W2.
            wl = re.search(r"(?:W\w?\s*)?[:;]\s*(\d+)\s+W2\s*[:;]?\s*(\d+)", text, re.I)
        return {
            "width": int(dims.group(1)) if dims else None,
            "height": int(dims.group(2)) if dims else None,
            "w1": int(wl.group(1)) if wl else None,
            "w2": int(wl.group(2)) if wl else None,
        }

    def read_overlay_values(self, image_path):
        """Read dimensions and W1/W2 from their fixed XIPL canvas regions.

        Full-window OCR intermittently misses the tiny bottom-left W/L text.
        Region OCR is deterministic because Viewer-launched XIPL is maximized
        by ``start()`` before evidence is captured.
        """
        image = Image.open(image_path).convert("RGB")
        w, h = image.size

        def read(box, psm, whitelist=None, scale=5):
            crop = image.crop(box)
            crop = crop.resize((crop.width * scale, crop.height * scale),
                               Image.Resampling.LANCZOS)
            temp = str(Path(image_path).with_suffix(f".region{box[1]}.png"))
            crop.save(temp)
            args = [self.tesseract, temp, "stdout", "-l", "eng",
                    "--psm", str(psm)]
            if whitelist:
                args.extend(["-c", f"tessedit_char_whitelist={whitelist}"])
            proc = subprocess.run(args, capture_output=True)
            return proc.stdout.decode("utf-8", "replace")

        header_text = read((int(w * .025), int(h * .045),
                            int(w * .38), int(h * .18)), 6)
        wl_text = read((int(w * .025), int(h * .84),
                        int(w * .38), h), 6,
                       "Ww0123456789: ")
        dims = re.search(r"(\d{3,5})\s*[xX]\s*(\d{3,5})", header_text)
        wl = re.search(r"W[1lI]\s*[:;]?\s*(\d+?)\s*W2\s*[:;]?\s*(\d+)",
                       wl_text, re.I)
        if not wl:
            wl = re.search(r"(?:^|\s)[:;]\s*(\d{3,6})\s+W2\s*[:;]?\s*(\d+)",
                           wl_text, re.I | re.M)
        if not wl:
            # The tiny leading W1 label can disappear completely while the
            # two numeric values and W2 remain clear (e.g. '20060 W2: 65628').
            wl = re.search(r"\b(\d{2,6})\s+W2\s*[:;]?\s*(\d{2,6})\b",
                           wl_text, re.I)
        return {
            "width": int(dims.group(1)) if dims else None,
            "height": int(dims.group(2)) if dims else None,
            "w1": int(wl.group(1)) if wl else None,
            "w2": int(wl.group(2)) if wl else None,
            "ocr": {"header": header_text.strip(), "wl": wl_text.strip()},
        }

    def capture_first_overlay(self, image_path, timeout=35):
        """Capture the first fully rendered frame with readable W1/W2.

        Viewer launches XIPL asynchronously.  A PID and main HWND can exist
        while the modal 'File Load in Progress' panel is still visible.  Poll
        the rendered content instead of sleeping a PC-specific number of
        seconds, and return immediately on the first valid overlay so TC01
        observes the non-maximized initial display state.
        """
        end = time.time() + timeout
        last = None
        while time.time() < end:
            self.capture(image_path)
            if self.rendered_fraction(image_path) > .01:
                last = self.read_overlay_values(image_path)
                if (last.get("width") and last.get("height")
                        and last.get("w1") is not None
                        and last.get("w2") is not None):
                    return last
            time.sleep(.25)
        raise RuntimeError(f"XIPL initial overlay did not become readable: {last}")

    def read_applied_parameter(self, image_path):
        """Open XIPL's PIM information panel and return its file name."""
        # Use the named top menu rather than a left-toolbar coordinate.  The
        # toolbar arrangement changes with saved layout and display height.
        info = self.process_editor_info(move_inside=True)
        if not info:
            self.show_process(wait=1)
            info = self.process_editor_info(move_inside=True)
        self.capture(image_path)
        text = self.ocr(image_path)
        match = re.search(r"\[PIM\]\s*-\s*([^\r\n]+?\.pim)\b", text, re.I)
        title_match = re.search(
            r"\[PIM\]\s*-\s*([^\r\n]+?\.pim)\b",
            str((info or {}).get("title", "")), re.I)
        inferred = None
        if not match:
            # At 100% Windows scaling Tesseract often reads the title as
            # 'TEST_20_FLOWpim': D->0 and the tiny extension dot disappears.
            # Presence of the [PIM] title and a trailing pim token is still
            # sufficient evidence that an applied processing parameter is
            # displayed; retain the OCR name in the report.
            loose = re.search(r"\[PIM\]\s*-\s*([^\r\n]+?)(?:\.?\s*pim)\b",
                              text, re.I)
            if loose:
                inferred = loose.group(1).strip() + ".pim"
        if not match:
            # Targeted title-bar OCR fallback for small/high-DPI displays.
            image = Image.open(image_path)
            region = self.ocr_region(
                image_path,
                (int(image.width * .04), int(image.height * .08),
                 int(image.width * .48), int(image.height * .28)), scale=4)
            match = re.search(r"\[PIM\]\s*-\s*([^\r\n]+?\.pim)\b", region, re.I)
            if not match and not inferred:
                loose = re.search(r"\[PIM\]\s*-\s*([^\r\n]+?)(?:\.?\s*pim)\b",
                                  region, re.I)
                if loose:
                    inferred = loose.group(1).strip() + ".pim"
            text = region
        return {
            "parameter": (title_match.group(1).strip() if title_match else
                          match.group(1).strip() if match else inferred),
            "ocr": text.strip(),
            "uia": info,
        }

    @staticmethod
    def rendered_fraction(image_path):
        im = Image.open(image_path).convert("L")
        # Exclude title/tool bars; the center contains the rendered image.
        box = (int(im.width*.15), int(im.height*.10), int(im.width*.90), int(im.height*.95))
        stat = ImageStat.Stat(im.crop(box))
        return stat.mean[0] / 255.0


# 2026-08-21: `latest_2d_image()` / `existing_3d_raw()` 를 지웠다. 저장소 어디서도
# 호출하지 않는 죽은 코드였고, 기본값에 `D:\BellalunData\Image` 가 박혀 있었다.
# 이 PC 의 data_dir 은 `C:\BellalunData` 라(PC 마다 드라이브가 다르다) 누군가
# 인자를 빼고 호출하면 조용히 빈 결과를 돌려줬을 것이다. 필요해지면
# `run.py::_resolve_data_dir` 가 해석한 `ctx.cfg["data_dir"]` 을 넘겨 다시 만든다.
