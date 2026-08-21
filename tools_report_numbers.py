# -*- coding: utf-8 -*-
r"""리포트 JSON 과 저장소에서 **문서에 적을 수치를 실측**한다.

AGENTS.md 9절: "주장하는 수치(코드 규모, 회귀 실적, 자동화 등급 건수)를 실측으로
다시 확인하고 기준 시점을 함께 적는다." 그 확인을 손으로 하다 보니 README 의
숫자가 회차마다 낡았다(2026-08-21 에 `REGRESSION_TC_LINE` 같은 치환 자리표시자가
그대로 남아 있는 것을 발견했다). 그래서 한 명령으로 뽑는다.

```
python tools_report_numbers.py                      # 가장 최신 리포트
python tools_report_numbers.py Reports\Result_....json
```

출력은 사람이 읽는 표와, README 자리표시자에 넣을 한 줄 문장이다.
"""

from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
STATUSES = ("PASS", "FAIL", "MANUAL", "SKIP")


def latest_report():
    hits = sorted(glob.glob(os.path.join(ROOT, "Reports", "Result_*.json")))
    return hits[-1] if hits else ""


def code_size():
    """core + tests 줄 수와 모듈 수. `__pycache__` 는 세지 않는다."""
    out = {}
    for name in ("core", "tests"):
        files = sorted(glob.glob(os.path.join(ROOT, name, "*.py")))
        lines = 0
        for path in files:
            with open(path, encoding="utf-8") as f:
                lines += sum(1 for _ in f)
        out[name] = {"files": len(files), "lines": lines}
    with open(os.path.join(ROOT, "run.py"), encoding="utf-8") as f:
        out["run.py"] = {"files": 1, "lines": sum(1 for _ in f)}
    out["total_lines"] = sum(v["lines"] for v in out.values()
                             if isinstance(v, dict))
    out["total_modules"] = sum(v["files"] for v in out.values()
                               if isinstance(v, dict))
    return out


def scope_counts():
    path = os.path.join(ROOT, "automation_scope.json")
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    levels = {}
    for row in rows:
        levels[row.get("level")] = levels.get(row.get("level"), 0) + 1
    categories = {}
    for row in rows:
        cov = row.get("coverage") or {}
        if cov.get("category"):
            categories[cov["category"]] = categories.get(cov["category"], 0) + 1
    return {"levels": levels, "categories": categories,
            "checklist_tc": sum(1 for r in rows if r.get("level") != "SUPPORT")}


def report_numbers(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    results = data["results"]
    tc = dict.fromkeys(STATUSES, 0)
    checks = dict.fromkeys(STATUSES, 0)
    for r in results:
        tc[r["verdict"]] = tc.get(r["verdict"], 0) + 1
        for k, v in r["counts"].items():
            checks[k] += v
    seconds = sum(r["duration_seconds"] for r in results)
    fails = [(r["tc_id"], c["step"], c["title"])
             for r in results for c in r["checks"] if c["status"] == "FAIL"]
    manual_tcs = sorted({r["tc_id"] for r in results
                         for c in r["checks"]
                         if c["status"] in ("MANUAL", "SKIP")})
    return {"path": path, "generated": data.get("generated"),
            "tc_total": len(results), "tc": tc, "checks": checks,
            "check_total": sum(checks.values()),
            "seconds": round(seconds, 1), "minutes": round(seconds / 60, 1),
            "fails": fails, "manual_tcs": manual_tcs}


def main():
    # 콘솔 기본 코드페이지(cp949)로는 `—` 같은 문자를 못 찍어 UnicodeEncodeError 로
    # 죽는다. `run.py::main` 과 같은 처리를 한다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1] if len(sys.argv) > 1 else latest_report()
    if not path or not os.path.isfile(path):
        print("리포트 JSON 을 찾지 못했습니다.")
        return 1
    n = report_numbers(path)
    size = code_size()
    scope = scope_counts()

    print("=" * 76)
    print(f" 리포트 : {n['path']}")
    print(f" 생성   : {n['generated']}")
    print("=" * 76)
    print(f" TC 수     : {n['tc_total']}")
    print(" TC 판정   : " + " / ".join(f"{k} {n['tc'][k]}" for k in STATUSES))
    print(f" 검증 항목 : {n['check_total']} (Step 단위)")
    print(" 검증 판정 : " + " / ".join(f"{k} {n['checks'][k]}" for k in STATUSES))
    print(f" 총 소요   : {n['seconds']}초 ({n['minutes']}분)")
    print()
    print(" 코드 규모 : "
          + " / ".join(f"{k} {v['lines']}줄({v['files']}개)"
                       for k, v in size.items() if isinstance(v, dict))
          + f" → 합계 {size['total_lines']}줄 / 모듈 {size['total_modules']}개")
    print(f" 자동화 범위(개정본 {scope['checklist_tc']} TC) : "
          + " / ".join(f"{k} {v}" for k, v in sorted(scope["levels"].items())))
    print(" 커버리지 분류 :")
    for k, v in scope["categories"].items():
        print(f"   - {k}: {v}")
    print()
    if n["fails"]:
        print(f" FAIL {len(n['fails'])}건")
        for tc_id, step, title in n["fails"]:
            print(f"   - {tc_id} / Step {step} / {title}")
    else:
        print(" FAIL 없음")
    print(f" MANUAL/SKIP 이 있는 TC {len(n['manual_tcs'])}건: "
          + ", ".join(n["manual_tcs"]))
    print()
    print("-" * 76)
    print(" README 자리표시자에 넣을 문장")
    print("-" * 76)
    stamp = str(n["generated"] or "")[:16].replace("T", " ")
    print(f"REGRESSION_TC_LINE  = {stamp} — TC {n['tc_total']}건 : "
          f"PASS {n['tc']['PASS']} / FAIL {n['tc']['FAIL']} / "
          f"MANUAL {n['tc']['MANUAL']} / SKIP {n['tc']['SKIP']} "
          f"({n['minutes']}분)")
    print(f"REGRESSION_CHECK_LINE = 검증 {n['check_total']}개 : "
          f"PASS {n['checks']['PASS']} / FAIL {n['checks']['FAIL']} / "
          f"MANUAL {n['checks']['MANUAL']} / SKIP {n['checks']['SKIP']}")
    if n["fails"]:
        print("REGRESSION_FAIL_LINE = "
              + "; ".join(f"{t} Step {s}" for t, s, _ in n["fails"]))
    else:
        print("REGRESSION_FAIL_LINE = 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
