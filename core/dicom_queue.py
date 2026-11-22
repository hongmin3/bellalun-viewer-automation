# -*- coding: utf-8 -*-
r"""DICOM 창 Queue 모드 판독과 Retry 조작 (REQ-QUEUE-001).

화면 근거 (2026-11-22, Bellalun 1.0.12.105 Demo 모드 실측 캡처)
  메인 메뉴 DICOM(59) -> DICOM 창. 상단 모드 버튼 Queue(2305) / SCP List(2306).
  Storage 목록 ListCtrl(2214), 열 순서 State / Commitment / Type / Server /
  Patient Name / Patient ID. 목록 위 아이콘은 왼쪽부터 Select All(2216),
  Retry(2217), Delete(2218). Print 목록은 2215, 아이콘은 2219~2221.
  하단 StaticText(1001)에 `Total: N`, `Success: N / Fail: N` 이 보인다.

사양 근거: SRS 06-10-10 Queue List. State 로 표시되는 값은 Pending / Failed /
Sending / Stopped / Done 다섯 가지다.

판정은 화면의 State 문구로 한다. DB(`DATA.DICOM_STORAGE_QUEUE`)는 참고 기록이다.
"""
import difflib
import re
import time

from core import flows, screen

QUEUE_MODE = 2305
SCP_LIST_MODE = 2306
STORAGE_LIST = 2214
STORAGE_SELECT_ALL = 2216
STORAGE_RETRY = 2217
STORAGE_DELETE = 2218
SUMMARY_TEXT = 1001
#: Retry 뒤 시험 행을 이 시간(초) 넘게 연속으로 읽지 못하면 관찰을 끝낸다.
UNREAD_LIMIT = 20

#: SRS 06-10-10 의 전송 상태 표.
QUEUE_STATES = ("Pending", "Failed", "Sending", "Stopped", "Done")

# OCR 이 자주 섞는 글자를 한쪽으로 모은다. Patient ID 비교의 양쪽에 똑같이 적용한다.
_OCR_FOLD = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})


def canonical_id(text):
    """Patient ID 비교용 정규형. 영숫자만 남기고 OCR 혼동 글자를 접는다."""
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper()).translate(_OCR_FOLD)


def parse_state(text):
    """행 OCR 문구에서 State 값을 읽는다. 첫 열이므로 앞쪽 단어만 본다.

    OCR 이 `Faiied` 처럼 한두 글자를 틀려도 다섯 값 중 하나에 충분히 가까우면
    그 값으로 본다. 어느 값에도 가깝지 않으면 None 이다(추측하지 않는다).
    """
    for token in re.findall(r"[A-Za-z]{3,}", str(text or ""))[:3]:
        hit = difflib.get_close_matches(token.capitalize(), QUEUE_STATES, n=1,
                                        cutoff=0.75)
        if hit:
            return hit[0]
        # State 열이 좁아 `Sending` 이 `Send...` 로 잘려 보인다(2026-11-22 실측).
        # 4글자 이상이 정확히 한 값의 앞부분이면 그 값으로 본다.
        prefix = [s for s in QUEUE_STATES
                  if len(token) >= 4 and s.lower().startswith(token.lower())]
        if len(prefix) == 1:
            return prefix[0]
    return None


#: 열 너비 때문에 잘린 Patient ID(`QRETRY_261122_15...`)를 접두어로 비교할 최소 길이.
MIN_TRUNCATED_ID = 8


def _id_matches(token, want):
    truncated = bool(re.search(r"(\.{2,}|…)$", token))
    got = canonical_id(token)
    if not got:
        return False
    if got == want:
        return True
    return truncated and len(got) >= MIN_TRUNCATED_ID and want.startswith(got)


