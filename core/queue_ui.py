# -*- coding: utf-8 -*-
"""DICOM 창 Queue 모드의 Storage 목록 읽기와 Retry 조작. SPEC REQ-QUEUE-001.

컨트롤 ID는 2026-11-22 Bellalun 1.0.12.105에서 `tools/probe_queue_window.py`로
실측했다(`Evidence/ui/probe_queue_window/probe.json`).

| ID | 컨트롤 | 확인 방법 |
|---|---|---|
| 2305 / 2306 | Queue / SCP List 모드 | 화면 문구 |
| 2214 | Storage Queue 목록(ListCtrl) | 왼쪽 목록, 머리글 State·Commitment·Type·Server·Patient Name·Patient ID |
| 2216 / 2217 / 2218 | Storage Select All / Retry / Delete | 툴팁 문구 |

목록 행은 자식 창이 아니라 직접 그린 그림이다. 그래서 행 문구는 OCR로 읽고, 행을 고를 때는
읽은 줄의 세로 위치에서 State 칸을 누른다. Retry 아이콘은 모양으로 추정하지 않고 누르기 전에
툴팁 문구 `Retry`를 확인한다. Delete는 이 모듈에서 누르지 않는다.
"""

from __future__ import annotations

import difflib
import os
import re
import time
from datetime import datetime

from core import flows, screen
from core.ui import children

QUEUE_MODE = 2305
SCP_LIST_MODE = 2306
STORAGE_LIST = 2214
STORAGE_SELECT_ALL = 2216
STORAGE_RETRY = 2217
STORAGE_DELETE = 2218
COUNTER_TEXT = 1001

#: SRS 06-10-10 "전송 상태 (State)로 표시되는 항목" 표의 값.
STATES = ("Pending", "Failed", "Sending", "Stopped", "Done")
TYPES = ("Image", "DSR")
#: 행을 읽을 때 쓰는 이미지 변형. 선택된 행은 배경색이 달라 한 가지 변형으로는 놓칠 수 있다.
ROW_VARIANTS = ("auto", "bin150i", "invert")


class QueueUiError(RuntimeError):
    """Queue 화면을 안전하게 조작할 수 없을 때."""


# --- 문구 해석(화면 없이 시험한다) ---------------------------------------
def _letters(text):
    return re.sub(r"[^a-z]", "", str(text or "").lower())


def parse_state(token):
    """OCR 한 단어를 SRS의 State 값으로 바꾼다. 애매하면 None."""
    word = _letters(token)
    if len(word) < 3:
        return None
    exact = [s for s in STATES if s.lower() == word]
    if exact:
        return exact[0]
    # 좁은 State 칸은 `Sending`을 `Send...`처럼 줄임표로 자른다(2026-11-22 실기
    # `Evidence/ui/queue_retry/step5_01.png`). 줄임표가 있으면 접두사가 하나뿐일 때만 인정한다.
    if re.search(r"(\.\.|…)\s*$", str(token)) and len(word) >= 4:
        prefixed = [s for s in STATES if s.lower().startswith(word)]
        if len(prefixed) == 1:
            return prefixed[0]
    # Pending/Sending처럼 철자가 비슷한 값이 있어 1등과 2등의 차이도 본다.
    scored = sorted(((difflib.SequenceMatcher(None, word, s.lower()).ratio(), s)
                     for s in STATES), reverse=True)
    best, second = scored[0], scored[1]
    if best[0] >= 0.75 and best[0] - second[0] >= 0.1:
        return best[1]
    return None


def compact(text):
    return re.sub(r"[^0-9a-z]", "", str(text or "").lower())


def contains_id(text, wanted, min_prefix=8):
    """좁은 열에서 잘린 Patient ID도 찾는다. 접두사는 min_prefix 글자까지만 줄인다."""
    hay, key = compact(text), compact(wanted)
    if not key:
        return False
    if key in hay:
        return True
    return any(key[:n] in hay for n in range(len(key) - 1, min_prefix - 1, -1))


def parse_row(text):
    """한 줄의 OCR 문구 → {"state", "type", "text"}. 첫 단어가 State 칸이다."""
    words = str(text or "").split()
    state = parse_state(words[0]) if words else None
    kind = next((t for t in TYPES
                 for w in words if _letters(w) == t.lower()), None)
    return {"state": state, "type": kind, "text": str(text or "").strip()}


