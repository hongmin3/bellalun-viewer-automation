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
    3. 검증 대상 비파괴 설정을 여러 메뉴에서 변경한다.
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
    변경 항목: 서로 다른 설정 테이블을 덮는 비파괴 설정 여러 개
              (Theme 은 제외 — 화면 색이 바뀌어 후속 판정에 영향)

## Step 3 의 변경 항목 — 왜 여러 개인가

**2026-08-28 에 체크리스트 원문을 이 수행에 맞게 고쳤다**(사용자 승인).
그전 원문은 "Theme **또는** 검증 대상 비파괴 설정 **1개**" 였고 자동화는 이미
8개를 바꾸고 있어 문서와 실제가 어긋나 있었다. 문서를 실제에 맞춘 이유는
아래 ②와 같다 — 1개만 바꾸면 사람이 손으로 수행할 때도 검증이 얕아진다.
수정 전 원본은 `..\Baseline\Checklist_개정본_20260828_WF14Step3수정전.xlsx`.

### ① Theme 을 쓰지 않는다

Theme 은 Viewer 전체의 색을 바꾼다. 이 저장소의 판정 다수가 **브랜드 핑크
픽셀**(`core/screen.radio_selected`)과 **흰 배경/검은 글자 OCR** 에 의존하므로,
Import 복원이 실패해 Theme 이 되돌아오지 않으면 뒤따르는 모든 TC 가 무인 회귀에서
연쇄로 무너진다.

### ② **7개 메뉴 / 7개 설정 테이블**을 바꾼다

Step 7 의 판정은 설정 테이블 **전수 대조**인데, **바꾸지 않은 영역은 그 판정이
아무것도 증명하지 못한다.** Import 가 `TOOL_COMMON` 을 통째로 건너뛰어도 그
테이블을 건드린 적이 없으면 Export 전후가 당연히 같아 통과한다. 즉 **변경 범위가
곧 이 TC 의 실제 검증 범위**이고, 1개만 바꾸면 "전수 대조" 라는 이름과 달리 실제로
검증되는 것은 그 한 테이블뿐이다.

    System    > General       SYSTEM_COMMON.StorageWarning
    Patient   > Patient List  REGISTRATION_COMMON.AutoRefreshTime
    Display   > Overlay       OVERLAY.OverlayFontSize
    Procedure > General       PROCEDURE_COMMON.TargetExposureIndex
    Q.C.      > Setting 3D    QC_COMMON.TomoMTFThick
    DICOM     > General       DICOM_COMMON.AllowLongAcc
    Tool      > General       TOOL_COMMON.CopyImgCrop

무엇을 왜 제외했는지(Theme / Language / Security / DICOM Port / Device 노출
인터록 / 자동 삭제)는 `core/setting_changes.py` docstring 에 적었다.

2026-08-25 왕복 실측: 7개 적용 -> 설정 섹션 7개 변경 -> 7개 원복 -> **잔여 차이 0**.

### ③ 여기에 **UPS 설정**을 하나 더 얹는다 — DB 가 아니라 화면으로 판정한다

`Setting > Device > UPS` 의 `UPS Setting`(`None` / `EATON Ellipse ECO 650`)은
위 7개와 성격이 다르다. **어느 설정 테이블에도 저장되지 않는다.**

2026-08-25 확인 (사용자 제보로 조사)

    .vms 안 20개 항목                          UPS 관련 0건
    CONFIGURATION/ACCOUNT/PROCEDURE 전 컬럼    'UPS'/'EATON' 0건, %UPS% 컬럼명 0건
    ExternalInput.xml                          ups/eaton/battery 0건
    레지스트리 HKLM|HKCU\SOFTWARE\Vieworks     UPS 값 0건
    UPSHandler\ 폴더                           설정 파일 없음(exe/dll/log 뿐)
    값을 바꾸고 Update                          설정 섹션 38개 중 0개 변화
    값을 바꾸고 Viewer 재기동                   **값이 남는다** (= 저장은 된다)

즉 **저장은 되는데 Export 산출물에는 들어가지 않는다** → Import 로 복원될 방법이
없다. 사양서1 60절이 Export 대상을 "Study 정보를 제외한 모든 설정 정보" 로
정의하는 것과 어긋난다. Step 7 마지막에 판정으로 남기고 **완화하지 않는다**
(`TC_XIPL_compatibility_03` Step 9 와 같은 취급).

같은 페이지의 `2537~2541`(Model / Serial No. / Battery Charged / Power State /
Remaining run time)은 **설정이 아니라 실시간 장치 상태**라 비교에서 뺀다
(`setting_values.VOLATILE_CONTROLS`).

