# -*- coding: utf-8 -*-
"""실시간 WU 체인의 단계별 시간 상한·응답 없음 감지·저장점·재개 (REQ-WU-002).

`run.py run-winupdate`는 기준 DB 복원부터 WU_10까지 한 시간 반 넘게 걸린다. 한 단계가
멈추면 그 뒤 단계가 전부 막히고, 중간에 PC나 세션이 끊기면 처음부터 다시 해야 했다.
이 모듈은 체인 실행 코드(`run.py`)가 쓰는 세 가지를 맡는다.

1. 단계 감시(`run_stage`): 단계마다 시간 상한을 두고, Viewer가 계속 응답하지 않는지
   (`SendMessageTimeoutW` + `SMTO_ABORTIFHUNG`) 본다. 넘으면 Viewer를 끝내고 그 단계의
   TC를 BLOCKED와 사유로 남긴다. 다음 단계는 USB 실패 뒤와 같이 Viewer를 다시 띄워 계속한다.
2. 저장점(`Checkpoint`): 단계가 끝날 때마다 `work/winupdate_checkpoint.json`에 결과를
   원자적으로 쓴다(임시 파일 → `os.replace`). 내용 해시와 체인 구성을 함께 적어 손상되거나
   다른 체인의 저장점은 거부한다.
3. 절전 방지(`keep_awake`): 실행 중 PC가 절전이나 화면 꺼짐으로 들어가지 않게 한다.

시계·프로세스·응답 검사는 모두 주입할 수 있어 단위시험이 실제 Viewer 없이 돈다.
ctypes 함수 원형은 공유 `ctypes.windll`이 아니라 이 모듈 전용 `WinDLL` 사본에만 붙인다.
"""
import contextlib
import hashlib
import json
import os
import tempfile
import threading
import time
from datetime import datetime

SCHEMA = 1
CHECKPOINT_NAME = "winupdate_checkpoint.json"

#: 단계별 시간 상한(초). 후보8·10·11 실측 체인 전체가 1시간 40분 안팎이었고 가장 긴 단계도
#: 30분을 넘지 않았다. 정상 실행을 끊지 않도록 실측의 두 배 이상으로 둔다.
#: `config.json > winupdate.stage_timeouts`로 단계별로 바꿀 수 있다.
DEFAULT_TIMEOUT = 30 * 60
STAGE_TIMEOUTS = {
    "AUTOMATION_ENVIRONMENT_RESET": 15 * 60,
    "TC_Basic_Install_01": 10 * 60,
    "TC_Basic_Install_02": 10 * 60,
    "DICOM_Server_Setup": 20 * 60,
    "TC_Basic_WorkFlow_02": 45 * 60,
    "TC_XIPL_compatibility_subset": 60 * 60,
    "TC_Basic_WorkFlow_14": 45 * 60,
    "WU09_USB": 30 * 60,
    "TC_WindowsUpdate_10": 60 * 60,
}
#: Viewer가 이 시간 동안 계속 응답하지 않으면 응답 없음으로 본다. 화면 전환·Import 같은
#: 긴 작업 중 잠깐 바쁜 것과 구분하려고 한 번의 검사로 정하지 않는다.
HANG_SECONDS = 120
POLL_SECONDS = 5
#: Viewer를 끝낸 뒤 단계 코드가 스스로 예외로 빠져나오기를 기다리는 시간.
KILL_GRACE_SECONDS = 90

#: 한 단계가 만드는 TC 결과. 상한을 넘으면 이 ID마다 BLOCKED 결과를 만든다.
STAGE_OUTPUTS = {
    "TC_XIPL_compatibility_subset": [
        ("TC_XIPL_compatibility_02", "Viewer 2D Image Processing"),
        ("TC_XIPL_compatibility_03", "Viewer 3D Post Reconstruction"),
        ("TC_XIPL_compatibility_04", "Preset별 2D Default Parameter"),
        ("TC_XIPL_compatibility_06", "XIPL Parameter 저장 후 Viewer 적용"),
        ("TC_XIPL_compatibility_07", "XIPL Parameter 적용"),
    ],
}


