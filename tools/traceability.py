# -*- coding: utf-8 -*-
r"""`traceability.json` 을 원문·저장소와 다시 대조하고 양방향 인덱스를 낸다.

## 왜 도구로 만드는가

추적성 표를 문서에 손으로 적으면 **문서만 낡는다.** 사양서가 개정되거나 TC 가
바뀌면 표는 그대로 남아 "근거가 있다"고 거짓말한다. 그래서 데이터는
`traceability.json` 한 곳에만 두고, 이 도구가 **매번 원문과 대조**한다.

## 검사하는 것

1. `tc_id` 가 기준 체크리스트(`개정 TC` 시트)에 실제로 있는가
2. 체크리스트의 모든 TC 가 이 파일에 있는가(빠진 TC 없음)
3. TC가 범위 원장과 추적표 양쪽에 있고 등급이 일치하는가. 지원 작업(SUPPORT)은 별도로 둔다.
4. `module` 의 파일과 함수가 실제로 있는가
5. `command` 가 `run.py` 의 서브명령에 있는가
6. 인용한 `quote` 가 그 문서 원문에 **실제로 있는가**(공백 무시 비교)
7. 사양서 인용의 `page` / `srs` 가 실측값과 같은가
8. `steps` 번호가 체크리스트 Step Description 의 범위 안인가
9. Windows Update 항목(`checklist: windows_update`)은 기본기능 체크리스트가 아니라
   WU 체크리스트(`Checklist` 시트)와 대조하고, `reuses` 의 기본 TC 가 이 파일에
   있는가. WU 원본 또는 추적 행이 없으면 기준서 검사를 실패로 기록한다.

## 출력

- 위반 목록(있으면 종료 코드 1)
- **사양→TC** 역방향 인덱스: SRS ID 별로 어떤 TC 가 그것을 검증하는가
- **TC→사양** 요약: TC 별 인용 수와 미확정 사유

실행: `python tools/traceability.py --config config.json` (역방향 목록은 `--reverse`)
"""


import _paths  # noqa: F401 — 저장소 루트를 sys.path 와 cwd 에 맞춘다
import argparse
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


from core import specs, tc_basis

TRACE_PATH = "traceability.json"
SCOPE_PATH = "automation_scope.json"
WU_CHECKLIST = "windows_update"

#: 위반은 아니지만 알릴 것(WU 원본 없음, WU 약칭 사용 등). `check()` 가 채운다.
NOTES = []

MANUALS = {
    "Operation Manual": "Bellalun Viewer Operation Manual.V1.0.12W1_KO_확인완료.txt",
    "Service Manual": "Bellalun Viewer Service Manual.V1.0.12W1_KO_완료.txt",
    "DICOM Conformance Statement":
        "Bellalun Viewer DICOM Conformance Statement.V1.3W1_EN.txt",
}


class _Ctx:
    """`core.specs` / `core.checklist` 가 요구하는 최소 컨텍스트."""

    root = "."
    cfg = {}
    documents = {}


def squash(text):
    return re.sub(r"\s+", "", text or "")


def _load(path):
    with io.open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _run_commands():
    """`run.py` 가 등록한 서브명령 이름. 정규식으로 읽어 import 부작용을 피한다."""
    with io.open("run.py", encoding="utf-8") as stream:
        source = stream.read()
    return set(re.findall(r'sub\.add_parser\(\s*"([^"]+)"', source))


def _module_has(spec):
    """`tests/x.py::func` 형태를 파일·함수 존재로 확인한다."""
    if "::" not in spec:
        return False, f"형식 오류(파일::함수 여야 한다): {spec}"
    path, func = spec.split("::", 1)
    if not os.path.isfile(path):
        return False, f"파일 없음: {path}"
    with io.open(path, encoding="utf-8") as stream:
        body = stream.read()
    if not re.search(r"^def %s\(" % re.escape(func), body, re.M):
        return False, f"{path} 에 def {func}( 가 없음"
    return True, ""


