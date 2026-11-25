# -*- coding: utf-8 -*-
"""Bellalun·VXvue 공통 자동화 프레임 사본 검사 (frame/FRAME.md).

두 제품 저장소는 `frame/frame.lock.json`에 적힌 공유 파일을 같은 내용으로 가진다.
이 도구는 같은 파일이 두 저장소에 있으며, 어느 쪽에서 고쳐도 커밋 전에 차이를 드러낸다.

사용법(저장소 루트에서):
    python frame/sync_check.py                # 검사: 잠금 해시 일치 + 형제 사본 일치
    python frame/sync_check.py --update-lock  # 공유 파일을 고친 뒤 잠금 해시 갱신
    python frame/sync_check.py --propagate    # 이 저장소의 공유 파일과 잠금을 형제 저장소에 복사

종료 코드: 0 일치, 1 불일치, 2 사용법·잠금 파일 오류.
형제 저장소가 이 PC에 없으면 사본 비교는 건너뛰고 안내만 출력한다(다른 PC·배포 환경).
줄바꿈(CRLF/LF)은 해시 전에 LF로 맞춘다. Git autocrlf 차이를 내용 차이로 보지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
LOCK_NAME = "frame/frame.lock.json"


def file_hash(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def load_lock(repo: Path) -> dict:
    lock = json.loads((repo / LOCK_NAME).read_text(encoding="utf-8"))
    if not isinstance(lock.get("files"), dict) or not isinstance(lock.get("products"), dict):
        raise ValueError(f"{LOCK_NAME}에 files·products가 없습니다")
    return lock


def siblings(repo: Path, lock: dict) -> list[tuple[str, Path]]:
    """잠금 파일의 products(작업공간 projects 폴더 기준 상대 경로) 중 이 저장소가 아닌 것."""
    projects = repo.resolve().parent.parent
    out = []
    for name, rel in sorted(lock["products"].items()):
        root = (projects / rel).resolve()
        if root != repo.resolve():
            out.append((name, root))
    return out


def local_problems(repo: Path, lock: dict) -> list[str]:
    problems = []
    for rel, expected in sorted(lock["files"].items()):
        path = repo / rel
        if not path.is_file():
            problems.append(f"공유 파일 없음: {rel}")
        elif file_hash(path) != expected:
            problems.append(f"잠금과 다름: {rel}")
    return problems


def sibling_problems(repo: Path, lock: dict, other: Path) -> list[str]:
    try:
        other_lock = load_lock(other)
    except (OSError, ValueError) as exc:
        return [f"형제 잠금 파일을 읽지 못함: {exc}"]
    problems = []
    if other_lock["files"] != lock["files"] or other_lock["products"] != lock["products"]:
        problems.append("frame.lock.json 내용이 다름")
    for rel in sorted(set(lock["files"]) | set(other_lock["files"])):
        mine, theirs = repo / rel, other / rel
        if not mine.is_file() or not theirs.is_file():
            problems.append(f"한쪽에만 있음: {rel}")
        elif file_hash(mine) != file_hash(theirs):
            problems.append(f"내용 다름: {rel}")
    return problems


def selected_siblings(repo, lock, peer):
    if peer is None:
        return siblings(repo, lock)
    other = Path(peer).resolve()
    if other == repo.resolve() or not (other / LOCK_NAME).is_file():
        raise ValueError(f"다른 제품의 작업 트리와 잠금 파일을 지정하세요: {other}")
    return [("지정한 형제 작업 트리", other)]


def check(repo: Path = REPO, out=sys.stdout, peer=None) -> int:
    lock = load_lock(repo)
    failed = False
    problems = local_problems(repo, lock)
    if problems:
        failed = True
        print("[FAIL] 공유 프레임 파일이 잠금과 다릅니다.", file=out)
        for p in problems:
            print(f"  - {p}", file=out)
        print("  해결 방법: 의도한 변경이면 python frame/sync_check.py --update-lock 뒤 "
              "--propagate로 형제 저장소에도 반영하세요(frame/FRAME.md 3절).", file=out)
    for name, other in selected_siblings(repo, lock, peer):
        if not other.is_dir():
            print(f"[안내] 형제 저장소({name}) 없음: {other} — 사본 비교를 건너뜁니다.", file=out)
            continue
        problems = (sibling_problems(repo, lock, other) if (other / LOCK_NAME).is_file()
                    else [f"{LOCK_NAME} 없음(공유 프레임 미반영)"])
        if problems:
            failed = True
            print(f"[FAIL] 형제 저장소({name})의 공유 프레임과 다릅니다: {other}", file=out)
            for p in problems:
                print(f"  - {p}", file=out)
            print("  해결 방법: 변경한 쪽 저장소에서 python frame/sync_check.py --propagate를 실행하고, "
                  "양쪽 검증을 통과한 뒤 각 저장소에 커밋하세요.", file=out)
        else:
            print(f"[PASS] 형제 저장소({name})와 공유 프레임 {len(lock['files'])}개 파일 일치", file=out)
    if not failed:
        print(f"[PASS] 공유 프레임 잠금 일치 ({len(lock['files'])}개 파일)", file=out)
    return 1 if failed else 0


def update_lock(repo: Path = REPO, out=sys.stdout) -> int:
    lock = load_lock(repo)
    missing = [rel for rel in lock["files"] if not (repo / rel).is_file()]
    if missing:
        print("[FAIL] 공유 파일 없음: " + ", ".join(missing), file=out)
        return 1
    lock["files"] = {rel: file_hash(repo / rel) for rel in sorted(lock["files"])}
    (repo / LOCK_NAME).write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] 잠금 갱신: {len(lock['files'])}개 파일", file=out)
    return 0


def propagate(repo: Path = REPO, out=sys.stdout, peer=None) -> int:
    lock = load_lock(repo)
    problems = local_problems(repo, lock)
    if problems:
        print("[FAIL] 먼저 --update-lock으로 이 저장소의 잠금을 맞추세요: " + "; ".join(problems), file=out)
        return 1
    copied = 0
    for name, other in selected_siblings(repo, lock, peer):
        if not other.is_dir():
            print(f"[안내] 형제 저장소({name}) 없음: {other}", file=out)
            continue
        for rel in [*sorted(lock["files"]), LOCK_NAME]:
            target = other / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / rel, target)
        copied += 1
        print(f"[OK] {name}에 공유 프레임 {len(lock['files'])}개 파일과 잠금을 복사했습니다: {other}", file=out)
        print(f"     다음: {other}에서 그 저장소의 검증을 실행하고 커밋하세요.", file=out)
    return 0 if copied or not selected_siblings(repo, lock, peer) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bellalun·VXvue 공통 자동화 프레임 사본 검사")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--update-lock", action="store_true", help="공유 파일 해시로 잠금 파일 갱신")
    group.add_argument("--propagate", action="store_true", help="공유 파일과 잠금을 형제 저장소에 복사")
    ap.add_argument("--peer", type=Path, help="비교하거나 반영할 형제 제품의 작업 트리")
    args = ap.parse_args(argv)
    try:
        if args.update_lock:
            return update_lock()
        if args.propagate:
            return propagate(peer=args.peer)
        return check(peer=args.peer)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {exc}")
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
