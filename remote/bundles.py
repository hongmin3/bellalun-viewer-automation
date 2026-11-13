"""명시 파일 집합을 SHA-256으로 고정하는 코드/결과 묶음."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile
import zlib

MAX_BYTES = 512 * 1024 * 1024
MAX_FILES = 20000


class BundleError(ValueError):
    pass


def safe_path(name, code_only=False):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\x00" in name:
        raise BundleError("잘못된 묶음 경로")
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ("", ".", "..") for p in name.split("/")):
        raise BundleError("절대/상위 경로는 허용하지 않습니다")
    if any(p.endswith((".", " ")) or re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", p)
           for p in path.parts):
        raise BundleError("Windows에서 안전하지 않은 경로")
    if code_only and any(p.lower() in {".git", ".env", "config.json", "evidence", "reports", "work", "baseline", "지식"}
                         or p.lower().endswith((".bak", ".dcm", ".pfx", ".key")) for p in path.parts):
        raise BundleError("코드 묶음에 운영 자료나 비밀 파일을 넣을 수 없습니다")
    return path


def check_local(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BundleError("링크/reparse 경로를 허용하지 않습니다")
    return path


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def create_bundle(source, files, *, code_only=True):
    source = check_local(source)
    manifest = {"version": 1, "files": {}}
    payload = {}
    folded = set()
    total = 0
    for name in sorted(files):
        safe_path(name, code_only)
        if name.casefold() in folded:
            raise BundleError("중복 파일 경로")
        folded.add(name.casefold())
        path = check_local(source / name)
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise BundleError("일반 파일만 묶을 수 있습니다")
        total += path.stat().st_size
        if total > MAX_BYTES or len(folded) > MAX_FILES:
            raise BundleError("묶음 크기 제한 초과")
        data = path.read_bytes()
        payload[name] = data
        manifest["files"][name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if not payload:
        raise BundleError("묶음 파일 집합이 비어 있습니다")
    encoded = _canonical(manifest)
    identity = hashlib.sha256(encoded).hexdigest()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", encoded)
        for name, data in payload.items():
            archive.writestr("payload/" + name, data)
    return output.getvalue(), identity


def unpack_bundle(package, destination, expected_id, *, code_only=True):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_id or "") or len(package) > MAX_BYTES:
        raise BundleError("잘못된 묶음 식별자/크기")
    destination = check_local(destination)
    if destination.exists():
        raise BundleError("기존 목적지를 덮어쓸 수 없습니다")
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            members = archive.infolist()
            if len(members) > MAX_FILES + 1 or sum(m.file_size for m in members) > MAX_BYTES:
                raise BundleError("묶음 압축 해제 제한 초과")
            names = [m.filename for m in members]
            if len({n.casefold() for n in names}) != len(names):
                raise BundleError("중복 압축 경로")
            for member in members:
                safe_path(member.filename)
                kind = stat.S_IFMT(member.external_attr >> 16)
                if member.is_dir() or kind not in (0, stat.S_IFREG):
                    raise BundleError("압축 링크/특수 파일 거부")
            raw_manifest = archive.read("manifest.json")
            if hashlib.sha256(raw_manifest).hexdigest() != expected_id:
                raise BundleError("manifest 해시 불일치")
            manifest = json.loads(raw_manifest)
            if manifest.get("version") != 1 or not isinstance(manifest.get("files"), dict) or not manifest["files"]:
                raise BundleError("manifest 형식 불일치")
            if set(names) != {"manifest.json", *("payload/" + n for n in manifest["files"])}:
                raise BundleError("manifest와 실제 파일 집합 불일치")
            # 모든 파일을 검증한 뒤에만 목적지를 생성한다.
            data = {}
            for name, expected in manifest["files"].items():
                safe_path(name, code_only)
                content = archive.read("payload/" + name)
                if len(content) != expected["size"] or hashlib.sha256(content).hexdigest() != expected["sha256"]:
                    raise BundleError("파일 내용 해시 불일치")
                data[name] = content
            destination.mkdir(parents=True)
            for name, content in data.items():
                path = check_local(destination / name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            return {"bundle_id": expected_id, "files": manifest["files"]}
    except (KeyError, TypeError, ValueError, zipfile.BadZipFile, OSError, zlib.error) as exc:
        if isinstance(exc, BundleError):
            raise
        raise BundleError("묶음 검증/쓰기 실패") from exc
