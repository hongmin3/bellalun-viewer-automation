# -*- coding: utf-8 -*-
r"""Windows Update 매핑·예외 경로 판정·공유 ctypes 정적 자체검사.

Viewer/DB 없이 소스와 JSON 만 읽는다. 검사 세 가지:

a. **WU 매핑 일치** — `tests/winupdate.py` 의 `WU_TITLES` 키, 각 매핑 함수가
   참조하는 기본 TC ID(문자열 리터럴), `KNOWN_DEFECT_EXCLUDE` 의 `wu_tc` 가
   `automation_scope.json` / `traceability.json` 의 WU 항목과 같은가.
b. **예외 경로 PASS 금지** — `tests/*.py`, `core/*.py` 의 `except` 블록 안에서
   PASS 를 직접 기록하는 호출(`.add(..., PASS)`, `status=PASS`,
   `.assert_true(..., True)` 리터럴, `x.status = PASS`)이 있는가.
c. **공유 ctypes.windll 함수 속성 변경 금지** — `ctypes.windll.X.Y.restype/
   argtypes/errcheck` 대입(별칭 포함)이 있는가. `ctypes.WinDLL(...)` 로 만든
   개별 인스턴스는 다른 모듈과 함수 객체를 공유하지 않으므로 허용한다.

b, c 는 이미 있는 위반을 **기준선(BASELINE)** 으로 기록해 두고, 기준선과
달라지면(새 위반 또는 해소) 실패한다. 기준선 키는 줄 번호가 아니라
`경로::함수: 내용` 이라 위반과 무관한 편집으로 줄이 밀려도 흔들리지 않는다.
기준선 항목을 고칠지는 사용자 확인 대상이다 — 이 도구는 고치지 않는다.

실행: python tools/wu_selfcheck.py   (위반이 있으면 종료 코드 1)
"""

import ast
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

WU_SOURCE = "tests/winupdate.py"
SCOPE_PATH = "automation_scope.json"
TRACE_PATH = "traceability.json"
WU_CHECKLIST = "windows_update"
WU_PREFIX = "TC_WindowsUpdate_"
#: 매핑 함수가 참조하는 기본기능/XIPL TC ID. 문장 속 언급(`... TC_Basic_WorkFlow_16과`)은
#: 문자열 전체가 ID 인 경우만 세므로 잡히지 않는다.
BASIC_TC_RE = re.compile(r"TC_(?:Basic|XIPL)_\w+")

EXCEPT_PASS_GLOBS = ("core/*.py", "tests/*.py")
WINDLL_GLOBS = ("core/*.py", "tests/*.py", "tools/*.py", "run.py", "bellalunauto/**/*.py")
CTYPES_FUNC_ATTRS = {"restype", "argtypes", "errcheck"}

#: 검사 b 기준선 — 기존 위반(사용자 확인 전까지 보고만 한다). 2026-11-04 실측 0건.
#: `PASS if ok else FAIL` 처럼 조건으로 고르는 식은 직접 기록이 아니라 세지 않는다.
EXCEPT_PASS_BASELINE = ()

#: 검사 c 기준선 — 기존 위반(사용자 확인 전까지 보고만 한다). 2026-11-04 실측:
#: `core/ui.py` 모듈 수준에서 공유 `ctypes.windll.user32` 함수 서명을 지정한다.
WINDLL_BASELINE = (
    "core/ui.py::<module>: u32.SendInput.argtypes = ...",
    "core/ui.py::<module>: u32.SendInput.restype = ...",
    "core/ui.py::<module>: u32.WindowFromPoint.argtypes = ...",
    "core/ui.py::<module>: u32.WindowFromPoint.restype = ...",
    "core/ui.py::<module>: u32.GetAncestor.argtypes = ...",
    "core/ui.py::<module>: u32.GetAncestor.restype = ...",
)


# ---------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------

def _read(path):
    return Path(path).read_text(encoding="utf-8")


