# -*- coding: utf-8 -*-
"""변경 파일로 UI 회귀 범위를 추천한다(SPEC REQ-SPEEDUP-002, REQ-REGRESSION-002). 제품을 조작하지 않는다.

추천 범위
  none      문서·단위시험·운영 도구만 바뀜. 제품 UI 회귀 없음
  selected  바뀐 파일이 한정된 기본 TC에서만 쓰임. `run-regression --select <TC>`
  wu        WU 체인·WU 매핑·USB·업데이트 근거만 바뀜. `run-winupdate`
  full      실행 진입점·공용 계층·지도 밖 동작 파일이거나 기본과 WU가 함께 바뀜. 기본과 WU 전체

판단 방법
  바뀐 파일을 import하는 파일을 거슬러 올라간다. TC 진입 파일(`core/tc_modules.py`의
  `TC_MODULES`에 있는 `tests/` 파일)에 닿으면 그 TC, WU 진입 파일에 닿으면 WU를 더하고
  계속 올라간다(다른 TC·WU가 그 진입 파일의 함수를 가져다 쓰기 때문이다). 진입 파일을
  사슬로 부르기만 하는 `run.py`는 그때 건너뛴다. 실행 진입점(`run.py`·`bellalunauto/`·
  `remote/`)이나 보존·복원·결과 계층에 닿으면 공용으로 본다.
  추천은 판단 자료다. UI 회귀 전 사용자 확인을 대신하지 않는다.

실행: python tools/impact_scope.py [--base origin/main] [--files a.py b.py] [--json]
"""
import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import selection  # noqa: E402
from core.tc_modules import TC_MODULES  # noqa: E402

#: WU 전용 진입 파일. 여기에 닿으면 WU 묶음이 영향을 받는다.
WU_ENTRIES = {"tests/winupdate.py", "core/wu_chain.py", "core/winupdate_report.py",
              "core/update_evidence.py"}
#: 기본과 WU가 함께 쓰는 실행 진입점·보존 계층. 여기에 닿으면 두 묶음 전체다.
SHARED_ROOTS = {"run.py", "core/execution_session.py", "core/run_preservation.py",
                "core/preservation_storage.py", "core/dbreset.py", "core/result.py"}
SHARED_PREFIXES = ("bellalunauto/", "remote/", "packaging/")
#: 제품 실행에 쓰이는 데이터·빌드 파일.
FULL_FILES = {"automation_scope.json", "traceability.json", "config.example.json",
              "requirements.txt", "verified_environments.json", "BellalunAuto.py",
              "tools/build_distribution.py"}
BEHAVIOR_PREFIXES = ("core/", "tests/", "bellalunauto/", "remote/")
#: TC·WU 진입 파일을 사슬로 부르기만 하는 실행기.
RUNNERS = {"run.py"}


def _entries():
    """TC 진입 파일 → 기본 사슬 단계 ID. 사슬 밖 TC(Install_07 등)는 빈 집합이다."""
    entries = {}
    for tc_id, paths in TC_MODULES.items():
        stage = tc_id
        if tc_id.startswith("TC_XIPL_compatibility_"):
            stage = selection.XIPL_STAGE
        for path in paths:
            if path.startswith("tests/"):
                entries.setdefault(path, set())
                if stage in selection.BASIC_CHAIN_IDS or stage in selection.OPTIONAL_STAGES:
                    entries[path].add(stage)
    return entries


def _module_path(name):
    parts = name.split(".")
    for candidate in (Path(*parts).with_suffix(".py"), Path(*parts) / "__init__.py"):
        if (ROOT / candidate).is_file():
            return candidate.as_posix()
    return None


def _imports(path):
    """한 파일이 import하는 저장소 안 파일들(함수 안의 지연 import 포함)."""
    try:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError, ValueError):
        return set()
    package = ".".join(Path(path).with_suffix("").parts[:-1])
    found = set()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                prefix = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join([p for p in prefix if p] + ([base] if base else []))
            names = [base] + [f"{base}.{alias.name}" if base else alias.name for alias in node.names]
        for name in names:
            target = _module_path(name) if name else None
            if target and target != path:
                found.add(target)
    return found


def import_graph():
    """저장소 Python 파일의 역 import 지도: 파일 → 그 파일을 import하는 파일들."""
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8").stdout.split()
    users = {}
    for path in files:
        if path.startswith(("work/", "tools/")) or Path(path).name.startswith("test_"):
            continue
        for target in _imports(path):
            users.setdefault(target, set()).add(path)
    return users


