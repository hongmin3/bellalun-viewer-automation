"""실제 Tk 동의 화면의 취소와 직접 체크 경로. 제품은 실행하지 않는다."""
import tkinter as tk
from tkinter import ttk

import pytest


def widgets(parent):
    for widget in parent.winfo_children():
        yield widget
        yield from widgets(widget)


@pytest.mark.parametrize('agree', [False, True])
def test_real_confirmation_requires_check_and_closes_without_product(agree, monkeypatch, tk_root):
    from bellalunauto.qa_dialogs import confirm_plan
    from bellalunauto import runplan
    monkeypatch.setattr(runplan, 'format_plan', lambda plan: '합성 대상 · DB 변경 · 복구 정책')
    root = tk_root
    checked = []

    def interact():
        dialog = root.winfo_children()[0]
        controls = list(widgets(dialog))
        start = next(w for w in controls if isinstance(w, ttk.Button) and w.cget('text') == '동의하고 시작')
        checked.append('disabled' in start.state())
        if agree:
            next(w for w in controls if isinstance(w, ttk.Checkbutton)).invoke()
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
        assert confirm_plan(root, {}) is agree
        assert checked == ([True, True] if agree else [True])
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
