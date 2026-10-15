# -*- coding: utf-8 -*-
"""Windows Update 호환성 검증 체크리스트 자동화 — 매핑 계층.

기준 문서: `..\\..\\Windows Update 호환성 검증 Checklist_Bellalun Viewer_R-25-782.xlsx`
시트 `Checklist`, TC_WindowsUpdate_01~13 (6~18행).

**신규 검증 TC를 만들지 않는다.** 이미 검증된 기본기능/XIPL `TCResult` 를
재사용하고, WU Expected Result 기준으로 재판정하는 얇은 매핑 계층이다(예외:
TC_WindowsUpdate_09 의 USB Import, TC_WindowsUpdate_10 은 대응하는 기존 TC가
없어 이 파일에 직접 구현했다 — 매핑 표에 이미 "신규 필요"로 명시됨).

실행 경로는 둘이다 — `run.py run-winupdate`(전용 체인, 실제 UI 실행)와
`run-winupdate --from-regression <json>`(이미 끝난 전체 회귀 결과 재사용).
**둘 다 이 모듈의 `build_wu_results()` 하나를 공유한다** — 매핑 로직을 두
곳에 복제하지 않는다.

## 판정 정책

WU 판정은 **WU Expected Result** 기준이다. 재사용한 원본 TC 의 verdict 를
그대로 승계하지 않는다 — 원본 TC 의 개별 Check 를 그대로 복사해 오되, WU
Expected 가 요구하지 않는 항목에서 난 FAIL 중 **사용자가 이미 확인한 2건만**
`KNOWN_DEFECT_EXCLUDE` 에 등록해 WU 집계에서 뺀다(대신 Issues 시트에 반드시
남는다). 다른 FAIL 은 전부 그대로 WU 판정에 반영된다 — 임의로 더 빼지
않는다.
"""

import os
from pathlib import Path
import time

from core.result import TCResult, PASS, FAIL, MANUAL, SKIP, BLOCKED

WU_TITLES = {
    "TC_WindowsUpdate_01": "패키지 설치 확인",
    "TC_WindowsUpdate_02": "MWL 조회",
    "TC_WindowsUpdate_03": "영상 조작",
    "TC_WindowsUpdate_04": "Image Processing(2D)",
    "TC_WindowsUpdate_05": "Image Processing(3D)",
    "TC_WindowsUpdate_06": "DICOM 전송(2D)",
    "TC_WindowsUpdate_07": "DICOM 전송(3D)",
    "TC_WindowsUpdate_08": "DICOM Print",
    "TC_WindowsUpdate_09": "Study Export",
    "TC_WindowsUpdate_10": "Setting 화면 표시",
    "TC_WindowsUpdate_11": "Setting Import/Export",
    "TC_WindowsUpdate_12": "OS User 계정",
    "TC_WindowsUpdate_13": "KIOSK 설정",
}

# (기존 TC ID, title) -> 이 WU 판정에서 빼는 이유. WU Expected 가 요구하지
# 않는데 원본에서 FAIL 나는 **이미 확인된** 제품 결함만 등록한다. Step 번호가
# 아니라 title 로 키를 잡는다 — 같은 결함을 여러 판독 방식(값 단위/화면 전체
# 스캔 등)으로 중복 확인하는 check 가 여러 개 있을 수 있어서다(실측:
# `Setting > Device > UPS 설정이 Export 시점 값으로 복원`과 `Setting 화면
# 컨트롤 값 항목 단위 복원(보강 근거)` 둘 다 같은 UPS 결함으로 FAIL 한다).
KNOWN_DEFECT_EXCLUDE = {
    ("TC_Basic_WorkFlow_14",
     "Setting > Device > UPS 설정이 Export 시점 값으로 복원"): {
        "wu_tc": "TC_WindowsUpdate_11",
        "kind": "기존 알려진 제품 결함",
        "detail": "Setting Export/Import 시 UPS 설정(Setting > Device > UPS)이 "
                  "복원되지 않는다.",
        "impact": "WU_11 Expected는 '1시점의 Setting이 반영된다'만 요구하고 "
                  "UPS를 특정하지 않아 WU 판정에서는 제외한다(원본 WF_14는 "
                  "FAIL 그대로 유지 — 기본기능 판정은 안 바꾼다).",
        "basis": "tests/workflow14.py Step 7. NEXT_WORK.md 3-A / B.22.",
    },
    ("TC_Basic_WorkFlow_14",
     "Setting 화면 컨트롤 값 항목 단위 복원(보강 근거)"): {
        "wu_tc": "TC_WindowsUpdate_11",
        "kind": "기존 알려진 제품 결함",
        "detail": "위와 같은 UPS 결함을 화면 전체 컨트롤 값 스캔으로 다시 "
                  "확인하는 보강 check — 달라진 항목이 device.ups 하나뿐일 "
                  "때만 같은 결함으로 본다.",
        "impact": "WU_11 판정에서는 제외한다(원본 WF_14는 FAIL 유지).",
        "basis": "tests/workflow14.py Step 7 보강 근거. NEXT_WORK.md 3-A.",
    },
    ("TC_XIPL_compatibility_03",
     "Apply 후 TEST_3D 이름과 Recon/Syn 10개 값 유지"): {
        "wu_tc": "TC_WindowsUpdate_05",
        "kind": "기존 알려진 제품 결함",
        "detail": "3D Post Reconstruction Apply 후 재진입하면 선택했던 "
                  "파라미터가 기본값으로 되돌아간다(유지되지 않는다).",
        "impact": "WU_05 Expected는 'Image에 적용된다'만 요구하고 재진입 시 "
                  "유지 여부는 요구하지 않아 WU 판정에서는 제외한다(원본 "
                  "XIPL_03은 FAIL 그대로 유지).",
        "basis": "tests/xipl_flows.py compatibility_03 Step 9. NEXT_WORK.md 3절 #2.",
    },
}


