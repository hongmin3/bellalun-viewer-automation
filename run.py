# -*- coding: utf-8 -*-
"""Bellalun Viewer 기본기능 자동화 독립 실행 CLI."""
import argparse
import json
import os
import string
import sys
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


def finish(ctx, results):
    completed = datetime.now()
    for index, result in enumerate(results):
        next_started = (results[index + 1].started
                        if index + 1 < len(results) else completed)
        result.finalize(next_started)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = write_reports(results, ctx.reports_root, stamp)
    for r in results:
        print(f"[{r.verdict}] {r.tc_id} - {r.title}")
        for c in r.checks:
            print(f"  [{c.status}] Step {c.step} {c.title}: {c.actual}")
    print("Reports:")
    for k, v in paths.items():
        print(f"  {k}: {v}")
    return 1 if any(r.verdict == "FAIL" for r in results) else 0


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
    sub.add_parser("run-wf02", help="TC_Basic_WorkFlow_02 2D/3D Demo 촬영 및 Tool 자동화")
    sub.add_parser("run-wf03", help="TC_Basic_WorkFlow_03 Print Overlay 실제 출력 및 웹 검증")
    sub.add_parser("run-xipl", help="XIPL 01~03 실제 UI 자동화 및 Pass/Fail 판정")
    sub.add_parser("run-xipl-01", help="Viewer/XIPL Histogram, W1/W2, PIM TC01만 실행")
    sub.add_parser("run-xipl-02", help="Viewer 2D Image Processing TC02만 실행")
    sub.add_parser("run-xipl-03", help="Viewer 3D Post Reconstruction TC03만 실행")
    sub.add_parser("run-xipl-04", help="Preset별 2D Default Parameter TC04만 실행")
    sub.add_parser("run-xipl-05", help="Q.C Default Image Process Parameter TC05만 실행")
    sub.add_parser("run-xipl-06", help="XIPL Parameter 저장 후 Viewer 적용 TC06만 실행")
    sub.add_parser("run-sys3d", help="System 연동 3D-Narrow/3D-Wide 촬영 TC03/04 실행")
    sub.add_parser("run-regression", help="DB 기준 스냅샷 복원→DICOM→WF01→WF02→WF03→XIPL 전체 회귀")
    sub.add_parser("run-auto", help="비파괴 정적 점검 + DICOM + UI Demo 흐름")
    sub.add_parser("portability-check", help="해상도/DPI/필수 경로 이식성 사전 점검")
    sub.add_parser("snapshot-baseline", help="현재 4개 DB를 회귀 테스트 기준 스냅샷(.bak)으로 저장")
    sub.add_parser("reset-environment", help="기준 스냅샷(.bak)으로 4개 DB만 복원(단독 실행)")
    sub.add_parser("list", help="자동화 범위와 제외 사유 표시")
    args = ap.parse_args()
    ctx = Context(args.config)
    results = []
    if args.cmd == "list":
        scope_path = os.path.join(ctx.root, "automation_scope.json")
        with open(scope_path, encoding="utf-8") as f:
            scope = json.load(f)
        for item in scope:
            print(f"[{item['level']}] {item['tc_id']} - {item['reason']}")
        return 0
    if args.cmd == "snapshot-baseline":
        from core.dbreset import backup_baseline
        saved = backup_baseline(ctx)
        for db, path in saved.items():
            print(f"[baseline] {db} -> {path}")
        return 0
    if args.cmd == "reset-environment":
        from core.dbreset import restore_baseline
        restore_baseline(ctx)
        print("[reset-environment] 4개 DB를 기준 스냅샷으로 복원했습니다.")
        return 0
    ui_commands = {"setup-dicom", "setup-storage", "setup-print", "run-ui", "run-wf01", "run-wf02", "run-wf03", "run-xipl",
                   "run-xipl-01", "run-xipl-02", "run-xipl-03", "run-xipl-04", "run-xipl-05",
                   "run-xipl-06", "run-sys3d", "run-auto",
                   "run-regression", "portability-check"}
    if args.cmd in ui_commands:
        from core.display import normalize
        from core.result import TCResult, PASS, FAIL
        display = normalize(ctx.cfg)
        env = TCResult("AUTOMATION_ENVIRONMENT", "UI 자동화 실행 환경")
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
        if args.cmd == "portability-check":
            return finish(ctx, [env])
        if env.verdict == "FAIL":
            return finish(ctx, [env])
    if args.cmd == "run-regression":
        from tests.install import install_01, install_02
        from tests.workflow01 import run as run_workflow01
        from tests.workflow02 import run as run_workflow02
        from tests.workflow03 import run as run_workflow03
        from tests.xipl_flows import run_xipl
        from tests.system_compat import run as run_system_3d
        from core.dbreset import has_baseline, restore_baseline, baseline_state
        from core.result import TCResult, PASS, FAIL
        from core import viewer_processing as vp
        reset = TCResult("AUTOMATION_ENVIRONMENT_RESET", "회귀 테스트 전 기준 상태 복원")
        if has_baseline(ctx):
            try:
                restore_baseline(ctx)
                reset.add(0, "DATA/ACCOUNT/CONFIGURATION/PROCEDURE 기준 스냅샷 복원",
                          PASS, actual="restore 완료")
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
        results.append(reset)
        results.extend([install_01(ctx), install_02(ctx)])
        results.append(setup_all(ctx))
        results.append(run_workflow01(ctx))
        results.append(run_workflow02(ctx))
        results.append(run_workflow03(ctx))
        results.extend(run_xipl(ctx))
        results.extend(run_system_3d(ctx))
        return finish(ctx, results)
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
    if args.cmd == "run-wf03":
        from tests.workflow03 import run as run_workflow03
        results.append(run_workflow03(ctx))
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
    sys.exit(main())
