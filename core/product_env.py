# -*- coding: utf-8 -*-
"""Viewer·XIPL Studio를 띄울 때 쓰는 환경 변수.

Viewer는 시스템 환경 변수 `XIPL_PATH`로 `SERVER_X64\\XIPL.KEEPALIVE.exe`를 찾는다.
이 값이 실행 환경에 없으면 `XIPL is not installed. [E2100]`을 기록한 뒤 PC 전원을 끈다
(2026-10-18 실측, System 이벤트 1074 `VIEWER.exe`). BellalunAuto가 오래된 셸·예약 작업·
줄어든 환경에서 시작되어도 같은 일이 생기지 않도록, 실행 환경에 없는 등록 환경 변수를
레지스트리에서 보충하고 그래도 `XIPL_PATH`가 맞지 않으면 Viewer를 띄우지 않는다.
"""
import os
from pathlib import Path

_MACHINE_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
_USER_KEY = "Environment"
#: 실행 환경의 값을 그대로 둔다. PATH는 호출한 쪽이 정한 검색 순서를 바꾸지 않는다.
_NEVER_FILL = {"PATH", "PSMODULEPATH"}


def _read_key(root, subkey):
    import winreg
    values = {}
    try:
        with winreg.OpenKey(root, subkey) as key:
            index = 0
            while True:
                try:
                    name, value, kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if kind == winreg.REG_EXPAND_SZ:
                    value = winreg.ExpandEnvironmentStrings(value)
                if isinstance(value, str):
                    values[name] = value
    except OSError:
        pass
    return values


def registered_environment():
    """시스템 → 사용자 순서로 레지스트리에 등록된 환경 변수. 같은 이름은 사용자 값이 이긴다."""
    if os.name != "nt":
        return {}
    import winreg
    merged = {}
    for root, subkey in ((winreg.HKEY_LOCAL_MACHINE, _MACHINE_KEY),
                         (winreg.HKEY_CURRENT_USER, _USER_KEY)):
        for name, value in _read_key(root, subkey).items():
            for existing in [k for k in merged if k.upper() == name.upper()]:
                del merged[existing]
            merged[name] = value
    return merged


def product_environment(base=None, registered=None):
    """`base`(기본: 현재 환경)에 없는 등록 환경 변수만 더한 새 dict. 기존 값은 바꾸지 않는다."""
    env = dict(os.environ if base is None else base)
    registered = registered_environment() if registered is None else registered
    present = {key.upper() for key in env}
    for name, value in registered.items():
        if name.upper() in _NEVER_FILL or name.upper() in present:
            continue
        env[name] = value
        present.add(name.upper())
    return env


def lookup(env, name):
    """대소문자를 가리지 않는 환경 변수 조회."""
    return next((value for key, value in env.items() if key.upper() == name.upper()), None)


def xipl_problem(env):
    """`XIPL_PATH`가 Viewer가 찾는 XIPL 설치를 가리키면 None, 아니면 한국어 설명."""
    value = lookup(env, "XIPL_PATH")
    if not value:
        return "환경 변수 XIPL_PATH가 없습니다."
    keepalive = Path(value) / "SERVER_X64" / "XIPL.KEEPALIVE.exe"
    if not keepalive.is_file():
        return f"XIPL_PATH={value} 아래에 SERVER_X64\\XIPL.KEEPALIVE.exe가 없습니다."
    return None


XIPL_FIX = ("XIPL을 다시 설치하거나 시스템 환경 변수 XIPL_PATH를 XIPL 설치 폴더(예: C:\\XIPL\\)로 "
            "설정하세요. 이 값이 없으면 Viewer가 시작 중 PC 전원을 끕니다.")


def viewer_environment():
    """Viewer 실행 환경. XIPL_PATH가 맞지 않으면 Viewer를 띄우지 않도록 RuntimeError."""
    env = product_environment()
    problem = xipl_problem(env)
    if problem:
        raise RuntimeError(f"Viewer를 시작하지 않습니다. {problem} {XIPL_FIX}")
    return env
