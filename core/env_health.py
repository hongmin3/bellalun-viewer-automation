# -*- coding: utf-8 -*-
"""시험 환경을 다시 점검해 환경 장애를 제품 FAIL과 가른다 (REQ-VERDICT-005).

2026-11-23 1.0.0.007 회귀에서 시험 서버가 실행 도중 멈췄다. 그 결과 Storage·Print·MWL을 쓰는
TC 6개가 제품 FAIL로 기록됐다. 이 모듈은 다음을 맡는다.

1. TC마다 필요한 시험 환경(`TC_REQUIREMENTS`)을 정한다. TC 모듈이 실제로 서버를 호출하는 곳을
   기준으로 했고 `tests/test_env_health.py`가 모듈의 호출과 이 표가 맞는지 확인한다.
2. 환경을 점검한다(`check`). TCP 연결이 안 되거나 HTTP가 5xx면 "안 됨"이다.
3. 안 된 환경 때문에 생긴 FAIL을 BLOCKED로 바꾸고(`reclassify`), 이후 같은 환경이 필요한 TC는
   실행하지 않고 BLOCKED 한 건으로 남긴다(`blocked_result`).

연결 함수는 주입할 수 있어 단위시험이 실제 서버 없이 돈다.
"""
import socket
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlsplit

STORAGE, MWL, PRINT = "storage", "mwl", "print"
LABELS = {STORAGE: "Storage 서버", MWL: "MWL 서버", PRINT: "Print 서버"}

#: TC별 필요한 시험 환경. 근거: 각 TC 모듈의 서버 호출
#: (Storage: `send_verify`/`storagescp` 호출, MWL: `mwl` 사용, Print: `printscp` 사용).
TC_REQUIREMENTS = {
    "TC_Basic_WorkFlow_01": (MWL,),
    "TC_Basic_WorkFlow_04": (STORAGE,),
    "TC_Basic_WorkFlow_05": (STORAGE,),
    "TC_Basic_WorkFlow_06": (STORAGE,),
    "TC_Basic_WorkFlow_07": (STORAGE,),
    "TC_Basic_WorkFlow_08": (PRINT,),
    "TC_Basic_WorkFlow_10": (MWL,),
    "TC_Basic_WorkFlow_15": (STORAGE,),
}

TCP_TIMEOUT = 3
HTTP_TIMEOUT = 5


def required(tc_id):
    return TC_REQUIREMENTS.get(tc_id, ())


def _section(value):
    return value if isinstance(value, dict) else {}


def targets(cfg):
    """환경 이름 → 점검 대상 [(종류, 대상)] 목록. 설정에 없는 대상은 넣지 않는다."""
    dicom = _section((cfg or {}).get("dicom"))
    storage, print_scp = _section(dicom.get("storage_scp")), _section(dicom.get("print_scp"))
    registered = {str(s.get("kind", "")).lower(): s for s in dicom.get("servers_to_register") or []
                  if isinstance(s, dict)}
    out = {STORAGE: [], MWL: [], PRINT: []}

    def add(name, kind, value):
        if value and all(value if isinstance(value, tuple) else (value,)):
            out[name].append((kind, value))

    add(STORAGE, "http", storage.get("api_url"))
    add(STORAGE, "tcp", (storage.get("host"), storage.get("port")))
    add(MWL, "http", dicom.get("mwl_server_url"))
    mwl = registered.get("mwl") or {}
    add(MWL, "tcp", (mwl.get("ip"), mwl.get("port")))
    add(PRINT, "http", dicom.get("print_server_url"))
    add(PRINT, "tcp", (print_scp.get("host"), print_scp.get("port")))
    return out


def tcp_ok(host, port, timeout=TCP_TIMEOUT):
    try:
        with socket.create_connection((str(host), int(port)), timeout=timeout):
            return True, f"{host}:{port} 연결됨"
    except (OSError, ValueError) as exc:
        return False, f"{host}:{port} 연결 실패({type(exc).__name__}: {exc})"


def http_ok(url, timeout=HTTP_TIMEOUT):
    """서버가 응답하는지. 4xx는 서버가 살아 있는 것으로 본다. 5xx와 연결 실패는 안 됨이다."""
    parts = urlsplit(str(url))
    root = f"{parts.scheme}://{parts.netloc}/"
    try:
        with urllib.request.urlopen(root, timeout=timeout) as response:
            return True, f"{root} HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            return False, f"{root} HTTP {exc.code} 서버 오류"
        return True, f"{root} HTTP {exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, f"{root} 연결 실패({type(exc).__name__}: {exc})"


def check(cfg, names, *, tcp=tcp_ok, http=http_ok, now=None):
    """환경 이름마다 {"ok", "details", "checked_at"}. 점검 대상이 설정에 없으면 판단하지 않는다(ok)."""
    plan = targets(cfg)
    stamp = (now or datetime.now)().astimezone().isoformat(timespec="seconds")
    status = {}
    for name in dict.fromkeys(names):
        results = [tcp(*value) if kind == "tcp" else http(value) for kind, value in plan.get(name, [])]
        status[name] = {"ok": all(ok for ok, _ in results),
                        "details": [detail for _, detail in results] or ["설정에 점검 대상이 없음"],
                        "checked_at": stamp}
    return status


def down_of(status):
    return {name: value for name, value in status.items() if not value["ok"]}


def describe(down):
    """사람이 읽는 원인과 해제 조건."""
    labels = ", ".join(LABELS.get(name, name) for name in down)
    details = "; ".join(d for value in down.values() for d in value["details"] if "실패" in d or "오류" in d)
    cause = f"시험 환경 {labels} 응답 없음({details})" if details else f"시험 환경 {labels} 응답 없음"
    unblock = f"{labels} 복구를 확인한 뒤 이 TC를 다시 실행한다."
    return cause, unblock


def _environment_check(result, down, phase):
    from core.result import BLOCKED
    cause, unblock = describe(down)
    result.add(0, "시험 환경 재점검", BLOCKED, stop=False,
               expected="TC에 필요한 시험 환경이 응답한다",
               actual={name: value["details"] for name, value in down.items()},
               note=f"{cause}. {phase}\n해제 조건: {unblock}\n"
                    "이 실행으로 말할 수 없는 것: 이 TC의 제품 동작.")


def reclassify(result, down):
    """환경이 안 된 상태에서 나온 FAIL Step을 BLOCKED로 바꾼다. 바꾼 개수를 돌려준다."""
    from core.result import BLOCKED, FAIL
    if not down:
        return 0
    cause, unblock = describe(down)
    changed = 0
    for check_ in result.checks:
        if check_.status != FAIL:
            continue
        check_.status = BLOCKED
        original = str(check_.note or "").strip()
        check_.note = (f"원래 FAIL로 관찰한 내용이지만 {cause}이어서 제품 판정에서 뺐다."
                       + (f"\n원래 비고: {original}" if original else "")
                       + f"\n해제 조건: {unblock}")
        changed += 1
    _environment_check(result, down, "실패 직후 다시 점검했다.")
    return changed


NOT_STARTED_NOTE = "시작 전 다시 점검했고 실행하지 않았다."


def blocked_result(tc_id, title, down):
    """앞선 TC에서 안 된 환경이 아직 안 되면 이 TC는 제품을 조작하지 않고 BLOCKED로 남긴다."""
    from core.result import TCResult
    result = TCResult(tc_id, title)
    _environment_check(result, down, NOT_STARTED_NOTE)
    result.finalize()
    return result