def _view(obj):
    """TCResult 또는 회귀 JSON `results[i]` dict를 같은 인터페이스로 감싼다."""
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    return obj


def lookup_from_results(underlying_results):
    """tc_id -> view dict. `run()`(라이브) 과 `from_regression()`(JSON) 이 공유."""
    return {v["tc_id"]: v for v in (_view(r) for r in underlying_results)}


def lookup_from_regression_json(data):
    """`Reports/Result_*.json` 의 최상위 dict -> tc_id -> view dict."""
    return {item["tc_id"]: item for item in (data.get("results") or [])}


def _copy_checks(wu_result, view, basis_label, only_steps=None, exclude_keys=None,
                 abort_keyword=None):
    """원본 TC 의 check 를 WU TCResult 로 복사한다.

    `exclude_keys` 에 있는 (tc_id, title) 은 **복사하지 않는다**(알려진 제품
    결함 — WU 집계에서 뺀다. Issues 시트에는 별도로 실린다). Step 번호가
    아니라 title 로 매칭한다 — 같은 결함을 여러 판독 방식으로 중복 확인하는
    check 가 있어도(예: 값 단위 확인 + 화면 전체 스캔) Step 번호에 기대지 않고
    둘 다 잡는다.

    `abort_keyword` 를 주면, **다른 FAIL 이 전혀 없고**(=이 결함이 유일한
    원인일 때만) `TCResult.abort()` 가 남긴 cascading 중단 기록(FAIL 이고
    `actual`/`title` 에 이 키워드가 있음)도 함께 뺀다 — 원본 TC 는 결함 하나
    때문에 Step 을 다 못 돌고 중단했는데, 그 중단 기록까지 WU 로 넘기면
    "판정 근거 없이 FAIL" 처럼 보인다. `abort()` 호출 규약(제목·Step 번호)이
    TC 파일마다 달라(예: workflow14 는 Step 0 "... 실행", xipl_flows 는 Step 1
    "... 수행") 키워드 포함 여부만 본다 — 대신 **다른 FAIL 이 하나라도 있으면**
    (=이 결함 말고 다른 문제도 있었다는 뜻) 안전하게 그대로 둔다.

    `stop=False` 로 넣는다 — 이미 끝난 판정을 재현하는 것이라 여기서 다시
    StepFailed 를 던지면 안 된다(TCResult.stop_on_fail 이 True 여도 안전).
    """
    exclude_keys = exclude_keys or set()
    if view is None:
        wu_result.add(0, f"[{basis_label}] 근거 TC 결과 없음", FAIL,
                      expected="재사용 대상 TC 결과 존재",
                      actual="회귀/실행 결과에서 찾지 못함", stop=False)
        return 0
    tc_id = view["tc_id"]
    checks = view["checks"]

    def _is_cascading_abort(check):
        if not abort_keyword or check.get("status") != "FAIL":
            return False
        if (tc_id, check.get("title")) in exclude_keys:
            return False  # 이미 title 매칭으로 빠지는 것과는 별개로 센다
        text = str(check.get("title") or "") + str(check.get("actual") or "")
        return abort_keyword in text

    other_fail_exists = any(
        c.get("status") == "FAIL" and (tc_id, c.get("title")) not in exclude_keys
        and not _is_cascading_abort(c) for c in checks)

    copied = 0
    for check in checks:
        step = check.get("step")
        if only_steps is not None and step not in only_steps:
            continue
        key = (tc_id, check.get("title"))
        if key in exclude_keys:
            continue
        if not other_fail_exists and _is_cascading_abort(check):
            continue
        wu_result.add(
            step, f"[{tc_id}] {check.get('title')}",
            check.get("status"), expected=check.get("expected"),
            actual=check.get("actual"), note=check.get("note"), stop=False)
        copied += 1
    return copied


