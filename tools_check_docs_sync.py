# -*- coding: utf-8 -*-
"""운영 상세 HTML이 기준 문서 변경 뒤 검토됐는지 확인한다.

``프로젝트 상세.html``은 사용자가 2026-08-24에 **직접 갱신**하도록 정한 문서다.
따라서 MD를 자동 변환해 덮어쓰지 않는다. 대신 README/현재 상태/영구 지침 중 하나가
HTML보다 새로우면 명시적으로 경고해, 수동 갱신 누락을 파이프라인에서 잡는다.
"""

from __future__ import annotations

import os
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(ROOT)
TARGET = os.path.join(PROJECT, "프로젝트 상세.html")
SOURCES = [
    os.path.join(ROOT, "README.md"),
    os.path.join(ROOT, "AGENTS.md"),
    os.path.join(ROOT, "NEXT_WORK.md"),
    os.path.join(ROOT, "NEXT_TASK.md"),
    os.path.join(PROJECT, "지식", "[자동화 운영 지침] Bellalun Viewer auto 저장소 구현 규칙.md"),
    os.path.join(PROJECT, "지식", "[자동화 구현 현황] Bellalun Viewer auto 구현 상태.md"),
]


def check(target=TARGET, sources=SOURCES):
    if not os.path.isfile(target):
        return {"ok": False, "reason": "운영 상세 HTML 없음", "target": target,
                "newer": []}
    target_mtime = os.path.getmtime(target)
    newer = [path for path in sources
             if os.path.isfile(path) and os.path.getmtime(path) > target_mtime]
    return {"ok": not newer, "reason": "최신" if not newer else "기준 문서가 더 최신",
            "target": target, "newer": newer}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    result = check()
    if result["ok"]:
        print("[OK] 프로젝트 상세.html이 기준 문서보다 최신입니다.")
        return 0
    print("[WARN] %s: %s" % (result["reason"], result["target"]))
    for path in result["newer"]:
        print("  더 최신: %s" % path)
    print("  자동 변환으로 덮어쓰지 말고 프로젝트 상세.html을 직접 검토·갱신하십시오.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
