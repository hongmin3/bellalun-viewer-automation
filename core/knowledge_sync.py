# -*- coding: utf-8 -*-
"""상위 `지식/` 폴더를 검증 자료 관리 서버의 최신 판으로 맞춘다 (REQ-KNOW-001).

서버의 제품 화면(`/knowledge/products/<제품>`)에 보이는 문서가 기준이다. 다운로드 링크가 있는
문서는 HTTP로, 링크가 없는 QA 지침·Skill 지침은 SSH로 서버의 원본 저장소에서 받는다.

- 받은 파일은 먼저 `.staging/`에 두고 크기(SSH는 SHA-256도)가 맞을 때만 폴더에 넣는다.
- 같은 문서의 옛 판은 지우지 않고 `_이전판/<날짜>/`로 옮긴다. 서버에 없는 로컬 자료는 건드리지 않는다.
  이름이 다른 문서(예: 예전 분권 `사양서1`과 통합본 `사양서`)는 다른 문서로 보고 자동으로 옮기지 않는다.
- 판 표시(HTTP etag, SSH SHA-256)와 로컬 내용 SHA-256이 기록(`.sync-state.json`)과 같으면 다시 받지 않는다.
  서버 etag는 내용 해시가 아니므로 내용 비교는 받은 뒤에 한다.

같은 방식을 VXvue 저장소가 먼저 쓰고 있다(VXvue `core/knowledge_sync.py`). 두 저장소는 서로 의존하지 않는다.

사용 예

    python run.py sync-knowledge --dry-run      # 받아서 비교만 하고 폴더는 그대로
    python run.py sync-knowledge                # 실제로 맞춘다
    python run.py sync-knowledge --install-task --apply   # 평일 예약 작업 등록
"""

import base64
import hashlib
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
from datetime import date

TASK_NAME = "Bellalun_Knowledge_Sync"
KNOWLEDGE_DIR = "지식"
STATE_FILE = ".sync-state.json"
STAGING_DIR = ".staging"
ARCHIVE_DIR = "_이전판"
#: 제품 화면에 다운로드 링크가 없어 SSH로 받는 구역 (2026-11-04 서버 화면 실측)
SSH_KINDS = ("qa_rules", "skill_instruction", "instruction_prompt")


class SyncError(RuntimeError):
    pass


# --- 설정 ---------------------------------------------------------------------

def settings(cfg):
    """config.json의 `knowledge_sync` 절. 서버 주소는 코드에 두지 않는다(NFR-BOUNDARY-001)."""
    s = (cfg or {}).get("knowledge_sync") or {}
    url = (s.get("server_url") or "").strip().rstrip("/")
    if not url:
        raise SyncError("config.json에 knowledge_sync.server_url이 없다 (config.example.json 참고)")
    return {
        "server_url": url,
        "product": (s.get("product") or "bellalun-viewer").strip(),
        "ssh_target": (s.get("ssh_target") or "").strip(),
        "ssh_dir": (s.get("ssh_dir") or "").strip().rstrip("/"),
        "ssh_kinds": tuple(s.get("ssh_kinds") or SSH_KINDS),
        "timeout": int(s.get("timeout") or 60),
        "hosts": tuple(h.strip().upper() for h in (s.get("hosts") or []) if h.strip()),
    }


def host_name():
    return (os.environ.get("COMPUTERNAME") or "").strip().upper()


def check_host(s, host, uploader=""):
    """이 PC가 받는 쪽인지 확인한다. 지식 폴더를 서버로 올리는 PC에서 돌면 원본을 덮어쓴다."""
    host = (host or "").upper()
    if not s["hosts"]:
        raise SyncError("config.json knowledge_sync.hosts가 비어 있다. 받는 PC 이름(COMPUTERNAME)을 적어야 돈다")
    if host not in s["hosts"]:
        raise SyncError("이 PC(%s)는 knowledge_sync.hosts(%s)에 없어 돌지 않는다" % (host, ", ".join(s["hosts"])))
    if uploader and uploader.strip().upper() == host:
        raise SyncError("이 PC(%s)가 서버로 지식 폴더를 올리는 PC라 받아서 덮어쓰지 않는다" % host)


def knowledge_dir(cfg, repo_root):
    """`지식` 폴더. config의 `knowledge_dir`가 우선이고, 없으면 저장소 위로 올라가며 찾는다."""
    override = ((cfg or {}).get("knowledge_dir") or "").strip()
    if override:
        return os.path.abspath(override) if os.path.isdir(override) else ""
    here = os.path.abspath(repo_root)
    for _ in range(4):
        here = os.path.dirname(here)
        candidate = os.path.join(here, KNOWLEDGE_DIR)
        if os.path.isdir(candidate):
            return candidate
    return ""


# --- 서버 목록 ------------------------------------------------------------------

