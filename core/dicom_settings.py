# -*- coding: utf-8 -*-
"""Setting > DICOM 서버 등록 자동화.

UI 조작뿐 아니라 CONFIGURATION DB, TCP 연결, Viewer C-ECHO 결과를 함께
검증한다. 기존 서버는 삭제하지 않으며 MWL/Storage는 등록 대상 서버만
Use=1 단일 활성으로 정리한다(DICOM_PRINT에는 [Use] 컬럼이 없어 Print는
대상이 아니다). 신규 PC는 MWL/Storage가 기본 Use=0으로 남아 있어,
활성화하지 않으면 이후 WF01의 MWL 등록 등이 막힌다.
"""
import os
import socket
import time

from core import flows
from core.result import TCResult, PASS, FAIL
from core.ui import children

PAGE = {"MWL": "mwl", "Storage": "storage", "Print": "print"}


def ensure_storage_reachable(cfg):
    """Storage SCP 가 전송을 받을 수 있는 상태인지 확인한다.

    2026-08-26 Bunny(로컬 애플리케이션)를 원격 Storage SCP 웹 서버로 바꿨다.
    **우리가 띄울 것이 없다** — 그래서 '기동' 이 아니라 **'도달 가능'** 을 본다.

    두 가지를 함께 본다. 하나만 보면 조용히 틀린다.
      - HTTP API `/api/scp-status` 의 `running` — 웹은 살아 있는데 SCP 가 안 떠
        있는 경우를 걸러낸다.
      - DICOM 포트 TCP 연결 — API 가 running 이라고 해도 방화벽에 막히면
        전송은 실패한다.

    반환: `(가능한가, 상세)`. 상세는 판정 `actual` 에 그대로 실을 수 있다.
    """
    spec = (cfg.get("dicom") or {}).get("storage_scp") or {}
    host = spec.get("host")
    port = int(spec.get("port") or 0)
    detail = {"ae_title": spec.get("ae_title"), "host": host, "port": port}

    api_url = spec.get("api_url")
    if api_url:
        try:
            from core.storagescp import StorageServer
            status = StorageServer(api_url, timeout=15).status() or {}
            detail["api"] = {k: status.get(k) for k in
                             ("ae_title", "host", "port", "running", "tls_running")}
            detail["api_running"] = bool(status.get("running"))
            # 서버가 말하는 AE/Port 가 우리가 등록할 값과 같은지도 본다.
            if status.get("ae_title") and spec.get("ae_title"):
                detail["ae_matches"] = (status["ae_title"] == spec["ae_title"])
            if status.get("port") and port:
                detail["port_matches"] = (int(status["port"]) == port)
        except Exception as exc:
            detail["api_error"] = str(exc)[:140]
            detail["api_running"] = False
    else:
        detail["api_running"] = None      # API 주소가 없으면 TCP 만으로 판단

    detail["tcp_open"] = bool(host and port and tcp_open(host, port))
    ok = detail["tcp_open"] and detail.get("api_running") is not False
    return ok, detail


def tcp_open(host, port, timeout=2):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _open_page(ui, kind):
    # Setting 창이 열려 있으면 그룹/페이지를 직접 사용한다.
    group = [c for c in ui.by_id(183) if c.visible]
    if group:
        ui.click(group[0], settle=.7)
        ui.click([c for c in ui.by_id(flows.SETTING_DICOM_PAGES[PAGE[kind]]) if c.visible][0], settle=1)
        time.sleep(2)
    else:
        flows.open_dicom_setting(ui, PAGE[kind], wait=2)


def _server_items(ui):
    win = ui.main_window()
    if not win:
        return []
    l, t, r, b = win.rect
    width, height = r - l, b - t
    return [c for c in ui.controls(max_depth=8) if c.text == "ListItem" and c.visible
            and c.rect[0] < l + width * .40
            and c.rect[1] < t + height * .55]


def _select_name(ui, item):
    ui.click(item, settle=.3)
    return ui.get_text([c for c in ui.by_id(2434) if c.visible][0])


def _set_server(ui, spec):
    items = _server_items(ui)
    target = next((x for x in items if _select_name(ui, x) == spec["name"]), None)
    created = target is None
    if target is None:
        ui.click([c for c in ui.by_id(2431) if c.visible][0], settle=.5)
        target = _server_items(ui)[-1]
    ui.click(target, settle=.3)
    # Name/AE Title은 EN_CHANGE 알림이 필요하고, IP/Port 숫자 필드는
    # 유니코드 SendInput을 거부하므로 각각 검증된 입력 경로를 쓴다.
    controls = {cid: [c for c in ui.by_id(cid) if c.visible][0]
                for cid in (2434, 2435, 2436, 2437)}
    wanted = {2434: spec["name"], 2435: spec["ae_title"],
              2436: spec["ip"], 2437: str(spec["port"])}
    changed = created
    for cid in (2434, 2435, 2436, 2437):
        control, value = controls[cid], str(wanted[cid])
        if ui.get_text(control) == value:
            continue
        changed = True
        if cid in (2434, 2435):
            ui.type_text(control, value)
        else:
            # IP/Port 편집기는 유니코드 SendInput을 거부할 수 있다. WM_SETTEXT 후
            # 다른 필드로 포커스를 옮겨 EN_KILLFOCUS 검증/commit을 각각 발생시킨다.
            ui.set_text(control, value)
            ui.click(controls[2437 if cid == 2436 else 2434], settle=.3)
        if ui.get_text(control) != value:
            raise RuntimeError(
                f"DICOM field {cid} 입력 검증 실패: "
                f"expected={value!r}, actual={ui.get_text(control)!r}")
    return target, changed, created


