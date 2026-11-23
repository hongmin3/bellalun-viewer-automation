# -*- coding: utf-8 -*-
"""사람이 여는 기본 실행 흐름을 VXvue와 같은 공용 화면으로 보인다 (REQ-FRAME-002, frame/FRAME.md 2.2).

1. 시작 → 2. 준비 점검 → 3. 실행 동의 → 4. 진행 → 5. 결과.
시험 실행·동의 검증·실행 기록은 기존 `gui.RunController`·`runplan`·`runs`를 그대로 쓴다.
PC별 설정·수동 검토·공유 ZIP은 기존 창을 연다. 무인 실행(`--unattended`)은 기존 Tk 화면을 쓴다.
"""
from __future__ import annotations

import os
from pathlib import Path

from core import frame_ui as ui

TARGETS = (('run-regression', '기본기능 체크리스트'), ('run-winupdate', 'Windows Update 체크리스트'))
TARGET_LABEL = dict(TARGETS)
STATUS_LABEL = {'completed': '자동 실행 완료', 'stopped': '중단', 'abnormal': '비정상 종료',
                'uac_cancelled': 'UAC 취소 — 시험 시작 안 함', 'running': '실행 중'}
HOME_LINES = (
    'Bellalun Viewer의 QA 체크리스트를 실제 화면에서 자동으로 수행합니다.',
    '각 TC의 판정(PASS·FAIL·MANUAL)과 근거 화면을 레포트로 남깁니다.',
    '시험 중에는 마우스·키보드를 쓰지 마세요. 끝나면 결과 화면이 열립니다.',
)


def product_label():
    from . import __version__
    return f'BellalunAuto {__version__}'


def _verdict_text(verdicts):
    from .completion_notice import verdict_totals
    return verdict_totals(verdicts or {})


def last_result(record):
    """시작 화면의 마지막 실행 결과 한 줄. 기록이 없으면 None."""
    if record is None:
        return None
    data = record.data
    verdicts = {k: v for k, v in (data.get('verdicts') or {}).items() if k in ui.VERDICT_LEVEL}
    level = ui.outcome_headline(verdicts, aborted=data.get('status') != 'completed')['level']
    target = TARGET_LABEL.get(data.get('action'), data.get('action', ''))
    text = (f"{data.get('run_id', '')} · {target} · {STATUS_LABEL.get(data.get('status'), data.get('status'))}"
            f" · {_verdict_text(data.get('verdicts'))}")
    return {'text': text, 'level': level}


def home_data(record=None, first_run=False):
    tips = ['처음이면 "준비 점검 시작"을 누르세요. 시험 전에 고칠 것을 표로 알려 주고, 아직 시험은 시작하지 않습니다.']
    if first_run:
        tips.insert(0, '이 PC의 설정을 자동으로 찾아 저장했습니다. 준비 점검에서 "조치 필요" 항목만 채우면 됩니다.')
    return ui.home(product_label(), '무엇을 할까요?', HOME_LINES,
                   [ui.button('inspect', '준비 점검 시작', primary=True), ui.button('settings', 'PC별 설정'),
                    ui.button('results', '결과 폴더 열기'), ui.button('review', '수동 검토'),
                    ui.button('share', '공유 ZIP'), ui.button('close', '닫기')],
                   last_result=last_result(record), tips=tips)


# PC별 설정 칸 이름 → 같은 내용을 보는 준비 점검 항목 이름(app.diagnostics). 한 줄로 합칠 때 쓴다.
SAME_CHECK = {'승인 Baseline 폴더': '승인 Baseline', '사양 / 매뉴얼 폴더': '근거 문서'}


