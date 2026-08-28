# -*- coding: utf-8 -*-
"""설치 패키지 검증 — **신규 설치용 Install.exe 를 설치하지 않고 점검한다.**

이 모듈은 **전체 회귀(`run-regression`)에 들어 있지 않다.** 회귀는 이미 설치된
Viewer 를 대상으로 돌지만 이 점검은 **설치 이전**에 패키지 자체를 보는 일이라
전제도 대상도 다르다. 단독 실행 전용이다.

    python run.py verify-install-package

무엇을 보는가
  1. 정적 — 패키지 파일 구성, 코드 서명, Install Package 버전,
     `Install.xml` 이 참조하는 파일의 실존, `Config.xml` 의 설치 기본값.
  2. 마법사 — Welcome → Configure Path → Register Options → Input License →
     Summary 까지 실제로 진행하며 각 화면이 사양서/매뉴얼과 맞는지 본다.

무엇을 하지 않는가
  **Install 버튼을 누르지 않는다.** Summary 까지 확인하고 마법사를 열어 둔 채
  끝낸다. 실제 설치(Install Software)는 사람이 직접 시작한다.

전제
  **신규 설치 구성**이어야 한다(SRS 08-10-10). 업그레이드일 때 인스톨러는
  Welcome / Summary / Install Software 3단계만 만들므로(SRS 08-10-20) 이
  점검의 Configure Path·Register Options·Input License 검사가 성립하지 않는다.
  그래서 메뉴가 6단계가 아니면 그 사실을 기록하고 마법사 검사를 멈춘다.

근거 문서
  - `(사양서) Bellalun Viewer 사양서2` SRS 08-10-10 설치 / 08-10-20 업그레이드
  - `(사양서) Bellalun Viewer 사양서1` SRS 01-10-20 UI Theme / 01-10-30 언어 설정
  - `(매뉴얼) Bellalun Viewer Service Manual` "설치하기" 절
"""

import os
import re
import subprocess
import xml.etree.ElementTree as ET

from core import screen, sysinfo
from core.installer_ui import (LICENSE_SEGMENTS, LIC_GUIDE, LIC_HWKEY_LABEL,
                               LIC_LABEL, OPT_GUIDE, OPT_KIOSK_COMBO,
                               OPT_KIOSK_LABEL, OPT_LANG_COMBO, OPT_LANG_LABEL,
                               OPT_THEME_COMBO, OPT_THEME_LABEL,
                               PAGES_NEW_INSTALL, PATH_DB_EDIT, PATH_DRIVE_LIST,
                               PATH_GUIDE, PATH_TITLE, PATH_VIEWER_EDIT,
                               SUM_GUIDE, SUM_TEXT, SUM_TITLE, WELCOME_ACCEPT,
                               WELCOME_DISACCEPT, WELCOME_EULA, WELCOME_GUIDE,
                               WELCOME_TITLE)
from core.result import BLOCKED, FAIL, MANUAL, PASS, SKIP, TCResult

# --- 사양서가 정한 기대값 --------------------------------------------------
# SRS 01-10-30 언어 설정 — 공식 지원 언어 4종. Config.xml 의 LanguageList 와 같다.
EXPECTED_LANGUAGES = ["English", "한국어", "日本語", "Русский"]
# SRS 01-10-20 UI Theme — 제공 테마 3종.
EXPECTED_THEMES = ["Pure White", "Dark Violet", "Light Violet"]
# SRS 08-10-10 — KIOSK 사용 여부는 신규 설치 시에도 설정할 수 있다.
EXPECTED_KIOSK = ["Use", "Not Use"]
# SRS 08-10-10 / Service Manual — Database 기본 경로.
EXPECTED_DB_PATH = r"D:\BellalunData"
# SRS 08-10-10 — Viewer 설치 기본 경로는 Windows 가 설치된 드라이브 기준이다.
EXPECTED_VIEWER_DIR = "Bellalun"
# 사양서2 "버전 관리" 표 — 뷰어 V1.0.12 ↔ Install Package V1.0.3.
EXPECTED_PACKAGE_VERSION = "1.0.3"
# SRS 08-10-10 — 설치 로그 위치.
#
# 사양서는 `C:\Documents\Bellalun\InstallLog` 로 적지만 **드라이브 루트의
# 절대경로가 아니다.** 실제 위치는 **로그인 사용자의 Documents 폴더 아래**다
# (실측: `C:\Users\<계정>\Documents\Bellalun\InstallLog`).
# 2026-08-26 사양서 표기를 그대로 절대경로로 보고 "로그가 생성되지 않는다
# (사양 불일치)" 고 **잘못 판정했다.** 사용자가 실제 경로를 알려 주어 바로잡았다.
# 로그는 사양대로 정상 생성되고 있었다 — `Install.exe` 를 띄우기만 해도 파일이
# 하나 생기고(약 242바이트), 실제 설치를 하면 단계별 기록이 쌓인다(2,228바이트).
SPEC_INSTALL_LOG_DIR = r"C:\Documents\Bellalun\InstallLog"      # 사양서 표기(참고)
# EULA 본문 스크롤 캡처 상한. 약관이 29KB(약 360줄)라 한 화면씩 훑으면 40장쯤
# 된다. 2026-08-26 상한을 12로 뒀더니 **화면이 중간에서 멈췄고** 사용자가 바로
# 알아봤다 — 끝까지 닿도록 넉넉히 잡는다. 상한에 걸리면 판정 `actual` 에 그
# 사실을 적는다(조용히 자르지 않는다).
EULA_MAX_SHOTS = 60