def _attach_known_issues(wu_result, view, exclude_keys):
    """이번 실행에서 **실제로 FAIL 난** 알려진 결함만 Issues 탭에 싣는다.

    title 이 `KNOWN_DEFECT_EXCLUDE`에 등록돼 있어도 이번 실행에서 그
    check 가 PASS 였다면(결함이 재현되지 않았다면) Issues 에 올리지 않는다
    — 재현 안 된 실행까지 "알려진 결함"으로 표시하면 오해를 준다.
    """
    if view is None:
        return
    tc_id = view["tc_id"]
    issues = []
    for check in view["checks"]:
        key = (tc_id, check.get("title"))
        if (key in exclude_keys and key in KNOWN_DEFECT_EXCLUDE
                and check.get("status") == "FAIL"):
            item = dict(KNOWN_DEFECT_EXCLUDE[key])
            item["tc_id"] = wu_result.tc_id
            item.setdefault("detail", check.get("title"))
            issues.append(item)
    if issues:
        existing = getattr(wu_result, "wu_known_issues", None) or []
        wu_result.wu_known_issues = existing + issues


def _basis_line(*views):
    parts = []
    for v in views:
        if v is not None:
            parts.append(f"{v['tc_id']}={v['verdict']}")
        else:
            parts.append("(결과 없음)")
    return " + ".join(parts)


def _wu_02(lookup):
    r = TCResult("TC_WindowsUpdate_02", WU_TITLES["TC_WindowsUpdate_02"])
    wf01, wf02, wf04 = (lookup.get("TC_Basic_WorkFlow_01"),
                        lookup.get("TC_Basic_WorkFlow_02"),
                        lookup.get("TC_Basic_WorkFlow_04"))
    _copy_checks(r, wf01, "TC_Basic_WorkFlow_01")
    # WF_02 의 Step 6/7(Tool 적용)은 TC_WindowsUpdate_03 소관이라 여기서는 뺀다
    # (같은 증거를 두 WU 행에 중복 귀속시키지 않는다).
    if wf02 is not None:
        exclude = {6, 7}
        for check in wf02["checks"]:
            if check.get("step") in exclude:
                continue
            r.add(check.get("step"), f"[TC_Basic_WorkFlow_02] {check.get('title')}",
                 check.get("status"), expected=check.get("expected"),
                 actual=check.get("actual"), note=check.get("note"), stop=False)
    else:
        _copy_checks(r, wf02, "TC_Basic_WorkFlow_02")
    _copy_checks(r, wf04, "TC_Basic_WorkFlow_04")
    r.wu_basis = _basis_line(wf01, wf02, wf04)
    return r


def _wu_03(lookup):
    r = TCResult("TC_WindowsUpdate_03", WU_TITLES["TC_WindowsUpdate_03"])
    wf02 = lookup.get("TC_Basic_WorkFlow_02")
    _copy_checks(r, wf02, "TC_Basic_WorkFlow_02", only_steps={6, 7})
    r.wu_basis = (f"TC_Basic_WorkFlow_02 Step 6/7(Tool 적용) — "
                  f"{_basis_line(wf02)}")
    return r


def _wu_04(lookup):
    r = TCResult("TC_WindowsUpdate_04", WU_TITLES["TC_WindowsUpdate_04"])
    views = [lookup.get(t) for t in ("TC_XIPL_compatibility_02",
                                     "TC_XIPL_compatibility_04",
                                     "TC_XIPL_compatibility_06")]
    for v in views:
        _copy_checks(r, v, v["tc_id"] if v else "?")
    r.wu_basis = _basis_line(*views)
    return r


def _wu_05(lookup):
    r = TCResult("TC_WindowsUpdate_05", WU_TITLES["TC_WindowsUpdate_05"])
    xipl03, xipl07 = (lookup.get("TC_XIPL_compatibility_03"),
                      lookup.get("TC_XIPL_compatibility_07"))
    _copy_checks(r, xipl03, "TC_XIPL_compatibility_03",
                exclude_keys=KNOWN_DEFECT_EXCLUDE, abort_keyword="TEST_3D")
    _copy_checks(r, xipl07, "TC_XIPL_compatibility_07")
    _attach_known_issues(r, xipl03, KNOWN_DEFECT_EXCLUDE)
    r.wu_basis = _basis_line(xipl03, xipl07)
    return r


def _wu_06(lookup):
    r = TCResult("TC_WindowsUpdate_06", WU_TITLES["TC_WindowsUpdate_06"])
    wf04, wf06 = lookup.get("TC_Basic_WorkFlow_04"), lookup.get("TC_Basic_WorkFlow_06")
    _copy_checks(r, wf04, "TC_Basic_WorkFlow_04")
    _copy_checks(r, wf06, "TC_Basic_WorkFlow_06")
    r.wu_basis = _basis_line(wf04, wf06)
    return r


def _wu_07(lookup):
    r = TCResult("TC_WindowsUpdate_07", WU_TITLES["TC_WindowsUpdate_07"])
    wf05, wf06 = lookup.get("TC_Basic_WorkFlow_05"), lookup.get("TC_Basic_WorkFlow_06")
    _copy_checks(r, wf05, "TC_Basic_WorkFlow_05")
    _copy_checks(r, wf06, "TC_Basic_WorkFlow_06")
    r.wu_basis = _basis_line(wf05, wf06)
    return r


