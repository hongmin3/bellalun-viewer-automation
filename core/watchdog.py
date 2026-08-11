# -*- coding: utf-8 -*-
"""행(hang) 방지 계층.

UI 자동화가 멈추는 원인은 대부분 셋 중 하나다.
  1) 기대한 화면이 안 떠서 무한 대기
  2) 예상 못 한 모달 대화상자가 떠서 이후 조작이 전부 막힘
  3) 조작은 됐는데 DB 반영이 늦어 판정이 어긋남

이 모듈은 모든 대기에 상한을 두고, 모달 대화상자를 자동으로 걷어내며,
실패한 단계가 전체 실행을 중단시키지 않도록 격리한다.
"""

import time
import traceback


class StepTimeout(RuntimeError):
    pass


class StepFailed(RuntimeError):
    pass


def wait_until(predicate, timeout=30, poll=0.5, desc="조건"):
    """predicate()가 참을 반환할 때까지 대기. 초과하면 StepTimeout."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = predicate()
            if last:
                return last
        except Exception as exc:          # 조회 자체가 일시적으로 실패할 수 있다
            last = exc
        time.sleep(poll)
    raise StepTimeout(f"{desc} 대기 시간 초과 ({timeout}s). 마지막 값={last!r}")


def wait_value(getter, target, timeout=40, poll=1.0, desc="값"):
    """getter()가 target에 도달할 때까지 대기. 초과해도 예외 없이 최종값 반환."""
    end = time.time() + timeout
    val = getter()
    while time.time() < end and val != target:
        time.sleep(poll)
        val = getter()
    return val


def retry(fn, attempts=3, delay=1.0, desc="동작"):
    """일시적 실패를 재시도한다. 마지막 예외를 그대로 올린다."""
    err = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            err = exc
            if i < attempts - 1:
                time.sleep(delay)
    raise StepFailed(f"{desc} {attempts}회 실패: {err}") from err


class DialogGuard:
    """예기치 않은 모달 대화상자를 걷어내는 가드.

    Viewer는 조작 중 확인/경고 팝업을 띄운다. 이걸 방치하면 이후 모든 클릭이
    막혀 자동화가 멈춘 것처럼 보인다. 뜬 팝업의 문구를 증적으로 남기고 닫는다.
    닫은 팝업 목록은 판정에 그대로 반영해야 하므로 caught에 쌓아 둔다.
    """

    def __init__(self, ui, allow_titles=(), evidence_dir=None):
        self.ui = ui
        self.allow = set(allow_titles)
        self.evidence_dir = evidence_dir
        self.caught = []

    def sweep(self, max_rounds=5, tag=""):
        """지금 떠 있는 대화상자를 모두 닫고, 닫은 내용을 반환한다.

        커스텀 팝업은 문구를 컨트롤로 노출하지 않으므로 캡처를 함께 남긴다.
        """
        import os
        closed = []
        for i in range(max_rounds):
            d = self.ui.dialog()
            if not d or d.text in self.allow:
                break
            path = None
            if self.evidence_dir:
                path = os.path.join(
                    self.evidence_dir,
                    f"dialog{tag}_{len(self.caught) + 1}.png")
            msg = self.ui.dismiss_dialog(timeout=1, evidence_path=path)
            if msg is None:
                break
            info = {"title": d.text, "message": msg, "evidence": path}
            closed.append(info)
            self.caught.append(info)
            time.sleep(0.4)
        return closed


def guarded(step_name, result, step_no=0, guard=None, on_error="fail"):
    """단계 실행을 격리하는 컨텍스트 매니저 팩토리.

    with guarded("검사 종료", r, 8, guard):
        flows.close_examine(ui)

    블록 안에서 예외가 나면 TCResult에 FAIL로 기록하고 삼킨다.
    on_error='raise'면 다시 올린다(선행 단계 실패로 뒤가 무의미할 때).
    """
    return _Guarded(step_name, result, step_no, guard, on_error)


class _Guarded:
    def __init__(self, name, result, step_no, guard, on_error):
        self.name, self.result, self.step_no = name, result, step_no
        self.guard, self.on_error = guard, on_error
        self.ok = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        from core.result import FAIL
        if exc is None:
            self.ok = True
            if self.guard:
                for d in self.guard.sweep():
                    self.result.add(self.step_no, f"{self.name} 중 팝업 표시", FAIL,
                                    expected="팝업 없음",
                                    actual=f"{d['title']}: {d['message']}")
            return False

        detail = f"{type(exc).__name__}: {exc}"
        self.result.add(self.step_no, self.name, FAIL, actual=detail,
                        note="".join(traceback.format_exception_only(exc_type, exc)).strip())
        if self.guard:
            self.guard.sweep()
        return self.on_error != "raise"
