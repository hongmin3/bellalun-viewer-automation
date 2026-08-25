# -*- coding: utf-8 -*-
"""마지막 **완료 전체 회귀**가 너무 오래됐는지 점검한다.

개별 TC나 전제 실패 조기 종료 리포트는 정상 전체 회귀로 세지 않는다. Windows
작업 스케줄러에서는 ``check_automation_status.cmd``를 매일 호출하면 된다.
"""

from __future__ import annotations

import _paths  # noqa: F401 — 저장소 루트를 sys.path 와 cwd 에 맞춘다

import argparse
import os
import sys

from core import automation_health as health


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-days", type=float, default=7,
                    help="이 일수보다 오래됐으면 경고(기본 7일)")
    ap.add_argument("--notify", action="store_true",
                    help="오래됐거나 없을 때 Windows 알림 표시")
    args = ap.parse_args(argv)
    root = _paths.REPO
    result = health.regression_age(
        os.path.join(root, "Reports"), max_age_days=args.max_age_days)
    if result["status"] == "ok":
        latest = result["latest"]
        print("[OK] %s" % result["message"])
        print("  %s" % latest["path"])
        return 0
    label = "전체 회귀 이력 없음" if result["status"] == "missing" else "전체 회귀 지연"
    print("[WARN] %s" % result["message"])
    if result.get("latest"):
        print("  %s" % result["latest"]["path"])
    if args.notify:
        health.notify_windows("Bellalun %s" % label, result["message"], "warning", 10)
    return 2


if __name__ == "__main__":
    sys.exit(main())
