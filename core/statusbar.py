# -*- coding: utf-8 -*-
"""상태바의 DICOM 서버 연결 상태 판독.

Operation Manual 3.13 / 11.2.1 근거:
상태바 우측에 Storage / Print / MWL 연결 상태 아이콘이 각각 표시되며,
상태는 '연결됨' / '연결되지 않음' 두 가지다.

아이콘은 이미지라 텍스트로 읽을 수 없다. 컨트롤 ID로 위치를 특정한 뒤
해당 영역을 캡처해 '연결되지 않음' 표시(적색 배지)의 유무로 판정한다.
판정 근거를 사람이 검증할 수 있도록 캡처를 증적으로 남긴다.

컨트롤 ID는 2026-08-10 실측값이다. 재설치·버전 변경 시
`python run.py ui-probe` 로 재확인할 것.
"""

import os

# 상태바 StatusBarItem 컨트롤 ID (좌 → 우)
ICONS = {
    "system":  2020,   # 시스템 연결 상태
    "heat":    2027,   # Heat Unit
    "disk":    2021,   # 디스크 잔여 용량
    "storage": 2022,   # DICOM 영상 전송 서버
    "print":   2023,   # DICOM 프린트 서버
    "mwl":     2024,   # DICOM Worklist 서버
    "ups":     2025,   # UPS
}
DICOM_ICONS = ("storage", "print", "mwl")

# '연결되지 않음' 배지는 적색이다. 적색 화소 비율이 이 값을 넘으면 미연결로 본다.
RED_RATIO_THRESHOLD = 0.012


def _grab(rect):
    from PIL import ImageGrab
    l, t, r, b = rect
    return ImageGrab.grab(bbox=(l, t, r, b), all_screens=True).convert("RGB")


def _red_ratio(img):
    """적색 계열 화소 비율. 배지 색(#E74C3C 계열)을 넓게 잡는다."""
    px = img.load()
    w, h = img.size
    if w == 0 or h == 0:
        return 0.0
    red = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r > 130 and r - g > 55 and r - b > 55:
                red += 1
    return red / float(w * h)


def read(ui, evidence_dir=None, tag=""):
    """상태바 아이콘 상태를 읽는다.

    반환: {name: {"connected": bool|None, "red_ratio": float, "evidence": path}}
    컨트롤을 못 찾으면 connected=None (판정 불가).
    """
    out = {}
    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)

    for name, ctrl_id in ICONS.items():
        hits = [c for c in ui.by_id(ctrl_id) if c.visible]
        if not hits:
            out[name] = {"connected": None, "red_ratio": None, "evidence": None,
                         "detail": f"컨트롤 {ctrl_id} 없음"}
            continue
        c = hits[0]
        img = _grab(c.rect)
        ratio = _red_ratio(img)
        path = None
        if evidence_dir:
            path = os.path.join(evidence_dir, f"statusbar_{name}{tag}.png")
            img.save(path)
        connected = ratio < RED_RATIO_THRESHOLD
        out[name] = {"connected": connected, "red_ratio": round(ratio, 4),
                     "evidence": path,
                     "detail": "연결됨" if connected else "연결되지 않음"}
    return out


def dicom_summary(status):
    """DICOM 3종의 연결 여부만 추린다."""
    return {k: status.get(k, {}).get("connected") for k in DICOM_ICONS}


def all_dicom_connected(status):
    vals = dicom_summary(status).values()
    return bool(vals) and all(v is True for v in vals)


def describe(status):
    order = ["system", "storage", "print", "mwl", "disk", "heat", "ups"]
    parts = []
    for k in order:
        v = status.get(k)
        if not v:
            continue
        state = ("연결됨" if v["connected"] else
                 "연결되지 않음" if v["connected"] is False else "판정 불가")
        parts.append(f"{k}={state}")
    return ", ".join(parts)
