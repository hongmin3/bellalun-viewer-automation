"""BellalunAuto 표시 버전과 Windows 숫자형 버전."""
import re

_BASE_VERSION = r"[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}"
DISPLAY_VERSION = rf"{_BASE_VERSION}(?:\.[0-9]{{3}})?"
ARCHIVED_DISPLAY_VERSION = rf"{_BASE_VERSION}(?:\.(?:[0-9]{{3}}|\([0-9]{{3}}\)))?"


def is_development_version(display):
    return isinstance(display, str) and display.count(".") == 3


def windows_version(display, *, allow_legacy=False):
    """정식은 A.B.C.0, 개발 검증판은 A.B.C.N 숫자형 버전으로 바꾼다."""
    pattern = ARCHIVED_DISPLAY_VERSION if allow_legacy else DISPLAY_VERSION
    if not isinstance(display, str) or not re.fullmatch(pattern, display):
        raise ValueError("BellalunAuto 버전 형식 오류")
    major, minor, patch, *build = display.split(".")
    parts = [int(value) for value in (major, minor, patch)]
    revision = int(build[0].strip("()")) if build else 0
    if any(value > 65535 for value in parts) or (build and not revision):
        raise ValueError("BellalunAuto 버전 범위 오류")
    return ".".join(str(value) for value in (*parts, revision))