def inspection_rows(items, config_errors=()):
    """점검 표의 행. 비어 있는 PC별 설정과 같은 이름의 점검 실패는 한 줄로 합친다."""
    rows, merged = [], set()
    for error in config_errors:
        field, _, detail = str(error).partition(':')
        field = field.strip() if detail else 'PC별 설정'
        merged.add(field)
        merged.add(SAME_CHECK.get(field, field))
        rows.append({'status': '조치 필요', 'level': 'bad', 'item': field,
                     'result': (detail.strip() or str(error)) if detail else str(error),
                     'fix': '"PC별 설정"에서 값을 입력하고 "다시 점검"을 누르세요.'})
    for item in items:
        if not item.get('ok') and not item.get('notice') and item.get('name') in merged:
            continue
        if item.get('notice'):
            status, level = '안내', 'info'
        elif item.get('ok'):
            status, level = '정상', 'ok'
        else:
            status, level = '조치 필요', 'bad'
        rows.append({'status': status, 'level': level, 'item': item.get('name', ''),
                     'result': item.get('detail', ''), 'fix': '' if item.get('ok') else item.get('fix', '')})
    # 고칠 것을 먼저 보인다. 같은 상태 안에서는 점검 순서를 지킨다.
    order = {'bad': 0, 'info': 1, 'ok': 2}
    return sorted(rows, key=lambda row: order.get(row['level'], 3))


def inspect_data(items, config_errors=()):
    rows = inspection_rows(items, config_errors)
    problems = sum(1 for row in rows if row['level'] == 'bad')
    if config_errors:
        headline = {'text': f'시작 전에 해결할 문제 {problems}개 — PC별 설정을 먼저 채우세요.', 'level': 'bad'}
    elif problems:
        headline = {'text': f'확인할 문제 {problems}개 — 해결하지 않으면 시험이 환경 점검에서 멈출 수 있습니다.',
                    'level': 'warn'}
    else:
        headline = {'text': '시작할 수 있습니다. 실행할 체크리스트를 고르세요.', 'level': 'ok'}
    blocked = bool(config_errors)
    targets = [ui.button(key, label, primary=(index == 0), enabled=not blocked, target=True)
               for index, (key, label) in enumerate(TARGETS)]
    return ui.inspect(product_label(), '준비 점검', headline, rows, targets,
                      [ui.button('reinspect', '다시 점검'), ui.button('settings', 'PC별 설정'),
                       ui.button('home', '처음으로')])


def confirm_data(plan):
    from core.run_preparation import preparation_items
    from .runplan import format_plan
    action = plan['action']
    checks = [{'key': item['key'], 'label': item['label']} for item in preparation_items(action)]
    checks.append({'key': 'agree', 'label': '위 변경에 동의합니다'})
    facts = [f"실행할 체크리스트: {TARGET_LABEL.get(action, action)}",
             '시험 동안 Bellalun Viewer와 관련 서비스가 여러 번 다시 시작됩니다. 마우스·키보드를 쓰지 마세요.',
             'UAC 권한 승인은 아래 데이터 변경 동의를 대신하지 않습니다.']
    restore = {'key': 'restore_after', 'value': True,
               'label': '시험 종료 후 DB·변경 대상 파일을 실행 전 상태로 복원 (이번 실행만)',
               'note': '복원은 매 실행 기본 선택이며 이번 실행에서 해제할 수 있습니다. 원상복원을 해제하면 '
                       'DB의 영상 참조를 보존하기 위해 생성 이미지 자동 삭제도 하지 않습니다.'}
    return ui.confirm(product_label(), '실행 전 확인 — 데이터 변경 동의', facts, checks, '동의하고 시작',
                      details=format_plan(plan), toggles=[restore])


def apply_consent(plan, answer):
    """동의 화면의 답을 실행 계획에 옮긴다. 모든 필수 확인이 없으면 ValueError."""
    from core.run_preparation import preparation_complete, validate_preparation
    checked = [key for key in answer.get('checked') or [] if key != 'agree']
    if 'agree' not in (answer.get('checked') or []) or not preparation_complete(plan['action'], checked):
        raise ValueError('모든 확인 항목을 체크해야 시작할 수 있습니다.')
    validate_preparation(plan['action'], checked)
    plan['preparation_checked'] = checked
    plan['restore_after'] = bool((answer.get('toggles') or {}).get('restore_after', True))
    return plan


