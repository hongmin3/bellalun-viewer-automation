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
        return subprocess.run([git, *args], cwd=str(root), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def source_identity(root, executable=None):
    """리포트 meta 에 넣을 소스 식별 정보.

    소스 실행(저장소 안)은 `git rev-parse HEAD` 와 `git status --porcelain` 으로,
    설치판 실행은 EXE 옆(또는 `root`)의 `build-info.json` 의 `source_commit`·
    `source_dirty` 로 정한다. 둘 다 없으면 None 으로 남긴다(추측하지 않는다).
    """
    root = Path(root)
    if (root / ".git").exists():
        commit = _git(root, "rev-parse", "HEAD")
        status = _git(root, "status", "--porcelain")
        if commit and status is not None:
            return {"source_commit": commit, "source_dirty": bool(status),
                    "source_identity_origin": "git"}
    # 설치판(Nuitka)은 sys.executable 이 BellalunAuto.exe 이고 build-info.json 이 그 옆에 있다.
    candidates = [root / "build-info.json",
                  Path(executable or sys.executable).parent / "build-info.json"]
    for path in candidates:
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        commit = info.get("source_commit")
        if isinstance(commit, str) and commit:
            return {"source_commit": commit, "source_dirty": info.get("source_dirty"),
                    "source_identity_origin": "build-info"}
    return {"source_commit": None, "source_dirty": None, "source_identity_origin": "unknown"}