def stage_timeout(stage_id, cfg=None):
    """설정값을 우선하는 단계 시간 상한(초)."""
    overrides = ((cfg or {}).get("winupdate") or {}).get("stage_timeouts") or {}
    value = overrides.get(stage_id, STAGE_TIMEOUTS.get(stage_id, DEFAULT_TIMEOUT))
    try:
        value = float(value)
    except (TypeError, ValueError):
        return float(STAGE_TIMEOUTS.get(stage_id, DEFAULT_TIMEOUT))
    return value if value > 0 else float(DEFAULT_TIMEOUT)


# ---------------------------------------------------------------------
# 절전 방지
# ---------------------------------------------------------------------
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
_KEEP = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
_awake_lock = threading.Lock()
_awake_depth = 0


def _set_execution_state(flags):
    if os.name != "nt":
        return 0
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
    kernel.SetThreadExecutionState.restype = ctypes.c_uint32
    return kernel.SetThreadExecutionState(flags)


@contextlib.contextmanager
def keep_awake(setter=None):
    """with 블록 동안 절전·화면 꺼짐을 막고 끝나면(예외가 나도) 원래대로 되돌린다.

    Windows 전원 설정은 바꾸지 않는다. 겹쳐 불러도 가장 바깥 블록이 끝날 때만 푼다.
    설정 실패는 판정에 영향을 주지 않는다.
    """
    global _awake_depth
    setter = setter or _set_execution_state
    with _awake_lock:
        _awake_depth += 1
        first = _awake_depth == 1
    if first:
        try:
            setter(_KEEP)
        except Exception:                                 # noqa: BLE001
            pass
    try:
        yield
    finally:
        with _awake_lock:
            _awake_depth -= 1
            last = _awake_depth == 0
        if last:
            try:
                setter(ES_CONTINUOUS)
            except Exception:                             # noqa: BLE001
                pass


# ---------------------------------------------------------------------
# Viewer 응답 검사
# ---------------------------------------------------------------------
def _user32():
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL("user32", use_last_error=True)
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsWindowVisible.restype = wintypes.BOOL
    user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                         wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                         ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    return user, enum_proc


def viewer_responding(pid, timeout_ms=5000):
    """Viewer 최상위 창이 메시지에 답하면 True, 응답 없음이면 False, 창이 없으면 None."""
    if not pid or os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    user, enum_proc = _user32()
    windows = []

    def collect(hwnd, _lparam):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(hwnd):
            windows.append(hwnd)
        return True

    user.EnumWindows(enum_proc(collect), 0)
    if not windows:
        return None
    WM_NULL, SMTO_ABORTIFHUNG = 0x0000, 0x0002
    answer = ctypes.c_size_t()
    for hwnd in windows:
        if user.SendMessageTimeoutW(hwnd, WM_NULL, 0, 0, SMTO_ABORTIFHUNG,
                                    timeout_ms, ctypes.byref(answer)):
            return True
    return False


_viewer_ui = None


def _viewer_pid():
    # ViewerUi.pid 는 살아 있는 PID 를 기억하고 죽었을 때만 다시 찾는다. 감시 스레드가
    # 5초마다 부르므로 매번 새 객체(=PowerShell 조회)를 만들지 않는다.
    global _viewer_ui
    from core.ui import ViewerUi
    if _viewer_ui is None:
        _viewer_ui = ViewerUi()
    return _viewer_ui.pid


def _kill_viewer():
    pid = _viewer_pid()
    if pid:
        from core import flows
        flows._kill_viewer(pid)
    return pid


# ---------------------------------------------------------------------
# 단계 감시
# ---------------------------------------------------------------------
class StageTimeout(Exception):
    """감시자가 단계를 끊었음을 단계 코드 안으로 알리는 신호."""


