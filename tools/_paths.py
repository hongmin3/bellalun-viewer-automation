# -*- coding: utf-8 -*-
"""`tools/` 안의 도구들이 저장소 루트를 기준으로 동작하게 맞춘다.

## 왜 필요한가

2026-08-26 사용자 지시로 `auto/` 바닥에 흩어져 있던 `tools_*.py` 10개를
`auto/tools/` 한 폴더로 모았다. 그런데 이 도구들은 원래 **저장소 루트에서 실행되는
것을 전제로** 쓰여 있었다.

- `ROOT = os.path.dirname(os.path.abspath(__file__))` 로 저장소 루트를 잡는다
- `from core import ...` 로 저장소 모듈을 import 한다
- `glob("core/*.py")`, `open("run.py")` 처럼 **상대 경로**를 쓴다

한 단계 깊어졌으므로 그대로 옮기면 세 가지가 전부 깨진다. 그래서 각 도구는 맨 위에서
이 모듈을 import 해 `REPO` 를 받고, 이 모듈이 로드되는 순간

- `sys.path` 에 저장소 루트를 넣어 `from core import ...` 가 되게 하고,
- **작업 디렉터리를 저장소 루트로 옮겨** 기존 상대 경로가 그대로 동작하게 한다.

`os.chdir` 은 부작용이 있는 조작이라 보통 모듈 import 시점에 하지 않는다. 여기서는
**의도한 것**이다 — 도구를 어디서 실행하든(`auto/` 에서든 `auto/tools/` 에서든
프로젝트 루트에서든) 같은 결과를 내게 하려는 것이고, 이 도구들은 전부 단독 실행되는
스크립트라 다른 코드의 cwd 를 빼앗을 일이 없다.
"""

import os
import sys

#: `auto/` — 저장소 루트
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: `Bellalun Viewer\` — 프로젝트 루트(저장소 밖). 문서·기준 체크리스트가 여기 있다
PROJECT = os.path.dirname(REPO)

if REPO not in sys.path:
    sys.path.insert(0, REPO)

os.chdir(REPO)