def merge_reads(reads, tolerance=8):
    """변형별 줄 판독을 세로 위치로 묶고 State를 다수결로 정한다.

    reads: {변형: [{"y": 화면 y, "text": 문구}]}
    반환: 위→아래 순서의 [{"y", "state", "type", "texts", "votes"}]
    State 표가 갈리면 None으로 둔다. 애매한 행을 특정 State로 판정하지 않는다.
    """
    groups = []
    for variant, lines in reads.items():
        for line in lines:
            parsed = parse_row(line["text"])
            group = next((g for g in groups if abs(g["y"] - line["y"]) <= tolerance), None)
            if group is None:
                group = {"y": line["y"], "texts": {}, "votes": [], "types": []}
                groups.append(group)
            group["texts"][variant] = parsed["text"]
            if parsed["state"]:
                group["votes"].append(parsed["state"])
            if parsed["type"]:
                group["types"].append(parsed["type"])
    rows = []
    for g in sorted(groups, key=lambda g: g["y"]):
        votes = sorted(set(g["votes"]))
        rows.append({"y": g["y"], "state": votes[0] if len(votes) == 1 else None,
                     "type": g["types"][0] if len(set(g["types"])) == 1 else None,
                     "texts": g["texts"], "votes": g["votes"]})
    return [r for r in rows if r["votes"] or r["type"]]


def pick_row(rows, patient_id, state=None, kind="Image"):
    """Patient ID가 보이는 행 하나를 고른다. 둘 이상이거나 없으면 None."""
    hits = [r for r in rows
            if any(contains_id(t, patient_id) for t in r["texts"].values())
            and (state is None or r["state"] == state)
            and (kind is None or r["type"] in (kind, None))]
    return hits[0] if len(hits) == 1 else None


# --- 화면 -----------------------------------------------------------------
def _visible(ui, ctrl_id):
    return [c for c in ui.by_id(ctrl_id) if c.visible]


def is_open(ui):
    return bool(_visible(ui, STORAGE_LIST))


def open_queue(ui, timeout=10):
    """DICOM 창을 열고 Queue 모드로 둔다. 이미 열려 있으면 메뉴를 누르지 않는다."""
    if not is_open(ui):
        flows.open_dicom_window(ui)
    end = time.time() + timeout
    while not is_open(ui):
        mode = _visible(ui, QUEUE_MODE)
        if mode:
            ui.click(mode[0], settle=1.0)
        if time.time() >= end:
            raise QueueUiError("DICOM 창의 Storage Queue 목록(2214)이 보이지 않습니다.")
        time.sleep(.5)
    return True


def body_rect(ui):
    """Storage 목록에서 머리글을 뺀 행 영역(ScrollWnd id 3)."""
    lists = _visible(ui, STORAGE_LIST)
    if not lists:
        raise QueueUiError("Storage Queue 목록(2214)을 찾지 못했습니다.")
    inner = [c for c in children(lists[0].hwnd, 4)
             if c.ctrl_id == 3 and c.text == "ScrollWnd" and c.visible]
    if not inner:
        raise QueueUiError("Storage Queue 행 영역을 찾지 못했습니다.")
    return min(inner, key=lambda c: c.rect[1]).rect


def _variant_image(image, name):
    from PIL import ImageOps
    gray = image.convert("L")
    if name == "auto":
        return ImageOps.autocontrast(gray)
    if name == "invert":
        return ImageOps.invert(ImageOps.autocontrast(gray))
    if name == "bin150i":
        return gray.point(lambda v: 0 if v > 150 else 255)
    raise ValueError(name)


def ocr_lines(image, origin, scale=3):
    """이미지의 줄 문구와 화면 기준 세로 중심. pytesseract image_to_data를 쓴다."""
    import pytesseract
    big = image.resize((image.width * scale, image.height * scale))
    data = pytesseract.image_to_data(big, config="--psm 6", lang="eng",
                                     output_type=pytesseract.Output.DICT)
    lines = {}
    for i, word in enumerate(data["text"]):
        if not str(word).strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        top, height, left = data["top"][i], data["height"][i], data["left"][i]
        lines.setdefault(key, []).append((left, word, top + height / 2))
    out = []
    for words in lines.values():
        words.sort()
        y = sum(w[2] for w in words) / len(words)
        out.append({"y": int(origin[1] + y / scale),
                    "text": " ".join(w[1] for w in words)})
    return sorted(out, key=lambda x: x["y"])


def read_rows(ui, evidence_path=None, tesseract_exe=None):
    """보이는 Storage Queue 행을 읽는다. 반환: (rows, raw reads)."""
    from PIL import ImageGrab
    if tesseract_exe:
        screen.configure_ocr(tesseract_exe)
    rect = body_rect(ui)
    shot = ImageGrab.grab(bbox=rect, all_screens=True)
    if evidence_path:
        os.makedirs(os.path.dirname(evidence_path), exist_ok=True)
        shot.save(evidence_path)
    reads = {name: ocr_lines(_variant_image(shot, name), rect)
             for name in ROW_VARIANTS}
    return merge_reads(reads), reads


def read_counters(ui):
    """목록 아래 `Total: n`, `Success: a / Fail: b` 문구(Storage 쪽만)."""
    lists = _visible(ui, STORAGE_LIST)
    if not lists:
        return {}
    l, t, r, b = lists[0].rect
    texts = [c for c in _visible(ui, COUNTER_TEXT)
             if c.rect[1] >= b - 2 and l - 5 <= c.rect[0] <= r]
    out = {}
    for c in texts:
        try:
            out[str(c.rect[0])] = screen.ocr(c.rect, scale=3, psm=7).strip()
        except Exception as exc:                               # noqa: BLE001
            out[str(c.rect[0])] = f"(OCR 실패: {exc})"
    return out