def _wu_08(lookup):
    r = TCResult("TC_WindowsUpdate_08", WU_TITLES["TC_WindowsUpdate_08"])
    wf08 = lookup.get("TC_Basic_WorkFlow_08")
    _copy_checks(r, wf08, "TC_Basic_WorkFlow_08")
    r.wu_basis = _basis_line(wf08)
    return r


def _wu_09(lookup, usb_outcome):
    r = TCResult("TC_WindowsUpdate_09", WU_TITLES["TC_WindowsUpdate_09"])
    wf09 = lookup.get("TC_Basic_WorkFlow_09")
    _copy_checks(r, wf09, "TC_Basic_WorkFlow_09")
    r.skip(0, "CD Export/Import",
          "공디스크·버너는 무인 실행에서 보장되지 않는다(사용자 확정) — "
          "CD 경로는 자동화 대상이 아니다.",
          expected="사용자 수동 확인", actual="자동화 대상 아님")
    if usb_outcome is None:
        r.skip(0, "USB Export/Import",
              "run-winupdate --from-regression 변환 경로에는 USB 결과가 "
              "없다(과거 회귀에는 이 항목이 없었다) — run-winupdate로 직접 "
              "실행해야 확인할 수 있다.",
              expected="USB 드라이브로 Export 후 되읽기 Import",
              actual="이 실행 경로에서는 수행하지 않음")
    elif usb_outcome.get("error"):
        r.add(0, "USB Export/Import", FAIL,
             expected="USB 드라이브로 Export 후 되읽기 Import",
             actual=usb_outcome["error"], stop=False,
             note=f"드라이브 {usb_outcome.get('drive')} 실행 중 예외 발생.")
    elif usb_outcome.get("drive") is None:
        r.skip(0, "USB Export/Import",
              "이 PC에 이동식(USB) 드라이브가 꽂혀 있지 않아 건너뛴다"
              "(GetDriveTypeW 기준, 사용자 확정 정책).",
              expected="USB 드라이브 존재", actual="이동식 드라이브 없음")
    else:
        export_ok = bool(usb_outcome.get("export", {}).get("files"))
        r.assert_true(
            0, "USB Export",
            export_ok,
            expected=f"{usb_outcome['drive']} 에 IMG 파일 생성",
            actual=usb_outcome.get("export"),
            note="core/export_manager.py 재사용, 경로만 USB 드라이브로 지정.")
        imp = usb_outcome.get("import") or {}
        if imp.get("error"):
            r.add(0, "USB Import 되읽기", FAIL,
                  expected="Import Study 목록에 대상 검사 표시 후 Import 수행",
                  actual=imp, stop=False,
                  note="되읽기 절차 실행 중 예외. core/usb_media.py 참고.")
        elif not imp.get("rows"):
            r.add(0, "USB Import 되읽기", FAIL,
                  expected="Import Study 목록에 대상 검사 표시",
                  actual=imp, stop=False,
                  note="폴더 찾아보기로 경로를 확정했는데도 목록이 비었다. "
                       "Export 산출물이 IMG 포맷인지 확인할 것 — plain DICOM/"
                       "DICOMDIR 은 이 목록에 잡히지 않는다(2026-09-09 실측).")
        elif not imp.get("imported_clicked"):
            r.add(0, "USB Import 되읽기", FAIL,
                  expected="목록의 대상 행을 선택하고 Import 수행",
                  actual=imp, stop=False,
                  note="목록에는 행이 나타났으나 Import 를 수행하지 못했다.")
        elif imp.get("evidence") is not None:
            from core.usb_verification import verify_import_evidence
            evidence = imp["evidence"]
            if isinstance(evidence, dict):
                verification = verify_import_evidence(
                    evidence.get("before"), evidence.get("after"),
                    evidence.get("completion"), evidence.get("examined"),
                    export_inventory=usb_outcome.get("export", {}).get("inventory"),
                    expected_studies=1)
            else:
                verification = {"ok": False, "reason": "수집한 Import 근거의 형식이 잘못되었습니다."}
            r.add(0, "USB Import 되읽기", PASS if verification["ok"] else FAIL,
                  expected="완료 신호·재생성 UID·영상 파일·Examined 신규 검사 일치",
                  actual={"import": imp, "verification": verification}, stop=False,
                  note=verification["reason"])
        else:
            # Import 클릭과 중복 팝업 처리까지는 자동화했지만, 되읽기 **완료**를
            # 교차 확인하는 단계(Examined 재검색 등)를 아직 붙이지 못했다
            # (2026-09-09, 사용자 요청으로 그 직전에 중단). 클릭만으로 PASS 를
            # 주지 않는다 — 이 저장소는 로그 한 줄로 PASS 를 판정하지 않는다.
            r.manual(
                0, "USB Import 되읽기",
                "Import Study 목록에 대상 검사가 나타났고 행 선택 후 Import 를 "
                "수행했다(중복 팝업이 뜨면 'Use existing data' 처리). 되읽기 "
                "**완료** 여부를 Examined 재검색으로 교차 확인하는 단계는 아직 "
                "구현하지 않았다 — 그 부분만 사람이 확인한다.",
                expected="뷰어로 import 성공",
                actual=imp)
    r.wu_basis = _basis_line(wf09) + " + USB 신규 로직(core/usb_media.py)"
    return r


