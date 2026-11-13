"""실제 Tk 동의 화면의 취소와 직접 체크 경로. 제품은 실행하지 않는다."""
import tkinter as tk
from tkinter import ttk

import pytest


def widgets(parent):
    for widget in parent.winfo_children():
        yield widget
        yield from widgets(widget)


def test_settings_selects_storage_and_saves_only_nested_field(monkeypatch, tk_root, tmp_path):
    import json
    from types import SimpleNamespace
    from tkinter import filedialog, messagebox
    from bellalunauto import gui
    layout = SimpleNamespace(workspace=tmp_path, config_path=tmp_path / 'synthetic.json')
    original = {'preservation': {'future_policy': {'keep': 1}},
                'viewer': {'login': {'id': 'synthetic', 'password': ' synthetic-secret '}},
                'unknown': ['keep']}
    chosen = str(tmp_path / 'offline-storage')
    original_exists = gui.Path.exists
    def guarded_exists(path):
        assert str(path) != chosen, '설정 폼에서 보존 저장소에 연결하면 안 됩니다.'
        return original_exists(path)
    monkeypatch.setattr(gui.Path, 'exists', guarded_exists)
    monkeypatch.setattr(filedialog, 'askdirectory', lambda **kwargs: chosen)
    monkeypatch.setattr(messagebox, 'askyesno', lambda *args, **kwargs: True)
    observed, failures = [], []

    def interact():
        dialog = tk_root.winfo_children()[0]
        try:
            controls = list(widgets(dialog))
            label = next(w for w in controls if isinstance(w, ttk.Label)
                         and '보존 저장소' in w.cget('text'))
            row = label.grid_info()['row']
            siblings = label.master.winfo_children()
            entry = next(w for w in siblings if isinstance(w, ttk.Entry)
                         and w.grid_info()['row'] == row)
            assert entry.get() == ''
            next(w for w in siblings if isinstance(w, ttk.Button)
                 and w.grid_info()['row'] == row).invoke()
            observed.append(entry.get())
            next(w for w in controls if isinstance(w, ttk.Button)
                 and w.cget('text') == '설정 저장').invoke()
        except Exception as error:
            failures.append(error)
            dialog.destroy()

    tk_root.after(20, interact)
    timeout = tk_root.after(2000, lambda: [w.destroy() for w in tk_root.winfo_children()])
    try:
        updated = gui._settings_dialog(tk_root, layout, original)
        assert not failures, str(failures)
        assert observed == [chosen]
        saved = json.loads(layout.config_path.read_text(encoding='utf-8'))
        assert saved == updated
        assert saved['preservation'] == {'future_policy': {'keep': 1}, 'storage_dir': chosen}
        assert saved['viewer']['login'] == original['viewer']['login']
        assert saved['unknown'] == ['keep']
        assert original['preservation'] == {'future_policy': {'keep': 1}}
    finally:
        tk_root.after_cancel(timeout)


def test_basic_diagnostics_panel_explains_separate_preservation_budget(monkeypatch, tk_root, tmp_path):
    from types import SimpleNamespace
    from bellalunauto import app, qa_dialogs
    monkeypatch.setattr(app, 'diagnostics', lambda layout: [
        {'name': '합성 기본 연결', 'ok': True, 'detail': '확인', 'fix': ''},
    ])
    panel = qa_dialogs._diagnostics_panel(tk_root, SimpleNamespace(workspace=tmp_path), lambda: None)
    try:
        text = ' '.join(str(w.cget('text')) for w in widgets(panel) if isinstance(w, ttk.Label))
        assert '기본 설치·연결 점검을 통과' in text
        assert '보존' in text and '용량' in text and '별도' in text
        assert '시험을 시작할 수 있습니다' not in text
    finally:
        panel.destroy()


