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
SRS_PATTERN = re.compile(r"SRS \d\d-\d\d-\d\d")

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


def search(ctx, pattern, flags=re.I, context=160, limit=20):
    """사양서에서 문구를 찾아 쪽 번호와 SRS ID를 함께 돌려준다.

    반환: [{"source": 짧은 이름, "page": 1-based 쪽, "srs": [ID...],
            "text": 주변 문구}]

    판정의 `note`에 `source`/`page`/`srs`를 적으면 근거가 추적된다.
    """
    regex = re.compile(pattern, flags)
    out = []
    for short, path in sorted(spec_paths(ctx).items()):
        for index, page_text in enumerate(extract(path), start=1):
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
                "srs": sorted(set(SRS_PATTERN.findall(page_text))),
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
