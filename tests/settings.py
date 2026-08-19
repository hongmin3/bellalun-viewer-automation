# -*- coding: utf-8 -*-
r"""설정·계정·시스템 계열 TC의 판정부.

  TC_Basic_WorkFlow_03  Image Overlay 및 Print Overlay 설정   [pre/post]
  TC_Basic_WorkFlow_10  MWL Hospital Code와 Procedure 매핑    [pre/post]
  TC_Basic_WorkFlow_13  계정 추가·수정 및 로그인               [pre/post]
  TC_Basic_WorkFlow_14  Setting Export 및 Import              [pre/post]
  TC_Basic_WorkFlow_16  Kiosk 및 System Launcher (검증부)      [완전 자동]

WF_03은 `tests/workflow03.py`가 실제 UI로 수행하므로 여기 판정부는 쓰이지 않는다.
나머지는 pre/post 스냅샷을 만드는 UI 드라이버가 없어 `run.py`에 연결돼 있지 않다.

**2026-08-19 번호 재정렬**: 이전 체크리스트 번호를 쓰고 있었다(예: Kiosk가 `WF_18`).
기준 문서인 `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`에 맞춰 다시 매겼다
(`AGENTS.md` 0절). Title은 개정본과 같았고 번호만 어긋나 있었다.
"""

import os

from core import snapshot, sysinfo
from core.result import TCResult, PASS, FAIL, MANUAL


def _rows(snap, sec):
    v = snap["_sections"].get(sec)
    return v if isinstance(v, list) else []


# --------------------------------------------------------------------------
def workflow_03_evaluate(ctx, pre, post):
    r = TCResult("TC_Basic_WorkFlow_03", "Image Overlay 및 Print Overlay 설정")

    # Step 1. Image Overlay 항목 추가 저장
    a = {(x.get("Position"), x.get("FieldID")) for x in _rows(pre, "overlay_item")}
    b = {(x.get("Position"), x.get("FieldID")) for x in _rows(post, "overlay_item")}
    added = sorted(b - a)
    removed = sorted(a - b)
    r.assert_true(1, "[Setting > Display > Overlay] 추가 항목 저장", bool(added),
                  expected="OVERLAY_ITEM에 신규 (Position, FieldID) 추가",
                  actual=f"추가 {added} / 제거 {removed}",
                  note="FieldID와 화면 표시명 매핑표는 문서상 확인되지 않아 항목명 대조는 수동")

    # Step 2. Print Overlay 구성 저장
    pa = {(x.get("PrintOverlayKey"), x.get("Position"), x.get("FieldID"))
          for x in _rows(pre, "print_overlay_item")}
    pb = {(x.get("PrintOverlayKey"), x.get("Position"), x.get("FieldID"))
          for x in _rows(post, "print_overlay_item")}
    r.assert_true(2, "[Setting > DICOM > Print] Print Overlay 구성 저장", bool(pb - pa),
                  expected="PRINT_OVERLAY_ITEM에 신규 항목 추가",
                  actual=f"추가 {sorted(pb - pa)} / 제거 {sorted(pa - pb)}")

    # Step 3. Print 설정에 선택 반영
    d = snapshot.diff_section(pre, post, "dicom_print")
    r.assert_true(3, "Print 설정에 선택한 Overlay 적용", bool(d["changed"] or (pb - pa)),
                  expected="DICOM_PRINT 또는 PRINT_OVERLAY 변경",
                  actual=d["changed"] or "변경 없음")

    # Step 5~6. 화면 표시
    r.manual(5, "2D 영상의 Image Overlay 표시", "화면 표시는 캡처 증적으로 확인 (OCR 보조 가능)")
    r.manual(6, "Film 창의 Print Overlay 표시", "Film 창 표시는 캡처 증적으로 확인")
    return r


