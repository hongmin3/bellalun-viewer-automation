# -*- coding: utf-8 -*-
"""Windows Update 전후 근거 수집과 변화 감지 (`update-watch`).

이 PC의 OS 빌드(빌드.UBR)·설치된 KB 목록·마지막 업데이트 설치 시각을 모아
`work/update-evidence/history.jsonl`에 한 줄씩 쌓고, 직전 기록과 비교해
업데이트 전/후 표를 만든다. 빌드나 KB가 바뀐 경우에만 Windows Update 호환성
체크리스트(`run-winupdate`)를 한 번 돌린다.

판단 규칙
- 첫 기록(직전 기록 없음)은 "기준 없음"이다. 비교할 대상이 없으므로 변화로 보지 않고
  기준만 저장하며 `run-winupdate`를 돌리지 않는다.
- 빌드 비교는 `build_full`(빌드.UBR)로 한다. 어느 한쪽 값이 비어 있으면 비교하지 않는다.
- KB 비교는 두 기록 모두 KB 수집에 성공했을 때만 한다. 한쪽이 실패(`kb_error`)했는데
  목록 차이로 보면 "전부 제거됨"으로 잘못 감지해 체크리스트를 돌리게 되기 때문이다.
- `run-winupdate`가 예외로 끝나거나 프로세스가 죽어도 근거 기록은 남는다(실행 **전에** 저장).
  다음 감시는 그 기록을 기준으로 비교하므로 같은 변화로 다시 돌리지 않는다. 실패한 실행은
  `run_result` 줄과 반환값으로 알리고, 다시 돌릴지는 사람이 정한다(실패 반복 실행 방지).

저장 형식 (`history.jsonl`, UTF-8, 한 줄 = JSON 객체 하나)
- 근거 기록: `{"schema": 1, "kind": "evidence", "collected_at", "os", "kbs", "kb_source",
  "kb_error", "last_update_installed", "last_update_source", "triggered"}`
- 실행 결과: `{"schema": 1, "kind": "run_result", "evidence_at", "finished_at",
  "exit_code", "error"}`
- 덧붙이기(append) 뒤 flush+fsync 한다. 파일 전체를 다시 쓰지 않으므로 지난 기록을
  잃을 위험이 없고, 중단으로 생길 수 있는 손상은 마지막 한 줄뿐이다. 그 줄은 읽을 때
  경고와 함께 건너뛰고, 다음 덧붙이기 전에 줄바꿈을 보충해 새 기록과 섞이지 않게 한다.

사용 예

    python -m core.update_evidence --show                 # 수집·비교만 (저장하지 않음)
    python -m core.update_evidence --record               # 수집해 기록에 덧붙인다
    python -m core.update_evidence --show --work-dir DIR  # 다른 작업 폴더 기준
"""

import argparse
import base64
import ctypes
import json
import os
import re
import subprocess
import sys
from datetime import datetime

SCHEMA = 1
TASK_NAME = "Bellalun_WU_UpdateWatch"
EVIDENCE_DIR = "update-evidence"
HISTORY_FILE = "history.jsonl"
HOTFIX_TIMEOUT = 60  # 초. Get-HotFix(WMI)가 멈춰도 수집 전체가 멈추지 않게 한다.

_NT_CURRENT = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
_WU_INSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\Results\Install"
_KB_RE = re.compile(r"KB\d{6,8}", re.I)

REPORT_HEADER = ("항목", "업데이트 전", "업데이트 후", "변화")


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --- 이 PC 조회 (읽기 전용) ------------------------------------------------------