# 패키지 최상위에 반드시 있어야 하는 항목 (Service Manual 패키지 구성)
REQUIRED_ENTRIES = [
    ("Install.exe", "file"), ("Config.xml", "file"), ("Install.xml", "file"),
    ("Data", "dir"), ("Program", "dir"), ("Support", "dir"),
]
# Install.xml 이 설치한다고 적은 사전 설치 프로그램 (SRS 08-10-10 설치 항목)
EXPECTED_INSTALL_ITEMS = [
    "MSSQL", "VC 2015 2022 Redistributable x64", "VIVIX.M SDK", "XIPL",
    "SystemSetup", "Viewer",
]
# `[RunningDirectory]` 로 시작하는 패키지 내부 경로를 뽑는다. ExecuteFile 같은
# 경로 전용 속성만 보면 안 된다 — Argument 안에도 파일 경로가 들어 있어서
# (XIPLInstall.reg 가 그렇다) 속성값을 가리지 않고 전부 훑는다.
RUNNING_DIR_TOKEN = re.compile(r"\[RunningDirectory\]([^\"]+?)(?=\"|$)")
# Shell 등록 .reg 는 KIOSK 선택에 따라 파일명이 갈린다(Install.xml [ShellFileName]).
SHELL_FILE_NAMES = ("shell_Kiosk", "shell_NoKiosk")


# ==========================================================================
# 정적 검증
# ==========================================================================
def _read_xml(path):
    """BOM 과 UTF-16 을 가리지 않고 XML 을 읽는다.

    Config.xml 은 UTF-16 LE, Install.xml 은 UTF-8 BOM 이다(실측).
    """
    with open(path, "rb") as f:
        raw = f.read()
    for encoding in ("utf-8-sig", "utf-16", "utf-8", "cp949"):
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
        try:
            return ET.fromstring(text), text
        except ET.ParseError:
            continue
    raise ValueError(f"XML 을 해석할 수 없습니다: {path}")


def _authenticode(path):
    """코드 서명 상태와 서명자를 돌려준다. 확인 불가면 (None, 사유)."""
    script = (f"$s = Get-AuthenticodeSignature -LiteralPath '{path}'; "
              f"\"$($s.Status)|$($s.SignerCertificate.Subject)\"")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             capture_output=True, timeout=90)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"서명 조회 실패: {exc}"
    text = out.stdout.decode("utf-8", "replace").strip()
    if "|" not in text:
        return None, text or "서명 정보를 읽지 못했습니다"
    status, subject = text.split("|", 1)
    return status.strip(), subject.strip()


def _referenced_paths(install_xml_text, root):
    """`Install.xml` 이 참조하는 **패키지 내부** 상대 경로를 모은다.

    `[ProgramFiles]` / `C:\\XIPL` 처럼 **설치 대상 시스템**을 가리키는 경로는
    패키지에 있을 리 없으므로 검사 대상이 아니다. `[RunningDirectory]` 로 시작하는
    것과, Copy/Move 의 `Source` 가 상대경로인 것만 본다.
    """
    found = {}          # 상대경로 -> 그 경로를 쓴 곳
    for item in root.iter("Item"):
        where = item.get("ProgressText") or item.get("Name") or item.get("Type") or "Item"
        for attr, value in item.attrib.items():
            if not value:
                continue
            for hit in RUNNING_DIR_TOKEN.findall(value):
                found.setdefault(hit.strip().lstrip("\\"), f"{where} / {attr}")
            if attr == "Source" and "[" not in value and not re.match(r"^[A-Za-z]:", value):
                found.setdefault(value.strip().lstrip("\\"), f"{where} / {attr}")
    return found


def _expand_tokens(rel):
    """치환 변수가 남은 경로를 실제 후보들로 펼친다.

    `[ShellFileName]` 은 KIOSK 선택에 따라 `shell_Kiosk` / `shell_NoKiosk` 가
    되므로 **두 파일 모두** 있어야 한다.
    """
    if "[ShellFileName]" in rel:
        return [rel.replace("[ShellFileName]", name) for name in SHELL_FILE_NAMES]
    return [rel]


def static_package(package_dir):
    """Pkg_Static_01 — 패키지 구성·서명·버전·참조 무결성."""
    r = TCResult("Pkg_Static_01", "설치 패키지 구성 및 무결성")

    # Step 1. 최상위 구성
    missing = []
    for name, kind in REQUIRED_ENTRIES:
        path = os.path.join(package_dir, name)
        ok = os.path.isfile(path) if kind == "file" else os.path.isdir(path)
        if not ok:
            missing.append(name)
    r.assert_true(1, "패키지 최상위 구성 (Install.exe/Config.xml/Install.xml/Data/Program/Support)",
                  not missing,
                  expected="6개 항목 모두 존재",
                  actual="모두 존재" if not missing else f"누락: {missing}",
                  note="Service Manual '설치 패키지 파일 모음 구성'")

    # Step 2. 코드 서명
    exe = os.path.join(package_dir, "Install.exe")
    status, subject = _authenticode(exe)
    if status is None:
        r.manual(2, "Install.exe 코드 서명", subject, expected="Valid / Vieworks")
    else:
        r.assert_equal(2, "Install.exe 코드 서명 상태", "Valid", status,
                       note="SRS 08-10-10 '설치/업그레이드 패키지에는 코드 서명이 적용되어 있다'")
        r.assert_true(2, "Install.exe 서명자", "Vieworks" in subject,
                      expected="Vieworks Co., Ltd", actual=subject)

    # Step 3. Install Package 버전
    version = sysinfo.file_version(exe)
    ok_version = bool(version) and version.startswith(EXPECTED_PACKAGE_VERSION)
    r.assert_true(3, "Install Package 버전", ok_version,
                  expected=f"{EXPECTED_PACKAGE_VERSION}.x",
                  actual=version or "확인 불가",
                  note="사양서2 '버전 관리' 표 — 뷰어 V1.0.12 는 Install Package V1.0.3")

    # Step 4. Install.xml 이 참조하는 파일의 실존
    install_xml = os.path.join(package_dir, "Install.xml")
    if not os.path.isfile(install_xml):
        r.add(4, "Install.xml 참조 파일 실존", FAIL, actual="Install.xml 없음")
        return r
    root, text = _read_xml(install_xml)
    refs = _referenced_paths(text, root)
    absent = []
    for rel, where in sorted(refs.items()):
        for candidate in _expand_tokens(rel):
            if "[" in candidate:            # 아직 못 푼 치환 변수 — 검사 불가
                continue
            full = os.path.join(package_dir, candidate)
            if not (os.path.isfile(full) or os.path.isdir(full)):
                absent.append(f"{candidate}  <- {where}")
    r.assert_true(4, "Install.xml 이 참조하는 패키지 내부 파일이 모두 존재",
                  not absent,
                  expected=f"참조 {len(refs)}건 모두 존재",
                  actual="모두 존재" if not absent else f"누락 {len(absent)}건: " + " | ".join(absent),
                  note="누락된 파일은 설치 도중 해당 단계가 조용히 건너뛰어지거나 "
                       "실패하는 원인이 된다")

    # Step 5. 사전 설치 프로그램 구성
    names = [el.get("Name") for el in root.iter("ItemList")]
    lacking = [want for want in EXPECTED_INSTALL_ITEMS
               if not any(want.lower() in (n or "").lower() for n in names)]
    r.assert_true(5, "설치 항목 구성 (MSSQL / VC++ / VIVIX.M SDK / XIPL / SystemSetup / Viewer)",
                  not lacking,
                  expected=EXPECTED_INSTALL_ITEMS,
                  actual=names if lacking else "사양의 설치 항목을 모두 포함",
                  note="SRS 08-10-10 '설치 파일을 통해 설치되는 항목'")
    return r