# --------------------------------------------------------------------------
def workflow_10_evaluate(ctx, pre, post):
    r = TCResult("TC_Basic_WorkFlow_10", "MWL Hospital Code와 Procedure 매핑")
    code = ctx.cfg["test_data"]["hospital_code"]
    proc = ctx.cfg["test_data"]["procedure_name"]

    # Step 1. Hospital Code 저장
    hc = [x for x in _rows(post, "hospital_code") if (x.get("Code") or "") == code]
    r.assert_true(1, f"[Setting > Procedure > Hospital Code] {code} 저장", bool(hc),
                  expected=f"HOSPITAL_CODE.Code = {code}",
                  actual=hc[0] if hc else "없음")

    # Step 2. Procedure 매핑
    if hc:
        mk = hc[0].get("MappingKey")
        pi = [x for x in _rows(post, "procedure_info") if x.get("Key") == mk]
        r.assert_true(2, f"Hospital Code에 Procedure 매핑", bool(pi),
                      expected=f"MappingKey({mk}) → PROCEDURE_INFO 존재",
                      actual=pi[0].get("Name") if pi else "매핑 대상 없음")
        if pi:
            r.assert_equal(2, "매핑된 Procedure 명", proc, pi[0].get("Name"),
                           note="config.json > test_data.procedure_name 기준")
    else:
        r.skip(2, "Hospital Code에 Procedure 매핑", "Hospital Code 미생성으로 수행 불가")

    # Step 3. MWL Hospital Code Mapping 설정
    d = snapshot.diff_section(pre, post, "dicom_mwl")
    r.assert_true(3, "[Setting > DICOM > MWL] Hospital Code Mapping 저장",
                  bool(d["changed"] or d["added"]),
                  expected="DICOM_MWL 변경",
                  actual=d["changed"] or d["added"] or "변경 없음",
                  note="CodeMappingTag 컬럼 의미는 사양 확인 필요")

    # Step 7. Examine 진입 시 Study에 반영
    new_study = snapshot.diff_section(pre, post, "study")["added"]
    hit = [s for s in new_study if (s.get("HospitalCode") or "") == code]
    r.assert_true(7, "생성된 검사에 Hospital Code 반영", bool(hit),
                  expected=f"STUDY.HospitalCode = {code}",
                  actual=[{"Key": s.get("Key"), "HospitalCode": s.get("HospitalCode"),
                           "ProcedureKey": s.get("ProcedureKey")} for s in new_study] or "신규 검사 없음")
    if hit:
        r.assert_true(7, "생성된 검사에 Procedure 매핑", bool(hit[0].get("ProcedureKey")),
                      expected="STUDY.ProcedureKey 설정됨",
                      actual=hit[0].get("ProcedureKey"))
    r.manual(7, "첫 Step/Preset 선택 상태", "Examine 화면의 Step 선택 상태는 캡처 증적으로 확인")
    return r


# --------------------------------------------------------------------------
def workflow_13_evaluate(ctx, pre, post):
    r = TCResult("TC_Basic_WorkFlow_13", "계정 추가·수정 및 로그인")
    acc_id = ctx.cfg["test_data"]["account_id"]

    d = snapshot.diff_section(pre, post, "account")
    added = [x for x in d["added"] if (x.get("ID") or "") == acc_id]
    r.assert_true(1, f"[Setting > System > Account] {acc_id} 계정 저장", bool(added),
                  expected=f"ACCOUNT.ID = {acc_id}",
                  actual=added[0] if added else f"추가된 계정: {[x.get('ID') for x in d['added']]}")

    if added:
        r.assert_true(2, "계정 권한 그룹 설정", added[0].get("Group") is not None,
                      expected="ACCOUNT.Group 설정됨", actual=added[0].get("Group"),
                      note="Group 코드와 권한 범위의 매핑은 문서상 확인 필요")
    else:
        r.skip(2, "계정 권한 그룹 설정", "계정 미생성")

    changed = [c for c in d["changed"] if acc_id in str(c)]
    r.add(3, "계정 정보 수정 반영", PASS if changed else MANUAL,
          expected="ACCOUNT 행 변경",
          actual=changed or "변경 감지 없음",
          note="" if changed else "수정 단계를 수행하지 않았거나 변경 항목이 Password인 경우 "
                                  "해시 저장 여부에 따라 감지되지 않을 수 있음")

    r.manual(4, "로그오프 시 이전 사용자 정보 미표시", "로그인 화면 표시는 캡처 증적으로 확인")
    r.manual(5, "시험 계정으로 로그인", "로그인 성공 여부는 화면 확인 필요")
    r.manual(6, "허용된 기능만 사용 가능", "메뉴 접근 제한은 화면 확인 필요")

    # 정리 절차 안내
    r.add(0, "정리 절차", MANUAL, note=f"검증 종료 후 {acc_id} 계정을 수동 삭제할 것")
    return r


# --------------------------------------------------------------------------
def workflow_14_evaluate(ctx, pre, post):
    """Setting Export → 설정 변경 → Import → 재시작 후 복원 확인.

    pre  : Export 직후(기준 설정) 스냅샷
    post : 설정 변경 → Import → Viewer 재시작 후 스냅샷
    """
    r = TCResult("TC_Basic_WorkFlow_14", "Setting Export 및 Import")

    # Step 2. Export 파일 생성
    path = (ctx.cfg.get("settings_export") or {}).get("exported_file") or ""
    if path:
        exists = os.path.isfile(path)
        r.assert_true(2, "Setting Export 파일 생성", exists,
                      expected=path,
                      actual=f"{os.path.getsize(path)} bytes" if exists else "파일 없음")
    else:
        r.manual(2, "Setting Export 파일 생성",
                 "config.json > settings_export.exported_file 경로 지정 시 자동 확인")

    # Step 7. 설정 복원 — 스크린샷 SSIM 대신 설정값 전수 대조
    same, d = snapshot.config_identical(pre, post)
    r.assert_true(7, "재시작 후 Export 시점 설정값으로 복원", same,
                  expected="설정 테이블 전수 일치",
                  actual="일치" if same else f"불일치 {len(d)}개 섹션",
                  note="" if same else _fmt_diff(d))

    # 섹션별 상세를 개별 Check로 남겨 실패 지점을 바로 특정할 수 있게 한다
    for sec in sorted(d):
        r.add(7, f"설정 섹션 [{sec}] 복원", FAIL,
              expected="Export 시점과 동일",
              actual=_fmt_section(d[sec]))
    return r


