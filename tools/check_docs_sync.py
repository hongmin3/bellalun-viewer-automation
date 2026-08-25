# -*- coding: utf-8 -*-
"""운영 상세 문서가 기준 문서 변경 뒤 갱신됐는지 확인한다.

``..\프로젝트_상세.md`` 가 **이 프로젝트의 기본 문서**이고 ``auto/README.md`` 는
그 포트폴리오 축약형이다(2026-08-26 사용자 확정). 그래서 저장소 문서 중 하나라도
상세 원본보다 새로우면 **상세를 갱신하지 않고 넘어간 것**이므로 경고한다.

2026-08-24 에는 "HTML 을 손으로 갱신한다"는 방침이라 렌더러를 두지 않았다.
2026-08-26 사용자 지시로 ``auto/render_docs.py`` 를 도입했고, 이제 원본이 ``.md``
하나뿐이라 자동 변환이 손으로 쓴 내용을 덮을 위험이 없다. **HTML 을 직접 고치지
않는다** — 고쳐도 다음 렌더에서 사라진다.

  1. ``..\프로젝트_상세.md`` 를 고친다        ← 원본
  2. ``python render_docs.py``                 ← HTML 재생성
  3. ``auto/README.md`` 를 축약형으로 맞춘다
"""

from __future__ import annotations

import _paths  # noqa: F401 — 저장소 루트를 sys.path 와 cwd 에 맞춘다

import os
import sys


ROOT = _paths.REPO
PROJECT = _paths.PROJECT
TARGET = os.path.join(PROJECT, "프로젝트_상세.md")   # 기본 문서(원본)
RENDERED = os.path.join(PROJECT, "프로젝트_상세.html")
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
        return {"ok": False, "reason": "운영 상세 원본(.md) 없음", "target": target,
                "newer": [], "stale_html": False}
    target_mtime = os.path.getmtime(target)
    newer = [path for path in sources
             if os.path.isfile(path) and os.path.getmtime(path) > target_mtime]
    # HTML 이 원본보다 오래됐으면 렌더를 빠뜨린 것이다.
    stale_html = (not os.path.isfile(RENDERED)
                  or os.path.getmtime(RENDERED) < target_mtime)
    return {"ok": (not newer) and not stale_html,
            "reason": "최신" if not (newer or stale_html)
                      else ("HTML 재생성 누락" if stale_html else "기준 문서가 더 최신"),
            "target": target, "newer": newer, "stale_html": stale_html}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    result = check()
    if result["ok"]:
        print("[OK] 프로젝트_상세.md 가 저장소 문서보다 최신이고 HTML 도 최신입니다.")
        return 0
    print("[WARN] %s: %s" % (result["reason"], result["target"]))
    for path in result["newer"]:
        print("  더 최신: %s" % path)
    if result["newer"]:
        print("  ..\프로젝트_상세.md 를 먼저 갱신하십시오 (상세가 기본, README 는 축약형).")
    if result.get("stale_html"):
        print("  그리고 `python render_docs.py` 로 ..\프로젝트_상세.html 을 재생성하십시오.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