## 판정 근거

- Step 2: 사양서1 "60. Setting Export/Import" 개발 사양이 `.vms` 를
  `.zip 파일로 설정을 내보낸다. (확장자 변경 .vms)` 로 정의하고 담을 내용을
  나열한다 → `core/setting_transfer.inspect_vms()` 가 그 구성을 대조한다.
  파일이 "생겼다"만으로 통과시키지 않는다.
- Step 3: 항목마다 **DB 컬럼으로** 변경을 확인한다. 화면이 바뀐 것처럼 보여도
  DB 에 반영되지 않으면 Import 판정이 무의미해지므로 실패로 본다.
- Step 4: 사양이 `System / Account / Procedure 중 사용자가 선택한 설정 값만`
  가져온다고 하므로 그 세 옵션이 실제로 있는지 OCR 로 확인한다.
- Step 6: 사양이 `Import 한 설정은 Viewer를 재시작해야 적용된다` 고 하므로
  재시작을 **판정 단계**로 둔다(재시작 없이 값이 바뀌었다면 사양과 다르다).
- Step 7 주 판정: 설정 테이블 **전수 대조**(`snapshot.config_identical`).
  좌표·픽셀·OCR 이 개입하지 않는 결정적 근거다. 여기에 **변경한 7개 항목이
  하나씩 원래 값으로 돌아왔는지**를 항목 단위로 덧붙인다 — 전수 대조가 통과해도
  어느 항목이 어떻게 복원됐는지 보고서에 남게 하기 위해서다.
- Step 7 보강: Setting **56개 페이지의 컨트롤 값**을 ID 기준으로 읽어 항목 단위
  대조(`core/setting_values.py`). 사내 선행 도구(Setting 화면 캡처-비교 프로그램)와 같은
  목적이지만 **이미지 비교가 아니다** — 그 도구가 회고에 적은 두 오탐
  ("텍스트 커서가 캡처되면 같은 값인데 Fail", "Setting 창 로딩이 늦어진 Fail")은
  픽셀을 값의 대리물로 쓴 데서 나오므로, 값을 직접 읽어 원인을 없앴다.
  Calibration 도 필요 없다(절대좌표 대신 컨트롤 ID 로 이동).
  캡처 이미지는 사람이 눈으로 볼 증거로만 남기고 **판정에 쓰지 않는다**.

## 상태 복구

