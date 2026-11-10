# -*- coding: utf-8 -*-
r"""DICOM Storage SCP 서버(웹) 클라이언트 — Bunny 를 대체한다(2026-08-26).

`http://<host>:5003` 에서 도는 시험용 Storage SCP. **PC 에 Bunny 를 띄울 필요가
없다**(사용자 확인) — MWL(5000) / Print(8000) 과 같은 방식으로 이 서버에 바로
전송하고, 수신 결과를 HTTP API 로 읽는다.

확인된 엔드포인트 (2026-08-26, 실제 응답으로 검증)
  GET    /api/scp-status              {"ae_title","host","port","running",
                                       "tls_port","tls_running","max_storage_mib",
                                       "retention_days","allowed_calling_aes"}
  GET    /api/usage                   {"bytes","count","max_bytes"}
  GET    /api/settings                {"max_storage_mib","retention_days"}
  GET    /api/studies                 수신 스터디 목록(환자·스터디 단위 요약)
  GET    /api/studies/signature       {"signature":"<건수>|<최근수신시각>"}
  GET    /api/studies/<uid>/series    시리즈 목록(series_instance_uid, modality,
                                       series_number, instance_count, ...)
  GET    /api/studies/<uid>/download  그 스터디의 객체 전부(application/zip)
  DELETE /api/studies                 수신 전체 삭제
  GET    /api/qr-status, /api/move-destinations   Q/R SCP 용(이 저장소는 미사용)

**왜 `/download` 까지 쓰는가**
  판정은 SOP Instance UID / SOP Class UID **단위**로 원본과 대조한다
  (`core/send_verify.py`, 운영 지침 2절). API 는 series 단위까지만 주므로
  ZIP 을 받아 `core/dicomlite` 로 파싱한다. 그러면 Bunny 파일을 읽던 기존 판정
  로직을 **그대로** 쓸 수 있다 — 실측으로 2D(MG) / 3D(DBT) / Dose SR(RDSR)
  세 SOP Class 와 StationName 까지 읽히는 것을 확인했다.
"""

import io
import hashlib
import json
import os
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from urllib.error import HTTPError

from core import dicomlite


class StorageScpError(RuntimeError):
    def __init__(self, message, diagnostics=None):
        self.diagnostics = diagnostics or {}
        super().__init__(message + (": " + json.dumps(self.diagnostics, ensure_ascii=False)
                                   if self.diagnostics else ""))


def observation():
    """응답 본문·주소·환자정보 없이 수신 관측의 근거만 남긴다."""
    return {"observed_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending", "requests": [], "downloads": [],
            "parse_errors": []}


def observation_error(exc, diagnostics, stage):
    if isinstance(exc, StorageScpError):
        return exc
    status = ("http_error" if isinstance(exc, (HTTPError, OSError))
              else "response_error")
    diagnostics.update(status=status, error={"stage": stage,
                       "type": type(exc).__name__})
    if isinstance(exc, HTTPError):
        diagnostics["error"]["http_status"] = exc.code
    return StorageScpError("Storage SCP 관측 실패", diagnostics)