class StageMonitor:
    """한 단계를 감시하는 스레드. 상한 초과나 계속된 응답 없음이면 `on_trip`을 부른다."""

    def __init__(self, stage_id, timeout, *, clock=time.monotonic, responding=None,
                 pid_getter=None, hang_seconds=HANG_SECONDS, poll=POLL_SECONDS,
                 on_trip=None, sleep=None):
        self.stage_id = stage_id
        self.timeout = timeout
        self.clock = clock
        self.responding = responding or viewer_responding
        self.pid_getter = pid_getter or _viewer_pid
        self.hang_seconds = hang_seconds
        self.poll = poll
        self.on_trip = on_trip
        self.reason = None
        self.kind = None
        self._stop = threading.Event()
        self._sleep = sleep or self._stop.wait
        self._started = None
        self._hung_since = None
        self._thread = None

    def check_once(self):
        """한 번 검사한다. 끊어야 하면 (kind, reason)을 돌려준다."""
        now = self.clock()
        elapsed = now - self._started
        if elapsed >= self.timeout:
            return "timeout", (f"단계 시간 상한 {self.timeout / 60:.0f}분을 넘었다"
                               f"(경과 {elapsed / 60:.1f}분).")
        try:
            state = self.responding(self.pid_getter())
        except Exception:                                 # noqa: BLE001
            state = None
        if state is False:
            if self._hung_since is None:
                self._hung_since = now
            if now - self._hung_since >= self.hang_seconds:
                return "hang", (f"Viewer가 {now - self._hung_since:.0f}초 동안 계속 응답하지 "
                                "않았다(SendMessageTimeoutW, SMTO_ABORTIFHUNG).")
        else:
            self._hung_since = None
        return None

    def _loop(self):
        while not self._stop.is_set():
            tripped = self.check_once()
            if tripped:
                self.kind, self.reason = tripped
                if self.on_trip:
                    try:
                        self.on_trip(self)
                    except Exception:                     # noqa: BLE001
                        pass
                return
            self._sleep(self.poll)

    def start(self):
        self._started = self.clock()
        self._thread = threading.Thread(target=self._loop, name=f"wu-stage-{self.stage_id}",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.poll * 2))


def blocked_results(stage_id, title, kind, reason):
    """상한을 넘은 단계의 TC마다 BLOCKED 결과를 만든다."""
    from core.result import TCResult
    outputs = STAGE_OUTPUTS.get(stage_id) or [(stage_id, title)]
    label = "단계 시간 상한 초과" if kind == "timeout" else "Viewer 응답 없음"
    produced = []
    for tc_id, tc_title in outputs:
        r = TCResult(tc_id, tc_title)
        r.blocked(
            0, f"{stage_id} {label}",
            f"{reason} 감시자가 Viewer를 끝내고 이 단계를 중단했다. 이 단계의 판정 근거는 "
            "모으지 못했다.\n해제 조건: 원인을 확인한 뒤 `run-winupdate --resume`으로 이 "
            "단계부터 다시 실행한다.\n이 실행으로 말할 수 없는 것: 이 단계 TC의 제품 동작.",
            expected="단계가 시간 상한 안에 끝나고 Viewer가 응답한다",
            actual={"kind": kind, "reason": reason})
        produced.append(r)
    return produced