def _fmt_section(sd):
    bits = []
    if sd.get("added"):
        bits.append(f"추가 {len(sd['added'])}행")
    if sd.get("removed"):
        bits.append(f"삭제 {len(sd['removed'])}행")
    for c in sd.get("changed", [])[:5]:
        bits.append(f"{c['row']}: " + ", ".join(
            f"{k} {v['pre']}→{v['post']}" for k, v in c["fields"].items()))
    return " / ".join(bits)


def _fmt_diff(d):
    return "; ".join(f"{k}({_fmt_section(v)})" for k, v in sorted(d.items()))


# --------------------------------------------------------------------------
def workflow_16_verify(ctx):
    """Kiosk / System Launcher 검증부. 재시작·로그인은 수동."""
    r = TCResult("TC_Basic_WorkFlow_16", "Kiosk 및 System Launcher (검증부)")

    row = ctx.db.one("CONFIGURATION",
                     "SELECT UseKiosk,ExitPermission,LastLoginID FROM SYSTEM_COMMON") or {}
    expected_kiosk = ctx.cfg["install_option"]["expected_kiosk"]
    r.assert_equal(2, "[Setting > System > Security] Kiosk mode 저장",
                   expected_kiosk, row.get("UseKiosk"),
                   note="config.json > install_option.expected_kiosk 기준. "
                        "Use=1 / Not Use=0 매핑은 실제 화면과 대조 필요")

    shell = sysinfo.registry_value(
        r"HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon", "Shell")
    if expected_kiosk:
        r.assert_true(3, "Kiosk 적용 시 Winlogon Shell 대체", bool(shell) and "explorer" not in (shell or "").lower(),
                      expected="Bellalun Shell 항목", actual=shell or "(미설정)")
    else:
        r.assert_true(3, "Kiosk 미적용 시 Winlogon Shell 기본값",
                      not shell or "explorer" in shell.lower(),
                      expected="explorer.exe 또는 미설정", actual=shell or "(미설정)")

    # Step 5~8. System Launcher 실행 대상 존재 확인
    targets = {
        "Viewer": "VIEWER.exe",
        "System Launcher": "SystemLauncher.exe",
        "Bellalun System Setup": "Launcher",
    }
    for label, rel in targets.items():
        p = os.path.join(ctx.cfg["install_dir"], rel)
        r.assert_true(5, f"System Launcher 실행 대상 [{label}] 존재", os.path.exists(p),
                      expected=p, actual="존재" if os.path.exists(p) else "없음")

    running = set(sysinfo.process_names())
    r.add(8, "현재 기동 중인 Bellalun 프로세스", PASS,
          expected="참고 정보",
          actual=", ".join(sorted(p for p in running
                                  if p.lower().startswith(("viewer", "systemlauncher",
                                                           "bellalun", "pv.loader",
                                                           "upshandler")))) or "없음")

    r.manual(3, "시스템 재시작 후 Kiosk 조건 실행", "PC 재시작이 필요해 수동 수행")
    r.manual(9, "일반 계정에서 Exit 제한", f"ExitPermission={row.get('ExitPermission')} "
                                         "코드 의미가 문서상 확인되지 않아 화면 확인 필요")
    r.manual(12, "Shutdown 동작", "PC 종료를 유발하므로 자동화 대상에서 제외")
    return r


REGISTRY = [
    {"id": "TC_Basic_WorkFlow_03", "title": "Image Overlay 및 Print Overlay 설정",
     "mode": "prepost", "evaluate": workflow_03_evaluate,
     "pre_hint": "Overlay 설정 변경 전", "post_hint": "Overlay 설정 저장(Update/OK) 후"},
    {"id": "TC_Basic_WorkFlow_10", "title": "MWL Hospital Code와 Procedure 매핑",
     "mode": "prepost", "evaluate": workflow_10_evaluate,
     "pre_hint": "Hospital Code 생성 전", "post_hint": "매핑 처방으로 Examine 진입 후"},
    {"id": "TC_Basic_WorkFlow_13", "title": "계정 추가·수정 및 로그인",
     "mode": "prepost", "evaluate": workflow_13_evaluate,
     "pre_hint": "계정 추가 전", "post_hint": "계정 추가 및 수정 후"},
    {"id": "TC_Basic_WorkFlow_14", "title": "Setting Export 및 Import",
     "mode": "prepost", "evaluate": workflow_14_evaluate,
     "pre_hint": "Setting Export 직후(기준 설정 상태)",
     "post_hint": "설정 변경 → Import → Viewer 재시작 후"},
    {"id": "TC_Basic_WorkFlow_16", "title": "Kiosk 및 System Launcher (검증부)",
     "mode": "single", "run": workflow_16_verify},
]
