"""공용 payload와 로컬 journal을 사용하는 순차 차이 복원.

파일시스템만 경계로 사용한다. 제품/서비스/SQL 실행은 호출자가 소유한다.
사전 사본과 archive는 수정하거나 지우지 않는다.
"""
from __future__ import annotations

import hashlib
import copy
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

from core.run_preservation import (PreservationError, _absolute, _check_path, _hash,
                                   _relative_path, _write_json, snapshot)


STORE_MARKER = ".bellalun-preservation-store.json"


def prepare_store(run):
    directory = _check_path(run.storage_dir)
    if not directory.is_dir():
        raise PreservationError("설정한 공용 저장소에 연결할 수 없습니다")
    marker = _check_path(directory / STORE_MARKER)
    if not marker.exists():
        # x 모드로 다른 실행이 만든 식별자를 덮어쓰지 않는다.
        try:
            with marker.open("x", encoding="utf-8") as output:
                json.dump({"version": 1, "id": str(uuid.uuid4())}, output)
                output.flush()
                os.fsync(output.fileno())
        except FileExistsError:
            pass
    identity = json.loads(marker.read_text(encoding="utf-8"))
    if identity.get("version") != 1 or not isinstance(identity.get("id"), str) or not identity["id"]:
        raise PreservationError("공용 저장소 식별자가 잘못되었습니다")
    run.journal["storage"]["id"] = identity["id"]
    run._save("preparing")
    _check_path(run.data_dir).mkdir()  # 실행별 기존 사본 재사용 금지


def verify_store(storage):
    directory = _check_path(storage["path"])
    identity = json.loads(_check_path(directory / STORE_MARKER).read_text(encoding="utf-8"))
    if identity.get("version") != 1 or identity.get("id") != storage.get("id"):
        raise PreservationError("공용 저장소 식별자가 변경되었습니다")


def _matches(path, expected):
    path = _check_path(path)
    return (path.is_file() and path.stat().st_size == expected["size"]
            and _hash(path) == expected["sha256"])


def _current_snapshot(path):
    path = _check_path(path)
    if path.is_file():
        return {"exists": True, "directories": [], "files": {},
                "root_file": {"size": path.stat().st_size, "sha256": _hash(path)}}
    return snapshot(path)


def _file_copy(source, destination, expected, temporary_dir=None):
    source, destination = _check_path(source), _check_path(destination)
    if destination.exists():
        if _matches(destination, expected):
            return  # journal에 고정한 중단 사본만 다시 사용한다.
        raise PreservationError("기존 보존 사본을 덮어쓰지 않습니다")
    if not _matches(source, expected):
        raise PreservationError("보관 전에 원본 파일이 변경되었습니다")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if temporary_dir is None:
        temporary = _check_path(destination.with_name(destination.name + ".bellalun-copying"))
    else:
        temporary_dir = _check_path(temporary_dir)
        temporary_dir.mkdir(parents=True, exist_ok=True)
        temporary = _check_path(temporary_dir / hashlib.sha256(str(destination).encode("utf-8")).hexdigest())
    # 최종 사본은 원자적 이름 교체 뒤에만 나타난다. 불완전한 임시 파일은
    # journal에 고정한 목적지의 전용 파일이므로 재시도 때 다시 작성한다.
    if temporary.exists():
        if not temporary.is_file():
            raise PreservationError("복사 임시 경로가 파일이 아닙니다")
        temporary.chmod(temporary.stat().st_mode | stat.S_IWRITE)
        temporary.unlink()
    shutil.copy2(source, temporary)
    mode = temporary.stat().st_mode
    temporary.chmod(mode | stat.S_IWRITE)
    with temporary.open("r+b") as copied:
        os.fsync(copied.fileno())
    temporary.chmod(mode)
    if not _matches(temporary, expected) or not _matches(source, expected):
        raise PreservationError("공용 파일 사본의 해시 검증 실패")
    if destination.exists():
        raise PreservationError("기존 보존 사본을 덮어쓰지 않습니다")
    os.replace(temporary, destination)


