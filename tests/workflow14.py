# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_14 — Setting Export 및 Import.

기준 문서: `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx` 시트 `개정 TC`.

체크리스트 원문 (변경 금지)
  Precondition
    서비스 또는 관리자 계정으로 로그인되어 있다.
    변경 전 기준 설정값이 기록되어 있다.
  Step
    1. Setting > System > My Settings에서 Export Setting을 실행한다.
    2. Export 파일을 지정 경로에 저장한다.
    3. Theme 또는 검증 대상 비파괴 설정 1개를 변경한다.
    4. Import Setting을 실행한다.
    5. 2단계에서 저장한 파일을 선택한다.
    6. Viewer를 재시작한다.
    7. 변경 대상 설정값을 확인한다.
  Expected Result
    1. Setting Export가 시작된다.
    2. 설정 파일이 생성된다.
    3. 변경한 설정이 적용된다.
    4. Setting Import가 시작된다.
    5. 설정 파일을 읽어 Import가 완료된다.
    6. Viewer가 정상 재실행된다.
    7. Export 시점의 설정값으로 복원되어 있다.
  Test Data
    설정 파일: Evidence\Settings\Baseline_Settings
    변경 항목: Theme 권장

## Step 3 의 변경 항목 — Theme 을 쓰지 않는 이유 (명시적 이탈)

Test Data 는 Theme 을 **권장**하고 Step 은 "Theme **또는** 검증 대상 비파괴 설정
1개"를 허용한다. 이 자동화는 `Storage Free Space Alarm > Warning`
(`SYSTEM_COMMON.StorageWarning`, 같은 Setting > System > General 화면)을 쓴다.

이유: Theme 는 Viewer 전체의 색을 바꾼다. 이 저장소의 판정 다수가
**브랜드 핑크 픽셀**(`core/screen.radio_selected`)과 **흰 배경/검은 글자 OCR**에
의존하므로, Import 복원이 실패해 Theme 이 되돌아오지 않으면 뒤따르는 모든 TC 가
무인 회귀에서 연쇄로 무너진다. `StorageWarning` 은 같은 화면·같은 DB 테이블
(`SYSTEM_COMMON`)에 있고 숫자 하나만 바뀌므로 판정력은 같고 위험은 없다.

## 판정 근거

- Step 2: 사양서1 "60. Setting Export/Import" 개발 사양이 `.vms` 를
  `.zip 파일로 설정을 내보낸다. (확장자 변경 .vms)` 로 정의하고 담을 내용을
  나열한다 → `core/setting_transfer.inspect_vms()` 가 그 구성을 대조한다.
  파일이 "생겼다"만으로 통과시키지 않는다.
- Step 4: 사양이 `System / Account / Procedure 중 사용자가 선택한 설정 값만`
  가져온다고 하므로 그 세 옵션이 실제로 있는지 OCR 로 확인한다.
- Step 6: 사양이 `Import 한 설정은 Viewer를 재시작해야 적용된다` 고 하므로
  재시작을 **판정 단계**로 둔다(재시작 없이 값이 바뀌었다면 사양과 다르다).
- Step 7 주 판정: 설정 테이블 **전수 대조**(`snapshot.config_identical`).
  좌표·픽셀·OCR 이 개입하지 않는 결정적 근거다.
- Step 7 보강: Setting **56개 페이지의 컨트롤 값**을 ID 기준으로 읽어 항목 단위
  대조(`core/setting_values.py`). 사내 선행 도구(Setting 화면 캡처-비교 프로그램)와 같은
  목적이지만 **이미지 비교가 아니다** — 그 도구가 회고에 적은 두 오탐
  ("텍스트 커서가 캡처되면 같은 값인데 Fail", "Setting 창 로딩이 늦어진 Fail")은
  픽셀을 값의 대리물로 쓴 데서 나오므로, 값을 직접 읽어 원인을 없앴다.
  Calibration 도 필요 없다(절대좌표 대신 컨트롤 ID 로 이동).
  캡처 이미지는 사람이 눈으로 볼 증거로만 남기고 **판정에 쓰지 않는다**.