def static_config(package_dir):
    """Pkg_Static_02 — Config.xml 설치 기본값과 신규 설치 전제."""
    r = TCResult("Pkg_Static_02", "설치 기본값(Config.xml) 및 신규 설치 전제")

    config_xml = os.path.join(package_dir, "Config.xml")
    if not os.path.isfile(config_xml):
        r.add(1, "Config.xml 읽기", FAIL, actual="Config.xml 없음")
        return r
    root, _ = _read_xml(config_xml)

    env = {el.get("Type"): el.get("Value") for el in root.iter("Item")
           if el.get("Type")}
    r.assert_equal(1, "설치 대상 OS", "Windows 11", env.get("OS"),
                   note="SRS 08-10-10 '신규 설치는 Windows 11에서만 가능하다'")
    r.assert_equal(1, "64bit 전용", "True", env.get("PlatformOnly64bit"))

    info = next(iter(root.iter("InstallInfo")), None)
    installed_dir = info.get("InstalledDirectory") if info is not None else None
    r.assert_true(2, "Viewer 설치 기본 경로", bool(installed_dir)
                  and installed_dir.endswith(EXPECTED_VIEWER_DIR),
                  expected="[ProgramFiles]Bellalun",
                  actual=installed_dir,
                  note="SRS 08-10-10 'Viewer 설치 기본 경로: (Windows가 설치된 드라이브)"
                       "\\Program Files\\Bellalun'")

    paths = {el.get("Name"): el.get("Value") for el in root.iter("Value")}
    r.assert_equal(3, "Database 기본 경로", EXPECTED_DB_PATH,
                   paths.get("DatabaseDirectory"),
                   note="SRS 08-10-10 'Database 기본 경로: D:\\BellalunData'")

    languages = [el.get("Name") for el in root.iter("Language")]
    r.assert_equal(4, "Config.xml 언어 목록", EXPECTED_LANGUAGES, languages,
                   note="SRS 01-10-30 공식 지원 언어 4종")

    theme = next(iter(root.iter("Theme")), None)
    r.assert_equal(5, "기본 테마", "Pure White",
                   theme.get("Default") if theme is not None else None,
                   note="SRS 01-10-20 UI Theme")

    eula = next(iter(root.iter("EULA")), None)
    eula_path = _package_path(package_dir, eula.get("File")) if eula is not None else None
    r.assert_true(6, "EULA 파일 존재", bool(eula_path) and os.path.isfile(eula_path),
                  expected="Support\\EULA.txt", actual=eula_path or "미지정")

    # Step 7. 신규 설치 전제 — 이미 설치돼 있으면 인스톨러가 업그레이드 UI 를 낸다.
    installed = {k: v for k, v in sysinfo.installed_programs().items()
                 if "bellalun" in k.lower()}
    r.assert_true(7, "신규 설치 전제 (Bellalun 미설치)", not installed,
                  expected="설치된 Bellalun 없음",
                  actual=installed or "없음",
                  note="설치돼 있으면 Welcome/Summary/Install Software 3단계 "
                       "업그레이드 UI 가 뜬다(SRS 08-10-20) — 이 점검의 대상이 아니다")

    caption = sysinfo.pc_info().get("os_caption", "") if hasattr(sysinfo, "pc_info") else ""
    if caption:
        r.assert_true(7, "실행 PC OS", "11" in caption,
                      expected="Windows 11", actual=caption,
                      note="SRS 08-10-10 신규 설치는 Windows 11 에서만 가능하다")
    return r


def _package_path(package_dir, value):
    """`[RunningDirectory]...` 를 실제 경로로 바꾼다."""
    if not value:
        return None
    return os.path.join(package_dir,
                        value.replace("[RunningDirectory]", "").lstrip("\\"))


# ==========================================================================
# 마법사 검증
# ==========================================================================
def _evidence(ui, out_dir, name):
    """현재 마법사 화면을 증거로 남기고 경로를 돌려준다."""
    win = ui.wizard()
    if win is None:
        return None
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.png")
    try:
        screen.grab(win.rect, path)
    except Exception:
        return None
    return path


