"""실행별 파일 보존. 제품/SQL 동작은 호출자가 명시적으로 주입한다.

작업 중 제품은 정지 상태여야 한다. 파일 목록과 해시를 앞뒤로 대조하지만
외부 쓰기 프로세스를 잠그는 서비스가 아니므로 실행 경계에서 호출한다.
보관·사전 사본·복원 중 옮긴 원본은 자동 삭제하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
import re
import shutil
import stat


class PreservationError(RuntimeError):
    pass


class RecoveryRequired(PreservationError):
    pass


def _absolute(path):
    value = os.fspath(path)
    if os.name == "nt":
        if value[:8].lower() == "\\\\?\\unc\\":
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
    return Path(os.path.abspath(value))


def _io_path(path):
    """Windows의 긴 로컬/UNC 경로를 Win32 extended-length 형식으로 연다."""
    path = _absolute(path)
    value = str(path)
    if os.name == "nt" and not value.startswith("\\\\?\\") and len(value) >= 240:
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return Path(value)


def _check_path(path):
    """resolve 이전에 모든 조상의 reparse point도 거부한다."""
    path = _io_path(path)
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise PreservationError(f"링크/reparse 경로는 보존할 수 없습니다: {part}")
    return path


def _hash(path):
    path = _check_path(path)
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot(root):
    """존재 여부·정확한 파일/빈 폴더 목록·파일별 SHA-256. 링크는 추적하지 않는다."""
    root = _check_path(root)
    if not root.exists():
        return {"exists": False, "directories": [], "files": {}}
    if not root.is_dir():
        raise PreservationError(f"보존 root는 폴더여야 합니다: {root}")
    result = {"exists": True, "directories": [], "files": {}}
    def visit(directory, prefix=""):
        with os.scandir(directory) as listing:
            entries = sorted(listing, key=lambda item: item.name)
        for entry in entries:
            path = _check_path(entry.path)
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                result["directories"].append(relative)
                visit(path, relative)
            elif stat.S_ISREG(info.st_mode):
                result["files"][relative] = {"size": info.st_size, "sha256": _hash(path)}
            else:
                raise PreservationError(f"일반 파일이 아닌 항목: {path}")
    visit(root)
    result["directories"].sort()
    return result


def _inside(child, parent):
    return child == parent or parent in child.parents


def _write_json(path, value):
    path = _check_path(path)
    temp = path.with_name(path.name + ".tmp")
    _check_path(temp)
    with temp.open("w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp, path)


def _copy_tree(source, destination, expected):
    source = _check_path(source)
    destination = _check_path(destination)
    if destination.exists():
        raise PreservationError(f"기존 사본을 덮어쓰지 않습니다: {destination}")
    if not expected["exists"]:
        return
    destination.mkdir(parents=True)
    for directory in expected["directories"]:
        _check_path(destination / _relative_path(directory)).mkdir(parents=True, exist_ok=True)
    for relative in expected["files"]:
        relative = _relative_path(relative)
        src, dst = _check_path(source / relative), _check_path(destination / relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        # Windows의 _commit은 쓰기 가능한 descriptor를 요구한다.
        copied_mode = dst.stat().st_mode
        dst.chmod(copied_mode | stat.S_IWRITE)
        with dst.open("r+b") as copied:
            os.fsync(copied.fileno())
        dst.chmod(copied_mode)
    if snapshot(destination) != expected or snapshot(source) != expected:
        raise PreservationError("복사 후 파일 목록 또는 내용 해시가 일치하지 않습니다")


def _relative_path(value):
    value = str(value)
    path = PurePosixPath(value.replace("\\", "/"))
    windows = PureWindowsPath(value)
    if not value or path.as_posix() == "." or path.is_absolute() or windows.drive or any(p in {"..", "."} for p in path.parts):
        raise PreservationError("보존 파일의 상대경로가 범위를 벗어납니다")
    if ":" in value:
        raise PreservationError("보존 파일의 대체 데이터 스트림은 허용하지 않습니다")
    return path.as_posix()


def preserved_path(result, root_name, relative):
    """시험 후 자료를 찾는다. 공용 모드의 변경 없는 파일은 before를 참조한다."""
    relative = _relative_path(relative)
    locator = result.get("archive_manifest")
    if locator:
        manifest = json.loads(_check_path(locator).read_text(encoding="utf-8"))
        run_id = manifest.get("run_id", "")
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", run_id)
                or run_id != result.get("run_id")):
            raise PreservationError("보존 위치의 실행 번호 불일치")
        root = manifest.get("roots", {}).get(root_name)
        if root is None or relative not in root["snapshot"]["files"]:
            return None
        from core.preservation_storage import verify_store
        storage = manifest["storage"]
        verify_store(storage)
        base = _check_path(storage["path"]) / manifest["run_id"]
        origin = root["references"][relative]
        if origin not in {"before", "archive"}:
            raise PreservationError("알 수 없는 보존 참조")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", root_name):
            raise PreservationError("유효하지 않은 보존 범위 이름")
        path = _check_path(base / origin / root_name / relative)
        expected = root["snapshot"]["files"][relative]
        if not path.is_file() or path.stat().st_size != expected["size"] or _hash(path) != expected["sha256"]:
            raise PreservationError("시험 후 보존 파일 검증 실패")
        return path
    root = result.get("roots", {}).get(root_name, {})
    archive = root.get("archive")
    if not archive:
        return None
    path = _check_path(Path(archive) / relative)
    return path if path.is_file() else None


def roots_from_config(cfg, usb_drive=None):
    data_dir = cfg.get("data_dir")
    parameters = (cfg.get("xipl") or {}).get("parameter_dir")
    if not data_dir or not parameters:
        raise PreservationError("data_dir와 xipl.parameter_dir 설정이 필요합니다")
    roots = {name: _absolute(Path(data_dir) / name)
             for name in ("Config", "Image", "ImageTemp", "Export", "ExportSettingTemp")}
    roots["xipl"] = _absolute(parameters)
    if usb_drive:
        roots["usb"] = _absolute(Path(usb_drive) / "BellalunWU09")
    return roots


class RunPreservation:
    """prepare 성공 후에만 제품을 실행하고 모든 종료 경계에서 finalize를 호출한다.

    DB adapter: backup(folder)->metadata, verify_backup(folder,metadata)->bool,
    restore(folder,metadata), verify_restored(folder,metadata)->bool.
    DB metadata는 비교 테이블/열 범위를 명시해야 한다. 자동 SQL은 없다.
    """
    TERMINAL = {"completed", "verified"}

    def __init__(self, workspace, run_id, roots, restore_after=False, db_adapter=None,
                 storage_dir=None, require_finalization=False):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", run_id):
            raise PreservationError("유효하지 않은 실행 번호")
        self.workspace = _absolute(workspace)
        self.run_id = run_id
        self.roots = {name: _absolute(path) for name, path in roots.items()}
        self.run_dir = self.workspace / "preservation" / run_id
        self.storage_dir = _absolute(storage_dir) if storage_dir is not None else None
        self.data_dir = self.storage_dir / run_id if self.storage_dir is not None else self.run_dir
        self.restore_after = bool(restore_after)
        self.db_adapter = db_adapter
        self.require_finalization = bool(require_finalization)
        self.manifest = None
        self.journal = None

    def _validate(self):
        _check_path(self.workspace)
        _check_path(self.run_dir)
        if not self.roots:
            raise PreservationError("보존 범위가 비어 있습니다")
        paths = []
        for name, path in self.roots.items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name):
                raise PreservationError("유효하지 않은 범위 이름")
            _check_path(path)
            if _inside(self.run_dir, path) or _inside(path, self.run_dir):
                raise PreservationError("원본과 백업 경로가 겹칩니다")
            if self.storage_dir is not None:
                _check_path(self.storage_dir)
                if _inside(self.storage_dir, path) or _inside(path, self.storage_dir):
                    raise PreservationError("원본과 공용 저장소 경로가 겹칩니다")
            if any(_inside(path, other) or _inside(other, path) for other in paths):
                raise PreservationError("보존 폴더가 중복되거나 중첩됩니다")
            paths.append(path)

    @classmethod
    def pending(cls, workspace):
        parent = _check_path(Path(workspace) / "preservation")
        if not parent.exists():
            return []
        pending = []
        for directory in parent.iterdir():
            _check_path(directory)
            if not directory.is_dir():
                raise RecoveryRequired("보존 저장소에 알 수 없는 항목이 있습니다")
            try:
                marker = _check_path(directory / "image-cleanup-pending.json")
                if marker.exists():
                    pending.append(directory.name)
                    continue
                _check_path(directory / "journal.json")
                journal = json.loads((directory / "journal.json").read_text(encoding="utf-8"))
                if journal["state"] not in cls.TERMINAL or journal.get("execution_finalization_pending"):
                    pending.append(directory.name)
            except (OSError, ValueError, KeyError):
                pending.append(directory.name)
        return pending

    def _save(self, state, **fields):
        self.journal.update(fields)
        self.journal["state"] = state
        _write_json(self.run_dir / "journal.json", self.journal)

    def prepare(self):
        self._validate()
        if self.run_dir.exists():
            raise PreservationError("기존 실행 백업은 재사용하거나 덮어쓸 수 없습니다")
        pending = self.pending(self.workspace)
        if pending:
            raise RecoveryRequired("미완료 보존 기록의 명시적 복구가 필요합니다: " + ", ".join(pending))
        self.run_dir.mkdir(parents=True)
        self.journal = {"run_id": self.run_id, "roots": {k: str(v) for k, v in self.roots.items()},
                        "restore_after": self.restore_after, "operations": []}
        if self.require_finalization:
            # 복원 verified는 서비스·보고서·정리까지 마친 실행 완료가 아니다.
            # 제품 시작 전에 기록하여 finalize 직후의 강제 종료도 다음 실행을 막는다.
            self.journal["execution_finalization_pending"] = True
        if self.storage_dir is not None:
            self.journal["storage"] = {"mode": "shared_delta", "path": str(self.storage_dir)}
        self._save("preparing")
        try:
            if self.storage_dir is not None:
                from core.preservation_storage import prepare_store
                prepare_store(self)
            self.manifest = {"version": 1, "run_id": self.run_id,
                             "roots": {name: snapshot(path) for name, path in self.roots.items()},
                             "db": None}
            _write_json(self.run_dir / "manifest.json", self.manifest)
            for name, path in self.roots.items():
                _copy_tree(path, self.data_dir / "before" / name, self.manifest["roots"][name])
            if self.db_adapter is not None:
                db_dir = _check_path(self.data_dir / "database")
                db_dir.mkdir()
                metadata = self.db_adapter.backup(db_dir)
                if not isinstance(metadata, dict) or not metadata.get("scope"):
                    raise PreservationError("DB 비교 범위(scope)가 없습니다")
                if not self.db_adapter.verify_backup(db_dir, metadata):
                    raise PreservationError("DB 사전 사본 검증 실패")
                self.manifest["db"] = {"metadata": metadata, "files": snapshot(db_dir)}
                _write_json(self.run_dir / "manifest.json", self.manifest)
            # 사본 작성 도중 다른 root가 변한 경우도 시작을 거부한다.
            for name, path in self.roots.items():
                if snapshot(path) != self.manifest["roots"][name]:
                    raise PreservationError("사전 백업 도중 원본이 변경되었습니다")
            self._save("prepared", backup_complete=True)
            return {"status": "prepared", "manifest": str(self.run_dir / "manifest.json"),
                    "backup": str(self.data_dir), "run_id": self.run_id}
        except Exception as exc:
            self._save("error", error_type=type(exc).__name__)
            raise PreservationError("사전 보존 실패: 제품 실행을 차단합니다") from exc

    def _verify_backups(self):
        if self.storage_dir is not None:
            from core.preservation_storage import verify_store
            verify_store(self.journal["storage"])
        for name, expected in self.manifest["roots"].items():
            if snapshot(self.data_dir / "before" / name) != expected:
                return False
        db = self.manifest.get("db")
        if db:
            if self.db_adapter is None:
                raise PreservationError("DB 사본이 있으므로 명시적 DB adapter가 필요합니다")
            db_dir = _check_path(self.data_dir / "database")
            return (snapshot(db_dir) == db["files"]
                    and self.db_adapter.verify_backup(db_dir, db["metadata"]))
        return True

    def finalize(self):
        if self.journal is None or self.manifest is None:
            raise PreservationError("준비되지 않은 실행입니다")
        if self.journal["state"] in self.TERMINAL:
            return self.journal["result"]
        if self.journal["state"] == "cleanup_required":
            return self.journal["result"]
        if self.storage_dir is not None:
            from core.preservation_storage import finalize_shared
            return finalize_shared(self)
        result = {"run_id": self.run_id, "manifest": str(self.run_dir / "manifest.json"),
                  "backup": str(self.run_dir), "roots": {}, "db": {"status": "no_prior_copy"}}
        try:
            self._validate()
            if not self._verify_backups():
                result["status"] = "mismatch"
                self._save("mismatch", result=result)
                return result
            if not self.restore_after:
                result["status"] = "preserved"
                result["roots"] = {name: {"status": "preserved" if before["exists"] else "no_prior_copy"}
                                   for name, before in self.manifest["roots"].items()}
                self._save("completed", result=result)
                return result
            self._save("restoring")
            for name, source in self.roots.items():
                before = self.manifest["roots"][name]
                current = snapshot(source)
                # 복구 재시도 시 앞선 archive를 덮어쓰지 않는다.
                sequence = len(self.journal["operations"])
                archive = self.run_dir / "archive" / (name if sequence < len(self.roots) else f"{name}-{sequence}")
                while archive.exists():
                    sequence += 1
                    archive = self.run_dir / "archive" / f"{name}-{sequence}"
                _copy_tree(source, archive, current)
                holding = source.with_name(f".{source.name}.bellalun-{self.run_id}-{sequence}")
                _check_path(holding)
                if holding.exists():
                    raise PreservationError("보존 이동 목적지가 이미 존재합니다")
                operation = {"root": name, "archive": str(archive), "holding": str(holding),
                             "current": current, "phase": "archived"}
                self.journal["operations"].append(operation)
                self._save("restoring")
                if current["exists"]:
                    if snapshot(source) != current:
                        raise PreservationError("보존 이동 전에 원본이 변경되었습니다")
                    os.replace(source, holding)  # 같은 볼륨의 원자적 이동, 원본 자동 삭제 없음
                operation["phase"] = "moved"
                self._save("restoring")
                _copy_tree(self.run_dir / "before" / name, source, before)
                if snapshot(source) != before:
                    result["status"] = "mismatch"
                    self._save("mismatch", result=result)
                    return result
                operation["phase"] = "verified"
                self._save("restoring")
                result["roots"][name] = {"status": "verified" if before["exists"] else "no_prior_copy",
                                         "restoration_status": "verified", "archive": str(archive),
                                         "holding": str(holding) if current["exists"] else None}
            db = self.manifest.get("db")
            if db:
                self.db_adapter.restore(self.run_dir / "database", db["metadata"])
                if not self.db_adapter.verify_restored(self.run_dir / "database", db["metadata"]):
                    result["status"] = "mismatch"
                    result["db"] = {"status": "mismatch", "scope": db["metadata"]["scope"]}
                    self._save("mismatch", result=result)
                    return result
                result["db"] = {"status": "verified", "scope": db["metadata"]["scope"]}
            # 복원된 root가 후속 root 복사 도중 변했는지도 다시 확인한다.
            if any(snapshot(self.roots[name]) != expected for name, expected in self.manifest["roots"].items()):
                result["status"] = "mismatch"
                self._save("mismatch", result=result)
                return result
            result["status"] = "verified"
            self._save("verified", result=result)
        except Exception as exc:
            result["status"] = "error"
            result["error_type"] = type(exc).__name__
            self._save("error", result=result)
        return result

    def cleanup_generated_images(self, *, normal_completion=False, services_verified=False):
        """정상 완주·복원·서비스 확인 뒤 자기 Image 격리 파일만 정리한다."""
        from core.preservation_storage import cleanup_generated_images
        return cleanup_generated_images(self, normal_completion=normal_completion,
                                        services_verified=services_verified)

    def finish_execution_finalization(self):
        """서비스·최종 보고서 저장을 끝낸 호출자만 실행 마무리 잠금을 해제한다."""
        if not self.journal.get("execution_finalization_pending"):
            return
        if (self.journal.get("state") not in self.TERMINAL
                or self.journal.get("result", {}).get("status") not in {"verified", "preserved"}):
            raise PreservationError("복원과 정리가 미완료인 실행은 마무리할 수 없습니다")
        self._save(self.journal["state"], execution_finalization_pending=False)

    def pin_cleanup_completion(self, report_data, command):
        """정리 전 정상완주 보고서를 로컬에 고정한다. 기존 증거는 덮어쓰지 않는다."""
        meta = report_data.get("meta", {}) if isinstance(report_data, dict) else {}
        if (command not in {"run-regression", "run-winupdate"}
                or meta.get("run_id") != self.run_id or meta.get("chain_completed") is not True
                or not self.journal or self.journal.get("result", {}).get("status") != "verified"):
            raise PreservationError("정상완주 보고서의 실행 번호/명령/완료 상태 불일치")
        encoded = json.dumps(report_data, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        proof = _check_path(self.run_dir / "cleanup-completion.json")
        if proof.exists():
            if proof.read_bytes() != encoded:
                raise PreservationError("기존 정상완주 증거를 덮어쓰지 않습니다")
        else:
            with proof.open("xb") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
        expected = hashlib.sha256(encoded).hexdigest()
        if _hash(proof) != expected:
            raise PreservationError("정상완주 증거의 파일 해시 불일치")
        locator = {"run_id": self.run_id, "command": command, "report": str(proof), "sha256": expected}
        previous = self.journal.get("normal_completion_before_cleanup")
        if previous and previous != locator:
            raise PreservationError("기존 정상완주 증거 위치/신원 불일치")
        self._save(self.journal["state"], normal_completion_before_cleanup=locator)
        return locator

    @classmethod
    def load(cls, workspace, run_id, db_adapter=None):
        """동작 없이 고정 journal을 읽는다. 정리 재개도 별도 완료 확인이 필요하다."""
        run = cls(workspace, run_id, {"placeholder": Path(workspace) / "placeholder"},
                  db_adapter=db_adapter)
        run.journal = json.loads(_check_path(run.run_dir / "journal.json").read_text(encoding="utf-8"))
        run.manifest = json.loads(_check_path(run.run_dir / "manifest.json").read_text(encoding="utf-8"))
        if run.journal.get("run_id") != run_id or run.manifest.get("run_id") != run_id:
            raise PreservationError("보존 기록의 실행 번호 불일치")
        run.roots = {name: _absolute(path) for name, path in run.journal["roots"].items()}
        if set(run.roots) != set(run.manifest["roots"]):
            raise PreservationError("보존 범위와 manifest 불일치")
        run.restore_after = bool(run.journal.get("restore_after"))
        storage = run.journal.get("storage")
        if storage:
            if storage.get("mode") != "shared_delta" or not storage.get("path"):
                raise PreservationError("알 수 없는 보존 저장소 기록")
            run.storage_dir = _absolute(storage["path"])
            run.data_dir = run.storage_dir / run_id
        if _check_path(run.run_dir / "image-cleanup-pending.json").exists():
            result = run.journal.get("result", {})
            if result.get("status") == "verified":
                result.update(status="cleanup_required", restoration_status="verified")
                run.journal["state"] = "cleanup_required"
        return run

    @classmethod
    def recover(cls, workspace, run_id, db_adapter=None, restore_after=True,
                acknowledge_unstarted=False):
        """사람이 선택한 실행만 복구. 불완전 prepare는 복원으로 추측 처리하지 않는다."""
        run = cls(workspace, run_id, {"placeholder": Path(workspace) / "placeholder"},
                  restore_after=restore_after, db_adapter=db_adapter)
        _check_path(run.run_dir)
        _check_path(run.run_dir / "journal.json")
        _check_path(run.run_dir / "manifest.json")
        run.journal = json.loads((run.run_dir / "journal.json").read_text(encoding="utf-8"))
        if run.journal.get("run_id") != run_id:
            raise PreservationError("복구 기록의 실행 번호 불일치")
        storage = run.journal.get("storage")
        if storage:
            if storage.get("mode") != "shared_delta" or not storage.get("path"):
                raise PreservationError("알 수 없는 보존 저장소 기록")
            run.storage_dir = _absolute(storage["path"])
            run.data_dir = run.storage_dir / run_id
        if acknowledge_unstarted:
            if run.journal.get("backup_complete") or run.journal.get("operations"):
                raise PreservationError("이미 준비되거나 복원이 시작된 실행은 미시작으로 확인할 수 없습니다")
            result = {"status": "unstarted_acknowledged", "run_id": run_id,
                      "backup": str(run.run_dir)}
            run._save("completed", result=result, execution_finalization_pending=False)
            return result
        run.manifest = json.loads((run.run_dir / "manifest.json").read_text(encoding="utf-8"))
        if run.manifest.get("run_id") != run_id:
            raise PreservationError("복구 manifest 실행 번호 불일치")
        run.roots = {name: _absolute(path) for name, path in run.journal["roots"].items()}
        if set(run.roots) != set(run.manifest["roots"]):
            raise PreservationError("복구 범위와 manifest 불일치")
        if _check_path(run.run_dir / "image-cleanup-pending.json").exists():
            result = dict(run.journal.get("result", {}))
            result.update(status="cleanup_required", restoration_status="verified")
            return result
        if run.journal["state"] in cls.TERMINAL or run.journal["state"] == "cleanup_required":
            if run.journal.get("execution_finalization_pending"):
                return dict(run.journal.get("result", {}), status="finalization_required",
                            reason="services_report_or_cleanup_unfinished")
            return run.journal.get("result", {"status": run.journal["state"]})
        if not run.journal.get("backup_complete"):
            raise PreservationError("불완전 사전 백업은 복원할 수 없습니다. 미시작 사실 확인이 필요합니다")
        result = run.finalize()
        if run.journal.get("execution_finalization_pending") and result.get("status") == "verified":
            return dict(result, status="finalization_required",
                        reason="services_report_or_cleanup_unfinished")
        return result
