"""허용 profile만 실행하는 원격 서버/클라이언트 CLI. 비밀은 argv로 받지 않는다."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from remote.bundles import BundleError, create_bundle, unpack_bundle
from remote.coordinator import Coordinator, RemoteError
from remote.service import make_server
from remote.winrm_executor import WinRMExecutor


def call_api(base, token, path, data=None):
    parsed = urlparse(base)
    if parsed.scheme not in ("https", "http") or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RemoteError("유효한 서버 주소가 필요합니다")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise RemoteError("외부 서버는 TLS가 필요합니다")
    request = Request(base.rstrip("/") + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description="원격 QA 실행: 로컬 설정과 환경 비밀 참조 필요")
    parser.add_argument("--server", default=os.environ.get("BELLALUN_REMOTE_URL", "http://127.0.0.1:9195"))
    parser.add_argument("--token-env", default="BELLALUN_REMOTE_TOKEN")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--config", required=True, help="커밋하지 않는 서버 로컬 JSON 설정")
    pack = sub.add_parser("bundle")
    pack.add_argument("source")
    pack.add_argument("output")
    pack.add_argument("files", nargs="+", help="포함할 명시적 상대 파일 경로")
    upload = sub.add_parser("upload")
    upload.add_argument("package")
    upload.add_argument("bundle_id")
    submit = sub.add_parser("submit")
    submit.add_argument("pc_id")
    submit.add_argument("profile_id")
    submit.add_argument("bundle_id")
    choice = submit.add_mutually_exclusive_group(required=True)
    choice.add_argument("--restore-after", dest="restore_after", action="store_true")
    choice.add_argument("--no-restore-after", dest="restore_after", action="store_false")
    sub.add_parser("list")
    for command in ("status", "logs", "cancel", "collect"):
        operation = sub.add_parser(command)
        operation.add_argument("job_id")
        if command == "collect":
            operation.add_argument("destination")
    args = parser.parse_args(argv)
    try:
        if args.command == "bundle":
            package, identity = create_bundle(args.source, args.files)
            output = Path(args.output)
            with output.open("xb") as stream:
                stream.write(package)
            print(json.dumps({"bundle_id": identity, "package": str(output)}, ensure_ascii=False))
            return 0
        token = os.environ.get(args.token_env)
        if not token:
            raise RemoteError("인증 token 환경 변수가 설정되지 않았습니다")
        if args.command == "serve":
            config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
            manager = Coordinator(config["state_dir"], config["pcs"], config["profiles"], WinRMExecutor())
            server = make_server(manager, token, "127.0.0.1", int(config.get("port", 9195)))
            print("로컬 원격 실행 API를 시작합니다. 실제 대상/계정 미설정 요청은 차단됩니다.", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        if args.command == "upload":
            result = call_api(args.server, token, "/bundles", {"package": base64.b64encode(Path(args.package).read_bytes()).decode(), "bundle_id": args.bundle_id})
        elif args.command == "submit":
            result = call_api(args.server, token, "/jobs", {"pc_id": args.pc_id, "profile_id": args.profile_id, "bundle_id": args.bundle_id, "restore_after": args.restore_after})
        elif args.command == "list":
            result = call_api(args.server, token, "/jobs")
        else:
            path = "/jobs/" + args.job_id
            path += {"status": "", "logs": "/logs", "cancel": "/cancel", "collect": "/results"}[args.command]
            result = call_api(args.server, token, path, {} if args.command == "cancel" else None)
            if args.command == "collect":
                result = unpack_bundle(base64.b64decode(result["package"], validate=True), args.destination,
                                       result["bundle_id"], code_only=False)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (RemoteError, BundleError, OSError, ValueError, KeyError) as exc:
        print("원격 실행 요청 실패: " + type(exc).__name__ + " — 로컬 설정·조회 상태·해시를 확인하세요.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