_manual_cache = {}


def manual_text(ctx, name):
    if name not in _manual_cache:
        if name in ctx.documents:
            path = _verified_document(ctx, name)
            if path is None:
                _manual_cache[name] = None
            else:
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                with ZipFile(path) as docx:
                    root = ET.fromstring(docx.read("word/document.xml"))
                _manual_cache[name] = "\n".join(
                    "".join(t.text or "" for t in par.iter(ns + "t"))
                    for par in root.iter(ns + "p"))
            return _manual_cache[name]
        path = os.path.join(specs.knowledge_dir(ctx), MANUALS[name])
        if not os.path.isfile(path):
            _manual_cache[name] = None
        else:
            with io.open(path, encoding="utf-8", errors="replace") as stream:
                _manual_cache[name] = stream.read()
    return _manual_cache[name]


_spec_cache = {}


def _verified_document(ctx, source):
    ref = ctx.documents[source]
    directory = specs.knowledge_dir(ctx)
    if not directory:
        return None
    path = Path(directory) / ref["file"]
    try:
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == ref["sha256"]:
                return path
    except OSError:
        pass
    # 기록한 이름의 파일이 없거나 다르면, 같은 SHA256의 파일(이름만 바뀐 같은 원본)을 찾는다.
    # 예: 2026-11-26 지식 폴더 개편으로 `사양서(261030).pdf`가 `기존 원노트 사양서(261030).pdf`가 됐다.
    found = specs.find_by_sha256([directory], ref["sha256"], (Path(ref["file"]).suffix.lower(),))
    return Path(found) if found else None


def spec_pages(ctx, source):
    if source not in _spec_cache:
        path = (_verified_document(ctx, source) if source in ctx.documents
                else specs.spec_paths(ctx).get(source))
        _spec_cache[source] = specs.extract(path) if path else None
    return _spec_cache[source]


def locate_in_spec(ctx, source, quote, prefer=None):
    """(page, srs). 못 찾으면 (None, None).

    통합 사양서에는 같은 문장이 변경 메모와 요구사항 본문에 함께 나오기도 한다
    (예: "FB 및 CV는 촬영 불가"가 294쪽 메모와 678쪽 SRS 03-30-20에 있다).
    `prefer`(기록된 쪽)에 문장이 있으면 그 쪽을 쓰고, 없으면 첫 쪽을 쓴다.
    """
    pages = spec_pages(ctx, source)
    if not pages:
        return None, None
    needle = squash(quote)
    order = list(range(len(pages)))
    if prefer and 1 <= prefer <= len(pages):
        order.remove(prefer - 1)
        order.insert(0, prefer - 1)
    for i in order:
        page_text = pages[i]
        flat, index = [], []
        for j, ch in enumerate(page_text):
            if not ch.isspace():
                flat.append(ch)
                index.append(j)
        at = "".join(flat).find(needle)
        if at < 0:
            continue
        prev = list(reversed(pages[max(0, i - specs.ID_LOOKBACK_PAGES):i]))
        ids = specs.ids_near(page_text, index[at], prev)
        return i + 1, (ids[0] if ids else None)
    return None, None


def _check_wu(item, wu_rows, basic_ids, problems):
    """WU 항목의 체크리스트 대조. 기본기능 체크리스트와는 대조하지 않는다."""
    tc_id = item["tc_id"]
    if wu_rows:
        row = wu_rows.get(tc_id)
        if row is None:
            problems.append(f"WU 체크리스트에 없는 tc_id: {tc_id}")
        elif item.get("title") and squash(item["title"]) != squash(row.get("title")):
            # WU_TITLES 는 일부 행에서 Title 대신 Function 열 표기(약칭)를 쓴다.
            if squash(item["title"]) == squash(row.get("function")):
                NOTES.append(f"{tc_id}: title 이 체크리스트 Title 이 아니라 Function 열 "
                             "표기(약칭)와 같다")
            else:
                problems.append(f"{tc_id}: WU 체크리스트 Title 불일치 — 추적성 "
                                f"{item['title']!r}")
    if not (item.get("requirements") or item.get("reuses") or item.get("pending_reason")):
        problems.append(f"{tc_id}: 인용·reuses 가 없는데 pending_reason 도 없다")
    for ref in item.get("reuses") or []:
        if ref not in basic_ids:
            problems.append(f"{tc_id}: reuses 의 {ref} 가 기본 TC 추적성에 없다")


