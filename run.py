# -*- coding: utf-8 -*-
"""Bellalun Viewer 기본기능 자동화 독립 실행 CLI."""
import argparse
import json
import os
import platform
import re
import string
import subprocess
import sys
import time
from datetime import datetime

from core.db import BellalunDb
from core.dicom_settings import setup_all
from core.result import write_reports


def _resolve_data_dir(configured):
    """Find BellalunData's actual drive letter.

    QA PCs have installed it on different drives (observed C: and D:), and
    config.json's data_dir is PC-specific/git-ignored, so a stale value from
    a previous machine must not silently break every DB/file check that
    depends on it. Keep the configured path's tail and probe every fixed
    drive letter for it instead of trusting the configured drive letter.
    """
    if os.path.isdir(configured):
        return configured
    tail = configured[2:] if len(configured) > 1 and configured[1] == ":" else configured
    for letter in string.ascii_uppercase:
        candidate = f"{letter}:{tail}"
        if os.path.isdir(candidate):
            return candidate
    raise RuntimeError(
        f"data_dir was not found on any drive: configured={configured!r} "
        f"(looked for {tail!r} on every drive letter)")


class Context:
    def __init__(self, config_path):
        self.config_path = os.path.abspath(config_path)
        with open(self.config_path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.cfg["data_dir"] = _resolve_data_dir(
            self.cfg.get("data_dir", r"D:\BellalunData"))
        self.db = BellalunDb(self.cfg.get("sql_server", r".\BELLALUN"))
        self.root = os.path.dirname(self.config_path)
        self.evidence_root = os.path.join(self.root, "Evidence")
        self.reports_root = os.path.join(self.root, "Reports")


def _report_meta(ctx, results):
    """HTML 리포트에 실을 부가 정보를 모은다.

    실패해도 리포트 생성 자체는 살린다 — 대신 **조용히 넘기지 않고** 이유를
    출력한다(체크리스트 기록이 죽은 코드였던 2026-08-18 사례와 같은 처리).
    """
    meta = {"command": "python " + " ".join(sys.argv[1:])
                       if len(sys.argv) > 1 else "python run.py"}
    try:
        from core import checklist, sysinfo, tc_modules
        source = checklist.source_path(ctx)
        meta["checklist"] = checklist.read_tc_rows(source) if source else {}
        meta["modules"] = tc_modules.as_map()
        try:
            with open(os.path.join(ctx.root, "automation_scope.json"),
                      encoding="utf-8") as f:
                scope_rows = json.load(f)
            meta["scope"] = {x["tc_id"]: {"level": x.get("level"),
                                          "reason": x.get("reason")}
                             for x in scope_rows}
            # 리포트 앞머리의 "자동화 커버리지 총괄" 섹션 데이터.
            # 기준 체크리스트 TC(= SUPPORT 가 아닌 항목)만 싣는다 — 자동화 보조
            # 항목(환경 복원 / DICOM 등록 / 3D 촬영 보조)은 개정본 TC 가 아니다.
            meta["coverage"] = [
                {"tc_id": x["tc_id"], "title": x.get("title"),
                 "level": x.get("level"),
                 "category": (x.get("coverage") or {}).get("category"),
                 "gap": (x.get("coverage") or {}).get("gap"),
                 "unblock": (x.get("coverage") or {}).get("unblock")}
                for x in scope_rows
                if x.get("level") != "SUPPORT" and x.get("coverage")]
        except Exception as exc:                       # noqa: BLE001
            print(f"  report-meta: automation_scope.json 읽기 실패 — {exc}")
        xipl_cfg = ctx.cfg.get("xipl") or {}
        viewer_exe = ctx.cfg["viewer"]["exe"]
        # PC/OS 실측 정보. 2026-08-21 사용자 요청으로 `TC_Basic_Install_02` 의
        # "OS 정보 (참고)" MANUAL 항목을 없애고 **여기**에 싣는다. 지원 OS Build
        # 기준이 문서상 확정되지 않아 확인 항목으로 두면 영구 MANUAL 이 되는데,
        # 정작 필요한 것은 "어떤 PC 에서 돌렸는가" 라는 기록이기 때문이다.
        try:
            pc = sysinfo.pc_info()
        except Exception as exc:                       # noqa: BLE001
            print(f"  report-meta: PC 정보 수집 실패 — {exc}")
            pc = {}
        env = {
            "수행 일시": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "호스트": pc.get("host") or platform.node(),
            "실행 계정": pc.get("user"),
            "PC 제조사·모델": " ".join(x for x in (pc.get("manufacturer"),
                                                pc.get("model")) if x),
            "CPU": (f"{pc.get('cpu')} ({pc.get('cpu_cores')}C/"
                    f"{pc.get('cpu_threads')}T)" if pc.get("cpu") else None),
            "메모리": f"{pc.get('ram_gb')} GB" if pc.get("ram_gb") else None,
            "GPU": pc.get("gpu"),
            "BIOS": pc.get("bios"),
            "OS": (f"{pc.get('os_caption')} {pc.get('os_version')} "
                   f"(Build {pc.get('os_build')}, {pc.get('os_arch')})"
                   if pc.get("os_caption") else
                   f"{platform.system()} {platform.release()} "
                   f"(build {platform.version()})"),
            "OS 설치일 / 최근 부팅": " / ".join(
                x for x in (pc.get("os_install"), pc.get("last_boot")) if x),
            "Python": platform.python_version(),
            "Primary display": _display_summary(ctx),
            "관리자 권한(High Integrity)": sysinfo.is_elevated(),
            "Viewer 실행 파일": viewer_exe,
            "Viewer 버전": _file_version(viewer_exe),
            "data_dir": ctx.cfg.get("data_dir"),
            "SQL Server": ctx.cfg.get("sql_server"),
            "XIPL Studio": xipl_cfg.get("studio_exe"),
            "XIPL Parameter": xipl_cfg.get("parameter_dir"),
            "Tesseract": _tesseract_version(xipl_cfg.get("tesseract_exe")),
            "기준 체크리스트": source or "(찾지 못함)",
            "설정 파일": ctx.config_path,
            # 제품 로그. 판정 근거로 로그를 인용한 단계(파라미터 적용 등)를
            # 리포트만 보고 되짚을 수 있게 경로를 함께 남긴다.
            "Viewer 로그": _viewer_log_path(ctx),
            "증거 폴더": ctx.evidence_root,
        }
        meta["env"] = {k: v for k, v in env.items() if v not in (None, "")}
    except Exception as exc:                           # noqa: BLE001
        print(f"  report-meta: 수집 실패 — {exc}")
    return meta


def _display_summary(ctx):
    try:
        from core.display import screen_size, system_dpi
        w, h = screen_size()
        return f"{w}x{h} @ {system_dpi()}DPI"
    except Exception:                                  # noqa: BLE001
        d = ctx.cfg.get("display") or {}
        return f"{d.get('width')}x{d.get('height')} @ {d.get('expected_dpi')}DPI (설정값)"


def _viewer_log_path(ctx):
    """오늘자 Viewer 로그 경로. 없으면 None.

    경로 규칙은 `tests/xipl_flows._viewer_log_mark` 와 같다
    (`<data_dir>\\Log\\Viewer\\YYYY_MM_DD.log`).
    """
    path = os.path.join(ctx.cfg["data_dir"], "Log", "Viewer",
                        datetime.now().strftime("%Y_%m_%d.log"))
    return path if os.path.exists(path) else None


def _file_version(path):
    """실행 파일의 파일 버전. 못 읽으면 None (추측하지 않는다)."""
    if not path or not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Item -LiteralPath '{path}').VersionInfo.FileVersion"],
            capture_output=True, timeout=30)
        return out.stdout.decode("utf-8", "replace").strip() or None
    except Exception:                                  # noqa: BLE001
        return None


