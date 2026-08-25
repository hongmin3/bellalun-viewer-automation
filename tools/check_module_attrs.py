# -*- coding: utf-8 -*-
"""모듈 속성 오염과 없는 이름 참조를 훑는다.

왜 필요한가 (2026-08-19 회귀 16차)
  `send_flows.py` 를 TC별 모듈로 나눌 때 자동 치환이 **지역 변수까지** `sv.` 로
  한정해 `sv.received = sv.received(ctx)` 가 됐다. 모듈 함수가 리스트로 덮어써져
  뒤따르는 TC 가 `'list' object is not callable` 로 죽었다.
  `py_compile` 도, 정의되지 않은 전역 이름 검사도 이것을 잡지 못한다 —
  둘 다 "존재하는 이름에 대입하는 것"은 정상 문법이기 때문이다.

검사 두 가지
  1. `<모듈별칭>.<이름> = ...` 형태의 **모듈 속성 대입**이 있는지
  2. 참조하는 `<모듈별칭>.<이름>` 이 실제로 그 모듈에 **있는지**

실행: python tools_check_module_attrs.py
"""

import _paths  # noqa: F401 — 저장소 루트를 sys.path 와 cwd 에 맞춘다
import ast
import glob
import importlib
import io
import sys


TARGETS = sorted(glob.glob("tests/*.py") + glob.glob("core/*.py"))


PROJECT_ROOTS = ("core", "tests")


def module_aliases(tree):
    """별칭 -> 모듈 경로. **이 저장소 모듈만** 본다.

    표준 라이브러리는 제외한다. `import urllib.request` 는 이름 `urllib` 를
    바인딩하는데(서브모듈이 아니라 패키지), 그것까지 검사하면
    `urllib.parse` 가 "없는 이름"으로 오탐된다.
    """
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                target = f"{node.module}.{a.name}"
                if node.module.split(".")[0] in PROJECT_ROOTS                         or node.module.startswith("."):
                    aliases[a.asname or a.name] = target
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in PROJECT_ROOTS:
                    continue
                # `import a.b` 는 `a` 를 바인딩한다. `import a.b as x` 는 `x` -> a.b.
                aliases[a.asname or a.name.split(".")[0]] =                     a.name if a.asname else a.name.split(".")[0]
    return aliases


problems = []
for path in TARGETS:
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src, filename=path)
    aliases = module_aliases(tree)

    # 1) 모듈 속성 대입
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases):
            problems.append(
                f"{path}:{node.lineno} 모듈 속성에 대입: "
                f"{node.value.id}.{node.attr} = ... "
                f"(지역 변수여야 하는지 확인하십시오)")

    # 2) 없는 이름 참조
    for alias, target in aliases.items():
        if target.startswith("."):
            # `from . import x` — 파일 위치로 패키지를 정한다.
            pkg = path.replace("\\", "/").split("/")[0]
            target = f"{pkg}.{target.lstrip('.')}"
        try:
            mod = importlib.import_module(target)
        except Exception:
            continue
        if not hasattr(mod, "__file__"):
            continue
        have = set(dir(mod))
        used = {n.attr for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id == alias and isinstance(n.ctx, ast.Load)}
        for name in sorted(used - have):
            problems.append(f"{path}: {alias}.{name} 이 {target} 에 없습니다")

if problems:
    print("문제 발견:")
    for p in problems:
        print(" ", p)
    sys.exit(1)
print(f"이상 없음 ({len(TARGETS)}개 모듈 검사)")