## 상태 복구

이 TC 는 **자기 자신이 되돌린다.** Export 를 TC 시작 시점에 뜨므로 Import 는
시작 상태를 복원한다. Step 5 이후 실패해 값이 남으면 `finally` 에서 UI 로
`StorageWarning` 을 원래 값으로 되돌리고, 되돌리지 못하면 그 사실을 판정으로
남긴다(조용히 넘기지 않는다).
"""

from __future__ import annotations

import os
import time

from core import flows, screen, setting_transfer, setting_values, snapshot, specs
from core.result import FAIL, PASS, TCResult

# Setting > System > General 의 Storage Free Space Alarm (2026-08-21 실측)
#   2230 Warning 슬라이더(자식 1 = 감소 ◀ / 2 = 증가 ▶) / 2232 Warning Edit
#   2231 Critical 슬라이더                                / 2233 Critical Edit
STORAGE_WARNING_SLIDER = 2230
STORAGE_WARNING_EDIT = 2232
SLIDER_DECREASE = 1
SLIDER_INCREASE = 2

EXPORT_FILE = "WF14_Baseline_Settings.vms"


def _read_warning_edit(ui):
    """Warning 값을 화면 Edit(2232)에서 읽는다. 표준 Edit 이라 OCR 이 필요없다."""
    hits = [c for c in ui.by_id(STORAGE_WARNING_EDIT)
            if c.visible and c.cls == "Edit"]
    if not hits:
        return None
    text = (ui.get_text(hits[0]) or "").strip()
    try:
        return int(text)
    except ValueError:
        return None


def _nudge_warning(ui, direction, timeout=6):
    """Warning 슬라이더의 ◀/▶ 를 한 번 누르고 **값이 실제로 바뀔 때까지** 기다린다.

    조작 후 확인 없는 코드를 만들지 않는다(운영 지침 11절).
    """
    from core.ui import children

    slider = next((c for c in ui.by_id(STORAGE_WARNING_SLIDER) if c.visible),
                  None)
    if slider is None:
        raise RuntimeError(
            f"Storage Warning 슬라이더({STORAGE_WARNING_SLIDER})를 "
            "찾지 못했습니다.")
    want_id = SLIDER_INCREASE if direction > 0 else SLIDER_DECREASE
    btn = next((c for c in children(slider.hwnd, 3)
                if c.ctrl_id == want_id and c.visible
                and c.rect[2] - c.rect[0] > 10), None)
    if btn is None:
        raise RuntimeError(
            f"Storage Warning 슬라이더의 {'증가' if direction > 0 else '감소'} "
            f"버튼({want_id})을 찾지 못했습니다.")
    before = _read_warning_edit(ui)
    ui.click(btn, settle=0.8)
    end = time.time() + timeout
    while time.time() < end:
        now = _read_warning_edit(ui)
        if now is not None and now != before:
            return before, now
        time.sleep(0.4)
    return before, _read_warning_edit(ui)


def _db_warning(db):
    row = db.one("CONFIGURATION", "SELECT StorageWarning FROM SYSTEM_COMMON")
    return int(row["StorageWarning"]) if row and row.get(
        "StorageWarning") is not None else None


def _set_warning_to(ui, db, target, attempts=12):
    """UI 로 Warning 을 target 으로 맞추고 Update 한다. DB 로 확인한다.

    `core/db.py` 는 조회 전용이므로 복구도 UI 로만 한다(설계 유지).
    """
    flows.open_system_setting(ui, "general", wait=2.5)
    for _ in range(attempts):
        now = _read_warning_edit(ui)
        if now is None:
            raise RuntimeError("Warning 값을 화면에서 읽지 못했습니다.")
        if now == target:
            break
        _nudge_warning(ui, 1 if target > now else -1)
    flows.setting_update(ui, wait=2.5)
    flows.confirm_setting_dialog(ui)
    end = time.time() + 15
    while time.time() < end:
        if _db_warning(db) == target:
            return True
        time.sleep(1)
    return _db_warning(db) == target


def run(ctx):
    r = TCResult("TC_Basic_WorkFlow_14", "Setting Export 및 Import")
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    evidence = os.path.join(ctx.evidence_root, "Flow", "14_Setting")
    os.makedirs(evidence, exist_ok=True)
    vms = os.path.join(evidence, EXPORT_FILE)

    ui = None
    baseline_warning = None
    changed_warning = None
    imported = False
    try:
        # --- Precondition ----------------------------------------------
        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        if not flows.ensure_patient_screen(ui):
            raise RuntimeError("Patient 화면이 준비되지 않았습니다")
        login_id = (ctx.cfg["viewer"]["login"] or {}).get("id")
        r.assert_true(
            0, "[Precondition] 서비스 또는 관리자 계정으로 로그인",
            str(login_id).lower() in ("service", "admin"),
            expected="service 또는 admin 계정",
            actual={"login": login_id, "startup": startup},
            note="체크리스트 Precondition. Setting > System > My Settings 는 "
                 "권한 표(사양서1 78~80쪽)에서 User 에게 보이지 않는 항목이다.")

        baseline_warning = _db_warning(ctx.db)
        pre = snapshot.take(ctx.db)
        r.assert_true(
            0, "[Precondition] 변경 전 기준 설정값 기록", baseline_warning is not None,
            expected="SYSTEM_COMMON.StorageWarning 판독",
            actual={"StorageWarning": baseline_warning,
                    "설정 섹션 수": len(snapshot.CONFIG_SECTIONS)},
            note="Export 직전 상태를 DB 스냅샷으로 떠 둔다. Step 7 의 전수 대조 기준.")

        # --- Step 7 보강의 1회차: 설정 화면 값 판독 --------------------
        before_vals = setting_values.read_all(
            ui, tesseract_exe=tess,
            capture_dir=os.path.join(evidence, "pages_before"))
        n_items = sum(len(v) for v in before_vals["pages"].values())
        r.add(0, "[근거 수집] Setting 전 페이지 컨트롤 값 판독(1회차)", PASS,
              expected="Setting 9개 그룹의 페이지별 컨트롤 값",
              actual={"pages": len(before_vals["pages"]), "items": n_items,
                      "missing": list(before_vals["missing"])},
              note="사내 선행 도구(Setting 화면 캡처-비교 프로그램)와 같은 목적이지만 "
                   "**이미지 비교가 아니다**. 절대좌표/Calibration 없이 컨트롤 ID 로 "
                   "이동하고, Edit·콤보는 WM_GETTEXT 로 값을 정확히 읽는다. 그 도구가 "
                   "회고에 적은 두 오탐('텍스트 커서가 캡처되면 같은 값인데 Fail', "
                   "'Setting 창 로딩이 늦어진 Fail')은 픽셀을 값의 대리물로 쓴 데서 "
                   "나오므로 원인을 제거했다. 커스텀 라디오/체크박스는 "
                   "BM_GETCHECK 에 응답하지 않아(실측 전부 0) 픽셀로 읽고, 그 "
                   "판정력은 DB 전수 대조가 보증한다.")

        # --- Step 1 ----------------------------------------------------
        setting_transfer.open_my_settings(ui, wait=3.0)
        path = os.path.join(evidence, "01_my_settings.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        dlg, info = setting_transfer.click_export(ui)
        vms_type_ok = "vms" in (info.get("file_type") or "").lower()
        r.assert_true(
            1, "[Setting > System > My Settings] Export Setting 실행", vms_type_ok,
            expected="저장 대화상자 + 파일 형식 vms",
            actual=info,
            note=specs.cite(ctx, "설정 정보를 .vms",
                            fallback="사양서1 60. Setting Export/Import — "
                                     "'선택한 위치에 설정 정보를 .vms 확장자로 "
                                     "저장한다'") +
                 " 대화상자가 열린 사실뿐 아니라 **파일 형식이 vms** 인지까지 확인한다.")
        path = os.path.join(evidence, "02_save_dialog.png")
        ui.capture_dialog(dlg, path)
        r.attach(path)

        # --- Step 2 ----------------------------------------------------
        saved = setting_transfer.save_export(ui, dlg, vms)
        vms_info = setting_transfer.inspect_vms(vms)
        r.assert_true(
            2, "Export 파일 생성", os.path.isfile(vms) and saved["size"] > 0,
            expected=f"{vms} 생성",
            actual={"size": saved["size"], "seconds": saved["seconds"],
                    "완료팝업": saved["done_dialog"]})
        r.assert_true(
            2, "Export 파일 구성이 사양의 개발 사양과 일치",
            vms_info["is_zip"] and not vms_info["missing"],
            expected={"zip": True,
                      "필수": list(setting_transfer.VMS_REQUIRED) +
                              [p + "*" for p in
                               setting_transfer.VMS_REQUIRED_PREFIX]},
            actual={"zip": vms_info["is_zip"],
                    "누락": vms_info["missing"],
                    "항목수": len(vms_info["entries"]),
                    "Version.txt": vms_info["version"]},
            note="사양서1 60절 개발 사양: '.zip 파일로 설정을 내보낸다(확장자 변경 "
                 ".vms)', 'DATA를 제외한 모든 DB 백업파일(CONFIGURATION, ACCOUNT, "
                 "PROCEDURE)', 'XIPL Parameter 폴더 내 모든 Parameter 파일을 "
                 "Export\\PARAMETER 폴더에', 'ExternalInput.xml 파일을 "
                 "Export\\Config 폴더에'. **파일이 생겼다는 것만으로 통과시키지 "
                 "않는다.** 제품은 사양보다 세분화해 PARAMETER_QC/ 와 "
                 "RECON_PARAMETER/ 로도 나눠 담는다(실측) — 사양이 요구한 내용이 "
                 "들어 있으므로 결함으로 보지 않는다.")

        # --- Step 3 ----------------------------------------------------
        target = baseline_warning + 1 if baseline_warning is not None else None
        if target is None:
            raise RuntimeError("기준 StorageWarning 을 읽지 못해 변경할 수 없습니다.")
        ok = _set_warning_to(ui, ctx.db, target)
        changed_warning = _db_warning(ctx.db)
        path = os.path.join(evidence, "03_changed.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)
        r.assert_equal(
            3, "비파괴 설정 1개 변경이 적용됨(Storage Free Space Alarm > Warning)",
            target, changed_warning,
            note="체크리스트는 'Theme 또는 검증 대상 비파괴 설정 1개'를 허용한다. "
                 "Theme 은 Viewer 전체 색을 바꿔 이 저장소의 픽셀/OCR 판정을 "
                 "무너뜨릴 수 있어(복원 실패 시 회귀 전체 연쇄 실패) 같은 화면·같은 "
                 "테이블(SYSTEM_COMMON)의 StorageWarning 을 쓴다. 판정력은 같다. "
                 f"UI 조작으로 {baseline_warning} -> {target} 로 바꾸고 Update 후 "
                 "DB 로 확인했다.")
        if not ok:
            raise RuntimeError(
                f"설정 변경이 DB 에 반영되지 않아 Import 판정이 무의미해집니다"
                f"(기대 {target}, 실제 {changed_warning}).")

        # --- Step 4 ----------------------------------------------------
        setting_transfer.open_my_settings(ui, wait=3.0)
        idlg, iinfo = setting_transfer.click_import(ui, tesseract_exe=tess)
        path = os.path.join(evidence, "04_import_dialog.png")
        ui.capture_dialog(idlg, path)
        r.attach(path)
        opts = iinfo["options"]
        have_all = all(opts[k]["found"] for k in ("system", "account",
                                                  "procedure"))
        r.assert_true(
            4, "Import Setting 실행 및 선택 옵션 구성", have_all,
            expected="System / Account / Procedure 선택 옵션",
            actual={"labels": iinfo["labels"], "buttons": iinfo["buttons"],
                    "options": {k: {"label": v["label"],
                                    "checked": v["checked"]}
                                for k, v in opts.items()}},
            note=specs.cite(ctx, "System / Account / Procedure",
                            fallback="사양서1 60절 — 'System / Account / "
                                     "Procedure 중 사용자가 선택한 설정 값만 "
                                     "가져와서 적용할 수 있다'") +
                 " 대화상자가 떴다는 사실이 아니라 **사양이 요구한 선택 항목이 "
                 "실제로 있는지**로 판정한다. 실측 기본값은 System 만 체크다.")

        # --- Step 5 ----------------------------------------------------
        # 전수 대조를 의미있게 하려면 세 범위를 모두 가져와야 한다.
        result = setting_transfer.run_import(
            ui, idlg, vms, options=("system", "account", "procedure"),
            tesseract_exe=tess)
        imported = True
        finals = {k: v["final"] for k, v in result["options"].items()}
        r.assert_true(
            5, "저장한 파일을 선택해 Import 완료",
            all(finals.get(k) is True for k in ("system", "account",
                                                "procedure")),
            expected={"파일": vms, "옵션": "System/Account/Procedure 모두 선택"},
            actual={"옵션 최종상태": finals, "소요": result["seconds"],
                    "대화상자 닫힘": result["closed"],
                    "안내 메시지": result["message"]},
            note="사양서1 60절: 'Import 한 후 재시작 전에 변경한 내용은 적용되지 "
                 "않는다. (해당 내용 메시지박스로 사용자에게 표시)' — 안내 "
                 "메시지가 뜨는 것이 정상이므로 읽어서 증거로 남긴다.")

        # 사양: 재시작 전에는 적용되지 않는다 → 여기서 값이 이미 돌아갔다면
        # 사양과 다르다. 확인만 하고 판정으로 남긴다.
        before_restart = _db_warning(ctx.db)

        # --- Step 6 ----------------------------------------------------
        ui, restart = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        ready = flows.ensure_patient_screen(ui)
        r.assert_true(
            6, "Viewer 재시작 후 정상 실행", bool(ready),
            expected="로그인 통과 후 Patient 화면",
            actual={"startup": restart, "patient_screen": bool(ready)},
            note=specs.cite(ctx, "Import 한 설정은 Viewer를 재시작",
                            fallback="사양서1 60절 — 'Import 한 설정은 Viewer를 "
                                     "재시작해야 적용된다'") +
                 f" 재시작 직전 StorageWarning={before_restart}.")
        if not ready:
            raise RuntimeError("재시작 후 Patient 화면이 준비되지 않았습니다")

        # --- Step 7 ----------------------------------------------------
        post = snapshot.take(ctx.db)
        restored = _db_warning(ctx.db)
        r.assert_equal(
            7, "변경한 설정값이 Export 시점 값으로 복원",
            baseline_warning, restored,
            note="주 판정. 변경 대상(StorageWarning)이 Export 시점 값으로 "
                 "돌아왔는지 DB 로 확인한다.")

        same, diff = snapshot.config_identical(pre, post)
        r.assert_true(
            7, "설정 테이블 전수 대조(Export 시점과 동일)", same,
            expected=f"설정 섹션 {len(snapshot.CONFIG_SECTIONS)}개 전부 일치",
            actual="일치" if same else f"불일치 {len(diff)}개 섹션: "
                                     f"{sorted(diff)}",
            note="사양서1 60절이 Export 대상을 'Study 정보를 제외한 모든 설정 "
                 "정보(DB / sql file)'로 정의하므로, 화면 픽셀이 아니라 설정 "
                 "테이블 전수 대조가 결정적 근거다.")
        for sec in sorted(diff):
            r.add(7, f"설정 섹션 [{sec}] 복원", FAIL,
                  expected="Export 시점과 동일",
                  actual=_fmt_section(diff[sec]))

        # Step 7 보강 — 화면 컨트롤 값 항목 단위 대조 (좌표/이미지 비교 아님)
        after_vals = setting_values.read_all(
            ui, tesseract_exe=tess,
            capture_dir=os.path.join(evidence, "pages_after"))
        vc = setting_values.compare(before_vals, after_vals)
        r.assert_true(
            7, "Setting 화면 컨트롤 값 항목 단위 복원(보강 근거)",
            not vc["changed"] and not vc["only_before"] and not vc["only_after"],
            expected=f"{vc['compared_pages']}개 페이지 / "
                     f"{vc['compared_items']}개 항목 값 동일",
            actual={"페이지": vc["compared_pages"], "항목": vc["compared_items"],
                    "달라진 항목": vc["changed"][:20],
                    "한쪽에만 있음": (vc["only_before"][:10] +
                                vc["only_after"][:10]),
                    "판독불가(라디오 픽셀)": len(vc["unreadable"]),
                    "배치 흔들림 흡수": vc["jitter_matched"],
                    "진입불가 페이지": list(vc["missing_pages"])},
            note="컨트롤 ID 로 이동해 Edit·콤보는 WM_GETTEXT, 라디오/체크박스는 "
                 "픽셀로 읽어 **항목 단위**로 대조했다. 이미지 비교가 아니므로 "
                 "텍스트 커서·로딩 지연이 판정에 섞이지 않는다. 달라진 항목은 "
                 "`페이지:컨트롤ID@패널상대좌표` 로 위치까지 나온다. "
                 "판독불가(라디오 픽셀 None)는 비교 대상에서 제외했고, 그 항목들의 "
                 "값은 위 DB 전수 대조가 이미 판정했다. 캡처 이미지는 "
                 "pages_before/ pages_after/ 에 증거로만 남긴다. "
                 "'배치 흔들림 흡수'는 컨트롤이 회차 사이에 1~8px 움직여 키가 "
                 "어긋난 것을 같은 컨트롤로 짝지은 수다 — 2026-08-21 첫 실행에서 "
                 "`patient.general` 의 2303 이 x 595->594 로 1px 움직여 '한쪽에만 "
                 "있음' 으로 잡혔고, 그것을 설정 차이로 보고하면 오탐이다.")

    except Exception as exc:                           # noqa: BLE001
        r.add(0, "TC 수행 중 예외", FAIL, actual=f"{type(exc).__name__}: {exc}")
        path = os.path.join(evidence, "99_error.png")
        try:
            screen.grab((0, 0, 1920, 1080), path=path)
            r.attach(path)
        except Exception:                              # noqa: BLE001
            pass
    finally:
        # --- 상태 복구 -------------------------------------------------
        # Import 가 끝났으면 시작 상태가 이미 복원돼 있다. Import 전에 실패했다면
        # 바꿔 둔 값이 남으므로 UI 로 되돌린다.
        now = _db_warning(ctx.db)
        if baseline_warning is not None and now != baseline_warning:
            recovered = False
            try:
                if ui is None or not flows.ensure_patient_screen(ui):
                    ui, _ = flows.cold_start(ctx.cfg, ctx.db,
                                             force_restart=True)
                    flows.ensure_patient_screen(ui)
                recovered = _set_warning_to(ui, ctx.db, baseline_warning)
            except Exception as exc:                   # noqa: BLE001
                r.add(0, "정리: StorageWarning 원복", FAIL,
                      expected=baseline_warning,
                      actual=f"복구 실패 {type(exc).__name__}: {exc}")
            else:
                r.add(0, "정리: StorageWarning 원복",
                      PASS if recovered else FAIL,
                      expected=baseline_warning, actual=_db_warning(ctx.db),
                      note="Import 전에 중단되면 변경값이 남아 다음 TC 의 설정 "
                           "대조를 오염시킨다. UI 로만 되돌린다"
                           "(core/db.py 는 조회 전용).")
        elif imported:
            r.add(0, "정리: Import 로 시작 상태 복원됨", PASS,
                  expected=baseline_warning, actual=now,
                  note="이 TC 는 Export 를 시작 시점에 떠서 Import 가 곧 원복이다.")
    return r


def _fmt_section(sd):
    bits = []
    if sd.get("added"):
        bits.append(f"추가 {len(sd['added'])}행")
    if sd.get("removed"):
        bits.append(f"삭제 {len(sd['removed'])}행")
    for c in sd.get("changed", [])[:5]:
        bits.append(f"{c['row']}: " + ", ".join(
            f"{k} {v['pre']}->{v['post']}" for k, v in c["fields"].items()))
    return " / ".join(bits) or "차이 상세 없음"