def rows_for_patient(rows, patient_id):
    """화면 행 중 Patient ID 가 일치하는 행만 돌려준다. 다른 행으로 대체하지 않는다.

    Patient ID 열은 마지막 열이라 행 문구의 끝 단어와 비교한다. 열이 좁아 `...` 로
    잘린 경우에만 보이는 앞부분(`MIN_TRUNCATED_ID` 글자 이상)을 접두어로 비교한다
    (2026-11-22 실측: `QRETRY_261122_151933` 이 `QRETRY_261122_15...` 로 표시됨).
    """
    want = canonical_id(patient_id)
    if not want:
        return []
    hits = []
    for row in rows:
        for text in row.get("alts") or [row.get("text")]:
            words = str(text or "").split()
            if words and _id_matches(words[-1], want):
                hits.append(row)
                break
    return hits


def rows_from_ocr_data(data, *, scale=1, left=0, top=0, min_conf=-1):
    """Tesseract `image_to_data` 결과를 화면 좌표의 행 목록으로 묶는다.

    같은 (block, par, line) 의 단어를 한 행으로 잇고, 머리글 줄(State/Commitment)은
    뺀다. 반환: [{"text", "state", "y", "click"}] (y 는 화면 좌표, 위에서 아래 순).
    """
    lines = {}
    for i, word in enumerate(data.get("text", [])):
        word = (word or "").strip()
        if not word:
            continue
        try:
            conf = float(data.get("conf", [0] * len(data["text"]))[i])
        except (TypeError, ValueError):
            conf = 0
        if conf < min_conf:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        entry = lines.setdefault(key, {"words": [], "tops": [], "bottoms": []})
        entry["words"].append((data["left"][i], word))
        entry["tops"].append(data["top"][i])
        entry["bottoms"].append(data["top"][i] + data["height"][i])
    rows = []
    for entry in lines.values():
        text = " ".join(w for _, w in sorted(entry["words"]))
        lowered = text.lower()
        if "commitment" in lowered and "state" in lowered:
            continue
        y = top + (min(entry["tops"]) + max(entry["bottoms"])) / 2 / scale
        rows.append({"text": text, "state": parse_state(text), "y": int(y),
                     "click": (int(left + 30), int(y))})
    return sorted(rows, key=lambda r: r["y"])


def choose_wrong_port(correct_port, is_open, preferred=None, span=40):
    """연결되지 않는 Port 를 고른다.

    `preferred`(설정 파일 `queue_retry.wrong_port`)가 있으면 그 값만 검사한다.
    없으면 올바른 Port 다음 번호부터 `span` 개를 차례로 본다. 열려 있는 Port 는
    다른 SCP 가 받을 수 있으므로 쓰지 않는다. 찾지 못하면 None.
    """
    correct_port = int(correct_port)
    candidates = ([int(preferred)] if preferred else
                  [p for p in range(correct_port + 1, correct_port + 1 + span)
                   if p <= 65535])
    for port in candidates:
        if port != correct_port and not is_open(port):
            return port
    return None


_LOG_LINE = re.compile(r"^\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]")


def retry_log_events(lines, since, queue_key):
    """Viewer 로그에서 Retry 이후 시험 Queue 항목의 상태 변화와 연결 대상을 뽑는다.

    로그 형식 (2026-11-22 실측, `<data_dir>/Log/Viewer/YYYY_MM_DD.log`):
      [2026/11/22 15:31:04.922] ... [Update Queue Storage Item : 2(Pending, -)]
      [2026/11/22 15:31:04.934] ... [Storage>      Connecting to 10.13.0.222:11117]
    `since` 는 같은 형식의 시각 문자열("2026/11/22 15:31:04.000")이다.
    반환: {"states": [...], "connect": ["host:port", ...], "lines": [...]}
    참고 기록이다. 판정은 화면 State 로 한다.
    """
    key = int(queue_key)
    state_re = re.compile(rf"Queue Storage Item : {key}\((\w+)")
    connect_re = re.compile(r"Storage>\s+Connecting to ([\w.\-]+:\d+)")
    out = {"states": [], "connect": [], "lines": []}
    for line in lines:
        m = _LOG_LINE.match(line)
        if not m or m.group(1) < since:
            continue
        state = state_re.search(line)
        connect = connect_re.search(line)
        if state:
            out["states"].append(state.group(1))
        elif connect:
            out["connect"].append(connect.group(1))
        else:
            continue
        out["lines"].append(" ".join(line.split()))
    return out