def parse_listing(page):
    """제품 화면 HTML → [{kind, name, id}]. id는 다운로드 번호이고 링크가 없으면 None이다."""
    docs = []
    for kind, body in re.findall(r'<section id="kind-([\w-]+)"[^>]*>(.*?)</section>', page, re.S):
        tbody = re.search(r"<tbody>(.*?)</tbody>", body, re.S)
        if not tbody:
            continue
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody.group(1), re.S):
            cell = re.search(r"<td[^>]*>(.*?)</td>", row, re.S)
            if not cell:
                continue
            link = re.search(r'href="/knowledge/download/(\d+)"', cell.group(1))
            name = html.unescape(re.sub(r"<[^>]+>", "", cell.group(1))).strip()
            if name:
                docs.append({"kind": kind, "name": name, "id": link.group(1) if link else None})
    if not docs:
        raise SyncError("서버 화면에서 문서 목록을 읽지 못했다 (화면 구조가 바뀌었거나 점검 중)")
    return docs


def attach_sources(docs, ssh_kinds=SSH_KINDS, ssh_ready=False):
    """문서마다 받는 길: http(다운로드 링크), ssh(링크 없는 지정 구역), None(받을 수 없음)."""
    out = []
    for d in docs:
        source = "http" if d.get("id") else ("ssh" if ssh_ready and d["kind"] in ssh_kinds else None)
        out.append(dict(d, source=source))
    return out


def safe_name(name):
    """폴더 안의 파일 하나만 가리키는 이름인가."""
    if not name or name.startswith(".") or name == ARCHIVE_DIR:
        return False
    if any(c in name for c in '/\\:*?"<>|') or any(ord(c) < 32 for c in name):
        return False
    return True


# --- 같은 문서 가리기 ---------------------------------------------------------------

_PREFIX_RE = re.compile(r"^\([^)]{1,10}\)\s*")                  # (사양서) (매뉴얼) (TC)
_DATE_RE = re.compile(r"\s*\(\d{6}\)")                         # (261030)
_VERSION_RE = re.compile(r"[\s._]v\d+(?:\.\d+)*(?:w\d+)?", re.I)  # .V1.0.12W1  .V1.1
_REV_RE = re.compile(r"[\s_]*rev\d+(?:\.\d+)*", re.I)          # _Rev1.17


def doc_key(name):
    """판 표시(날짜·버전·Rev)를 뺀 문서 이름. 확장자는 남긴다 — PDF판과 DOCX판은 다른 문서로 본다."""
    stem, ext = os.path.splitext(_PREFIX_RE.sub("", name))
    for rx in (_DATE_RE, _VERSION_RE, _REV_RE):
        stem = rx.sub("", stem)
    return re.sub(r"[\s_]+", " ", stem).strip().lower() + ext.lower()


def plan_moves(remote, local, changed):
    """`_이전판/`으로 옮길 로컬 파일 이름.

    remote: 이번에 폴더에 둘 서버 문서 이름, local: 지금 폴더의 파일 이름, changed: 내용이 바뀌어 새로 넣을 이름.
    """
    owners = {doc_key(r) for r in remote}
    remote = set(remote)
    moves = []
    for name in local:
        if name.startswith("."):
            continue
        if name in remote:
            if name in changed:
                moves.append(name)
            continue
        if doc_key(name) in owners:
            moves.append(name)
    return moves


# --- 기록 -----------------------------------------------------------------------

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _unique(folder, name):
    path = os.path.join(folder, name)
    stem, ext = os.path.splitext(name)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, "%s (%d)%s" % (stem, n, ext))
        n += 1
    return path


# --- 동기화 -----------------------------------------------------------------------