def wizard_welcome(ui, package_dir, evidence_dir):
    """Pkg_Wizard_01 — Welcome(EULA)과 신규 설치 단계 구성."""
    r = TCResult("Pkg_Wizard_01", "Welcome — EULA 및 설치 단계 구성")

    r.assert_equal(1, "현재 화면", "Welcome", ui.current_page())

    # Step 2. 단계 구성 — 신규 설치는 6단계 (SRS 08-10-10 / 08-10-20)
    menu = ui.menu_items()
    r.assert_equal(2, "좌측 설치 단계 수", 6, len(menu),
                   note="신규 설치 6단계. 업그레이드면 Welcome/Summary/"
                        "Install Software 3단계만 표시된다(SRS 08-10-20)")
    pages = ui.page_windows()
    missing = [p for p in PAGES_NEW_INSTALL if p not in pages]
    r.assert_true(2, "6개 설치 화면 생성", not missing,
                  expected=list(PAGES_NEW_INSTALL),
                  actual=sorted(pages) if missing else "6개 모두 생성됨")

    # Step 3. 안내 문구
    r.assert_true(3, "EULA 제목 표시",
                  "End-User License Agreement" in (ui.text_of(WELCOME_TITLE, "Static") or ""),
                  expected="End-User License Agreement",
                  actual=ui.text_of(WELCOME_TITLE, "Static"))
    r.assert_true(3, "EULA 안내 문구",
                  "license agreement" in (ui.text_of(WELCOME_GUIDE, "Static") or "").lower(),
                  expected="Please read the following license agreement carefully.",
                  actual=ui.text_of(WELCOME_GUIDE, "Static"),
                  note="Service Manual '설치하기' — End-User License Agreement 확인 안내")

    # Step 4. EULA 본문이 패키지의 EULA.txt 와 같은가
    shown = ui.text_of(WELCOME_EULA, "Edit") or ""
    eula_file = os.path.join(package_dir, "Support", "EULA.txt")
    if not os.path.isfile(eula_file):
        r.add(4, "EULA 본문이 패키지 EULA.txt 와 일치", FAIL,
              expected="Support\\EULA.txt", actual="파일 없음")
    else:
        with open(eula_file, "rb") as f:
            raw = f.read()
        for encoding in ("utf-8-sig", "utf-16", "cp949", "utf-8"):
            try:
                original = raw.decode(encoding)
                break
            except (UnicodeDecodeError, UnicodeError):
                original = None
        squeeze = lambda s: re.sub(r"\s+", " ", s or "").strip()
        tidy_shown, tidy_file = squeeze(shown), squeeze(original or "")
        r.assert_true(4, "EULA 본문이 패키지 EULA.txt 와 일치",
                      bool(original) and tidy_file == tidy_shown,
                      expected=f"Support\\EULA.txt ({len(tidy_file)}자)",
                      actual=f"화면 {len(tidy_shown)}자"
                             + ("" if original and tidy_file == tidy_shown
                                else " — 내용 불일치"),
                      note="설치 화면이 패키지에 동봉된 약관을 그대로 보여주는지 확인")

        # 본문이 **끊기거나 깨지지 않았는지** — 파일과 일치해도 파일 자체가
        # 잘려 있을 수 있어 화면 문구를 따로 본다.
        r.assert_true(4, "EULA 본문 분량", len(tidy_shown) >= 1000,
                      expected="1,000자 이상",
                      actual=f"{len(tidy_shown)}자"
                             + (" — 본문이 비었거나 잘렸다" if len(tidy_shown) < 1000 else ""))
        broken = sorted({ch for ch in shown if ch == "�"})
        r.assert_true(4, "EULA 본문에 깨진 문자 없음", not broken,
                      expected="치환 문자(U+FFFD) 0개",
                      actual="없음" if not broken else f"{shown.count(chr(0xFFFD))}개 발견",
                      note="설치 화면이 약관을 잘못된 인코딩으로 읽으면 여기서 드러난다")
        head_ok = tidy_shown.lower().startswith("it is important to know the terms")
        r.assert_true(4, "EULA 첫 문장", head_ok,
                      expected="It is important to know the terms and conditions...",
                      actual=tidy_shown[:60] + ("..." if len(tidy_shown) > 60 else ""))
        for keyword in ("ARTICLE 1", "SOFTWARE LICENSE"):
            r.assert_true(4, f"EULA 본문에 [{keyword}] 포함", keyword in shown.upper(),
                          expected=keyword,
                          actual="포함" if keyword in shown.upper() else "없음")

        # 사람이 눈으로 되짚을 수 있게 **스크롤하며** 화면을 남긴다.
        eula_box = ui.find(WELCOME_EULA, "Edit")
        if eula_box is not None:
            os.makedirs(evidence_dir, exist_ok=True)
            shots = ui.scroll_through(
                eula_box,
                lambda i: os.path.join(evidence_dir, f"01_Welcome_EULA_{i + 1:02d}.png"),
                max_shots=EULA_MAX_SHOTS)
            # 상한에 걸렸으면 **그 사실을 적는다.** 그냥 "N장" 만 남기면 끝까지
            # 훑은 것처럼 읽힌다.
            capped = len(shots) >= EULA_MAX_SHOTS
            r.add(4, "EULA 전문 화면 캡처", PASS if shots else MANUAL,
                  expected="본문을 처음부터 끝까지 훑은 캡처",
                  actual=(f"{len(shots)}장"
                          + (f" (상한 {EULA_MAX_SHOTS}장에 걸려 뒷부분이 남았을 수 있다)"
                             if capped else " — 끝까지 훑음"))
                         if shots else "캡처 실패",
                  note="본문 판정은 위 문구 대조로 하고, 이 캡처는 사람이 되짚는 용도다")
            r.evidence.extend(shots)

    # Step 5. 동의 / 비동의 선택지
    accept, disaccept = ui.radio_selected(WELCOME_ACCEPT), ui.radio_selected(WELCOME_DISACCEPT)
    r.assert_true(5, "동의/비동의 선택지 2개 표시",
                  accept is not None and disaccept is not None,
                  expected="I accept / I do not accept 라디오 2개",
                  actual=f"accept={accept} disaccept={disaccept}")

    # Step 6. 동의하지 않으면 진행할 수 없다
    ui.select_radio(WELCOME_DISACCEPT)
    moved, page = ui.next_page()
    if moved:
        r.add(6, "비동의 상태에서 Next 차단", FAIL,
              expected="Welcome 에 머무름", actual=f"{page} 로 진행됨",
              note="Service Manual — 동의한 경우에만 Next 로 진행한다")
        ui.back_page()
    else:
        r.add(6, "비동의 상태에서 Next 차단", PASS,
              expected="Welcome 에 머무름", actual="진행되지 않음",
              note="Service Manual '해당 내용에 동의한다면 I accept the terms in the "
                   "License Agreement를 선택한 후 Next 버튼을 클릭하십시오'")

    # Step 7. 동의 후 진행
    ui.select_radio(WELCOME_ACCEPT)
    r.assert_true(7, "동의 선택 반영", ui.radio_selected(WELCOME_ACCEPT) is True,
                  expected="I accept 선택됨",
                  actual=ui.radio_selected(WELCOME_ACCEPT))
    r.evidence.append(_evidence(ui, evidence_dir, "01_Welcome"))
    moved, page = ui.next_page(expect="Configure Path")
    r.assert_equal(7, "Next 로 Configure Path 진행", "Configure Path", page)
    return r


