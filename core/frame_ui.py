# -*- coding: utf-8 -*-
"""Bellalun·VXvue 공용 실행 화면 (frame/FRAME.md 2.2·2.3, REQ-FRAME-001).

창은 `core/frame_ui.ps1`(Windows PowerShell 5.1의 WinForms)이 그린다. 이 모듈은 제품이 넘긴 값으로
화면 데이터(JSON)를 만들고, 창을 띄우고, 사람이 고른 결과를 돌려준다. 제품 이름·문구·판정은 넣지 않는다.

화면 순서(처음 쓰는 사람용):
    1. 시작(home) → 2. 준비 점검(inspect) → 3. 실행 동의(confirm) → 4. 진행(progress) → 5. 결과(result)

진행 기록(`events.jsonl`)은 한 줄에 JSON 하나다:
    {"time": "14:03:22", "tc_id": "TC_A", "index": 3, "total": 27, "message": "실행 시작"}
"""
from __future__ import annotations

from datetime import datetime
import json
import os
import subprocess
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frame_ui.ps1')

STEPS = ('시작', '준비 점검', '실행 동의', '진행', '결과')
SCREENS = {'home': 0, 'inspect': 1, 'confirm': 2, 'progress': 3, 'result': 4}

# 화면 색. 판정 색은 레포트 배지(core/report_layout.py)와 같다.
PALETTE = {
    'ok': '#167451', 'bad': '#a41926', 'warn': '#976a15', 'blocked': '#71419b',
    'info': '#334e68', 'auto': '#1e5aaa', 'text': '#182638',
}
VERDICT_LEVEL = {'PASS': 'ok', 'FAIL': 'bad', 'MANUAL': 'warn', 'SKIP': 'info', 'BLOCKED': 'blocked'}

INSPECT_COLUMNS = (
    {'key': 'status', 'label': '상태', 'width': 110},
    {'key': 'item', 'label': '항목', 'width': 190},
    {'key': 'result', 'label': '확인 결과', 'width': 250},
    {'key': 'fix', 'label': '해결 방법', 'width': 270},
)
RESULT_COLUMNS = (
    {'key': 'status', 'label': '판정', 'width': 100},
    {'key': 'item', 'label': 'TC', 'width': 230},
    {'key': 'reason', 'label': '확인할 내용', 'width': 490},
)


def _base(screen, product, heading, window_title=None):
    if screen not in SCREENS:
        raise ValueError('알 수 없는 화면: %s' % screen)
    return {'screen': screen, 'product': product, 'heading': heading,
            'window_title': window_title or '%s · %s' % (product, STEPS[SCREENS[screen]]),
            'steps': list(STEPS), 'step_index': SCREENS[screen], 'palette': dict(PALETTE), 'buttons': []}


def button(key, label, primary=False, enabled=True, open_path=None, target=False):
    """footer 버튼. `open_path`가 있으면 창을 닫지 않고 그 파일·폴더를 연다."""
    data = {'key': key, 'label': label, 'primary': bool(primary), 'enabled': bool(enabled), 'target': bool(target)}
    if open_path:
        data['open'] = str(open_path)
    return data


def home(product, heading, lines, buttons, last_result=None, tips=()):
    """1. 시작 화면. `lines`는 이 프로그램이 하는 일(세 줄 안팎), `last_result`는 {'text','level'}."""
    data = _base('home', product, heading)
    data.update(lines=list(lines), tips=list(tips), buttons=list(buttons),
                last_result=last_result, last_result_label='마지막 실행 결과')
    return data


def inspect(product, heading, headline, rows, targets, buttons, options=(), views=None, view_option=None,
            notes=()):
    """2. 준비 점검 화면.

    rows: [{'status','level','item','result','fix'}] — level은 PALETTE 키.
    targets: 실행 버튼 목록(button(..., target=True)). 막힌 대상은 enabled=False.
    options: [{'key','label','choices':[{'key','label'}],'value'}] — 모드·테마처럼 실행 전에 고르는 값.
    views: {선택값: {'headline','rows','blocked_targets'}} — view_option 값에 따라 표·실행 버튼을 바꾼다.
    notes: 결론 아래에 보일 짧은 안내 줄.
    """
    data = _base('inspect', product, heading)
    options = list(options)
    data.update(headline=headline, notes=list(notes), rows=list(rows), columns=list(INSPECT_COLUMNS), targets=list(targets),
                buttons=list(buttons), options=options, options_by_key={o['key']: o for o in options},
                views=views or {}, view_option=view_option,
                blocked_hint='꺼진 실행 버튼은 위 표의 "조치 필요" 항목을 해결하고 "다시 점검"을 누르면 켜집니다.',
                ready_hint='실행할 체크리스트를 고르면 실행 전 확인 화면이 열립니다. 아직 시험은 시작하지 않습니다.')
    return data


