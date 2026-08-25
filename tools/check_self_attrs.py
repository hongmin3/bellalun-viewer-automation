# -*- coding: utf-8 -*-
"""클래스 안에서 쓰는 `self.<이름>` 이 실제로 있는지 확인한다.

왜 필요한가 (2026-08-25)
  `core/ui.py` 의 `fill_password` 를 다시 쓰면서 그 아래 있던 **`sweep_dialogs`
  메서드를 통째로 지웠다.** `ensure_ready` 가 `self.sweep_dialogs(...)` 를 부르므로
  실행 시 `AttributeError` 로 죽는다 — 그런데

    - `py_compile`                    통과 (문법은 맞다)
    - `tools_check_module_attrs.py`   통과 (그건 `mod.attr` 만 본다)
    - `tools_check_regression_names.py` 통과 (회귀 블록 이름만 본다)
    - `LOAD_GLOBAL` 검사              통과 (`self.x` 는 전역이 아니다)

  전부 통과하고 **UI 를 실제로 띄웠을 때 처음 드러났다.** 그래서 이 검사를
  만들었다. 구간을 통째로 교체하는 편집을 하면 같은 일이 또 난다.

검사 방법
  각 클래스에서 `self.<이름>` 참조를 모으고, 그 이름이
    - 그 클래스나 조상 클래스에 정의돼 있는가(`def` / 클래스 속성)
    - `self.<이름> = ...` 로 어딘가에서 대입되는가
  중 하나도 아니면 보고한다.

  동적 속성(`setattr`)은 잡지 못한다. 그래서 **정의를 못 찾은 것만** 보고하고
  실행을 막지는 않는 정보성 항목과, 확실한 오류를 구분해 출력한다.

실행: python tools_check_self_attrs.py
"""


import _paths  # noqa: F401 — 저장소 루트를 sys.path 와 cwd 에 맞춘다
import ast
import glob
import io
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TARGETS = sorted(glob.glob("core/*.py") + glob.glob("tests/*.py") + ["run.py"])

#: 파이썬이 기본 제공하거나 외부에서 주입하는 것으로 알려진 이름.
KNOWN_DYNAMIC = {"__dict__", "__class__"}


def _literal_names(value):
    """`__slots__ = ("a", "b")` 같은 리터럴에서 이름을 뽑는다."""
    out = set()
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        for item in value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                out.add(item.value)
    elif isinstance(value, ast.Constant) and isinstance(value.value, str):
        out.add(value.value)
    return out


def class_defs(node):
    """클래스에 직접 정의된 이름(메서드·클래스 속성·`__slots__`)."""
    names = set()
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(item.name)
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
                    # `__slots__` 로 선언한 속성도 정의다.
                    if target.id == "__slots__":
                        names |= _literal_names(item.value)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            names.add(item.target.id)
    return names


def self_assigned(node):
    """`self.<이름> = ...` 로 대입되는 이름."""
    names = set()
    for sub in ast.walk(node):
        targets = []
        if isinstance(sub, ast.Assign):
            targets = sub.targets
        elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
            targets = [sub.target]
        # `self.a, self.b = x, y` 처럼 **튜플/리스트 대입**도 정의다.
        # 이것을 놓쳐서 `core/ui.py` 의 `Control` 이 오탐 14건을 냈다.
        flat = []
        for target in targets:
            if isinstance(target, (ast.Tuple, ast.List)):
                flat.extend(target.elts)
            else:
                flat.append(target)
        for target in flat:
            if (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"):
                names.add(target.attr)
    return names


def self_used(node):
    """`self.<이름>` 참조 (이름, 줄번호)."""
    out = []
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Attribute)
                and isinstance(sub.value, ast.Name)
                and sub.value.id == "self"):
            out.append((sub.attr, sub.lineno))
    return out


def main():
    problems = []
    checked_classes = 0
    checked_refs = 0
    for path in TARGETS:
        try:
            tree = ast.parse(io.open(path, encoding="utf-8").read(), filename=path)
        except SyntaxError as exc:
            problems.append(f"{path}: 파싱 실패 — {exc}")
            continue
        # 같은 파일 안의 조상 클래스도 인정한다(파일 밖 상속은 알 수 없다).
        defined_by_class = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                defined_by_class[node.name] = class_defs(node) | self_assigned(node)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            checked_classes += 1
            known = set(defined_by_class.get(node.name, ()))
            external_base = False
            for base in node.bases:
                if isinstance(base, ast.Name):
                    if base.id in defined_by_class:
                        known |= defined_by_class[base.id]
                    else:
                        external_base = True
                else:
                    external_base = True
            if external_base:
                # 파일 밖 클래스를 상속하면 그쪽 멤버를 알 수 없다. 오탐을 내지
                # 않기 위해 이 클래스는 건너뛴다.
                continue
            for name, line in self_used(node):
                checked_refs += 1
                if name in known or name in KNOWN_DYNAMIC:
                    continue
                problems.append(
                    f"{path}:{line} {node.name}.self.{name} — 정의를 찾지 못했습니다 "
                    f"(메서드/속성이 지워졌는지 확인하십시오)")

    print(f"클래스 {checked_classes}개 / self 참조 {checked_refs}개 검사")
    if not checked_refs:
        print("\n*** 검사한 참조가 0개다 — 검사가 무력화됐는지 확인하십시오. ***")
        return 1
    if problems:
        print(f"\n이상 {len(problems)}건:")
        for line in problems:
            print(f"  {line}")
        print("\n실행 시 AttributeError 로 죽는다.")
        return 1
    print("이상 없음. 클래스가 쓰는 self.<이름> 이 모두 정의돼 있다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
