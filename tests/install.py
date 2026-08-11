# -*- coding: utf-8 -*-
"""Install 계열 TC.

TC_Basic_Install_01  설치 버전 및 패키지 구성 확인        [완전 자동]
TC_Basic_Install_02  Viewer 실행 전 필수 환경 확인        [완전 자동]
TC_Basic_Install_07  Theme/Language/Kiosk 적용·유지       [pre/post]
TC_Basic_Install_08  Upgrade 후 기존 데이터 유지          [pre/post]
TC_Basic_Install_09  Uninstall 후 잔존 확인 (검증부만)     [완전 자동 / 수동 제거 후 실행]
"""

import os

from core import net, sysinfo
from core.result import TCResult, PASS, FAIL, MANUAL


# --------------------------------------------------------------------------
def install_01(ctx):
    r = TCResult("TC_Basic_Install_01", "설치 버전 및 패키지 구성 확인")
    rn = ctx.cfg["release_note"]

    # Step 1. 검증 대상 버전 정보
    r.add(1, "검증 대상 Release Note 기준값 로드", PASS,
          expected="config.json > release_note",
          actual=f"programs {len(rn['programs'])}건 / files {len(rn['files'])}건",
          note=rn.get("_source", ""))

    # Step 2. Programs and Features 버전 대조
    installed = sysinfo.installed_programs()
    for name, expected in rn["programs"].items():
        actual = installed.get(name)
        if actual is None:
            # 표시명이 완전히 일치하지 않는 경우 부분 일치로 재탐색
            cand = [k for k in installed if name.lower() in k.lower()]
            actual = installed[cand[0]] if cand else None
        r.assert_equal(2, f"[Programs and Features] {name} 버전", expected,
                       actual if actual is not None else "설치되지 않음")

    # Step 3. Programs and Features에 표시되지 않는 구성 파일 버전
    for rel, expected in rn["files"].items():
        path = os.path.join(ctx.cfg["install_dir"], rel)
        actual = sysinfo.file_version(path)
        r.assert_equal(3, f"[설치 경로] {rel} 버전", expected,
                       actual if actual is not None else "파일 없음",
                       note=path)

    # Step 3-b. DB에 기록된 소프트웨어 버전
    db_ver = ctx.db.scalar("DATA", "SELECT Version FROM SOFTWARE_VERSION")
    r.assert_equal(3, "[DATA.SOFTWARE_VERSION] 버전", rn["db_software_version"], db_ver)

    return r


# --------------------------------------------------------------------------
def install_02(ctx):
    r = TCResult("TC_Basic_Install_02", "Viewer 실행 전 필수 환경 확인")
    pre = ctx.cfg["prerequisites"]

    # Step 1. VC++ Redistributable
    pattern = pre["vcredist_pattern"].strip("*").lower()
    hits = [f"{k} {v}" for k, v in sysinfo.installed_programs().items()
            if pattern in k.lower()]
    r.assert_true(1, "Microsoft Visual C++ 2015-2022 Redistributable 설치",
                  bool(hits), expected="설치됨",
                  actual="; ".join(hits) if hits else "미설치")

    # Step 2. SQL Server(BELLALUN) 서비스
    svc = sysinfo.service_state(ctx.cfg["sql_service_name"])
    if svc is None:
        r.add(2, "SQL Server(BELLALUN) 서비스 존재", FAIL,
              expected=ctx.cfg["sql_service_name"], actual="서비스 없음")
    else:
        r.assert_equal(2, "SQL Server(BELLALUN) 시작 유형", "Automatic", svc["start_type"])
        r.assert_equal(2, "SQL Server(BELLALUN) 실행 상태", "Running", svc["status"])
    r.assert_true(2, "BELLALUN 인스턴스 DB 접속", ctx.db.ping(),
                  expected="접속 성공",
                  actual="접속 성공" if ctx.db.ping() else "접속 실패")

    # Step 3. 방화벽 허용 항목
    for kw in pre["firewall_keywords"]:
        rules = sysinfo.firewall_rules(kw)
        r.assert_true(3, f"방화벽 허용 규칙 [{kw}]", bool(rules),
                      expected="활성 규칙 1건 이상",
                      actual=f"{len(rules)}건: " + ", ".join(rules[:3]) if rules else "없음")

    # Step 4. DICOM 통신 어댑터 IPv4
    nic = sysinfo.nic_ipv4(pre["dicom_nic_alias"])
    if nic is None:
        r.add(4, f"네트워크 어댑터 [{pre['dicom_nic_alias']}]", MANUAL,
              expected=pre["dicom_nic_alias"], actual=net.summary(),
              note="지정한 별칭의 어댑터가 없습니다. 검증 환경서의 DICOM 어댑터 별칭을 "
                   "config.json > prerequisites.dicom_nic_alias 에 입력하면 자동 판정됩니다.")
    else:
        r.assert_equal(4, f"어댑터 [{nic['name']}] 상태", "Up", nic["status"])
        expected_ip = pre.get("expected_ipv4")
        if expected_ip:
            r.assert_true(4, "IPv4 주소가 검증 환경서와 일치",
                          expected_ip in nic["ipv4"],
                          expected=expected_ip, actual=", ".join(nic["ipv4"]))
        else:
            r.manual(4, "IPv4 주소가 검증 환경서와 일치",
                     "config.json > prerequisites.expected_ipv4 미설정. 환경서 기준값 입력 필요",
                     expected="검증 환경서 값", actual=", ".join(nic["ipv4"]))

    # 참고 정보
    osi = sysinfo.os_info()
    r.manual(0, "OS 정보 (참고)", "지원 OS Build는 문서상 확정되지 않아 수동 확인 필요",
             expected="제품 사양서 지원 OS",
             actual=f"{osi.get('Caption')} {osi.get('Version')} "
                    f"Build {osi.get('BuildNumber')} {osi.get('OSArchitecture')}")
    return r