def _ensure_storage_options(ui):
    """Burn 3개, Image option을 체크하고 Dose SR을 Send로 맞춘다."""
    from core import screen
    changed, states = False, {}
    for cid, label in ((2455, "Annotation"), (2456, "Label"),
                       (2457, "Information"), (2458, "Apply preview position")):
        hits = [c for c in ui.by_id(cid) if c.visible]
        if not hits:
            raise RuntimeError(f"Storage option {label}(ID {cid})을 찾지 못했습니다")
        selected = screen.radio_selected(hits[0])
        if selected is not True:
            ui.click(hits[0], settle=.3)
            changed = True
            selected = screen.radio_selected(hits[0])
        if selected is not True:
            raise RuntimeError(f"Storage option {label} 체크 검증 실패: {selected}")
        states[label] = True

    combo = [c for c in ui.by_id(2461) if c.visible]
    if not combo:
        raise RuntimeError("Dose SR combo(ID 2461)를 찾지 못했습니다")
    if ui.combo_value(combo[0]).strip().lower() != "send":
        l, t, rr, bb = combo[0].rect
        ui.click((rr - 12, (t + bb) // 2), settle=.4)
        # 실측 목록: 위 ID 1=Not Send, 아래 ID 2=Send.
        send = [c for c in ui.by_id(2) if c.visible and c.text == "TextButton"
                and c.rect[0] >= l - 5 and c.rect[0] <= rr + 5
                and c.rect[1] >= bb]
        if not send:
            raise RuntimeError("Dose SR 목록의 Send 항목을 찾지 못했습니다")
        ui.click(sorted(send, key=lambda c: c.rect[1])[-1], settle=.5)
        changed = True
    states["Dose SR"] = ui.combo_value(combo[0])
    if states["Dose SR"].strip().lower() != "send":
        raise RuntimeError(f"Dose SR Send 설정 검증 실패: {states['Dose SR']}")
    return changed, states


def _ensure_storage_transfer_syntax_control(ui, tesseract_exe=None):
    """현재 선택된 Storage 행의 Transfer Syntax를 Implicit VR LE로 맞춘다.

    서버 등록 단계에서 다른 Storage 옵션과 **같은 Update**로 저장한다. 그러면
    뒤따르는 Send TC 들은 이 값이 이미 맞아 Setting 화면을 아예 열지 않는다
    (`ensure_storage_transfer_syntax` 가 조기 반환) — 위험한 UI 조작 횟수를 줄인다.

    **항목은 문구를 OCR로 읽어 고른다.** 2026-08-21까지는 팝업 rect에서
    `(가운데, top+17)` 좌표를 눌러 "첫 항목"을 골랐다. 항목 높이와 팝업 여백을
    가정한 절대 좌표라 AGENTS.md 5절 위반이고, 빗나가면 팝업 뒤의 컨트롤을 누를 수
    있다. 그래서 `uitext.pick_combo_by_text` 로 바꿔 **실제 항목 컨트롤**을 누른다.
    원하는 문구가 없으면 아무것도 누르지 않고 실패한다.

    (참고: 이 좌표 클릭이 `DICOM_STORAGE` 중복 행의 원인이라고 한때 판단했지만
    **틀렸다.** 실제 원인은 제품이 전송 작업마다 만드는 사본 행이었고 —
    `STORAGE_SCP_USE_TYPE` 주석 참고 — 여기 변경은 그와 무관한 별개의 개선이다.)

    반환: 값을 바꿨으면 True, 이미 선언값이면 False.
    """
    from core import uitext

    combo = [c for c in ui.by_id(STORAGE_TRANSFER_SYNTAX) if c.visible]
    if not combo:
        raise RuntimeError(
            f"Transfer Syntax 콤보({STORAGE_TRANSFER_SYNTAX})를 찾지 못했습니다.")
    current = uitext.norm(ui.combo_value(combo[0]))
    if current and current == uitext.norm(TRANSFER_SYNTAX_LABEL):
        return False
    uitext.pick_combo_by_text(
        ui, STORAGE_TRANSFER_SYNTAX, TRANSFER_SYNTAX_LABEL,
        tesseract_exe=tesseract_exe, what="Storage Transfer Syntax",
        settle=.8)
    return True


def active_storage_rows(db):
    """**설정된** 활성 Storage 행(Key 순).

    `SCPUseType=0` 만 센다 — 전송 작업 사본 행(`SCPUseType=1`)은 설정 항목이 아니다
    (`STORAGE_SCP_USE_TYPE` 주석의 실측 근거 참고).
    """
    return db.query(
        "CONFIGURATION",
        "SELECT [Key],Name,AETitle,IP,Port,[Use],TransferSyntax,SCPUseType "
        "FROM DICOM_STORAGE WHERE [Use]=1 AND SCPUseType=@t ORDER BY [Key]",
        {"t": STORAGE_SCP_USE_TYPE})


def storage_job_copies(db):
    """전송 작업 사본 행(`SCPUseType<>0`). **판정 대상이 아니라 관측용**이다.

    전제 판정의 `actual` 에 함께 실어 "왜 DB 에 같은 이름이 여러 행인가"를 리포트만
    보고 알 수 있게 한다. 근거를 남기지 않으면 다음 사람이 다시 상태 누수로 오진한다.
    """
    return db.query(
        "CONFIGURATION",
        "SELECT [Key],Name,[Use],SCPUseType FROM DICOM_STORAGE "
        "WHERE SCPUseType<>@t ORDER BY [Key]", {"t": STORAGE_SCP_USE_TYPE})


def _close_setting_window(ui):
    """Setting 창을 닫는다(`tests/workflow08.py::_close_setting` 과 같은 선택자).

    복구 경로에서만 쓴다. `ensure_storage_transfer_syntax` 의 정상 경로는
    호출부가 곧바로 `cold_start(force_restart=True)` 로 Viewer 를 다시 띄우므로
    남은 창이 문제가 되지 않지만, `WF_15` 처럼 같은 세션에서 곧바로 Examined 를
    여는 TC 는 열린 Setting 창 때문에 메인 메뉴를 못 찾을 수 있다.
    """
    try:
        closes = [c for c in ui.by_id(4) if c.visible
                  and c.rect[2] - c.rect[0] <= 60 and c.rect[3] - c.rect[1] <= 60]
        if closes:
            ui.click(min(closes, key=lambda c: c.rect[1]), settle=3)
            return True
    except Exception:                                          # noqa: BLE001
        pass
    return False


def repair_storage_use(ctx, ui, target_name, timeout=10):
    """활성 Storage가 여럿이면 **UI로** 하나만 남긴다.

    왜 필요한가: 이 저장소의 Send 판정은 "수신 객체가 정확히 N건"을 쓴다.
    `Use=1`인 Storage가 둘 이상이면 같은 영상이 여러 SCP로 나가 그 판정이 조용히
    틀린다. 그래서 전제 판정이 먼저 그것을 드러내는데, 드러내는 것만으로는 회귀가
    그 지점부터 진행되지 않는다. 여기서 **상태를 복구한 뒤 다시 확인**한다.

    왜 이름이 아니라 **행 순서**로 맞추는가: `_sync_use`는 `{Name: Use}` 사전을
    쓰므로 같은 이름이 여러 행이면 서로를 구분하지 못한다(2026-08-21 확인 —
    그래서 `setup-dicom`이 중복을 정리하지 못했다). UI 목록 순서와 `Key` 순서가
    같다는 것에 의존하되, **결과를 DB로 다시 확인**하고 못 맞추면 실패로 남긴다.

    `core/db.py`는 조회 전용이다 — 상태 변경은 전부 UI 클릭으로 한다.

    반환: {"needed": bool, "ok": bool, "before": [...], "after": [...],
           "clicked": [행 index...], "error": str|None}
    """
    before = active_storage_rows(ctx.db)
    out = {"needed": len(before) > 1, "ok": len(before) == 1,
           "before": [dict(x) for x in before], "after": [dict(x) for x in before],
           "clicked": [], "error": None}
    if len(before) <= 1:
        return out

    try:
        flows.open_dicom_setting(ui, "storage", wait=3)
    except Exception as exc:                                   # noqa: BLE001
        out["error"] = f"Storage 설정 화면을 열지 못했습니다: {exc}"
        return out

    # UI 목록과 짝지을 대상은 **설정 행만**이다. 전송 작업 사본(`SCPUseType<>0`)은
    # 어느 설정 화면에도 나오지 않으므로 포함하면 행 수가 어긋난다.
    all_rows = ctx.db.query(
        "CONFIGURATION",
        "SELECT [Key],Name,[Use] FROM DICOM_STORAGE WHERE SCPUseType=@t "
        "ORDER BY [Key]", {"t": STORAGE_SCP_USE_TYPE})
    items = _server_items(ui)
    if len(items) != len(all_rows):
        out["error"] = (f"UI 목록 {len(items)}행과 DB {len(all_rows)}행이 달라 "
                        "행을 짝지을 수 없습니다. 자동 복구를 하지 않습니다.")
        return out

    # 남길 행: 대상 이름과 같은 행 중 **Key 가 가장 작은 것**. 판정에서 쓰는
    # `_stored_transfer_syntax` 가 `ORDER BY [Key]` 의 첫 행을 보기 때문이다.
    keep = next((i for i, row in enumerate(all_rows)
                 if str(row.get("Name")) == str(target_name)), None)
    if keep is None:
        out["error"] = f"대상 Storage {target_name!r} 행이 DB 에 없습니다."
        return out

    for index, (item, row) in enumerate(zip(items, all_rows)):
        want = 1 if index == keep else 0
        if int(row.get("Use") or 0) == want:
            continue
        checkbox = children(item.hwnd, 1)
        if not checkbox:
            out["error"] = f"{index}번째 행의 Use 체크박스를 찾지 못했습니다."
            return out
        ui.click(checkbox[0], settle=.4)
        out["clicked"].append({"index": index, "key": row.get("Key"),
                               "from": int(row.get("Use") or 0), "to": want})
    if not out["clicked"]:
        out["error"] = ("활성 행이 둘 이상인데 되돌릴 체크박스를 찾지 못했습니다"
                        "(UI 목록과 DB 상태 불일치).")
        return out

    _update(ui)
    end = time.time() + timeout
    while True:
        after = active_storage_rows(ctx.db)
        out["after"] = [dict(x) for x in after]
        if len(after) == 1 and str(after[0].get("Name")) == str(target_name):
            out["ok"] = True
            break
        if time.time() >= end:
            out["error"] = ("Use 정리 후에도 활성 Storage 가 "
                            f"{len(after)}행입니다.")
            break
        time.sleep(1)
    out["setting_closed"] = _close_setting_window(ui)
    return out


def _sync_use(ui, db, kind, target_name):
    table = {"MWL": "DICOM_MWL", "Storage": "DICOM_STORAGE", "Print": "DICOM_PRINT"}[kind]
    rows = db.query("CONFIGURATION", f"SELECT Name,[Use] FROM {table}")
    state = {str(x.get("Name")): int(x.get("Use") or 0) for x in rows}
    changed = False
    for item in _server_items(ui):
        name = _select_name(ui, item)
        want = name == target_name
        if bool(state.get(name, 0)) != want:
            ch = children(item.hwnd, 1)
            if ch:
                ui.click(ch[0], settle=.3)
                changed = True
    return changed


def _echo(ui, evidence_path=None):
    from core import screen
    ui.click([c for c in ui.by_id(2433) if c.visible][0], settle=.5)
    deadline = time.monotonic() + 15
    rows = []
    while time.monotonic() < deadline:
        win = ui.main_window()
        if not win:
            time.sleep(.25)
            continue
        l, t, r, b = win.rect
        split_y = t + (b - t) * .55
        seen = set()
        rows = []
        for c in ui.controls(max_depth=9):
            if (c.text == "ListItem" and c.visible and c.hwnd not in seen
                    and c.rect[0] < l + (r - l) * .55 and c.rect[1] >= split_y):
                seen.add(c.hwnd)
                rows.append(c)
        if len(rows) >= 6:
            break
        time.sleep(.25)
    win = ui.main_window()
    if not win:
        return False, 0, "Viewer window 없음", None
    l, t, r, b = win.rect
    split_y = t + (b - t) * .55
    box = (int(l + (r - l) * .20), int(split_y),
           int(l + (r - l) * .56), int(t + (b - t) * .84))
    ocr_text = screen.ocr(box, scale=3, psm=6, path=evidence_path)
    normalized = " ".join(ocr_text.lower().split())
    fail_seen = "connected fail" in normalized
    # 성공 시 association 단계가 6행 이상, 실패 시 실측상 1행이다.
    return len(rows) >= 6 and not fail_seen, len(rows), ocr_text, evidence_path


def _update(ui):
    ui.click([c for c in ui.by_id(2226) if c.visible][0], settle=1)
    time.sleep(2)
    ok = [c for c in ui.by_id(500) if c.visible]
    if ok:
        ui.click(ok[0], settle=.5)


def _saved_rows(db, kind, spec):
    """서버 종류별 실제 저장 필드를 같은 형태로 조회한다."""
    params = {"name": spec["name"]}
    if kind == "Print":
        return db.query(
            "CONFIGURATION",
            "SELECT p.[Key],p.Name,p.AETitle,d.IP,d.Port "
            "FROM DICOM_PRINT p LEFT JOIN DICOM_PRINT_DICOM d "
            "ON d.PrintKey=p.[Key] WHERE p.Name=@name", params)
    table = {"MWL": "DICOM_MWL", "Storage": "DICOM_STORAGE"}[kind]
    extra = (",BurnAnno,BurnLabel,BurnInfo,ApplyPreviewPosition,SendDoseSR,TransferSyntax"
             if kind == "Storage" else "")
    return db.query(
        "CONFIGURATION",
        f"SELECT [Key],Name,AETitle,IP,Port,[Use]{extra} "
        f"FROM {table} WHERE Name=@name",
        params)


def _exact_saved(rows, spec):
    return any(
        str(row.get("Name")) == str(spec["name"])
        and str(row.get("AETitle")) == str(spec["ae_title"])
        and str(row.get("IP")) == str(spec["ip"])
        and int(row.get("Port") or 0) == int(spec["port"])
        for row in rows)


# --- Storage Transfer Syntax ------------------------------------------------
#
# 제품 기본값은 JPEG 2000 Lossless(`1.2.840.10008.1.2.4.90`)이고, conformant SCP는
# 이 Presentation Context를 거절한다(2026-08-18 Bunny 로그 실측:
#   Abstract Syntax 1.2.840.10008.5.1.4.1.1.1.2 / Transfer Syntax
#   1.2.840.10008.1.2.4.90 -> `Presentation Context ID: 1 - Rejected`).
# DICOM Conformance Statement V1.3W1 "Proposed Presentation Context Table"이
# 네트워크 Storage SCU에 선언한 값은 Implicit VR LE와 Explicit VR LE 뿐이므로,
# 여기서 맞추는 것은 우회가 아니라 **선언된 conformance로 되돌리는 것**이다.
#
# WF04(Overlay)와 WF05(Send)가 같이 쓴다. WF04에 이 전제가 없어서 회귀에서 매번
# 수신 0건으로 FAIL했다(DB를 기준 복원하면 설정이 제품 기본값으로 돌아간다).
#
# **호출 시점 주의**: 이 함수는 Setting 화면을 드나든다. 검사를 연 상태에서 부르면
# Examine 화면의 영상 선택이 풀려 Send 버튼이 비활성이 되고, 전송 범위 대화상자가
# 아예 뜨지 않는다(2026-08-18 회귀에서 WF05 Step 2/5가 이렇게 실패했다).
# **반드시 검사를 열기 전(Patient 화면)에 호출한다.**
STORAGE_TRANSFER_SYNTAX = 2459
TRANSFER_SYNTAX_IMPLICIT = 0
#: 화면 항목 문구. Service Manual "Setting > DICOM > Storage > Option" 표가
#  선택지를 `Implicit VR Little Endian` / `Explicit VR Little Endian` /
#  `JPEG2000 Lossless` 세 개로 정한다. 순서(인덱스)로 고르지 않고 이 문구를
#  OCR 로 읽어 고른다 — 콤보 순서와 DB 값이 일치한다고 가정하지 않는다는
#  이 저장소의 규칙(AGENTS.md 3절)이다.
TRANSFER_SYNTAX_LABEL = "Implicit VR Little Endian"


# --- `DICOM_STORAGE.SCPUseType` -------------------------------------------
#
# **이 컬럼을 걸러야 한다.** 2026-08-21 에 확정한 실측이다.
#
# 증상: 전체 회귀에서 `WF_04`(2D Send) 뒤 `DICOM_STORAGE` 에 같은 서버
# (`BUNNY_TEST`)가 새 Key 로 늘어나고 둘 다 `Use=1` 이 됐다. "활성 Storage SCP 가
# 하나" 전제가 FAIL 해 `WF_05`/`WF_06`/`WF_15` 가 전제에서 멈췄다.
#
# 처음에는 자동화의 상태 누수로 판단했지만 **아니었다.** 세 가지를 실측했다.
#
#   1. `DATA.DICOM_STORAGE_QUEUE` 의 전송 작업 행이
#      `OriginalStorageKey=17`(SCPUseType=0) / `StorageKey=18`(SCPUseType=1) 이다.
#      즉 제품이 전송을 큐에 넣을 때 **그 시점의 Storage 설정을 작업용 사본 행으로
#      복제**하고, 원본을 `OriginalStorageKey` 로 가리킨다. 사용자가 나중에 서버
#      설정을 바꿔도 진행 중인 작업이 자기 설정을 유지하게 하는 구조다.
#   2. `Setting > DICOM > Storage` 의 SCP List 는 **`SCPUseType=0` 행만** 보여 준다
#      (DB 2행 / UI 1행. 자동 복구가 "UI 목록 1행과 DB 2행이 달라 짝지을 수 없다"고
#      스스로 멈춘 것이 이 사실을 드러냈다).
#   3. `Storage Group` / `Storage Commitment` / `Query/Retrieve` / `MPPS` 페이지의
#      목록은 모두 비어 있다 — 그 사본 행은 어느 설정 화면에도 속하지 않는다.
#
# 따라서 **제품 결함이 아니고 자동화 상태 누수도 아니다.** 판정 쿼리가 작업용 사본을
# 설정 항목으로 세던 것이 결함이었다. 여기서 `SCPUseType=0` 으로 좁힌다.
#
# `SCPUseType` 전체 열거값은 문서로 확인하지 않았다. **0 = 설정된 Storage SCP** 만
# 위 세 근거로 확정했고, 1 이 "전송 작업 사본"이라는 것은 큐 행의 참조 관계로
# 관찰한 것이다. 다른 값의 의미는 단정하지 않는다.
STORAGE_SCP_USE_TYPE = 0


def _stored_transfer_syntax(ctx):
    return ctx.db.one(
        "CONFIGURATION",
        "SELECT TOP 1 [Key],Name,AETitle,IP,Port,TransferSyntax "
        "FROM DICOM_STORAGE WHERE [Use]=1 AND SCPUseType=@t "
        "ORDER BY [Key]", {"t": STORAGE_SCP_USE_TYPE}) or {}


def ensure_storage_transfer_syntax(ctx, ui, timeout=8, tesseract_exe=None):
    """Storage 서버의 Transfer Syntax를 사양이 선언한 Implicit VR LE로 맞춘다.

    반환: {"ok": bool, "changed": bool, "before": {...}, "after": {...},
           "active_before": int, "active_after": int, "error": str|None}
    이미 Implicit이면 **UI를 전혀 건드리지 않고** `changed=False`로 돌려준다 —
    2026-08-21부터 `setup-dicom`이 서버 등록 Update와 같은 시점에 이 값을
    확정하므로 회귀에서는 이 경로가 거의 실행되지 않는다.
    """
    before = _stored_transfer_syntax(ctx)
    active_before = len(active_storage_rows(ctx.db))
    out = {"ok": False, "changed": False, "before": before, "after": before,
           "active_before": active_before, "active_after": active_before,
           "error": None}
    if int(before.get("TransferSyntax", -1)) == TRANSFER_SYNTAX_IMPLICIT:
        out["ok"] = True
        return out

    flows.open_dicom_setting(ui, "storage", wait=3)
    rows = _server_items(ui)
    if not rows:
        out["error"] = "Storage SCP 목록이 비어 있습니다."
        return out
    # Option 영역은 SCP 행을 선택해야 활성화된다(실측). 목록의 첫 행이 대상 서버라고
    # 가정하지 않고, DB에서 확인한 활성 SCP와 이름이 같은 행을 UI 값으로 다시
    # 확인해 고른다.
    target_name = str(before.get("Name") or "")
    target = next((row for row in rows if _select_name(ui, row) == target_name), None)
    if target is None:
        out["error"] = (f"활성 Storage SCP {target_name!r} 행을 UI 목록에서 "
                        "찾지 못했습니다.")
        return out
    # `_select_name` 이 이미 이 행을 클릭해 선택했다. 한 번 더 누르지 않는다 —
    # `ui.click(row)` 는 행 **중앙**을 누르므로(AGENTS.md 3절) 이 목록에서는
    # Use 체크박스나 다른 셀을 건드릴 수 있다.
    try:
        changed = _ensure_storage_transfer_syntax_control(ui, tesseract_exe)
    except Exception as exc:                                   # noqa: BLE001
        out["error"] = str(exc)
        return out
    if not changed:
        # 화면은 이미 선언값인데 DB 가 다르다 = 저장되지 않은 상태다. 그대로
        # Update 해서 반영한다.
        pass
    flows.setting_update(ui)
    flows.confirm_setting_dialog(ui)
    out["changed"] = True

    end = time.time() + timeout
    while True:
        after = _stored_transfer_syntax(ctx)
        if int(after.get("TransferSyntax", -1)) == TRANSFER_SYNTAX_IMPLICIT:
            out.update(ok=True, after=after)
            break
        if time.time() >= end:
            out["after"] = after
            out["error"] = "저장 후에도 Implicit VR LE로 바뀌지 않았습니다."
            break
        time.sleep(1)

    # **Update 뒤에 설정된 활성 행 수를 다시 확인한다.** 값만 맞고 활성 행이
    # 여러 개면 뒤따르는 "수신 객체가 정확히 N건" 판정이 조용히 틀린다.
    # (`active_storage_rows` 는 전송 작업 사본 행을 세지 않는다 —
    #  `STORAGE_SCP_USE_TYPE` 주석 참고.)
    repair = None
    if len(active_storage_rows(ctx.db)) > 1:
        repair = repair_storage_use(ctx, ui, target_name)
        out["repair"] = repair
        if not repair["ok"]:
            out["ok"] = False
            out["error"] = ((out["error"] + " / ") if out["error"] else "") + (
                "Update 후 활성 Storage 가 여러 행이 되어 UI 로 복구를 시도했으나 "
                f"실패했습니다: {repair.get('error')}")
    out["active_after"] = len(active_storage_rows(ctx.db))
    return out


def setup_all(ctx, kinds=None):
    r = TCResult("DICOM_Server_Setup", "MWL/Storage/Print 서버 자동 등록 및 연결")
    # **이 함수는 첫 FAIL 에서 멈추지 않는다.** 아래 루프는 MWL/Storage/Print 를
    # 차례로 등록하며 실패해도 다음 종류로 넘어가도록 설계돼 있다 — 어느 서버가
    # 안 되는지 전부 보여 주는 것이 진단에 필요하기 때문이다.
    #
    # 2026-08-24 21차 회귀에서 전역 중단 정책(`TCResult.stop_on_fail`)이 이 루프를
    # 첫 실패에서 끊어 **DICOM 서버가 하나도 등록되지 않았고**, 그 뒤 19개 TC 가
    # 연쇄 실패했다(80분 낭비). 정책은 "TC 하나의 남은 Step 을 건너뛴다"는 뜻이지
    # "전제 준비를 반만 하고 만다"는 뜻이 아니다.
    #
    # 대신 **회귀는 이 결과가 FAIL 이면 즉시 중단한다**(`run.py` 의 전제 게이트).
    # 서버가 등록되지 않으면 이후 시험에 의미가 없다(2026-08-25 사용자 지시).
    r.stop_on_fail = False
    kinds = set(kinds or ("MWL", "Storage", "Print"))

    # DICOM setup is the first UI phase of run-auto.  Never assume that the
    # operator has already launched or foregrounded Viewer: doing so can send
    # coordinate clicks to the Windows desktop.  A clean start also prevents
    # stale dialogs/settings pages from changing the control map.
    startup_log = []
    try:
        ui, startup_log = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError(
                "Viewer Patient screen was not reached "
                f"(현재 화면 랜드마크: {flows.known_screen(ui) or '없음'})")
        win = ui.activate()
        if not win:
            raise RuntimeError("Viewer main window was not found")
        l, t, rr, bb = win.rect
        if (rr - l) * (bb - t) < ui.MAIN_WINDOW_MIN_AREA:
            raise RuntimeError(f"Viewer window is not in a safe full-screen state: {win.rect}")
        r.add(0, "Viewer 시작·로그인·전면 활성화", PASS,
              expected="관리자 권한 Viewer / Patient 화면",
              actual=" / ".join(startup_log) or f"PID {ui.pid}")
    except Exception as exc:
        # 여기서 실패하면 회귀 전체가 연쇄로 무너진다(2026-08-18: 8개 TC).
        # 그래서 **기동 로그와 마지막 화면 증거를 반드시 남긴다.** 이전에는
        # 예외 문구만 남아 어느 단계에서 멈췄는지 추적할 수 없었다.
        shot = None
        try:
            from core import screen
            from PIL import ImageGrab
            box = ImageGrab.grab(all_screens=True).getbbox()
            shot = os.path.join(ctx.cfg.get("evidence_ui_dir", "Evidence/ui"),
                                "setup_startup_failed.png")
            screen.grab(box, path=shot)
        except Exception as shot_exc:
            shot = f"(캡처 실패: {shot_exc})"
        r.add(0, "Viewer 시작·로그인·전면 활성화", FAIL,
              expected="첫 UI 클릭 전에 Viewer 준비 완료",
              actual={"error": str(exc), "startup_log": startup_log,
                      "screenshot": shot},
              note="안전장치가 동작하여 DICOM 좌표 클릭을 수행하지 않음. "
                   "이 단계가 실패하면 MWL 서버가 미등록으로 남아 후속 TC가 "
                   "모두 연쇄 실패하므로, 재실행 전 이 증거를 먼저 확인할 것.")
        return r

    if "Storage" in kinds:
        ok, detail = ensure_storage_reachable(ctx.cfg)
        spec = (ctx.cfg.get("dicom") or {}).get("storage_scp") or {}
        r.add(0, "Storage SCP 도달 확인", PASS if ok else FAIL,
              expected=f"{spec.get('ae_title')} @ {spec.get('host')}:"
                       f"{spec.get('port')} — SCP running + DICOM 포트 연결",
              actual=detail,
              note="2026-08-26 Bunny(로컬 앱)를 원격 Storage SCP 웹 서버로 "
                   "대체했다. 우리가 띄울 것이 없으므로 '기동' 이 아니라 "
                   "'도달 가능' 을 판정한다.")
    for spec in ctx.cfg["dicom"]["servers_to_register"]:
        kind = spec["kind"]
        if kind not in kinds:
            continue
        try:
            ui.activate()
            _open_page(ui, kind)
            # Use 정리는 목록의 여러 행을 선택하므로 입력/옵션 변경 전에 끝낸다.
            # 변경 뒤에 실행하면 마지막으로 선택된 다른 서버가 Update될 수 있다.
            # MWL도 신규 PC에서 기본 Use=0으로 남아 있으면 이후 WF01의 MWL
            # 등록이 막히므로 Storage와 동일하게 대상 서버만 활성화한다.
            # DICOM_PRINT 테이블에는 [Use] 컬럼이 없어(단일 활성 개념 없음) 대상이 아니다.
            use_changed = _sync_use(ui, ctx.db, kind, spec["name"]) if kind != "Print" else False
            target, changed, created = _set_server(ui, spec)
            if kind == "Storage" and created:
                ch = children(target.hwnd, 1)
                if ch:
                    ui.click(ch[0], settle=.3)
                    use_changed = True
            option_states = None
            if kind == "Storage":
                option_changed, option_states = _ensure_storage_options(ui)
                changed = changed or option_changed
                # Transfer Syntax도 서버 등록 시 같은 Update로 확정한다. 뒤따르는
                # WF04가 Setting 상태에 따라 같은 Storage 행을 복제하지 않게 한다.
                tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
                changed = (_ensure_storage_transfer_syntax_control(ui, tess)
                           or changed)
            changed = changed or use_changed
        except Exception as exc:
            r.add(1, f"{kind} 설정 화면 준비", FAIL,
                  expected="Viewer Setting > DICOM 화면", actual=str(exc),
                  note="필수 Viewer 컨트롤이 없어 이후 클릭을 중단함")
            continue
        # Storage는 단일 Use. 다른 종류도 대상 서버를 활성화한다.
        evidence = os.path.join(ctx.evidence_root, "ui",
                                f"dicom_echo_{kind.lower()}.png")
        echo_ok, n, echo_text, echo_evidence = _echo(ui, evidence)
        # 기존 값과 옵션이 모두 같으면 불필요하게 다시 저장하지 않는다.
        # Echo는 매 실행마다 수행해 현재 연결 상태를 검증한다.
        if changed:
            _update(ui)
        rows = _saved_rows(ctx.db, kind, spec)
        saved = _exact_saved(rows, spec)
        net = tcp_open(spec["ip"], spec["port"])
        r.assert_true(1, f"{kind} 서버 저장", saved,
                      expected=(f"{spec['name']} / {spec['ae_title']} / "
                                f"{spec['ip']}:{spec['port']}"), actual=rows)
        if kind != "Print":
            table = {"MWL": "DICOM_MWL", "Storage": "DICOM_STORAGE"}[kind]
            # Storage 는 전송 작업 사본 행(`SCPUseType<>0`)도 `Use=1` 이므로
            # 설정 행만 센다(`STORAGE_SCP_USE_TYPE` 주석의 실측 근거 참고).
            extra_where = (f" AND SCPUseType={STORAGE_SCP_USE_TYPE}"
                           if kind == "Storage" else "")
            uses = ctx.db.query(
                "CONFIGURATION",
                f"SELECT Name,[Use] FROM {table} WHERE [Use]=1{extra_where}")
            only_target = (len(uses) == 1 and
                           str(uses[0].get("Name")) == str(spec["name"]))
            r.assert_true(1, f"{kind} Use 단일 선택", only_target,
                          expected=f"{spec['name']}만 Use=1", actual=uses)
        if kind == "Storage":
            saved_option = next((x for x in rows if
                                 str(x.get("Name")) == spec["name"]), {})
            db_option_ok = all(int(saved_option.get(x) or 0) == 1 for x in
                               ("BurnAnno", "BurnLabel", "BurnInfo",
                                "ApplyPreviewPosition", "SendDoseSR"))
            r.assert_true(1, "Storage 전송 옵션",
                          bool(option_states) and db_option_ok and
                          all(option_states.get(x) is True for x in
                              ("Annotation", "Label", "Information",
                               "Apply preview position")) and
                          str(option_states.get("Dose SR", "")).lower() == "send",
                          expected="Burn 3개 + Image 체크, Dose SR=Send",
                          actual={"ui": option_states, "db": saved_option})
            active = active_storage_rows(ctx.db)
            transfer_ok = (len(active) == 1 and
                           int(active[0].get("TransferSyntax", -1)) ==
                           TRANSFER_SYNTAX_IMPLICIT)
            r.assert_true(
                1, "Storage Transfer Syntax 단일 행 저장", transfer_ok,
                expected="활성 Storage 1행 / Implicit VR Little Endian(0)",
                actual=active,
                note="DICOM Conformance Statement V1.3W1의 선언값. "
                     "회귀 시작 단계에서 전송 옵션과 한 번에 저장한다.")
        r.assert_true(2, f"{kind} TCP 연결", net, expected=f"{spec['ip']}:{spec['port']}", actual=net)
        r.assert_true(3, f"{kind} C-ECHO", echo_ok,
                      expected="Verification 6단계 이상 및 Connected Fail 없음",
                      actual={"rows": n, "ocr": echo_text,
                              "evidence": echo_evidence})
    return r
