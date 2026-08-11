# -*- coding: utf-8 -*-
"""DICOM Print SCP 서버(웹) 클라이언트.

http://<host>:8000 에서 동작하는 시험용 Print SCP.
Film 수신 목록을 JSON으로 읽을 수 있어 Print TC의 '실제 수신' 판정이 자동화된다.

확인된 엔드포인트 (2026-08-10, 실제 응답으로 검증)
  GET    /api/scp-status       {"running","ae_title","host","port","tls_running","tls_port"}
  GET    /api/jobs             수신 필름 목록
  DELETE /api/jobs/<id>        필름 1건 삭제
  GET    /api/storage-usage    저장 사용량
"""

import json
import urllib.request


class PrintScpError(RuntimeError):
    pass


class PrintServer:
    def __init__(self, base_url, timeout=15):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _req(self, path, method="GET"):
        req = urllib.request.Request(self.base + path, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else None

    def _bytes(self, path):
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as resp:
            return resp.read()

    def status(self):
        """SCP 기동 상태와 SCU 등록에 필요한 AE/IP/Port."""
        return self._req("/api/scp-status")

    def jobs(self):
        return self._req("/api/jobs") or []

    def preview(self, job_id):
        """Return the server-rendered preview bytes for a received film job."""
        return self._bytes(f"/api/jobs/{job_id}/preview")

    def storage_usage(self):
        return self._req("/api/storage-usage")

    def delete_job(self, job_id):
        self._req(f"/api/jobs/{job_id}", method="DELETE")
        return True

    def clear(self):
        """수신 목록을 비운다. Print TC 수행 전 기준선을 만들 때 쓴다."""
        n = 0
        for j in self.jobs():
            jid = j.get("id")
            if jid and self.delete_job(jid):
                n += 1
        return n

    def jobs_since(self, known_ids):
        """기존 ID 집합에 없는 신규 수신 필름만 반환한다."""
        known = {str(value) for value in known_ids}
        return [j for j in self.jobs() if str(j.get("id")) not in known]

    def wait_for_jobs(self, count=1, timeout=60, poll=2.0, exclude_ids=()):
        """신규 필름이 count건 수신될 때까지 대기한다. 도달하면 목록, 아니면 부분 목록."""
        import time
        deadline = time.time() + timeout
        # The server returns numeric IDs, while report/config values may be
        # strings.  Normalize both sides so an old job can never be mistaken
        # for the print that this run just submitted.
        exclude = {str(value) for value in exclude_ids}
        while time.time() < deadline:
            new = [j for j in self.jobs() if str(j.get("id")) not in exclude]
            if len(new) >= count:
                return new
            time.sleep(poll)
        return [j for j in self.jobs() if str(j.get("id")) not in exclude]