def select_row(ui, row):
    """읽은 행의 State 칸을 눌러 고른다."""
    l, t, r, b = body_rect(ui)
    if not (t <= row["y"] <= b):
        raise QueueUiError(f"행 위치가 목록 밖입니다: y={row['y']}, 목록={l, t, r, b}")
    ui.click((l + 28, row["y"]), settle=.6)


def tooltips(ui):
    """보이는 툴팁 창의 문구. 문구가 비면 OCR로 읽는다."""
    tips = []
    for w in ui.windows():
        if "tooltip" in (w.cls or "").lower() and w.visible:
            text = w.text
            if not text and w.rect[2] - w.rect[0] > 4:
                try:
                    text = screen.ocr(w.rect, scale=3, psm=7).strip()
                except Exception as exc:                       # noqa: BLE001
                    text = f"(OCR 실패: {exc})"
            tips.append({"cls": w.cls, "text": text, "rect": list(w.rect)})
    return tips


def click_retry(ui, attempts=3):
    """Storage Retry 아이콘을 툴팁 `Retry` 확인 뒤 누른다. 반환: 확인한 툴팁."""
    buttons = _visible(ui, STORAGE_RETRY)
    if len(buttons) != 1:
        raise QueueUiError(f"Storage Retry 버튼(2217)이 {len(buttons)}개 보입니다.")
    button = buttons[0]
    seen = []
    for _ in range(attempts):
        ui.hover(button, settle=1.2)
        seen = tooltips(ui)
        if any(_letters(t["text"]) == "retry" for t in seen):
            ui.click(button, settle=.3)
            return {"tooltips": seen, "clicked_at": datetime.now().isoformat(timespec="milliseconds")}
    raise QueueUiError(f"Retry 툴팁을 확인하지 못해 누르지 않았습니다: {seen}")


def close_window(ui):
    """DICOM 창을 닫는다. 열려 있지 않으면 아무것도 누르지 않는다."""
    if not is_open(ui):
        return False
    lists = _visible(ui, STORAGE_LIST)
    top = lists[0].rect[1]
    closes = [c for c in _visible(ui, 4)
              if c.rect[2] - c.rect[0] <= 60 and c.rect[3] - c.rect[1] <= 60
              and c.rect[1] < top]
    if not closes:
        raise QueueUiError("DICOM 창 닫기 버튼(4)을 찾지 못했습니다.")
    ui.click(min(closes, key=lambda c: c.rect[1]), settle=1.5)
    return not is_open(ui)


# --- Viewer 로그(참고 근거) -----------------------------------------------
#
# Retry의 상태 변화와 접속 대상은 Viewer 로그(`Log\Viewer\YYYY_MM_DD.log`, UTF-16)에 남는다.
# 2026-11-22 실기에서 Retry 직후 다음 줄을 확인했다.
#   [DICOM] [Update Queue Storage Item : 13(Pending, -)]
#   [DICOM] [Update Queue Storage Item : 13(Sending, -)]
#   [DICOM] [Storage>      Connecting to 10.13.0.222:11117]
#   [DICOM] [Update Queue Storage Item : 13(Failed, -)]
# `Log\DICOM\..._Storage.log`는 같은 시각에 아무 줄도 쓰지 않아 신호 출처로 쓰지 않는다.
def viewer_log_path(data_dir, when=None):
    when = when or datetime.now()
    return os.path.join(data_dir, "Log", "Viewer", when.strftime("%Y_%m_%d.log"))


def log_mark(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def log_lines_since(path, mark):
    """UTF-16 로그에서 mark 바이트 뒤에 추가된 줄."""
    try:
        with open(path, "rb") as f:
            f.seek(mark - (mark % 2))
            data = f.read()
    except OSError:
        return []
    if mark == 0 and data.startswith(b"\xff\xfe"):
        data = data[2:]
    return data.decode("utf-16-le", errors="replace").splitlines()


def queue_log_events(lines, key):
    """한 Queue 항목의 로그 상태 변화와 그 사이의 Storage 접속 대상.

    반환: {"states": [상태...], "connects": ["host:port", ...], "lines": [근거 줄...]}
    접속 줄에는 Queue Key가 없으므로 이 항목이 Pending/Sending인 동안 나온 줄만 센다.
    """
    state_re = re.compile(rf"Update Queue Storage Item\s*:\s*{int(key)}\((\w+)")
    connect_re = re.compile(r"Storage>\s*Connecting to\s+([0-9A-Za-z_.\-]+:\d+)")
    states, connects, evidence, active = [], [], [], False
    for line in lines:
        match = state_re.search(line)
        if match:
            states.append(match.group(1))
            evidence.append(line.strip())
            active = match.group(1) in ("Pending", "Sending")
            continue
        match = connect_re.search(line)
        if match and active:
            connects.append(match.group(1))
            evidence.append(line.strip())
    return {"states": states, "connects": connects, "lines": evidence}