def sync(folder, docs, fetcher, dry_run=False, today=None, log=print, move=os.replace):
    """폴더를 서버 문서 목록에 맞춘다. 결과 dict의 exit_code는 실패가 있으면 1이다."""
    today = today or date.today().isoformat()
    state_path = os.path.join(folder, STATE_FILE)
    state = load_state(state_path)
    staging = os.path.join(folder, STAGING_DIR)
    result = {"changed": [], "unchanged": [], "failed": [], "unavailable": [], "moves": [],
              "archived": [], "dry_run": dry_run, "exit_code": 0}
    records = {}
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    try:
        available = []
        for d in docs:
            name = d["name"]
            if not safe_name(name):
                result["failed"].append({"name": name, "reason": "폴더 밖을 가리키는 파일 이름"})
                continue
            if not d.get("source"):
                result["unavailable"].append(name)
                continue
            try:
                meta = fetcher.meta(d)
                local = os.path.join(folder, name)
                local_sha = sha256(local) if os.path.isfile(local) else None
                rec = state.get(name) or {}
                if local_sha and rec.get("version") == meta["version"] and rec.get("sha256") == local_sha:
                    records[name] = rec
                    available.append(name)
                    result["unchanged"].append(name)
                    continue
                staged = os.path.join(staging, name)
                fetcher.download(d, staged)
                size = os.path.getsize(staged)
                if meta.get("size") is not None and size != meta["size"]:
                    raise SyncError("받은 크기 %d바이트가 서버 크기 %d바이트와 다르다" % (size, meta["size"]))
                new_sha = sha256(staged)
                if meta.get("sha256") and new_sha != meta["sha256"]:
                    raise SyncError("받은 파일의 SHA-256이 서버 값과 다르다")
                records[name] = {"version": meta["version"], "sha256": new_sha, "size": size}
                available.append(name)
                if new_sha == local_sha:
                    os.remove(staged)
                    result["unchanged"].append(name)
                else:
                    result["changed"].append(name)
            except Exception as exc:                                  # noqa: BLE001
                result["failed"].append({"name": name, "reason": "%s: %s" % (type(exc).__name__, exc)})

        local = sorted(n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n)))
        result["moves"] = plan_moves(available, local, set(result["changed"]))
        if dry_run:
            _report(result, log)
            return _finish(result)

        archive = os.path.join(folder, ARCHIVE_DIR, today)
        blocked = set()
        for name in result["moves"]:
            try:
                os.makedirs(archive, exist_ok=True)
                move(os.path.join(folder, name), _unique(archive, name))
                result["archived"].append(name)
            except OSError as exc:
                blocked.add(doc_key(name))
                result["failed"].append({"name": name, "reason": "옮기지 못했다(열려 있음?) %s" % exc})
        placed = []
        for name in result["changed"]:
            if doc_key(name) in blocked:
                result["failed"].append({"name": name, "reason": "옛 판을 옮기지 못해 새 판을 넣지 않았다"})
                continue
            try:
                move(os.path.join(staging, name), os.path.join(folder, name))
                placed.append(name)
            except OSError as exc:
                result["failed"].append({"name": name, "reason": "넣지 못했다 %s" % exc})
        result["changed"] = placed

        new_state = {n: records[n] for n in result["unchanged"] + placed}
        for f in result["failed"]:
            if f["name"] in state and f["name"] not in new_state:
                new_state[f["name"]] = state[f["name"]]
        save_state(state_path, new_state)
        _report(result, log)
        return _finish(result)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _finish(result):
    result["exit_code"] = 1 if result["failed"] else 0
    return result


def _report(result, log):
    head = "미리보기(폴더를 바꾸지 않았다)" if result["dry_run"] else "동기화 결과"
    moved = result["moves"] if result["dry_run"] else result["archived"]
    log("%s: 새로 넣음 %d, 그대로 %d, 이전판으로 %d, 받을 수 없음 %d, 실패 %d" % (
        head, len(result["changed"]), len(result["unchanged"]), len(moved),
        len(result["unavailable"]), len(result["failed"])))
    for name in result["changed"]:
        log("  + 새로 넣음: %s" % name)
    for name in moved:
        log("  > %s/%s: %s" % (ARCHIVE_DIR, "<날짜>" if result["dry_run"] else "", name))
    for name in result["unavailable"]:
        log("  = 받을 수 없어 로컬 판 유지: %s" % name)
    for f in result["failed"]:
        log("  ! 실패: %s — %s" % (f["name"], f["reason"]))


# --- 서버 접속 ---------------------------------------------------------------------

