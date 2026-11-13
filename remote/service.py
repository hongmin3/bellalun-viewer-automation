"""기본 loopback 전용 인증 HTTP API. 외부 노출은 별도 TLS 프록시 검증 후 운영한다."""
import base64
import hmac
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path

from remote.bundles import MAX_BYTES, BundleError
from remote.coordinator import RemoteError


def make_server(manager, token, host="127.0.0.1", port=0):
    if not token:
        raise RemoteError("서버 인증 token 환경 참조가 필요합니다")
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise RemoteError("기본 서버는 loopback만 허용합니다. TLS 프록시를 별도로 구성하세요")

    class Handler(BaseHTTPRequestHandler):
        server_version = "BellalunRemote/1"
        def log_message(self, format, *args):
            pass  # Authorization/URL/사용자 입력을 access log에 기록하지 않는다.
        def _reply(self, code, value):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        def _handle(self, post):
            static = {"/": ("index.html", "text/html"), "/dashboard.js": ("dashboard.js", "application/javascript"),
                      "/dashboard.css": ("dashboard.css", "text/css")}
            if not post and self.path in static:
                filename, content_type = static[self.path]
                content = (Path(__file__).parent / "static" / filename).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type + "; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(content)
                return
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self._reply(401, {"error": "인증 실패"})
                return
            try:
                download = re.fullmatch(r"/bundles/([0-9a-f]{64})/download", self.path)
                if not post and download:
                    package, digest = manager.bundle_download(download[1])
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Length", str(len(package)))
                    self.send_header("X-Content-SHA256", digest)
                    self.send_header("X-Bundle-Id", download[1])
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(package)
                    return
                data = {}
                if post:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= MAX_BYTES * 4 // 3 + 4096:
                        self._reply(413, {"error": "요청 크기 초과/누락"})
                        return
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise RemoteError("JSON 객체가 필요합니다")
                if self.path == "/catalog" and not post:
                    result = {"pcs": [{"id": name, "enabled": value.get("enabled") is True,
                                       "shared_interlock": bool(value.get("shared_interlock"))} for name, value in manager.pcs.items()],
                              "profiles": [{"id": name} for name in manager.profiles],
                              "bundles": [p.name for p in (manager.root / "bundles").iterdir()
                                          if p.is_dir() and re.fullmatch(r"[0-9a-f]{64}", p.name)] if (manager.root / "bundles").exists() else []}
                elif self.path == "/bundles" and post:
                    if set(data) != {"package", "bundle_id"}:
                        raise RemoteError("묶음 요청 필드 불일치")
                    result = manager.add_bundle(base64.b64decode(data["package"], validate=True), data["bundle_id"])
                elif self.path == "/jobs":
                    if post:
                        if not set(data) <= {"pc_id", "profile_id", "bundle_id", "restore_after"}:
                            raise RemoteError("임의 명령/추가 요청 필드를 허용하지 않습니다")
                        result = manager.submit(data["pc_id"], data["profile_id"], data["bundle_id"], data.get("restore_after", False))
                    else:
                        result = {"jobs": manager.list()}
                else:
                    match = re.fullmatch(r"/jobs/([0-9a-f]{32})(?:/(cancel|logs|results))?", self.path)
                    if not match:
                        self._reply(404, {"error": "경로 없음"})
                        return
                    job_id, operation = match.groups()
                    if operation == "cancel" and post:
                        result = manager.cancel(job_id)
                    elif operation == "logs" and not post:
                        result = {"log": manager.logs(job_id)}
                    elif operation == "results" and not post:
                        package, identity = manager.results(job_id)
                        result = {"package": base64.b64encode(package).decode(), "bundle_id": identity,
                                  "package_sha256": hashlib.sha256(package).hexdigest()}
                    elif operation is None and not post:
                        result = manager.get(job_id)
                    else:
                        self._reply(405, {"error": "허용하지 않은 동작"})
                        return
                self._reply(200, result)
            except (RemoteError, BundleError, ValueError, KeyError, TypeError):
                self._reply(409, {"error": "요청 거부: 등록 대상·잠금·입력·해시·준비 상태를 확인하세요"})
            except Exception:
                self._reply(500, {"error": "서버 작업 실패; 실행 상태를 확인하세요"})
        def do_GET(self):
            self._handle(False)
        def do_POST(self):
            self._handle(True)
    return ThreadingHTTPServer((host, port), Handler)