def _archive(run):
    """시험 후 목록을 먼저 고정하고 새/변경 파일만 원격에 보관한다."""
    journal = run.journal
    archive = journal.get("archive")
    if archive is None:
        archive = {"version": 1, "run_id": run.run_id,
                   "storage": dict(journal["storage"]), "roots": {}, "db": None}
        for name, source in run.roots.items():
            current = _current_snapshot(source)
            before = run.manifest["roots"][name]
            archive["roots"][name] = {
                "snapshot": current,
                "references": {relative: "before" if metadata == before["files"].get(relative) else "archive"
                               for relative, metadata in current["files"].items()}}
        journal["archive"] = archive
        run._save("archiving")
    if not journal.get("archive_complete"):
        for name, item in archive["roots"].items():
            current = item["snapshot"]
            destination = _check_path(run.data_dir / "archive" / name)
            if current["exists"]:
                destination.mkdir(parents=True, exist_ok=True)
                for directory in current["directories"]:
                    _check_path(destination / _relative_path(directory)).mkdir(parents=True, exist_ok=True)
            if current.get("root_file"):
                _file_copy(run.roots[name], destination / ".root-file", current["root_file"],
                           temporary_dir=run.data_dir / "copying")
            for relative, origin in item["references"].items():
                relative = _relative_path(relative)
                if origin == "archive":
                    _file_copy(run.roots[name] / relative, destination / relative, current["files"][relative],
                               temporary_dir=run.data_dir / "copying")
            if _current_snapshot(run.roots[name]) != current:
                raise PreservationError("시험 후 보관 중 원본이 변경되었습니다")
        if run.manifest.get("db") and archive.get("db") is None:
            # backup() 도중 중단된 폴더도 지우거나 재사용하지 않는다.
            sequence = journal.get("db_archive_attempt", -1) + 1
            journal["db_archive_attempt"] = sequence
            relative = "archive/database" + (f"-{sequence}" if sequence else "")
            journal["db_archive_inflight"] = relative
            run._save("archiving")
            directory = _check_path(run.data_dir / relative)
            directory.mkdir(parents=True)
            metadata = run.db_adapter.backup(directory)
            if not isinstance(metadata, dict) or not metadata.get("scope"):
                raise PreservationError("시험 후 DB 비교 범위(scope)가 없습니다")
            if not run.db_adapter.verify_backup(directory, metadata):
                raise PreservationError("시험 후 DB 사본 검증 실패")
            archive["db"] = {"path": relative, "metadata": metadata, "files": snapshot(directory)}
            run._save("archiving")
        _verify_archive(run)
        _write_json(run.run_dir / "archive_manifest.json", archive)
        run._save("archived", archive_complete=True)
    else:
        _verify_archive(run)
    return archive


def _verify_archive(run):
    verify_store(run.journal["storage"])
    archive = run.journal["archive"]
    for name, item in archive["roots"].items():
        expected_archive = {"exists": item["snapshot"]["exists"],
                            "directories": item["snapshot"]["directories"], "files": {}}
        if item["snapshot"].get("root_file"):
            expected_archive["files"][".root-file"] = item["snapshot"]["root_file"]
        for relative, origin in item["references"].items():
            relative = _relative_path(relative)
            if origin not in {"before", "archive"}:
                raise PreservationError("잘못된 archive 참조")
            expected = item["snapshot"]["files"][relative]
            if not _matches(run.data_dir / origin / name / relative, expected):
                raise PreservationError("공용 시험 후 자료 검증 실패")
            if origin == "archive":
                expected_archive["files"][relative] = expected
        if snapshot(run.data_dir / "archive" / name) != expected_archive:
            raise PreservationError("공용 시험 후 보관 목록 불일치")
    db = archive.get("db")
    if db:
        directory = _check_path(run.data_dir / db["path"])
        if (snapshot(directory) != db["files"]
                or not run.db_adapter.verify_backup(directory, db["metadata"])):
            raise PreservationError("공용 시험 후 DB 사본 검증 실패")


