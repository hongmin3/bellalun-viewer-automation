# -*- coding: utf-8 -*-
"""OCR 판독 대조표 기록(REQ-REPORT-002, `frame/FRAME.md` 2.9).

화면 글자를 OCR로 읽어 판정한 Step에 "칸 · 기대 텍스트 · 화면 캡처 · 자동화 판독 · 결과"를 붙인다.
리포트는 이 기록을 공용 표(`core/report_layout.render_reading_evidence`)로 그린다.

판정은 바꾸지 않는다. 판정 코드가 이미 정한 결과(일치·불일치·판독 불가·잘림)를 칸마다 옮겨 적기만 한다.
기록을 만들다 실패해도 Step 판정은 그대로 남아야 하므로 호출하는 쪽은 `safe()`로 감싼다.
"""

import os

#: 칸별 결과. 뜻과 색은 `core/report_layout.READING_OUTCOMES`가 정한다.
OUTCOMES = ('match', 'mismatch', 'unread', 'truncated')

#: 표시용 사본의 확대 배율, 글자 둘레 여백(px, 원래 배율), 사본의 최대 폭(px).
VIEW_SCALE = 3
VIEW_MARGIN = 6
VIEW_MAX_WIDTH = 1200
#: 판독 목록 한 칸에 보일 판독 원문 수와 한 원문의 최대 길이.
READS_LIMIT = 6
READ_TEXT_LIMIT = 160


