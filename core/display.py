# -*- coding: utf-8 -*-
"""Windows display normalization for deterministic UI automation."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w


ENUM_CURRENT_SETTINGS = -1
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
CDS_TEST = 0x00000002
DISP_CHANGE_SUCCESSFUL = 0


class POINTL(ctypes.Structure):
    _fields_ = [("x", w.LONG), ("y", w.LONG)]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", w.WCHAR * 32),
        ("dmSpecVersion", w.WORD), ("dmDriverVersion", w.WORD),
        ("dmSize", w.WORD), ("dmDriverExtra", w.WORD),
        ("dmFields", w.DWORD),
        ("dmPosition", POINTL),
        ("dmDisplayOrientation", w.DWORD),
        ("dmDisplayFixedOutput", w.DWORD),
        ("dmColor", w.SHORT), ("dmDuplex", w.SHORT),
        ("dmYResolution", w.SHORT), ("dmTTOption", w.SHORT),
        ("dmCollate", w.SHORT), ("dmFormName", w.WCHAR * 32),
        ("dmLogPixels", w.WORD), ("dmBitsPerPel", w.DWORD),
        ("dmPelsWidth", w.DWORD), ("dmPelsHeight", w.DWORD),
        ("dmDisplayFlags", w.DWORD), ("dmDisplayFrequency", w.DWORD),
        ("dmICMMethod", w.DWORD), ("dmICMIntent", w.DWORD),
        ("dmMediaType", w.DWORD), ("dmDitherType", w.DWORD),
        ("dmReserved1", w.DWORD), ("dmReserved2", w.DWORD),
        ("dmPanningWidth", w.DWORD), ("dmPanningHeight", w.DWORD),
    ]


def screen_size():
    u32 = ctypes.windll.user32
    return int(u32.GetSystemMetrics(0)), int(u32.GetSystemMetrics(1))


def system_dpi():
    u32 = ctypes.windll.user32
    getter = getattr(u32, "GetDpiForSystem", None)
    return int(getter()) if getter else 96


def ensure_resolution(width=1920, height=1080, enforce=True):
    """Set the primary display resolution when supported, then verify it.

    The mode is tested before it is applied.  Unsupported modes fail safely
    instead of leaving Windows in a partially changed display state.
    """
    before = screen_size()
    target = (int(width), int(height))
    if before == target:
        return {"ok": True, "before": before, "actual": before,
                "changed": False, "detail": "already configured"}
    if not enforce:
        return {"ok": False, "before": before, "actual": before,
                "changed": False, "detail": "resolution mismatch"}

    u32 = ctypes.windll.user32
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    if not u32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS,
                                    ctypes.byref(mode)):
        return {"ok": False, "before": before, "actual": before,
                "changed": False, "detail": "EnumDisplaySettings failed"}
    mode.dmPelsWidth, mode.dmPelsHeight = target
    mode.dmFields |= DM_PELSWIDTH | DM_PELSHEIGHT
    test_code = int(u32.ChangeDisplaySettingsW(ctypes.byref(mode), CDS_TEST))
    if test_code != DISP_CHANGE_SUCCESSFUL:
        return {"ok": False, "before": before, "actual": screen_size(),
                "changed": False,
                "detail": f"1920x1080 mode unsupported (code={test_code})"}
    apply_code = int(u32.ChangeDisplaySettingsW(ctypes.byref(mode), 0))
    actual = screen_size()
    return {"ok": apply_code == DISP_CHANGE_SUCCESSFUL and actual == target,
            "before": before, "actual": actual, "changed": actual != before,
            "detail": f"ChangeDisplaySettings code={apply_code}"}


def normalize(cfg):
    spec = cfg.get("display") or {}
    width = int(spec.get("width", 1920))
    height = int(spec.get("height", 1080))
    result = ensure_resolution(width, height, bool(spec.get("enforce", True)))
    result["dpi"] = system_dpi()
    result["dpi_ok"] = result["dpi"] == int(spec.get("expected_dpi", 96))
    result["ok"] = bool(result["ok"] and result["dpi_ok"])
    return result