def run_stage(fn, ctx, stage_id, title, *, guarded, timeout=None, monitor_factory=None,
              kill=None, interrupt=None, grace=KILL_GRACE_SECONDS, before_kill=None):
    """단계 하나를 감시하며 실행한다.

    반환: (produced, trip). trip은 끊지 않았으면 None, 끊었으면
    {"kind": "timeout"|"hang", "reason": str}.

    단계 코드는 주 스레드에서 그대로 돈다(UI 자동화는 스레드를 옮기면 동작이 달라진다).
    감시 스레드가 상한을 감지하면 먼저 Viewer를 끝내 UI 호출이 빨리 실패하게 하고,
    그래도 `grace`초 안에 돌아오지 않으면 주 스레드에 중단 신호를 보낸다.
    `before_kill(monitor)`는 Viewer를 끝내기 전에 불러 실패 증거(핸들 수 등)를 남긴다.
    """
    import _thread
    kill = kill or _kill_viewer
    interrupt = interrupt or _thread.interrupt_main
    timeout = timeout if timeout is not None else stage_timeout(stage_id, getattr(ctx, "cfg", None))
    tripped = threading.Event()
    returned = threading.Event()
    handoff = threading.Lock()

    def on_trip(monitor):
        tripped.set()
        if before_kill is not None:
            try:
                before_kill(monitor)
            except Exception:                             # noqa: BLE001
                pass
        try:
            kill()
        except Exception:                                 # noqa: BLE001
            pass
        if not returned.wait(grace):
            # 주 스레드가 단계를 끝낸 뒤에는 중단 신호를 보내지 않는다(아래 finally 와 같은 잠금).
            with handoff:
                if not returned.is_set():
                    interrupt()

    factory = monitor_factory or StageMonitor
    monitor = factory(stage_id, timeout, on_trip=on_trip)
    monitor.start()
    produced = None
    try:
        try:
            produced = guarded(fn, ctx, stage_id, title)
        except KeyboardInterrupt:
            if not tripped.is_set():
                raise
    finally:
        with handoff:
            returned.set()
        monitor.stop()
    if tripped.is_set():
        trip = {"kind": monitor.kind or "timeout",
                "reason": monitor.reason or "단계 감시자가 중단했다."}
        return blocked_results(stage_id, title, trip["kind"], trip["reason"]), trip
    return produced or [], None


# ---------------------------------------------------------------------
# 저장점
# ---------------------------------------------------------------------
class CheckpointError(Exception):
    """저장점을 믿을 수 없어 재개를 거부한다."""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")


def chain_identity(stage_ids):
    """체인 구성(단계 순서)이 같을 때만 저장점을 재사용한다."""
    return hashlib.sha256(_canonical({"schema": SCHEMA, "stages": list(stage_ids)})).hexdigest()


def checkpoint_path(root):
    return os.path.join(root, "work", CHECKPOINT_NAME)


def _as_view(result):
    return result.as_dict() if hasattr(result, "as_dict") else result