def view_image(path):
    """칸 캡처에서 글자 부분만 남겨 확대한 표시용 사본(`*_view.png`)을 만든다. 못 만들면 원본 경로다.

    배경색(가장 많은 색)과 다른 픽셀을 모두 포함해 자르므로 글자를 잘라 내지 않는다. 원본 파일은 그대로 둔다.
    사본이 레포트에 넣을 수 있는 크기(`READING_IMAGE_MAX_BYTES`)를 넘으면 원본을 쓴다.
    """
    try:
        from PIL import Image, ImageChops
        from core.report_layout import READING_IMAGE_MAX_BYTES
        source = str(path)
        target = os.path.splitext(source)[0] + '_view.png'
        if not os.path.isfile(target):
            with Image.open(source) as opened:
                image = opened.convert('RGB')
            colors = image.getcolors(image.width * image.height) or []
            if len(colors) <= 1:
                return source
            background = max(colors)[1]
            box = ImageChops.difference(image, Image.new('RGB', image.size, background)).getbbox()
            if box is None:
                return source
            box = (max(box[0] - VIEW_MARGIN, 0), max(box[1] - VIEW_MARGIN, 0),
                   min(box[2] + VIEW_MARGIN, image.width), min(box[3] + VIEW_MARGIN, image.height))
            view = image.crop(box)
            scale = max(1, min(VIEW_SCALE, VIEW_MAX_WIDTH // max(view.width, 1)))
            view = view.resize((view.width * scale, view.height * scale), Image.NEAREST)
            view.save(target)
        return target if os.path.getsize(target) <= READING_IMAGE_MAX_BYTES else source
    except (ImportError, OSError, ValueError):
        return str(path)


def _one_line(value, limit=READ_TEXT_LIMIT):
    text = ' '.join(str('' if value is None else value).split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _segments(line, truth):
    """한 판독 줄에서 비교할 후보. 기대 텍스트에 머리말(`ID:`)이 없으면 머리말을 뗀 부분도 본다."""
    line = ' '.join(str(line or '').split())
    if not line or line.lower().startswith('<ocr err'):
        return []
    found = [line]
    if ':' in line and ':' not in truth:
        tail = line.split(':', 1)[1].strip()
        if tail:
            found.append(tail)
    # 한 줄에 여러 값이 있으면(필름 Header의 ID·생년월일) 기대 텍스트와 단어 수가 비슷한 구간도 본다.
    words, size = line.split(), max(1, len(truth.split()))
    for width in {max(1, size - 1), size, size + 1}:
        found.extend(' '.join(words[start:start + width]) for start in range(0, len(words) - width + 1))
    return list(dict.fromkeys(found))


def closest(truth, texts):
    """`[(판독 이름, 원문)]`에서 기대 텍스트와 가장 비슷한 한 구절 `(구절, 판독 이름)`. 없으면 `('', '')`.

    표시만 돕는다. 판정은 바꾸지 않으며 판독값을 기대값으로 고치지 않는다.
    """
    from difflib import SequenceMatcher
    want = ' '.join(str(truth).lower().split())
    best, best_score = ('', ''), -1.0
    for name, text in texts or ():
        for line in str(text or '').splitlines():
            for segment in _segments(line, truth):
                # 공백·기호도 길이에 넣어 비교해야 `35 N`에 `N` 한 글자보다 `99 N`이 가깝게 잡힌다.
                score = SequenceMatcher(None, want, segment.lower(), autojunk=False).ratio()
                if score > best_score:
                    best, best_score = (segment, str(name)), score
    return best


def compare(expected, read='', reads=None, label=''):
    """글자 차이 표시 기록 `{"expected", "read", "label"}`(`frame/FRAME.md` 2.9 3항).

    `expected`는 Bellalun이 확정한 진짜 텍스트(DB 값·사양 문구)다. `read`는 판정에 쓴 판독이고,
    없으면 `reads`(판독 방식별 원문)에서 기대값과 가장 비슷한 구절을 고른다.
    진짜 텍스트나 읽은 글자가 없으면 None이다(표는 기대 텍스트와 판독 기록을 그대로 보인다).
    """
    truth = ' '.join(str('' if expected is None else expected).split())
    if not truth:
        return None
    segment, source = ('', '')
    if str(read or '').strip():
        segment, _ = closest(truth, [('판정', read)])
        source = '판정에 쓴 판독'
    if not segment:
        segment, name = closest(truth, reads)
        source = ('가장 비슷한 판독: %s' % name) if name else ''
    if not segment:
        return None
    note = ' · '.join(part for part in (str(label or ''), source) if part)
    return {'expected': truth, 'read': _one_line(segment), 'label': note}


def row(field, expected, outcome, read='', reads=None, image=None, note='', compare=None):
    """대조표 한 줄. `outcome`은 `OUTCOMES` 중 하나이며 판정 코드가 정한 결과여야 한다.

    `reads`는 `(판독 방식, 값)` 목록이다. `image`는 칸 캡처 원본 경로다.
    표에는 글자 부분을 확대한 사본(`image`)을 보이고 원본은 `source_image`로 남긴다.
    `compare`는 `compare()`가 만든 글자 차이 표시 기록이다(선택).
    """
    if outcome not in OUTCOMES:
        raise ValueError('알 수 없는 판독 결과: %r' % (outcome,))
    item = {'field': str(field), 'expected': '' if expected is None else str(expected),
            'read': _one_line(read), 'outcome': outcome,
            'reads': [[str(label), _one_line(value)] for label, value in (reads or [])]}
    if image:
        item['source_image'] = str(image)
        item['image'] = view_image(image) if os.path.isfile(str(image)) else str(image)
    if note:
        item['note'] = str(note)
    if compare:
        item['compare'] = {key: str(compare.get(key) or '') for key in ('expected', 'read', 'label')}
    return item


#: 대조표 제목(공용 `render_reading_evidence`의 기본 제목과 같다).
TITLE = '판독 대조표 · 기대 텍스트와 화면 캡처'


def pack(rows, context=(), title=None):
    """Step에 붙일 기록 `{"rows": [...], "context": [...]}`. `context`는 `(라벨, 넓은 캡처 경로)` 목록이다.

    `title`은 OCR 글자 대조가 아닌 근거(픽셀 비교, 화면 선택용 판독)에 쓴다. 없으면 기본 제목이다.
    """
    evidence = {'rows': list(rows),
                'context': [{'label': str(label), 'image': str(image)} for label, image in context if image]}
    if title:
        evidence['title'] = str(title)
    return evidence


def ocr_reads(texts, limit=READS_LIMIT):
    """`{판독 이름: 원문}`에서 비어 있지 않은 서로 다른 원문을 `[이름, 원문]` 목록으로 만든다."""
    out, seen = [], set()
    for name, text in (texts or {}).items():
        line = _one_line(text)
        if not line or line.lower().startswith('<ocr err') or line in seen:
            continue
        seen.add(line)
        out.append([str(name), line])
        if len(out) >= limit:
            break
    return out


def valid(evidence):
    """Step·저장점에서 되살린 기록이 이 형식인지 본다(형식이 다르면 버린다)."""
    if not isinstance(evidence, dict) or set(evidence) - {'rows', 'context', 'title'}:
        return False
    if not isinstance(evidence.get('title', ''), str):
        return False
    rows, context = evidence.get('rows', []), evidence.get('context', [])
    if not isinstance(rows, list) or not isinstance(context, list) or not (rows or context):
        return False
    return (all(isinstance(item, dict) and isinstance(item.get('field'), str)
                and item.get('outcome') in OUTCOMES and _valid_compare(item.get('compare'))
                for item in rows)
            and all(isinstance(item, dict) for item in context))


def _valid_compare(value):
    """선택 필드 `compare`가 없거나 `{"expected", "read", "label"}` 글자 기록인지 본다."""
    return value is None or (isinstance(value, dict) and set(value) <= {'expected', 'read', 'label'}
                             and all(isinstance(text, str) for text in value.values()))


def safe(build, *args, **kwargs):
    """`build(*args)`로 대조표 기록을 만든다. 실패하거나 형식이 틀리면 None이다(Step 판정은 그대로)."""
    try:
        evidence = build(*args, **kwargs)
    except Exception:                                   # noqa: BLE001 - 표시용 기록이 판정을 깨지 않게 한다
        return None
    return evidence if valid(evidence) else None
