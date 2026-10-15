"""한국어 배포 실행 화면. 제품 엔진은 별도 CLI 감시 프로세스로만 실행한다."""
from __future__ import annotations

import copy
from datetime import datetime
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import uuid
from typing import Any


# (탭, 설정 경로, 표시명, 입력 종류). 폼에 없는 설정은 그대로 보존한다.
FIELDS = (
    ("제품 / DB", "viewer.exe", "Viewer 실행파일", "file"),
    ("제품 / DB", "install_dir", "Viewer 설치 폴더", "dir"),
    ("제품 / DB", "data_dir", "Viewer 데이터 폴더", "dir"),
    ("제품 / DB", "sql_server", "SQL Server 인스턴스", "text"),
    ("제품 / DB", "sql_service_name", "SQL 서비스 이름", "text"),
    ("XIPL / OCR", "xipl.studio_exe", "XIPL Studio 실행파일", "file"),
    ("XIPL / OCR", "xipl.parameter_dir", "XIPL Parameter 폴더", "dir"),
    ("XIPL / OCR", "xipl.tesseract_exe", "Tesseract OCR 실행파일", "file"),
    ("DICOM 서버", "dicom.mwl_server_url", "MWL HTTP 주소", "url"),
    ("DICOM 서버", "dicom.print_server_url", "Print HTTP 주소", "url"),
    ("DICOM 서버", "dicom.print_scp.host", "Print 호스트", "text"),
    ("DICOM 서버", "dicom.print_scp.ae_title", "Print AE Title", "text"),
    ("DICOM 서버", "dicom.print_scp.port", "Print 포트", "port"),
    ("DICOM 서버", "dicom.storage_scp.api_url", "Storage HTTP 주소", "url"),
    ("DICOM 서버", "dicom.storage_scp.host", "Storage 호스트", "text"),
    ("DICOM 서버", "dicom.storage_scp.ae_title", "Storage AE Title", "text"),
    ("DICOM 서버", "dicom.storage_scp.port", "Storage 포트", "port"),
    ("시험 로그인", "viewer.login.id", "시험 계정 ID", "text"),
    ("시험 로그인", "viewer.login.password", "시험 계정 비밀번호", "password"),
    ("시험 자료", "checklist_xlsx", "기본기능 체크리스트", "file"),
    ("시험 자료", "winupdate_checklist_xlsx", "Windows Update 체크리스트", "file"),
    ("시험 자료", "baseline_dir", "승인 Baseline 폴더", "dir"),
    ("시험 자료", "knowledge_dir", "사양 / 매뉴얼 폴더", "dir"),
)
_ACTIONS = {"run-regression", "run-winupdate", "selfcheck", "portability-check"}


def _get(config: dict, key: str, default: Any = "") -> Any:
    value: Any = config
    for part in key.split("."):
        if isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return default
    return value


def _set(config: dict, key: str, value: Any) -> None:
    parts = key.split(".")
    target = config
    for part in parts[:-1]:
        if isinstance(target, list):
            target = target[int(part)]
            continue
        if not isinstance(target.get(part), dict):
            if not isinstance(target.get(part), list):
                target[part] = {}
        target = target[part]
    target[parts[-1]] = value


def form_fields(config: dict) -> tuple:
    """실제 등록 서버 순서와 종류를 유지하며 기존 목록도 폼에서 편집한다."""
    fields = list(FIELDS)
    servers = _get(config, "dicom.servers_to_register", [])
    if isinstance(servers, list):
        for index, server in enumerate(servers):
            if not isinstance(server, dict):
                continue
            tab = f"등록{index + 1} {server.get('kind', 'DICOM')}"
            for key, label, kind in (("name", "이름", "text"), ("ip", "호스트", "text"),
                                     ("ae_title", "AE Title", "text"), ("port", "포트", "port")):
                fields.append((tab, f"dicom.servers_to_register.{index}.{key}", f"등록 서버 {index + 1} {label}", kind))
    return tuple(fields)


def command_arguments(layout, action: str, *, stop_file=None) -> list[str]:
    """UAC 전환과 CWD 변경에도 동일한 설정을 선택한다."""
    if action not in _ACTIONS:
        raise ValueError("지원하지 않는 실행입니다. 과거 WU 결과 변환은 CLI를 사용하세요.")
    arguments = ["--workspace", str(Path(layout.workspace).resolve()), "--config",
                 str(Path(layout.config_path).resolve())]
    if stop_file is not None:
        arguments += ["--stop-file", str(Path(stop_file).resolve())]
    return arguments + [action]