def progress_data(record, process_id, stop_path):
    events = (Path(record.path).parent / 'events.jsonl') if record else None
    return ui.progress(product_label(), '시험 진행 중',
                       ['끝나면 결과 화면이 자동으로 열립니다. 이 창을 닫아도 시험은 계속됩니다.',
                        '중단하려면 아래 버튼을 누르세요. 진행 중인 TC를 정리한 뒤 멈춥니다.'],
                       events, process_id, stop_path=stop_path)


def _first_reason(row):
    for check in row.get('checks') or []:
        if check.get('status') != 'PASS':
            text = check.get('note') or check.get('actual') or check.get('title') or ''
            return str(text).strip().splitlines()[0][:200] if str(text).strip() else ''
    return ''


def result_data(record, workspace):
    from .completion_notice import primary_report
    data = record.data
    verdicts = {k: v for k, v in (data.get('verdicts') or {}).items() if k in ui.VERDICT_LEVEL}
    status = data.get('status')
    if status == 'uac_cancelled':
        headline = {'text': '시험을 시작하지 않았습니다. UAC 권한 요청을 취소했습니다.', 'level': 'info'}
    elif status == 'stopped':
        headline = {'text': '요청에 따라 시험을 중단했습니다. 끝나지 않은 TC는 레포트에 미수행으로 남습니다.', 'level': 'warn'}
    else:
        headline = ui.outcome_headline(verdicts, aborted=status != 'completed')
    rows = [{'status': row.get('verdict', ''), 'level': ui.VERDICT_LEVEL.get(row.get('verdict'), 'info'),
             'item': f"{row.get('tc_id', '')} {row.get('title', '')}".strip(), 'reason': _first_reason(row)}
            for row in record.result_rows() if row.get('verdict') != 'PASS']
    lines = [f"실행 번호 {data.get('run_id', '')} · {TARGET_LABEL.get(data.get('action'), '')} · "
             f"{STATUS_LABEL.get(status, status)}",
             f"판정: {_verdict_text(data.get('verdicts'))}",
             str(data.get('summary') or ''),
             f"다음 할 일: {data.get('next_action', '')}"]
    report = primary_report(data.get('reports'))
    buttons = []
    if report:
        buttons.append(ui.button('report', '레포트 열기', primary=True, open_path=report))
    buttons += [ui.button('folder', '결과 폴더 열기', open_path=Path(workspace) / 'Reports'),
                ui.button('review', '수동 검토'), ui.button('share', '공유 ZIP'), ui.button('home', '처음으로')]
    return ui.result(product_label(), '결과', headline, [line for line in lines if line.strip()], rows, buttons)