class StorageServer:
    def __init__(self, base_url, timeout=30):
        self.base = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.observation = observation()

    # --- 원시 요청 -----------------------------------------------------
    def _req(self, path, method="GET"):
        req = urllib.request.Request(self.base + path, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            blob = resp.read()
        self.observation["requests"].append({
            "kind": "json", "bytes": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "observed_at": datetime.now(timezone.utc).isoformat()})
        raw = blob.decode("utf-8", "strict")
        return json.loads(raw) if raw.strip() else None

    def _bytes(self, path, timeout=None):
        with urllib.request.urlopen(self.base + path,
                                    timeout=timeout or self.timeout) as resp:
            return resp.read()

    # --- 상태 ----------------------------------------------------------
    def status(self):
        """SCP 기동 상태와 SCU 등록에 필요한 AE/IP/Port."""
        return self._req("/api/scp-status")

    def usage(self):
        return self._req("/api/usage")

    def reachable(self):
        """서버가 살아 있고 SCP 가 떠 있는가. 예외를 밖으로 내지 않는다."""
        try:
            state = self.status() or {}
        except Exception:
            return False
        return bool(state.get("running"))

    # --- 수신 목록 -----------------------------------------------------
    def studies(self):
        rows = self._req("/api/studies")
        if not isinstance(rows, list):
            raise ValueError("Storage SCP study list 형식 오류")
        return rows

    def signature(self):
        """수신 상태 서명. **폴링에 이것을 쓴다** — 목록 전체를 받지 않아도
        새 객체가 왔는지 알 수 있다(`"13|2026-08-26T06:25:22Z"` 형태)."""
        got = self._req("/api/studies/signature") or {}
        return got.get("signature")

    def series(self, study_uid):
        return self._req(
            f"/api/studies/{urllib.parse.quote(study_uid, safe='')}/series") or []

    def clear(self):
        """수신 전체 삭제. 전송 1회의 도착분만 세기 위한 준비다."""
        self._req("/api/studies", method="DELETE")

    # --- 객체 단위 ----------------------------------------------------
    def download(self, study_uid, timeout=180):
        """스터디 하나의 객체 전부를 ZIP 바이트로 받는다."""
        path = f"/api/studies/{urllib.parse.quote(study_uid, safe='')}/download"
        return self._bytes(path, timeout=timeout)

    def objects(self, study_uids=None, tags=None, work_dir=None):
        """수신 객체를 **DICOM 태그까지 파싱해서** 돌려준다.

        반환 형식은 `dicomlite.scan_dir` 과 같다(dict 목록). 그래서
        `core/send_verify.py` 의 판정이 Bunny 파일을 읽던 때와 똑같이 동작한다.

        `study_uids` 를 주면 그 스터디만, 없으면 수신된 전부를 본다.
        """
        uids = (list(study_uids) if study_uids is not None
                else [s["study_instance_uid"] for s in self.studies()])
        if not uids:
            return []
        if work_dir:
            os.makedirs(work_dir, exist_ok=True)
        # 이전 work_dir의 파일을 이번 수신으로 세지 않는다.
        temp = tempfile.mkdtemp(prefix="storagescp_", dir=work_dir)
        made_temp = work_dir is None
        try:
            for uid in uids:
                try:
                    blob = self.download(uid)
                except Exception as exc:
                    raise observation_error(exc, self.observation, "download") from None
                self.observation["downloads"].append({
                    "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob),
                    "observed_at": datetime.now(timezone.utc).isoformat()})
                if not blob[:2] == b"PK":
                    self.observation["status"] = "zip_error"
                    raise StorageScpError("Storage SCP ZIP 응답 형식 오류", self.observation)
                target = os.path.join(temp, _safe_name(uid))
                os.makedirs(target, exist_ok=True)
                try:
                    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                        self.observation["downloads"][-1]["files"] = len(zf.infolist())
                        zf.extractall(target)
                except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
                    self.observation.update(status="zip_error",
                        error={"stage": "unzip", "type": type(exc).__name__})
                    raise StorageScpError("Storage SCP ZIP 압축 해제 오류", self.observation) from None
            objects = dicomlite.scan_dir(temp, tags) if tags else dicomlite.scan_dir(temp)
            errors = []
            for index, obj in enumerate(objects):
                missing = [key for key in ("PatientID", "StudyInstanceUID",
                           "SeriesInstanceUID", "SOPInstanceUID")
                           if not obj.get(key)] if not tags else []
                if obj.get("_error") or missing:
                    errors.append({"object_index": index, "type": "DicomIdentityParseError",
                                   "missing_tags": missing, "reader_error": bool(obj.get("_error"))})
            if not objects and any(item.get("files") for item in self.observation["downloads"]):
                errors.append({"type": "NoReadableDicomObjects"})
            self.observation["objects_parsed"] = len(objects)
            if errors:
                self.observation.update(status="parse_error", parse_errors=errors)
                raise StorageScpError("Storage SCP DICOM 파싱 오류", self.observation)
            return objects
        finally:
            if made_temp:
                shutil.rmtree(temp, ignore_errors=True)


def _safe_name(uid):
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in uid)[:120]


# --------------------------------------------------------------------------
def config(ctx):
    """`config.json > dicom.storage_scp` 를 돌려준다."""
    return (ctx.cfg.get("dicom") or {}).get("storage_scp") or {}


def server(ctx, timeout=30):
    """설정에 적힌 Storage SCP 서버 클라이언트.

    `api_url` 이 없으면 `host` 로 기본 포트(5003)를 조립한다 — 예전 설정
    (Bunny)에서 넘어온 config 로도 최소한 동작하게 한다.
    """
    scp = config(ctx)
    base = scp.get("api_url")
    if not base:
        host = scp.get("host")
        if not host:
            raise StorageScpError(
                "config.json > dicom.storage_scp.api_url 또는 host 가 필요합니다")
        base = f"http://{host}:5003"
    return StorageServer(base, timeout=timeout)
