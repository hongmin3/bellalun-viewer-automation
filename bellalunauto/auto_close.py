"""Tk 예약 작업과 monotonic 시계로 완료 후 자동 닫기를 관리한다 (REQ-FOLLOWUP-003).

무인 실행(명시 신호가 있을 때)만 자동으로 닫는다. 신호 이름과 표시 문구는 VXvue 자동화와 같게 쓴다.
"""
from __future__ import annotations

from functools import wraps
import math
import os
import time

UNATTENDED_OPTION = '--unattended'
UNATTENDED_ENV = 'QA_AUTOMATION_UNATTENDED'
AUTO_CLOSE_SECONDS = 60
HUMAN_LABEL = '자동 닫기 꺼짐(사람 실행)'


def unattended_signal(option=False, environ=None):
    """무인 신호의 출처(`option`·`environment`) 또는 사람 실행이면 None. 다른 정황으로 추측하지 않는다."""
    if option:
        return 'option'
    if (os.environ if environ is None else environ).get(UNATTENDED_ENV) == '1':
        return 'environment'
    return None


def mode_label(unattended, seconds=None):
    if not unattended:
        return HUMAN_LABEL
    return f'{AUTO_CLOSE_SECONDS if seconds is None else seconds}초 뒤 자동 닫힘(무인 실행)'


class CompletionAutoClose:
    def __init__(self, scheduler, close, update, *, clock=time.monotonic, unattended=False):
        self.scheduler, self.close, self.update, self.clock = scheduler, close, update, clock
        self.unattended = bool(unattended)
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

    def interaction(self, event=None):
        """사람의 클릭·스크롤·키 입력. 카운트다운 중이면 그 회차를 취소하고 True를 돌려준다."""
        if not self.active:
            return False
        self.cancel()
        return True

    def command(self, callback):
        """마우스·키보드·invoke 모두 동일한 Tk command 경로를 사용한다."""
        @wraps(callback)
        def invoke(*args, **kwargs):
            self.cancel()
            return callback(*args, **kwargs)
        return invoke

    def start(self, record):
        self.cancel()
        if (not self.unattended or record.get('action') not in {'run-regression', 'run-winupdate'}
                or record.get('status') != 'completed'):
            return False
        self.deadline = self.clock() + AUTO_CLOSE_SECONDS
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
