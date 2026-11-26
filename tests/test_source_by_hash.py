"""이름이 바뀐 같은 원본을 SHA256으로 찾는다(REQ-TRACE-001, 2026-11-26 지식 폴더 개편)."""
import hashlib
from types import SimpleNamespace

from core import specs, tc_basis


def test_find_by_sha256_matches_content_not_name(tmp_path):
    (tmp_path / "새 이름(261030).pdf").write_bytes(b"spec-body")
    (tmp_path / "다른 판(261126).pdf").write_bytes(b"other")
    want = hashlib.sha256(b"spec-body").hexdigest()
    assert specs.find_by_sha256([str(tmp_path)], want, (".pdf",)).endswith("새 이름(261030).pdf")
    assert specs.find_by_sha256([str(tmp_path)], hashlib.sha256(b"x").hexdigest()) is None


def test_knowledge_dir_accepts_server_managed_folder_name(tmp_path):
    (tmp_path / "Bellalun Viewer 지식파일").mkdir()
    repo = tmp_path / "auto"
    repo.mkdir()
    ctx = SimpleNamespace(root=str(repo), cfg={})
    assert specs.knowledge_dir(ctx).endswith("Bellalun Viewer 지식파일")


def test_checklist_source_found_by_approved_hash_only(tmp_path):
    knowledge = tmp_path / "Bellalun Viewer 지식파일"
    knowledge.mkdir()
    (knowledge / "(TC) 이름 바뀐 기준서.xlsx").write_bytes(b"approved")
    (knowledge / "(TC) 다른 기준서.xlsx").write_bytes(b"other")
    repo = tmp_path / "auto"
    repo.mkdir()
    ctx = SimpleNamespace(root=str(repo), cfg={})
    approved = hashlib.sha256(b"approved").hexdigest()
    found = tc_basis._source(ctx, "checklist_xlsx", "없는 이름.xlsx", None, approved)
    assert found is not None and found.name == "(TC) 이름 바뀐 기준서.xlsx"
    assert tc_basis._source(ctx, "checklist_xlsx", "없는 이름.xlsx", None, hashlib.sha256(b"z").hexdigest()) is None