def read_viewer_log_tail(data_dir, day, max_bytes=8_000_000):
    """그날 Viewer 로그의 끝부분을 줄 목록으로 읽는다. 없으면 [].

    Viewer 로그는 UTF-16LE 로 기록된다(2026-11-22 실측: 첫 판독을 UTF-8 로 해
    줄은 읽혔지만 글자 사이에 NUL 이 끼어 아무것도 일치하지 않았다). 파일 앞의
    BOM 또는 NUL 비율로 인코딩을 고르고, UTF-16 이면 짝수 위치부터 읽는다.
    """
    import os
    path = os.path.join(str(data_dir), "Log", "Viewer", f"{day:%Y_%m_%d}.log")
    if not os.path.exists(path):
        return []
    with open(path, "rb") as handle:
        head = handle.read(4096)
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        start = max(0, size - max_bytes)
        utf16 = head.startswith(b"\xff\xfe") or head.count(b"\x00") > len(head) // 4
        if utf16:
            start -= start % 2
        handle.seek(start)
        data = handle.read()
    return decode_log(data, utf16)


def decode_log(data, utf16):
    """로그 바이트를 줄 목록으로 바꾼다. BOM 과 NUL 은 지운다."""
    text = data.decode("utf-16-le" if utf16 else "utf-8", "replace")
    return [line.replace("\ufeff", "").replace("\x00", "") for line in text.splitlines()]


def evaluate_retry(states_after, final_state, db_before=None, db_after=None,
                   log_states=None):
    """Retry 결과를 판정한다. 반환: (판정 문자열, 설명).

    판정 문자열은 "pass" / "done" / "no_signal" / "unread" / "other".
      - pass      : 최종 Failed 이고 재전송 신호가 있다(사양대로 등록 당시 정보로 재전송).
      - done      : 최종 Done. 바뀐 Storage 설정으로 보냈다는 뜻이라 사양과 다르다.
      - no_signal : 최종 Failed 지만 화면 중간 상태도 DB 행 변화도 없다.
      - unread    : 최종 State 를 읽지 못했다.
      - other     : 그 밖의 최종 State(Pending/Sending/Stopped 에서 멈춤).
    화면 중간 상태(Failed 가 아닌 값)를 1차 신호로, 제품 로그의 상태 변화와 DB 행
    변화를 보조 신호로 쓴다. 최종 판정 값은 언제나 화면의 최종 State 다.
    """
    if final_state is None:
        return "unread", "Retry 후 시험 행의 State 를 화면에서 읽지 못했다"
    if final_state == "Done":
        return "done", "Retry 후 Done: 바뀐 Storage 설정으로 전송된 것으로 보인다"
    if final_state != "Failed":
        return "other", f"Retry 후 State 가 {final_state} 에서 끝나지 않았다"
    transitions = [s for s in states_after if s and s != "Failed"]
    db_changed = (db_before is not None and db_after is not None
                  and db_before != db_after)
    log_moves = [s for s in (log_states or []) if s and s != "Failed"]
    if transitions or db_changed or log_moves:
        signal = []
        if transitions:
            signal.append(f"화면 중간 상태 {sorted(set(transitions))}")
        if log_moves:
            signal.append(f"제품 로그 상태 변화 {log_moves}(참고)")
        if db_changed:
            signal.append("DB Queue 행 변화(참고)")
        return "pass", "재전송 신호: " + ", ".join(signal)
    return "no_signal", ("Retry 를 눌렀지만 재전송 신호(화면 중간 상태, 제품 로그, "
                         "DB 행 변화)가 없다")


# --- UI -------------------------------------------------------------------

def _visible(ui, ctrl_id):
    return [c for c in ui.by_id(ctrl_id) if c.visible]


def is_open(ui):
    return bool(_visible(ui, STORAGE_LIST))