def merge_form_config(config: dict, values: dict[str, str]) -> dict:
    """검증 후 복사본에 폼 값만 반영한다. 비밀번호는 공백도 보존한다."""
    merged = copy.deepcopy(config)
    field_types = {key: kind for _, key, _, kind in form_fields(config)}
    field_labels = {key: label for _, key, label, _ in form_fields(config)}
    for key, raw in values.items():
        if key not in field_types:
            raise ValueError("지원하지 않는 설정 항목입니다.")
        value: Any = raw if field_types[key] == "password" else raw.strip()
        if field_types[key] == "port" and value:
            try:
                value = int(value)
                if not 1 <= value <= 65535:
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError(f"{field_labels[key]}: 1~65535 정수가 필요합니다.") from None
        if field_types[key] == "url" and value:
            from urllib.parse import urlsplit
            try:
                parsed = urlsplit(value)
                valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
                parsed.port
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(f"{field_labels[key]}: 계정 정보를 포함하지 않은 HTTP(S) 주소가 필요합니다.")
        _set(merged, key, value)
    return merged


def validate_config(config: dict) -> list[str]:
    """제품 시험 시작 전 필수 설정만 확인한다. 실제 연결 점검은 CLI gate가 한다."""
    errors = []
    fields = form_fields(config)
    for _, key, label, _ in fields:
        value = _get(config, key)
        if value is None or not str(value).strip() or "REPLACE_ME" in str(value) or "SERVER_IP" in str(value):
            errors.append(f"{label}: 값을 입력하세요.")
    try:
        merge_form_config(config, {key: str(_get(config, key)) for _, key, _, kind in fields
                                   if kind in {"port", "url"}
                                   and _get(config, key) is not None and str(_get(config, key)).strip()})
    except ValueError as error:
        errors.append(str(error))
    return errors


