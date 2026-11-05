# -*- coding: utf-8 -*-
"""리포트에 실을 실행 소스 식별 정보(커밋·수정 여부) (REQ-DIST-005).

릴리스 게이트(`tools/release_gate.py`)는 같은 커밋·수정 없는 소스에서 나온 실행 결과만
인정한다. 설치판(Nuitka)에는 `tools/`가 들어가지 않으므로 이 함수는 `core`에 둔다.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _git(root, *args):
    git = shutil.which("git")
    if not git:
        return None
    try:
        return subprocess.run([git, *args], stdin=subprocess.DEVNULL, cwd=str(root), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def source_identity(root, executable=None):
    """리포트 meta 에 넣을 소스 식별 정보.

    소스 실행(저장소 안)은 `git rev-parse HEAD` 와 `git status --porcelain` 으로,
    설치판 실행은 EXE 옆의 `build-info.json` 의 `source_commit`·`source_dirty` 로 정한다.
    EXE 옆 build-info 가 Git 보다 먼저다. `root` 의 build-info 는 Git 이 없을 때만 본다.
    모두 없으면 None 으로 남긴다(추측하지 않는다).
    """
    root = Path(root)
    # 설치판(Nuitka)은 sys.executable 이 BellalunAuto.exe 이고 build-info.json 이 그 옆에 있다.
    # 작업 폴더가 저장소 checkout 이어도 실제로 도는 EXE 의 값이 우선이다.
    beside_exe = Path(executable or sys.executable).parent / "build-info.json"
    git_identity = None
    if (root / ".git").exists():
        commit = _git(root, "rev-parse", "HEAD")
        status = _git(root, "status", "--porcelain")
        if commit and status is not None:
            git_identity = {"source_commit": commit, "source_dirty": bool(status),
                            "source_identity_origin": "git"}
    candidates = [beside_exe] + ([] if git_identity else [root / "build-info.json"])
    for path in candidates:
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        commit = info.get("source_commit")
        if isinstance(commit, str) and commit:
            return {"source_commit": commit, "source_dirty": info.get("source_dirty"),
                    "source_identity_origin": "build-info"}
    if git_identity:
        return git_identity
    return {"source_commit": None, "source_dirty": None, "source_identity_origin": "unknown"}


def combine_run_identity(start, end):
    """실행 시작 때와 리포트 작성 때의 식별 정보를 합친다.

    리포트 시점의 값만 쓰면 실행 도중 커밋이 바뀌어도 새 커밋의 깨끗한 결과로 보인다.
    시작 때 커밋이 다르거나 시작 때부터 수정이 있었으면 `source_dirty`를 참으로 둔다.
    """
    if not start:
        return dict(end)
    merged = dict(end, source_commit_at_start=start.get("source_commit"))
    if (start.get("source_commit") != end.get("source_commit")
            or start.get("source_dirty") is not False):
        merged["source_dirty"] = True
    return merged
