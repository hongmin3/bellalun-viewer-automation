# -*- coding: utf-8 -*-
"""정식 배포 전 릴리스 게이트 — 실시간 WU 리포트와 기본기능 전체 회귀 리포트를 판정한다.

Bellalun 정책은 VXvue 의 "전 항목 PASS·flake 0" 정책과 **다르다.**

* MANUAL 은 사용자 결정으로 허용한다. WU 는 사용자 지정 수동 TC(WU_01·12·13)만,
  기본기능 회귀는 MANUAL TC 를 그대로 허용하고 목록만 보고한다.
* FAIL 은 `tests/winupdate.py::KNOWN_DEFECT_EXCLUDE` 에 등록된 (tc_id, check
  title) 기존 알려진 제품 결함만 허용한다. 그 결함 때문에 TC 가 중단되며 생긴
  연쇄 기록도 허용한다(아래 `classify_fail`). 그 밖의 FAIL·BLOCKED 는 거부한다.
* 두 리포트는 빌드할 소스 커밋과 같은 커밋에서, 수정 없는(clean) 소스로
  실행됐어야 한다. 리포트에 소스 식별 정보가 없으면 거부한다.

리포트 meta 에 필요한 식별 필드(`source_identity()` 가 만든다):
    meta["source_commit"]           40자 커밋 SHA
    meta["source_dirty"]            bool — 실행 소스에 커밋되지 않은 변경이 있었는가
    meta["source_identity_origin"]  "git" | "build-info" | "unknown"

사용 예:
    python tools/release_gate.py --wu Reports/Result_WindowsUpdate_X.json \
        --basic Reports/Result_X.json --commit-from-git [--language]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.automation_health import FULL_REGRESSION_MARKERS  # noqa: E402
from tests.winupdate import KNOWN_DEFECT_EXCLUDE  # noqa: E402

WU_IDS = tuple(f"TC_WindowsUpdate_{i:02}" for i in range(1, 14))
#: 사용자 지정 수동 TC. 이 셋만 MANUAL 이어야 하고 나머지 10건은 PASS 여야 한다.
WU_MANUAL = frozenset({"TC_WindowsUpdate_01", "TC_WindowsUpdate_12", "TC_WindowsUpdate_13"})
#: `run.py::pad_aborted_steps` 가 채우는 미수행 Step 의 제목·실제값.
PAD_TITLE = re.compile(r"^Step \d+ 미수행$")
PAD_ACTUAL = "수행하지 않음(앞선 단계에서 TC 가 중단됨)"
#: `TCResult.add(stop=True)` 가 던진 StepFailed 를 `abort()` 가 기록한 실제값 머리.
STEPFAILED_PREFIX = "StepFailed:"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
GATE_LABEL_PASSED = "게이트 통과"
GATE_LABEL_CANDIDATE = "게이트 미통과 후보"


# ---------------------------------------------------------------- 소스 식별
from core.source_identity import _git, source_identity  # noqa: E402,F401


def resolve_commit(ref, root=ROOT):
    """짧은 SHA·참조를 40자 커밋 SHA 로. 못 풀면 ValueError."""
    full = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if not full or not _SHA.match(full):
        raise ValueError(f"커밋을 확인하지 못했습니다: {ref}")
    return full


# ---------------------------------------------------------------- 판정
def _check(checks, reasons, name, ok, detail):
    checks.append({"name": name, "passed": bool(ok), "detail": detail})
    if not ok:
        reasons.append(f"{name}: {detail}")


def _identity(label, report, expected_commit, checks, reasons):
    meta = (report or {}).get("meta") or {}
    commit, dirty = meta.get("source_commit"), meta.get("source_dirty")
    name = f"{label} 소스 식별"
    if not commit:
        _check(checks, reasons, name, False,
               "리포트 meta 에 source_commit 이 없어 어느 커밋에서 실행했는지 알 수 없습니다")
        return
    if str(commit).lower() != str(expected_commit or "").lower():
        _check(checks, reasons, name, False,
               f"실행 커밋 {commit} 이 기대 커밋 {expected_commit} 과 다릅니다")
        return
    if dirty is not False:
        _check(checks, reasons, name, False,
               "실행 소스에 커밋되지 않은 변경이 있었거나(source_dirty) 기록이 없습니다"
               f" (값: {dirty!r})")
        return
    _check(checks, reasons, name, True,
           f"커밋 {commit} · 변경 없음 ({meta.get('source_identity_origin') or '출처 미기록'})")


def _evaluate_wu(report, checks, reasons):
    meta = report.get("meta") or {}
    mode = meta.get("execution_mode")
    _check(checks, reasons, "WU 실행 방식", mode == "live",
           "실시간 제품 시험" if mode == "live" else f"실시간 시험이 아닙니다 (execution_mode={mode!r})")
    chained = meta.get("chain_completed")
    _check(checks, reasons, "WU 체인 완료", chained is True,
           "완료" if chained is True else f"체인이 끝까지 완료되지 않았습니다 (chain_completed={chained!r})")
    results = report.get("results") or []
    ids = [row.get("tc_id") for row in results]
    ok_ids = sorted(ids) == sorted(WU_IDS) and len(set(ids)) == len(ids)
    _check(checks, reasons, "WU TC 구성", ok_ids,
           "WU_01~13 13건" if ok_ids else f"WU_01~13 정확히 13건이어야 합니다 (실제 {len(ids)}건)")
    verdicts = {row.get("tc_id"): row.get("verdict") for row in results}
    passed = sorted(t for t, v in verdicts.items() if v == "PASS")
    manual = sorted(t for t, v in verdicts.items() if v == "MANUAL")
    other = sorted(f"{t}={v}" for t, v in verdicts.items() if v not in ("PASS", "MANUAL"))
    ok = len(passed) == 10 and set(manual) == WU_MANUAL and not other
    detail = f"PASS {len(passed)} / MANUAL {len(manual)}"
    if not ok:
        detail += (" — 목표는 PASS 10 / MANUAL 3(WU_01·12·13)"
                   + (f"; MANUAL {', '.join(manual)}" if set(manual) != WU_MANUAL else "")
                   + (f"; 그 밖 {', '.join(other)}" if other else ""))
    _check(checks, reasons, "WU 목표 판정", ok, detail)


def classify_fail(tc_id, check, has_known_defect, known_defects):
    """기본기능 FAIL 한 건을 분류한다: known | cascade | real.

    * known — (tc_id, title) 이 알려진 결함 목록에 있다.
    * cascade — 같은 TC 에 실제로 FAIL 난 알려진 결함이 있을 때만 인정하는 연쇄 기록.
      (a) `abort()` 가 남긴 StepFailed 기록: StepFailed 는 FAIL check 가 stop 으로
          추가될 때만 던져지므로, 그 원인은 같은 TC 의 FAIL check 다.
      (b) `pad_aborted_steps()` 의 "Step N 미수행": 제품 결함 판정이 아니라 중단 뒤
          수행하지 못한 Step 이다. 이 Step 들은 **검증되지 않았다** — 게이트는 이를
          허용하되 checks 에 미검증 Step 으로 따로 보고한다.
      StepFailed 가 아닌 예외 중단(KeyError 등)은 자동화 결함일 수 있어 real 이다.
      같은 TC 에 real FAIL 이 하나라도 있으면 연쇄 기록도 real 로 본다(evaluate 쪽).
    * real — 그 밖의 모든 FAIL.
    """
    title, actual = check.get("title"), str(check.get("actual") or "")
    if (tc_id, title) in known_defects:
        return "known"
    if has_known_defect and (actual.startswith(STEPFAILED_PREFIX)
                             or (PAD_TITLE.match(str(title or "")) and actual == PAD_ACTUAL)):
        return "cascade"
    return "real"


def _evaluate_basic(report, checks, reasons, known_defects):
    results = report.get("results") or []
    ids = {row.get("tc_id") for row in results}
    missing = sorted(FULL_REGRESSION_MARKERS - ids)
    _check(checks, reasons, "기본기능 전체 회귀", not missing,
           f"전체 회귀 {len(results)} TC" if not missing else
           f"전체 회귀가 아닙니다(개별 실행 또는 조기 종료) — 표식 누락 {', '.join(missing)}")
    blocked, real, tolerated, unverified, manual = [], [], [], [], []
    for row in results:
        tc_id = row.get("tc_id")
        rows = row.get("checks") or []
        if row.get("verdict") == "BLOCKED" or any(c.get("status") == "BLOCKED" for c in rows):
            blocked.append(tc_id)
        if row.get("verdict") == "MANUAL":
            manual.append(tc_id)
        fails = [c for c in rows if c.get("status") == "FAIL"]
        has_known = any((tc_id, c.get("title")) in known_defects for c in fails)
        kinds = [(c, classify_fail(tc_id, c, has_known, known_defects)) for c in fails]
        tc_real = [c for c, kind in kinds if kind == "real"]
        if tc_real:
            # 원인 불명 FAIL 이 섞이면 연쇄 기록도 그 FAIL 탓일 수 있어 함께 거부한다.
            real.extend(f"{tc_id} Step {c.get('step')} {c.get('title')}" for c, _ in kinds)
            continue
        for c, kind in kinds:
            if kind == "known":
                tolerated.append(f"{tc_id} Step {c.get('step')} {c.get('title')}")
            elif PAD_TITLE.match(str(c.get("title") or "")):
                unverified.append(f"{tc_id} {c.get('title')}")
    _check(checks, reasons, "기본기능 BLOCKED 없음", not blocked,
           "없음" if not blocked else f"BLOCKED TC {', '.join(blocked)}")
    _check(checks, reasons, "기본기능 알려진 결함 외 FAIL 없음", not real,
           "없음" if not real else f"허용 목록 밖 FAIL {len(real)}건: {'; '.join(real)}")
    checks.append({"name": "허용된 알려진 결함", "passed": True,
                   "detail": "; ".join(tolerated) or "없음"})
    checks.append({"name": "알려진 결함 중단으로 미검증된 Step", "passed": True,
                   "detail": "; ".join(unverified) or "없음"})
    checks.append({"name": "기본기능 MANUAL TC(사용자 결정 허용)", "passed": True,
                   "detail": ", ".join(manual) or "없음"})


def check_report_language(report, label="리포트"):
    """사용자에게 보이는 문장 완결성의 간단한 점검. 문제 목록을 돌려준다.

    FAIL/MANUAL/BLOCKED 의 빈 실제값·"None" 실제값, 그리고 title·expected·actual·
    note 에 남은 `{name}` 형태의 미치환 자리표시자를 찾는다. dict 표기(`{'a': 1}`)는
    자리표시자로 보지 않는다.
    """
    problems = []
    for row in report.get("results") or []:
        for c in row.get("checks") or []:
            where = f"{label} {row.get('tc_id')} Step {c.get('step')} {c.get('title')}"
            actual = str(c.get("actual") if c.get("actual") is not None else "").strip()
            if c.get("status") in ("FAIL", "MANUAL", "BLOCKED") and actual in ("", "None"):
                problems.append(f"{where}: 실제값이 비어 있거나 \"None\" 입니다")
            for field in ("title", "expected", "actual", "note"):
                text = str(c.get(field) or "")
                if _PLACEHOLDER.search(text) or (field == "note" and text.strip() == "None"):
                    problems.append(f"{where}: {field} 에 미치환 문구가 있습니다")
    return problems


def evaluate(wu_report, basic_report, expected_commit, *, known_defects=KNOWN_DEFECT_EXCLUDE,
             language=False):
    """두 리포트(JSON dict)를 판정한다. 하나라도 None 이면 거부한다."""
    checks, reasons = [], []
    if not expected_commit:
        _check(checks, reasons, "기대 커밋", False, "비교할 기대 커밋이 지정되지 않았습니다")
    for label, report in (("WU 리포트", wu_report), ("기본기능 리포트", basic_report)):
        _check(checks, reasons, f"{label} 존재", report is not None,
               "있음" if report is not None else "리포트가 없습니다")
        if report is not None:
            _identity(label, report, expected_commit, checks, reasons)
    if wu_report is not None:
        _evaluate_wu(wu_report, checks, reasons)
    if basic_report is not None:
        _evaluate_basic(basic_report, checks, reasons, known_defects)
    if language:
        problems = []
        for label, report in (("WU", wu_report), ("기본기능", basic_report)):
            if report is not None:
                problems += check_report_language(report, label)
        _check(checks, reasons, "리포트 문장 점검", not problems,
               "문제 없음" if not problems else f"{len(problems)}건: {'; '.join(problems)}")
    return {"passed": not reasons, "reasons": reasons, "checks": checks}


def load_report(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def gate_for_build(wu_path, basic_path, commit, dirty):
    """배포 빌드용: 게이트 입력이 없거나 미통과면 후보로 표시할 build-info 항목을 만든다."""
    if not wu_path or not basic_path:
        return {"status": "candidate", "label": GATE_LABEL_CANDIDATE, "passed": False,
                "reasons": ["게이트 입력(--gate-wu, --gate-basic)이 지정되지 않았습니다"],
                "inputs": {}}
    result = evaluate(load_report(wu_path), load_report(basic_path), commit)
    reasons = list(result["reasons"])
    if dirty:
        reasons.append("빌드 소스에 커밋되지 않은 변경이 있습니다")
    passed = not reasons
    return {"status": "passed" if passed else "candidate",
            "label": GATE_LABEL_PASSED if passed else GATE_LABEL_CANDIDATE,
            "passed": passed, "reasons": reasons, "checks": result["checks"],
            "inputs": {"wu": Path(wu_path).name, "basic": Path(basic_path).name}}


def print_verdict(result, stream=None):
    stream = stream or sys.stdout
    for item in result["checks"]:
        mark = "통과" if item["passed"] else "실패"
        print(f"[{mark}] {item['name']}: {item['detail']}", file=stream)
    if result["passed"]:
        print("릴리스 게이트 통과", file=stream)
    else:
        print(f"릴리스 게이트 거부 — 사유 {len(result['reasons'])}건", file=stream)
        for reason in result["reasons"]:
            print(f"  - {reason}", file=stream)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="BellalunAuto 릴리스 게이트")
    parser.add_argument("--wu", required=True, type=Path, help="실시간 WU 리포트 JSON")
    parser.add_argument("--basic", required=True, type=Path, help="기본기능 전체 회귀 리포트 JSON")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--commit", help="기대 소스 커밋(짧은 SHA 허용)")
    group.add_argument("--commit-from-git", action="store_true", help="현재 저장소 HEAD 를 기대 커밋으로")
    parser.add_argument("--language", action="store_true", help="리포트 문장 완결성 점검도 수행")
    args = parser.parse_args(argv)
    try:
        commit = resolve_commit(args.commit or "HEAD")
        reports = []
        for path in (args.wu, args.basic):
            try:
                reports.append(load_report(path))
            except (OSError, ValueError) as error:
                print(f"리포트를 읽지 못했습니다: {path.name} — {error}", file=sys.stderr)
                reports.append(None)
    except ValueError as error:
        print(f"게이트 중단: {error}", file=sys.stderr)
        return 1
    print(f"기대 커밋: {commit}")
    result = evaluate(reports[0], reports[1], commit, language=args.language)
    print_verdict(result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