def detect_settings(config: dict) -> dict[str, str]:
    """읽기 전용 파일 탐지. 저장 없이 확인 폼에만 후보를 채운다."""
    values = {key: str(_get(config, key) or "") for _, key, _, _ in form_fields(config)}
    candidates = {
        "viewer.exe": [Path(values["install_dir"]) / "VIEWER.exe"] if values["install_dir"] else [],
        "xipl.studio_exe": [Path("C:/XIPL/STUDIO_X64/XIPL.STUDIO.exe")],
        "xipl.parameter_dir": [Path("C:/XIPL/PARAMETER")],
        "xipl.tesseract_exe": [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR/tesseract.exe"],
    }
    found_ocr = shutil.which("tesseract")
    if found_ocr:
        candidates["xipl.tesseract_exe"].insert(0, Path(found_ocr))
    for key, paths in candidates.items():
        if values[key] and Path(values[key]).exists():
            continue
        # Explicit values are kept even when a device is currently disconnected.
        if values[key]:
            continue
        for path in paths:
            if path.exists():
                values[key] = str(path.resolve())
                break
    return values


def load_gui_config(layout) -> dict:
    """설치 자료 기본값을 폼과 실행 검증에도 동일하게 제공한다. 저장하지 않는다."""
    from .resources import bundled_config
    from .runtime import load_config
    return bundled_config(load_config(layout), layout.resource_dir)


def secret_redactor(config: dict):
    secrets = set()

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if any(word in key.lower() for word in ("password", "passwd", "secret", "token", "api_key")) and isinstance(item, str) and item:
                    secrets.add(item)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(config)

    def scrub(text: str) -> str:
        for secret in sorted(secrets, key=len, reverse=True):
            text = text.replace(secret, "[비공개]")
        return re.sub(r'(?i)((?:password|passwd|secret|token|api_key)[\"\']?\s*[:=]\s*)(?:"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\s,;}]+)',
                      r"\1[비공개]", text)
    return scrub


class RunController:
    """Tk와 독립적인 단일 자식 수명/로그 관리. PC 전역 잠금은 CLI가 소유한다."""

    def __init__(self, layout, config: dict):
        self.layout = layout
        self.config = config
        self.process = None
        self.reader = None
        self.log_path = None
        self.stop_path = None
        self.lines: queue.Queue[str] = queue.Queue()

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, action: str) -> None:
        from .runtime import child_command
        if self.running:
            raise RuntimeError("이미 실행 중입니다. 현재 작업 종료 후 실행하세요.")
        self.stop_path = Path(self.layout.workspace) / "work" / f"stop-{uuid.uuid4().hex}.json"
        self.start_argv(child_command(command_arguments(self.layout, action, stop_file=self.stop_path)))

    def start_argv(self, argv: list[str]) -> None:
        if self.running:
            raise RuntimeError("이미 실행 중입니다. 현재 작업 종료 후 실행하세요.")
        if self.reader is not None and self.reader.is_alive():
            raise RuntimeError("이전 실행 로그를 마무리하고 있습니다.")
        log_dir = Path(self.layout.workspace) / "Log"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / ("BellalunAuto-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".log")
        environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        self.process = subprocess.Popen(
            argv, cwd=str(self.layout.workspace), env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        scrub = secret_redactor(self.config)
        stream = self.process.stdout
        path = self.log_path

        def read_output():
            try:
                with path.open("w", encoding="utf-8", newline="\n") as output:
                    for line in stream:
                        safe_line = scrub(line)
                        output.write(safe_line)
                        output.flush()
                        self.lines.put(safe_line)
            except OSError:
                self.lines.put("로그 파일을 기록하지 못했습니다. 작업 폴더 권한과 디스크 공간을 확인하세요.\n")
            finally:
                stream.close()
        self.reader = threading.Thread(target=read_output, daemon=True)
        self.reader.start()

    def drain(self) -> list[str]:
        lines = []
        while True:
            try:
                lines.append(self.lines.get_nowait())
            except queue.Empty:
                return lines

    def stop(self) -> None:
        if not self.running:
            return
        process = self.process
        if self.stop_path is not None:
            self.stop_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.stop_path.with_suffix(".tmp")
            temporary.write_text('{"stop": true}\n', encoding="utf-8")
            os.replace(temporary, self.stop_path)
            try:
                # Guardian cleans its worker tree and Viewer before returning.
                process.wait(timeout=20)
                return
            except subprocess.TimeoutExpired:
                pass
        # Last resort targets only this child's tree, never a global image name.
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10,
                           check=False)
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _settings_dialog(root, layout, config: dict, *, first_run=False):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from .runtime import save_config

    dialog = tk.Toplevel(root)
    dialog.title("BellalunAuto · PC별 설정")
    dialog.geometry("850x650")
    dialog.transient(root)
    dialog.grab_set()
    result = []
    ttk.Label(dialog, text="설정은 이 PC의 작업 폴더에만 저장합니다. 저장 전에는 파일을 변경하지 않습니다.", padding=10).pack(anchor="w")
    if first_run:
        ttk.Label(dialog, text="처음 실행입니다. 경로와 시험 계정을 확인하고 설정 저장을 누르세요. 시험은 자동 시작하지 않습니다.").pack(anchor="w", padx=10)
    notebook = ttk.Notebook(dialog)
    notebook.pack(fill="both", expand=True, padx=10, pady=8)
    tabs = {}
    variables = {}
    status = {}
    fields = form_fields(config)

    def browse(key, kind):
        selected = (filedialog.askdirectory(parent=dialog) if kind == "dir"
                    else filedialog.askopenfilename(parent=dialog))
        if selected:
            variables[key].set(selected)

    def refresh_status():
        for _, key, _, kind in fields:
            value = variables[key].get()
            if kind in {"file", "dir"}:
                status[key].set("확인됨" if value and Path(value).exists() else "미확인")
            else:
                status[key].set("입력됨" if value else "미입력")

    for tab_name, key, label, kind in fields:
        if tab_name not in tabs:
            tabs[tab_name] = ttk.Frame(notebook, padding=12)
            tabs[tab_name].columnconfigure(1, weight=1)
            notebook.add(tabs[tab_name], text=tab_name)
        tab = tabs[tab_name]
        row = len([entry for entry in variables if next(item[0] for item in fields if item[1] == entry) == tab_name])
        ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=8)
        variables[key] = tk.StringVar(value=str(_get(config, key) or ""))
        ttk.Entry(tab, textvariable=variables[key], show="●" if kind == "password" else "").grid(row=row, column=1, sticky="ew", padx=4, pady=8)
        if kind in {"file", "dir"}:
            ttk.Button(tab, text="찾기", command=lambda k=key, t=kind: browse(k, t)).grid(row=row, column=2, padx=4)
        status[key] = tk.StringVar()
        ttk.Label(tab, textvariable=status[key], width=9).grid(row=row, column=3, padx=4)

    def detect():
        try:
            draft = merge_form_config(config, {key: value.get() for key, value in variables.items()})
        except ValueError:
            messagebox.showerror("입력 확인", "포트와 HTTP 주소를 먼저 확인하세요.", parent=dialog)
            return
        for key, value in detect_settings(draft).items():
            variables[key].set(value)
        refresh_status()
        messagebox.showinfo("자동 탐지", "로컬 파일 후보를 폼에 채웠습니다. 서버·계정·SQL 서비스 값은 직접 확인하세요. 저장을 눌러야 반영됩니다.", parent=dialog)

    def save():
        try:
            updated = merge_form_config(config, {key: value.get() for key, value in variables.items()})
            errors = validate_config(updated)
            if errors and not messagebox.askyesno("미완성 설정 저장", "아래 항목을 나중에 입력할 수 있습니다. 현재 설정을 저장할까요?\n\n" + "\n".join(errors), parent=dialog):
                return
            save_config(layout, updated)
        except (ValueError, OSError) as error:
            messagebox.showerror("설정 저장 실패", secret_redactor(config)(str(error)), parent=dialog)
            return
        result.append(updated)
        dialog.destroy()

    actions = ttk.Frame(dialog, padding=10)
    actions.pack(fill="x")
    ttk.Button(actions, text="자동 탐지 / 입력 확인", command=detect).pack(side="left")
    ttk.Button(actions, text="취소", command=dialog.destroy).pack(side="right")
    ttk.Button(actions, text="설정 저장", command=save).pack(side="right", padx=8)
    refresh_status()
    root.wait_window(dialog)
    return result[0] if result else None