def _load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _repo_sources(globs, root=ROOT):
    """{상대경로(/구분): 소스}. 생성물·캐시는 제외한다."""
    out = {}
    root = Path(root)
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            out[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return out


class _Scoped(ast.NodeVisitor):
    """노드마다 감싸는 함수 이름(qualname)을 알 수 있게 순회한다."""

    def __init__(self):
        self.stack = []

    def qualname(self):
        return ".".join(self.stack) or "<module>"

    def _scope(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scope


# ---------------------------------------------------------------------
# a. WU 매핑 일치
# ---------------------------------------------------------------------

def _assigned_literal(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def _wu_ids_built(func):
    """함수 안 `TCResult("TC_WindowsUpdate_NN", ...)` 의 WU ID."""
    ids = set()
    for node in ast.walk(func):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "TCResult" and node.args
                and isinstance(node.args[0], ast.Constant)
                and str(node.args[0].value).startswith(WU_PREFIX)):
            ids.add(node.args[0].value)
    return ids


def parse_wu_source(source):
    """`tests/winupdate.py` 소스에서 매핑 정보를 뽑는다(import 하지 않는다)."""
    tree = ast.parse(source)
    titles = _assigned_literal(tree, "WU_TITLES") or {}
    defects = _assigned_literal(tree, "KNOWN_DEFECT_EXCLUDE") or {}
    refs, only_steps, defect_users = {}, {}, set()
    for func in tree.body:
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        wu_ids = _wu_ids_built(func)
        if not wu_ids:
            continue
        basic, steps, uses_defects = set(), {}, False
        for node in ast.walk(func):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and BASIC_TC_RE.fullmatch(node.value)):
                basic.add(node.value)
            elif isinstance(node, ast.Name) and node.id == "KNOWN_DEFECT_EXCLUDE":
                for parent in ast.walk(func):
                    if (isinstance(parent, ast.keyword) and parent.arg == "exclude_keys"
                            and parent.value is node):
                        uses_defects = True
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_copy_checks"):
                label = node.args[2] if len(node.args) > 2 else None
                for kw in node.keywords:
                    if (kw.arg == "only_steps" and isinstance(label, ast.Constant)):
                        steps[label.value] = set(ast.literal_eval(kw.value))
        for wu_id in wu_ids:
            refs.setdefault(wu_id, set()).update(basic)
            for tc_id, value in steps.items():
                only_steps.setdefault(wu_id, {})[tc_id] = value
            if uses_defects:
                defect_users.add(wu_id)
    return {"titles": titles, "defects": defects, "refs": refs,
            "only_steps": only_steps, "defect_users": defect_users}


def _wu_rows(rows, label, problems):
    """WU 항목만 tc_id 로 묶고 `checklist` 표식 누락/오표기를 보고한다."""
    out = {}
    for row in rows:
        tc_id = str(row.get("tc_id") or "")
        is_wu_id = tc_id.startswith(WU_PREFIX)
        marked = row.get("checklist") == WU_CHECKLIST
        if is_wu_id != marked:
            problems.append(f"{label}: {tc_id} checklist 표식 불일치 — "
                            f"checklist={row.get('checklist')!r}")
        if is_wu_id:
            if tc_id in out:
                problems.append(f"{label}: {tc_id} 중복")
            out[tc_id] = row
    return out


def _reuse_ids(row):
    items = row.get("reuses") or []
    return {item["tc_id"] if isinstance(item, dict) else item for item in items}


def check_mapping(wu_source, scope_rows, trace):
    """검사 a. 위반 문장 리스트."""
    problems = []
    try:
        info = parse_wu_source(wu_source)
    except (SyntaxError, ValueError) as exc:
        return [f"{WU_SOURCE}: 파싱 실패 — {exc}"]
    titles = info["titles"]
    scope = _wu_rows(scope_rows, SCOPE_PATH, problems)
    traced = _wu_rows(trace.get("tc") or [], TRACE_PATH, problems)
    known_basic = {str(r.get("tc_id")) for r in trace.get("tc") or []
                   if r.get("checklist") != WU_CHECKLIST}

    if not titles:
        problems.append(f"{WU_SOURCE}: WU_TITLES 를 읽지 못했다")
    for label, rows in ((SCOPE_PATH, scope), (TRACE_PATH, traced)):
        for tc_id in sorted(set(titles) - set(rows)):
            problems.append(f"{label}: WU_TITLES 의 {tc_id} 가 없다")
        for tc_id in sorted(set(rows) - set(titles)):
            problems.append(f"{label}: WU_TITLES 에 없는 {tc_id}")
        for tc_id, row in sorted(rows.items()):
            if tc_id in titles and row.get("title") != titles[tc_id]:
                problems.append(f"{label}: {tc_id} title {row.get('title')!r} ≠ "
                                f"WU_TITLES {titles[tc_id]!r}")
    for tc_id in sorted(set(titles) - set(info["refs"])):
        problems.append(f"{WU_SOURCE}: {tc_id} 를 만드는 매핑 함수가 없다")

    for tc_id in sorted(set(titles)):
        code_refs = info["refs"].get(tc_id, set())
        for label, rows in ((SCOPE_PATH, scope), (TRACE_PATH, traced)):
            if tc_id not in rows:
                continue
            listed = _reuse_ids(rows[tc_id])
            for missing in sorted(code_refs - listed):
                problems.append(f"{label}: {tc_id} reuses 에 코드가 참조하는 {missing} 가 없다")
            for extra in sorted(listed - code_refs):
                problems.append(f"{label}: {tc_id} reuses 의 {extra} 를 코드가 참조하지 않는다")
            for ref in sorted(listed - known_basic):
                problems.append(f"{label}: {tc_id} reuses 의 {ref} 가 {TRACE_PATH} 기본 TC 에 없다")
        row = scope.get(tc_id)
        if row is None:
            continue
        code_steps = info["only_steps"].get(tc_id, {})
        json_steps = {item["tc_id"]: set(item["only_steps"])
                      for item in row.get("reuses") or []
                      if isinstance(item, dict) and item.get("only_steps")}
        if code_steps != json_steps:
            problems.append(f"{SCOPE_PATH}: {tc_id} only_steps {json_steps} ≠ 코드 {code_steps}")

    # 판정 제외 결함: KNOWN_DEFECT_EXCLUDE ↔ scope known_defect_exclude
    code_defects = {(wu["wu_tc"], key[0], key[1]) for key, wu in info["defects"].items()}
    json_defects = set()
    for tc_id, row in scope.items():
        for item in row.get("known_defect_exclude") or []:
            json_defects.add((tc_id, item.get("tc_id"), item.get("title")))
    for wu_tc, src, title in sorted(code_defects - json_defects):
        problems.append(f"{SCOPE_PATH}: {wu_tc} known_defect_exclude 에 ({src}, {title!r}) 가 없다")
    for wu_tc, src, title in sorted(json_defects - code_defects):
        problems.append(f"{SCOPE_PATH}: {wu_tc} known_defect_exclude 의 ({src}, {title!r}) 가 "
                        "KNOWN_DEFECT_EXCLUDE 에 없다")
    for wu_tc, src, _title in sorted(code_defects):
        if src not in info["refs"].get(wu_tc, set()):
            problems.append(f"{WU_SOURCE}: 결함 제외 {src} 를 {wu_tc} 매핑 함수가 참조하지 않는다")
    defect_wus = {wu for wu, _s, _t in code_defects}
    for wu_tc in sorted(defect_wus ^ info["defect_users"]):
        problems.append(f"{WU_SOURCE}: {wu_tc} — KNOWN_DEFECT_EXCLUDE 의 wu_tc 와 "
                        "exclude_keys=KNOWN_DEFECT_EXCLUDE 사용 함수가 다르다")
    return problems


def repo_mapping_problems(root=ROOT):
    root = Path(root)
    return check_mapping(_read(root / WU_SOURCE), _load_json(root / SCOPE_PATH),
                         _load_json(root / TRACE_PATH))


# ---------------------------------------------------------------------
# b. except 블록 안의 PASS 기록
# ---------------------------------------------------------------------

def _is_pass(node):
    return ((isinstance(node, ast.Name) and node.id == "PASS")
            or (isinstance(node, ast.Attribute) and node.attr == "PASS")
            or (isinstance(node, ast.Constant) and node.value == "PASS"))


def _handler_nodes(handler):
    """except 본문 노드. 안에 정의된 함수/클래스 본문은 그 블록 실행이 아니라 제외."""
    stack = list(handler.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.ExceptHandler):
            continue  # 안쪽 except 는 그 블록 방문에서 따로 센다(중복 보고 방지)
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _pass_record(node):
    """PASS 를 직접 기록하는 노드면 설명 문자열, 아니면 None."""
    if isinstance(node, ast.Call):
        name = (node.func.attr if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "?"))
        if any(_is_pass(arg) for arg in node.args):
            return f"{name}(..., PASS)"
        for kw in node.keywords:
            if _is_pass(kw.value):
                return f"{name}({kw.arg}=PASS)"
        if name == "assert_true":
            cond = node.args[2] if len(node.args) > 2 else next(
                (kw.value for kw in node.keywords if kw.arg == "cond"), None)
            if isinstance(cond, ast.Constant) and cond.value is True:
                return "assert_true(..., True)"
    elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and _is_pass(node.value):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            attr = getattr(target, "attr", None) or getattr(target, "id", None)
            if attr in ("status", "verdict"):
                return f"{attr} = PASS"
    elif isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value in ("status", "verdict") and _is_pass(value):
                return f"{{'{key.value}': PASS}}"
    return None


