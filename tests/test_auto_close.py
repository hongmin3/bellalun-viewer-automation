"""제품을 실행하지 않는 완료 타이머의 경계·취소 계약."""
import pytest


class Scheduler:
    def __init__(self):
        self.pending = {}
        self.next_id = 0
    def after(self, delay, callback):
        self.next_id += 1
        self.pending[self.next_id] = callback
        return self.next_id
    def after_cancel(self, token):
        self.pending.pop(token, None)
    def tick(self):
        _, callback = self.pending.popitem()
        callback()


def make_timer():
    from bellalunauto.auto_close import CompletionAutoClose
    scheduler, now, updates, closed = Scheduler(), [100.0], [], []
    timer = CompletionAutoClose(scheduler, lambda: closed.append(True), updates.append,
                                clock=lambda: now[0])
    return timer, scheduler, now, updates, closed


def test_completed_product_failure_closes_only_at_monotonic_sixty_seconds():
    timer, scheduler, now, updates, closed = make_timer()
    assert timer.start({'action': 'run-regression', 'status': 'completed', 'exit_code': 1})
    assert updates[-1] == 60 and timer.active
    now[0] = 159.999
    scheduler.tick()
    assert not closed and updates[-1] == 1
    now[0] = 160
    scheduler.tick()
    assert closed == [True] and not timer.active


@pytest.mark.parametrize('action,status', [
    ('run-regression', 'running'), ('run-regression', 'stopped'),
    ('run-winupdate', 'abnormal'), ('run-regression', 'uac_cancelled'),
    ('selfcheck', 'completed'), ('portability-check', 'completed')])
def test_incomplete_or_diagnostic_run_does_not_arm(action, status):
    timer, scheduler, _, _, closed = make_timer()
    assert not timer.start({'action': action, 'status': status})
    assert not timer.active and not scheduler.pending and not closed


def test_cancelled_and_previous_generation_callback_cannot_close_new_run():
    timer, scheduler, now, _, closed = make_timer()
    completed = {'action': 'run-winupdate', 'status': 'completed'}
    timer.start(completed)
    old = next(iter(scheduler.pending.values()))
    timer.cancel()
    now[0] = 300
    old()
    assert not closed
    timer.start(completed)
    now[0] = 360
    old()
    assert not closed and timer.active
    scheduler.tick()
    assert closed == [True]


def test_button_command_cancels_before_callback_even_for_direct_invoke():
    timer, scheduler, now, _, closed = make_timer()
    timer.start({'action': 'run-regression', 'status': 'completed'})
    observed = []
    command = timer.command(lambda: observed.append(timer.active))
    command()
    now[0] = 500
    assert observed == [False] and not scheduler.pending and not closed