def _entry(path):
    path = _check_path(path)
    if not path.exists():
        return {"kind": "missing"}
    if path.is_dir():
        return {"kind": "directory", "snapshot": snapshot(path)}
    return {"kind": "file", "size": path.stat().st_size, "sha256": _hash(path)}


def _plan(run):
    if "delta_operations" in run.journal:
        return run.journal["delta_operations"]
    operations = []
    for name, source in run.roots.items():
        before = run.manifest["roots"][name]
        current = run.journal["archive"]["roots"][name]["snapshot"]
        if _current_snapshot(source) != current:
            raise PreservationError("복원 계획 전에 원본이 변경되었습니다")
        quarantine = source.with_name(f".{source.name}.bellalun-{run.run_id}-quarantine")
        stage = source.with_name(f".{source.name}.bellalun-{run.run_id}-stage")
        if (_check_path(quarantine).exists() or _check_path(stage).exists()
                or _check_path(stage.with_name(stage.name + ".bellalun-copying")).exists()):
            raise PreservationError("실행별 임시/격리 경로가 이미 존재합니다")
        candidates = []
        if current.get("root_file"):
            candidates.append("")
        elif not before["exists"]:
            if current["exists"]:
                candidates.append("")
        else:
            for relative in current["directories"]:
                if relative not in before["directories"]:
                    candidates.append(relative)
            for relative in current["files"]:
                if relative not in before["files"]:
                    candidates.append(relative)
        selected = []
        for relative in sorted(candidates, key=lambda p: (len(Path(p).parts), p)):
            if any(not parent or relative.startswith(parent + "/") for parent in selected):
                continue
            selected.append(relative)
            target = source / relative if relative else source
            operations.append({"kind": "quarantine", "root": name, "relative": relative,
                               "destination": str(quarantine / str(len(operations))),
                               "expected": _entry(target), "phase": "planned"})
        if before["exists"]:
            for relative in ["", *before["directories"]]:
                operations.append({"kind": "mkdir", "root": name, "relative": relative,
                                   "phase": "planned"})
            for relative, metadata in before["files"].items():
                if current["files"].get(relative) != metadata:
                    operations.append({"kind": "restore", "root": name, "relative": relative,
                                       "stage": str(stage), "phase": "planned"})
    run.journal["delta_operations"] = operations
    run._save("restoring")
    return operations


def _safe_current(run, operation, target):
    """교체 직전에 시험 후 사본과 현재 파일을 다시 대조한다."""
    verify_store(run.journal["storage"])
    name, relative = operation["root"], operation["relative"]
    item = run.journal["archive"]["roots"][name]
    expected = item["snapshot"]["files"].get(relative)
    if expected:
        origin = item["references"][relative]
        if not _matches(run.data_dir / origin / name / relative, expected):
            raise PreservationError("교체 전 시험 후 사본 검증 실패")
        if target.exists() and not _matches(target, expected):
            raise PreservationError("보관 후 작업 파일이 변경되었습니다")
    elif target.exists():
        raise PreservationError("복원 중 예상하지 못한 파일이 생겼습니다")