@pytest.mark.parametrize('agree', [False, True])
@pytest.mark.parametrize('action', ['run-regression', 'run-winupdate'])
def test_real_confirmation_requires_check_and_closes_without_product(agree, action, monkeypatch, tk_root):
    from bellalunauto.qa_dialogs import confirm_plan
    from bellalunauto import runplan
    monkeypatch.setattr(runplan, 'format_plan', lambda plan: '합성 대상 · DB 변경 · 복구 정책')
    monkeypatch.setattr('core.usb_media.find_usb_drive', lambda: 'D:\\')
    plan = {'action': action}
    root = tk_root
    checked = []

    def interact():
        dialog = root.winfo_children()[0]
        controls = list(widgets(dialog))
        start = next(w for w in controls if isinstance(w, ttk.Button) and w.cget('text') == '동의하고 시작')
        checked.append('disabled' in start.state())
        if agree:
            boxes = [w for w in controls if isinstance(w, ttk.Checkbutton)]
            assert len(boxes) == (6 if action == 'run-winupdate' else 4)
            for box in boxes[:-1]:
                box.invoke()
                assert 'disabled' in start.state()
            boxes[-1].invoke()
            checked.append('disabled' not in start.state())
            start.invoke()
        else:
            next(w for w in controls if isinstance(w, ttk.Button) and w.cget('text') == '취소').invoke()
    root.after(30, interact)
    timed_out = []
    def timeout():
        timed_out.append(True)
        for dialog in root.winfo_children():
            dialog.destroy()
    timer = root.after(2000, timeout)
    try:
        assert confirm_plan(root, plan) is agree
        assert checked == ([True, True] if agree else [True])
        assert bool(plan.get('preparation_checked')) is agree
        assert not timed_out
    finally:
        root.after_cancel(timer)