# --------------------------------------------------------------------------
def install_07_evaluate(ctx, pre, post):
    """설치 옵션(Theme/Language/Kiosk) 적용 및 Viewer 재시작 후 유지 확인.

    pre  : 설정 변경 직후 스냅샷
    post : Viewer 재시작 후 스냅샷
    """
    r = TCResult("TC_Basic_Install_07", "설치 옵션 및 변경 적용 확인 (Theme/Language/Kiosk)")
    opt = ctx.cfg["install_option"]

    def sc(snap):
        rows = snap["_sections"].get("system_common") or []
        return rows[0] if rows else {}

    a, b = sc(pre), sc(post)
    if not b:
        r.add(0, "CONFIGURATION.SYSTEM_COMMON 조회", FAIL, actual="행 없음")
        return r

    r.assert_equal(3, "설치/설정 시 지정한 Theme 적용", opt["expected_theme"], b.get("Theme"))
    r.assert_equal(3, "설치/설정 시 지정한 Language 적용", opt["expected_language"], b.get("Language"))
    r.assert_equal(4, "Kiosk 옵션 값", opt["expected_kiosk"], b.get("UseKiosk"))

    # Step 7. 재시작 후 유지
    for field, step in (("Theme", 5), ("Language", 7), ("UseKiosk", 4)):
        r.assert_equal(step, f"Viewer 재시작 후 {field} 유지", a.get(field), b.get(field),
                       note="재시작 전(pre) 값과 재시작 후(post) 값 비교")

    r.manual(6, "Language 변경 후 재시작 필요 안내 표시", "팝업 문구는 화면 확인 필요 (증적 캡처)")
    return r


# --------------------------------------------------------------------------
def install_08_evaluate(ctx, pre, post):
    """Upgrade 전/후 기존 데이터 유지 확인."""
    from core import snapshot

    r = TCResult("TC_Basic_Install_08", "Upgrade 후 기존 데이터 유지 확인")

    def rows(snap, sec):
        v = snap["_sections"].get(sec)
        return v if isinstance(v, list) else []

    # Step 2. 모듈 버전
    sub = install_01(ctx)
    for c in sub.checks:
        if c.step in (2, 3):
            r.add(2, c.title, c.status, c.expected, c.actual, c.note)

    # Step 3. 기존 검사 누락 여부
    for sec, label, step in (("patient", "Patient", 3), ("study", "Study", 3),
                             ("series", "Series", 3), ("instance", "Image(INSTANCE)", 3),
                             ("qc_study", "Q.C 결과", 5)):
        n_pre, n_post = len(rows(pre, sec)), len(rows(post, sec))
        r.assert_true(step, f"{label} 건수 유지", n_post >= n_pre,
                      expected=f">= {n_pre}", actual=n_post)

    # UID 단위 대조 — 오매칭/손실 방지 (P0)
    pre_uid = {x.get("StudyInstanceUID") for x in rows(pre, "study")}
    post_uid = {x.get("StudyInstanceUID") for x in rows(post, "study")}
    missing = sorted(u for u in pre_uid - post_uid if u)
    r.assert_true(3, "기존 Study Instance UID 전건 유지", not missing,
                  expected="누락 0건", actual=f"누락 {len(missing)}건 {missing[:5]}")

    pre_img = {x.get("ImageInstanceUID") for x in rows(pre, "instance")}
    post_img = {x.get("ImageInstanceUID") for x in rows(post, "instance")}
    missing_img = sorted(u for u in pre_img - post_img if u)
    r.assert_true(3, "기존 SOP Instance UID 전건 유지", not missing_img,
                  expected="누락 0건", actual=f"누락 {len(missing_img)}건 {missing_img[:5]}")

    # Step 4. Annotation/Crop 정보
    r.manual(4, "Annotation 및 Crop 정보 유지",
             "Annotation/Crop 저장 위치가 DB 스키마에서 확인되지 않음. 화면 확인 필요",
             expected="Upgrade 전과 동일")

    # Step 6~7. Setting Import 후 유지
    same, d = snapshot.config_identical(pre, post)
    r.add(7, "Upgrade 및 Setting Import 후 설정값", PASS if same else MANUAL,
          expected="Export 시점 설정과 동일",
          actual="동일" if same else f"차이 {len(d)}개 섹션: {', '.join(sorted(d))}",
          note="" if same else "Upgrade 시 신규 추가된 설정 항목일 수 있어 사양 확인 필요")
    return r


