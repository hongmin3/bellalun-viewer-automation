# -*- coding: utf-8 -*-
"""commit-msg hook 설치 (REQ-SPECSYNC-001).

`tools/spec_sync_check.py --staged`를 commit-msg hook으로 건다. 동작 파일을 바꾸고 SPEC을 바꾸지
않은 커밋은 `[spec-unchanged: <REQ-ID> <사유>]` 표기가 없으면 커밋 전에 막힌다.

사용법:
    python tools/install_git_hooks.py           # 설치(이 도구가 만든 hook만 덮어쓴다)
    python tools/install_git_hooks.py --check   # 설치 여부만 확인(없으면 종료 코드 1)

다른 사람이 만든 commit-msg hook이 있으면 덮어쓰지 않고 실패한다. clone마다 한 번 실행한다.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
MARKER = "# managed-by: tools/install_git_hooks.py (spec-sync)"
HOOK = f"""#!/bin/sh
{MARKER}
# 동작 파일 변경에 SPEC 갱신 또는 [spec-unchanged: <REQ-ID> <사유>] 표기가 있는지 확인한다.
cd "$(git rev-parse --show-toplevel)" || exit 1
for py in python python3 py; do
  if command -v "$py" >/dev/null 2>&1; then
    exec "$py" tools/spec_sync_check.py --staged --message-file "$1"
  fi
done
echo "[spec-sync] python을 찾지 못해 커밋을 막습니다." >&2
exit 1
"""


def hooks_dir(repo: Path) -> Path:
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "hooks"],
                         check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()
    path = Path(out)
    return path if path.is_absolute() else repo / path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="spec-sync commit-msg hook을 설치한다.")
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    target = hooks_dir(Path(args.repo).resolve()) / "commit-msg"
    current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else None

    if args.check:
        if current == HOOK:
            print(f"[hooks] 설치됨: {target}")
            return 0
        print(f"[hooks] 설치 필요: {target} ({'없음' if current is None else '다른 내용'})")
        return 1
    if current is not None and MARKER not in current:
        print(f"[hooks] 다른 commit-msg hook이 있어 덮어쓰지 않습니다: {target}", file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(HOOK, encoding="utf-8", newline="\n")
    try:
        target.chmod(0o755)
    except OSError:
        pass
    print(f"[hooks] commit-msg 설치: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
