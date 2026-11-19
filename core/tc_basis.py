"""체크리스트 정본의 SHA256, TC 원문 위치와 traceability 연결."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException

from core import checklist

WU_NAME = "Windows Update 호환성 검증 Checklist_Bellalun Viewer_R-25-782.xlsx"
SOURCES = {
    "basic": ("checklist_xlsx", "basic-checklist", checklist.CHECKLIST_NAME, checklist.CHECKLIST_SHEET),
    "windows_update": ("winupdate_checklist_xlsx", "windows-update-checklist", WU_NAME, checklist.WU_SHEET),
}


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _source(ctx, key, name, bundled):
    override = (ctx.cfg.get(key) or "").strip()
    if override and override not in ("REPLACE_ME", r"C:\QA\Bellalun_Viewer_Checklist.xlsx"):
        return Path(override)
    if bundled and bundled.is_file():
        return bundled
    knowledge = ctx.cfg.get("knowledge_dir")
    if knowledge and (candidate := Path(knowledge) / name).is_file():
        return candidate
    root = Path(getattr(ctx, "root", ".")).resolve()
    for parent in (root, *list(root.parents)[:4]):
        for subdirectory in ("", "지식", "Bellalun Viewer 지식파일"):
            candidate = parent / subdirectory / name
            if candidate.is_file():
                return candidate
    return None


def resolve(ctx, kind):
    """정본 후보 한 개를 읽고 같은 바이트에서 해시와 행을 결정한다."""
    key, role, name, sheet = SOURCES[kind]
    resources = Path(getattr(ctx, "resource_root", Path(__file__).resolve().parents[1]))
    origin = {"status": "missing", "kind": kind, "file": name, "sheet": sheet}
    basis = {"source": origin, "rows": {}, "trace": {}}
    try:
        trace = _read_json(resources / "traceability.json")
        basis["documents"] = trace.get("_sources", {})
        for row in trace["tc"]:
            if row.get("checklist", "basic") == kind:
                if row["tc_id"] in basis["trace"]:
                    raise ValueError("추적표에 중복 TC ID가 있습니다.")
                basis["trace"][row["tc_id"]] = row
        baseline = trace["_baseline" if kind == "basic" else "_baseline_windows_update"]
        approved = baseline["sha256"]
        bundled = None
        manifest = resources / "assets-manifest.json"
        if manifest.exists():
            package = _read_json(manifest)
            entries = [row for row in package["files"] if row.get("role") == role]
            if len(entries) != 1:
                raise ValueError("패키지 매니페스트에서 체크리스트 역할을 하나로 확인할 수 없습니다.")
            assets = (resources / "assets").resolve()
            bundled = (assets / entries[0]["destination"]).resolve()
            if not bundled.is_relative_to(assets):
                raise ValueError("패키지 체크리스트 경로가 자료 폴더 밖입니다.")
            approved = entries[0]["sha256"]
        path = _source(ctx, key, name, bundled)
        if path is None or not path.is_file():
            origin["reason"] = "기준 체크리스트 파일을 찾지 못했습니다."
            return basis
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        origin.update(file=path.name, sha256=sha256)
        if sha256 != approved:
            origin.update(status="conflict", reason="승인된 체크리스트 SHA256과 다릅니다.")
            return basis
        rows = checklist.read_tc_rows(BytesIO(data), sheet, strict=True)
        if not rows or rows.keys() != basis["trace"].keys():
            raise ValueError("기준 시트와 추적표의 TC ID가 다릅니다.")
        for tc_id, row in rows.items():
            expected = basis["trace"][tc_id]["title"]
            titles = [row["title"]]
            if kind == "windows_update":
                titles.append(row["function"])
            if not any("".join(expected.split()) == "".join(title.split()) for title in titles):
                raise ValueError(f"기준 시트와 추적표의 Title이 다릅니다 ({tc_id}).")
        origin["status"] = "verified"
        basis.update(rows=rows, path=path, data=data)
    except (OSError, TypeError, ValueError, KeyError, AttributeError,
            BadZipFile, InvalidFileException, ParseError) as exc:
        origin.update(status="invalid", reason=f"기준서 또는 추적표 확인 실패 ({type(exc).__name__}): {exc}")
    return basis


def capture(ctx, kind):
    cache = getattr(ctx, "checklist_bases", None)
    if cache is None:
        cache = ctx.checklist_bases = {}
    if kind not in cache:
        cache[kind] = resolve(ctx, kind)
    return cache[kind]


def report_meta(basis):
    source = basis["source"]
    return {
        "checklist_basis": source,
        "source_doc": source["file"],
        "source_sheet": source["sheet"],
        "checklist": basis["rows"],
        "tc_basis": {
            tc_id: {
                "cells": row["cells"],
                "implementation": basis["trace"][tc_id].get("module"),
                "requirements": [
                    {**basis.get("documents", {}).get(req.get("doc"), {}),
                     **{key: req[key] for key in ("doc", "page", "srs", "steps") if key in req}}
                    for req in basis["trace"][tc_id].get("requirements", [])
                ],
                "reuses": basis["trace"][tc_id].get("reuses", []),
            } for tc_id, row in basis["rows"].items()
        },
    }