def _tesseract_version(exe):
    if not exe or not os.path.exists(exe):
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, timeout=30)
        first = (out.stdout or out.stderr).decode("utf-8", "replace").splitlines()
        return f"{first[0].strip()} ({exe})" if first else exe
    except Exception:                                  # noqa: BLE001
        return exe


#: `finish()` 가 마지막으로 생성한 리포트 경로. 완료 배너가 HTML 경로를 싣는 데
#: 쓴다(`finish()` 는 종료 코드만 돌려주므로 경로를 여기 남긴다).
LAST_REPORT_PATHS = {}


def guarded(fn, ctx, tc_id, title):
    """TC 하나가 예외로 죽어도 **회귀 전체를 멈추지 않는다.**

    대부분의 TC 모듈은 스스로 `try/except` 로 감싸 `TCResult.abort()` 를 남긴다.
    그런데 감싸지 않은 진입점이 있었다 — 2026-08-24 정적 감사에서
    `tests/install.py` 의 `install_01`/`install_02` 가 `except` 없이 설정·시스템을
    읽는 것을 확인했다. 그 둘은 **회귀의 첫 단계**라 여기서 죽으면 나머지 25개
    TC 가 아예 수행되지 않는다.

    개별 파일을 하나씩 고치는 대신 **호출 지점에서 한 번에** 막는다. 새 TC 를
    붙이는 사람이 `except` 를 잊어도 회귀는 계속 돈다.

    반환: `TCResult` 리스트(진입 함수가 단일 객체를 주면 감싸 준다).
    """
    from core.result import TCResult
    try:
        out = fn(ctx)
    except Exception as exc:                           # noqa: BLE001
        import traceback
        r = TCResult(tc_id, title)
        r.abort(0, f"{tc_id} 진입", exc,
                note="이 TC 의 진입 함수가 예외를 던졌다(모듈 자체 예외처리가 "
                     "없거나 그보다 앞에서 발생). **회귀는 중단하지 않고 다음 TC "
                     "로 넘어간다.** 남은 Step 은 미수행(FAIL)으로 채워진다.\n"
                     + traceback.format_exc(limit=8))
        print(f"  [guard] {tc_id} 예외로 중단 — 다음 TC 로 계속합니다: "
              f"{type(exc).__name__}: {exc}")
        return [r]
    if out is None:
        return []
    return list(out) if isinstance(out, (list, tuple)) else [out]


def _checklist_step_count(text):
    """Step Description 원문에서 마지막 단계 번호."""
    numbers = [int(n) for n in re.findall(r"^\s*(\d+)\.", text or "", re.M)]
    return max(numbers) if numbers else 0


def pad_aborted_steps(ctx, results):
    """**중단된 TC 의 남은 Step 을 FAIL(미수행)로 채운다.**

    2026-08-24 사용자 요청: "step 처리 중에 다른 버그가 발견되서 문제가 있을 수
    있자나, 이후 step 은 fail 처리하고 다음 tc 를 수행해 주면 좋겠다."

    예전에는 TC 가 중간에 죽으면 남은 Step 이 리포트에 **아예 나오지 않았다.**
    그래서 "3단계까지 갔는가, 8단계까지 갔는가"를 리포트만 보고 알 수 없었다.

    **`aborted` 가 True 인 TC 만** 채운다. 단순히 "FAIL 이 있다"로 판단하면
    정상 수행한 TC 까지 오염된다 — `TC_XIPL_compatibility_03` 은 Step 3·5 를
    별도 판정으로 내지 않으므로(다른 단계 판정에 포함) 없는 FAIL 이 생긴다.

    단계 수는 **기준 체크리스트**에서 읽는다(`AGENTS.md` 0절). 자동화가 임의로
    정하지 않는다.
    """
    from core import checklist
    from core.result import FAIL
    source = checklist.source_path(ctx)
    rows = checklist.read_tc_rows(source) if source else {}
    if not rows:
        return 0
    added = 0
    for result in results:
        if not getattr(result, "aborted", False):
            continue
        row = rows.get(result.tc_id)
        total = _checklist_step_count((row or {}).get("steps"))
        if not total:
            continue
        done = {int(c.step) for c in result.checks if c.step}
        for step in range(1, total + 1):
            if step in done:
                continue
            result.add(step, f"Step {step} 미수행", FAIL, stop=False,
                       expected="기준 체크리스트 Step Description 의 해당 단계 수행",
                       actual="수행하지 않음(앞선 단계에서 TC 가 중단됨)",
                       note="**제품 결함 판정이 아니다.** 이 TC 가 앞선 단계에서 "
                            "중단되어 수행되지 못한 단계다. 원인은 같은 TC 의 "
                            "앞선 FAIL 을 본다.")
            added += 1
    if added:
        print(f"  aborted-steps: 중단된 TC 의 미수행 Step {added}건을 "
              f"FAIL 로 기록했습니다.")
    return added


def shutdown_viewer(reason="회귀 종료"):
    """제품을 **안전하게** 종료한다. 열린 검사는 Suspend 로 보존한다.

    2026-08-24 사용자 요청: "회귀가 끝나면 뷰어가 종료된 다음에 결과가 출력되도록".
    결과 출력보다 **먼저** 부른다 — 리포트를 읽는 동안 제품이 화면을 점유하지
    않게 한다.

    0장 검사에서 `Close`(501) 는 Discard 다. 데이터를 잃지 않는 Suspend(502) 를
    쓴다(`flows.cold_start` 와 같은 판단).
    """
    detail = {"reason": reason}
    try:
        from core import flows
        from core.ui import ViewerUi
        ui = ViewerUi()
        if not ui.pid:
            detail["state"] = "이미 종료됨"
            return detail
        detail["pid"] = ui.pid
        try:
            if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
                flows.close_examine(ui, option="suspend", wait=8)
                detail["examine"] = "Suspend 로 보존 후 종료"
        except Exception as exc:                       # noqa: BLE001
            detail["examine"] = f"검사 종료 시도 실패(계속 진행): {exc}"
        flows._kill_viewer(ui.pid)
        time.sleep(3)
        detail["state"] = "종료됨" if not ViewerUi().pid else "종료되지 않음"
    except Exception as exc:                           # noqa: BLE001
        detail["state"] = f"종료 시도 실패: {exc}"
    return detail