def check_except_pass(sources):
    """검사 b. [(키, 줄 번호)] — 키는 `경로::함수: 내용`."""
    found = []
    for path, source in sorted(sources.items()):
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            found.append((f"{path}::<parse>: 파싱 실패 — {exc.msg}", exc.lineno or 0))
            continue

        class Visitor(_Scoped):
            def visit_ExceptHandler(self, handler):
                for node in _handler_nodes(handler):
                    desc = _pass_record(node)
                    if desc:
                        found.append((f"{path}::{self.qualname()}: {desc}", node.lineno))
                self.generic_visit(handler)

        Visitor().visit(tree)
    return found


# ---------------------------------------------------------------------
# c. 공유 ctypes.windll 함수 속성 변경
# ---------------------------------------------------------------------

def _chain(node):
    """`a.b.c` -> ["a", "b", "c"]; 이름 체인이 아니면 None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


def _windll_aliases(tree):
    """(ctypes 모듈 별칭, windll 계열 이름). 파일 전체 기준(보수적으로 넓게)."""
    ctypes_names, windll_names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "ctypes":
                    ctypes_names.add(alias.asname or "ctypes")
        elif isinstance(node, ast.ImportFrom) and node.module == "ctypes":
            for alias in node.names:
                if alias.name == "windll":
                    windll_names.add(alias.asname or "windll")
    ctypes_names.add("ctypes")

    def rooted(value):
        chain = _chain(value)
        if not chain:
            return False
        if chain[0] in windll_names:
            return True
        return chain[0] in ctypes_names and len(chain) > 1 and chain[1] == "windll"

    changed = True
    while changed:  # `u32 = ctypes.windll.user32`, `f = u32.GetX` 같은 연쇄 별칭
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and rooted(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in windll_names:
                        windll_names.add(target.id)
                        changed = True
    return rooted


def check_windll(sources):
    """검사 c. [(키, 줄 번호)] — 키는 `경로::함수: 대입식`."""
    found = []
    for path, source in sorted(sources.items()):
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            found.append((f"{path}::<parse>: 파싱 실패 — {exc.msg}", exc.lineno or 0))
            continue
        rooted = _windll_aliases(tree)

        class Visitor(_Scoped):
            def _check(self, node, targets):
                for target in targets:
                    if (isinstance(target, ast.Attribute) and target.attr in CTYPES_FUNC_ATTRS
                            and rooted(target.value)):
                        text = ".".join(_chain(target) or [target.attr])
                        found.append((f"{path}::{self.qualname()}: {text} = ...", node.lineno))

            def visit_Assign(self, node):
                self._check(node, node.targets)
                self.generic_visit(node)

            def visit_AugAssign(self, node):
                self._check(node, [node.target])
                self.generic_visit(node)

            def visit_AnnAssign(self, node):
                self._check(node, [node.target])
                self.generic_visit(node)

        Visitor().visit(tree)
    return found


# ---------------------------------------------------------------------
# 기준선 대조와 CLI
# ---------------------------------------------------------------------

def baseline_diff(found, baseline):
    """(새 위반 키, 해소된 기준선 키). 같은 키가 여러 번이면 개수까지 맞춘다."""
    now, base = Counter(key for key, _line in found), Counter(baseline)
    return sorted((now - base).elements()), sorted((base - now).elements())


def repo_except_pass(root=ROOT):
    return check_except_pass(_repo_sources(EXCEPT_PASS_GLOBS, root))


def repo_windll(root=ROOT):
    return check_windll(_repo_sources(WINDLL_GLOBS, root))


def _report(title, found, baseline):
    new, gone = baseline_diff(found, baseline)
    print(f"[{title}] 현재 {len(found)}건 / 기준선 {len(baseline)}건")
    for key, line in sorted(found, key=lambda x: (x[0].split('::')[0], x[1])):
        mark = "  (기준선)" if key in baseline else "  (신규)"
        path, rest = key.split("::", 1)
        print(f"  {path}:{line} {rest}{mark}")
    for key in gone:
        print(f"  기준선에 있으나 지금은 없음(기준선 갱신 필요): {key}")
    return not new and not gone


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ok = True
    mapping = repo_mapping_problems()
    print(f"[a. WU 매핑 일치] 위반 {len(mapping)}건")
    for line in mapping:
        print("  -", line)
    ok = ok and not mapping
    ok = _report("b. 예외 경로 PASS 금지", repo_except_pass(), EXCEPT_PASS_BASELINE) and ok
    ok = _report("c. 공유 ctypes.windll 속성 변경 금지", repo_windll(), WINDLL_BASELINE) and ok
    print("이상 없음(기준선 위반은 보고만 함)." if ok else "*** 위반 또는 기준선 불일치 ***")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