def _wu_10(live_result):
    if live_result is not None:
        live_result.wu_basis = "신규 구현 — setting_values.read_all + 탭 빠른 클릭"
        return live_result
    r = TCResult("TC_WindowsUpdate_10", WU_TITLES["TC_WindowsUpdate_10"])
    r.skip(0, "Setting 화면 표시",
          "run-winupdate --from-regression 변환 경로에는 이 항목이 없다"
          "(과거 회귀에는 없던 신규 TC) — run-winupdate로 직접 실행해야 "
          "확인할 수 있다.",
          expected="9개 그룹 전 페이지 정상 표시 + 탭 빠른 전환",
          actual="이 실행 경로에서는 수행하지 않음")
    r.wu_basis = "신규 구현 — 이 실행에서는 미수행"
    return r


def _wu_11(lookup):
    r = TCResult("TC_WindowsUpdate_11", WU_TITLES["TC_WindowsUpdate_11"])
    wf14 = lookup.get("TC_Basic_WorkFlow_14")
    _copy_checks(r, wf14, "TC_Basic_WorkFlow_14", exclude_keys=KNOWN_DEFECT_EXCLUDE,
                abort_keyword="UPS")
    _attach_known_issues(r, wf14, KNOWN_DEFECT_EXCLUDE)
    r.wu_basis = _basis_line(wf14)
    return r


def _wu_01(lookup):
    r = TCResult("TC_WindowsUpdate_01", WU_TITLES["TC_WindowsUpdate_01"])
    install1, install2 = (lookup.get("TC_Basic_Install_01"),
                          lookup.get("TC_Basic_Install_02"))
    from core import sysinfo
    pc = sysinfo.pc_info()
    upd = sysinfo.os_update_info()
    ref = {
        "Install_01 판정": (install1 or {}).get("verdict", "결과 없음"),
        "Install_02 판정": (install2 or {}).get("verdict", "결과 없음"),
        "실측 OS": pc.get("os_caption"),
        "실측 OS Build": upd.get("build_full") or pc.get("os_build"),
    }
    r.manual(
        0, "OS Update 수행과 패키지 설치는 사람이 직접 확인한다",
        "**사용자 지정 수동 TC.** OS Update 수행과 패키지 설치 행위 자체는 "
        f"사람 몫이라 자동화 대상이 아니다(TC_Basic_WorkFlow_16과 같은 방식). "
        f"참고 근거: {ref}",
        expected="시험자가 WU 체크리스트 Step 1을 수동 수행",
        actual="자동화 미수행 (사용자 지정 수동, 참고 근거 첨부)")
    r.wu_basis = f"참고: TC_Basic_Install_01/02, core.sysinfo"
    return r


def _wu_12():
    r = TCResult("TC_WindowsUpdate_12", WU_TITLES["TC_WindowsUpdate_12"])
    r.manual(
        0, "OS User 계정 로그인/권한 확인은 사람이 직접 확인한다",
        "**사용자 지정 수동 TC(2026-09-07 사용자 확정).** OS User 그룹 "
        "계정은 스스로를 승격할 수 없고, UI 자동화는 그 계정의 대화형 세션 "
        "안에서만 동작해 완전 자동화가 불가능하다고 판단했다.",
        expected="시험자가 WU 체크리스트 Step 1~3을 수동 수행",
        actual="자동화 미수행 (사용자 지정 수동)")
    r.wu_basis = "자동화 대상 아님(사용자 확정)"
    return r


def _wu_13():
    r = TCResult("TC_WindowsUpdate_13", WU_TITLES["TC_WindowsUpdate_13"])
    r.manual(
        0, "KIOSK 모드 설정/해제와 System Launcher는 사람이 직접 확인한다",
        "**사용자 지정 수동 TC.** 기본기능 TC_Basic_WorkFlow_16과 동일한 "
        "사유(시스템 재기동·KIOSK 전환·Shutdown 등 파괴적 동작)로 이미 "
        "사용자 지정 수동이다.",
        expected="시험자가 WU 체크리스트 Step 1~7을 수동 수행",
        actual="자동화 미수행 (사용자 지정 수동)")
    r.wu_basis = "자동화 대상 아님(TC_Basic_WorkFlow_16과 동일 사유)"
    return r


