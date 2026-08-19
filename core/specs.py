# -*- coding: utf-8 -*-
r"""사양서·매뉴얼 원문을 코드에서 직접 찾아 인용한다.

`AGENTS.md` 0절은 "TC가 무엇을 하는지는 개정본에서, 왜 그것이 정상인지는
매뉴얼·사양서에서 확인한다"고 정한다. 그런데 사양서는 `.pdf`라 grep이 되지 않아
지금까지 근거를 대기 어려웠다.

이 모듈이 그 간격을 메운다. `pypdf`(MIT, 순수 Python)로 텍스트를 뽑아 `.txt`로
캐시하고, `search()`로 문구를 찾아 **쪽 번호와 SRS ID까지** 돌려준다. 판정의
`note`에 그 값을 적으면 리포트만 보고도 기준의 출처를 확인할 수 있다.

사양서에는 요구사항마다 `SRS 01-10-10` 형태의 ID가 붙어 있다(실측). 절 번호보다
이 ID가 인용에 정확하다.

사용 예

    from core import specs

    hits = specs.search(ctx, "Anonymous")
    # [{'source': '사양서1', 'page': 214, 'srs': ['SRS 09-30-10'],
    #   'text': '... 익명화 ...'}, ...]
"""

import io
import os
import re

# `지식` 폴더에 함께 관리되는 근거 문서.
KNOWLEDGE_DIR = "지식"
# 끝 번호는 2자리도 3자리도 있다(`SRS 01-10-130`). `\d\d` 로 두면 3자리가 잘려
# **존재하지 않는 번호**가 인용된다 — 사양서1 전체에 3자리 끝 번호가 38건이다
# (2026-08-20 실측).
SRS_PATTERN = re.compile(r"SRS \d\d-\d\d-\d+")

# 본문 속 **교차참조**를 구분한다. 요구사항 제목은 ID 뒤에 바로 불릿/줄바꿈이 오고,
# 교차참조는 `SRS 01-10-70. License 체크 참조` 나 `(SRS 01-10-130)` 처럼 마침표+설명
# 또는 닫는 괄호가 붙는다. 교차참조는 그 문구의 근거가 아니므로 후보 순서에서 뒤로
# 미룬다(완전히 버리지는 않는다 — 형태만으로 100% 단정할 수 없다).
SRS_CROSSREF_SUFFIX = re.compile(r"\s*(?:\.|\))")

# 파일명 일부 -> 짧은 이름. 파일명에 날짜가 붙어 바뀔 수 있으므로 부분 일치로 찾는다.
SPEC_FILES = {
    "사양서1": "사양서1",
    "사양서2": "사양서2",
}


class SpecError(RuntimeError):
    pass


def knowledge_dir(ctx):
    """`지식` 폴더를 PC 독립적으로 찾는다.

    `core/dbreset.source_dir`, `core/checklist.source_path`와 같은 방식이다 —
    저장소 위치 기준으로 위로 올라가며 찾는다. 절대경로를 코드에 박지 않는다.
    """
    here = os.path.abspath(ctx.root)
    for _ in range(4):                      # auto -> Bellalun Viewer -> 자동화 ...
        here = os.path.dirname(here)
        if not here:
            break
        candidate = os.path.join(here, KNOWLEDGE_DIR)
        if os.path.isdir(candidate):
            return candidate
    return ""


def spec_paths(ctx):
    """사양서 PDF 경로를 {짧은 이름: 경로}로 돌려준다."""
    root = knowledge_dir(ctx)
    if not root:
        return {}
    found = {}
    for name in os.listdir(root):
        if not name.lower().endswith(".pdf"):
            continue
        for short, marker in SPEC_FILES.items():
            if marker in name:
                found[short] = os.path.join(root, name)
    return found


def _cache_path(pdf_path):
    """추출 텍스트 캐시 경로. 원본과 같은 폴더에 `.txt`로 둔다.

    매뉴얼 `.docx`도 같은 규칙으로 `.txt` 사본을 두고 있어(운영 지침 0절) 일관된다.
    다음 사람이 grep으로 바로 찾을 수 있는 것이 목적이다.
    """
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    base = base.replace("(사양서) ", "")
    return os.path.join(os.path.dirname(pdf_path), f"{base}.txt")