def announce_done(results, elapsed_minutes, paths):
    """전체 회귀 완료를 터미널에 **눈에 띄게** 알린다.

    2026-08-24 사용자 요청. 긴 실행을 켜 두고 다른 일을 하다가 돌아왔을 때
    "끝났는지"를 스크롤하지 않고 알 수 있어야 한다. 콘솔 벨(`\\a`)도 함께 낸다.
    """
    from core.result import BLOCKED, FAIL, MANUAL, PASS, SKIP
    tc = {}
    checks = {}
    for r in results:
        tc[r.verdict] = tc.get(r.verdict, 0) + 1
        for c in r.checks:
            checks[c.status] = checks.get(c.status, 0) + 1
    order = (PASS, FAIL, MANUAL, SKIP, BLOCKED)
    line = " / ".join(f"{k} {tc.get(k, 0)}" for k in order)
    sub = " / ".join(f"{k} {checks.get(k, 0)}" for k in order)
    bar = "=" * 74
    print()
    print(bar)
    print(f"  전체 회귀 완료  —  {datetime.now():%Y-%m-%d %H:%M:%S}"
          f"  ({elapsed_minutes:.1f}분)")
    print(bar)
    print(f"  TC {len(results)}건   : {line}")
    print(f"  검증 {sum(checks.values())}개 : {sub}")
    fails = [(r.tc_id, c.step, c.title) for r in results for c in r.checks
             if c.status == FAIL]
    if fails:
        print(f"  FAIL {len(fails)}건:")
        for tc_id, step, title in fails[:12]:
            print(f"    - {tc_id}  Step {step}  {title}")
        if len(fails) > 12:
            print(f"    ... 외 {len(fails) - 12}건 (리포트 참고)")
    else:
        print("  FAIL 없음")
    if paths.get("html"):
        print(f"  리포트: {paths['html']}")
    print(bar)
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:                                  # noqa: BLE001
        pass
    if os.environ.get("BELLALUN_EXTERNAL_GUARD") != "1":
        try:
            from core import automation_health
            automation_health.notify_windows(
                "Bellalun 전체 회귀 완료",
                f"TC {len(results)}건 · {line} · {elapsed_minutes:.1f}분",
                "warning" if tc.get(FAIL, 0) else "info")
        except Exception as exc:                       # noqa: BLE001
            # 알림은 보조 장치다. 리포트 생성과 회귀 판정을 절대 가리지 않는다.
            print(f"  windows-notification: 표시 실패 — {exc}")


def recover_viewer_after_termination(ctx, tc_id, produced, started):
    """TC 중 Viewer가 사라졌으면 원인을 기록하고 다음 TC용으로 재기동한다.

    WER 덤프가 있으면 실제 크래시로, 없으면 원인 불명 종료로 구분한다. 단순히
    PID가 없다는 이유만으로 제품 크래시라고 단정하지 않는다.
    """
    if not produced:
        return None
    # 이 TC들은 정상적으로 끝났다면 다음 TC가 재사용할 Viewer가 살아 있어야 한다.
    expected = (tc_id.startswith("TC_Basic_WorkFlow_")
                and tc_id != "TC_Basic_WorkFlow_16") or (
                    tc_id == "TC_XIPL_compatibility")
    if not expected:
        return None
    from core.ui import ViewerUi
    if ViewerUi().pid:
        return None
    from core import automation_health, flows
    from core.result import FAIL, PASS
    info = automation_health.process_exit_message("VIEWER", started)
    target = produced[0]
    target.cleanup(
        0, "회귀 중 Viewer 비정상 종료 감지", FAIL,
        expected="TC 수행 중 Viewer 프로세스 유지",
        actual=info,
        note=("WER 덤프로 실제 크래시를 확인했다."
              if info["kind"] == "crash" else
              "프로세스 소멸은 확인했지만 새 WER 덤프가 없어 크래시로 단정하지 "
              "않는다. 어느 경우든 이 TC 이후의 화면 판정은 신뢰할 수 없어 "
              "FAIL로 남기고 다음 TC를 위해 재기동한다."))
    try:
        ui, startup = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        ready = flows.ensure_patient_screen(ui)
        target.cleanup(
            0, "Viewer 종료 후 다음 TC용 자동 복구", PASS if ready else FAIL,
            expected="재기동·로그인 후 Patient 화면", actual=startup)
    except Exception as exc:                           # noqa: BLE001
        target.cleanup(
            0, "Viewer 종료 후 다음 TC용 자동 복구", FAIL,
            expected="재기동·로그인 후 Patient 화면",
            actual=f"{type(exc).__name__}: {exc}")
    automation_health.notify_windows(
        "Bellalun Viewer 종료 감지", f"{tc_id}: {info['message']}", "error", 12)
    return info


def finish(ctx, results):
    completed = datetime.now()
    pad_aborted_steps(ctx, results)
    for index, result in enumerate(results):
        next_started = (results[index + 1].started
                        if index + 1 < len(results) else completed)
        result.finalize(next_started)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = write_reports(results, ctx.reports_root, stamp,
                          meta=_report_meta(ctx, results))
    LAST_REPORT_PATHS.clear()
    LAST_REPORT_PATHS.update(paths)

    # 체크리스트 xlsx에 TC별 판정을 기록한다(원본은 건드리지 않고 사본 생성).
    # 이 호출이 없어서 `core/checklist.py`가 죽은 코드였고, README가 "체크리스트
    # xlsx 결과 기록"을 하고 있다고 적어둔 것과 달리 2026-08-10 이후 파일이
    # 생성되지 않았다(2026-08-18 확인). 실패해도 리포트 생성 자체는 살린다 —
    # 대신 **조용히 넘기지 않고** 이유를 출력한다.
    try:
        from core import checklist
        source = checklist.source_path(ctx)
        if not source:
            expected = os.path.join("..", checklist.KNOWLEDGE_DIR,
                                    checklist.CHECKLIST_NAME)
            print("  checklist: 원본 xlsx를 찾지 못해 기록을 건너뜁니다 "
                  f"(config.json > checklist_xlsx 또는 {expected}).")
        else:
            out = os.path.join(ctx.reports_root,
                               f"Checklist_Result_{stamp}.xlsx")
            info = checklist.write_results(source, results, out_path=out)
            paths["checklist"] = info["path"]
    except Exception as exc:
        print(f"  checklist: 기록 실패 — {exc}")

    for r in results:
        print(f"[{r.verdict}] {r.tc_id} - {r.title}")
        for c in r.checks:
            print(f"  [{c.status}] Step {c.step} {c.title}: {c.actual}")
    print("Reports:")
    for k, v in paths.items():
        print(f"  {k}: {v}")
    return 1 if any(r.verdict == "FAIL" for r in results) else 0


