# -*- coding: utf-8 -*-
"""1회성 스모크 점검: Viewer 실행 + 로그인만 확인하고 종료한다.

TC를 수행하지 않는다 - run.py의 cold_start()만 호출해 로그인 성공 여부만 본다.
"""
from run import Context
from core import flows

ctx = Context("config.json")


def on_event(msg):
    print(f"[login-check] {msg}")


ui, log = flows.cold_start(ctx.cfg, ctx.db, on_event=on_event, force_restart=False)
print(f"\n로그인 성공. Viewer PID={ui.pid}, at_login_screen={ui.at_login_screen()}")