def _restore_operations(run):
    for operation in _plan(run):
        if operation["phase"] == "verified":
            continue
        name = operation["root"]
        source = run.roots[name]
        relative = operation["relative"]
        target = _check_path(source / _relative_path(relative) if relative else source)
        verify_store(run.journal["storage"])
        kind = operation["kind"]
        if kind == "quarantine":
            destination = _check_path(operation["destination"])
            operation["phase"] = "quarantine"
            run._save("restoring")
            if destination.exists():
                if target.exists() or _entry(destination) != operation["expected"]:
                    raise PreservationError("격리 중단 상태가 예상과 다릅니다")
            else:
                if _entry(target) != operation["expected"]:
                    raise PreservationError("보관 후 격리 대상이 변경되었습니다")
                _verify_archive(run)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, destination)
        elif kind == "mkdir":
            operation["phase"] = "mkdir"
            run._save("restoring")
            target.mkdir(parents=True, exist_ok=True)
        elif kind == "restore":
            expected = run.manifest["roots"][name]["files"][relative]
            stage = _check_path(operation["stage"])
            # replace() 직후 journal 저장 전 중단되어도 다시 덮어쓰지 않는다.
            if operation["phase"] == "replace" and not stage.exists() and _matches(target, expected):
                operation["phase"] = "verified"
                run._save("restoring")
                continue
            before = _check_path(run.data_dir / "before" / name / relative)
            if not _matches(before, expected):
                raise PreservationError("교체 전 사전 사본 검증 실패")
            _safe_current(run, operation, target)
            operation["phase"] = "stage"
            run._save("restoring")
            if stage.exists() and not _matches(stage, expected):
                # 이 journal이 소유하는 불완전 임시 사본만 재작성한다.
                stage.unlink()
            _file_copy(before, stage, expected)
            operation["phase"] = "replace"
            run._save("restoring")
            _safe_current(run, operation, target)
            if not _matches(before, expected) or not _matches(stage, expected):
                raise PreservationError("교체 직전 복원 사본 검증 실패")
            os.replace(stage, target)
            if not _matches(target, expected):
                raise PreservationError("교체된 파일 검증 실패")
        else:
            raise PreservationError("알 수 없는 복원 작업")
        operation["phase"] = "verified"
        run._save("restoring")