def _with_tk(callback):
    """기존 Tk 보조 창(설정·검토·공유)을 연다. 부모 창은 투명하게 두어 보조 창이 가려지지 않게 한다."""
    import tkinter as tk
    root = tk.Tk()
    root.geometry('1x1+0+0')
    root.attributes('-alpha', 0.0)
    try:
        value = callback(root)
        for child in list(root.winfo_children()):
            if isinstance(child, tk.Toplevel) and child.winfo_exists():
                root.wait_window(child)
        return value
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def launch(layout, workspace_chosen=False, show=ui.show):
    """공용 화면 흐름. 호출만으로 제품 시험이나 DB 복원을 시작하지 않는다."""
    from . import gui
    from .app import diagnostics
    from .runs import latest_run

    # 데이터 위치를 묻지 않는다. 설치판은 설치 폴더, 소스 실행은 C:\BellalunAuto를 쓴다(REQ-FRAME-003).
    first_run = not Path(layout.config_path).exists()
    try:
        config = gui.prepare_first_run(layout) if first_run else gui.load_gui_config(layout)
    except (OSError, ValueError) as error:
        text = gui.workspace_error_text(layout.workspace, error) if first_run else gui.config_error_text(layout, error)
        show(ui.result(product_label(), '시작할 수 없습니다', {'text': text, 'level': 'bad'}, [], [],
                       [ui.button('close', '닫기', primary=True)]))
        return 1
    controller = gui.RunController(layout, config)
    screen = 'inspect' if first_run else 'home'
    notice = None

    def notify(title, text, level='bad'):
        show(ui.result(product_label(), title, {'text': text, 'level': level}, [], [],
                       [ui.button('back', '확인', primary=True)]))

    def secondary(action, record=None):
        if action == 'settings':
            updated = _with_tk(lambda root: gui._settings_dialog(root, layout, controller.config))
            if updated is not None:
                controller.config = updated
        elif action in ('review', 'share'):
            record = record or controller.record or latest_run(layout.workspace)
            if record is None:
                notify('실행 기록 없음', '저장된 실행 기록이 없습니다. 먼저 체크리스트를 실행하세요.', 'info')
                return
            from .qa_dialogs import review_run, share_run
            _with_tk(lambda root: (review_run if action == 'review' else share_run)(root, record))
        elif action == 'results':
            folder = Path(layout.workspace) / 'Reports'
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))

    while True:
        if screen == 'home':
            record = latest_run(layout.workspace)
            answer = show(home_data(record, first_run=False))
            if record is not None and record.data.get('result_seen') is False:
                try:
                    record.mark_result_seen()
                except (OSError, ValueError):
                    pass
            action = answer.get('action', 'close')
            if action == 'close':
                return 0
            if action == 'inspect':
                screen = 'inspect'
            else:
                secondary(action)
            continue
        if screen == 'inspect':
            items = diagnostics(layout)
            data = inspect_data(items, gui.validate_config(controller.config))
            if first_run:
                data['heading'] = '준비 점검 — 이 PC의 설정을 자동으로 찾아 저장했습니다'
                first_run = False
            answer = show(data)
            action = answer.get('action', 'close')
            if action == 'close':
                return 0
            if action == 'home':
                screen = 'home'
            elif action in TARGET_LABEL:
                screen = 'confirm'
                notice = action
            elif action != 'reinspect':
                secondary(action)
            continue
        if screen == 'confirm':
            from .runplan import build_plan
            try:
                plan = build_plan(layout, controller.config, notice)
            except (OSError, ValueError, RuntimeError) as error:
                notify('실행 계획을 만들지 못했습니다', gui.secret_redactor(controller.config)(str(error)))
                screen = 'inspect'
                continue
            answer = show(confirm_data(plan))
            if answer.get('action') != 'start':
                screen = 'inspect'
                continue
            try:
                apply_consent(plan, answer)
                controller.start(notice, consent=True, plan=plan)
            except (OSError, ValueError, RuntimeError) as error:
                notify('시험을 시작하지 못했습니다', gui.secret_redactor(controller.config)(str(error)))
                screen = 'inspect'
                continue
            if controller.record:
                ui.append_event(Path(controller.record.path).parent / 'events.jsonl', '',
                                f'{TARGET_LABEL[notice]} 시작')
            screen = 'progress'
            continue
        if screen == 'progress':
            # 진행 창을 닫아도 시험은 계속된다. 끝날 때까지 다시 연다.
            while controller.running:
                show(progress_data(controller.record, controller.process.pid, controller.stop_path))
            if controller.reader is not None:
                controller.reader.join(timeout=30)
            record = controller.record
            if record is None:
                screen = 'home'
                continue
            try:
                if controller.stop_path is not None and Path(controller.stop_path).exists():
                    record.request_stop()
                record.finish(controller.process.returncode)
                record.annotate(launch_mode={'mode': 'human', 'signal': None})
            except (OSError, ValueError) as error:
                notify('실행 기록 저장 실패', f'{type(error).__name__} · 작업 폴더 권한과 보고서를 확인하세요.')
            screen = 'result'
            continue
        if screen == 'result':
            record = controller.record or latest_run(layout.workspace)
            if record is None:
                screen = 'home'
                continue
            answer = show(result_data(record, layout.workspace))
            try:
                record.mark_result_seen()
            except (OSError, ValueError):
                pass
            action = answer.get('action', 'close')
            if action == 'close':
                return 0
            if action == 'home':
                screen = 'home'
            else:
                secondary(action, record)