def launch(layout) -> int:
    """Tk 이벤트 루프. 호출만으로 제품 시험이나 DB 복원을 시작하지 않는다."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
    from . import __version__
    from .runtime import remember_workspace, resolve_layout

    root = tk.Tk()
    root.withdraw()
    root.title(f"BellalunAuto {__version__}")
    root.geometry("960x720")
    first_run = not Path(layout.config_path).exists()
    if first_run:
        chosen = filedialog.askdirectory(parent=root, title="BellalunAuto 작업 폴더 선택 (설정·결과·증거·로그)", initialdir=str(layout.workspace), mustexist=False)
        if not chosen:
            root.destroy()
            return 0
    try:
        if first_run:
            layout = resolve_layout(workspace=chosen, resource_dir=layout.resource_dir)
        config = load_gui_config(layout)
        if first_run:
            root.deiconify()
            updated = _settings_dialog(root, layout, config, first_run=True)
            if updated is None:
                root.destroy()
                return 0
            config = updated
            remember_workspace(layout.workspace)
    except (OSError, ValueError) as error:
        messagebox.showerror("설정 불러오기 실패", str(error), parent=root)
        root.destroy()
        return 1
    controller = RunController(layout, config)
    root.deiconify()
    ttk.Label(root, text=f"BellalunAuto {__version__}", font=("맑은 고딕", 19, "bold"), padding=12).pack(anchor="w")
    ttk.Label(root, text=f"작업 폴더: {layout.workspace}", wraplength=920).pack(anchor="w", padx=12)
    ttk.Label(root, text="제품 시험 중에는 마우스·키보드 사용을 피하세요. 두 전체 시험은 순서대로 실행합니다.", padding=12).pack(anchor="w")
    toolbar = ttk.Frame(root, padding=10)
    toolbar.pack(fill="x")
    buttons = []
    status = tk.StringVar(value="대기 중 · 시험을 선택하세요.")
    ttk.Label(root, textvariable=status, padding=10).pack(anchor="w")
    progress = ttk.Progressbar(root, mode="indeterminate")
    progress.pack(fill="x", padx=12)
    output = scrolledtext.ScrolledText(root, wrap="word", height=22, state="disabled", font=("Consolas", 10))
    output.pack(fill="both", expand=True, padx=12, pady=10)
    active = [False]
    stopping = threading.Event()
    close_requested = [False]

    def append(text):
        output.configure(state="normal")
        output.insert("end", text)
        if int(output.index("end-1c").split(".")[0]) > 2000:
            output.delete("1.0", "500.0")
        output.see("end")
        output.configure(state="disabled")

    def set_busy(value):
        for button in buttons:
            button.configure(state="disabled" if value else "normal")
        stop_button.configure(state="normal" if value else "disabled")
        if value:
            progress.start(15)
        else:
            progress.stop()

    def run(action):
        if controller.running:
            return
        if action in {"run-regression", "run-winupdate"}:
            errors = validate_config(controller.config)
            if errors:
                messagebox.showerror("PC별 설정 확인", "시험 전 아래 항목을 입력하세요.\n\n" + "\n".join(errors), parent=root)
                return
        try:
            controller.start(action)
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror("실행 실패", secret_redactor(controller.config)(str(error)), parent=root)
            return
        active[0] = True
        set_busy(True)
        status.set(f"실행 중: {action} · 로그: {controller.log_path.name}")
        append(f"\n실행 시작: {action}\n")

    for label, action in (("기본기능 전체 실행", "run-regression"), ("Windows Update 실시간 전체 실행", "run-winupdate"), ("자체진단", "selfcheck"), ("환경 점검", "portability-check")):
        button = ttk.Button(toolbar, text=label, command=lambda selected=action: run(selected))
        button.pack(side="left", padx=4)
        buttons.append(button)

    def settings():
        updated = _settings_dialog(root, layout, controller.config)
        if updated is not None:
            controller.config = updated
            status.set("PC별 설정을 저장했습니다. 시험을 선택하세요.")

    footer = ttk.Frame(root, padding=10)
    footer.pack(fill="x")
    settings_button = ttk.Button(footer, text="PC별 설정", command=settings)
    settings_button.pack(side="left", padx=4)
    buttons.append(settings_button)

    def open_results():
        folder = Path(layout.workspace) / "Reports"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(folder))
        except OSError:
            messagebox.showerror("결과 폴더", "결과 폴더를 열 수 없습니다. 작업 폴더의 Reports를 확인하세요.", parent=root)
    ttk.Button(footer, text="결과 폴더 열기", command=open_results).pack(side="left", padx=4)
    ttk.Button(footer, text="버전", command=lambda: messagebox.showinfo("버전", f"BellalunAuto {__version__}", parent=root)).pack(side="left", padx=4)
    ttk.Label(footer, text="과거 WU 결과 변환은 CLI 명령을 사용하세요.").pack(side="left", padx=12)

    def stop():
        if stopping.is_set():
            return
        stopping.set()
        status.set("실행 중단 및 자식 프로세스 정리 중…")
        stop_button.configure(state="disabled")

        def request_stop():
            try:
                controller.stop()
            except (OSError, subprocess.TimeoutExpired):
                controller.lines.put("자식 프로세스 종료를 확인하지 못했습니다. 로그를 확인하세요.\n")
            finally:
                stopping.clear()
        threading.Thread(target=request_stop, daemon=True).start()
    stop_button = ttk.Button(footer, text="실행 중단", command=stop, state="disabled")
    stop_button.pack(side="right")

    def poll():
        for line in controller.drain():
            append(line)
        if active[0] and not controller.running and (controller.reader is None or not controller.reader.is_alive()):
            for line in controller.drain():
                append(line)
            code = controller.process.returncode
            status.set(f"실행 종료 · 종료 코드 {code} · 새 리포트의 TC별 판정을 확인하세요.")
            active[0] = False
            set_busy(False)
            if close_requested[0]:
                root.destroy()
                return
        if not stopping.is_set() and controller.running:
            stop_button.configure(state="normal")
        root.after(200, poll)

    def close():
        if controller.running:
            if not messagebox.askyesno("실행 중 종료", "시험을 중단하고 이 실행의 자식 프로세스를 정리한 뒤 종료할까요?", parent=root):
                return
            close_requested[0] = True
            stop()
            return
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(200, poll)
    root.mainloop()
    return 0