def build_wu_results(lookup, live_extra=None):
    """13개 WU TCResult 를 만든다. `run()`/`from_regression()` 공유 진입점."""
    live_extra = live_extra or {}
    return [
        _wu_01(lookup),
        _wu_02(lookup),
        _wu_03(lookup),
        _wu_04(lookup),
        _wu_05(lookup),
        _wu_06(lookup),
        _wu_07(lookup),
        _wu_08(lookup),
        _wu_09(lookup, live_extra.get("usb")),
        _wu_10(live_extra.get("wu10")),
        _wu_11(lookup),
        _wu_12(),
        _wu_13(),
    ]


# ---------------------------------------------------------------------
# TC_WindowsUpdate_10 — 신규 구현 (대응하는 기존 TC 없음)
# ---------------------------------------------------------------------

def _quick_tab_check(ui):
    """탭을 빠르게 오가도 선택한 탭 화면이 바르게 표시되는지 본다(신규 로직).

    인접한 두 그룹을 A→B→A 순서로 **정상보다 훨씬 짧은 대기(0.15초)**로 빠르게
    전환하며, 매 클릭 뒤 (1) 그 탭이 활성 강조 표시인지(`screen.radio_selected`)
    (2) 공통 Update 버튼(2226)이 보여 콘텐츠가 실제로 그려졌는지를 함께 본다.
    """
    from core import flows, screen
    order = list(flows.SETTING_GROUPS.items())
    results = []
    for i in range(len(order) - 1):
        (name_a, id_a), (name_b, id_b) = order[i], order[i + 1]
        for name, cid in ((name_a, id_a), (name_b, id_b), (name_a, id_a)):
            hits = [c for c in ui.by_id(cid) if c.visible]
            if not hits:
                results.append({"pair": f"{name_a}->{name_b}", "clicked": name,
                                "ok": False, "reason": "탭 컨트롤 없음"})
                continue
            ui.click(hits[0], settle=0.15)
            active = screen.radio_selected(hits[0])
            rendered = bool([c for c in ui.by_id(flows.SETTING_UPDATE_BUTTON)
                            if c.visible])
            results.append({"pair": f"{name_a}->{name_b}", "clicked": name,
                            "ok": bool(active) and rendered,
                            "active": active, "content_rendered": rendered})
    return results


def run_setting_display(ctx, ui):
    """TC_WindowsUpdate_10 — Setting 화면 표시. `run-winupdate` 전용 체인에서만 호출."""
    from core import flows, setting_changes, setting_values

    r = TCResult("TC_WindowsUpdate_10", WU_TITLES["TC_WindowsUpdate_10"])
    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    failure_cause = None
    try:
        if not flows.ensure_patient_screen(ui):
            raise flows.FlowError("Patient 화면이 준비되지 않았습니다.")
        sweep = setting_values.read_all(ui, tesseract_exe=tess)
        missing = sweep.get("missing") or {}
        pages = sweep.get("pages") or {}
        expected_pages = {f"{group}.{page}" for group in flows.SETTING_GROUPS
                          for page in flows.setting_pages(group)}
        actual_pages = set(pages)
        renders = sweep.get("page_render") or {}
        rendered_pages = set(renders)
        empty_pages = sorted(name for name in expected_pages & actual_pages
                             if not setting_values.page_rendered(renders.get(name)))
        complete = (bool(pages) and actual_pages == expected_pages and not empty_pages
                    and rendered_pages == expected_pages
                    and not sweep.get("viewer_died") and not missing)
        r.assert_true(
            1, "Setting 전 메뉴/하위 메뉴 정상 오픈",
            complete,
            expected="9개 그룹 전 페이지 정상 오픈, 안정화된 패널별 실제 콘텐츠 존재, Viewer 생존",
            actual={"pages": len(pages), "expected_pages": len(expected_pages),
                    "missing": missing, "unvisited": sorted(expected_pages - actual_pages),
                    "unexpected": sorted(actual_pages - expected_pages),
                    "empty_pages": empty_pages, "page_render": renders,
                    "render_unvisited": sorted(expected_pages - rendered_pages),
                    "render_unexpected": sorted(rendered_pages - expected_pages),
                    "viewer_died": sweep.get("viewer_died")},
            note="setting_values.read_all 전수 순회를 그대로 재사용한다(경량화 "
                 "하지 않는다 — 사용자 지시). NEXT_WORK.md 3-B 간헐 종료가 "
                 "재현되면 축소하지 않고 이 판정에 그대로 남긴다.")

        if not flows.ensure_patient_screen(ui):
            raise flows.FlowError("Setting 순회 후 Patient 화면으로 돌아오지 못했습니다.")
        flows.open_setting(ui)
        quick = _quick_tab_check(ui) or []
        expected_quick_count = (len(flows.SETTING_GROUPS) - 1) * 3
        failed_quick = [item for item in quick if not isinstance(item, dict)
                        or item.get("ok") is not True]
        ok = (bool(quick) and len(quick) == expected_quick_count and not failed_quick)
        r.assert_true(
            2, "탭을 빠르게 클릭해도 선택한 탭 화면이 바르게 표시",
            ok,
            expected="인접 탭 빠른 전환(A→B→A, 0.15초 간격) 전 구간 활성표시+콘텐츠 렌더",
            actual={"checked": len(quick), "expected": expected_quick_count,
                    "failed": failed_quick},
            note="신규 로직 — 대응하는 기존 TC가 없다(매핑 표에 '신규 필요'로 "
                 "명시). Setting > System 탭(177)부터 QC 탭(185)까지 인접 쌍을 "
                 "전부 오간다.")
    except Exception as exc:
        failure_cause = f"{type(exc).__name__}: {exc}"
        r.abort(0, "TC_WindowsUpdate_10 실행", exc,
                note="본 시험의 실패 원인을 유지하고 Setting 화면 정리는 finally에서 수행한다.")
    finally:
        try:
            if setting_changes.close_setting(ui) is False:
                raise flows.FlowError("Setting 화면이 닫히지 않았습니다.")
        except Exception as cleanup_error:
            r.cleanup(0, "Setting 화면 정리", FAIL,
                      expected="Setting 화면 닫힘",
                      actual=f"{type(cleanup_error).__name__}: {cleanup_error}",
                      note=f"본 시험 오류: {failure_cause or '없음'}. "
                           "앞선 시험 판정은 유지하며 정리 실패를 별도로 기록한다.")
    return r


