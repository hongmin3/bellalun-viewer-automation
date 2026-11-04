# -*- coding: utf-8 -*-
"""실행 PC 지문과 검증된 환경 목록(`verified_environments.json`) 대조.

자동화 결과를 읽는 사람은 "이 PC가 전체 실행이 실제로 끝까지 검증된 환경과
같은가"를 알아야 FAIL이 제품 결함인지 환경 차이인지 가늠할 수 있다. 그래서
OS 에디션·빌드·해상도·DPI·Viewer 버전으로 지문을 만들고 등록 항목과 비교한다.

미등록 환경은 **WARN으로만 알린다.** 등록 목록은 지금까지 검증한 범위의 기록일
뿐 지원 범위의 경계가 아니므로 실행을 막지 않는다.

값 조회는 레지스트리(`winreg`)만 쓴다. `core.sysinfo.os_update_info()`와 같은
`CurrentVersion` 키를 읽지만 PowerShell 프로세스를 띄우지 않아 시간 제한이
필요 없다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

FIELDS = ("os_edition", "build_ubr", "resolution", "dpi", "viewer_version")
FIELD_LABELS = {
    "os_edition": "OS 에디션",
    "build_ubr": "OS 빌드",
    "resolution": "해상도",
    "dpi": "DPI",
    "viewer_version": "Viewer 버전",
}

DATA_FILE = "verified_environments.json"
_CURRENT_VERSION = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
# Windows 11도 레지스트리 ProductName은 "Windows 10 ..."으로 남아 있다.
# 빌드 22000부터가 Windows 11이다.
_WIN11_FIRST_BUILD = 22000


def probe_value(probe, key, default=None):
    """`probe[key]`를 읽는다. 값이 호출 가능하면 호출 결과를 쓴다.

    조회 실패는 예외 대신 `default`로 돌려준다 — 사전 점검 한 항목의 조회
    오류가 점검 전체를 멈추면 안 된다.
    """
    if probe is None:
        return default
    try:
        value = probe.get(key, default) if hasattr(probe, "get") else probe[key]
    except Exception:
        return default
    if callable(value):
        try:
            return value()
        except Exception:
            return default
    return value


# ---------------------------------------------------------------- 실제 조회

def _current_version_values():
    import winreg
    out = {}
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CURRENT_VERSION, 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        for name in ("ProductName", "CurrentBuildNumber", "UBR", "DisplayVersion"):
            try:
                out[name] = winreg.QueryValueEx(key, name)[0]
            except OSError:
                out[name] = None
    return out


def edition_from_registry(values):
    """ProductName을 Windows 11 표기로 보정한다. 앞의 "Microsoft "는 뗀다."""
    name = str(values.get("ProductName") or "").strip()
    if not name:
        return None
    if name.startswith("Microsoft "):
        name = name[len("Microsoft "):]
    try:
        build = int(values.get("CurrentBuildNumber") or 0)
    except (TypeError, ValueError):
        build = 0
    if build >= _WIN11_FIRST_BUILD and name.startswith("Windows 10"):
        name = "Windows 11" + name[len("Windows 10"):]
    return name


def build_from_registry(values):
    """`26200.7171` 형식. UBR이 없으면 빌드 번호만."""
    build = values.get("CurrentBuildNumber")
    if not build:
        return None
    ubr = values.get("UBR")
    return f"{build}.{ubr}" if ubr is not None else str(build)


def real_os_edition():
    return edition_from_registry(_current_version_values())


def real_build_ubr():
    return build_from_registry(_current_version_values())


# ---------------------------------------------------------------- 지문과 대조

def normalize_edition(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if text.startswith("Microsoft "):
        text = text[len("Microsoft "):]
    return text.casefold()


def fingerprint(probe):
    """probe에서 지문 5개 필드를 만든다.

    probe 키: `os_edition`(또는 `os_caption`), `build_ubr`, `display`
    (`{"actual": (w, h), "dpi": n}`) 또는 `resolution`/`dpi`, `viewer_version`.
    조회하지 못한 값은 None으로 둔다.
    """
    edition = probe_value(probe, "os_edition")
    if not edition:
        edition = probe_value(probe, "os_caption")
    display = probe_value(probe, "display") or {}
    resolution = probe_value(probe, "resolution")
    if resolution is None and display.get("actual"):
        w, h = display["actual"]
        resolution = f"{int(w)}x{int(h)}"
    dpi = probe_value(probe, "dpi")
    if dpi is None:
        dpi = display.get("dpi")
    edition_text = re.sub(r"\s+", " ", str(edition)).strip() if edition else None
    if edition_text and edition_text.startswith("Microsoft "):
        edition_text = edition_text[len("Microsoft "):]
    build = probe_value(probe, "build_ubr")
    viewer = probe_value(probe, "viewer_version")
    return {
        "os_edition": edition_text,
        "build_ubr": str(build) if build else None,
        "resolution": str(resolution) if resolution else None,
        "dpi": int(dpi) if dpi is not None else None,
        "viewer_version": str(viewer) if viewer else None,
    }


def _edition_matches(actual, expected):
    """같거나, 뒤에 연도 표기만 붙은 경우(예: "... LTSC 2024")를 같은 에디션으로 본다.

    단순 접두어 비교는 "Windows 11 Pro"와 "Windows 11 Pro for Workstations"를
    같다고 판정하므로 쓰지 않는다.
    """
    a, e = normalize_edition(actual), normalize_edition(expected)
    if a == e:
        return True
    return bool(a.startswith(e + " ") and re.fullmatch(r"\d{4}", a[len(e) + 1:]))


def _build_matches(actual, expected):
    """등록값에 점이 없으면 빌드 번호만, 있으면 UBR까지 정확히 비교한다."""
    a, e = str(actual).strip(), str(expected).strip()
    if "." in e:
        return a == e
    return a.split(".", 1)[0] == e


def _field_matches(field, actual, expected):
    if field == "os_edition":
        return _edition_matches(actual, expected)
    if field == "build_ubr":
        return _build_matches(actual, expected)
    if field == "dpi":
        try:
            return int(actual) == int(expected)
        except (TypeError, ValueError):
            return False
    return str(actual).strip() == str(expected).strip()


def differences(fp, entry):
    """등록 항목과 다른 필드 목록. 등록값이 null이면 그 필드는 비교하지 않는다."""
    out = []
    for field in FIELDS:
        expected = entry.get(field)
        if expected is None:
            continue
        actual = fp.get(field)
        if actual is None:
            out.append({"field": field, "actual": None, "expected": expected,
                        "text": f"{FIELD_LABELS[field]}: 조회 불가 (등록 {expected})"})
        elif not _field_matches(field, actual, expected):
            out.append({"field": field, "actual": actual, "expected": expected,
                        "text": f"{FIELD_LABELS[field]}: 실제 {actual} / 등록 {expected}"})
    return out


def match(fp, entries):
    """지문을 등록 항목과 대조한다.

    반환: `{"status": "verified"|"unregistered", "matched": entry|None,
    "differences": [...], "closest": entry|None}`. 미등록이면 차이가 가장 적은
    항목과의 차이를 `differences`에 싣는다.
    """
    entries = list(entries or [])
    best, best_diff = None, None
    for entry in entries:
        diff = differences(fp, entry)
        if not diff:
            return {"status": "verified", "matched": entry, "differences": [],
                    "closest": entry}
        if best_diff is None or len(diff) < len(best_diff):
            best, best_diff = entry, diff
    if best is None:
        best_diff = [{"field": None, "actual": None, "expected": None,
                      "text": "검증된 환경 목록이 비어 있음"}]
    return {"status": "unregistered", "matched": None, "differences": best_diff,
            "closest": best}


def data_path():
    """등록 목록 파일 위치. 배포판은 실행 자료 폴더(`BELLALUN_RESOURCE_DIR`)를 먼저 본다."""
    resource = os.environ.get("BELLALUN_RESOURCE_DIR")
    if resource and (Path(resource) / DATA_FILE).is_file():
        return Path(resource) / DATA_FILE
    return Path(__file__).resolve().parent.parent / DATA_FILE


def load_entries(path=None):
    """등록 항목 목록. 파일이 없거나 형식이 깨졌으면 빈 목록(= 모든 PC가 미등록)."""
    path = Path(path) if path else data_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else data
    return [e for e in (entries or []) if isinstance(e, dict)]


def describe(result):
    """한 줄 설명. 예: "검증됨 (win11-pro-26200)" / "미등록 환경: OS 빌드: ..."."""
    if result.get("status") == "verified":
        entry = result.get("matched") or {}
        return f"검증됨 ({entry.get('id') or entry.get('os_edition')})"
    texts = [d["text"] for d in result.get("differences") or []]
    closest = result.get("closest") or {}
    near = f" [가장 가까운 등록: {closest.get('id')}]" if closest.get("id") else ""
    return "미등록 환경: " + ("; ".join(texts) or "차이 불명") + near
