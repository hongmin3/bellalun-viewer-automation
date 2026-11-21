"""BellalunAuto display and Windows PE version names."""
import re

DISPLAY_VERSION = r"[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}(?:\.\([0-9]{3}\))?"


def windows_version(display):
    """Map a release to A.B.C.0 and a development version to A.B.C.N."""
    if not isinstance(display, str) or not re.fullmatch(DISPLAY_VERSION, display):
        raise ValueError("BellalunAuto 버전 형식 오류")
    base, _, number = display.partition(".(")
    parts = [int(value) for value in base.split(".")]
    revision = int(number[:-1]) if number else 0
    if any(value > 65535 for value in parts) or (number and not revision):
        raise ValueError("BellalunAuto 버전 범위 오류")
    return ".".join(str(value) for value in (*parts, revision))
