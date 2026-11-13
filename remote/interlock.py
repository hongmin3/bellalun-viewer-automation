"""VHD와 QA가 함께 사용하는 외부 durable exclusive lock API 계약."""
import json
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from remote.coordinator import RemoteBlocked


class SharedInterlock:
    def __init__(self, environ):
        self.environ = environ

    def _call(self, settings, suffix, payload):
        base = settings.get("url", "")
        parsed = urlparse(base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise RemoteBlocked("TLS 공용 잠금 API가 미설정입니다")
        token = self.environ.get(settings.get("token_env", ""))
        if not token:
            raise RemoteBlocked("공용 잠금 API 비밀 환경 참조가 없습니다")
        request = Request(base.rstrip("/") + suffix, data=json.dumps(payload).encode(),
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urlopen(request, timeout=15) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise RemoteBlocked("공용 잠금 응답 크기 초과")
        return json.loads(raw)

    def acquire(self, job, pc):
        settings = pc.get("shared_interlock") or {}
        target = settings.get("target")
        if not target:
            raise RemoteBlocked("VHD와 공유하는 원자적 잠금이 미설정입니다")
        payload = {"target": target, "owner": job["id"], "domain": "vhd-and-qa", "durable": True}
        lease = self._call(settings, "/acquire", payload)
        if (not isinstance(lease, dict) or lease.get("target") != target or lease.get("owner") != job["id"]
                or lease.get("domain") != "vhd-and-qa" or lease.get("exclusive") is not True
                or lease.get("durable") is not True or lease.get("expires") is not None
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", lease.get("lease_id", ""))):
            raise RemoteBlocked("공용 잠금의 배타성·소유자·영속성을 확인하지 못했습니다")
        return lease

    def release(self, job, pc, lease):
        result = self._call(pc["shared_interlock"], "/release", {
            "target": lease["target"], "owner": job["id"], "lease_id": lease["lease_id"]})
        if not isinstance(result, dict) or result.get("released") is not True:
            raise RemoteBlocked("공용 잠금 해제 확인 실패")