이 TC 는 **자기 자신이 되돌린다.** Export 를 TC 시작 시점에 뜨므로 Import 는
시작 상태를 복원한다. Step 5 이후 실패해 값이 남으면 `finally` 에서
`setting_changes.restore_all` 이 UI 로 7개를 모두 되돌리고, 되돌리지 못한 항목은
그 사실을 판정으로 남긴다(조용히 넘기지 않는다).
"""

from __future__ import annotations

import os

from core import (flows, screen, setting_changes, setting_lists,
                  setting_transfer, setting_values, snapshot, specs)
from core.result import FAIL, PASS, StepFailed, TCResult

EXPORT_FILE = "WF14_Baseline_Settings.vms"

#: 목록 행 상세값을 대조할 후보 페이지 `(그룹, 페이지)`.
#
#  Setting 56개 페이지를 전부 훑지 않는 이유는 비용이다 — 목록이 없는 페이지에
#  들어가 확인만 해도 페이지당 1~2초가 든다(WF_14 는 이미 약 16.5분이다).
#  여기 적은 것은 **목록을 가진 것으로 알려진 페이지**이고, 실제로 목록이 없으면
#  `sweep` 이 "목록 없음" 으로 건너뛰고 그 사실을 남긴다(조용히 빠지지 않는다).
#  `core/setting_lists.ROW_COUNT_QUERIES` 에 원천 테이블이 매핑된 페이지와 짝을
#  이룬다 — 매핑이 있는 페이지는 "개수 증명"까지 받는다.
LIST_PAGES = (
    ("system", "account"),
    ("patient", "physician"),
    ("display", "overlay"),
    ("display", "lut"),
    ("tool", "predefined_text"),
    ("study", "reject_retake"),
    ("procedure", "procedure"),
    ("procedure", "hospital_code"),
    ("dicom", "mwl"),
    ("dicom", "mpps"),
    ("dicom", "storage"),
    ("dicom", "storage_group"),
    ("dicom", "storage_commitment"),
    ("dicom", "print"),
    ("dicom", "print_overlay"),
    ("dicom", "query_retrieve"),
    ("dicom", "tag_mapping"),
    ("qc", "scheduler"),
)


def _list_summary(sweep_result):
    """`setting_lists.sweep` 결과를 판정 `actual` 에 실을 형태로 줄인다."""
    pages = sweep_result.get("pages") or {}
    return {
        "목록 페이지": len(pages),
        "열거한 행": {k: len(v.get("signatures") or []) for k, v in pages.items()},
        "DB 원천 행": {k: v.get("expected_count") for k, v in pages.items()
                    if v.get("expected_count") is not None},
        "스크롤 횟수": {k: v.get("steps") for k, v in pages.items()},
        "불완전": sweep_result.get("incomplete") or [],
        "불완전 사유": {k: pages[k].get("reasons")
                   for k in (sweep_result.get("incomplete") or [])},
        "목록 없음/진입 실패": sweep_result.get("skipped") or {},
    }


def run(ctx):
    r = TCResult("TC_Basic_WorkFlow_14", "Setting Export 및 Import")
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    evidence = os.path.join(ctx.evidence_root, "Flow", "14_Setting")
    os.makedirs(evidence, exist_ok=True)
    vms = os.path.join(evidence, EXPORT_FILE)

    ui = None
    applied = []
    imported = False
    ups_baseline = None
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

        baseline = setting_changes.plan_targets(ctx.db)
        ups_baseline = setting_changes.read_ups(ui)
        setting_changes.close_setting(ui)
        pre = snapshot.take(ctx.db)
        r.assert_true(
            0, "[Precondition] 변경 전 기준 설정값 기록",
            all("error" not in b for b in baseline),
            expected=f"변경 대상 {len(setting_changes.CHANGE_PLAN)}개 항목의 "
                     f"현재값 판독",
            actual={"기준값": {b["item"].key: b.get("before", b.get("error"))
                            for b in baseline},
                    "UPS Setting(화면)": ups_baseline,
                    "설정 섹션 수": len(snapshot.CONFIG_SECTIONS)},
            note="Export 직전 상태를 DB 스냅샷으로 떠 둔다. Step 7 의 전수 대조 "
                 "기준이며, Import 가 실패했을 때 되돌릴 목표값이기도 하다.")

        # --- Step 7 보강의 1회차: 설정 화면 값 판독 --------------------
        before_vals = setting_values.read_all(
            ui, tesseract_exe=tess,
            capture_dir=os.path.join(evidence, "pages_before"))
        n_items = sum(len(v) for v in before_vals["pages"].values())
        if before_vals.get("viewer_died"):
            # 순회 도중 제품이 종료됐다. 여기서 멈추면 정작 검증하려는
            # Export/Import 를 한 번도 못 해 본다 — 재기동해서 본 시험을
            # 계속하고, **이 사실은 Step 7 에서 판정으로 남긴다.**
            ui, _restart = flows.cold_start(ctx.cfg, ctx.db,
                                            force_restart=True)
            flows.ensure_patient_screen(ui)
        r.add(0, "[근거 수집] Setting 전 페이지 컨트롤 값 판독(1회차)", PASS,
              expected="Setting 9개 그룹의 페이지별 컨트롤 값",
              actual={"pages": len(before_vals["pages"]), "items": n_items,
                      "Viewer 종료됨": bool(before_vals.get("viewer_died")),
                      "missing": list(before_vals["missing"])},
              note="사내 선행 도구(Setting 화면 캡처-비교 프로그램)와 같은 목적이지만 "
                   "**이미지 비교가 아니다**. 절대좌표/Calibration 없이 컨트롤 ID 로 "
                   "이동하고, Edit·콤보는 WM_GETTEXT 로 값을 정확히 읽는다. 그 도구가 "
                   "회고에 적은 두 오탐('텍스트 커서가 캡처되면 같은 값인데 Fail', "
                   "'Setting 창 로딩이 늦어진 Fail')은 픽셀을 값의 대리물로 쓴 데서 "
                   "나오므로 원인을 제거했다. 커스텀 라디오/체크박스는 "
                   "BM_GETCHECK 에 응답하지 않아(실측 전부 0) 픽셀로 읽고, 그 "
                   "판정력은 DB 전수 대조가 보증한다.")

        # --- Step 7 보강의 1회차: 목록 행 상세값 판독 -------------------
        before_lists = setting_lists.sweep(ui, ctx.db, LIST_PAGES)
        r.add(0, "[근거 수집] Setting 목록 행 상세값 판독(1회차)", PASS,
              expected="스크롤 아래 숨은 행을 포함한 목록 전 행의 상세값",
              actual=_list_summary(before_lists),
              note="2026-08-27 신설(core/setting_lists.py). 목록은 가상 ListItem 이 "
                   "같은 HWND/ID 를 재사용해 행을 핸들로 식별할 수 없다 — "
                   "2026-08-25 에 그래서 일부 행만 읽고 끝으로 오인했고 스크롤을 "
                   "통째로 제거했다. 이번에는 **행에 찍힌 문구**로 식별하고 끝까지 "
                   "봤다는 것을 세 겹으로 증명한다: (1) 스크롤해도 시퀀스가 더 "
                   "바뀌지 않고, (2) 스크롤 전후 시퀀스가 겹치며(겹치지 않으면 "
                   "화면을 건너뛴 것이라 열거 실패로 보고한다), (3) 열거한 행 수가 "
                   "**DB 원천 테이블 행 수**와 같다. 셋 중 하나라도 성립하지 않으면 "
                   "그 페이지는 불완전으로 남기고 판정 근거로 쓰지 않는다.")

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
        applied = setting_changes.apply_all(ui, ctx.db)
        summary = setting_changes.summarize(applied)
        setting_changes.close_setting(ui)
        path = os.path.join(evidence, "03_changed.png")
        screen.grab(ui.main_window().rect, path=path)
        r.attach(path)

        want_n = len(setting_changes.CHANGE_PLAN)
        r.assert_true(
            3, "여러 메뉴의 비파괴 설정 변경이 모두 적용됨",
            summary["적용됨"] == want_n,
            expected=f"{want_n}개 항목 모두 DB 컬럼에 반영",
            actual=summary,
            note="체크리스트 Step 3 은 '검증 대상 비파괴 설정을 여러 메뉴에서 "
                 "변경한다' 다(2026-08-28 사용자 승인으로 원문을 이 수행에 맞게 "
                 "고쳤다 — 그전에는 '1개'였다). Theme 은 Viewer 전체 색을 바꿔 "
                 "이 저장소의 픽셀/OCR 판정을 무너뜨릴 수 있어 쓰지 않고, "
                 "**7개 메뉴/7개 설정 테이블**을 바꾼다. 바꾸지 않은 테이블은 "
                 "Step 7 의 전수 대조가 아무것도 증명하지 못하기 때문이다"
                 "(변경 범위 = 실제 검증 범위). "
                 "제외 항목과 이유는 core/setting_changes.py 에 적었다. "
                 "항목마다 **DB 컬럼으로** 반영을 확인했다.")

        mid = snapshot.take(ctx.db, snapshot.CONFIG_SECTIONS)
        _same_mid, changed_sections = snapshot.config_identical(pre, mid)
        r.assert_true(
            3, "변경이 서로 다른 설정 테이블에 걸쳐 반영됨",
            set(summary["덮은 설정테이블"]) <= set(changed_sections),
            expected=f"변경한 {len(summary['덮은 설정테이블'])}개 테이블이 "
                     f"DB 차이로 확인됨",
            actual={"실제로 달라진 섹션": sorted(changed_sections),
                    "변경 세트가 덮은 테이블": summary["덮은 설정테이블"]},
            note="Step 7 전수 대조가 실제로 검증하게 될 범위를 여기서 확정한다. "
                 "이 목록이 비면 Step 7 은 통과해도 아무 의미가 없다.")

        ups_target = setting_changes.other_ups_value(ups_baseline)
        ups_changed = setting_changes.set_ups(ui, ups_target)
        # **Update 를 반드시 누른다.** 누르지 않고 `close_setting` 으로 닫으면
        # 저장 확인 팝업에 "저장 안 함" 으로 답해 변경이 버려진다. 그러면 Step 7 의
        # "Export 시점 값으로 복원" 판정은 **바뀐 적 없는 값을 확인하는 빈 판정**이
        # 된다 — 2026-08-25 첫 실행에서 실제로 그렇게 통과했다.
        flows.setting_update(ui, wait=1.8)
        flows.confirm_setting_dialog(ui, required=True)
        # **닫기 전에** 다시 읽는다. 닫고 다시 열면 Setting 창을 한 회차 더
        # 여닫게 되는데, 그 직후 `Setting > System > My Settings` 진입이
        # 레일 항목(193)을 못 찾고 실패했다(2026-08-25 실측).
        ups_saved = setting_changes.read_ups(ui)
        setting_changes.close_setting(ui)
        r.assert_true(
            3, "Setting > Device > UPS 설정 변경이 적용됨",
            ups_target.startswith(ups_saved) and ups_saved != ups_baseline,
            expected=ups_target,
            actual={"변경 전": ups_baseline, "고른 값": ups_changed,
                    "Update 후 다시 읽은 값": ups_saved},
            note="이 항목은 **어느 설정 테이블에도 저장되지 않는다** — 2026-08-25 "
                 "에 CONFIGURATION/ACCOUNT/PROCEDURE 의 모든 문자열 컬럼과 "
                 "`%UPS%` 컬럼명을 뒤져 0건이었고, 레지스트리(Vieworks 트리)와 "
                 "UPSHandler 폴더, `ExternalInput.xml` 에도 없었다. 그래서 "
                 "DB 가 아니라 화면 콤보 값으로 판정한다. 재기동 후에도 값이 "
                 "남으므로 **저장은 되는 설정**이다.")

        if summary["적용됨"] == 0:
            raise RuntimeError(
                "설정이 하나도 바뀌지 않아 Import 판정이 무의미해집니다: "
                f"{summary['실패']}")

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
        # 변경 세트도 System(CONFIGURATION) 과 Procedure(PROCEDURE) 양쪽에
        # 걸쳐 있으므로, 한 범위만 고르면 나머지가 복원되지 않는다.
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
        before_restart = _current_values(ctx.db)

        # --- Step 6 ----------------------------------------------------
        ui, restart = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        ready = flows.ensure_patient_screen(ui)
        r.assert_true(
            6, "Viewer 재시작 후 정상 실행", bool(ready),
            expected="로그인 통과 후 Patient 화면",
            actual={"startup": restart, "patient_screen": bool(ready),
                    "재시작 직전 변경항목 값": before_restart},
            note=specs.cite(ctx, "Import 한 설정은 Viewer를 재시작",
                            fallback="사양서1 60절 — 'Import 한 설정은 Viewer를 "
                                     "재시작해야 적용된다'"))
        if not ready:
            raise RuntimeError("재시작 후 Patient 화면이 준비되지 않았습니다")

        # --- Step 7 ----------------------------------------------------
        post = snapshot.take(ctx.db)
        now = _current_values(ctx.db)
        not_restored = [
            {"메뉴": rec["key"], "항목": rec["label"], "컬럼": rec["column"],
             "기대": rec.get("before"), "실제": now.get(rec["key"])}
            for rec in applied if rec.get("ok")
            and str(now.get(rec["key"])) != str(rec.get("before"))]
        r.assert_true(
            7, "변경한 설정값이 Export 시점 값으로 복원(항목 단위)",
            not not_restored,
            expected={rec["key"]: rec.get("before")
                      for rec in applied if rec.get("ok")},
            actual={"현재값": now,
                    "복원 안 된 항목": not_restored or "없음"},
            note="주 판정. Step 3 에서 바꾼 항목 하나하나가 Export 시점 값으로 "
                 "돌아왔는지 DB 컬럼으로 확인한다. 전수 대조가 통과해도 어느 "
                 "항목이 어떻게 복원됐는지 보고서에 남기기 위해 따로 둔다.")

        same, diff = snapshot.config_identical(pre, post)
        r.assert_true(
            7, "설정 테이블 전수 대조(Export 시점과 동일)", same,
            expected=f"설정 섹션 {len(snapshot.CONFIG_SECTIONS)}개 전부 일치",
            actual="일치" if same else f"불일치 {len(diff)}개 섹션: "
                                     f"{sorted(diff)}",
            note="사양서1 60절이 Export 대상을 'Study 정보를 제외한 모든 설정 "
                 "정보(DB / sql file)'로 정의하므로, 화면 픽셀이 아니라 설정 "
                 "테이블 전수 대조가 결정적 근거다. Step 3 에서 "
                 f"{len(summary['덮은 설정테이블'])}개 테이블을 실제로 바꿨으므로 "
                 "이 대조는 그만큼의 범위를 실제로 검증한다.")
        for sec in sorted(diff):
            r.add(7, f"설정 섹션 [{sec}] 복원", FAIL,
                  expected="Export 시점과 동일",
                  actual=_fmt_section(diff[sec]))

        # Step 7 보강 — 화면 컨트롤 값 항목 단위 대조 (좌표/이미지 비교 아님)
        after_vals = setting_values.read_all(
            ui, tesseract_exe=tess,
            capture_dir=os.path.join(evidence, "pages_after"))
        swept_ok = not (before_vals.get("viewer_died")
                        or after_vals.get("viewer_died"))
        if after_vals.get("viewer_died"):
            ui, _restart = flows.cold_start(ctx.cfg, ctx.db,
                                            force_restart=True)
            flows.ensure_patient_screen(ui)
        vc = setting_values.compare(before_vals, after_vals)
        r.assert_true(
            7, "Setting 전 페이지 순회 중 Viewer 가 종료되지 않음", swept_ok,
            expected="56개 페이지를 두 회차 도는 동안 Viewer 유지",
            actual={"1회차 종료": bool(before_vals.get("viewer_died")),
                    "2회차 종료": bool(after_vals.get("viewer_died")),
                    "1회차 읽은 페이지": len(before_vals["pages"]),
                    "2회차 읽은 페이지": len(after_vals["pages"])},
            note="제품 관찰. Setting 페이지를 순회하면 페이지마다 콘텐츠 패널이 "
                 "새로 생기고 이전 것이 남는다 — 2026-08-25 실측으로 51개 페이지를 "
                 "도는 동안 GDI 객체 348->2886, USER 객체 1433->5610 으로 늘고 "
                 "한 번도 반환되지 않았다. 같은 51페이지 뒤 Q.C. 그룹에 들어가면 "
                 "Viewer 가 종료됐다. 다만 그룹 순서를 뒤집어 Q.C. 를 먼저 읽으면 "
                 "56개 페이지가 모두 정상이었으므로 Q.C. 고유 문제는 아니고, "
                 "3페이지짜리 최소 재현으로도 재현되지 않았다. 원인은 아직 "
                 "특정하지 못했다. 판정을 흐리지 않으려고 **순회 완주 여부를 따로 "
                 "남긴다** — 순회가 중단되면 아래 화면 값 대조의 근거가 불완전하다.")

        # --- Step 7 보강: 목록 행 상세값 (스크롤 아래 숨은 행 포함) --------
        #
        # 2026-08-27 자동화. 그전에는 MANUAL 이었다 — 2026-08-25 에 붙였던 스크롤이
        # 가상 ListItem 의 HWND/ID 재사용 때문에 일부 행만 읽고 끝으로 오인해
        # 사용자 지시로 제거했기 때문이다. 해제 조건이 "이동을 증명하고 겹치는 행을
        # 제거하면서 끝 행 도달을 보장하는 전용 탐색기 + 전후 DB 무변경 시험" 이었고,
        # `core/setting_lists.py` 가 그것이다.
        db_before_lists = snapshot.take(ctx.db)
        after_lists = setting_lists.sweep(ui, ctx.db, LIST_PAGES)
        db_after_lists = snapshot.take(ctx.db)
        lists_readonly, lists_diff = snapshot.config_identical(
            db_before_lists, db_after_lists)

        # (a) 탐색 자체가 무해한가 — 해제 조건의 "전후 DB 무변경 시험".
        r.add(7, "목록 탐색이 설정을 바꾸지 않음(전후 DB 무변경)",
              PASS if lists_readonly else FAIL,
              expected=f"설정 섹션 {len(snapshot.CONFIG_SECTIONS)}개가 목록 탐색 "
                       f"전후로 동일",
              actual="일치" if lists_readonly
                     else f"불일치 {len(lists_diff)}개 섹션: {sorted(lists_diff)}",
              note="행을 선택하는 것은 조회 동작이어야 한다. 그런데 이 제품에는 "
                   "**누르지 않아도 즉시 저장되는 화면**이 있었다 — 2026-08-20 에 "
                   "Hospital Code 의 `+`(2558)가 Update 없이 DB 행을 만들어 사용자 "
                   "DB 에 5행을 남겼다(AGENTS.md 3절). 그래서 탐색을 조회 전용이라 "
                   "가정하지 않고 전후 스냅샷으로 확인한다.",
              stop=False)

        # (b) 전 행을 실제로 봤는가 — 정지·연속·개수 세 증명.
        incomplete = sorted(set(before_lists.get("incomplete") or [])
                            | set(after_lists.get("incomplete") or []))
        r.add(7, "목록 전 행 열거 완주(스크롤 아래 숨은 행 포함)",
              PASS if not incomplete else FAIL,
              expected="후보 목록 페이지 전부에서 정지·연속·개수 증명 통과",
              actual={"1회차": _list_summary(before_lists),
                      "2회차": _list_summary(after_lists),
                      "불완전 페이지": incomplete},
              note="세 겹으로 증명한다 — (1) 스크롤해도 행 시퀀스가 더 바뀌지 "
                   "않는다(끝), (2) 스크롤 전후 시퀀스가 겹친다(건너뛰지 않았다. "
                   "겹치지 않으면 폭을 줄여 재시도하고 그래도 안 겹치면 실패로 "
                   "보고한다), (3) 열거한 행 수가 DB 원천 테이블 행 수와 같다"
                   "(core/setting_lists.ROW_COUNT_QUERIES). (3)은 화면과 무관한 "
                   "결정적 근거라 (1)·(2)가 통과해도 어긋나면 실패다. **불완전한 "
                   "열거는 아래 상세값 대조의 근거로 쓰지 않는다.**",
              stop=False)

        # (c) 본 판정 — 행 상세값이 Export 시점으로 복원되었는가.
        lc = setting_lists.compare_sweep(before_lists, after_lists)
        lc_changed = [item for v in lc["pages"].values() for item in v["changed"]]
        lists_restored = (not lc["changed_total"] and not lc["only_before_pages"]
                          and not lc["only_after_pages"])
        r.add(7, "Setting 목록 행 상세값 복원(스크롤 아래 숨은 행 포함)",
              PASS if lists_restored else FAIL,
              expected=f"{lc['compared_rows']}개 행 / {lc['compared_items']}개 "
                       f"항목 값이 Export 시점과 동일",
              actual={"행": lc["compared_rows"], "항목": lc["compared_items"],
                      "달라진 항목": lc_changed[:20],
                      "한쪽에만 있는 페이지": (lc["only_before_pages"]
                                     + lc["only_after_pages"]),
                      "페이지별 차이": {k: v["changed"] for k, v in
                                  lc["pages"].items() if v["changed"]}},
              note="개정본 Expected 7 을 **목록 행**에도 적용한다. 행을 좌측 첫 열 "
                   "좌표로 선택해(행 가운데 버튼을 피한다 — AGENTS.md 3절) 상세 "
                   "영역의 값을 컨트롤 ID 기준으로 읽고 Import 전후를 항목 단위로 "
                   "대조했다. 장치 상태 칸은 제외한다"
                   "(core/setting_values.VOLATILE_CONTROLS).",
              stop=False)

        screen_restored = (not vc["changed"] and not vc["only_before"]
                           and not vc["only_after"])
        r.add(
            7, "Setting 화면 컨트롤 값 항목 단위 복원(보강 근거)",
            PASS if screen_restored else FAIL,
            expected=f"{vc['compared_pages']}개 페이지 / "
                     f"{vc['compared_items']}개 항목 값 동일",
            actual={"페이지": vc["compared_pages"], "항목": vc["compared_items"],
                    "달라진 항목": vc["changed"][:20],
                    "한쪽에만 있음": (vc["only_before"][:10] +
                                vc["only_after"][:10]),
                    "판독불가(라디오 픽셀)": len(vc["unreadable"]),
                    "장치 상태라 제외": vc["volatile_skipped"],
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
                 "있음' 으로 잡혔고, 그것을 설정 차이로 보고하면 오탐이다. "
                 "'장치 상태라 제외'는 `device.ups` 의 UPS 연결상태·배터리 잔량처럼 "
                 "**설정이 아니라 실시간 장치 상태**를 보여 주는 칸이다 — "
                 "2026-08-25 실행에서 UPS 미연결 때문에 '0 %'/'Power Unknown' 이 "
                 "'Not Connected' 로 바뀌어 이 판정이 FAIL 했다. 판정을 약화시킨 "
                 "것이 아니라 **대상이 아닌 값을 뺀 것**이고, 몇 개를 뺐는지 "
                 "여기에 남긴다(core/setting_values.VOLATILE_CONTROLS).",
            stop=False)

        # 마지막에 둔다 — 앞의 판정을 가리지 않기 위해서다.
        ups_now = setting_changes.read_ups(ui)
        setting_changes.close_setting(ui)
        ups_restored = (str(ups_baseline).strip().lower()
                        == str(ups_now).strip().lower())
        r.add(
            7, "Setting > Device > UPS 설정이 Export 시점 값으로 복원",
            PASS if ups_restored else FAIL, ups_baseline, ups_now,
            note="**제품 결함으로 관찰됨(2026-08-25).** 사양서1 60절은 Export "
                 "대상을 'Study 정보를 제외한 모든 설정 정보' 로 정의하는데, UPS "
                 "설정은 Export 산출물 어디에도 들어가지 않는다 — .vms 안의 20개 "
                 "항목(CONFIGURATION/ACCOUNT/PROCEDURE 백업, ExternalInput.xml, "
                 "PARAMETER*, RECON_PARAMETER, Version.txt)에 UPS 관련이 0건이고, "
                 "설정을 바꿔 Update 해도 설정 테이블 38개 중 어느 것도 바뀌지 "
                 "않는다. 그런데 재기동 후에는 값이 남으므로 **저장은 되는 "
                 "설정**이다. 따라서 Import 로 되돌아올 방법이 없다. "
                 "완화하지 않고 계속 보고한다.",
            stop=False)
        if not screen_restored or not ups_restored:
            raise StepFailed(
                "Step 7 FAIL — 화면 설정값 또는 UPS 설정이 Export 시점 값으로 "
                "복원되지 않았습니다.")

    except Exception as exc:                           # noqa: BLE001
        # `r.abort` 를 쓴다. `r.add(..., FAIL)` 은 `stop_on_fail` 때문에 예외
        # 처리 블록 **안에서 다시 StepFailed 를 던져** TC 밖으로 샌다(2026-08-25
        # 실측 — 단독 실행이 통째로 죽었다). 게다가 `aborted` 가 서지 않아
        # 리포트의 남은 Step 이 '미수행' 으로 채워지지 않는다.
        # 다른 18개 TC 는 이미 `r.abort` 를 쓰고 있었고 이 파일만 예외였다.
        r.abort(0, "TC_Basic_WorkFlow_14 실행", exc)
        path = os.path.join(evidence, "99_error.png")
        try:
            screen.grab((0, 0, 1920, 1080), path=path)
            r.attach(path)
        except Exception:                              # noqa: BLE001
            pass
    finally:
        # --- 상태 복구 -------------------------------------------------
        # Import 가 끝났으면 시작 상태가 이미 복원돼 있다(대부분 "이미 원래 값"
        # 으로 끝난다). Import 전에 실패했다면 바꿔 둔 값이 남으므로 UI 로
        # 되돌린다 — `core/db.py` 는 조회 전용이라 복구도 UI 로만 한다.
        if applied:
            try:
                # **Setting 창을 먼저 닫는다.** 마지막 `read_all` 이 Setting 을
                # 열어 둔 채 끝나므로, 모달이 떠 있는 상태로 Patient 화면을
                # 확인하러 가면 상태바를 찾지 못한다.
                if ui is not None:
                    setting_changes.close_setting(ui)
                if ui is None or not flows.ensure_patient_screen(ui):
                    ui, _ = flows.cold_start(ctx.cfg, ctx.db,
                                             force_restart=True)
                    flows.ensure_patient_screen(ui)
                restored = setting_changes.restore_all(ui, ctx.db, applied)
                if ups_baseline:
                    # Import 가 되돌려 주지 못하는 항목이므로 **반드시** 손으로
                    # 되돌린다. 안 그러면 다음 회귀가 바뀐 값을 물려받는다.
                    setting_changes.set_ups(ui, ups_baseline)
                    flows.setting_update(ui, wait=1.8)
                    flows.confirm_setting_dialog(ui, required=True)
                setting_changes.close_setting(ui)
            except Exception as exc:                   # noqa: BLE001
                r.cleanup(0, "정리: 변경 설정 원복", FAIL,
                          expected=f"{len(applied)}개 항목 모두 Export 시점 값",
                          actual=f"복구 실패 {type(exc).__name__}: {exc}",
                          note="정리 실패는 FAIL 로 남기되 흐름을 끊지 않는다"
                               "(`TCResult.cleanup`). 다음 TC 가 오염된 설정을 "
                               "물려받을 수 있으니 사람이 확인해야 한다.")
            else:
                failed = [e for e in restored if not e.get("ok")]
                r.cleanup(0, "정리: 변경 설정 원복",
                          PASS if not failed else FAIL,
                          expected=f"{len(restored)}개 항목 모두 Export 시점 값",
                          actual={"원복 실패": failed or "없음",
                                  "결과": {e["key"]: e.get("actual")
                                         for e in restored}},
                          note="Import 전에 중단되면 변경값이 남아 다음 TC 의 "
                               "설정 대조를 오염시킨다. Import 가 정상이면 이미 "
                               "원래 값이라 대부분 조작 없이 끝난다."
                               + (" Import 로 이미 복원된 상태였다."
                                  if imported else ""))
    return r


def _current_values(db):
    """변경 세트 각 항목의 현재 DB 값(키 -> 값)."""
    out = {}
    for item in setting_changes.CHANGE_PLAN:
        try:
            out[item.key] = setting_changes.db_value(db, item)
        except Exception as exc:                       # noqa: BLE001
            out[item.key] = f"판독 실패: {exc}"
    return out


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
