# -*- coding: utf-8 -*-
"""회귀 블록이 쓰는 이름이 **그 블록 안에서** import 되는지 확인한다.

왜 필요한가 (2026-08-20 회귀 17차)
  WF_07/WF_10 을 회귀 사슬에 넣을 때 import 가 회귀 블록이 아니라 `run-wf10` 단독
  분기에 들어가, 회귀가 41분 만에
  `UnboundLocalError: cannot access local variable 'run_emergency'` 로 죽었다.

  `ast` 미정의 이름 검사도, `tools_check_module_attrs.py` 도 이것을 잡지 못한다 -
  함수 어딘가에 그 이름의 import 가 있으면 "정의됨" 으로 보이지만 실제로는 다른
  분기라 이 분기에서는 unbound 다.

검사 방법
  `if args.cmd == "run-regression":` 블록의 소스를 잘라서, 그 안에서 **쓰이는**
  `run_*` / `install_*` / `setup_*` 이름이 **같은 블록 안의 import 나 대입**으로
  묶여 있는지 본다.

  2026-08-24 주의: 예전에는 `name(` 형태의 **호출**만 셌다. 그런데 회귀 사슬을
  `chain = [(install_01, ...), ...]` 처럼 **함수 참조 목록**으로 바꾸자 세는 이름이
  0개가 되어 **검사가 조용히 아무것도 하지 않게** 됐다. 참조도 바인딩이 필요하므로
  (unbound 면 똑같이 `UnboundLocalError`) 지금은 호출과 참조를 함께 본다.
  세는 이름이 0개면 그 자체를 실패로 본다 — 검사가 무력화된 것을 침묵으로 넘기지
  않기 위해서다.

  2026-11-16: 사슬이 `_basic_chain_stages()` 같은 목록 함수로 옮겨진 뒤 예전 검사는
  분기 **주석** 속 `install_01` 을 세어 빌드를 막았고, 정작 사슬 함수는 보지 않았다.
  지금은 `ast` 로 실제 코드의 이름만 세고, 분기와 사슬 함수를 각각 따로 검사한다
  (SPEC REQ-DIST-003).

실행: python tools/check_regression_names.py
"""

import ast
import io
import re
import sys

SRC = "run.py"
#: 사슬 목록을 만드는 함수. 각 함수 안에서 TC 진입 함수를 import 해야 한다.
CHAIN_FUNCTIONS = ("_basic_chain_stages", "_wu_chain_stages", "_combined_chain_stages")
NAME = re.compile(r"(?:run|install|setup)_\w+$")


def _is_regression_branch(node):
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    return (isinstance(test.left, ast.Attribute) and test.left.attr == "cmd"
            and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "run-regression")


def _module_bound(tree):
    bound = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            bound |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound |= {a.asname or a.name.split(".")[0] for a in node.names}
    return bound


def _region_names(nodes):
    """영역 안의 바인딩(import·대입·for 등)과, 패턴에 맞는 읽기 이름."""
    bound, used = set(), set()
    for top in nodes:
        for node in ast.walk(top):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bound |= {a.asname or a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.Name):
                if isinstance(node.ctx, (ast.Store, ast.Del)):
                    bound.add(node.id)
                elif NAME.match(node.id):
                    used.add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                bound.add(node.name)
    return bound, used


def check(text):
    """검사 결과: 영역 이름 목록, 영역별 쓰는 이름, 빠진 바인딩, 검사 자체 오류."""
    tree = ast.parse(text, filename=SRC)
    module = _module_bound(tree)
    regions = {}
    for node in ast.walk(tree):
        if _is_regression_branch(node) and "run-regression" not in regions:
            regions["run-regression"] = node.body
        elif isinstance(node, ast.FunctionDef) and node.name in CHAIN_FUNCTIONS:
            regions[node.name] = node.body
    used_by, missing, errors = {}, {}, []
    if "run-regression" not in regions:
        errors.append("run-regression 분기를 찾지 못했습니다")
    for name, nodes in regions.items():
        bound, used = _region_names(nodes)
        used_by[name] = used
        lacking = sorted(used - bound - module)
        if lacking:
            missing[name] = lacking
    if not any(used_by.values()):
        errors.append("쓰는 이름이 0개다. 검사가 아무것도 확인하지 못하고 있다.")
    return {"regions": list(regions), "used": used_by, "missing": missing, "errors": errors}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import _paths  # noqa: F401 — 저장소 루트를 sys.path 와 cwd 에 맞춘다
    report = check(io.open(SRC, encoding="utf-8").read())
    for name in report["regions"]:
        print(f"검사 영역 {name}: 쓰는 이름 {len(report['used'][name])}개")
    for error in report["errors"]:
        print(f"\n*** {error} ***")
    if report["errors"]:
        print("회귀 블록 추출 규칙이나 이름 패턴이 코드와 어긋났는지 확인하십시오.")
        return 1
    if report["missing"]:
        for name, names in report["missing"].items():
            print(f"\n{name} 안에서 import/대입되지 않은 이름:")
            for item in names:
                print(f"  {item}")
        print("\n이 상태로 회귀를 돌리면 UnboundLocalError 로 죽는다.")
        return 1
    print("이상 없음. 회귀 분기와 사슬 함수가 쓰는 이름이 모두 그 안에서 묶여 있다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
