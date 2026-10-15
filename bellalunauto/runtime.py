"""Installation resources, user workspace, and machine-wide run coordination.

Resolving paths and reading defaults never creates workspace files. Only an
explicit settings save or workspace selection writes user data.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Iterable


@dataclass(frozen=True)
class Layout:
    resource_dir: Path
    workspace: Path
    config_path: Path


def _absolute(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve()


def _compiled() -> bool:
    return "__compiled__" in globals() or bool(getattr(sys, "frozen", False))


def _resources() -> Path:
    if _compiled():
        return _absolute(sys.executable).parent / "resources"
    return Path(__file__).resolve().parents[1]


def _validate_write_paths(workspace: Path, config_path: Path) -> None:
    """Compiled installations remain read-only, including through path aliases."""
    if not _compiled():
        return
    installation = _absolute(sys.executable).parent
    if any(_absolute(path).is_relative_to(installation) for path in (workspace, config_path)):
        raise ValueError("작업 폴더와 설정 파일은 설치 폴더 밖에 지정하세요.")


def _preferences_dir(preferences_dir: str | os.PathLike[str] | None = None) -> Path:
    if preferences_dir is not None:
        return _absolute(preferences_dir)
    local = os.environ.get("LOCALAPPDATA")
    return _absolute(local if local else Path.home() / "AppData" / "Local") / "BellalunAuto"


def resolve_layout(
    config_path: str | os.PathLike[str] | None = None,
    workspace: str | os.PathLike[str] | None = None,
    resource_dir: str | os.PathLike[str] | None = None,
    preferences_dir: str | os.PathLike[str] | None = None,
) -> Layout:
    """Resolve explicit paths once; otherwise reuse the last selected workspace.

    An explicit config must exist, so a misspelled CLI argument cannot silently
    start with unrelated defaults. A first-run GUI omits config_path.
    """
    resources = _absolute(resource_dir) if resource_dir is not None else _resources()
    if workspace is None:
        preference = _preferences_dir(preferences_dir) / "preferences.json"
        if preference.is_file():
            saved = _read_object(preference).get("workspace")
            if not isinstance(saved, str) or not Path(saved).is_absolute():
                raise ValueError("저장된 작업 폴더가 올바른 절대 경로가 아닙니다.")
            workspace = saved
        else:
            workspace = _preferences_dir() / "workspace"
    work = _absolute(workspace)
    config = _absolute(config_path) if config_path is not None else work / "config.json"
    _validate_write_paths(work, config)
    if config_path is not None and not config.is_file():
        raise FileNotFoundError("지정한 설정 파일이 없습니다.")
    return Layout(resources, work, config)


def _read_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError("설정 파일의 최상위 값은 JSON 객체여야 합니다.")
    return value


def default_config(resource_dir: str | os.PathLike[str] | None = None) -> dict:
    """Read public options and replace all example endpoints and credentials.

    This intentionally never reads config.json. The bundled example may include
    legacy lab values; first-run settings must ask for the target PC's values.
    """
    resources = _absolute(resource_dir) if resource_dir is not None else _resources()
    config = _read_object(resources / "config.example.json")

    def neutralize(value):
        if isinstance(value, list):
            return [neutralize(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered.startswith("_"):
                # Historical comments can themselves contain lab addresses.
                continue
            if lowered in {"accounts", "login"}:
                result[key] = {} if lowered == "accounts" else {"id": "", "password": ""}
            elif lowered in {"password", "token", "api_key", "secret"}:
                result[key] = ""
            elif lowered in {"host", "ip", "expected_ipv4"}:
                result[key] = None if lowered == "expected_ipv4" else "REPLACE_ME"
            elif lowered.endswith("_url") or lowered == "url":
                result[key] = ""
            else:
                result[key] = neutralize(item)
        return result

    return neutralize(config)


def load_config(layout: Layout) -> dict:
    """Read an existing user config unchanged, or return unwritten defaults."""
    if layout.config_path.exists():
        return _read_object(layout.config_path)
    return default_config(layout.resource_dir)


def _atomic_json(path: Path, value: dict) -> None:
    # Serialize before touching the destination, including for invalid objects.
    serialized = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix="." + path.name + ".", suffix=".tmp",
                                         dir=path.parent, delete=False) as target:
            temporary = Path(target.name)
            target.write(serialized)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_config(layout: Layout, config: dict) -> None:
    """Atomically replace only the selected config; retain unknown user fields."""
    if not isinstance(config, dict):
        raise ValueError("설정은 JSON 객체여야 합니다.")
    _validate_write_paths(layout.workspace, layout.config_path)
    _atomic_json(layout.config_path, config)


def remember_workspace(
    workspace: str | os.PathLike[str],
    preferences_dir: str | os.PathLike[str] | None = None,
) -> None:
    _atomic_json(_preferences_dir(preferences_dir) / "preferences.json",
                 {"workspace": str(_absolute(workspace))})


def _windows_executable_path() -> str:
    """Read this process's actual image path; Nuitka may report python.exe."""
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    locate = kernel.GetModuleFileNameW
    locate.argtypes = (wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD)
    locate.restype = wintypes.DWORD
    size = 260
    while True:
        buffer = ctypes.create_unicode_buffer(size)
        length = locate(None, buffer, size)
        if not length:
            raise ctypes.WinError(ctypes.get_last_error())
        if length < size:
            return buffer.value
        if size >= 32768:
            raise RuntimeError("실행 파일 경로가 Windows 경로 버퍼 한도를 초과했습니다.")
        size = min(size * 2, 32768)