@pytest.fixture(scope='module')
def tk_root():
    # 애플리케이션과 같이 Tcl/Tk 루트 하나에 여러 대화상자를 연다.
    # 다른 제품의 실제 자동화가 화면을 점유하면 grab_set 대화상자를 열지 않는다.
    import csv
    import io
    import os
    from pathlib import Path
    import subprocess
    if os.environ.get('BELLALUN_DESKTOP_BUSY') == '1':
        pytest.skip('운영자가 화면 사용 중으로 지정해 실제 Tk 화면 시험을 보류합니다.')
    peers = {'vxvueauto.exe', 'vxvue.exe', 'viewer.exe'}
    if os.name == 'nt':
        tasklist = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32' / 'tasklist.exe'
        result = subprocess.run([str(tasklist), '/FO', 'CSV', '/NH'], capture_output=True,
                                text=True, errors='replace', timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, '화면 점유 프로세스를 조회하지 못했습니다.'
        if any(row and row[0].casefold() in peers for row in csv.reader(io.StringIO(result.stdout))):
            pytest.skip('다른 제품/자동화가 실행 중이므로 실제 Tk 화면 시험을 보류합니다.')
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.mark.parametrize('restore', [False, True])
def test_consent_shows_diagnostics_and_records_each_run_restoration(restore, monkeypatch, tk_root, tmp_path):
    from types import SimpleNamespace
    from bellalunauto.qa_dialogs import confirm_plan
    from bellalunauto import runplan, app
    monkeypatch.setattr(runplan, 'format_plan', lambda plan: '합성 실행 계획')
    monkeypatch.setattr(app, 'diagnostics', lambda layout: [
        {'name': 'MWL 서버', 'ok': False, 'detail': '미설정', 'fix': '서버 주소를 입력하세요.'}])
    plan = {'action': 'run-regression', 'restore_after': True}
    layout = SimpleNamespace(workspace=tmp_path)
    opened, observed = [], []
    def interact():
        dialog = tk_root.winfo_children()[0]
        controls = list(widgets(dialog))
        tree = next(w for w in controls if isinstance(w, ttk.Treeview))
        row = tree.get_children()[0]
        observed.append(tuple(tree.item(row)['values']))
        tree.selection_set(row)
        tree.event_generate('<<TreeviewSelect>>')
        settings = next(w for w in controls if isinstance(w, ttk.Button)
                        and w.cget('text') == '선택 항목 설정 화면 열기')
        settings.invoke()
        boxes = [w for w in controls if isinstance(w, ttk.Checkbutton)]
        restoration = next(w for w in boxes if '실행 전 상태로 복원' in w.cget('text'))
        assert 'selected' in restoration.state(), '매 실행 복원을 기본 선택하고 이전 선택은 재사용하지 않습니다.'
        for box in boxes:
            if box is not restoration or not restore:
                box.invoke()
        next(w for w in controls if isinstance(w, ttk.Button) and w.cget('text') == '동의하고 시작').invoke()
    tk_root.after(20, interact)
    timeout = tk_root.after(2000, lambda: [w.destroy() for w in tk_root.winfo_children()])
    try:
        assert confirm_plan(tk_root, plan, layout=layout, open_config=lambda: opened.append(True))
        assert plan['restore_after'] is restore
        assert observed == [('FAIL', 'MWL 서버', '미설정')]
        assert opened == [True]
    finally:
        tk_root.after_cancel(timeout)


@pytest.fixture
def headless_confirmation(monkeypatch):
    """Tk 렌더링만 대체한다. 확인·해제·동의·취소의 앱 콜백은 그대로 실행한다."""
    from tkinter import scrolledtext
    controls = []

    class Variable:
        def __init__(self, value=False):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class Control:
        def __init__(self, parent, **options):
            self.options = options
            self.closed = False
            controls.append(self)

        def configure(self, **options):
            self.options.update(options)

        def invoke(self):
            if self.options.get('state') == 'disabled':
                return
            variable = self.options.get('variable')
            if variable is not None:
                variable.set(not variable.get())
            if self.options.get('command'):
                self.options['command']()

        def destroy(self):
            self.closed = True

        def pack(self, **kwargs):
            pass

        def title(self, value):
            pass

        def geometry(self, value):
            pass

        def insert(self, index, value):
            self.options['content'] = value

        def transient(self, root):
            pass

        def grab_set(self):
            pass

    monkeypatch.setattr(tk, 'BooleanVar', Variable)
    monkeypatch.setattr(tk, 'Toplevel', Control)
    for kind in ('Label', 'Button', 'Checkbutton'):
        monkeypatch.setattr(ttk, kind, Control)
    monkeypatch.setattr(scrolledtext, 'ScrolledText', Control)
    return controls


@pytest.mark.parametrize('choice', ['default', 'disable', 'cancel'])
def test_confirmation_defaults_restoration_and_honours_choice_without_gui(
        choice, headless_confirmation, monkeypatch):
    from types import SimpleNamespace
    from bellalunauto import qa_dialogs, runplan
    plan = {'action': 'run-regression', 'restore_after': False}
    formatted = []
    monkeypatch.setattr(runplan, 'format_plan', lambda value: formatted.append(value.copy()) or '합성 계획')
    controls = headless_confirmation

    def interact(dialog):
        restoration = next(w for w in controls if '실행 전 상태로 복원' in w.options.get('text', ''))
        assert restoration.options['variable'].get() is True
        texts = ' '.join(w.options.get('text', '') for w in controls)
        assert '공유 사본 검증' in texts and '정상 완주' in texts
        assert '서비스' in texts and '격리' in texts and 'Image' in texts
        assert '해제' in texts and 'DB' in texts and '자동 삭제' in texts
        if choice == 'cancel':
            next(w for w in controls if w.options.get('text') == '취소').invoke()
            return
        for control in controls:
            if 'variable' in control.options and (control is not restoration or choice == 'disable'):
                control.invoke()
        start = next(w for w in controls if w.options.get('text') == '동의하고 시작')
        assert start.options['state'] == 'normal'
        start.invoke()
        assert dialog.closed

    accepted = qa_dialogs.confirm_plan(SimpleNamespace(wait_window=interact), plan)
    assert accepted is (choice != 'cancel')
    assert formatted[0]['restore_after'] is True
    if choice == 'cancel':
        assert 'preparation_checked' not in plan
    else:
        assert plan['restore_after'] is (choice == 'default')


def test_reopened_confirmation_resets_disabled_choice_to_restore(headless_confirmation, monkeypatch):
    from types import SimpleNamespace
    from bellalunauto import qa_dialogs, runplan
    monkeypatch.setattr(runplan, 'format_plan', lambda value: '합성 계획')
    plan = {'action': 'run-regression'}
    controls = headless_confirmation
    observed = []

    def interact(dialog):
        current = controls[controls.index(dialog):]
        restoration = next(w for w in current if '실행 전 상태로 복원' in w.options.get('text', ''))
        observed.append(restoration.options['variable'].get())
        for control in current:
            if 'variable' in control.options and (control is not restoration or len(observed) == 1):
                control.invoke()
        next(w for w in current if w.options.get('text') == '동의하고 시작').invoke()

    root = SimpleNamespace(wait_window=interact)
    assert qa_dialogs.confirm_plan(root, plan)
    assert plan['restore_after'] is False
    assert qa_dialogs.confirm_plan(root, plan)
    assert plan['restore_after'] is True
    assert observed == [True, True]


@pytest.mark.parametrize('label,keyboard', [
    ('버전', True), ('결과 폴더 열기', False), ('PC별 설정', False),
    ('준비 점검', False), ('기본기능 체크리스트 자동화 수행', False),
    ('Windows Update 체크리스트 자동화 수행', False), ('수동 검토', False),
    ('공유 ZIP', False), ('자동 닫기 멈춤', False),
])
def test_real_gui_completion_countdown_is_cancelled_before_button_action(
        label, keyboard, monkeypatch, tk_root, tmp_path):
    from types import SimpleNamespace
    from bellalunauto import gui, qa_dialogs, runplan
    from tkinter import messagebox
    from bellalunauto.runs import RunRecord
    layout = SimpleNamespace(workspace=tmp_path, config_path=tmp_path / 'config.json', resource_dir=tmp_path)
    layout.config_path.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(gui, 'load_gui_config', lambda layout: {})
    monkeypatch.setattr(gui, 'validate_config', lambda config: [])
    monkeypatch.setattr(runplan, 'build_plan', lambda *args: {'action': args[-1]})
    monkeypatch.setattr(qa_dialogs, 'confirm_plan', lambda *args, **kwargs: True)
    monkeypatch.setattr(qa_dialogs, 'show_diagnostics', lambda *args: None)
    monkeypatch.setattr(qa_dialogs, 'review_run', lambda *args: None)
    monkeypatch.setattr(qa_dialogs, 'share_run', lambda *args: None)
    monkeypatch.setattr(gui, '_settings_dialog', lambda *args: None)
    monkeypatch.setattr(gui.os, 'startfile', lambda path: None)
    monkeypatch.setattr(messagebox, 'showinfo', lambda *args, **kwargs: None)
    def start(controller, action, **kwargs):
        controller.record = RunRecord.create(tmp_path, action, {})
        controller.record.data.update(status='completed', exit_code=1, verdicts={'FAIL': 1},
                                      next_action='review', review_status='pending')
        controller.record.save()
        controller.process = SimpleNamespace(poll=lambda: 1, returncode=1)
        controller.log_path = tmp_path / 'synthetic.log'
    monkeypatch.setattr(gui.RunController, 'start', start)
    root = tk.Toplevel(tk_root)
    root.withdraw()
    monkeypatch.setattr(tk, 'Tk', lambda: root)
    observed = []
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    def finish():
        root.quit()
        root.destroy()
    def interact():
        controls = list(widgets(root))
        regression = next(w for w in controls if isinstance(w, ttk.Button)
                          and w.cget('text') == '기본기능 체크리스트 자동화 수행')
        regression.invoke()
        root.after(250, cancel)
    def cancel():
        controls = list(widgets(root))
        stop_close = [w for w in controls if isinstance(w, ttk.Button) and w.cget('text') == '자동 닫기 멈춤']
        observed.append(bool(stop_close) and 'disabled' not in stop_close[0].state())
        if not stop_close:
            finish()
            return
        assert stop_close[0].winfo_ismapped(), '자동 닫기 멈춤은 완료 화면에서 항상 보여야 합니다.'
        countdown = [w for w in controls if isinstance(w, ttk.Label)
                     and w.cget('textvariable') and '초 후' in str(root.getvar(w.cget('textvariable')))]
        observed.append(bool(countdown))
        target = next(w for w in controls if isinstance(w, ttk.Button) and w.cget('text') == label)
        if keyboard:
            target.focus_force()
            root.update()
            target.event_generate('<KeyPress-space>')
            target.event_generate('<KeyRelease-space>')
            root.update()
        else:
            target.invoke()
        observed.append('disabled' in stop_close[0].state())
        finish()
    root.after(20, interact)
    root.after(2500, finish)
    assert gui.launch(layout) == 0
    assert not errors
    assert observed == [True, True, True]


def test_real_gui_automatically_destroys_only_after_sixty_seconds(monkeypatch, tk_root, tmp_path):
    from types import SimpleNamespace
    from bellalunauto import gui, qa_dialogs, runplan, auto_close
    from bellalunauto.runs import RunRecord
    layout = SimpleNamespace(workspace=tmp_path, config_path=tmp_path / 'config.json', resource_dir=tmp_path)
    layout.config_path.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(gui, 'load_gui_config', lambda layout: {})
    monkeypatch.setattr(gui, 'validate_config', lambda config: [])
    monkeypatch.setattr(runplan, 'build_plan', lambda *args: {'action': args[-1]})
    monkeypatch.setattr(qa_dialogs, 'confirm_plan', lambda *args, **kwargs: True)
    now, destroyed, boundary = [0.0], [], []
    original_init = auto_close.CompletionAutoClose.__init__
    def init(timer, scheduler, close, update):
        original_init(timer, scheduler, close, update, clock=lambda: now[0])
    monkeypatch.setattr(auto_close.CompletionAutoClose, '__init__', init)
    def start(controller, action, **kwargs):
        controller.record = RunRecord.create(tmp_path, action, {})
        controller.record.data.update(status='completed', exit_code=1, verdicts={'FAIL': 1},
                                      next_action='review', review_status='pending')
        controller.record.save()
        controller.process = SimpleNamespace(poll=lambda: 1, returncode=1)
        controller.log_path = tmp_path / 'synthetic.log'
    monkeypatch.setattr(gui.RunController, 'start', start)
    root = tk.Toplevel(tk_root)
    root.withdraw()
    monkeypatch.setattr(tk, 'Tk', lambda: root)
    original_destroy = root.destroy
    def destroy():
        destroyed.append(now[0])
        root.quit()
        original_destroy()
    root.destroy = destroy
    def begin():
        button = next(w for w in widgets(root) if isinstance(w, ttk.Button)
                      and w.cget('text') == '기본기능 체크리스트 자동화 수행')
        button.invoke()
    root.after(20, begin)
    root.after(350, lambda: now.__setitem__(0, 59.999))
    def at_boundary():
        boundary.append(root.winfo_exists())
        now[0] = 60.0
    root.after(1300, at_boundary)
    root.after(2500, root.destroy)
    assert gui.launch(layout) == 0
    assert boundary == [1]
    assert destroyed == [60.0]


@pytest.mark.parametrize('save_failure', [False, True])
def test_real_gui_manual_close_waits_for_log_and_final_record(save_failure, monkeypatch, tk_root, tmp_path):
    import json
    from types import SimpleNamespace
    from bellalunauto import gui, qa_dialogs, runplan
    from bellalunauto.runs import RunRecord
    if save_failure:
        def fail_save(*args):
            raise OSError('synthetic final write failure')
        monkeypatch.setattr(RunRecord, 'finish', fail_save)
    layout = SimpleNamespace(workspace=tmp_path, config_path=tmp_path / 'config.json', resource_dir=tmp_path)
    layout.config_path.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(gui, 'load_gui_config', lambda layout: {})
    monkeypatch.setattr(gui, 'validate_config', lambda config: [])
    monkeypatch.setattr(runplan, 'build_plan', lambda *args: {'action': args[-1]})
    monkeypatch.setattr(qa_dialogs, 'confirm_plan', lambda *args, **kwargs: True)
    reading, records, alive, ended = [True], [], [], []
    def start(controller, action, **kwargs):
        controller.record = RunRecord.create(tmp_path, action, {})
        records.append(controller.record.path)
        controller.process = SimpleNamespace(poll=lambda: 1, returncode=1)
        controller.reader = SimpleNamespace(is_alive=lambda: reading[0])
        controller.log_path = tmp_path / 'synthetic.log'
    monkeypatch.setattr(gui.RunController, 'start', start)
    root = tk.Toplevel(tk_root)
    root.withdraw()
    monkeypatch.setattr(tk, 'Tk', lambda: root)
    original_destroy = root.destroy
    def destroy():
        ended.append(json.loads(records[0].read_text(encoding='utf-8'))['status'])
        root.quit()
        original_destroy()
    root.destroy = destroy
    def begin():
        next(w for w in widgets(root) if isinstance(w, ttk.Button)
             and w.cget('text') == '기본기능 체크리스트 자동화 수행').invoke()
        root.tk.call(root.protocol('WM_DELETE_WINDOW'))
        alive.append(bool(root.winfo_exists()))
        reading[0] = False
    root.after(20, begin)
    if save_failure:
        def after_error():
            alive.append(bool(root.winfo_exists()))
            # 오류를 확인한 뒤의 명시적인 새 닫기 동작은 허용한다.
            root.tk.call(root.protocol('WM_DELETE_WINDOW'))
        root.after(350, after_error)
    root.after(2000, root.destroy)
    assert gui.launch(layout) == 0
    assert alive == ([True, True] if save_failure else [True])
    assert ended == (['running'] if save_failure else ['abnormal'])