def _probe_preset3d(ctx):
    r"""`Setting > Procedure > Preset` 의 컨트롤을 **조회 전용**으로 실측한다.

    TC 가 아니다. 리포트를 쓰지 않고 화면에 목록만 출력한다.

    ## 왜 필요한가

    2D Preset 목록·추가·삭제 컨트롤만 실측돼 있다(`flows.PRESET_2D_LIST` = 2554 /
    `PRESET_2D_ADD` = 2548 / `PRESET_2D_DELETE` = 2549). **3D-N / 3D-W 목록의
    ID 는 아직 실측되지 않았다.** 그래서 `TC_XIPL_compatibility_07` 은 3D Preset
    행을 편집하지 않고 `Setting > Procedure > General` 의 모드별 Default 만
    조작한다(`automation_scope.json` 의 `coverage.gap` 참고).

    번호가 이어질 것이라고 **추측하지 않는다**(AGENTS.md 3·5절). 이 명령으로
    한 번 실측해 두면 다음 회차에 "새 3D Preset 을 추가하면 그 시점 Default
    파라미터를 물려받는가"(Service Manual) 까지 자동 판정할 수 있다.

    ## 안전

    누르는 것은 이미 검증된 레일 컨트롤(`open_procedure_setting`)뿐이고 목록·
    버튼은 **읽기만 한다.** Update 를 누르지 않으므로 설정이 바뀌지 않는다.
    다만 Hospital Code 화면처럼 "누르지 않아도 즉시 저장되는" 화면이 있었으므로
    (AGENTS.md 3절) 전후로 `PROCEDURE_COMMON` 과 `VIEW_POSITION_PRESET` 행 수를
    찍어 대조해 출력한다.
    """
    from core import flows, setting_values
    from core.ui import ViewerUi

    def snapshot():
        return {
            "PROCEDURE_COMMON": ctx.db.one(
                "PROCEDURE", "SELECT DefaultImgProcess,DefaultReconNarrow,"
                             "DefaultReconWide FROM PROCEDURE_COMMON"),
            "VIEW_POSITION_PRESET": {
                int(row["Type"]): int(row["n"]) for row in ctx.db.query(
                    "PROCEDURE", "SELECT Type,COUNT(*) AS n "
                                 "FROM VIEW_POSITION_PRESET GROUP BY Type")},
        }

    before = snapshot()
    cfg = ctx.cfg["viewer"]
    ui = ViewerUi()
    ui.ensure_ready(cfg["exe"], cfg["login"]["id"], cfg["login"]["password"])
    flows.ensure_patient_screen(ui)
    rail = flows.open_procedure_setting(ui, "preset")
    controls = ui.controls(max_depth=8)
    pane = setting_values.content_pane(ui, rail, controls=controls)
    print(f"콘텐츠 패널 rect = {pane}")
    print(f"{'ctrl_id':>8}  {'class':<28} {'rect(패널 상대)':<28} text")
    rows = []
    for c in controls:
        if not c.visible:
            continue
        left, top, right, bottom = c.rect
        if left < pane[0] or top < pane[1] or right > pane[2] or bottom > pane[3]:
            continue
        if right - left < 8 or bottom - top < 8:
            continue
        rows.append((top, left, c))
    for _, _, c in sorted(rows, key=lambda row: (row[0], row[1])):
        left, top, right, bottom = c.rect
        rel = (left - pane[0], top - pane[1], right - pane[0], bottom - pane[1])
        print(f"{c.ctrl_id:>8}  {c.cls:<28} {str(rel):<28} {c.text!r}")
    shot = os.path.join(ctx.evidence_root, "Probe", "preset3d_page.png")
    os.makedirs(os.path.dirname(shot), exist_ok=True)
    from core import screen
    screen.grab(pane, path=shot)
    print(f"화면 캡처: {shot}")
    after = snapshot()
    print(f"DB 전: {before}")
    print(f"DB 후: {after}")
    print("DB 변화 없음" if before == after else "*** DB 가 바뀌었다 — 확인 필요 ***")
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup-dicom", help="MWL/Storage/Print 등록, Echo, DB/TCP 검증")
    sub.add_parser("setup-storage", help="Storage 서버/옵션만 등록, Echo, DB/TCP 검증")
    sub.add_parser("setup-print", help="Print 서버만 등록, Echo, DB/TCP 검증")
    sub.add_parser("run-ui", help="Local 검사 생성 + F8 Demo 촬영 완전자동화")
    sub.add_parser("run-wf01", help="TC_Basic_WorkFlow_01 MWL + Local 9단계 완전자동화")
    sub.add_parser("run-wf02",
                   help="TC_Basic_WorkFlow_02 공통 2D/3D 촬영 및 Tool 적용 자동화")
    sub.add_parser("run-wf03",
                   help="TC_Basic_WorkFlow_03 Image Overlay 및 Print Overlay 설정")
    sub.add_parser("run-wf04", help="TC_Basic_WorkFlow_04 2D 수동 DICOM Send")
    sub.add_parser("run-wf05", help="TC_Basic_WorkFlow_05 3D 수동 DICOM Send")
    sub.add_parser("run-wf06",
                   help="TC_Basic_WorkFlow_06 All Images 및 Dose SR 전송")
    sub.add_parser("run-wf07",
                   help="TC_Basic_WorkFlow_07 Emergency 검사 Auto Send")
    sub.add_parser("run-wf08", help="TC_Basic_WorkFlow_08 2D/3D Film Print")
    sub.add_parser("run-wf09",
                   help="TC_Basic_WorkFlow_09 Normal 및 Anonymous Export")
    sub.add_parser("run-wf12",
                   help="TC_Basic_WorkFlow_12 Study Reject 및 Restore")
    sub.add_parser("run-wf13",
                   help="TC_Basic_WorkFlow_13 계정 추가·수정 및 로그인 (1~6단계 완전자동)")
    sub.add_parser("run-wf10",
                   help="TC_Basic_WorkFlow_10 MWL Hospital Code와 Procedure 매핑")
    sub.add_parser("run-wf11",
                   help="TC_Basic_WorkFlow_11 Image Reject 및 Restore")
    sub.add_parser("run-wf14",
                   help="TC_Basic_WorkFlow_14 Setting Export 및 Import")
    sub.add_parser("run-wf15",
                   help="TC_Basic_WorkFlow_15 Pre-send Preview 표시 및 전송")
    sub.add_parser("run-wf16",
                   help="TC_Basic_WorkFlow_16 Kiosk 및 System Launcher "
                        "(**사용자 지정 수동** — MANUAL 판정만 기록, UI 조작 없음)")
    sub.add_parser("run-xipl", help="XIPL 01~06 실제 UI 자동화 및 Pass/Fail 판정")
    sub.add_parser("run-xipl-01", help="Viewer/XIPL Histogram, W1/W2, PIM TC01만 실행")
    sub.add_parser("run-xipl-02", help="Viewer 2D Image Processing TC02만 실행")
    sub.add_parser("run-xipl-03", help="Viewer 3D Post Reconstruction TC03만 실행")
    sub.add_parser("run-xipl-04", help="Preset별 2D Default Parameter TC04만 실행")
    sub.add_parser("run-xipl-05", help="Q.C Default Image Process Parameter TC05만 실행")
    sub.add_parser("run-xipl-06", help="XIPL Parameter 저장 후 Viewer 적용 TC06만 실행")
    sub.add_parser("run-xipl-07",
                   help="촬영 모드별 3D Default Recon Parameter TC07만 실행")
    sub.add_parser("run-sys3d", help="System 연동 3D-Narrow/3D-Wide 촬영 TC03/04 실행")
    sub.add_parser("run-regression", help="DB 기준 스냅샷 복원→DICOM→WF01→WF02→WF03→XIPL 전체 회귀")
    sub.add_parser("run-auto", help="비파괴 정적 점검 + DICOM + UI Demo 흐름")
    sub.add_parser("portability-check", help="해상도/DPI/필수 경로 이식성 사전 점검")
    sub.add_parser("probe-preset3d",
                   help="Setting > Procedure > Preset 의 3D-N/3D-W 목록 컨트롤을 "
                        "조회 전용으로 실측(TC 아님. 판정하지 않고 목록만 출력)")
    sub.add_parser("snapshot-baseline", help="현재 4개 DB를 회귀 테스트 기준 스냅샷(.bak)으로 저장")
    sub.add_parser("reset-environment", help="기준 스냅샷(.bak)으로 4개 DB만 복원(단독 실행)")
    verify_pkg = sub.add_parser(
        "verify-install-package",
        help="신규 설치용 Install.exe 패키지를 **설치하지 않고** 점검한다 "
             "(Welcome~Summary. 회귀에 포함되지 않는 단독 실행)")
    verify_pkg.add_argument(
        "--package", default=None,
        help="Install.exe 가 있는 폴더. 생략하면 실행 중에 묻는다")
    verify_pkg.add_argument("--language", default=None,
                            help="Register Options 의 Default Language. 주면 묻지 않는다")
    verify_pkg.add_argument("--theme", default=None,
                            help="Register Options 의 Default Theme. 주면 묻지 않는다")
    verify_pkg.add_argument("--kiosk", default=None, choices=["Use", "Not Use"],
                            help="Register Options 의 KIOSK Option. 주면 묻지 않는다")
    verify_pkg.add_argument(
        "--probe-options", action="store_true",
        help="드롭다운 항목을 **전부 눌러 보며** 목록 전문을 사양과 대조한다"
             "(느리다. 기본은 한 번만 열어 개수·화면으로 확인)")
    sub.add_parser("list", help="자동화 범위와 제외 사유 표시")
    args = ap.parse_args()

    # 설치 패키지 점검은 **설치 이전** PC 에서 돈다. `Context` 는 BellalunData 를
    # 못 찾으면 예외를 던지는데(신규 설치 전에는 없는 것이 정상) 그러면 이 명령은
    # 시작조차 못 한다. 그래서 Context 생성 **이전에** 가로챈다.
    # 이 명령은 `run-regression` 사슬에 들어 있지 않다 — 회귀는 이미 설치된
    # Viewer 를 대상으로 돌고, 이 점검은 설치 이전 패키지를 본다.
    if args.cmd == "verify-install-package":
        from tests.install_package_flow import run_interactive
        preset = {"language": args.language, "theme": args.theme,
                  "kiosk": args.kiosk}
        sys.exit(run_interactive(args.config, args.package,
                                 preset={k: v for k, v in preset.items() if v},
                                 probe_all=args.probe_options))

    ctx = Context(args.config)
    # **FAIL 이 나면 그 TC 를 즉시 중단한다**(2026-08-24 사용자 지시). 어차피 그
    # TC 는 사람이 직접 봐야 하므로, 남은 Step 을 계속 수행해 전체 시간을 늘리지
    # 않는다. 남은 Step 은 `pad_aborted_steps` 가 미수행(FAIL)으로 채운다.
    # 예전 동작(끝까지 수행)이 필요하면 config 에서 끈다.
    from core.result import TCResult as _TCResult
    _TCResult.stop_on_fail = bool(
        (ctx.cfg.get("regression") or {}).get("stop_tc_on_fail", True))
    results = []
    if args.cmd == "list":
        scope_path = os.path.join(ctx.root, "automation_scope.json")
        with open(scope_path, encoding="utf-8") as f:
            scope = json.load(f)
        print(r"기준 문서: ..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx"
              "  (시트: 개정 TC)")
        print("SUPPORT = 개정본 TC가 아닌 자동화 보조 항목")
        print()
        counts, categories = {}, {}
        for item in scope:
            counts[item["level"]] = counts.get(item["level"], 0) + 1
            title = item.get("title") or ""
            print(f"[{item['level']:<7}] {item['tc_id']:<32} {title}")
            print(f"{'':>10}  {item['reason']}")
            # 커버리지 분류·못 한 지점·해제 조건도 함께 보여 준다. 리포트의
            # "자동화 커버리지 총괄" 섹션과 같은 데이터다(2026-08-21 추가).
            cov = item.get("coverage") or {}
            if cov.get("category"):
                categories[cov["category"]] = categories.get(cov["category"], 0) + 1
                print(f"{'':>10}  · 분류: {cov['category']}")
                if cov.get("gap"):
                    print(f"{'':>10}  · 못 한 지점: {cov['gap']}")
                if cov.get("unblock"):
                    print(f"{'':>10}  · 해제 조건: {cov['unblock']}")
        print()
        print("합계: " + " / ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        if categories:
            print("커버리지 분류(개정본 TC만):")
            for name, n in sorted(categories.items(), key=lambda x: -x[1]):
                print(f"  - {name}: {n}")
        return 0
    if args.cmd == "snapshot-baseline":
        from core.dbreset import backup_baseline
        saved = backup_baseline(ctx)
        for db, path in saved.items():
            print(f"[baseline] {db} -> {path}")
        return 0
    if args.cmd == "reset-environment":
        from core.dbreset import restore_baseline
        outcome = restore_baseline(ctx)
        print("[reset-environment] 4개 DB를 기준 스냅샷으로 복원했습니다.")
        # 환경을 고쳤으면 **무엇을 고쳤는지 말한다.** 조용히 고치면 다음 사람이
        # 같은 함정을 또 밟는다.
        service = outcome.get("db_service") or {}
        if service.get("changed"):
            print("  DB 서비스 자동 복구: " + "; ".join(service["changed"]))
        if outcome.get("recreated"):
            print("  데이터 파일이 없어 새로 만든 DB: "
                  + ", ".join(outcome["recreated"]))
        return 0
    ui_commands = {"setup-dicom", "setup-storage", "setup-print", "run-ui", "run-wf01", "run-wf02", "run-wf03", "run-wf04", "run-wf05", "run-wf06", "run-wf07",
                   "run-wf08", "run-wf09", "run-wf10", "run-wf11", "run-wf12", "run-wf13",
                   # `run-wf16` 은 2026-08-21 부터 UI 를 건드리지 않는다
                   # (사용자 지정 수동 — MANUAL 판정만 기록). 그래서 관리자 권한·
                   # 해상도 게이트 대상에서 뺀다.
                   "run-wf14", "run-wf15", "run-xipl",
                   "run-xipl-01", "run-xipl-02", "run-xipl-03", "run-xipl-04", "run-xipl-05",
                   "run-xipl-06", "run-xipl-07", "run-sys3d", "run-auto",
                   "run-regression", "portability-check", "probe-preset3d"}
    if args.cmd in ui_commands:
        from core.display import normalize
        from core.result import TCResult, PASS, FAIL
        display = normalize(ctx.cfg)
        env = TCResult("AUTOMATION_ENVIRONMENT", "UI 자동화 실행 환경")
        # 환경 점검은 첫 FAIL에서 멈추면 안 된다. 권한·해상도·DPI·필수 경로 중
        # **무엇을 고쳐야 하는지 전부** 보여 주는 진단 명령이다. 전역
        # stop_tc_on_fail=True를 그대로 받으면 관리자 권한 False 한 건에서
        # StepFailed가 밖으로 새 리포트조차 남지 않았다(2026-08-25 실측).
        env.stop_on_fail = False
        env.add(0, "Primary display 1920x1080",
                PASS if display["actual"] == (1920, 1080) else FAIL,
                expected="1920x1080", actual=display)
        env.add(0, "Windows UI DPI 100%",
                PASS if display["dpi_ok"] else FAIL,
                expected="96 DPI (100%)", actual=f"{display['dpi']} DPI")
        from core import sysinfo
        elevated = sysinfo.is_elevated()
        env.add(0, "관리자 권한",
                PASS if elevated else FAIL,
                expected="관리자 권한 Python", actual=elevated)
        xipl_cfg = ctx.cfg.get("xipl") or {}
        required_paths = {
            "Viewer": ctx.cfg["viewer"]["exe"],
            "XIPL Studio": xipl_cfg.get("studio_exe", r"C:\XIPL\STUDIO_X64\XIPL.STUDIO.exe"),
            "XIPL Parameter": xipl_cfg.get("parameter_dir", r"C:\XIPL\PARAMETER"),
            "Tesseract OCR": xipl_cfg.get(
                "tesseract_exe", r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        }
        for label, path in required_paths.items():
            exists = os.path.exists(path)
            env.add(0, f"필수 경로 [{label}]", PASS if exists else FAIL,
                    expected=path, actual="존재" if exists else "없음")

        # DB 서비스는 회귀·UI TC 전체의 **전제**다. 꺼져 있으면 Viewer 가
        # `Database service is stopped.` 를 남기고 시작 단계에서 죽는다
        # (2026-08-26 실측 — 이전 설치가 남긴 SQL 인스턴스가 Manual/Stopped 로
        # 있는 PC 에 신규 설치를 하면 인스톨러가 MSSQL 설치를 건너뛰면서 이
        # 상태가 그대로 남는다). 그래서 실행 명령에서는 **되살리고**,
        # `portability-check` 는 진단 전용이라 **고치지 않고 알리기만** 한다.
        from core import dbreset
        sql_service = ctx.cfg.get("sql_service_name", "MSSQL$BELLALUN")
        if args.cmd == "portability-check":
            state = dbreset._service_state(sql_service)
            mode = dbreset._service_start_mode(sql_service)
            env.add(0, f"DB 서비스 [{sql_service}]",
                    PASS if state == "RUNNING" else FAIL,
                    expected="RUNNING / AUTO_START",
                    actual=f"{state} / {mode}",
                    note="정지 상태면 Viewer 가 시작 단계에서 종료된다. "
                         "실행 명령(run-*)은 이 상태를 자동으로 복구한다")
        else:
            recovered = dbreset.ensure_database_service(ctx)
            env.add(0, f"DB 서비스 [{sql_service}]",
                    PASS if recovered["after"] == "RUNNING" else FAIL,
                    expected="RUNNING",
                    actual=(recovered["after"]
                            + (f"  (자동 복구: {'; '.join(recovered['changed'])})"
                               if recovered["changed"] else "")),
                    note="꺼져 있으면 시작하고, 수동 시작이면 자동 시작으로 돌린다. "
                         "**무엇을 바꿨는지 이 줄에 남긴다** — 조용히 고치지 않는다")
            if recovered["changed"]:
                print("[환경 복구] DB 서비스: " + "; ".join(recovered["changed"]))

        if args.cmd == "portability-check":
            return finish(ctx, [env])
        if env.verdict == "FAIL":
            return finish(ctx, [env])
    if args.cmd == "probe-preset3d":
        return _probe_preset3d(ctx)
    if args.cmd == "run-regression":
        regression_started = datetime.now()
        print(f"[run-regression] 시작 {regression_started:%Y-%m-%d %H:%M:%S} — "
              "완료되면 Viewer 를 종료하고 결과 요약을 출력합니다.")
        # 개정본 TC 행 순서대로 적는다(읽는 사람이 실행 순서를 그대로 본다).
        from tests.install import install_01, install_02
        from tests.workflow01 import run as run_workflow01
        from tests.workflow02 import run as run_workflow02
        from tests.workflow03 import run as run_overlay
        from tests.workflow04 import run as run_send
        from tests.workflow05 import run as run_3d
        from tests.workflow06 import run as run_all_images
        from tests.workflow07 import run as run_emergency
        from tests.workflow08 import run as run_film_print
        from tests.workflow09 import run as run_export
        from tests.workflow10 import run as run_hospital_code
        from tests.workflow11 import run as run_reject
        from tests.workflow12 import run as run_study_reject
        from tests.workflow13 import run as run_account
        from tests.workflow14 import run as run_setting_transfer
        from tests.workflow15 import run as run_presend
        from tests.workflow16 import run as run_kiosk
        from tests.xipl_flows import run_xipl
        from core.dbreset import has_baseline, restore_baseline, baseline_state
        from core.result import TCResult, PASS, FAIL
        from core import viewer_processing as vp
        reset = TCResult("AUTOMATION_ENVIRONMENT_RESET", "회귀 테스트 전 기준 상태 복원")
        # 전제 준비는 첫 실패에서 멈추지 않는다 — DB 복원·서비스 기동·시험 파라미터
        # 재생성 중 **무엇이 안 됐는지 전부** 보여 줘야 진단이 된다. 대신 아래
        # 전제 게이트가 회귀 자체를 중단시킨다.
        reset.stop_on_fail = False
        if has_baseline(ctx):
            try:
                outcome = restore_baseline(ctx)
                # restore는 DB 단독 접속을 위해 제품 서비스를 내린다. 다시
                # RUNNING이 되지 않으면 이후 모든 TC가 Viewer 시작 단계에서
                # 연쇄 실패하므로, 여기서 잡아 원인을 명확히 남긴다
                # (2026-08-18 실측: 이 누락으로 8개 TC가 연쇄 FAIL).
                services = outcome.get("services") or {}
                down = {k: v for k, v in services.items() if v != "RUNNING"}
                reset.assert_true(
                    0, "DATA/ACCOUNT/CONFIGURATION/PROCEDURE 기준 스냅샷 복원 "
                       "및 제품 서비스 재기동",
                    not down,
                    expected="restore 완료 + 제품 서비스 RUNNING",
                    actual={"restore": "완료", "services": services},
                    note="서비스가 내려간 채로 진행하면 첫 Viewer 시작에서 "
                         "메인 메뉴(2015)를 찾지 못해 회귀가 연쇄 실패한다.")
            except Exception as exc:
                reset.add(0, "DATA/ACCOUNT/CONFIGURATION/PROCEDURE 기준 스냅샷 복원",
                          FAIL, actual=str(exc))
        else:
            reset.manual(0, "DB 기준 스냅샷 복원",
                         "기준 스냅샷(.bak 4개)을 찾지 못해 복원을 건너뛰었습니다. "
                         "저장소 상위 폴더의 Baseline 폴더에 DATA/ACCOUNT/"
                         "CONFIGURATION/PROCEDURE.bak을 넣거나 "
                         "`python run.py snapshot-baseline`으로 생성하세요.",
                         expected="기준 스냅샷 존재", actual=baseline_state(ctx))

        # 회귀는 시험 파라미터도 기준 상태에서 시작해야 한다. 이전 실행이 남긴
        # TEST_* 파일(제품이 만든 .pi 잔재, 예전 이름 규칙 포함)을 전부 지우고
        # 제품 기본 파라미터에서 새로 복사한다. 개별 TC 실행은 이와 달리
        # 없는 것만 만들어 재사용한다(vp.ensure_parameter_copies).
        param_root = (ctx.cfg.get("xipl") or {}).get(
            "parameter_dir", r"C:\XIPL\PARAMETER")
        try:
            param_reset = vp.reset_parameter_copies(param_root)
            reset.add(0, "XIPL 시험 파라미터(TEST_*) 전체 삭제 후 재생성", PASS,
                      expected=list(vp.TEST_PARAMETER_FILES),
                      actual={"removed": param_reset["removed"],
                              "created": [os.path.basename(p)
                                          for p in param_reset["created"]]})
        except Exception as exc:
            reset.add(0, "XIPL 시험 파라미터(TEST_*) 전체 삭제 후 재생성", FAIL,
                      expected=list(vp.TEST_PARAMETER_FILES), actual=str(exc))

        # Storage SCP 수신 목록은 **더 이상 자동으로 지우지 않는다**
        # (2026-08-28 사용자 확정 — 2026-08-27 결정을 뒤집음). 이 서버는 여러 PC 가
        # 함께 쓰고 개별 스터디 삭제 API 가 없어 `DELETE /api/studies` 가 전체를
        # 지운다. TC 판정은 환자 필터(`core/send_verify.received`)로 이미 정확하므로
        # 초기화 없이도 틀리지 않는다.
        results.append(reset)
        # **개정본 체크리스트의 TC 행 순서대로 수행한다**(사용자 요청 2026-08-20).
        # 체크리스트가 의존성 순서로 설계돼 있어서 행 순서 = 실행 순서가 된다.
        #   WF_03~15 는 DATA_FLOW_MWL_01 픽스처를 쓰고 WF_01·WF_02 가 그것을 만든다.
        #   WF_08 은 WF_03 이 만든 Print Overlay 를, WF_15 는 WF_03 이 만든
        #   Image Overlay 를 읽는다.
        # 설정을 바꾸는 TC 는 스스로 되돌리므로 순서를 미룰 필요가 없다 —
        #   WF_07 은 Auto Send 를, WF_13 은 로그인 계정을 finally 에서 원복한다
        #   (둘 다 실측으로 확인). 되돌리지 못하면 그 사실을 판정으로 남긴다.
        # **각 TC 를 `guarded()` 로 감싼다.** 진입 함수가 예외를 던져도 회귀는
        # 멈추지 않고 다음 TC 로 넘어가며, 그 TC 의 남은 Step 은 `finish()` 가
        # 미수행(FAIL)으로 채운다(2026-08-24 사용자 요청).
        #
        # 감싸지 않은 진입점이 실제로 있었다 — `install_01`/`install_02` 는
        # `except` 가 없는데 **회귀의 첫 단계**라, 거기서 죽으면 나머지 25개 TC 가
        # 아예 수행되지 않았다(2026-08-24 정적 감사).
        chain = [
            (install_01, "TC_Basic_Install_01", "설치 버전 및 패키지 구성 확인"),
            (install_02, "TC_Basic_Install_02", "Viewer 실행 전 필수 환경 확인"),
            (setup_all, "DICOM_Server_Setup", "MWL/Storage/Print 서버 자동 등록 및 연결"),
            (run_workflow01, "TC_Basic_WorkFlow_01", "MWL 및 Local 검사 생성"),
            (run_workflow02, "TC_Basic_WorkFlow_02", "공통 2D/3D 검사 촬영 및 Tool 적용"),
            (run_overlay, "TC_Basic_WorkFlow_03", "Image Overlay 및 Print Overlay 설정"),
            (run_send, "TC_Basic_WorkFlow_04", "2D 수동 DICOM Send"),
            (run_3d, "TC_Basic_WorkFlow_05", "3D 수동 DICOM Send"),
            (run_all_images, "TC_Basic_WorkFlow_06", "All Images 및 Dose SR 전송"),
            (run_emergency, "TC_Basic_WorkFlow_07", "Emergency 검사 Auto Send"),
            (run_film_print, "TC_Basic_WorkFlow_08", "2D/3D Film Print"),
            (run_export, "TC_Basic_WorkFlow_09", "Normal 및 Anonymous Export"),
            (run_hospital_code, "TC_Basic_WorkFlow_10", "MWL Hospital Code와 Procedure 매핑"),
            (run_reject, "TC_Basic_WorkFlow_11", "Image Reject 및 Restore"),
            (run_study_reject, "TC_Basic_WorkFlow_12", "Study Reject 및 Restore"),
            (run_account, "TC_Basic_WorkFlow_13", "계정 추가·수정 및 로그인"),
            (run_setting_transfer, "TC_Basic_WorkFlow_14", "Setting Export 및 Import"),
            (run_presend, "TC_Basic_WorkFlow_15", "Pre-send Preview 표시 및 전송"),
            (run_kiosk, "TC_Basic_WorkFlow_16", "Kiosk 및 System Launcher"),
            (run_xipl, "TC_XIPL_compatibility", "XIPL 연동 01~07"),
        ]
        # **전제 게이트** (2026-08-25 사용자 지시)
        #   "전제 준비부터 뻑나면 그냥 바로 전체 회귀를 종료해주라. 서버들이
        #    정상적으로 등록이 안되면 테스트의 의미가 없어."
        #
        # 21차 회귀가 정확히 그 낭비를 보여 줬다 — `DICOM_Server_Setup` 이 실패한
        # 뒤에도 80분을 더 돌며 19개 TC 를 연쇄 FAIL 로 채웠다. 전제가 깨지면
        # 이후 판정은 제품에 대해 아무것도 말해 주지 않는다.
        PRECONDITIONS = {"AUTOMATION_ENVIRONMENT_RESET", "DICOM_Server_Setup"}
        aborted_precondition = None
        # TC 단위 진행률을 work/regression_state.json 에 남긴다. 외부(Hub/Worker)가
        # Claude 를 깨우지 않고도 "지금 몇 번째 TC" 를 값싸게 읽을 수 있게 하기
        # 위함이다(2026-09-03 요청). 기록 실패가 회귀 자체를 막으면 안 된다.
        from core import automation_health as health
        total_tc = len(chain)
        for index, (fn, tc_id, title) in enumerate(chain, start=1):
            tc_started = time.time()
            try:
                health.write_state(
                    ctx.root, "running", regression_pid=os.getpid(),
                    current_tc=tc_id, current_title=title,
                    index=index, total=total_tc,
                    tc_started=datetime.now().astimezone()
                    .isoformat(timespec="seconds"))
            except OSError:
                pass
            produced = guarded(fn, ctx, tc_id, title)
            results.extend(produced)
            recover_viewer_after_termination(
                ctx, tc_id, produced, tc_started)
            if tc_id in PRECONDITIONS:
                broken = [x for x in produced if x.verdict == "FAIL"]
                if broken:
                    aborted_precondition = broken[0]
                    break
        if aborted_precondition is None:
            # 환경 복원 결과도 전제다(사슬보다 앞에서 만들어진다).
            if any(x.tc_id == "AUTOMATION_ENVIRONMENT_RESET"
                   and x.verdict == "FAIL" for x in results):
                aborted_precondition = next(
                    x for x in results
                    if x.tc_id == "AUTOMATION_ENVIRONMENT_RESET")
        if aborted_precondition is not None:
            fails = [f"Step {c.step} {c.title}: {c.actual}"
                     for c in aborted_precondition.checks if c.status == "FAIL"]
            print()
            print("!" * 74)
            print(f"  전제 준비 실패 — 전체 회귀를 중단합니다: "
                  f"{aborted_precondition.tc_id}")
            for line in fails[:6]:
                print(f"    - {str(line)[:160]}")
            print("  서버/환경이 준비되지 않으면 이후 판정은 제품에 대해 아무것도 "
                  "말해 주지 않습니다.")
            print("  조치 후 다시 실행하십시오: python run.py run-regression")
            print("!" * 74)
            shutdown = shutdown_viewer("전제 준비 실패로 회귀 중단")
            print(f"  viewer-shutdown: {shutdown}")
            elapsed = (datetime.now() - regression_started).total_seconds() / 60
            code = finish(ctx, results)
            announce_done(results, elapsed, LAST_REPORT_PATHS)
            return code or 1
        # **`AUTOMATION_3D_ACQUISITION_3DN/_3DW` 는 회귀에서 제외한다**
        # (2026-08-21 사용자 지시). 개정본 TC 가 아니고, 판정도 "장비 없이는
        # 확인 불가(MANUAL)"로 끝나 상세 결과에 실을 내용이 없다. 3D 촬영
        # 픽스처는 WF_02 가 이미 만들며, 이 보조 항목은 필요할 때
        # `python run.py run-sys3d` 로 단독 실행한다.
        #
        # **결과를 출력하기 전에 제품을 종료한다**(2026-08-24 사용자 요청).
        # 리포트를 읽는 동안 Viewer 가 화면을 점유하지 않게 하고, 다음 실행이
        # 깨끗한 콜드 스타트에서 시작하게 한다. 열린 검사는 Suspend 로 보존한다.
        shutdown = shutdown_viewer("전체 회귀 종료")
        print(f"  viewer-shutdown: {shutdown}")
        elapsed = (datetime.now() - regression_started).total_seconds() / 60
        code = finish(ctx, results)
        announce_done(results, elapsed, LAST_REPORT_PATHS)
        return code
    if args.cmd in ("setup-dicom", "run-auto"):
        results.append(setup_all(ctx))
    elif args.cmd == "setup-storage":
        results.append(setup_all(ctx, {"Storage"}))
    elif args.cmd == "setup-print":
        results.append(setup_all(ctx, {"Print"}))
    if args.cmd in ("run-ui", "run-auto"):
        from tests.ui_flows import run_local_workflow
        results.extend(run_local_workflow(ctx))
    if args.cmd == "run-wf01":
        from tests.workflow01 import run as run_workflow01
        results.append(run_workflow01(ctx))
    if args.cmd == "run-wf02":
        from tests.workflow02 import run as run_workflow02
        results.append(run_workflow02(ctx))
    # 개정본 번호 기준. 2026-08-19에 재정렬했다 — 이전에는 Overlay가 wf04,
    # 2D Send가 wf05, Film Print가 wf03이었다(다른 체크리스트 번호였다).
    if args.cmd == "run-wf03":
        from tests.workflow03 import run as run_overlay
        results.extend(run_overlay(ctx))
    if args.cmd == "run-wf04":
        from tests.workflow04 import run as run_send
        results.extend(run_send(ctx))
    if args.cmd == "run-wf05":
        from tests.workflow05 import run as run_3d
        results.extend(run_3d(ctx))
    if args.cmd == "run-wf06":
        from tests.workflow06 import run as run_all_images
        results.extend(run_all_images(ctx))
    if args.cmd == "run-wf09":
        from tests.workflow09 import run as run_export
        results.extend(run_export(ctx))
    if args.cmd == "run-wf12":
        from tests.workflow12 import run as run_study_reject
        return finish(ctx, [run_study_reject(ctx)])

    if args.cmd == "run-wf13":
        from tests.workflow13 import run as run_account
        return finish(ctx, [run_account(ctx)])

    if args.cmd == "run-wf10":
        # 2026-08-21: 여기 있던 `from tests.workflow07 import run as run_emergency`
        # 를 지웠다. 쓰이지 않는 import 였는데, 같은 이름이 회귀 블록에도 있어
        # `main()` 전체에서 지역 이름이 되게 만들었다(자동 치환이 **첫 등장**을
        # 바꿔 놓은 흔적). 이것이 2026-08-20 에 회귀가 41분을 돌고 나서
        # `UnboundLocalError: cannot access local variable 'run_emergency'` 로
        # 죽은 원인이다. `tools/check_regression_names.py` 가 재발을 검사한다.
        from tests.workflow10 import run as run_hospital_code
        return finish(ctx, [run_hospital_code(ctx)])

    if args.cmd == "run-wf11":
        from tests.workflow11 import run as run_reject
        return finish(ctx, [run_reject(ctx)])

    if args.cmd == "run-wf14":
        from tests.workflow14 import run as run_setting_transfer
        return finish(ctx, [run_setting_transfer(ctx)])

    if args.cmd == "run-wf15":
        from tests.workflow15 import run as run_presend
        return finish(ctx, [run_presend(ctx)])

    if args.cmd == "run-wf16":
        from tests.workflow16 import run as run_kiosk
        return finish(ctx, [run_kiosk(ctx)])

    if args.cmd == "run-wf07":
        from tests.workflow07 import run as run_emergency
        return finish(ctx, [run_emergency(ctx)])

    if args.cmd == "run-wf08":
        from tests.workflow08 import run as run_film_print
        results.append(run_film_print(ctx))
    if args.cmd in ("run-xipl", "run-auto"):
        from tests.xipl_flows import run_xipl
        results.extend(run_xipl(ctx))
    elif args.cmd == "run-xipl-01":
        from tests.xipl_flows import _prepare, compatibility_01
        try:
            results.append(compatibility_01(ctx, _prepare(ctx)))
        except Exception as exc:
            from core.result import TCResult, FAIL
            r = TCResult("TC_XIPL_compatibility_01", "Viewer와 XIPL 표시값 비교")
            r.add(0, "Viewer 시험 데이터 및 Overlay 준비", FAIL, actual=str(exc))
            results.append(r)
    elif args.cmd == "run-xipl-02":
        from tests.xipl_flows import _prepare, compatibility_02
        try:
            results.append(compatibility_02(ctx, _prepare(ctx)))
        except Exception as exc:
            from core.result import TCResult, FAIL
            r = TCResult("TC_XIPL_compatibility_02", "Viewer 2D Image Processing")
            r.add(0, "Viewer 시험 데이터 준비", FAIL, actual=str(exc))
            results.append(r)
    elif args.cmd == "run-xipl-03":
        from tests.xipl_flows import _prepare, compatibility_03
        try:
            results.append(compatibility_03(ctx, _prepare(ctx)))
        except Exception as exc:
            from core.result import TCResult, FAIL
            r = TCResult("TC_XIPL_compatibility_03", "Viewer 3D Post Reconstruction")
            r.add(0, "Viewer 시험 데이터 준비", FAIL, actual=str(exc))
            results.append(r)
    elif args.cmd == "run-xipl-04":
        from tests.xipl_flows import compatibility_04
        results.append(compatibility_04(ctx))
    elif args.cmd == "run-xipl-05":
        from tests.xipl_flows import compatibility_05
        results.append(compatibility_05(ctx))
    elif args.cmd == "run-xipl-07":
        from tests.xipl_flows import compatibility_07
        results.append(compatibility_07(ctx))
    elif args.cmd == "run-xipl-06":
        from tests.xipl_flows import _prepare, compatibility_06
        try:
            results.append(compatibility_06(ctx, _prepare(ctx)))
        except Exception as exc:
            from core.result import TCResult, FAIL
            r = TCResult("TC_XIPL_compatibility_06", "XIPL Parameter 저장 후 Viewer 적용")
            r.add(0, "Viewer 시험 데이터 준비", FAIL, actual=str(exc))
            results.append(r)
    if args.cmd == "run-sys3d":
        from tests.system_compat import run as run_system_3d
        results.extend(run_system_3d(ctx))
    if args.cmd == "run-auto":
        from tests.install import install_01, install_02
        results[0:0] = [install_01(ctx), install_02(ctx)]
    return finish(ctx, results)


if __name__ == "__main__":
    # **포그라운드 잠금을 명령 실행 내내 풀어 둔다.**
    #
    # 이 PC 의 `ForegroundLockTimeout` 이 INT_MAX 라 Windows 가 모든 포그라운드
    # 전환을 거부했고, 그 때문에 재기동한 Viewer 가 올라오지 못해 로그인 직전
    # 게이트가 TC 를 반복 중단시켰다(2026-08-28 실측). `core/ui.py` 의
    # `foreground_unlocked` 주석 참고. 끝나면 원래 값으로 되돌린다.
    from core.ui import foreground_unlocked

    with foreground_unlocked():
        sys.exit(main())
