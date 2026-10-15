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

실행: python tools/check_module_attrs.py
"""

import ast
import importlib
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]


PROJECT_ROOTS = ("core", "tests")


def _from_module_target(module, name, root):
    """from-import의 클래스·함수는 제외하고 실제 로컬 모듈만 고른다."""
    target = f"{module}.{name}"
    try:
        parent = importlib.import_module(module)
    except Exception:
        parent = None
    if parent is not None and hasattr(parent, name):
        value = getattr(parent, name)
        if not isinstance(value, ModuleType):
            return None
        target = value.__name__
        if target.split(".")[0] not in PROJECT_ROOTS:
            return None
    location = Path(root).joinpath(*target.split("."))
    if location.with_suffix(".py").is_file() or (location / "__init__.py").is_file():
        return target
    return None


def module_aliases(tree, root=ROOT):
    """별칭 -> 모듈 경로. **이 저장소 모듈만** 본다.

    표준 라이브러리는 제외한다. `import urllib.request` 는 이름 `urllib` 를
    바인딩하는데(서브모듈이 아니라 패키지), 그것까지 검사하면
    `urllib.parse` 가 "없는 이름"으로 오탐된다.
    """
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] not in PROJECT_ROOTS:
                continue
            for a in node.names:
                target = _from_module_target(node.module, a.name, root)
                if target is not None:
                    aliases[a.asname or a.name] = target
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in PROJECT_ROOTS:
                    continue
                # `import a.b` 는 `a` 를 바인딩한다. `import a.b as x` 는 `x` -> a.b.
                bound = a.asname or a.name.split(".")[0]
                aliases[bound] = a.name if a.asname else bound
    return aliases


def check_paths(paths, root=ROOT):
    """주어진 소스만 검사하고 메시지 목록을 반환한다. 소스는 실행하지 않는다."""
    problems = []
    for path in paths:
        path = str(path)
        source = Path(path)
        if not source.is_absolute():
            source = Path(root) / source
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=path)
        aliases = module_aliases(tree, root=root)

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
    return problems


def main():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    targets = sorted(str(path.relative_to(ROOT))
                     for folder in ("tests", "core")
                     for path in (ROOT / folder).glob("*.py"))
    problems = check_paths(targets)
    if problems:
        print("문제 발견:")
        for problem in problems:
            print(" ", problem)
        return 1
    print(f"이상 없음 ({len(targets)}개 모듈 검사)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
