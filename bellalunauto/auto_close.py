"""Tk 예약 작업과 monotonic 시계로 완료 후 자동 닫기를 관리한다."""
from __future__ import annotations

from functools import wraps
import math
import time


class CompletionAutoClose:
    def __init__(self, scheduler, close, update, *, clock=time.monotonic):
        self.scheduler, self.close, self.update, self.clock = scheduler, close, update, clock
        self.deadline = None
        self.pending = None
        self.generation = 0

    @property
    def active(self):
        return self.deadline is not None

    def cancel(self):
        self.generation += 1
        self.deadline = None
        if self.pending is not None:
            self.scheduler.after_cancel(self.pending)
            self.pending = None
        self.update(None)

    def command(self, callback):
        """마우스·키보드·invoke 모두 동일한 Tk command 경로를 사용한다."""
        @wraps(callback)
        def invoke(*args, **kwargs):
            self.cancel()
            return callback(*args, **kwargs)
        return invoke

    def start(self, record):
        self.cancel()
        if (record.get('action') not in {'run-regression', 'run-winupdate'}
                or record.get('status') != 'completed'):
            return False
        self.deadline = self.clock() + 60
        generation = self.generation

        def tick():
            if generation != self.generation or not self.active:
                return
            self.pending = None
            remaining = self.deadline - self.clock()
            if remaining <= 0:
                self.cancel()
                self.close()
                return
            self.update(math.ceil(remaining))
            self.pending = self.scheduler.after(min(1000, max(1, math.ceil(remaining * 1000))), tick)

        tick()
        return True
