"""설치판과 복구용 EXE가 공유하는 복원 재개 화면."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
from threading import Thread
from types import SimpleNamespace

from core.run_preservation import RunPreservation


def _recovery_context(config_path):
    from core.db import BellalunDb

    config_path = Path(config_path)
    cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if not isinstance(cfg, dict):
        raise ValueError("config.json 설정은 JSON 객체여야 합니다.")
    data_dir = cfg.get("data_dir")
    if not isinstance(data_dir, str) or not Path(data_dir).is_absolute() or not Path(data_dir).is_dir():
        raise ValueError("config.json의 Viewer 데이터 폴더를 열 수 없습니다. PC별 설정의 경로를 확인하세요.")
    return SimpleNamespace(cfg=cfg, db=BellalunDb(cfg.get("sql_server", r".\BELLALUN")))


def recover_selected(workspace, config, run_id):
    from core.sysinfo import is_elevated
    from tools.recover_preservation import main

    if not is_elevated():
        raise PermissionError("관리자 권한으로 복원 도구를 실행하세요.")
    if run_id not in RunPreservation.pending(workspace):
        raise ValueError("선택한 실행은 복원 대기 목록에 없습니다.")
    if not config.is_file():
        raise FileNotFoundError("작업 폴더의 config.json을 찾을 수 없습니다.")
    output = StringIO()
    with redirect_stdout(output), redirect_stderr(output):
        code = main(["--workspace", str(workspace), "--config", str(config),
                     "--run-id", run_id, "--apply"], context_factory=_recovery_context)
    return code, output.getvalue()


def recover_with_installed_exe(workspace, config, run_id):
    from bellalunauto.runtime import child_command

    command = child_command(["--workspace", str(workspace), "--config", str(config),
                             "recover-preservation", run_id])
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.returncode, result.stdout + result.stderr


def launch_recovery(workspace, *, config=None, parent=None, recover=recover_selected):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    window = tk.Tk() if parent is None else tk.Toplevel(parent)
    window.title("BellalunAuto · 복원 재개")
    window.geometry("720x470")
    window.minsize(580, 380)
    panel = ttk.Frame(window, padding=16)
    panel.pack(fill="both", expand=True)
    path_text = tk.StringVar(value=str(workspace))
    status = tk.StringVar()
    in_progress = False
    results = Queue()
    ttk.Label(panel, text="BellalunAuto 작업 폴더").pack(anchor="w")
    path_row = ttk.Frame(panel)
    path_row.pack(fill="x", pady=(4, 12))
    path_entry = ttk.Entry(path_row, textvariable=path_text, state="readonly")
    path_entry.pack(side="left", fill="x", expand=True)
    ttk.Label(panel, text="복원 대기 실행을 선택하세요.").pack(anchor="w")
    pending = tk.Listbox(panel, height=7, exportselection=False)
    pending.pack(fill="both", expand=True, pady=(4, 8))
    ttk.Label(panel, textvariable=status, wraplength=640).pack(anchor="w", pady=(4, 10))
    actions = ttk.Frame(panel)
    actions.pack(fill="x")

    def refresh():
        work = Path(path_text.get())
        pending.delete(0, "end")
        start.configure(state="disabled")
        if not work.is_dir():
            status.set("작업 폴더를 찾을 수 없습니다. Auto의 준비 점검에 표시된 폴더를 선택하세요.")
            return
        try:
            runs = sorted(RunPreservation.pending(work), reverse=True)
        except (OSError, ValueError, RuntimeError) as error:
            status.set(f"복원 대기 목록 조회 실패 ({type(error).__name__}).")
            return
        for run_id in runs:
            pending.insert("end", run_id)
        if runs:
            status.set(f"복원 대기 {len(runs)}건입니다. 복원할 실행을 선택하세요.")
        else:
            status.set("이 작업 폴더에 복원 대기 기록이 없습니다.")

    def choose():
        selection = filedialog.askdirectory(parent=window, mustexist=True)
        if selection:
            path_text.set(selection)
            refresh()

    def restore():
        nonlocal in_progress
        selected = pending.curselection()
        if in_progress or not selected:
            return
        run_id = pending.get(selected[0])
        work = Path(path_text.get())
        cfg = Path(config) if config is not None and work == Path(workspace) else work / "config.json"
        if not messagebox.askyesno("복원 확인",
                                   f"실행 {run_id}의 백업으로 시험 DB와 파일을 복원합니다.\n"
                                   f"작업 폴더: {work}\n\n복원을 시작하시겠습니까?",
                                   parent=window, default="no"):
            return
        in_progress = True
        for control in (pending, start, browse, rescan, close):
            control.configure(state="disabled")
        status.set("복원을 수행하고 있습니다. 이 창을 닫거나 PC를 끄지 마세요.")
        bar.pack(fill="x", pady=8)
        bar.start()

        def worker():
            try:
                results.put(recover(work, cfg, run_id))
            except (OSError, ValueError, RuntimeError) as error:
                results.put((2, str(error)))
            except Exception as error:
                results.put((2, f"복원 결과를 처리하지 못했습니다 ({type(error).__name__}). "
                                "작업 폴더의 보존 기록을 유지하고 담당자에게 실행 번호를 전달하세요."))

        Thread(target=worker, daemon=False).start()
        window.after(150, poll)

    def poll():
        nonlocal in_progress
        try:
            code, detail = results.get_nowait()
        except Empty:
            window.after(150, poll)
            return
        in_progress = False
        bar.stop()
        bar.pack_forget()
        for control in (pending, browse, rescan, close):
            control.configure(state="normal")
        refresh()
        try:
            state = json.loads(detail).get("status")
        except (ValueError, AttributeError):
            state = None
        if code == 0:
            message = ("시험 후 상태 보존을 마쳤습니다." if state == "preserved"
                       else "선택한 실행의 복원 검증을 마쳤습니다.")
            messagebox.showinfo("복원 처리 완료", message + " Auto에서 준비 점검을 다시 실행하세요.", parent=window)
        else:
            if state == "cleanup_required":
                detail = "파일과 DB는 복원됐습니다. 생성 이미지 정리 대기입니다. 작업 폴더와 실행 번호를 담당자에게 전달하세요."
            elif state == "finalization_required":
                detail = "복원 뒤 서비스나 마무리 기록의 확인이 남았습니다. 작업 폴더와 실행 번호를 담당자에게 전달하세요."
            messagebox.showerror("복원 확인 필요",
                                 "복원이 끝나지 않았습니다. 실행 번호와 아래 내용을 담당자에게 전달하세요.\n\n"
                                 + detail.strip()[-1200:], parent=window)

    def close_window():
        if not in_progress:
            window.destroy()

    browse = ttk.Button(path_row, text="폴더 선택", command=choose)
    browse.pack(side="left", padx=(8, 0))
    bar = ttk.Progressbar(panel, mode="indeterminate")
    rescan = ttk.Button(actions, text="다시 확인", command=refresh)
    rescan.pack(side="left")
    close = ttk.Button(actions, text="닫기", command=close_window)
    close.pack(side="right")
    start = ttk.Button(actions, text="선택한 실행 복원", command=restore)
    start.pack(side="right", padx=8)
    pending.bind("<<ListboxSelect>>", lambda _event: start.configure(
        state="normal" if pending.curselection() and not in_progress else "disabled"))
    window.protocol("WM_DELETE_WINDOW", close_window)
    refresh()
    if parent is None:
        window.mainloop()
    else:
        window.transient(parent)
        window.grab_set()
        parent.wait_window(window)