# --------------------------------------------------------------------------
def install_09_verify(ctx):
    """수동 Uninstall 수행 후 실행하는 검증 전용 TC. 제거 동작 자체는 자동화하지 않는다."""
    r = TCResult("TC_Basic_Install_09", "Uninstall 및 데이터 유지 확인 (검증부)")

    r.assert_true(1, "관리자 권한으로 수행", sysinfo.is_elevated(),
                  expected="Administrator", actual=sysinfo.is_elevated())

    # Step 2. 제거 완료
    installed = sysinfo.installed_programs()
    remain = [k for k in installed if "bellalun" in k.lower()]
    r.assert_true(2, "Programs and Features에서 Bellalun 제거", not remain,
                  expected="목록 없음", actual=remain or "없음")

    # Step 3. 설치 경로 제거
    inst = ctx.cfg["install_dir"]
    left = []
    if os.path.isdir(inst):
        left = os.listdir(inst)
    r.assert_true(3, "설치 경로 제거", not left,
                  expected=f"{inst} 없음 또는 비어 있음",
                  actual=f"{len(left)}개 잔존: {left[:8]}" if left else "제거됨")

    # Step 4. 데이터 유지
    data = ctx.cfg["data_dir"]
    db_dir = os.path.join(data, "Database")
    img_dir = os.path.join(data, "Image")
    r.assert_true(4, "Database 데이터 유지", os.path.isdir(db_dir) and bool(os.listdir(db_dir)),
                  expected=f"{db_dir} 유지",
                  actual=os.listdir(db_dir)[:6] if os.path.isdir(db_dir) else "없음")
    r.assert_true(4, "Image 데이터 유지", os.path.isdir(img_dir),
                  expected=f"{img_dir} 유지", actual=os.path.isdir(img_dir))

    # Step 5. Winlogon Shell 복원
    shell = sysinfo.registry_value(
        r"HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon", "Shell")
    ok = shell is None or "bellalun" not in shell.lower()
    r.assert_true(5, "Winlogon Shell에서 Bellalun 항목 제거", ok,
                  expected="explorer.exe 또는 미설정", actual=shell or "(미설정)")
    return r


REGISTRY = [
    {"id": "TC_Basic_Install_01", "title": "설치 버전 및 패키지 구성 확인",
     "mode": "single", "run": install_01},
    {"id": "TC_Basic_Install_02", "title": "Viewer 실행 전 필수 환경 확인",
     "mode": "single", "run": install_02},
    {"id": "TC_Basic_Install_07", "title": "설치 옵션 및 변경 적용 확인",
     "mode": "prepost", "evaluate": install_07_evaluate,
     "pre_hint": "Theme/Language/Kiosk를 config.json의 기대값으로 설정한 직후",
     "post_hint": "Viewer를 재시작한 후"},
    {"id": "TC_Basic_Install_08", "title": "Upgrade 후 기존 데이터 유지 확인",
     "mode": "prepost", "evaluate": install_08_evaluate,
     "pre_hint": "Upgrade 수행 직전", "post_hint": "Upgrade 및 Setting Import 완료 후"},
    {"id": "TC_Basic_Install_09", "title": "Uninstall 및 데이터 유지 확인 (검증부)",
     "mode": "single", "run": install_09_verify,
     "guard": "Uninstall을 수동으로 수행한 뒤에만 실행하십시오."},
]