def wizard_configure_path(ui, evidence_dir):
    """Pkg_Wizard_02 — 설치 경로 기본값."""
    r = TCResult("Pkg_Wizard_02", "Configure Path — 설치 경로 기본값")
    r.assert_equal(1, "현재 화면", "Configure Path", ui.current_page())

    system_drive = os.environ.get("SystemDrive", "C:")
    expected_viewer = os.path.join(system_drive + "\\", "Program Files", "Bellalun")
    viewer_path = ui.text_of(PATH_VIEWER_EDIT, "Edit")
    r.assert_equal(2, "Viewer 설치 기본 경로", expected_viewer, viewer_path,
                   note="SRS 08-10-10 / Service Manual — Windows 가 설치된 드라이브의 "
                        "Program Files\\Bellalun")

    db_path = ui.text_of(PATH_DB_EDIT, "Edit")
    r.assert_equal(3, "Database 기본 경로", EXPECTED_DB_PATH, db_path,
                   note="SRS 08-10-10 'Database 기본 경로: D:\\BellalunData'")

    drives = ui.find(PATH_DRIVE_LIST, "SysListView32")
    r.assert_true(4, "드라이브 목록(남은 용량) 표시", drives is not None,
                  expected="드라이브별 잔여 용량 목록",
                  actual="표시됨" if drives else "없음",
                  note="Service Manual — 드라이브의 남은 용량을 확인한 후 선택하도록 안내")

    guide = ui.text_of(PATH_GUIDE, "Static") or ""
    r.assert_true(4, "경로 안내 문구", "remaining space" in guide.lower(),
                  expected="Configure database path after check the remaining space.",
                  actual=guide or ui.text_of(PATH_TITLE, "Static"))

    r.evidence.append(_evidence(ui, evidence_dir, "02_ConfigurePath"))
    moved, page = ui.next_page(expect="Register Options")
    r.assert_equal(5, "Next 로 Register Options 진행", "Register Options", page)
    return r