def _step_count(text):
    """Step Description 원문에서 마지막 단계 번호."""
    numbers = [int(n) for n in re.findall(r"^\s*(\d+)\.", text or "", re.M)]
    return max(numbers) if numbers else 0


def check(config=None):
    ctx = _Ctx()
    if config:
        ctx.cfg = _load(config)
        ctx.root = os.path.dirname(os.path.abspath(config))
    trace = _load(TRACE_PATH)
    ctx.documents = trace.get("_sources", {})
    _manual_cache.clear()
    _spec_cache.clear()
    scope = {x["tc_id"]: x for x in _load(SCOPE_PATH)}
    basic = tc_basis.resolve(ctx, "basic")
    rows = basic["rows"]
    commands = _run_commands()
    problems = []

    if not rows:
        problems.append(f"기본 기준서 {basic['source']['status']}: {basic['source']['reason']}")

    listed = [item["tc_id"] for item in trace["tc"]]
    if len(listed) != len(set(listed)):
        problems.append("traceability.json 에 중복 tc_id 가 있다")
    traced_ids = set(listed)
    for tc_id, item in scope.items():
        if item.get("level") != "SUPPORT" and tc_id not in traced_ids:
            problems.append(f"범위 원장에 있으나 추적성에 없다: {tc_id}")
    for tc_id in rows:
        if tc_id not in listed:
            problems.append(f"체크리스트에 있으나 추적성에 없다: {tc_id}")

    NOTES.clear()
    basic_ids = {x["tc_id"] for x in trace["tc"] if x.get("checklist") != WU_CHECKLIST}
    wu = tc_basis.resolve(ctx, WU_CHECKLIST)
    wu_rows = wu["rows"]
    if not wu_rows:
        problems.append(f"WU 기준서 {wu['source']['status']}: {wu['source']['reason']}")

    for item in trace["tc"]:
        tc_id = item["tc_id"]
        is_wu = item.get("checklist") == WU_CHECKLIST
        row = {} if is_wu else rows.get(tc_id)
        if is_wu:
            _check_wu(item, wu_rows, basic_ids, problems)
        elif row is None:
            row = {}
        if item.get("title") and row.get("title") and \
                squash(item["title"]) != squash(row["title"]):
            problems.append(f"{tc_id}: Title 불일치 — 추적성 {item['title']!r} / "
                            f"체크리스트 {row['title']!r}")
        expected_level = scope.get(tc_id, {}).get("level")
        if tc_id not in scope:
            problems.append(f"{tc_id}: 범위 원장에 없다")
        elif item.get("level") != expected_level:
            problems.append(f"{tc_id}: level 불일치 — 추적성 "
                            f"{item.get('level')!r} / scope {expected_level!r}")
        if item.get("module"):
            ok, why = _module_has(item["module"])
            if not ok:
                problems.append(f"{tc_id}: module {why}")
        if item.get("command") and item["command"] not in commands:
            problems.append(f"{tc_id}: run.py 에 없는 명령 "
                            f"{item['command']!r}")
        if not is_wu and not item.get("requirements") and not item.get("pending_reason"):
            problems.append(f"{tc_id}: 인용이 없는데 pending_reason 도 없다")

        last_step = _step_count(row.get("steps"))
        for req in item.get("requirements", []):
            doc, quote = req.get("doc"), req.get("quote")
            if not doc or not quote:
                problems.append(f"{tc_id}: doc/quote 가 비었다 — {req}")
                continue
            for step in req.get("steps", []):
                if last_step and not 1 <= int(step) <= last_step:
                    problems.append(
                        f"{tc_id}: Step {step} 은 체크리스트 범위(1~{last_step}) "
                        f"밖이다 — {quote[:40]}")
            if doc in MANUALS:
                text = manual_text(ctx, doc)
                if text is None:
                    problems.append(f"{tc_id}: 매뉴얼 텍스트를 찾지 못했다 — {doc}")
                elif squash(quote) not in squash(text):
                    problems.append(f"{tc_id}: {doc} 원문에 없는 인용 — "
                                    f"{quote[:60]}")
                continue
            page, srs = locate_in_spec(ctx, doc, quote, prefer=req.get("page"))
            if page is None:
                problems.append(f"{tc_id}: {doc} 원문에 없는 인용 — {quote[:60]}")
                continue
            if req.get("page") != page:
                problems.append(f"{tc_id}: {doc} 쪽 번호 불일치 — 기록 "
                                f"{req.get('page')} / 실측 {page} "
                                f"({quote[:40]})")
            if req.get("srs") != srs:
                problems.append(f"{tc_id}: {doc} SRS 불일치 — 기록 "
                                f"{req.get('srs')} / 실측 {srs} "
                                f"({quote[:40]})")
    return trace, problems


