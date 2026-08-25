# -*- coding: utf-8 -*-
"""`finally` 안의 판정 기록이 **흐름을 끊지 않는지** 확인한다.

왜 필요한가 (2026-08-25)
  `TCResult.add(..., FAIL)` 은 `stop_on_fail` 이 켜져 있으면 `StepFailed` 를
  던진다. 그것을 `finally` 안에서 부르면 **정리 블록 자체가 예외를 던져 TC 밖으로
  샌다.**

    - 단독 실행: 프로세스가 통째로 죽고 **리포트가 남지 않는다.**
    - 회귀: `guarded()` 가 받아 "TC 가 죽었다" 로 기록해, 실제로 일어난 일
      ("본 시험은 통과했고 정리만 실패했다")을 가린다.

  WF_14 에서 실측했다 — Step 1~7 을 다 통과한 실행이 정리 단계의
  `ensure_patient_screen` 예외 때문에 아무 결과도 남기지 못했다. 같은 형태가
  7개 TC 파일 **17곳**에 있었다.

  이 검사는 `py_compile` 도 단위 시험도 잡지 못한다. 정리 경로는 평소에 성공하기
  때문에 **정리가 실패하는 날에만** 드러난다.

규칙
  `finally` 블록 안에서는
    - `r.cleanup(...)`            권장 — 항상 `stop=False`
    - `r.add(..., stop=False)`    허용 — 뜻을 명시했으므로
    - `r.abort(...)` / `r.manual(...)`  허용 — 내부에서 `stop=False` 를 쓴다
    - `r.add(...)` (stop 없음)    **금지**

실행: python tools_check_cleanup_stop.py
"""

import ast
import glob
import io
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TARGETS = sorted(glob.glob("core/*.py") + glob.glob("tests/*.py") + ["run.py"])

#: `finally` 안에서 그냥 불러도 되는 기록 메서드. 내부에서 `stop=False` 를 쓴다.
SAFE_METHODS = {"cleanup", "abort", "manual", "attach", "record_timing"}

#: 중단 신호를 낼 수 있는 기록 메서드.
STOPPING_METHODS = {"add", "assert_true", "assert_equal"}


def _finally_calls(tree):
    """`finally` 블록 안의 모든 메서드 호출을 (이름, 줄번호, 키워드) 로."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try) or not node.finalbody:
            continue
        block = ast.Module(body=node.finalbody, type_ignores=[])
        for sub in ast.walk(block):
            if (isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)):
                out.append((sub.func.attr, sub.lineno,
                            {k.arg for k in sub.keywords}))
    return out


def main():
    problems = []
    checked = 0
    for path in TARGETS:
        try:
            tree = ast.parse(io.open(path, encoding="utf-8").read(),
                             filename=path)
        except SyntaxError as exc:
            problems.append(f"{path}: 파싱 실패 — {exc}")
            continue
        for name, line, kwargs in _finally_calls(tree):
            if name in SAFE_METHODS:
                checked += 1
                continue
            if name not in STOPPING_METHODS:
                continue
            checked += 1
            if "stop" in kwargs:
                continue
            problems.append(
                f"{path}:{line} finally 안에서 `.{name}(...)` 을 stop= 없이 "
                f"부릅니다 — FAIL 이면 정리 블록이 StepFailed 를 던집니다. "
                f"`r.cleanup(...)` 을 쓰십시오.")

    print(f"finally 블록 안의 기록 호출 {checked}개 검사")
    if not checked:
        print("\n*** 검사한 호출이 0개다 — 검사가 무력화됐는지 확인하십시오. ***")
        return 1
    if problems:
        print(f"\n이상 {len(problems)}건:")
        for line in problems:
            print(f"  {line}")
        print("\n정리가 실패하는 날 TC 결과가 통째로 사라집니다.")
        return 1
    print("이상 없음. finally 안의 판정 기록이 흐름을 끊지 않는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
