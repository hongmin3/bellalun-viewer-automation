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
import subprocess
import time

from core import flows
from core.result import TCResult, PASS, FAIL
from core.ui import ViewerUi, children

PAGE = {"MWL": "mwl", "Storage": "storage", "Print": "print"}


def ensure_bunny(cfg):
    spec = cfg["dicom"]["storage_scp"]
    exe = spec["app_path"]
    if not ViewerUi("Bunny").pid:
        subprocess.Popen([exe], cwd=os.path.dirname(exe))
        end = time.monotonic() + 15
        while time.monotonic() < end and not ViewerUi("Bunny").pid:
            time.sleep(.25)
    ui = ViewerUi("Bunny")
    tree = [c for c in ui.by_id(1022) if c.visible and c.cls == "SysTreeView32"]
    if tree:
        ui.click(tree[0], settle=.2)
        ui.raw_key(0x24)  # Home = Storage Server
        ui.raw_key(0x0D)
    end = time.monotonic() + 15
    while time.monotonic() < end:
        if (tcp_open(spec["host"], int(spec["port"])) or
                tcp_open("127.0.0.1", int(spec["port"]))):
            return True
        time.sleep(.25)
    return False


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
    extra = (",BurnAnno,BurnLabel,BurnInfo,ApplyPreviewPosition,SendDoseSR"
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


def setup_all(ctx, kinds=None):
    r = TCResult("DICOM_Server_Setup", "MWL/Storage/Print 서버 자동 등록 및 연결")
    kinds = set(kinds or ("MWL", "Storage", "Print"))

    # DICOM setup is the first UI phase of run-auto.  Never assume that the
    # operator has already launched or foregrounded Viewer: doing so can send
    # coordinate clicks to the Windows desktop.  A clean start also prevents
    # stale dialogs/settings pages from changing the control map.
    try:
        ui, startup_log = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError("Viewer Patient screen was not reached")
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
        r.add(0, "Viewer 시작·로그인·전면 활성화", FAIL,
              expected="첫 UI 클릭 전에 Viewer 준비 완료", actual=str(exc),
              note="안전장치가 동작하여 DICOM 좌표 클릭을 수행하지 않음")
        return r

    if "Storage" in kinds:
        if not ensure_bunny(ctx.cfg):
            r.add(0, "Bunny Storage SCP 시작", FAIL, expected="TCP 3000 LISTEN", actual="연결 실패")
        else:
            r.add(0, "Bunny Storage SCP 시작", PASS, expected="TCP 3000 LISTEN", actual="연결 성공")
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
            uses = ctx.db.query("CONFIGURATION", f"SELECT Name,[Use] FROM {table} WHERE [Use]=1")
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
        r.assert_true(2, f"{kind} TCP 연결", net, expected=f"{spec['ip']}:{spec['port']}", actual=net)
        r.assert_true(3, f"{kind} C-ECHO", echo_ok,
                      expected="Verification 6단계 이상 및 Connected Fail 없음",
                      actual={"rows": n, "ocr": echo_text,
                              "evidence": echo_evidence})
    return r
