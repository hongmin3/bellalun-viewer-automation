# -*- coding: utf-8 -*-
"""화면 픽셀에서 값을 읽어내는 보조 도구.

Bellalun Viewer는 상당수의 문구와 상태를 커스텀 렌더링한다. 그런 컨트롤은
WM_GETTEXT로 읽을 수 없으므로, 판정에 꼭 필요한 것만 화면 캡처 + OCR /
픽셀 검사로 읽는다. 읽은 값은 항상 캡처 파일을 증적으로 남겨 사람이
재확인할 수 있게 한다.
"""

import os
import subprocess
import tempfile

TESSERACT_EXE = os.environ.get(
    "BELLALUN_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def grab(box, path=None, scale=1):
    """화면 영역을 캡처한다. path를 주면 파일로 저장한다."""
    from PIL import ImageGrab
    img = ImageGrab.grab(bbox=tuple(box), all_screens=True).convert("RGB")
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale))
    if path:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        img.save(path)
    return img


def ocr(box, scale=3, psm=6, path=None):
    """화면 영역의 문자열을 읽는다. Tesseract가 없으면 빈 문자열."""
    if not os.path.exists(TESSERACT_EXE):
        return ""
    img = grab(box, path=path, scale=scale)
    fd, temp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        img.save(temp)
        p = subprocess.run([TESSERACT_EXE, temp, "stdout", "-l", "eng",
                            "--psm", str(psm)], capture_output=True)
        return p.stdout.decode("utf-8", "replace").strip()
    finally:
        os.remove(temp)


def ocr_contains(box, needle, **kw):
    """OCR 결과에 needle이 들어 있는지. (공백/대소문자 무시)"""
    got = " ".join(ocr(box, **kw).split()).lower()
    return needle.lower() in got, got


# --- 커스텀 라디오/토글 판독 ------------------------------------------
# 선택된 라디오는 브랜드 핑크(약 #F4657B)로 채워지고, 미선택은 흰 바탕에
# 회색 테두리다. 원 중심 픽셀의 색으로 구분한다.
def is_pink(rgb, r_min=190, g_max=150, b_max=170):
    r, g, b = rgb
    return r >= r_min and g <= g_max and b <= b_max and (r - g) > 50


def radio_selected(control, dx=17, dy=17, tol=3):
    """커스텀 RadioButton의 선택 여부. 좌측 원의 중심색으로 판정한다.

    판정이 애매하면 None을 반환한다(호출부에서 MANUAL 처리할 것).
    """
    l, t, _, _ = control.rect
    img = grab((l + dx - tol, t + dy - tol, l + dx + tol + 1, t + dy + tol + 1))
    px = img.load()
    hits = sum(1 for y in range(img.height) for x in range(img.width)
               if is_pink(px[x, y]))
    total = img.width * img.height
    if hits >= total * 0.6:
        return True
    if hits == 0:
        return False
    return None