def child_command(
    arguments: Iterable[str],
    executable: str | os.PathLike[str] | None = None,
    compiled: bool | None = None,
) -> list[str]:
    """Build an argv list without shell quoting or dependence on the child CWD."""
    is_compiled = _compiled() if compiled is None else compiled
    if executable is not None:
        binary = os.fspath(executable)
    elif is_compiled and os.name == "nt":
        binary = _windows_executable_path()
    else:
        binary = sys.executable
    prefix = [binary] if is_compiled else [binary, str(Path(__file__).resolve().parents[1] / "BellalunAuto.py")]
    return prefix + list(arguments)


class AlreadyRunning(RuntimeError):
    """Another process holds the machine-wide product-operation guard."""


class RunLock:
    """Hold one Global Windows mutex by handle lifetime, across user sessions.

    Authenticated users receive SYNCHRONIZE access only. CreateMutexEx requests
    that same access, allowing standard/elevated/different-account callers to
    detect an existing guard without requiring its owner's full-access ACL.
    No thread owns the mutex: a handle keeps it alive until release or crash.
    """
    DEFAULT_NAME = "Global\\BellalunAuto.ProductOperation.v1"

    def __init__(self, name: str = DEFAULT_NAME):
        self.name = name if name.startswith("Global\\") else "Global\\" + name
        self._handle = None
        self._kernel = None

    def acquire(self) -> RunLock:
        if self._handle is not None:
            raise AlreadyRunning("이 실행은 이미 제품 조작 잠금을 보유하고 있습니다.")
        if os.name != "nt":
            raise OSError("제품 조작 잠금은 Windows에서만 사용할 수 있습니다.")
        from ctypes import wintypes

        class SecurityAttributes(ctypes.Structure):
            _fields_ = [("nLength", wintypes.DWORD),
                        ("lpSecurityDescriptor", wintypes.LPVOID),
                        ("bInheritHandle", wintypes.BOOL)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                            ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.ULONG)]
        convert.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel.LocalFree.restype = wintypes.HLOCAL
        kernel.CreateMutexExW.argtypes = [ctypes.POINTER(SecurityAttributes), wintypes.LPCWSTR,
                                         wintypes.DWORD, wintypes.DWORD]
        kernel.CreateMutexExW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        descriptor = wintypes.LPVOID()
        # Protected DACL; SYSTEM/admins have full access, authenticated users can
        # open the sentinel. Explicit medium label also permits UAC transitions.
        sddl = "D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;0x00100000;;;AU)S:(ML;;NW;;;ME)"
        if not convert(sddl, 1, ctypes.byref(descriptor), None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
            ctypes.set_last_error(0)
            handle = kernel.CreateMutexExW(ctypes.byref(attributes), self.name, 0, 0x00100000)
            error = ctypes.get_last_error()
        finally:
            kernel.LocalFree(descriptor)
        if not handle:
            raise ctypes.WinError(error)
        if error == 183:  # ERROR_ALREADY_EXISTS; do not wait on an existing run.
            kernel.CloseHandle(handle)
            raise AlreadyRunning("이 PC에서 다른 자동화가 제품을 조작하고 있습니다.")
        self._handle = handle
        self._kernel = kernel
        return self

    def release(self) -> None:
        if self._handle is not None:
            handle, self._handle = self._handle, None
            if not self._kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())

    def __enter__(self) -> RunLock:
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