def wizard_register_options(ui, choices, evidence_dir, probe_all=False):
    """Pkg_Wizard_03 — 설치 옵션(언어/테마/KIOSK) 선택지와 사용자 선택 적용.

    `choices` 는 {"language":.., "theme":.., "kiosk":..}. 값이 None 이면 그 항목은
    기본값을 그대로 둔다.

    `probe_all=True` 면 항목을 **전부 눌러 보며** 목록 전문을 대조한다(느리다).
    기본은 드롭다운을 한 번만 열어 개수·화면을 남기고 원하는 값만 고른다.
    """
    r = TCResult("Pkg_Wizard_03", "Register Options — 설치 옵션 선택지 및 적용")
    r.assert_equal(1, "현재 화면", "Register Options", ui.current_page())

    # Step 1. 옵션 라벨
    labels = {
        "Default Language": ui.text_of(OPT_LANG_LABEL, "Static"),
        "Default Theme": ui.text_of(OPT_THEME_LABEL, "Static"),
        "KIOSK Option": ui.text_of(OPT_KIOSK_LABEL, "Static"),
    }
    for want, actual in labels.items():
        r.assert_true(1, f"옵션 항목 [{want}] 표시",
                      want.lower() in (actual or "").lower(),
                      expected=want, actual=actual)

    # 안내 문구와 실제 항목이 맞는지 — 문구는 viewer mode / image processing
    # parameter 도 고르라고 하는데 화면에는 그 항목이 없다(실측).
    guide = ui.text_of(OPT_GUIDE, "Static") or ""
    promised = [word for word in ("viewer mode", "image processing")
                if word in guide.lower()]
    if promised:
        r.add(1, "안내 문구가 약속한 항목이 화면에 있는가", MANUAL,
              expected="안내 문구의 항목이 모두 화면에 존재",
              actual=f"문구는 {promised} 도 선택하라고 하지만 화면 항목은 "
                     f"Default Language / Default Theme / KIOSK Option 3개뿐",
              note=f"안내 문구 원문: {guide.strip()!r} — 문구와 화면 구성이 다르므로 "
                   f"사양 확인이 필요하다(문구 정정 또는 항목 누락 여부).")

    # Step 2~4. 선택지 확인과 선택을 **드롭다운 한 번**으로 끝낸다.
    #
    # 예전에는 항목을 전부 눌러 보며 값을 모았다(`combo_options`). 목록 전체를
    # 문자열로 대조할 수 있어 정확하지만, **고를 값이 이미 정해진 실행에서는 화면을
    # 불필요하게 휘젓는다**(2026-08-26 사용자 지시로 기본 동작에서 뺐다).
    # 지금은 드롭다운을 한 번 열어 **항목 수를 세고 화면을 남긴 뒤**, 사양 목록에서의
    # 위치로 원하는 값을 눌러 고르고 **콤보 값을 읽어 검증**한다.
    # 목록 전문 대조가 필요하면 `probe_all=True` 로 예전 방식이 돌아온다.
    specs = (
        (2, "Default Language", OPT_LANG_COMBO, EXPECTED_LANGUAGES, "language",
         "SRS 01-10-30 공식 지원 언어 4종"),
        (3, "Default Theme", OPT_THEME_COMBO, EXPECTED_THEMES, "theme",
         "SRS 01-10-20 UI Theme 3종"),
        (4, "KIOSK Option", OPT_KIOSK_COMBO, EXPECTED_KIOSK, "kiosk",
         "SRS 08-10-10 KIOSK 사용 여부는 신규 설치 시에도 설정할 수 있다"),
    )
    os.makedirs(evidence_dir, exist_ok=True)
    defaults, applied = {}, {}
    for step, label, ctrl, expected, key, note in specs:
        current = ui.combo_text(ctrl)
        defaults[label] = current
        want = choices.get(key)

        if probe_all:
            options, current = ui.combo_options(ctrl)
            defaults[label] = current
            r.assert_equal(step, f"[{label}] 선택 가능 항목", expected, options,
                           note=note + " (전수 순회)")
            got = ui.select_combo(ctrl, want) if want else current
            by_order = None
            count = len(options)
        else:
            capture = os.path.join(evidence_dir, f"03_{key}_options.png")
            picked = ui.choose_option(ctrl, want, expected, capture)
            if picked is None:
                r.add(step, f"[{label}] 선택지 조회", FAIL, actual="콤보를 찾지 못했다")
                continue
            count, got, by_order = picked["count"], picked["value"], picked["by_order"]
            if picked["capture"]:
                r.evidence.append(picked["capture"])
            r.assert_equal(step, f"[{label}] 선택 가능 항목 수", len(expected), count,
                           note=note + f" — 기대 목록 {expected}. 항목 텍스트는 커스텀 "
                                       f"렌더링이라 읽히지 않으므로 개수로 대조하고 "
                                       f"드롭다운 화면을 증거로 남긴다")
            if by_order:
                target = want or current
                r.add(step, f"[{label}] 목록 {expected.index(target) + 1}번째 = {target!r}",
                      PASS, expected=target, actual=target,
                      note="사양 목록에서의 위치를 눌러 고른 뒤 값을 읽어 확인했다 — "
                           "순서가 사양과 다르면 값이 달라져 여기서 드러난다")
            elif picked["fell_back"]:
                r.add(step, f"[{label}] 목록 순서가 사양과 다름", MANUAL,
                      expected=f"사양 순서 {expected}",
                      actual=f"위치로 고른 값이 기대와 달라 전수 순회로 되짚었다 "
                             f"(최종 {got!r})",
                      note="순서가 바뀌었을 뿐 값 자체는 맞을 수 있다. "
                           "probe_all=True 로 목록 전문을 확인하십시오")
        applied[key] = got

    # Step 5. 기본값
    r.assert_equal(5, "[Default Language] 기본값", "English", defaults["Default Language"],
                   note="Config.xml LanguageList 의 첫 항목")
    r.assert_equal(5, "[Default Theme] 기본값", "Pure White", defaults["Default Theme"],
                   note="Config.xml Theme Default='Pure White'")

    # KIOSK 기본값은 레지스트리 Shell 값이 정한다 (SRS 08-10-10).
    shell = sysinfo.registry_value(
        r"HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon", "Shell")
    shell_is_viewer = bool(shell) and "bellalun" in shell.lower()
    expected_kiosk_default = "Use" if shell_is_viewer else "Not Use"
    r.assert_equal(5, "[KIOSK Option] 기본값", expected_kiosk_default,
                   defaults["KIOSK Option"],
                   note=f"SRS 08-10-10 'Registry의 Shell에 뷰어 경로가 설정되어 있을 "
                        f"경우는 KIOSK Use가 기본 설정. 아닌 경우에는 Not Use가 기본'. "
                        f"현재 Shell={shell!r}")

    # Step 6. 선택 결과
    for label, key in (("Default Language", "language"), ("Default Theme", "theme"),
                       ("KIOSK Option", "kiosk")):
        want = choices.get(key)
        got = applied.get(key)
        if want:
            r.assert_equal(6, f"[{label}] 선택 적용", want, got)
        else:
            r.add(6, f"[{label}] 선택", SKIP,
                  expected="사용자 미지정", actual=f"기본값 {got!r} 유지")

    r.evidence.append(_evidence(ui, evidence_dir, "03_RegisterOptions"))
    moved, page = ui.next_page(expect="Input License")
    r.assert_equal(7, "Next 로 Input License 진행", "Input License", page)
    return r, applied


def wizard_input_license(ui, evidence_dir):
    """Pkg_Wizard_04 — Hardware Key 와 라이선스 입력칸의 **구조만** 점검한다.

    **라이선스를 자동화가 대신 넣지 않는다**(2026-08-26 사용자 지시). 실제 설치에
    쓰이는 값이라 사람이 화면에서 직접 넣고 Next 까지 누른다. 그래서 여기서는
    화면이 사양대로 만들어졌는지만 보고, 입력 결과는 `license_entry_result()` 가
    사람이 넘긴 뒤에 기록한다.

    같은 이유로 **"미입력 상태에서 Next" 도 시도하지 않는다** — 자동화가 Next 를
    누르면 사람이 입력하려던 화면에 팝업이 끼어든다.
    """
    r = TCResult("Pkg_Wizard_04", "Input License — Hardware Key 및 라이선스 입력")
    r.assert_equal(1, "현재 화면", "Input License", ui.current_page())

    # Step 1. Hardware Key
    hw = ui.hardware_key()
    r.assert_true(1, "Hardware Key 표시", bool(hw) and len(hw) >= 16,
                  expected="Hardware Key 문자열",
                  actual=hw or "표시되지 않음",
                  note="Service Manual '라이선스 창에 표시된 Hardware Key로 발급된 "
                       "라이선스를 입력'")
    r.assert_true(1, "Hardware Key 라벨",
                  "hardware key" in (ui.text_of(LIC_HWKEY_LABEL, "Static") or "").lower(),
                  expected="Hardware Key :", actual=ui.text_of(LIC_HWKEY_LABEL, "Static"))

    # Step 2. 입력 안내와 입력칸 자릿수
    guide = ui.text_of(LIC_GUIDE, "Static") or ""
    limits = ui.license_limits()
    r.assert_equal(2, "라이선스 입력칸 수", len(LICENSE_SEGMENTS), len(limits),
                   note=ui.text_of(LIC_LABEL, "Static") or "")
    r.assert_equal(2, "입력칸별 자릿수", list(LICENSE_SEGMENTS), limits)
    stated = re.search(r"(\d+)\s*-?\s*character", guide, re.I)
    if stated:
        r.assert_equal(2, "안내 문구의 자릿수와 입력칸 합계",
                       int(stated.group(1)), sum(limits),
                       note=f"안내 문구: {guide.strip()!r}")
    else:
        r.manual(2, "안내 문구의 자릿수 명시", "문구에서 자릿수를 찾지 못했다",
                 expected="N-character license key", actual=guide.strip())

    r.evidence.append(_evidence(ui, evidence_dir, "04_InputLicense"))
    return r