def confirm(product, heading, facts, checks, start_label, cancel_label='뒤로', details='', toggles=()):
    """3. 실행 동의 화면. 모든 확인 항목을 체크해야 시작 버튼이 켜진다.

    checks: 필수 확인 — 문자열 또는 {'key','label'}. 답의 `checked`에 체크한 key가 온다.
    details: 실행 계획처럼 긴 설명(읽기 전용 상자).
    toggles: 선택 항목 [{'key','label','value','note'}] — 답의 `toggles`에 {key: bool}로 온다.
    """
    data = _base('confirm', product, heading)
    items = [c if isinstance(c, dict) else {'key': c, 'label': c} for c in checks]
    data.update(facts=list(facts), checks=items, details=details or '', toggles=list(toggles),
                checks_label='모두 확인하고 체크해야 시작할 수 있습니다',
                buttons=[button('start', start_label, primary=True), button('cancel', cancel_label)])
    return data


def progress(product, heading, lines, events_path, process_id, stop_path=None,
             stop_label='안전한 지점에서 중단', minimized=False):
    """4. 진행 화면. 실행 프로세스가 끝나면 'finished'로 닫힌다."""
    data = _base('progress', product, heading)
    data.update(lines=list(lines), events_path=str(events_path) if events_path else '',
                process_id=int(process_id) if process_id else 0, stop_path=str(stop_path) if stop_path else '',
                stop_label=stop_label, stop_sent_label='중단 요청을 보냈습니다',
                now_format='단계 {0}/{1} · 지금: {2}', elapsed_format='경과 {0}', minimized=bool(minimized))
    return data


def result(product, heading, headline, lines, rows, buttons):
    """5. 결과 화면. rows: [{'status','level','item','reason'}] — 사람이 확인할 TC."""
    data = _base('result', product, heading)
    data.update(headline=headline, lines=list(lines), rows=list(rows), columns=list(RESULT_COLUMNS),
                rows_label='사람이 확인할 항목', buttons=list(buttons))
    return data


def outcome_headline(counts, aborted=False):
    """판정별 TC 수로 결과 화면 맨 위 문장과 색을 정한다."""
    total = sum(counts.get(k, 0) for k in VERDICT_LEVEL)
    if aborted:
        return {'text': '실행이 끝까지 진행되지 않았습니다. 아래 내용과 레포트를 확인하세요.', 'level': 'bad'}
    if total == 0:
        return {'text': '결과가 없습니다. 실행 기록을 확인하세요.', 'level': 'bad'}
    if counts.get('FAIL'):
        return {'text': '실패한 TC가 %d개 있습니다. 원인을 확인하세요.' % counts['FAIL'], 'level': 'bad'}
    review = counts.get('MANUAL', 0) + counts.get('BLOCKED', 0)
    if review:
        return {'text': '자동 판정은 끝났고 사람이 확인할 TC가 %d개 있습니다.' % review, 'level': 'warn'}
    return {'text': '모든 TC가 통과했습니다(%d개).' % counts.get('PASS', 0), 'level': 'ok'}


def append_event(path, tc_id, message, index=None, total=None):
    """진행 기록 한 줄을 더한다. 화면이 마지막 줄들을 읽어 보인다."""
    if not path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    line = {'time': datetime.now().strftime('%H:%M:%S'), 'tc_id': str(tc_id or ''), 'message': str(message or '')}
    if index is not None and total:
        line.update(index=int(index), total=int(total))
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(line, ensure_ascii=False) + '\n')


def show(data, snapshot=None, runner=subprocess.run):
    """창을 띄우고 사람이 고른 결과 dict를 준다. `snapshot`이 있으면 그린 화면을 PNG로 저장하고 바로 닫는다."""
    folder = tempfile.mkdtemp(prefix='frame_ui_')
    src, out = os.path.join(folder, 'in.json'), os.path.join(folder, 'out.json')
    try:
        with open(src, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
        command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-File', SCRIPT,
                   '-In', src, '-Out', out]
        if snapshot:
            command += ['-Snapshot', os.path.abspath(snapshot)]
        # 세 표준 핸들을 모두 정한다. 콘솔 없는 설치판의 잘못된 입력 핸들을 물려받지 않는다.
        proc = runner(command, stdin=subprocess.DEVNULL, capture_output=True, creationflags=0x08000000)
        if proc.returncode != 0 or not os.path.isfile(out):
            raise RuntimeError('화면을 띄우지 못했습니다(종료 %s): %s' % (
                proc.returncode, (proc.stderr or b'').decode('utf-8', 'replace').strip()[:300]))
        with open(out, encoding='utf-8-sig') as stream:
            return json.load(stream)
    finally:
        for path in (src, out):
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            os.rmdir(folder)
        except OSError:
            pass
