"""실행 전 동의·준비 해결·사람 검토·선택 공유 화면."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


def diagnostic_state(row):
    if row.get('warning'):
        return 'WARN'
    return '안내' if row.get('notice') else 'OK' if row['ok'] else 'FAIL'


def _evidence_folder(workspace, folder):
    base = Path(workspace).resolve() / 'Evidence'
    target = Path(folder).resolve()
    if not target.is_relative_to(base) or not target.is_dir():
        raise ValueError('선택한 작업 폴더의 Evidence 안에서 증거 폴더를 선택하세요.')
    return target


def open_ocr_evidence(workspace, row):
    """파일에서 가져온 경로 대신 검증된 로컬 증거 폴더만 연다."""
    if not row or not row.get('evidence_dir'):
        raise ValueError('최근 OCR 선택 실패 행을 먼저 선택하세요.')
    os.startfile(str(_evidence_folder(workspace, row['evidence_dir'])))


def recent_ocr_failure(workspace):
    """OCR 실패 메타데이터만 읽는다. 인식 원문·환자 값은 화면에 옮기지 않는다."""
    base = Path(workspace) / 'Evidence'
    if not base.is_dir() or base.is_symlink():
        return None
    candidates = []
    for path in base.rglob('selection.json'):
        try:
            # Resolve before opening so a link cannot escape local Evidence.
            if not path.resolve().is_relative_to(base.resolve()) or path.stat().st_size > 1024 * 1024:
                continue
            candidates.append((path.stat().st_mtime_ns, path))
        except OSError:
            continue
    reasons = {'unreadable': '읽기 실패', 'ambiguous': '후보 중복', 'capture-failed': '화면 캡처 실패'}
    safe_labels = {'HVL', 'Top', 'Bottom', 'Left', 'Right', 'Center', 'None', 'Header', 'Footer'}
    for _, path in sorted(candidates, key=lambda item: item[0], reverse=True):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('reason') not in reasons:
                continue
            attempts = data.get('attempts')
            if type(attempts) is not int or not 0 <= attempts <= 100:
                continue
            wanted = data.get('wanted')
            wanted = wanted if isinstance(wanted, str) and wanted in safe_labels else '비공개 항목(증거에서 확인)'
            folder = _evidence_folder(workspace, path.parent)
        except (OSError, ValueError, TypeError):
            continue
        return {'name': '최근 OCR 선택 실패', 'ok': True, 'warning': True,
                'detail': f"대상: {wanted} · 원인: {reasons[data['reason']]} · 재판독 {attempts}회 · 증거: {folder}",
                'fix': '증거 폴더의 캡처와 selection.json을 확인하세요. 화면 배율 100%·해상도 1920×1080, '
                       '가림/중복 항목, OCR 환경 지문을 비교한 뒤 해당 시험만 다시 실행하세요. '
                       '이전 실패 기록은 자동 삭제하지 않습니다.',
                'evidence_dir': str(folder)}
    return None


def remediation_target(name):
    if any(word in name for word in ('화면', '해상도', '배율', 'DPI')):
        return 'ms-settings:display'
    if 'SQL' in name or '서비스' in name:
        return 'services.msc'
    return 'config'


def diagnostics_error_report(error, workspace):
    """준비 점검 예외를 오류 창 문구로 만들고 작업/Log에 남긴다.

    예외 문장·인자·설정 값은 계정이나 경로를 담을 수 있어 남기지 않는다. 종류, Windows 오류 번호,
    시스템 설명, 호출 위치(파일·함수·줄)만 쓴다.
    """
    import traceback
    from datetime import datetime
    frames = traceback.extract_tb(error.__traceback__)
    calls = [f"{'/'.join(Path(f.filename).parts[-2:])}:{f.lineno} {f.name}" for f in frames]
    code = getattr(error, 'winerror', None) or getattr(error, 'errno', None)
    reason = getattr(error, 'strerror', None) if isinstance(error, OSError) else None
    cause = ' · '.join(str(part) for part in (type(error).__name__, code and f'코드 {code}', reason) if part)
    location = calls[-1] if calls else '알 수 없음'
    log_path = Path(workspace) / 'Log' / 'diagnostics-error.log'
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('a', encoding='utf-8') as log:
            log.write(f"[{datetime.now().isoformat(timespec='seconds')}] {cause}\n")
            log.writelines(f'  {call}\n' for call in calls)
        saved = f'기록 위치: {log_path}'
    except OSError as log_error:
        failure = ' · '.join(str(part) for part in (type(log_error).__name__, log_error.errno and f'코드 {log_error.errno}') if part)
        saved = f'기록을 남기지 못했습니다({failure}). 작업 폴더 쓰기 권한을 확인하세요.'
    return (f'원인: {cause}\n실패 위치: {location}\n{saved}\n\n'
            '해결 방법: 프로그램을 다시 열어 [준비 점검]을 누르세요. 같은 오류가 반복되면 명령 창에서 '
            '`BellalunAuto.exe selfcheck`를 실행하고, 위 기록 파일과 함께 담당자에게 전달하세요.')


def confirm_plan(root, plan, *, layout=None, open_config=None):
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    from .runplan import format_plan
    from core.run_preparation import preparation_items, preparation_complete, validate_preparation
    dialog = tk.Toplevel(root)
    dialog.title('실행 전 확인 — 데이터 변경 동의')
    dialog.geometry('1000x900' if layout is not None else '850x740')
    # 매번 복원을 기본 선택한다. 이전 선택·동의는 승인으로 재사용하지 않는다.
    plan['restore_after'] = True
    view = scrolledtext.ScrolledText(dialog, wrap='word', height=10, font=('맑은 고딕', 10))
    view.pack(fill='both', expand=True, padx=12, pady=12)
    view.insert('end', format_plan(plan))
    view.configure(state='disabled')
    if layout is not None:
        _diagnostics_panel(dialog, layout, open_config or (lambda: None), height=5)
    restore = tk.BooleanVar(value=True)
    agreed = tk.BooleanVar(value=False)
    accepted = [False]
    ttk.Label(dialog, text='UAC 권한 승인은 아래 데이터 변경 동의를 대신하지 않습니다.').pack(pady=4)
    start = ttk.Button(dialog, text='동의하고 시작', state='disabled')
    checks = {}

    def checked():
        return [key for key, value in checks.items() if value.get()]

    def refresh():
        ready = agreed.get() and preparation_complete(plan['action'], checked())
        start.configure(state='normal' if ready else 'disabled')

    for item in preparation_items(plan['action']):
        value = tk.BooleanVar(value=False)
        checks[item['key']] = value
        ttk.Checkbutton(dialog, text=item['label'], variable=value, command=refresh).pack(anchor='w', padx=12)
    ttk.Checkbutton(dialog, text='시험 종료 후 DB·변경 대상 파일을 실행 전 상태로 복원 (이번 실행만)',
                    variable=restore).pack(anchor='w', padx=12, pady=6)
    ttk.Label(dialog, text='복원은 매 실행 기본 선택이며 이번 실행에서 해제할 수 있습니다. '
                          '공유 사본 검증·파일과 DB 원상복원·서비스 복구·정상 완주를 확인한 뒤 '
                          '이번 실행에서 생성되어 격리된 Image 파일만 자동 삭제합니다. '
                          '원상복원을 해제하면 DB의 영상 참조를 보존하기 위해 생성 이미지 자동 삭제도 하지 않습니다. '
                          '시험 전 사본·공유 보존 자료·기존 백업은 유지합니다.',
              wraplength=940).pack(anchor='w', padx=12)
    ttk.Checkbutton(dialog, text='위 변경에 동의합니다', variable=agreed,
                    command=refresh).pack(pady=6)

    def accept():
        if agreed.get() and preparation_complete(plan['action'], checked()):
            try:
                validate_preparation(plan['action'], checked())
            except ValueError as error:
                from tkinter import messagebox
                messagebox.showerror('준비 확인 필요', str(error), parent=dialog)
                return
            plan['preparation_checked'] = checked()
            plan['restore_after'] = restore.get()
            accepted[0] = True
            dialog.destroy()
    start.configure(command=accept)
    start.pack(pady=8)
    ttk.Button(dialog, text='취소', command=dialog.destroy).pack(pady=4)
    dialog.transient(root)
    dialog.grab_set()
    root.wait_window(dialog)
    return accepted[0]


def _diagnostics_panel(parent, layout, open_config, *, height=14):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from .app import diagnostics
    dialog = ttk.Frame(parent)
    dialog.pack(fill='both', expand=True)
    tree = ttk.Treeview(dialog, columns=('state', 'name', 'detail'), show='headings', height=height)
    for key, label, width in (('state', '결과', 65), ('name', '항목', 200), ('detail', '현재 상태', 620)):
        tree.heading(key, text=label)
        tree.column(key, width=width)
    tree.pack(fill='both', expand=True, padx=10, pady=10)
    explanation = tk.StringVar(value='행을 선택하면 해결 방법을 표시합니다. 실행 차단 기준은 기존과 같습니다.')
    ttk.Label(dialog, textvariable=explanation, wraplength=900).pack(fill='x', padx=12, pady=10)
    rows = {}

    def selected():
        keys = tree.selection()
        return rows.get(keys[0]) if keys else None

    def select(_=None):
        row = selected()
        if row:
            explanation.set(f"{row['name']}: {row['detail']}\n해결 방법: {row['fix']}")

    def refresh():
        try:
            result = diagnostics(layout)
        except (OSError, ValueError) as error:
            messagebox.showerror('점검 실패', diagnostics_error_report(error, layout.workspace), parent=dialog)
            return
        tree.delete(*tree.get_children())
        rows.clear()
        for row in result:
            key = tree.insert('', 'end', values=(diagnostic_state(row), row['name'], row['detail']))
            rows[key] = row
        failures = [key for key, row in rows.items() if not row['ok'] and not row.get('notice')]
        if not failures:
            failures = [key for key, row in rows.items() if row.get('warning')]
        if failures:
            tree.selection_set(failures[0])
            select()
        else:
            explanation.set('기본 설치·연결 점검을 통과했습니다. 보존 저장소 연결·용량 예산은 시험 준비에서 별도로 확인합니다. '
                            '시험 시작 시 환경 gate가 다시 적용됩니다.')

    def resolve():
        row = selected()
        if not row:
            return
        target = remediation_target(row['name'])
        try:
            if target == 'config':
                open_config()
            elif target == 'services.msc':
                subprocess.Popen(['mmc.exe', 'services.msc'])
            else:
                os.startfile(target)
        except OSError:
            messagebox.showerror('설정 열기 실패', 'Windows 설정 또는 PC별 설정에서 직접 확인하세요.', parent=dialog)
    tree.bind('<<TreeviewSelect>>', select)
    def open_evidence():
        try:
            open_ocr_evidence(layout.workspace, selected())
        except (OSError, ValueError):
            messagebox.showerror('증거 폴더 열기', '최근 OCR 선택 실패 행을 선택하세요. '
                                 '증거 폴더가 없으면 해당 시험을 다시 실행한 뒤 점검하세요.', parent=dialog)

    actions = ttk.Frame(dialog)
    actions.pack(fill='x')
    ttk.Button(actions, text='선택 항목 설정 화면 열기', command=resolve).pack(side='left', padx=12, pady=10)
    ttk.Button(actions, text='OCR 실패 증거 폴더 열기', command=open_evidence).pack(side='left', padx=6)
    ttk.Button(actions, text='다시 점검', command=refresh).pack(side='left', padx=12)
    refresh()
    return dialog


def show_diagnostics(root, layout, open_config):
    import tkinter as tk
    from tkinter import ttk
    dialog = tk.Toplevel(root)
    dialog.title('준비 점검 — 실패 해결 후 다시 점검')
    dialog.geometry('940x600')
    _diagnostics_panel(dialog, layout, open_config)
    ttk.Button(dialog, text='닫기', command=dialog.destroy).pack(anchor='e', padx=12, pady=10)
    return dialog


def review_run(root, record):
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
    dialog = tk.Toplevel(root)
    dialog.title(f"수동 검토 · {record.data['run_id']}")
    dialog.geometry('900x670')
    ttk.Label(dialog, text=f"자동 실행: {record.data['status']} · 검토: {record.data['review_status']}").pack(pady=8)
    reviewer = tk.StringVar()
    top = ttk.Frame(dialog)
    top.pack(fill='x', padx=12)
    ttk.Label(top, text='검토자 이름').pack(side='left')
    ttk.Entry(top, textvariable=reviewer, width=28).pack(side='left', padx=8)
    targets = record.review_targets()
    selected = tk.StringVar(value=targets[0] if targets else '')
    choice = ttk.Combobox(dialog, values=targets, textvariable=selected, state='readonly', width=65)
    choice.pack(pady=10)
    verdict = tk.StringVar()
    ttk.Combobox(dialog, values=('확인 완료', '결함 등록', '재시험 필요'), textvariable=verdict, state='readonly').pack()
    ttk.Label(dialog, text='의견 / 결함 번호').pack(pady=8)
    comment = scrolledtext.ScrolledText(dialog, height=12, wrap='word')
    comment.pack(fill='both', expand=True, padx=12)
    issue = tk.StringVar()
    ttk.Entry(dialog, textvariable=issue, width=65).pack(pady=8)
    entries = {}
    path = record.path.with_name('review.json')
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            reviewer.set(saved.get('reviewer', ''))
            entries.update(saved.get('entries', {}))
        except (OSError, ValueError):
            messagebox.showerror('검토 읽기 실패', '기존 review.json을 보존합니다. 파일을 먼저 확인하세요.', parent=dialog)
            dialog.destroy()
            return
    current = [selected.get()]

    def keep():
        if current[0] and verdict.get():
            entries[current[0]] = {'result': verdict.get(), 'comment': comment.get('1.0', 'end').strip(), 'issue': issue.get().strip()}

    def load(_=None):
        keep()
        current[0] = selected.get()
        entry = entries.get(current[0], {})
        verdict.set(entry.get('result', ''))
        comment.delete('1.0', 'end')
        comment.insert('end', entry.get('comment', ''))
        issue.set(entry.get('issue', ''))

    def save(complete):
        keep()
        try:
            record.save_review(reviewer.get(), entries, complete=complete)
        except (OSError, ValueError) as error:
            messagebox.showerror('검토 기록', str(error), parent=dialog)
            return
        messagebox.showinfo('검토 기록', record.data['review_status'], parent=dialog)
    choice.bind('<<ComboboxSelected>>', load)
    load()
    ttk.Label(dialog, text='자동 판정과 원본 보고서는 바꾸지 않습니다. 모든 PASS 아닌 TC를 검토해야 완료할 수 있습니다.').pack(pady=8)
    ttk.Button(dialog, text='검토 중 저장', command=lambda: save(False)).pack(side='left', padx=12, pady=12)
    ttk.Button(dialog, text='검수 완료', command=lambda: save(True)).pack(side='left', padx=12)


def share_run(root, record):
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from .share import create_package, verify_package
    dialog = tk.Toplevel(root)
    dialog.title(f"공유 범위 선택 · {record.data['run_id']}")
    dialog.geometry('620x310')
    ttk.Label(dialog, text='보고서·검토 기록을 공유합니다. 설정·비밀번호는 제외합니다.\n추가 자료는 시험 환자 정보를 포함할 수 있습니다.', wraplength=580).pack(pady=14)
    flags = [tk.BooleanVar(value=False) for _ in range(3)]
    for label, value in zip(('증거 스크린샷 (시험 환자 정보 포함)', 'DICOM (시험 환자 정보 포함)', 'Viewer 로그 구간'), flags):
        ttk.Checkbutton(dialog, text=label, variable=value).pack(anchor='w', padx=24, pady=6)

    def create():
        output = filedialog.asksaveasfilename(parent=dialog, defaultextension='.zip', initialfile=record.data['run_id'] + '.zip')
        if not output:
            return
        try:
            review = record.path.with_name('review.json')
            create_package(output, run_id=record.data['run_id'], reports=record.data['reports'],
                           review=review if review.exists() else None,
                           include_evidence=flags[0].get(), include_dicom=flags[1].get(), include_logs=flags[2].get())
            problems = verify_package(output)
            if problems:
                raise ValueError('\n'.join(problems))
            messagebox.showinfo('공유 ZIP', '생성과 무결성 검증을 완료했습니다.', parent=dialog)
        except (OSError, ValueError) as error:
            messagebox.showerror('공유 ZIP 실패', str(error), parent=dialog)
    ttk.Button(dialog, text='선택 범위로 ZIP 만들기', command=create).pack(pady=18)
