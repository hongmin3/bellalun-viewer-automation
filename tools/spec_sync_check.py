# -*- coding: utf-8 -*-
"""변경-사양 동반 검사 (REQ-SPECSYNC-001).

동작 파일(`run.py`, `core/`, `bellalunauto/`, `remote/`, `tests/`의 `.py`)을 바꾼 커밋은
같은 커밋에서 `SPEC.md`(또는 `specs/*.md`)도 바꿔야 한다. 기존 REQ가 이미 그 동작을 말하는
버그 수정처럼 사양이 그대로인 변경은 커밋 메시지에 아래 표기를 남길 때만 허용한다.

    [spec-unchanged: REQ-XXX-NNN <사유>]

REQ-ID는 `SPEC.md`(와 `specs/*.md`)에 정의된 것이어야 하고 사유는 비울 수 없다.

사용법:
    python tools/spec_sync_check.py                    # 기준(upstream) 이후 아직 push하지 않은 커밋 검사
    python tools/spec_sync_check.py --base <rev>       # <rev>..HEAD 커밋 검사
    python tools/spec_sync_check.py --staged --message-file <파일>   # commit-msg hook

이 도구는 `tools/_paths.py`를 import하지 않는다. 그 모듈은 import할 때 작업 폴더를 바꾼다.
"""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]

BEHAVIOR_DIRS = ("core", "bellalunauto", "remote", "tests")
BEHAVIOR_FILES = ("run.py",)
EXEMPTION_RE = re.compile(r"\[spec-unchanged:\s*((?:REQ|NFR)-[A-Z0-9]+-\d{3})\s+([^\]\n]*?)\s*\]")
DEFINED_RE = re.compile(r"^###\s+((?:REQ|NFR)-[A-Z0-9]+-\d{3})\b", re.M)
HINT = (
    "SPEC.md의 관련 REQ 본문과 12절을 같은 커밋에서 갱신하세요. 사양이 그대로인 변경(기존 REQ가 이미 "
    "말하는 버그 수정 등)이면 커밋 메시지에 [spec-unchanged: <REQ-ID> <사유>]를 적으세요."
)


def is_behavior_path(path: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    if p.suffix != ".py" or "__pycache__" in p.parts:
        return False
    if str(p) in BEHAVIOR_FILES:
        return True
    return len(p.parts) > 1 and p.parts[0] in BEHAVIOR_DIRS


def is_spec_path(path: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    return str(p) == "SPEC.md" or (len(p.parts) > 1 and p.parts[0] == "specs" and p.suffix == ".md")


def parse_exemptions(message: str) -> list[tuple[str, str]]:
    body = "\n".join(line for line in message.splitlines() if not line.lstrip().startswith("#"))
    return [(m.group(1), m.group(2).strip()) for m in EXEMPTION_RE.finditer(body) if m.group(2).strip()]


def defined_ids(repo: Path) -> set[str]:
    ids: set[str] = set()
    for doc in [repo / "SPEC.md", *sorted((repo / "specs").glob("*.md"))]:
        if doc.is_file():
            ids.update(DEFINED_RE.findall(doc.read_text(encoding="utf-8")))
    return ids


def evaluate(changed: list[str], message: str, ids: set[str]) -> str | None:
    """문제가 없으면 None, 있으면 사람이 읽을 설명을 돌려준다."""
    behavior = sorted(p for p in changed if is_behavior_path(p))
    if not behavior or any(is_spec_path(p) for p in changed):
        return None
    exemptions = parse_exemptions(message)
    unknown = [rid for rid, _ in exemptions if rid not in ids]
    if exemptions and not unknown:
        return None
    shown = ", ".join(behavior[:5]) + (f" 외 {len(behavior) - 5}개" if len(behavior) > 5 else "")
    if unknown:
        return f"동작 파일 변경({shown})의 예외 표기에 SPEC에 없는 ID가 있습니다: {', '.join(unknown)}"
    return f"동작 파일이 바뀌었는데 SPEC.md가 바뀌지 않았습니다: {shown}"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def _changed(repo: Path, commit: str) -> list[str]:
    out = _git(repo, "diff-tree", "--root", "--no-commit-id", "--no-renames", "-r", "--name-only", commit)
    return [line for line in out.splitlines() if line]


def check_range(repo: Path, base: str, head: str = "HEAD") -> list[tuple[str, str]]:
    commits = _git(repo, "rev-list", "--no-merges", "--reverse", f"{base}..{head}").split()
    ids = defined_ids(repo)
    problems = []
    for commit in commits:
        problem = evaluate(_changed(repo, commit), _git(repo, "log", "-1", "--format=%B", commit), ids)
        if problem:
            problems.append((commit, problem))
    return problems


def check_staged(repo: Path, message: str) -> str | None:
    git_dir = Path(_git(repo, "rev-parse", "--absolute-git-dir").strip())
    if (git_dir / "MERGE_HEAD").exists():
        return None
    out = _git(repo, "diff", "--cached", "--no-renames", "--name-only")
    return evaluate([line for line in out.splitlines() if line], message, defined_ids(repo))


def _default_base(repo: Path) -> tuple[str | None, str]:
    for ref in ("@{upstream}", "origin/main"):
        try:
            return _git(repo, "rev-parse", "--verify", "--quiet", ref).strip(), ref
        except subprocess.CalledProcessError:
            continue
    return None, ""


def _behind(repo: Path, ref: str) -> int:
    try:
        return int(_git(repo, "rev-list", "--count", f"HEAD..{ref}").strip() or 0)
    except (subprocess.CalledProcessError, ValueError):
        return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="동작 파일 변경에 SPEC 갱신이 함께 있는지 확인한다.")
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--base", help="검사 시작 기준 커밋(이 커밋은 제외). 기본: upstream 또는 origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--staged", action="store_true", help="commit-msg hook: 스테이징된 변경과 메시지를 검사")
    ap.add_argument("--message-file", help="--staged와 함께 쓰는 커밋 메시지 파일")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()

    if args.staged:
        if not args.message_file:
            ap.error("--staged에는 --message-file이 필요합니다")
        message = Path(args.message_file).read_text(encoding="utf-8", errors="replace")
        problem = check_staged(repo, message)
        if problem:
            print(f"[spec-sync] 커밋 차단: {problem}\n[spec-sync] {HINT}", file=sys.stderr)
            return 1
        return 0

    base, label = (args.base, args.base) if args.base else _default_base(repo)
    if not base:
        print("[spec-sync] 기준 커밋(upstream·origin/main)이 없어 HEAD 한 커밋만 검사합니다.")
        base, label = f"{args.head}~1", f"{args.head}~1"
    elif not args.base:
        behind = _behind(repo, base)
        if behind:
            print(f"[spec-sync] 주의: 이 checkout은 {label}보다 {behind}커밋 뒤처져 있습니다. "
                  "구현 전에 최신 SPEC을 받으세요(git pull --ff-only).")
    problems = check_range(repo, base, args.head)
    for commit, problem in problems:
        print(f"[spec-sync] FAIL {commit[:9]}: {problem}")
    if problems:
        print(f"[spec-sync] {HINT}")
        return 1
    count = len(_git(repo, "rev-list", "--no-merges", f"{base}..{args.head}").split())
    print(f"[spec-sync] OK: {label}..{args.head} 커밋 {count}개 검사, 위반 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