class Checkpoint:
    """단계 결과를 단계가 끝날 때마다 원자적으로 기록하는 저장점."""

    def __init__(self, path, identity, payload=None):
        self.path = path
        self.identity = identity
        self.payload = payload or {
            "schema": SCHEMA, "identity": identity,
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "stages": {}, "order": [], "extras": {}, "resumes": [],
        }

    # --- 읽기 ---------------------------------------------------------
    @classmethod
    def load(cls, path, identity):
        """저장점을 읽는다. 없거나 손상됐거나 다른 체인이면 CheckpointError."""
        if not os.path.isfile(path):
            raise CheckpointError(f"재개할 저장점이 없습니다: {path}")
        try:
            with open(path, encoding="utf-8") as stream:
                envelope = json.load(stream)
        except (OSError, ValueError) as exc:
            raise CheckpointError(f"저장점을 읽을 수 없습니다({type(exc).__name__}).") from exc
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "sha256"}:
            raise CheckpointError("저장점 형식이 다릅니다.")
        payload = envelope["payload"]
        if hashlib.sha256(_canonical(payload)).hexdigest() != envelope["sha256"]:
            raise CheckpointError("저장점 내용 해시가 맞지 않습니다(손상 또는 수정됨).")
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
            raise CheckpointError("저장점 판(schema)이 다릅니다.")
        if payload.get("identity") != identity:
            raise CheckpointError("저장점의 체인 구성이 현재 체인과 다릅니다.")
        stages = payload.get("stages")
        if not isinstance(stages, dict) or not isinstance(payload.get("order"), list):
            raise CheckpointError("저장점의 단계 기록이 잘못되었습니다.")
        for stage_id, entry in stages.items():
            results = entry.get("results") if isinstance(entry, dict) else None
            if not isinstance(results, list) or not all(
                    isinstance(item, dict) and item.get("tc_id")
                    and isinstance(item.get("checks"), list) for item in results):
                raise CheckpointError(f"저장점의 {stage_id} 결과가 잘못되었습니다.")
        if payload.get("finished"):
            raise CheckpointError("이미 끝난 체인의 저장점입니다. 새로 실행하십시오.")
        return cls(path, identity, payload)

    # --- 쓰기 ---------------------------------------------------------
    def save(self):
        folder = os.path.dirname(self.path)
        os.makedirs(folder, exist_ok=True)
        self.payload["updated"] = datetime.now().astimezone().isoformat(timespec="seconds")
        # 해시와 저장 내용을 같은 직렬화로 맞춘다(default=str 변환 결과를 저장한다).
        payload = json.loads(_canonical(self.payload).decode("utf-8"))
        envelope = {"payload": payload,
                    "sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
        fd, temporary = tempfile.mkstemp(prefix="winupdate_checkpoint_", suffix=".tmp",
                                         dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(envelope, stream, ensure_ascii=False, indent=1)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.payload = payload

    def complete(self, stage_id, results, *, trip=None):
        self.payload["stages"][stage_id] = {
            "results": [_as_view(r) for r in results],
            "completed": datetime.now().astimezone().isoformat(timespec="seconds"),
            "trip": trip,
        }
        if stage_id not in self.payload["order"]:
            self.payload["order"].append(stage_id)
        self.save()

    def set_extra(self, key, value):
        self.payload["extras"][key] = _as_view(value)
        self.save()

    def mark_resumed(self):
        self.payload["resumes"].append(datetime.now().astimezone().isoformat(timespec="seconds"))
        self.save()

    def finish(self):
        self.payload["finished"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self.save()

    # --- 조회 ---------------------------------------------------------
    def done(self, stage_id):
        return stage_id in self.payload["stages"]

    def results(self, stage_id):
        return list(self.payload["stages"][stage_id]["results"])

    def extra(self, key, default=None):
        return self.payload["extras"].get(key, default)

    @property
    def completed_stages(self):
        return list(self.payload["order"])

    @property
    def resume_count(self):
        return len(self.payload["resumes"])


def set_aside(path):
    """재개하지 않는 새 실행 전에 남은 저장점을 지우지 않고 옆으로 옮긴다."""
    if not os.path.isfile(path):
        return None
    target = f"{path}.{datetime.now():%Y%m%d_%H%M%S}.old"
    os.replace(path, target)
    return target


def result_from_dict(data):
    """저장점의 결과 dict를 리포트용 TCResult로 되살린다(WU_10처럼 객체가 필요한 곳)."""
    from core.result import Check, TCResult
    r = TCResult(data["tc_id"], data.get("title") or data["tc_id"])
    for item in data.get("checks") or []:
        r.checks.append(Check(item.get("step"), item.get("title"), item.get("status"),
                              item.get("expected_data", item.get("expected", "")),
                              item.get("actual_data", item.get("actual", "")),
                              item.get("note", ""),
                              blocks_verdict=item.get("blocks_verdict")))
    r.evidence = list(data.get("evidence") or [])
    r.timings = list(data.get("timings") or [])
    for key, attr in (("started", "started"), ("completed", "completed")):
        try:
            setattr(r, attr, datetime.fromisoformat(data[key]))
        except (KeyError, TypeError, ValueError):
            pass
    r._step_cursor_wall = r.started
    r.reused_from_checkpoint = True
    return r