class ServerFetcher:
    """검증 자료 관리 서버. HTTP 다운로드와 SSH(`cat`) 두 길로 받는다."""

    def __init__(self, s, opener=urllib.request.urlopen, runner=subprocess.run):
        self.s = s
        self.opener = opener
        self.runner = runner

    def listing(self):
        url = "%s/knowledge/products/%s" % (self.s["server_url"], self.s["product"])
        with self.opener(url, timeout=self.s["timeout"]) as r:
            return r.read().decode("utf-8", "replace")

    def uploader(self):
        """서버 기록의 지식 폴더 업로드 PC 이름. 읽지 못하면 빈 문자열."""
        url = "%s/knowledge/source/%s" % (self.s["server_url"], self.s["product"])
        try:
            with self.opener(url, timeout=self.s["timeout"]) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            return ((data.get("manifest") or {}).get("uploaded_from") or "").strip()
        except Exception:                                             # noqa: BLE001
            return ""

    def _url(self, doc):
        return "%s/knowledge/download/%s" % (self.s["server_url"], doc["id"])

    def _remote(self, doc):
        return shlex.quote("%s/%s/%s" % (self.s["ssh_dir"], doc["kind"], doc["name"]))

    def _ssh(self, command, stdout=subprocess.PIPE):
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", self.s["ssh_target"], command]
        flags = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW — 예약 실행에서 창을 띄우지 않는다
        p = self.runner(cmd, stdout=stdout, stderr=subprocess.PIPE, timeout=self.s["timeout"] * 5,
                        creationflags=flags)
        if p.returncode != 0:
            raise SyncError("ssh 실패(%d): %s" % (p.returncode, (p.stderr or b"").decode("utf-8", "replace").strip()[:200]))
        return p

    def meta(self, doc):
        if doc["source"] == "ssh":
            q = self._remote(doc)
            out = self._ssh("stat -c %%s -- %s && sha256sum -- %s" % (q, q)).stdout.decode("utf-8", "replace").split()
            if len(out) < 2 or not out[0].isdigit():
                raise SyncError("서버 파일 정보를 읽지 못했다: %r" % out[:2])
            return {"version": out[1], "size": int(out[0]), "sha256": out[1]}
        req = urllib.request.Request(self._url(doc), headers={"Range": "bytes=0-0"})
        with self.opener(req, timeout=self.s["timeout"]) as r:
            headers = r.headers
            total = None
            m = re.search(r"/(\d+)$", headers.get("Content-Range") or "")
            if m:
                total = int(m.group(1))
            elif getattr(r, "status", 200) == 200 and headers.get("Content-Length"):
                total = int(headers["Content-Length"])
            version = headers.get("ETag") or headers.get("Last-Modified") or ""
        if not version:
            raise SyncError("서버가 판 표시(ETag·Last-Modified)를 주지 않았다")
        return {"version": version, "size": total}

    def download(self, doc, dest):
        if doc["source"] == "ssh":
            with open(dest, "wb") as f:
                self._ssh("cat -- %s" % self._remote(doc), stdout=f)
            return
        with self.opener(self._url(doc), timeout=self.s["timeout"]) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)


def run(cfg, repo_root, dry_run=False, log=print, fetcher=None, host=None):
    """설정을 읽어 서버 목록을 받고 폴더를 맞춘다. run.py `sync-knowledge`의 본체."""
    s = settings(cfg)
    check_host(s, host or host_name())
    folder = knowledge_dir(cfg, repo_root)
    if not folder:
        raise SyncError("`지식` 폴더를 찾지 못했다 (config.json knowledge_dir 또는 상위 폴더)")
    fetcher = fetcher or ServerFetcher(s)
    check_host(s, host or host_name(), fetcher.uploader() if hasattr(fetcher, "uploader") else "")
    docs = attach_sources(parse_listing(fetcher.listing()), s["ssh_kinds"], bool(s["ssh_target"] and s["ssh_dir"]))
    log("서버 목록: %d건 (HTTP %d, SSH %d, 받을 수 없음 %d) → %s" % (
        len(docs), sum(d["source"] == "http" for d in docs), sum(d["source"] == "ssh" for d in docs),
        sum(d["source"] is None for d in docs), folder))
    return sync(folder, docs, fetcher, dry_run=dry_run, log=log)


def log_path(folder, today=None):
    """실행 기록 위치: `지식` 옆의 `logs/knowledge-sync/<날짜>.log`."""
    return os.path.join(os.path.dirname(os.path.normpath(folder)), "logs", "knowledge-sync",
                        "%s.log" % (today or date.today().isoformat()))


# --- 예약 작업 -----------------------------------------------------------------------

def pythonw(exe=None):
    """창 없이 도는 pythonw.exe. 없으면 지금 실행 파일."""
    exe = exe or sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.isfile(cand) else exe


def _ps(value):
    return "'" + value.replace("'", "''") + "'"


def task_script(python_exe, run_py):
    """평일 11:00에 도는 예약 작업 등록 스크립트(PowerShell).

    담당자 PC의 서버 업로드가 매일 10:10에 돌므로 그 뒤에 받는다. 그 시각에 PC가 꺼져 있었으면 켜진 뒤 돈다.
    """
    arg = '"%s" sync-knowledge' % run_py
    return "\n".join([
        "$a = New-ScheduledTaskAction -Execute %s -Argument %s -WorkingDirectory %s"
        % (_ps(python_exe), _ps(arg), _ps(os.path.dirname(run_py))),
        "$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday"
        " -At 11:00 -RandomDelay (New-TimeSpan -Minutes 5)",
        "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries"
        " -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)",
        "$p = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
        " -LogonType Interactive -RunLevel Limited",
        "Register-ScheduledTask -TaskName %s -Action $a -Trigger $t -Settings $s -Principal $p -Description %s -Force"
        " | Out-Null" % (_ps(TASK_NAME), _ps("Bellalun Viewer 지식 폴더를 검증 자료 관리 서버의 최신 판으로 맞춘다 (run.py sync-knowledge)")),
    ])


def install_task_command(python_exe, run_py):
    encoded = base64.b64encode(task_script(python_exe, run_py).encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]


def remove_task_command():
    return ["schtasks", "/Delete", "/F", "/TN", TASK_NAME]