def reverse_index(trace):
    """사양→TC. 키는 `문서 SRS` 또는 매뉴얼 이름."""
    index = {}
    for item in trace["tc"]:
        for req in item.get("requirements", []):
            key = req["doc"]
            if req.get("srs"):
                key = f"{req['doc']} {req['srs']}"
            index.setdefault(key, {})
            index[key].setdefault(item["tc_id"], set()).update(
                req.get("steps") or [])
    return index


def main():
    # 콘솔 기본 코드 페이지가 cp949 인 환경에서 한글·기호가 깨지지 않게 한다
    # (`run.py` 와 같은 처리).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="승인 기준서와 사양 추적성 검사")
    parser.add_argument("--config", help="기준서·지식 폴더의 경로를 지정한 설정 JSON")
    parser.add_argument("--reverse", action="store_true")
    args = parser.parse_args()
    trace, problems = check(args.config)
    total = sum(len(x.get("requirements", [])) for x in trace["tc"])
    covered = [x for x in trace["tc"] if x.get("requirements")]
    wu_count = sum(1 for x in trace["tc"] if x.get("checklist") == WU_CHECKLIST)
    print(f"TC {len(trace['tc']) - wu_count}건 / 인용 있는 TC {len(covered)}건 / "
          f"인용 {total}건" + (f" (+ Windows Update TC {wu_count}건)" if wu_count else ""))

    if args.reverse:
        print()
        print("=== 사양 → TC ===")
        for key, tcs in sorted(reverse_index(trace).items()):
            entries = ", ".join(
                f"{tc}(Step {','.join(str(s) for s in sorted(steps))})"
                if steps else tc
                for tc, steps in sorted(tcs.items()))
            print(f"  {key:<34} {entries}")
        print()
        print("=== TC → 사양 ===")
        for item in trace["tc"]:
            reqs = item.get("requirements", [])
            if reqs:
                anchors = sorted({(r["doc"] + (" " + r["srs"] if r.get("srs")
                                               else "")) for r in reqs})
                print(f"  {item['tc_id']:<28} {len(reqs)}건  "
                      f"{' / '.join(anchors)}")
            elif item.get("reuses"):
                print(f"  {item['tc_id']:<28} 재사용  "
                      f"{' + '.join(item['reuses'])}")
            else:
                print(f"  {item['tc_id']:<28} 미확정  "
                      f"{item.get('pending_reason', '')}")

    for line in NOTES:
        print("  참고:", line)
    if problems:
        print()
        print(f"*** 위반 {len(problems)}건 ***")
        for line in problems:
            print("  -", line)
        return 1
    print("이상 없음 — 모든 인용이 원문과 일치하고 모듈·명령·Step 범위도 맞다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