# ---------------------------------------------------------------------
# TC_WindowsUpdate_09 — USB Export/Import 보조 (WF_09 는 그대로 재사용,
# USB 매체 왕복만 이 함수가 새로 담당한다)
# ---------------------------------------------------------------------

# USB 왕복 전용 폴더. **드라이브 바로 아래 1단계**여야 한다(Import 되읽기
# 제약 — core/usb_media.py 참고). 매 실행 비우고 다시 만든다.
USB_EXPORT_FOLDER = "BellalunWU09"

def run_usb_export_import(ctx, ui, patient_id="DATA_FLOW_MWL_01"):
    """USB 드라이브가 꽂혀 있으면 Export→Import 를 시도하고 결과를 돌려준다.

    반환: {"drive": str|None, "export": {...}|None, "import": {...}|None}
    드라이브가 없으면 `{"drive": None}` 만 돌려준다(호출부가 SKIP으로 기록).
    """
    from core import usb_media, usb_paths, usb_evidence, export_manager as em, flows
    from tests.workflow03 import _open_examined
    result = {"drive": None, "export": None, "import": None,
              "cleanup": {"ok": True, "errors": []}}
    export_opened = False
    import_requested = False

    def record_error(stage, error):
        message = f"{stage}: {type(error).__name__}: {error}"
        original = (result.get("import") or {}).get("error")
        if not result.get("error"):
            result["error"] = original or message
        result.setdefault("errors", []).append(message)

    def cleanup_error(message):
        result["cleanup"]["ok"] = False
        result["cleanup"]["errors"].append(message)
        if not result.get("error"):
            result["error"] = f"USB 정리 실패: {message}"

    try:
        drive = usb_media.find_usb_drive()
        result["drive"] = drive
        if drive is None:
            return {"drive": None}
        # Guarded cleanup rejects path escapes, links/junctions and traversal
        # before touching the sole automation-owned child of a USB drive root.
        target, cleared = usb_paths.prepare_export_folder(drive)
        if not flows.ensure_patient_screen(ui, wait=3):
            raise flows.FlowError("Patient 화면이 준비되지 않았습니다(USB Export 전).")
        _open_examined(ui)
        rows = flows.examined_search(ui, patient_id)
        if not rows:
            raise flows.FlowError("시험 환자의 Examined 검색 결과가 없습니다.")
        ui.click(rows[0], settle=1.2)
        button = [c for c in ui.by_id(2191) if c.visible]
        if len(button) != 1:
            raise flows.FlowError("유일한 Export 버튼(2191)을 찾지 못했습니다.")
        export_opened = True
        ui.click(button[0], settle=3)
        manager = em.attach()
        path = em.set_path(manager, target)
        if em.is_checked(manager, em.OPT_PORTABLE_VIEWER) is True:
            # DICOMDIR enables this option so it can be explicitly turned off.
            em.select_format(manager, em.FORMAT_DICOMDIR)
        portable = em.set_portable_viewer(manager, False)
        anonymous = em.set_anonymous(manager, False)
        fmt = em.select_only_format(manager, em.FORMAT_IMG)
        format_states = {format_id: em.is_checked(manager, format_id) for format_id in em.ALL_FORMATS}
        if (portable.get("final") is not False or anonymous.get("final") is not False
                or fmt.get("selected", {}).get("final") is not True
                or any(checked is not (format_id == em.FORMAT_IMG) for format_id, checked in format_states.items())
                or any(value.get("final") is not False for value in fmt.get("turned_off", {}).values())):
            raise flows.FlowError("IMG 단독·Anonymous 해제·Portable Viewer 해제 상태를 확인하지 못했습니다.")
        outcome = em.export(manager, wait=180)
        inventory = []
        for image in sorted(Path(target).rglob("*")):
            if image.suffix.lower() != ".img":
                continue
            item = {"path": str(image), "exists": image.is_file(), "readable": False, "size": 0}
            try:
                item["size"] = image.stat().st_size
                with image.open("rb") as stream:
                    item["readable"] = bool(stream.read(1)) and item["size"] > 0
            except OSError as error:
                item["error"] = f"{type(error).__name__}: {error}"
            inventory.append(item)
        files = [item["path"] for item in inventory if item["exists"] and item["readable"] and item["size"] > 0]
        result["export"] = {"path": path, "files": files, "inventory": inventory, "format": fmt,
                            "format_states": format_states,
                            "anonymous": anonymous, "portable_viewer": portable,
                            "cleared": cleared, "outcome_files": outcome.get("files")}
        if not inventory or len(files) != len(inventory):
            raise flows.FlowError("Export된 IMG 파일이 없거나 비어 있거나 읽을 수 없습니다.")
        if outcome.get("closed") is not True:
            raise flows.FlowError("Export Manager가 닫히지 않아 Import를 시작하지 않았습니다.")

        evidence_dir = Path(ctx.evidence_root) / "WU09" / str(time.time_ns())
        evidence_dir.mkdir(parents=True, exist_ok=False)
        completion_path = str((evidence_dir / "import-completion.png").resolve())
        evidence = {"before": None, "after": None, "completion": None,
                    "examined": {"patient_id": patient_id, "searched": False, "study_uids": []}}
        try:
            # Take this immediately before the Import attempt, not before Export.
            evidence["before"] = usb_evidence.patient_snapshot(ctx.db, ctx.cfg["data_dir"], patient_id)
            import_requested = True
            result["import"] = usb_media.attempt_import(ui, target, expected=1, evidence_path=completion_path)
            if not isinstance(result["import"], dict):
                result["import"] = None
                raise TypeError("Import 수집 결과가 객체가 아닙니다.")
            evidence["completion"] = result["import"].get("completion")
            if result["import"].get("error"):
                result["error"] = result["import"]["error"]
            if result["import"].get("cleanup_error"):
                cleanup_error(result["import"]["cleanup_error"])
        except Exception as error:
            record_error("Import 실행/사전 관찰", error)
            if result["import"] is None:
                result["import"] = {"error": result["error"], "closed": False}
        finally:
            try:
                evidence["after"] = usb_evidence.patient_snapshot(ctx.db, ctx.cfg["data_dir"], patient_id)
            except Exception as error:
                record_error("Import 이후 DB/파일 관찰", error)
                evidence.setdefault("collection_errors", []).append(f"{type(error).__name__}: {error}")
            result["import"]["evidence"] = evidence

        imp = result["import"]
        completion = evidence["completion"]
        if (isinstance(completion, dict) and completion.get("observed") is True
                and not completion.get("error") and not imp.get("error")
                and not result.get("error") and imp.get("closed") is True):
            try:
                # Collector reads actual fresh UI-click Study Keys and DB UIDs;
                # it never receives or copies the expected new UID set.
                evidence["examined"] = usb_evidence.observe_examined(ui, ctx.db, ctx.cfg["data_dir"], patient_id)
            except Exception as error:
                record_error("Examined 독립 재검색", error)
                evidence.setdefault("collection_errors", []).append(f"{type(error).__name__}: {error}")
    except Exception as error:
        record_error("USB Export/Import", error)
    finally:
        if export_opened:
            try:
                remaining_manager = em.ViewerUi(em.PROCESS)
                if remaining_manager.pid:
                    # em.cancel can dismiss a modal. Unknown modals are kept
                    # for controlled recovery rather than clicking a guess.
                    if remaining_manager.dialog() is not None:
                        cleanup_error("Export Manager에 미확인 대화상자가 남아 자동으로 닫지 않았습니다.")
                    elif em.cancel(remaining_manager, timeout=10) is False:
                        cleanup_error("Export Manager 창을 닫지 못했습니다.")
            except Exception as error:
                cleanup_error(f"Export Manager 정리: {type(error).__name__}: {error}")
        if import_requested:
            try:
                if usb_media.cancel_browse_dialog(ui) is False:
                    cleanup_error("Import 폴더 찾아보기 창을 닫지 못했습니다.")
            except Exception as error:
                cleanup_error(f"Import 폴더 찾아보기 정리: {type(error).__name__}: {error}")
            # attempt_import owns known completion dismissal and scoped Import
            # closure. An unclosed result may contain an unknown/negative modal;
            # preserve it and request the caller's cold-start recovery for TC10.
            imp = result.get("import") or {}
            result["cleanup"]["import_closed"] = imp.get("closed") is True
            if imp.get("closed") is not True:
                cleanup_error("Import 창/완료 대화상자가 남아 있습니다. 미확인 버튼을 누르지 않고 복구를 요청합니다.")
    return result