def license_entry_result(r, ui, reached_summary, waited_seconds, evidence_dir):
    """사람이 라이선스를 넣고 Next 를 누른 뒤의 결과를 `Pkg_Wizard_04` 에 붙인다."""
    if reached_summary:
        r.add(3, "라이선스 입력 후 Summary 진행", PASS,
              expected="Summary 로 진행",
              actual=f"{int(waited_seconds)}초 만에 Summary 도달",
              note="SRS 08-10-10 '적합하지 않은 라이선스를 입력할 경우 설치 진행이 "
                   "불가능하다' — 진행됐다는 것은 인스톨러가 라이선스를 받아들였다는 뜻")
    else:
        r.add(3, "라이선스 입력 후 Summary 진행", BLOCKED,
              expected="Summary 로 진행",
              actual=f"{int(waited_seconds)}초 기다렸으나 현재 화면은 "
                     f"{ui.current_page()!r}",
              note="사람이 라이선스를 넣고 Next 를 누르지 않았거나, 인스톨러가 "
                   "입력값을 받아들이지 않았다")
        r.evidence.append(_evidence(ui, evidence_dir, "04_InputLicense_대기중단"))
    return r


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
# 실측한 Summary 구성 (2026-08-26). "항목 :" 다음 줄에 값이 온다.
SUMMARY_KEYS = ("Operation System", "Viewer Version", "Database Location",
                "Viewer Location", "Default Language", "Default Theme",
                "License", "XIPL License", "XIPL Tomo License")
LICENSE_PATTERN = re.compile(r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{5}-[A-Za-z0-9]{4}-"
                             r"[A-Za-z0-9]{5}$")


def _parse_summary(text):
    """Summary 본문을 {항목: 값} 으로 푼다.

    본문은 `' 항목 :'` 줄 다음에 들여쓴 값 줄이 오는 형태다(실측).
    """
    items, key = {}, None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.endswith(":"):
            key = line[:-1].strip()
            items.setdefault(key, "")
        elif key:
            items[key] = f"{items[key]} {line}".strip() if items[key] else line
    return items


def _mask(value):
    """라이선스처럼 그대로 남기면 안 되는 값을 가린다."""
    parts = (value or "").split("-")
    if len(parts) < 2:
        return value
    return "-".join([parts[0]] + ["*" * len(p) for p in parts[1:]])


def wizard_summary(ui, expected_values, evidence_dir):
    """Pkg_Wizard_05 — Summary 에 선택한 설치 정보가 그대로 실렸는지.

    본문은 한 화면에 다 담기지 않아 **스크롤하며 캡처**한다(2026-08-26 사용자 지시).
    판정 자체는 `WM_GETTEXT` 로 읽은 전문으로 하므로 스크롤 위치와 무관하게 정확하다.

    라이선스는 **입력이 제대로 됐는지만** 본다 — 값 자체는 사람이 직접 넣은 것이라
    자동화가 기대값을 갖고 있지 않고, 기록에는 가려서 남긴다.
    """
    r = TCResult("Pkg_Wizard_05", "Summary — 선택한 설치 정보 확인")
    r.assert_equal(1, "현재 화면", "Summary", ui.current_page())

    title = ui.text_of(SUM_TITLE, "Static") or ""
    r.assert_true(1, "Summary 제목", "ready to install" in title.lower(),
                  expected="Ready to Install the Program", actual=title)
    guide = ui.text_of(SUM_GUIDE, "Static") or ""
    r.assert_true(1, "Summary 안내 문구", "install" in guide.lower(),
                  expected="Click Install to continue with the installation.",
                  actual=guide.strip())

    summary_text = ui.text_of(SUM_TEXT, "Edit") or ""
    items = _parse_summary(summary_text)
    safe_text = summary_text
    if items.get("License"):
        safe_text = safe_text.replace(items["License"], _mask(items["License"]))
    r.add(2, "Summary 전문", PASS if summary_text else FAIL,
          expected="설치 정보 요약 표시",
          actual=safe_text.strip() or "비어 있음",
          note="Service Manual '설치 정보를 확인하고 Install 버튼을 클릭'. "
               "라이선스는 가려서 기록한다")

    # Step 2. 항목 구성
    missing_keys = [k for k in SUMMARY_KEYS if k not in items]
    r.assert_true(2, "Summary 항목 구성", not missing_keys,
                  expected=list(SUMMARY_KEYS),
                  actual=list(items) if missing_keys else "실측한 9개 항목 모두 표시")

    # Step 3. 선택한 값이 그대로 실렸는가
    for label, (key, value) in expected_values.items():
        if not value:
            r.add(3, f"Summary [{label}]", SKIP,
                  expected="앞 단계에서 값을 확정하지 못함", actual="대조 생략")
            continue
        actual = items.get(key)
        if actual is None:
            r.add(3, f"Summary 에 [{label}] 항목 없음", MANUAL,
                  expected=f"{key} : {value}",
                  actual=f"Summary 에 '{key}' 항목이 없다 (표시 항목: {list(items)})",
                  note="설치 정보 요약에 어떤 항목이 실려야 하는지는 사양서·매뉴얼에 "
                       "명시돼 있지 않다. 그래서 결함으로 단정하지 않고 사실만 남긴다 "
                       "— 사양 확인이 필요하다")
            continue
        r.assert_equal(3, f"Summary [{label}]", value, actual,
                       note="Register Options / Configure Path 에서 고른 값과 대조")

    # Step 4. 라이선스는 **입력이 제대로 됐는지만** 본다
    license_value = items.get("License")
    r.assert_true(4, "라이선스 입력됨", bool(license_value),
                  expected="License 항목에 값 표시",
                  actual=_mask(license_value) if license_value else "비어 있음")
    if license_value:
        r.assert_true(4, "라이선스 형식 (4-5-4-5)",
                      bool(LICENSE_PATTERN.match(license_value)),
                      expected="XXXX-XXXXX-XXXX-XXXXX",
                      actual=_mask(license_value),
                      note="값 자체는 사람이 직접 넣은 것이라 대조하지 않는다. "
                           "형식과 입력 여부만 본다")
    for key in ("XIPL License", "XIPL Tomo License"):
        value = items.get(key)
        r.assert_true(4, f"{key} 자동 발급", bool(value),
                      expected="자동 발급된 라이선스 표시",
                      actual=_mask(value) if value else "표시되지 않음",
                      note="SRS 08-10-10 'Viewer 라이선스를 사용하여 XIPL 라이선스를 "
                           "자동 발급 등록한다'")

    # Step 5. 스크롤하며 화면을 남긴다
    box = ui.find(SUM_TEXT, "Edit")
    if box is not None:
        os.makedirs(evidence_dir, exist_ok=True)
        shots = ui.scroll_through(
            box, lambda i: os.path.join(evidence_dir, f"05_Summary_{i + 1:02d}.png"))
        r.add(5, "Summary 전문 화면 캡처", PASS if shots else MANUAL,
              expected="요약을 처음부터 끝까지 훑은 캡처",
              actual=f"{len(shots)}장" if shots else "캡처 실패",
              note="본문이 한 화면에 다 들어가지 않아 위에서 아래로 스크롤하며 남긴다")
        r.evidence.extend(shots)
    r.evidence.append(_evidence(ui, evidence_dir, "05_Summary_전체화면"))

    r.add(6, "실제 설치는 수행하지 않음", SKIP,
          expected="Install Software 단계는 사람이 직접 시작",
          actual="Install 버튼을 누르지 않고 마법사를 열어 둔 채 종료",
          note="이 점검의 범위는 Summary 까지다")
    return r, items



