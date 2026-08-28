# -*- coding: utf-8 -*-
"""설치 패키지 검증의 **대화형 실행 흐름**.

판정 로직은 `tests/install_package.py` 에 있고, 이 파일은 사람에게 묻고 화면을
넘기는 순서만 담당한다.

    python run.py verify-install-package

전체 회귀(`run-regression`)에 **들어 있지 않다.** 회귀는 설치된 Viewer 를 보고
이 점검은 설치 이전 패키지를 보므로 전제가 다르다. `run.py` 는 이 명령을
`Context` 생성 **이전**에 가로챈다 — `Context` 는 `BellalunData` 를 못 찾으면
예외를 던지는데, 신규 설치 점검은 바로 그 폴더가 없는 PC 에서 도는 일이다.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime

from core import sysinfo
from core.installer_ui import (InstallerUi, OPT_KIOSK_COMBO, OPT_LANG_COMBO,
                               OPT_THEME_COMBO)
from core.result import BLOCKED, FAIL, MANUAL, PASS, SKIP, TCResult, write_reports
from tests import install_package as pkg

BANNER = "Bellalun 설치 패키지 검증 (신규 설치용 · 실제 설치는 하지 않습니다)"


# --------------------------------------------------------------------------
# 사용자 입력
# --------------------------------------------------------------------------
#: 터미널 입력이 끊겼는가(파이프로 실행했거나 Ctrl+C). **되묻는 루프는 이 값을
#: 보고 멈춰야 한다** — 2026-08-26 예행 실행에서 stdin 이 빈 채로 시작하자 경로
#: 되묻기가 무한 루프에 빠졌다. 한 번 끊긴 입력은 다시 열리지 않는다.
_INPUT_CLOSED = False


def input_closed():
    return _INPUT_CLOSED


def _ask(prompt, default=""):
    """한 줄 입력. 그냥 Enter 면 기본값. 입력이 끊기면 기본값으로 진행한다."""
    global _INPUT_CLOSED
    if _INPUT_CLOSED:
        return default
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        _INPUT_CLOSED = True
        return default
    return answer or default


def _ask_yes(prompt, default=True):
    hint = "Y/n" if default else "y/N"
    answer = _ask(f"{prompt} ({hint})", "").lower()
    if not answer:
        return default
    return answer.startswith("y")


def _ask_choice(label, options, default=None):
    """목록에서 하나 고르게 한다. 번호 또는 값 그대로 입력."""
    print(f"\n  [{label}] 선택 가능 항목")
    for i, option in enumerate(options, 1):
        mark = "  <- 현재 기본값" if option == default else ""
        print(f"    {i}) {option}{mark}")
    while True:
        answer = _ask(f"  {label} 선택 (번호 또는 값, Enter=기본값 유지)", "")
        if not answer:
            return None                      # 기본값 유지
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        for option in options:
            if answer.lower() == option.lower():
                return option
        print(f"    '{answer}' 는 선택지에 없습니다. 다시 입력하십시오.")


def _wait_for_license(ui, timeout=1800, poll=1.5):
    """사람이 라이선스를 넣고 Next 를 누를 때까지 기다린다.

    **자동화가 라이선스를 대신 넣지 않는다**(2026-08-26 사용자 지시). 실제 설치에
    쓰이는 값이라 사람이 설치 화면에서 직접 넣는다. 여기서는 안내만 하고 화면이
    Summary 로 넘어가는 것을 기다린다. 잘못된 라이선스면 인스톨러가 팝업으로
    막으므로 그 처리도 사람 몫이다.

    반환: (Summary 에 닿았는가, 기다린 초)
    """
    total = sum(pkg.LICENSE_SEGMENTS)
    bar = "─" * 68
    print("\n  " + bar)
    print("  ▶ 라이선스를 **직접 입력**하고 [ Next > ] 를 눌러 주십시오.")
    print(f"      · 형식        : 4-5-4-5 ({total}자)")
    print(f"      · Hardware Key: {ui.hardware_key()}")
    print("      · 자동화는 값을 대신 넣지 않습니다. 화면이 Summary 로 넘어가면")
    print("        이어서 요약 내용을 확인합니다.")
    print("  " + bar)

    start = time.time()
    announced, last_popup = 0, None
    while time.time() - start < timeout:
        if ui.current_page() == "Summary":
            waited = time.time() - start
            print(f"  Summary 로 넘어간 것을 확인했습니다 ({int(waited)}초). "
                  f"이어서 확인합니다.\n")
            return True, waited
        if not ui.alive():
            return False, time.time() - start

        # 인스톨러가 띄운 안내(잘못된 라이선스 등)를 터미널에도 전한다.
        # **닫지 않는다** — 사람이 화면에서 보고 직접 처리한다.
        popup = ui.popup()
        if popup is not None:
            text = ui.popup_text(popup)
            if text and text != last_popup:
                print(f"    [인스톨러 안내] {text}")
                last_popup = text
        else:
            last_popup = None

        minutes = int(time.time() - start) // 60
        if minutes > announced:
            announced = minutes
            print(f"    ... 기다리는 중 ({minutes}분). 현재 화면: {ui.current_page()}")
        time.sleep(poll)
    return False, time.time() - start


# --------------------------------------------------------------------------
# 인스톨러 기동
# --------------------------------------------------------------------------
def _find_default_package():
    """자주 두는 자리에서 Install.exe 를 찾아 기본값으로 제시한다."""
    home = os.path.expanduser("~")
    roots = [os.path.join(home, "Desktop"), os.path.join(home, "Downloads"),
             r"C:\Install", home]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            entries = sorted(os.listdir(root), reverse=True)
        except OSError:
            continue
        for name in entries:
            candidate = os.path.join(root, name)
            if os.path.isfile(os.path.join(candidate, "Install.exe")):
                return candidate
        if os.path.isfile(os.path.join(root, "Install.exe")):
            return root
    return ""


def _as_package_dir(text):
    """입력 문자열을 패키지 폴더로 정규화한다. Install.exe 가 없으면 None."""
    if not text:
        return None
    path = os.path.abspath(text.strip().strip('"'))
    if os.path.isfile(path) and os.path.basename(path).lower() == "install.exe":
        path = os.path.dirname(path)
    return path if os.path.isfile(os.path.join(path, "Install.exe")) else None


def _resolve_package_dir(given=None, tries=5):
    """Install.exe 가 있는 폴더를 확정한다. 확정하지 못하면 None.

    `--package` 로 받은 값이 맞으면 **묻지 않는다**(비대화형 실행 가능).
    입력이 끊긴 실행에서는 되묻지 않고 곧바로 포기한다.
    """
    if given:
        path = _as_package_dir(given)
        if path:
            return path
        print(f"  --package 로 준 경로에서 Install.exe 를 찾지 못했습니다: {given}")

    default = _find_default_package()
    for _ in range(tries):
        answer = _ask("Install.exe 가 있는 폴더 경로", default)
        path = _as_package_dir(answer)
        if path:
            return path
        print("  경로가 필요합니다." if not answer
              else f"  '{answer}' 에서 Install.exe 를 찾지 못했습니다.")
        if input_closed():
            return None
        default = ""
    return None


def _close_running_installer(ui):
    """이미 떠 있는 Install.exe 를 닫는다. 로그 생성 검사를 위해 새로 띄워야 한다."""
    if ui.pid is None:
        return True
    print("\n  이미 실행 중인 Install.exe 가 있습니다.")
    if not _ask_yes("  닫고 새로 시작할까요?", True):
        return False
    subprocess.run(["taskkill", "/F", "/IM", "Install.exe"],
                   capture_output=True)
    for _ in range(20):
        time.sleep(0.5)
        ui._pid = None
        if ui.pid is None:
            return True
    return False


def _launch(ui, package_dir, timeout=60):
    exe = os.path.join(package_dir, "Install.exe")
    subprocess.Popen([exe], cwd=package_dir)
    limit = time.time() + timeout
    while time.time() < limit:
        ui._pid = None
        if ui.alive():
            time.sleep(1.5)                 # 첫 화면이 그려질 때까지
            return True
        time.sleep(1.0)
    return False


# --------------------------------------------------------------------------
# 결과 정리
# --------------------------------------------------------------------------
def _tally(results):
    counts = {PASS: 0, FAIL: 0, MANUAL: 0, SKIP: 0, BLOCKED: 0}
    for r in results:
        for c in r.checks:
            counts[c.status] = counts.get(c.status, 0) + 1
    return counts


def _option_log(package_dir, applied, paths, summary_items):
    """설치 후 대조에 쓸 **선택 옵션 기록**.

    `config_json_install_option` 은 `config.json > install_option` 에 그대로 넣을
    수 있는 형태다. 그 값으로 설치 뒤 `TC_Basic_Install_07`(Theme/Language/Kiosk
    적용·유지)이 DB 와 대조한다.
    """
    kiosk = applied.get("kiosk")
    return {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "package_dir": package_dir,
        "package_version": sysinfo.file_version(
            os.path.join(package_dir, "Install.exe")),
        "install_type": "신규 설치",
        "selected": {
            "language": applied.get("language"),
            "theme": applied.get("theme"),
            "kiosk": kiosk,
            "viewer_path": paths.get("viewer"),
            "database_path": paths.get("database"),
            "license": pkg._mask(summary_items.get("License")),
        },
        "config_json_install_option": {
            "expected_theme": applied.get("theme"),
            "expected_language": applied.get("language"),
            "expected_kiosk": 1 if kiosk == "Use" else 0,
        },
        "summary": {k: (pkg._mask(v) if "License" in k else v)
                    for k, v in (summary_items or {}).items()},
        "note": "라이선스는 첫 칸만 남기고 가렸습니다. "
                "설치 후 이 값들이 실제로 적용됐는지는 "
                "`python run.py run-auto` 또는 TC_Basic_Install_07 로 확인하십시오.",
    }


# --------------------------------------------------------------------------
# 본 흐름
# --------------------------------------------------------------------------
def run_interactive(config_path="config.json", package_dir=None,
                    preset=None, probe_all=False):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = os.path.dirname(os.path.abspath(config_path)) or os.getcwd()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(root, "Reports", "InstallPackage")
    evidence_dir = os.path.join(root, "Evidence", "InstallPackage", stamp)

    print("=" * 78)
    print(BANNER)
    print("=" * 78)
    print("Welcome → Configure Path → Register Options → Input License → Summary")
    print("까지만 진행합니다. **Install 버튼은 누르지 않습니다.**\n")

    if not sysinfo.is_elevated():
        print("!! 관리자 권한이 아닙니다. Windows 가 다른 권한 수준의 창에 대한 "
              "입력을 막으므로(UIPI)\n"
              "   인스톨러 조작이 실패합니다. 관리자 권한 터미널에서 다시 "
              "실행하십시오.")
        if not _ask_yes("   그래도 계속할까요?", False):
            return 2

    package_dir = _resolve_package_dir(package_dir)
    if not package_dir:
        print("Install.exe 가 있는 폴더를 확정하지 못해 중단합니다.")
        print('  python run.py verify-install-package --package "<폴더 경로>"'
              " 형태로 경로를 직접 줄 수 있습니다.")
        return 2
    print(f"\n검증 대상: {package_dir}\n")

    results = []
    # 패키지 점검은 **결함을 모아서 한 번에 보고**하는 것이 목적이라 첫 FAIL 에서
    # 멈추지 않는다. 회귀(`run.py`)는 반대로 FAIL 이 나면 그 TC 를 중단한다.
    # 이 대입이 회귀에 새지 않는 이유: 이 명령은 `Context` 생성 전에 가로채는
    # **단독 실행**이고, 프로세스가 끝나면 클래스 속성도 함께 사라진다.
    TCResult.stop_on_fail = False

    # --- 1. 정적 검증 ---------------------------------------------------
    print("[1/3] 패키지 정적 검증 ...")
    results.append(pkg.static_package(package_dir))
    results.append(pkg.static_config(package_dir))
    for r in results:
        _print_tc(r)

    # --- 2. 인스톨러 기동 ------------------------------------------------
    ui = InstallerUi()
    if not _close_running_installer(ui):
        print("실행 중인 Install.exe 를 닫지 못해 중단합니다.")
        return 2
    logs_before = pkg.install_log_names()
    print("\n[2/3] Install.exe 실행 (관리자 권한 확인 창이 뜨면 예를 누르십시오) ...")
    if not _launch(ui, package_dir):
        print("Install.exe 창을 찾지 못했습니다. 중단합니다.")
        results.append(_blocked("Pkg_Wizard_01", "Welcome — EULA 및 설치 단계 구성",
                                "Install.exe 창이 뜨지 않았다"))
        _finish(results, out_dir, stamp, None, package_dir)
        return 1
    ui.bring_to_front()
    results.append(pkg.install_log_created(logs_before,
                                          pkg.install_log_names()))
    _print_tc(results[-1])

    # --- 3. 마법사 진행 --------------------------------------------------
    print("\n[3/3] 설치 마법사 확인 ...")
    applied, summary_items = {}, {}
    paths = {}
    try:
        welcome = pkg.wizard_welcome(ui, package_dir, evidence_dir)
        results.append(welcome)
        _print_tc(welcome)

        if len(ui.menu_items()) != 6:
            print("\n!! 설치 단계가 6개가 아닙니다 — 신규 설치 구성이 아닙니다.")
            print("   업그레이드 화면(Welcome/Summary/Install Software)일 수 있습니다.")
            print("   이 점검은 신규 설치 전용이므로 여기서 멈춥니다.")
            _finish(results, out_dir, stamp, None, package_dir)
            return 1

        if ui.current_page() == "Configure Path":
            path_tc = pkg.wizard_configure_path(ui, evidence_dir)
            results.append(path_tc)
            _print_tc(path_tc)
            paths = {"viewer": _actual_of(path_tc, "Viewer 설치 기본 경로"),
                     "database": _actual_of(path_tc, "Database 기본 경로")}

        if ui.current_page() == "Register Options":
            options = _collect_choices(ui, preset)
            opt_tc, applied = pkg.wizard_register_options(
                ui, options, evidence_dir, probe_all=probe_all)
            results.append(opt_tc)
            _print_tc(opt_tc)

        if ui.current_page() == "Input License":
            lic_tc = pkg.wizard_input_license(ui, evidence_dir)
            reached, waited = _wait_for_license(ui)
            pkg.license_entry_result(lic_tc, ui, reached, waited, evidence_dir)
            results.append(lic_tc)
            _print_tc(lic_tc)

        if ui.current_page() == "Summary":
            # {표시 이름: (Summary 항목 이름, 앞 단계에서 고른 값)}
            expected = {
                "Viewer 설치 경로": ("Viewer Location", paths.get("viewer")),
                "Database 경로": ("Database Location", paths.get("database")),
                "Default Language": ("Default Language", applied.get("language")),
                "Default Theme": ("Default Theme", applied.get("theme")),
                "KIOSK Option": ("KIOSK Option", applied.get("kiosk")),
            }
            sum_tc, summary_items = pkg.wizard_summary(ui, expected, evidence_dir)
            results.append(sum_tc)
            _print_tc(sum_tc)
    except Exception as exc:                 # 실패 지점을 기록으로 남긴다
        import traceback
        traceback.print_exc()
        results.append(_blocked("Pkg_Wizard_99", "마법사 진행 중 예외",
                                f"{type(exc).__name__}: {exc}"))

    option_log = _option_log(package_dir, applied, paths, summary_items)
    _finish(results, out_dir, stamp, option_log, package_dir)

    # --- 마무리 안내 ------------------------------------------------------
    print("\n" + "=" * 78)
    if ui.alive():
        print("자동화를 종료합니다. **프로그램을 설치하세요!**")
        print(f"  현재 화면: {ui.current_page()}")
        print("  Install 버튼을 직접 눌러 Install Software 단계를 진행하십시오.")
        print("  (설치를 하지 않으려면 Cancel 을 누르십시오.)")
    else:
        print("Install.exe 창이 닫혀 있습니다. 설치를 진행하려면 다시 실행하십시오.")
    print("=" * 78)

    counts = _tally(results)
    return 1 if counts.get(FAIL) else 0


# --------------------------------------------------------------------------
def _collect_choices(ui, preset=None):
    """Register Options 에서 쓸 값을 정한다.

    선택지는 **사양서가 정한 목록**을 보여 준다. 화면의 실제 항목 텍스트는 커스텀
    렌더링이라 읽으려면 항목을 전부 눌러 봐야 하는데, **고를 값이 이미 정해진
    실행에서 화면을 그렇게 휘저을 이유가 없다**(2026-08-26 사용자 지시).
    실제 화면이 사양과 맞는지는 `Pkg_Wizard_03` 이 드롭다운을 **한 번만** 열어
    항목 수를 세고 화면을 남겨 확인한다.

    `preset` 으로 값을 미리 주면(명령행 `--language` 등) 묻지 않는다.
    """
    picked = {}
    for key, label, ctrl, options in (
            ("language", "Default Language", OPT_LANG_COMBO, pkg.EXPECTED_LANGUAGES),
            ("theme", "Default Theme", OPT_THEME_COMBO, pkg.EXPECTED_THEMES),
            ("kiosk", "KIOSK Option", OPT_KIOSK_COMBO, pkg.EXPECTED_KIOSK)):
        given = (preset or {}).get(key)
        if given:
            picked[key] = given
            print(f"\n  [{label}] {given}   (명령행에서 지정)")
            continue
        picked[key] = _ask_choice(label, options, ui.combo_text(ctrl))
    return picked


def _actual_of(result, title_contains):
    for c in result.checks:
        if title_contains in c.title:
            return c.actual
    return None


def _blocked(tc_id, title, reason):
    r = TCResult(tc_id, title)
    r.add(0, title, BLOCKED, actual=reason, stop=False)
    return r


def _print_tc(result):
    counts = _tally([result])
    line = "  ".join(f"{k} {v}" for k, v in counts.items() if v)
    print(f"  - {result.tc_id} {result.title}: {line}")
    for c in result.checks:
        if c.status in (FAIL, BLOCKED):
            print(f"      [{c.status}] Step {c.step} {c.title}")
            print(f"          기대: {c.expected}")
            print(f"          실제: {c.actual}")


def _finish(results, out_dir, stamp, option_log, package_dir):
    os.makedirs(out_dir, exist_ok=True)
    meta = {"command": "python run.py verify-install-package",
            "env": {"검증 대상 패키지": package_dir,
                    "Install Package 버전": sysinfo.file_version(
                        os.path.join(package_dir, "Install.exe")) or "확인 불가",
                    "실행 계정 권한": "관리자" if sysinfo.is_elevated() else "일반",
                    "점검 범위": "Welcome ~ Summary (실제 설치 없음)"}}
    try:
        paths = write_reports(results, out_dir, run_name=f"InstallPkg_{stamp}",
                              meta=meta)
    except Exception as exc:
        print(f"  리포트 저장 실패: {exc}")
        paths = {}
    if option_log:
        log_path = os.path.join(out_dir, f"InstallOptions_{stamp}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(option_log, f, ensure_ascii=False, indent=2)
        print(f"\n  선택 옵션 기록: {log_path}")
        selected = option_log["selected"]
        for key, value in selected.items():
            if value:
                print(f"      {key:<14} {value}")
    counts = _tally(results)
    print("\n  판정 합계: " + "  ".join(f"{k} {v}" for k, v in counts.items() if v))
    for kind, path in (paths.items() if isinstance(paths, dict) else []):
        print(f"  리포트({kind}): {path}")
    if not isinstance(paths, dict) and paths:
        print(f"  리포트: {paths}")
