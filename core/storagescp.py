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
import json
import os
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile

from core import dicomlite


class StorageScpError(RuntimeError):
    pass


class StorageServer:
    def __init__(self, base_url, timeout=30):
        self.base = (base_url or "").rstrip("/")
        self.timeout = timeout

    # --- 원시 요청 -----------------------------------------------------
    def _req(self, path, method="GET"):
        req = urllib.request.Request(self.base + path, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
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
        return self._req("/api/studies") or []

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
        temp = work_dir or tempfile.mkdtemp(prefix="storagescp_")
        made_temp = work_dir is None
        try:
            for uid in uids:
                blob = self.download(uid)
                if not blob[:2] == b"PK":
                    raise StorageScpError(
                        f"ZIP 이 아닌 응답: {uid} ({blob[:16]!r})")
                target = os.path.join(temp, _safe_name(uid))
                os.makedirs(target, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    zf.extractall(target)
            return dicomlite.scan_dir(temp, tags) if tags else dicomlite.scan_dir(temp)
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