def open_queue(ui, wait=3.0):
    """DICOM 창을 열고 Queue 모드로 둔다. Storage 목록이 보이면 True."""
    if not is_open(ui):
        flows.open_dicom_window(ui, wait=wait)
    mode = _visible(ui, QUEUE_MODE)
    if mode:
        ui.click(mode[0], settle=1.0)
    end = time.time() + 10
    while time.time() < end:
        if is_open(ui):
            return True
        time.sleep(.5)
    return False


def close_window(ui):
    """DICOM 창의 오른쪽 위 닫기(4)를 누른다. 닫혔으면 True."""
    if not is_open(ui):
        return True
    closes = [c for c in ui.by_id(4) if c.visible
              and c.rect[2] - c.rect[0] <= 60 and c.rect[3] - c.rect[1] <= 60]
    if closes:
        ui.click(min(closes, key=lambda c: c.rect[1]), settle=2)
    end = time.time() + 8
    while time.time() < end and is_open(ui):
        time.sleep(.5)
    return not is_open(ui)


def read_storage_rows(ui, evidence_path=None, scale=3):
    """Storage 목록을 줄 단위로 OCR 해 [{text, state, y, click}] 로 돌려준다.

    목록 전체를 한 번 캡처해 Tesseract 단어 좌표로 행을 나눈다. 처음 구현은
    목록의 ListItem 자식 영역을 행마다 OCR 했는데, 2026-11-22 실측에서 화면에
    `Failed ... QRETRY_...` 행이 보이는데도 State 를 읽지 못했다(ListItem 영역이
    보이는 행과 일치하지 않았다). 같은 캡처 줄을 OCR 하면 정상으로 읽힌다.
    `click` 은 그 행의 State 칸 좌표다(목록 왼쪽 + 30, 행 가운데).
    """
    import pytesseract
    from PIL import ImageOps

    lists = _visible(ui, STORAGE_LIST)
    if not lists:
        raise RuntimeError(f"Queue Storage 목록({STORAGE_LIST})이 보이지 않습니다.")
    l, t, r, b = lists[0].rect
    image = screen.grab((l, t, r, b), path=evidence_path)
    pytesseract.pytesseract.tesseract_cmd = screen.TESSERACT_EXE
    gray = image.convert("L")
    variants = (ImageOps.autocontrast(gray),
                gray.point(lambda v: 255 if v > ROW_BINARY_THRESHOLD else 0))
    found = []
    for variant in variants:
        data = pytesseract.image_to_data(
            variant.resize((image.width * scale, image.height * scale)),
            lang="eng", config="--psm 6", output_type=pytesseract.Output.DICT)
        found.append(rows_from_ocr_data(data, scale=scale, left=l, top=t))
    return merge_rows(*found)


#: 선택된 행은 배경이 어두워져 autocontrast 전처리에서 글자가 사라진다(2026-11-22
#: 실측: Retry 를 위해 선택한 `QR22152904` 행이 판독 결과에서 통째로 빠짐).
#: 이 값으로 이진화한 판독을 함께 쓴다. 같은 캡처에서 두 행 모두 읽혔다.
ROW_BINARY_THRESHOLD = 140


def merge_rows(*row_lists, tolerance=8):
    """전처리별 판독 행을 화면 높이(y)로 묶어 한 행에 하나씩 남긴다.

    같은 높이 후보의 문구는 모두 `alts` 에 보존한다. 대표 문구는 State 를 읽은 후보 중
    먼저 넘긴 전처리(autocontrast)의 것이다. 문구 길이로 고르지 않는다 — 2026-11-22
    3회차에서 이진화 판독의 잡음 문구(`QOR22153835`)가 더 길어 대표로 뽑혀 시험 행을
    놓쳤다. 한 전처리에만 보이는 행(선택된 행)도 버리지 않는다.
    """
    merged = []
    candidates = [r for rows in row_lists for r in rows]
    for row in sorted(candidates, key=lambda r: r["y"]):
        same = next((m for m in merged if abs(m["y"] - row["y"]) <= tolerance), None)
        if same is None:
            merged.append(dict(row, alts=[row["text"]]))
            continue
        same["alts"].append(row["text"])
        if same["state"] is None and row["state"] is not None:
            same.update(text=row["text"], state=row["state"])
    return merged