class WindowsProbe:
    """실제 PC 조회. 테스트는 같은 메서드를 가진 가짜 객체를 `probe`로 넘긴다.

    `core.sysinfo.os_update_info()`는 PowerShell을 시간 제한 없이 부르고 에디션을 담지 않아
    여기서는 같은 레지스트리 키를 `winreg`로 직접 읽는다(빌드 실패 시 RtlGetVersion).
    """

    def __init__(self, runner=subprocess.run, timeout=HOTFIX_TIMEOUT):
        self.runner = runner
        self.timeout = timeout

    def os_version(self):
        values = {}
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _NT_CURRENT) as key:
                for name in ("CurrentBuild", "UBR", "DisplayVersion", "EditionID", "ProductName"):
                    try:
                        values[name] = winreg.QueryValueEx(key, name)[0]
                    except OSError:
                        pass
        except (ImportError, OSError):
            pass
        if not values.get("CurrentBuild"):
            rtl = _rtl_version()
            if rtl:
                values["CurrentBuild"] = str(rtl[2])
        return values

    def hotfixes(self):
        """`[{"id": "KB…", "installed_on": "YYYY-MM-DD"|None}]`. 실패하면 RuntimeError."""
        script = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                  "@(Get-HotFix -ErrorAction Stop | ForEach-Object { [pscustomobject]@{"
                  " id=$_.HotFixID; on=$(if ($_.InstalledOn) { $_.InstalledOn.ToString('yyyy-MM-dd') }) } })"
                  " | ConvertTo-Json -Compress")
        try:
            proc = self.runner(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                               capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Get-HotFix 시간 초과(%d초)" % self.timeout)
        except OSError as exc:
            raise RuntimeError("PowerShell 실행 실패: %s" % exc)
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            raise RuntimeError("Get-HotFix 실패(코드 %s): %s" % (proc.returncode, err[0] if err else ""))
        out = (proc.stdout or b"").decode("utf-8", "replace").strip()
        if not out:
            return []
        data = json.loads(out)
        data = [data] if isinstance(data, dict) else data
        return [{"id": d.get("id") or "", "installed_on": d.get("on") or None} for d in data]

    def last_success_time(self):
        """WU 클라이언트가 남긴 마지막 설치 성공 시각(UTC 문자열). 최근 Windows에는 없을 수 있다."""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _WU_INSTALL) as key:
                return str(winreg.QueryValueEx(key, "LastSuccessTime")[0]) or None
        except (ImportError, OSError):
            return None


def _rtl_version():
    """(major, minor, build). 공용 `ctypes.windll`을 건드리지 않게 전용 ntdll 인스턴스를 쓴다."""
    class OSVERSIONINFOEXW(ctypes.Structure):
        _fields_ = [("dwOSVersionInfoSize", ctypes.c_ulong), ("dwMajorVersion", ctypes.c_ulong),
                    ("dwMinorVersion", ctypes.c_ulong), ("dwBuildNumber", ctypes.c_ulong),
                    ("dwPlatformId", ctypes.c_ulong), ("szCSDVersion", ctypes.c_wchar * 128),
                    ("wServicePackMajor", ctypes.c_ushort), ("wServicePackMinor", ctypes.c_ushort),
                    ("wSuiteMask", ctypes.c_ushort), ("wProductType", ctypes.c_byte),
                    ("wReserved", ctypes.c_byte)]
    try:
        ntdll = ctypes.WinDLL("ntdll")
        info = OSVERSIONINFOEXW()
        info.dwOSVersionInfoSize = ctypes.sizeof(info)
        if ntdll.RtlGetVersion(ctypes.byref(info)) != 0:
            return None
        return info.dwMajorVersion, info.dwMinorVersion, info.dwBuildNumber
    except (AttributeError, OSError):
        return None


def _product_name(raw, build):
    # Windows 11도 레지스트리 ProductName은 "Windows 10 …"으로 남아 있다(빌드 22000 이상이면 11).
    raw = str(raw or "")
    try:
        if int(build) >= 22000 and raw.startswith("Windows 10"):
            return "Windows 11" + raw[len("Windows 10"):]
    except (TypeError, ValueError):
        pass
    return raw


def _registry_time(value):
    """`2026-10-15 03:12:44`(UTC) → ISO 문자열. 형식이 다르면 원문."""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").isoformat() + "+00:00"
    except (AttributeError, ValueError):
        return value


def collect(probe=None):
    """이 PC의 근거 기록 하나를 만든다. 조회 실패는 예외 대신 기록에 남긴다."""
    probe = probe or WindowsProbe()
    try:
        raw = probe.os_version() or {}
    except Exception:                                                  # noqa: BLE001
        raw = {}
    build = str(raw.get("CurrentBuild") or "")
    ubr = raw.get("UBR")
    os_part = {
        "edition": str(raw.get("EditionID") or ""),
        "product_name": _product_name(raw.get("ProductName"), build),
        "display_version": str(raw.get("DisplayVersion") or ""),
        "build": build,
        "ubr": ubr,
        "build_full": "%s.%s" % (build, ubr) if build and ubr is not None else build,
    }

    hotfixes, kb_error = [], None
    try:
        hotfixes = probe.hotfixes() or []
    except Exception as exc:                                           # noqa: BLE001
        kb_error = str(exc) if isinstance(exc, RuntimeError) else "%s: %s" % (type(exc).__name__, exc)
    kbs = sorted({m.group(0).upper() for h in hotfixes for m in [_KB_RE.search(h.get("id") or "")] if m})

    last, last_source = None, "없음"
    try:
        reg = probe.last_success_time()
    except Exception:                                                  # noqa: BLE001
        reg = None
    if reg:
        last, last_source = _registry_time(reg), "registry:WindowsUpdate\\Auto Update\\Results\\Install\\LastSuccessTime (UTC)"
    else:
        dates = [h["installed_on"] for h in hotfixes if h.get("installed_on")]
        if dates:
            last, last_source = max(dates), "hotfix:InstalledOn 최댓값(날짜만)"

    return {
        "schema": SCHEMA,
        "kind": "evidence",
        "collected_at": _now(),
        "os": os_part,
        "kbs": kbs,
        "kb_source": "PowerShell Get-HotFix (Win32_QuickFixEngineering, 시간 제한 %d초)"
                     % getattr(probe, "timeout", HOTFIX_TIMEOUT),
        "kb_error": kb_error,
        "last_update_installed": last,
        "last_update_source": last_source,
    }