def _documents_dir():
    """Windows 가 알려 주는 **현재 사용자의 Documents 폴더**. 모르면 None.

    Documents 는 OneDrive 등으로 옮겨져 있을 수 있어 경로를 조립하지 않고
    셸에 물어본다(`SHGetFolderPathW`, CSIDL_PERSONAL=5).
    """
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
            return buf.value or None
    except Exception:
        pass
    return None


def install_log_dir():
    """설치 로그 폴더의 **실제 경로**.

    사양서 표기(`SPEC_INSTALL_LOG_DIR`)를 그대로 쓰면 안 되는 이유는 그 상수의
    주석에 적어 두었다. 실제로 있는 폴더를 우선하고, 하나도 없으면 가장 그럴듯한
    후보(사용자 Documents 아래)를 돌려준다.
    """
    candidates = []
    docs = _documents_dir()
    if docs:
        candidates.append(os.path.join(docs, "Bellalun", "InstallLog"))
    candidates.append(os.path.join(os.path.expanduser("~"), "Documents",
                                   "Bellalun", "InstallLog"))
    candidates.append(SPEC_INSTALL_LOG_DIR)
    for path in candidates:
        if os.path.isdir(path):
            return path
    return candidates[0]


def install_log_created(before, after):
    """Pkg_Static_03 — Install.exe 실행 시 설치 로그가 생기는가.

    사양(SRS 08-10-10)은 **"Install 프로그램을 실행할 때마다 파일이 하나씩
    생성됨"** 이라고 못박는다. 실측으로 확인했듯 **설치를 시작하지 않고 창만 띄웠다
    닫아도 로그가 하나 생긴다**(약 242바이트). 그래서 여기서 정상/이상을 가릴 수
    있고, 없으면 그대로 FAIL 이다.

    2026-08-26 한때 이 판정을 MANUAL 로 낮췄던 적이 있는데, 그것은 사양서 표기
    경로(`C:\\Documents\\...`)를 드라이브 루트로 잘못 읽어 "로그가 없다" 고 본
    탓이었다. 경로를 바로잡자 정상 생성이 확인됐다(`install_log_dir`).
    """
    r = TCResult("Pkg_Static_03", "설치 로그 생성 확인")
    log_dir = install_log_dir()
    note = (f"SRS 08-10-10 '로그 저장 위치: {SPEC_INSTALL_LOG_DIR}, 파일명: "
            f"YYYYMMDD_hhmmss.log, Install 프로그램을 실행할 때마다 파일이 하나씩 "
            f"생성됨'. 실제 위치는 사용자 Documents 아래이며 이 회차는 {log_dir}")
    if before is None:
        r.skip(1, "설치 로그 생성", "인스톨러를 이 점검이 직접 띄우지 않아 비교 불가",
               expected=log_dir)
        return r
    created = sorted(set(after) - set(before))
    if not created:
        state = ("폴더는 있으나 새 파일이 없음" if os.path.isdir(log_dir)
                 else "폴더 자체가 없음")
        r.add(1, "Install.exe 실행 시 설치 로그 생성", FAIL,
              expected=f"{log_dir} 에 파일 1개 생성",
              actual=f"{log_dir}: {state}", note=note)
        return r
    r.add(1, "Install.exe 실행 시 설치 로그 생성", PASS,
          expected=f"{log_dir} 에 파일 1개 생성",
          actual=created, note=note)
    for name in created:
        ok = bool(re.fullmatch(r"\d{8}_\d{6}\.log", name))
        r.assert_true(2, f"로그 파일명 규칙 [{name}]", ok,
                      expected="YYYYMMDD_hhmmss.log", actual=name)
    return r


def install_log_names():
    """설치 로그 폴더의 현재 파일 목록. 폴더가 없으면 빈 목록."""
    path = install_log_dir()
    if not os.path.isdir(path):
        return []
    return sorted(os.listdir(path))
