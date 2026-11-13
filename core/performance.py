"""실행 범위 안의 호출 비용을 모은다. 선택자·판정·예외는 바꾸지 않는다."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import time


_current = ContextVar('bellalun_performance', default=None)


class PerformanceRecorder:
    def __init__(self, clock):
        self.clock = clock
        self.operations = {}

    def record(self, name, elapsed, failed):
        row = self.operations.setdefault(name, {
            'kind': 'performance', 'name': name, 'calls': 0,
            'duration_seconds': 0.0, 'max_seconds': 0.0, 'errors': 0})
        row['calls'] += 1
        row['duration_seconds'] += max(0.0, elapsed)
        row['max_seconds'] = max(row['max_seconds'], max(0.0, elapsed))
        row['errors'] += int(failed)

    def snapshot(self):
        # 호출 인자·창 제목·컨트롤 텍스트·예외 원문은 수집하지 않는다.
        return [dict(row, duration_seconds=round(row['duration_seconds'], 6),
                     max_seconds=round(row['max_seconds'], 6))
                for _, row in sorted(self.operations.items())]


@contextmanager
def collect_performance(*, clock=time.perf_counter):
    recorder = PerformanceRecorder(clock)
    token = _current.set(recorder)
    try:
        yield recorder
    finally:
        _current.reset(token)


@contextmanager
def measure(name):
    recorder = _current.get()
    if recorder is None:
        yield
        return
    started = recorder.clock()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        recorder.record(name, recorder.clock() - started, failed)


def timed(name):
    def decorate(function):
        @wraps(function)
        def invoke(*args, **kwargs):
            with measure(name):
                return function(*args, **kwargs)
        return invoke
    return decorate
