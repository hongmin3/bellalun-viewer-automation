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
  `if args.cmd == "run-regression":` 블록의 소스를 잘라서, 그 안에서 호출되는
  `run_*` / `install_*` / `setup_*` 이름이 **같은 블록 안의 import 나 대입**으로
  묶여 있는지 본다.

실행: python tools_check_regression_names.py
"""
import ast
import io
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = "run.py"
text = io.open(SRC, encoding="utf-8").read()
lines = text.split("\n")

start = next((i for i, l in enumerate(lines)
              if 'args.cmd == "run-regression"' in l), None)
if start is None:
    print("run-regression 블록을 찾지 못했습니다")
    sys.exit(1)
indent = len(lines[start]) - len(lines[start].lstrip())
end = start + 1
while end < len(lines):
    line = lines[end]
    if line.strip() and (len(line) - len(line.lstrip())) <= indent:
        break
    end += 1
block = "\n".join(lines[start:end])

bound = set(re.findall(r"import\s+\w+\s+as\s+(\w+)", block))
bound |= {n for stmt in re.findall(r"^\s*from\s+\S+\s+import\s+(.+)$", block,
                                   re.M)
          for n in re.findall(r"(\w+)(?:\s+as\s+(\w+))?", stmt)
          for n in ([n[1] or n[0]] if isinstance(n, tuple) else [n]) if n}
bound |= set(re.findall(r"^\s*(\w+)\s*=", block, re.M))

# 모듈 레벨에 정의된 함수/변수는 전역이라 어디서든 쓸 수 있다(예: run.py 의
# `def setup_all(...)`). 블록 밖 정의도 인정한다.
tree = ast.parse(text, filename=SRC)
bound |= {n.name for n in tree.body
          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
bound |= {t.id for n in tree.body if isinstance(n, ast.Assign)
          for t in n.targets if isinstance(t, ast.Name)}
bound |= {a.asname or a.name.split(".")[0]
          for n in tree.body if isinstance(n, ast.Import) for a in n.names}
bound |= {a.asname or a.name
          for n in tree.body if isinstance(n, ast.ImportFrom) for a in n.names}

called = set(re.findall(r"\b((?:run|install|setup)_\w+)\s*\(", block))
missing = sorted(called - bound)

print(f"회귀 블록: run.py {start + 1}~{end}행")
print(f"호출하는 이름 {len(called)}개 / 블록 안에서 묶인 이름 {len(bound)}개")
if missing:
    print("\n블록 안에서 import/대입되지 않은 이름:")
    for name in missing:
        print(f"  {name}")
    print("\n이 상태로 회귀를 돌리면 UnboundLocalError 로 죽는다.")
    sys.exit(1)
print("이상 없음. 회귀 블록이 쓰는 이름이 모두 그 블록 안에서 묶여 있다.")
