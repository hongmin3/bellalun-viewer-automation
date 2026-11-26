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


def row(field, expected, outcome, read='', reads=None, image=None, note=''):
    """대조표 한 줄. `outcome`은 `OUTCOMES` 중 하나이며 판정 코드가 정한 결과여야 한다.

    `reads`는 `(판독 방식, 값)` 목록이다. `image`는 칸 캡처 원본 경로다.
    표에는 글자 부분을 확대한 사본(`image`)을 보이고 원본은 `source_image`로 남긴다.
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
    return item


def pack(rows, context=()):
    """Step에 붙일 기록 `{"rows": [...], "context": [...]}`. `context`는 `(라벨, 넓은 캡처 경로)` 목록이다."""
    return {'rows': list(rows),
            'context': [{'label': str(label), 'image': str(image)} for label, image in context if image]}


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
    if not isinstance(evidence, dict) or set(evidence) - {'rows', 'context'}:
        return False
    rows, context = evidence.get('rows', []), evidence.get('context', [])
    if not isinstance(rows, list) or not isinstance(context, list) or not (rows or context):
        return False
    return (all(isinstance(item, dict) and isinstance(item.get('field'), str)
                and item.get('outcome') in OUTCOMES for item in rows)
            and all(isinstance(item, dict) for item in context))


def safe(build, *args, **kwargs):
    """`build(*args)`로 대조표 기록을 만든다. 실패하거나 형식이 틀리면 None이다(Step 판정은 그대로)."""
    try:
        evidence = build(*args, **kwargs)
    except Exception:                                   # noqa: BLE001 - 표시용 기록이 판정을 깨지 않게 한다
        return None
    return evidence if valid(evidence) else None