def _behavior(path):
    return (path in FULL_FILES or path in SHARED_ROOTS or path.startswith(SHARED_PREFIXES)
            or (path.startswith(BEHAVIOR_PREFIXES) and path.endswith(".py")
                and not Path(path).name.startswith("test_")))


def _trace(path, graph, entries):
    """한 파일의 영향: {"tcs": set, "wu": bool, "shared": 이유 또는 None}."""
    tcs, wu, shared = set(), False, None
    seen, pending = set(), [path]
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        if node in SHARED_ROOTS or node.startswith(SHARED_PREFIXES) or node in FULL_FILES:
            shared = shared or f"{node}(실행 진입점·공용 계층)"
            continue
        importers = graph.get(node, set())
        if node in entries or node in WU_ENTRIES:
            if node in entries:
                if not entries[node]:
                    shared = shared or f"{node}(기본 사슬 밖 TC)"
                tcs |= entries[node]
            else:
                wu = True
            # 사슬 실행기(run.py)가 부르는 것은 공용 사용이 아니다. 다른 사용처는 계속 따라간다.
            pending.extend(importers - RUNNERS)
            continue
        if not importers:
            shared = shared or f"{node}(TC 지도와 import 관계로 영향을 한정할 수 없음)"
        pending.extend(importers)
    return {"tcs": tcs, "wu": wu, "shared": shared}


def classify(paths, graph=None):
    graph = import_graph() if graph is None else graph
    entries = _entries()
    rows, tcs, wu, full = [], set(), False, []
    for path in sorted(set(paths)):
        if not _behavior(path):
            rows.append({"path": path, "impact": "none", "reason": "문서·단위시험·운영 도구"})
            continue
        traced = _trace(path, graph, entries)
        if traced["shared"]:
            full.append(path)
            rows.append({"path": path, "impact": "full", "reason": traced["shared"]})
            continue
        tcs |= traced["tcs"]
        wu = wu or traced["wu"]
        impact = ", ".join(sorted(traced["tcs"])) + (" + WU" if traced["wu"] else "")
        rows.append({"path": path, "impact": impact.strip(" +") or "none",
                     "reason": "import 관계로 닿는 TC 진입 파일"})
    order = {stage: index for index, stage in
             enumerate(selection.with_optional(selection.BASIC_CHAIN_IDS))}
    ordered = sorted(tcs, key=order.__getitem__)
    if full or (tcs and wu):
        scope, command = "full", "run-regression, run-winupdate (두 묶음 전체)"
    elif wu:
        scope, command = "wu", "run-winupdate"
    elif tcs:
        scope = "selected"
        try:
            selection.resolve(ordered)
            command = "run-regression --select " + ",".join(ordered)
        except ValueError:
            scope, command = "full", "run-regression (선택 결과가 기본 전체와 같음)"
    else:
        scope, command = "none", "제품 UI 회귀 없음(단위시험·정적 검사만)"
    return {"scope": scope, "tcs": ordered if scope == "selected" else [],
            "command": command, "files": rows}


def changed_files(base):
    def lines(*args):
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8")
        return [line.strip() for line in out.stdout.splitlines() if line.strip()]
    files = set(lines("diff", "--name-only", f"{base}...HEAD"))
    files |= set(lines("diff", "--name-only", "HEAD"))
    files |= set(lines("ls-files", "--others", "--exclude-standard"))
    return sorted(path for path in files if not path.startswith("work/"))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="변경 파일로 UI 회귀 범위 추천(REQ-SPEEDUP-002)")
    parser.add_argument("--base", default="origin/main", help="비교 기준(기본 origin/main)")
    parser.add_argument("--files", nargs="*", help="기준 대신 이 파일 목록으로 판단")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)
    paths = args.files if args.files is not None else changed_files(args.base)
    result = classify([os.path.normpath(p).replace(os.sep, "/") for p in paths])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print(f"추천 범위: {result['scope']}")
    print(f"명령: {result['command']}")
    for row in result["files"]:
        print(f"  - {row['path']}: {row['impact']} ({row['reason']})")
    print("추천은 판단 자료입니다. UI 회귀 전 사용자 확인(REQ-REGRESSION-002)을 대신하지 않습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
