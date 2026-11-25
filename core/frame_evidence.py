"""실행 근거 파일의 바이트 대조와 원자적 JSON 기록."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from .atomic_metadata import replace_metadata


def sha256(path):
    with Path(path).open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path):
    return {"path": str(path), "sha256": sha256(path)}


def file_matches(path, record):
    """경로가 바뀐 사본도 같은 바이트일 때 일치한다."""
    try:
        return sha256(path) == record["sha256"]
    except (OSError, ValueError, TypeError, KeyError):
        return False


def write_json(path, value):
    """중단 시에도 독자는 기존 전체 기록이나 새 전체 기록을 읽는다."""
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        replace_metadata(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