def _restore_error_detail(run, error):
    """오류 문구·실제 경로 대신 코드와 첫 미검증 작업의 안전한 필드만 남긴다."""
    detail = {"errno": None, "winerror": None, "operation": None}
    if isinstance(error, OSError):
        for key in ("errno", "winerror"):
            value = getattr(error, key, None)
            if isinstance(value, int) and not isinstance(value, bool):
                detail[key] = value
        known = {os.path.normcase(os.path.abspath(str(run.run_dir / name))): role
                 for name, role in [('journal.json', 'journal'), ('manifest.json', 'manifest'),
                                    ('archive_manifest.json', 'archive_manifest')]}
        for value in (error.filename, getattr(error, 'filename2', None)):
            if isinstance(value, (str, bytes, os.PathLike)):
                role = known.get(os.path.normcase(os.path.abspath(os.fsdecode(value))))
                if role:
                    detail['resource_role'] = role
                    break
    operations = run.journal.get("delta_operations", [])
    if not isinstance(operations, list):
        return detail
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            detail["operation"] = {"index": index, "kind": None, "root": None,
                                   "relative": None, "phase": None}
            break
        kind, phase = operation.get("kind"), operation.get("phase")
        if phase == "verified":
            continue
        relative = operation.get("relative")
        try:
            relative = (_relative_path(relative) if relative else "") if isinstance(relative, str) else None
        except PreservationError:
            relative = None
        root = operation.get("root", "")
        detail["operation"] = {
            "index": index,
            "kind": kind if isinstance(kind, str) and kind in {"quarantine", "mkdir", "restore"} else None,
            "root": root if isinstance(root, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", root) else None,
            "relative": relative,
            "phase": phase if isinstance(phase, str) and phase in {"planned", "quarantine", "mkdir", "stage", "replace"} else None,
        }
        break
    return detail


def finalize_shared(run):
    result = {"run_id": run.run_id, "manifest": str(run.run_dir / "manifest.json"),
              "backup": str(run.data_dir), "archive_manifest": str(run.run_dir / "archive_manifest.json"),
              "roots": {}, "db": {"status": "no_prior_copy"}}
    try:
        run._validate()
        if not run._verify_backups():
            result["status"] = "mismatch"
            run._save("mismatch", result=result)
            return result
        _archive(run)
        if run.restore_after:
            _restore_operations(run)
            db = run.manifest.get("db")
            if db:
                _verify_archive(run)
                directory = _check_path(run.data_dir / "database")
                if snapshot(directory) != db["files"] or not run.db_adapter.verify_backup(directory, db["metadata"]):
                    raise PreservationError("복원 직전 DB 사전 사본 검증 실패")
                phase = run.journal.get("db_restore_phase")
                if phase != "verified":
                    if phase != "restore" or not run.db_adapter.verify_restored(directory, db["metadata"]):
                        run._save("restoring", db_restore_phase="restore")
                        run.db_adapter.restore(directory, db["metadata"])
                    if not run.db_adapter.verify_restored(directory, db["metadata"]):
                        raise PreservationError("DB 복원 검증 실패")
                    run._save("restoring", db_restore_phase="verified")
                elif not run.db_adapter.verify_restored(directory, db["metadata"]):
                    raise PreservationError("복원 후 DB가 변경되었습니다")
                result["db"] = {"status": "verified", "scope": db["metadata"]["scope"]}
            if any(snapshot(run.roots[name]) != expected for name, expected in run.manifest["roots"].items()):
                result["status"] = "mismatch"
                run._save("mismatch", result=result)
                return result
        _verify_archive(run)
        for name, before in run.manifest["roots"].items():
            status = ("verified" if run.restore_after else "preserved") if before["exists"] else "no_prior_copy"
            result["roots"][name] = {"status": status,
                                     "restoration_status": "verified" if run.restore_after else "preserved",
                                     "archive": str(run.data_dir / "archive" / name)}
        result["status"] = "verified" if run.restore_after else "preserved"
        run._save("verified" if run.restore_after else "completed", result=result)
    except Exception as exc:
        result["status"] = "error"
        result["error_type"] = type(exc).__name__
        try:
            result["error_detail"] = _restore_error_detail(run, exc)
        except Exception:
            # 진단 자료가 손상돼도 최초 오류와 error journal 저장을 가리지 않는다.
            result["error_detail"] = {"errno": None, "winerror": None, "operation": None}
        run._save("error", result=result)
    return result


def _cleanup_destination(run, index, operation):
    source = run.roots["Image"]
    boundary = source.with_name(f".{source.name}.bellalun-{run.run_id}-quarantine")
    expected = boundary / str(index)
    if _absolute(operation.get("destination", "")) != _absolute(expected):
        raise PreservationError("Image 격리 경로의 실행 소유권 불일치")
    if operation.get("phase") != "verified":
        raise PreservationError("Image 격리가 검증되지 않았습니다")
    _check_path(boundary)
    return _check_path(expected)


def _cleanup_candidates(run):
    """journal의 격리 작업으로부터 생성 파일과 소유 경계를 다시 유도한다."""
    candidates, quarantines = [], []
    before = run.manifest["roots"]["Image"]
    for index, operation in enumerate(run.journal.get("delta_operations", [])):
        if operation.get("kind") != "quarantine" or operation.get("root") != "Image":
            continue
        destination = _cleanup_destination(run, index, operation)
        relative = operation["relative"]
        if relative:
            relative = _relative_path(relative)
        original = operation["expected"]
        quarantines.append((index, destination, original))
        if original["kind"] == "directory":
            files = original["snapshot"]["files"]
        elif original["kind"] == "file":
            files = {"": {"size": original["size"], "sha256": original["sha256"]}}
        else:
            raise PreservationError("Image 격리 항목의 형식이 잘못되었습니다")
        for local_relative, metadata in files.items():
            if local_relative:
                local_relative = _relative_path(local_relative)
            image_relative = "/".join(p for p in (relative, local_relative) if p)
            # 사전에 존재한 영상의 상대경로는 내용이 달라졌어도 삭제하지 않는다.
            if image_relative in before["files"]:
                continue
            candidates.append({"operation": index, "local_relative": local_relative,
                               "image_relative": image_relative, "metadata": metadata,
                               "phase": "planned"})
    return candidates, quarantines


def _cleanup_file_path(run, item):
    index = item["operation"]
    operation = run.journal["delta_operations"][index]
    if operation.get("kind") != "quarantine" or operation.get("root") != "Image":
        raise PreservationError("Image 정리 대상이 다른 보존 범위를 가리킵니다")
    base = _cleanup_destination(run, index, operation)
    relative = item["local_relative"]
    return _check_path(base / _relative_path(relative) if relative else base)


def _cleanup_remote_path(run, item):
    archive = run.journal["archive"]["roots"]["Image"]
    relative, metadata = item["image_relative"], item["metadata"]
    if not relative and archive["snapshot"].get("root_file"):
        if archive["snapshot"]["root_file"] != metadata:
            raise PreservationError("Image root 파일 사본 metadata 불일치")
        return _check_path(run.data_dir / "archive" / "Image" / ".root-file")
    relative = _relative_path(relative)
    if archive["snapshot"]["files"].get(relative) != metadata:
        raise PreservationError("Image 파일의 시험 후 목록 불일치")
    origin = archive["references"].get(relative)
    if origin not in {"before", "archive"}:
        raise PreservationError("Image 파일의 공용 사본 참조가 잘못되었습니다")
    return _check_path(run.data_dir / origin / "Image" / relative)


def _verify_cleanup_batch(run, items, quarantines):
    """모든 로컬/NAS 파일을 검증한 뒤에만 첫 unlink를 허용한다."""
    verify_store(run.journal["storage"])
    removed = set()
    for item in items:
        path = _cleanup_file_path(run, item)
        remote = _cleanup_remote_path(run, item)
        if not _matches(remote, item["metadata"]):
            raise PreservationError("Image 정리 전 공용 파일 사본 검증 실패")
        phase = item["phase"]
        if phase not in {"planned", "removing", "removed"}:
            raise PreservationError("알 수 없는 Image 정리 진행 단계")
        if not path.exists() and phase in {"removing", "removed"}:
            removed.add((item["operation"], item["local_relative"]))
        elif phase == "removed" or not _matches(path, item["metadata"]):
            raise PreservationError("Image 정리 전 로컬 격리 파일 검증 실패")
    for index, destination, original in quarantines:
        expected = copy.deepcopy(original)
        if original["kind"] == "directory":
            for operation, relative in removed:
                if operation == index:
                    expected["snapshot"]["files"].pop(relative, None)
        elif (index, "") in removed:
            expected = {"kind": "missing"}
        if _entry(destination) != expected:
            raise PreservationError("Image 격리 경로의 전체 목록/해시 불일치")
    return removed


def _cleanup_counts(items):
    removed = [item for item in items if item["phase"] == "removed"]
    return {"files_removed": len(removed),
            "logical_bytes_removed": sum(item["metadata"]["size"] for item in removed)}


def _cleanup_mark_pending(run):
    # journal 교체 자체가 실패해도 로컬 pending 검색에서 다음 실행을 막는다.
    _write_json(run.run_dir / "image-cleanup-pending.json", {"run_id": run.run_id})


def cleanup_generated_images(run, *, normal_completion=False, services_verified=False):
    """사용자가 승인한 예외: 이 실행 Image 격리에 있는 생성 파일만 제거한다."""
    skipped = {"status": "skipped", "files_removed": 0, "logical_bytes_removed": 0}
    result = run.journal.get("result", {}) if run.journal else {}
    reason = None
    if run.storage_dir is None:
        reason = "shared_storage_not_selected"
    elif not run.restore_after:
        reason = "restore_not_selected"
    elif not normal_completion:
        reason = "not_normal_completion"
    elif not services_verified:
        reason = "services_not_verified"
    elif "Image" not in run.roots:
        reason = "image_root_not_configured"
    elif (not run.journal or not run.manifest
          or result.get("status") not in {"verified", "cleanup_required"}
          or (result.get("status") == "cleanup_required" and result.get("restoration_status") != "verified")
          or not run.journal.get("backup_complete") or not run.journal.get("archive_complete")
          or set(result.get("roots", {})) != set(run.roots)
          or any(root.get("restoration_status") != "verified" for root in result.get("roots", {}).values())
          or result.get("db", {}).get("status") not in {"verified", "no_prior_copy"}
          or (run.manifest.get("db") and result.get("db", {}).get("status") != "verified")):
        reason = "restoration_not_verified"
    if reason:
        return dict(skipped, reason=reason)
    prior = run.journal.get("image_cleanup", {})
    if prior.get("status") == "completed":
        marker = _check_path(run.run_dir / "image-cleanup-pending.json")
        if not marker.exists():
            return prior["result"]
        try:
            # 최종 journal 기록 뒤 marker 제거 직전에 중단된 경우다.
            result.update(status="verified", restoration_status="verified", image_cleanup=prior["result"])
            run._save("verified", result=result)
            marker.unlink()
            return prior["result"]
        except Exception as exc:
            result.update(status="cleanup_required", restoration_status="verified")
            run.journal["state"] = "cleanup_required"
            return dict(status="cleanup_required", reason="journal_finalization_failed",
                        error_type=type(exc).__name__, **_cleanup_counts(prior.get("files", [])))
    items = prior.get("files", [])
    try:
        run._validate()
        candidates, quarantines = _cleanup_candidates(run)
        if prior:
            if [dict(item, phase="planned") for item in items] != candidates:
                raise PreservationError("Image 정리 계획과 격리 소유 기록이 달라졌습니다")
        else:
            items = candidates
        removed = _verify_cleanup_batch(run, items, quarantines)
        if not items:
            return dict(skipped, reason="no_generated_images")
        for item in items:
            if (item["operation"], item["local_relative"]) in removed:
                item["phase"] = "removed"
        run.journal["image_cleanup"] = {"status": "in_progress", "files": items}
        result["restoration_status"] = "verified"
        result["status"] = "cleanup_required"
        result["image_cleanup"] = dict(status="cleanup_required", reason="cleanup_in_progress",
                                        **_cleanup_counts(items))
        _cleanup_mark_pending(run)
        run._save("cleanup_required", result=result)
        for item in items:
            if item["phase"] == "removed":
                continue
            # 전체 사전 검증 뒤에도 각 unlink 직전에 저장소·대상 해시를 재확인한다.
            verify_store(run.journal["storage"])
            if not _matches(_cleanup_remote_path(run, item), item["metadata"]):
                raise PreservationError("Image 삭제 직전 공용 사본 검증 실패")
            path = _cleanup_file_path(run, item)
            if not _matches(path, item["metadata"]):
                raise PreservationError("Image 삭제 직전 로컬 파일 검증 실패")
            item["phase"] = "removing"
            run._save("cleanup_required", result=result)
            path.unlink()
            item["phase"] = "removed"
            result["image_cleanup"].update(_cleanup_counts(items))
            run._save("cleanup_required", result=result)
        cleanup = dict(status="completed", **_cleanup_counts(items))
        run.journal["image_cleanup"].update(status="completed", result=cleanup)
        result.update(status="verified", image_cleanup=cleanup)
        run._save("verified", result=result)
        _check_path(run.run_dir / "image-cleanup-pending.json").unlink()
        return cleanup
    except Exception as exc:
        # unlink 이후 예외가 났어도 내구성 있는 intent와 부재를 함께 확인한다.
        for item in items:
            if item.get("phase") == "removing":
                try:
                    if not _cleanup_file_path(run, item).exists():
                        item["phase"] = "removed"
                except (OSError, ValueError, PreservationError):
                    pass
        cleanup = dict(status="cleanup_required", reason="verification_or_removal_failed",
                       error_type=type(exc).__name__, **_cleanup_counts(items))
        if "image_cleanup" not in run.journal:
            run.journal["image_cleanup"] = {"status": "failed", "files": items}
        else:
            run.journal["image_cleanup"]["status"] = "failed"
        result.update(status="cleanup_required", restoration_status="verified", image_cleanup=cleanup)
        run.journal["state"] = "cleanup_required"
        try:
            _cleanup_mark_pending(run)
            run._save("cleanup_required", result=result)
        except Exception as journal_exc:
            cleanup["journal_error_type"] = type(journal_exc).__name__
        return cleanup