# --- 저장 ------------------------------------------------------------------------

def history_path(work_dir):
    return os.path.join(work_dir, EVIDENCE_DIR, HISTORY_FILE)


def _append(work_dir, obj):
    path = history_path(work_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n"
    with open(path, "ab+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell():
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":            # 중단으로 잘린 마지막 줄과 섞이지 않게
                line = "\n" + line
        f.write(line.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    return path


def save(record, work_dir):
    """근거 기록을 `history.jsonl`에 덧붙인다. 저장한 경로를 돌려준다."""
    return _append(work_dir, record)


def load_history(work_dir, log=None):
    """읽을 수 있는 모든 줄(dict). 손상된 줄은 경고하고 건너뛴다."""
    log = log or (lambda msg: print(msg, file=sys.stderr))
    path = history_path(work_dir)
    if not os.path.isfile(path):
        return []
    items = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for no, text in enumerate(f, 1):
            text = text.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except ValueError:
                log("경고: %s %d번째 줄을 읽지 못해 건너뜁니다." % (HISTORY_FILE, no))
                continue
            if isinstance(obj, dict):
                items.append(obj)
            else:
                log("경고: %s %d번째 줄이 기록 형식이 아니어서 건너뜁니다." % (HISTORY_FILE, no))
    return items


def load_last(work_dir, log=None):
    """마지막 근거 기록(`kind == "evidence"`). 없으면 None."""
    for obj in reversed(load_history(work_dir, log=log)):
        if obj.get("kind", "evidence") == "evidence" and isinstance(obj.get("os"), dict):
            return obj
    return None


# --- 비교 ------------------------------------------------------------------------

def _kb_text(kbs):
    return ", ".join(kbs) if kbs else "-"


def compare(previous, current):
    """직전 기록과 현재 기록의 차이. `previous`가 없으면 첫 기록(기준 없음)."""
    cur_os = current.get("os") or {}
    if not previous:
        rows = [
            ("OS 제품", "기준 없음", cur_os.get("product_name") or "-", "기준 없음"),
            ("OS 표시 버전", "기준 없음", cur_os.get("display_version") or "-", "기준 없음"),
            ("OS 빌드", "기준 없음", cur_os.get("build_full") or "-", "기준 없음"),
            ("설치된 KB 수", "기준 없음",
             "확인 불가" if current.get("kb_error") else str(len(current.get("kbs") or [])), "기준 없음"),
            ("마지막 업데이트 설치", "기준 없음", current.get("last_update_installed") or "-", "기준 없음"),
            ("기록 시각", "기준 없음", current.get("collected_at") or "-", "기준 없음"),
        ]
        return {"changed": False, "build_changed": False, "kb_added": [], "kb_removed": [],
                "kb_comparable": False, "build_comparable": False, "rows": rows,
                "first_record": True, "previous": None, "current": current}

    prev_os = previous.get("os") or {}
    pb, cb = prev_os.get("build_full") or "", cur_os.get("build_full") or ""
    build_comparable = bool(pb and cb)
    build_changed = build_comparable and pb != cb
    kb_comparable = not previous.get("kb_error") and not current.get("kb_error")
    pk, ck = set(previous.get("kbs") or []), set(current.get("kbs") or [])
    added = sorted(ck - pk) if kb_comparable else []
    removed = sorted(pk - ck) if kb_comparable else []

    def mark(before, after, comparable=True):
        if not comparable:
            return "확인 불가"
        return "변경" if before != after else "동일"

    def kb_count(rec):
        return "확인 불가" if rec.get("kb_error") else str(len(rec.get("kbs") or []))

    rows = [
        ("OS 제품", prev_os.get("product_name") or "-", cur_os.get("product_name") or "-",
         mark(prev_os.get("product_name"), cur_os.get("product_name"))),
        ("OS 표시 버전", prev_os.get("display_version") or "-", cur_os.get("display_version") or "-",
         mark(prev_os.get("display_version"), cur_os.get("display_version"))),
        ("OS 빌드", pb or "-", cb or "-", mark(pb, cb, build_comparable)),
        ("설치된 KB 수", kb_count(previous), kb_count(current), mark(pk, ck, kb_comparable)),
        ("추가된 KB", "-", _kb_text(added) if kb_comparable else "확인 불가",
         ("변경" if added else "없음") if kb_comparable else "확인 불가"),
        ("제거된 KB", _kb_text(removed) if kb_comparable else "확인 불가", "-",
         ("변경" if removed else "없음") if kb_comparable else "확인 불가"),
        ("마지막 업데이트 설치", previous.get("last_update_installed") or "-",
         current.get("last_update_installed") or "-",
         mark(previous.get("last_update_installed"), current.get("last_update_installed"))),
        ("기록 시각", previous.get("collected_at") or "-", current.get("collected_at") or "-", "-"),
    ]
    return {"changed": bool(build_changed or added or removed), "build_changed": build_changed,
            "kb_added": added, "kb_removed": removed, "kb_comparable": kb_comparable,
            "build_comparable": build_comparable, "rows": rows, "first_record": False,
            "previous": previous, "current": current}


def report_rows(comparison):
    """WU 보고서의 "업데이트 전/후" 표. 첫 행은 머리글(`REPORT_HEADER`)."""
    return [list(REPORT_HEADER)] + [list(r) for r in comparison["rows"]]


def meta_summary(comparison):
    """JSON/HTML 메타에 실을 평탄한 dict."""
    prev = comparison.get("previous") or {}
    cur = comparison.get("current") or {}
    return {
        "update_evidence_first_record": comparison["first_record"],
        "update_evidence_changed": comparison["changed"],
        "update_evidence_build_changed": comparison["build_changed"],
        "os_build_before": (prev.get("os") or {}).get("build_full", "") if prev else "",
        "os_build_after": (cur.get("os") or {}).get("build_full", ""),
        "kb_count_before": len(prev.get("kbs") or []) if prev else None,
        "kb_count_after": len(cur.get("kbs") or []),
        "kb_added": ", ".join(comparison["kb_added"]),
        "kb_removed": ", ".join(comparison["kb_removed"]),
        "kb_error": cur.get("kb_error") or "",
        "last_update_installed": cur.get("last_update_installed") or "",
        "last_update_source": cur.get("last_update_source") or "",
        "evidence_before_at": prev.get("collected_at", "") if prev else "",
        "evidence_after_at": cur.get("collected_at", ""),
    }


# --- update-watch ----------------------------------------------------------------

def watch(work_dir, run_winupdate, probe=None, log=None):
    """수집 → 직전 기록과 비교 → 저장 → 변화가 있을 때만 `run_winupdate()`를 한 번 부른다.

    근거 기록은 실행 **전에** 저장한다(실행이 죽어도 남는다). 실행 결과는 별도 `run_result`
    줄로 덧붙인다. `run_winupdate`의 예외는 다시 던지지 않고 `error`로 돌려준다.
    """
    current = collect(probe)
    previous = load_last(work_dir, log=log)
    comparison = compare(previous, current)
    if comparison["first_record"]:
        reason = "첫 기록 — 기준만 저장하고 체크리스트는 돌리지 않습니다."
    elif comparison["changed"]:
        parts = []
        if comparison["build_changed"]:
            parts.append("빌드 %s → %s" % (previous["os"].get("build_full"), current["os"].get("build_full")))
        if comparison["kb_added"]:
            parts.append("KB 추가 " + _kb_text(comparison["kb_added"]))
        if comparison["kb_removed"]:
            parts.append("KB 제거 " + _kb_text(comparison["kb_removed"]))
        reason = "변화 감지 — " + "; ".join(parts)
    else:
        reason = "변화 없음 — 체크리스트를 돌리지 않습니다."
        if not comparison["kb_comparable"]:
            reason += " (KB 목록은 수집 실패로 비교하지 못했습니다.)"

    trigger = comparison["changed"]
    current["triggered"] = trigger
    save(current, work_dir)
    result = {"ran": False, "reason": reason, "comparison": comparison, "exit_code": None, "error": None}
    if not trigger:
        return result

    result["ran"] = True
    try:
        result["exit_code"] = run_winupdate()
    except BaseException as exc:                                      # noqa: BLE001
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        if not isinstance(exc, Exception):
            _record_run(work_dir, current, result)
            raise
    _record_run(work_dir, current, result)
    return result


def _record_run(work_dir, evidence, result):
    try:
        _append(work_dir, {"schema": SCHEMA, "kind": "run_result", "evidence_at": evidence["collected_at"],
                           "finished_at": _now(), "exit_code": result["exit_code"], "error": result["error"]})
    except OSError as exc:
        result["error"] = (result["error"] or "") + " / 실행 결과 기록 실패: %s" % exc


# --- 예약 작업 (명령만 만든다. 등록은 run.py가 --apply에서 한다) -------------------

def _ps_quote(value):
    return "'" + value.replace("'", "''") + "'"


def task_script(python_exe, run_py, schedule="daily", at="09:00"):
    """`run.py update-watch`를 도는 예약 작업 등록 스크립트(PowerShell).

    기본은 매일 `at` 시각(보수적 기본값). `schedule="logon"`이면 현재 사용자 로그온 시.
    UI 자동화가 데스크톱을 써야 하므로 대화형 로그온으로만 돌고, 꺼져 있어 놓친 실행은
    켜진 뒤 한 번 돈다. 체크리스트 체인이 길어 실행 제한은 4시간이다.
    """
    if schedule == "daily":
        if not re.fullmatch(r"\d{2}:\d{2}", at or ""):
            raise ValueError("at은 HH:MM 형식이어야 합니다: %r" % (at,))
        trigger = "$t = New-ScheduledTaskTrigger -Daily -At %s -RandomDelay (New-TimeSpan -Minutes 5)" % at
    elif schedule == "logon":
        trigger = ("$t = New-ScheduledTaskTrigger -AtLogOn -User "
                   "([Security.Principal.WindowsIdentity]::GetCurrent().Name)")
    else:
        raise ValueError("schedule은 'daily' 또는 'logon'이어야 합니다: %r" % (schedule,))
    arg = '"%s" update-watch' % run_py
    return "\n".join([
        "$a = New-ScheduledTaskAction -Execute %s -Argument %s -WorkingDirectory %s"
        % (_ps_quote(python_exe), _ps_quote(arg), _ps_quote(os.path.dirname(run_py))),
        trigger,
        "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries"
        " -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)",
        # run-winupdate 는 관리자 권한 gate 를 통과해야 하므로 가장 높은 권한으로 등록한다.
        # 화면을 조작하므로 로그온한 사용자의 대화형 세션에서만 실행한다.
        "$p = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
        " -LogonType Interactive -RunLevel Highest",
        "Register-ScheduledTask -TaskName %s -Action $a -Trigger $t -Settings $s -Principal $p -Description %s -Force"
        " | Out-Null" % (_ps_quote(TASK_NAME), _ps_quote(
            "Windows Update로 OS 빌드·KB가 바뀌면 Bellalun Viewer WU 체크리스트를 돌린다 (run.py update-watch)")),
    ])


def install_task_command(python_exe, run_py, schedule="daily", at="09:00"):
    encoded = base64.b64encode(task_script(python_exe, run_py, schedule, at).encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]


def remove_task_command():
    return ["schtasks", "/Delete", "/F", "/TN", TASK_NAME]


# --- CLI -------------------------------------------------------------------------

def format_table(rows):
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def main(argv=None):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = argparse.ArgumentParser(prog="python -m core.update_evidence",
                                description="Windows Update 전후 근거 수집과 비교")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--show", action="store_true", help="수집해 직전 기록과 비교만 한다(저장하지 않음)")
    g.add_argument("--record", action="store_true", help="수집해 기록에 덧붙인다")
    p.add_argument("--work-dir", default=os.path.join(here, "work"), help="작업 폴더(기본: 저장소 work/)")
    args = p.parse_args(argv)
    started = datetime.now()
    current = collect()
    elapsed = (datetime.now() - started).total_seconds()
    comparison = compare(load_last(args.work_dir), current)
    print(format_table(report_rows(comparison)))
    print("")
    print("KB 수집: %s — %s" % (current["kb_source"], "실패: " + current["kb_error"] if current["kb_error"]
                                else "%d건" % len(current["kbs"])))
    print("마지막 업데이트 설치 근거: %s" % current["last_update_source"])
    print("수집 소요: %.1f초" % elapsed)
    if comparison["first_record"]:
        print("판정: 첫 기록(기준 없음) — update-watch는 이 경우 체크리스트를 돌리지 않습니다.")
    else:
        print("판정: %s" % ("변화 있음" if comparison["changed"] else "변화 없음"))
    if args.record:
        print("저장: %s" % save(current, args.work_dir))
    else:
        print("저장하지 않았습니다(--show). 기록하려면 --record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