def summary(ui):
    """하단 `Total` / `Success / Fail` 문구(OCR). 참고 기록용."""
    lists = _visible(ui, STORAGE_LIST)
    if not lists:
        return None
    l, _, r, b = lists[0].rect
    return " ".join(screen.ocr((l, b, r, b + 34), scale=3, psm=6).split())


def patient_row(ui, patient_id, evidence_path=None):
    """시험 Patient ID 행 하나를 찾는다. (행 또는 None, 전체 행 목록)."""
    rows = read_storage_rows(ui, evidence_path=evidence_path)
    hits = rows_for_patient(rows, patient_id)
    return (hits[0] if len(hits) == 1 else None), rows


def wait_patient_state(ui, patient_id, wanted, timeout=180, poll=2.0,
                       reopen_every=30):
    """시험 행의 State 가 `wanted` 중 하나가 될 때까지 화면을 읽는다.

    목록이 스스로 갱신되지 않는 경우에 대비해 `reopen_every` 초마다 창을 닫고
    다시 연다. 반환: {"state", "row_text", "seen": [...], "rows": n}
    """
    seen, row, rows = [], None, []
    end = time.time() + timeout
    last_reopen = time.time()
    while True:
        if not is_open(ui):
            open_queue(ui)
        row, rows = patient_row(ui, patient_id)
        state = row["state"] if row else None
        if not seen or seen[-1] != state:
            seen.append(state)
        if state in wanted or time.time() >= end:
            return {"state": state, "row_text": row["text"] if row else None,
                    "seen": seen, "rows": len(rows)}
        if time.time() - last_reopen >= reopen_every:
            close_window(ui)
            open_queue(ui)
            last_reopen = time.time()
        time.sleep(poll)


def retry_patient_row(ui, patient_id, watch=120, poll=0.4):
    """시험 행을 선택하고 Retry(2217)를 누른 뒤 State 변화를 기록한다.

    Retry 직후에는 짧게(`poll`) 읽어 Pending/Sending 같은 중간 상태를 놓치지
    않게 한다. 중간 상태가 끝나 Failed/Done 으로 다시 멈추거나 `watch` 초가 지나면
    끝낸다. 반환: {"clicked", "before", "states", "final", "row_text"}
    """
    row, rows = patient_row(ui, patient_id)
    if row is None:
        return {"clicked": False, "before": None, "states": [], "final": None,
                "row_text": None, "rows": [r["text"] for r in rows]}
    ui.click(row["click"], settle=.6)
    buttons = _visible(ui, STORAGE_RETRY)
    if not buttons:
        raise RuntimeError(f"Retry 버튼({STORAGE_RETRY})이 보이지 않습니다.")
    before = row["state"]
    ui.click(buttons[0], settle=.2)
    states, final, text = [], None, row["text"]
    left_failed = False
    started = time.time()
    last_read = started
    end = started + watch
    while time.time() < end:
        hit, _ = patient_row(ui, patient_id)
        state = hit["state"] if hit else None
        text = hit["text"] if hit else text
        states.append(state)
        if state is None:
            # 계속 읽지 못하면 끝까지 기다리지 않는다. final 은 마지막으로 읽은 값이다.
            if time.time() - last_read > UNREAD_LIMIT:
                break
            time.sleep(poll)
            continue
        last_read = time.time()
        if state != "Failed":
            left_failed = True
        final = state
        # 중간 상태를 본 뒤 다시 멈췄거나, 바로 Done 이 되면 끝낸다.
        if state == "Done" or (left_failed and state == "Failed"):
            break
        # 중간 상태를 못 봤어도 10초 넘게 Failed 그대로면 더 기다릴 근거가 없다.
        if not left_failed and state == "Failed" and time.time() > started + 10:
            break
        time.sleep(poll)
    return {"clicked": True, "before": before, "states": states, "final": final,
            "row_text": text}