def extract(pdf_path, force=False):
    """PDF 텍스트를 쪽 단위로 뽑고 `.txt`로 캐시한다.

    반환: 쪽별 문자열 리스트(0번째 원소가 1쪽).

    캐시가 원본보다 새로우면 재추출하지 않는다. 사양서1은 336쪽이라 매번 뽑으면
    느리다.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:                      # pragma: no cover
        raise SpecError(
            "pypdf가 없어 사양서를 읽을 수 없습니다. "
            "`python -m pip install -r requirements.txt`로 설치하십시오."
        ) from exc

    cache = _cache_path(pdf_path)
    if not force and os.path.isfile(cache):
        if os.path.getmtime(cache) >= os.path.getmtime(pdf_path):
            return io.open(cache, encoding="utf-8").read().split("\f")

    reader = PdfReader(pdf_path)
    pages = [(page.extract_text() or "") for page in reader.pages]
    try:
        io.open(cache, "w", encoding="utf-8", newline="\n").write("\f".join(pages))
    except OSError:
        pass                                        # 캐시 실패는 치명적이지 않다
    return pages


# 요구사항 본문이 여러 쪽에 걸칠 수 있으므로, 앞선 쪽을 이만큼까지 거슬러 올라가
# ID 를 찾는다. 297쪽(Print Overlay Header 사양)은 296쪽에도 ID 가 없어서 한 쪽만
# 보면 근거를 못 찾았다 — 실제 근거는 295쪽의 `SRS 04-10-20` 이다(2026-08-20 실측).
ID_LOOKBACK_PAGES = 6


def _srs_hits(page_text):
    """`(위치, ID, 교차참조인가)` 목록. 위치 순서를 유지한다."""
    out = []
    for m in SRS_PATTERN.finditer(page_text):
        tail = page_text[m.end():m.end() + 3]
        out.append((m.start(), m.group(0),
                    bool(SRS_CROSSREF_SUFFIX.match(tail))))
    return out


def ids_near(page_text, pos, prev_pages=()):
    """매치 위치 `pos` 에 **가장 그럴듯한 SRS ID 부터** 순서대로 돌려준다.

    사양서는 "SRS ID 다음에 그 요구사항 본문"이 오는 구조다. 그래서 어떤 문구의
    근거는 **그 문구보다 앞에 있는 가장 가까운 ID** 다.

    순서
      1. 같은 쪽에서 매치보다 앞에 있는 ID — 가까운 것부터
      2. 같은 쪽에 앞선 ID 가 없으면 **앞선 쪽들을 거슬러 올라가** 마지막 ID
         (요구사항 제목이 앞쪽에 있고 본문만 이 쪽에 있는 경우. 본문이 여러 쪽에
          걸치면 두 쪽 이상 앞일 수 있다)
      3. 매치 뒤의 ID — 가까운 것부터

    `prev_pages` 는 **이 쪽 직전부터 역순으로** 준다.

    정렬(`sorted`)로 고르면 안 된다. 2026-08-20 실측: SRS ID 가 2개 이상인 쪽 56개
    중 **36개**에서 정렬 첫 번째가 위치상 올바른 것과 달랐다.
    """
    hits = _srs_hits(page_text)
    before = [(srs, ref) for start, srs, ref in hits if start < pos]
    after = [(srs, ref) for start, srs, ref in hits if start >= pos]

    # 앞선 것 중 **제목**을 가장 먼저, 그 다음 앞선 교차참조.
    ordered = [srs for srs, ref in reversed(before) if not ref]
    if not ordered:
        for text in prev_pages[:ID_LOOKBACK_PAGES]:
            prev = [srs for _, srs, ref in _srs_hits(text or "") if not ref]
            if prev:
                ordered.append(prev[-1])
                break
    ordered.extend(srs for srs, ref in reversed(before) if ref)
    ordered.extend(srs for srs, _ in after)

    seen = set()
    unique = []
    for srs in ordered:
        if srs not in seen:
            seen.add(srs)
            unique.append(srs)
    return unique


def search(ctx, pattern, flags=re.I, context=160, limit=20):
    """사양서에서 문구를 찾아 쪽 번호와 SRS ID를 함께 돌려준다.

    반환: [{"source": 짧은 이름, "page": 1-based 쪽, "srs": [ID...],
            "text": 주변 문구}]

    `srs[0]` 은 **매치된 문구의 근거일 가능성이 가장 높은 ID** 다(`ids_near`).
    판정의 `note`에 `source`/`page`/`srs`를 적으면 근거가 추적된다.
    """
    regex = re.compile(pattern, flags)
    out = []
    for short, path in sorted(spec_paths(ctx).items()):
        pages = extract(path)
        for index, page_text in enumerate(pages, start=1):
            if not page_text:
                continue
            match = regex.search(page_text)
            if not match:
                continue
            start = max(0, match.start() - context // 2)
            snippet = " ".join(
                page_text[start:match.end() + context // 2].split())
            out.append({
                "source": short,
                "page": index,
                # 정렬이 아니라 **매치 위치 기준**으로 고른다.
                # 앞선 쪽들을 역순으로 넘긴다(직전 쪽이 먼저).
                "srs": ids_near(page_text, match.start(),
                                pages[max(0, index - 1 - ID_LOOKBACK_PAGES):
                                      index - 1][::-1]),
                "text": snippet,
            })
            if len(out) >= limit:
                return out
    return out


def cite(ctx, pattern, **kw):
    """`search` 결과를 판정 `note`에 넣을 한 줄 인용문으로 만든다.

    찾지 못하면 빈 문자열. **근거가 없으면 없다고 말하는 것**이 규칙이라
    억지로 문구를 만들지 않는다.
    """
    hits = search(ctx, pattern, limit=1, **kw)
    if not hits:
        return ""
    hit = hits[0]
    srs = f" {hit['srs'][0]}" if hit["srs"] else ""
    return f"근거: {hit['source']} {hit['page']}쪽{srs} — \"{hit['text'][:120]}\""
