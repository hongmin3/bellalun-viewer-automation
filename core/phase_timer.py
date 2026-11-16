# -*- coding: utf-8 -*-
"""단계별 소요 시간 기록(SPEC REQ-SPEEDUP-003). 측정용이며 판정·순서를 바꾸지 않는다."""
from contextlib import contextmanager
import time


def _now():
    return time.monotonic()


def since(started):
    """`started`(`_now()` 값)부터 지금까지의 초, 소수 1자리."""
    return round(_now() - started, 1)


class PhaseTimer:
    """`with timer.phase(이름):` 구간마다 `{"phase", "seconds"}`를 `rows`에 남긴다. 실패한 구간도 남긴다."""

    def __init__(self, rows=None):
        self.rows = [] if rows is None else rows

    @contextmanager
    def phase(self, name):
        started = _now()
        try:
            yield
        finally:
            self.rows.append({"phase": name, "seconds": since(started)})
