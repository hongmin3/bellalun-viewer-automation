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

실행: python tools_check_regression_names.py
"""

import _paths  # noqa: F401 — 저장소 루트를 sys.path 와 cwd 에 맞춘다
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

# 호출(`name(`)과 **참조**(`name,` / `(name,` / `[name`)를 함께 본다.
# 참조만 해도 바인딩이 없으면 UnboundLocalError 다.
PATTERN = r"\b((?:run|install|setup)_\w+)\b"
# **import 줄을 먼저 걷어낸다.** 회귀 블록은 쓰는 이름을 그 블록 안에서
# import 하므로, import 문에 나온 이름을 그냥 빼면 남는 게 없어진다
# (2026-08-24 실수). 검사하려는 것은 'import 가 아닌 곳에서 쓰이는 이름' 이다.
IMPORT_LINE = r"\s*(?:from\s+\S+\s+)?import\s"
body = "\n".join(line for line in block.split("\n")
                 if not re.match(IMPORT_LINE, line))
used = set(re.findall(PATTERN, body))
missing = sorted(used - bound)

print(f"회귀 블록: run.py {start + 1}~{end}행")
print(f"쓰는 이름 {len(used)}개 / 블록 안에서 묶인 이름 {len(bound)}개")
if not used:
    print("\n*** 쓰는 이름이 0개다 — 검사가 아무것도 확인하지 못하고 있다. ***")
    print("회귀 블록 추출 규칙이나 이름 패턴이 코드와 어긋났는지 확인하십시오.")
    sys.exit(1)
if missing:
    print("\n블록 안에서 import/대입되지 않은 이름:")
    for name in missing:
        print(f"  {name}")
    print("\n이 상태로 회귀를 돌리면 UnboundLocalError 로 죽는다.")
    sys.exit(1)
print("이상 없음. 회귀 블록이 쓰는 이름이 모두 그 블록 안에서 묶여 있다.")
