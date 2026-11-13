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
import re
import shutil
import stat


class PreservationError(RuntimeError):
    pass


class RecoveryRequired(PreservationError):
    pass


def _absolute(path):
    return Path(os.path.abspath(os.fspath(path)))


def _check_path(path):
    """resolve 이전에 모든 조상의 reparse point도 거부한다."""
    path = _absolute(path)
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise PreservationError(f"링크/reparse 경로는 보존할 수 없습니다: {part}")
    return path


def _hash(path):
    _check_path(path)
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
    def visit(directory):
        with os.scandir(directory) as listing:
            entries = sorted(listing, key=lambda item: item.name)
        for entry in entries:
            path = _check_path(entry.path)
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                result["directories"].append(relative)
                visit(path)
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
    _check_path(source)
    _check_path(destination)
    if destination.exists():
        raise PreservationError(f"기존 사본을 덮어쓰지 않습니다: {destination}")
    if not expected["exists"]:
        return
    destination.mkdir(parents=True)
    for directory in expected["directories"]:
        (destination / directory).mkdir(parents=True, exist_ok=True)
    for relative in expected["files"]:
        src, dst = source / relative, destination / relative
        _check_path(src)
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

    def __init__(self, workspace, run_id, roots, restore_after=False, db_adapter=None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", run_id):
            raise PreservationError("유효하지 않은 실행 번호")
        self.workspace = _absolute(workspace)
        self.run_id = run_id
        self.roots = {name: _absolute(path) for name, path in roots.items()}
        self.run_dir = self.workspace / "preservation" / run_id
        self.restore_after = bool(restore_after)
        self.db_adapter = db_adapter
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
                _check_path(directory / "journal.json")
                journal = json.loads((directory / "journal.json").read_text(encoding="utf-8"))
                if journal["state"] not in cls.TERMINAL:
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
        self._save("preparing")
        try:
            self.manifest = {"version": 1, "run_id": self.run_id,
                             "roots": {name: snapshot(path) for name, path in self.roots.items()},
                             "db": None}
            _write_json(self.run_dir / "manifest.json", self.manifest)
            for name, path in self.roots.items():
                _copy_tree(path, self.run_dir / "before" / name, self.manifest["roots"][name])
            if self.db_adapter is not None:
                db_dir = self.run_dir / "database"
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
                    "backup": str(self.run_dir), "run_id": self.run_id}
        except Exception as exc:
            self._save("error", error_type=type(exc).__name__)
            raise PreservationError("사전 보존 실패: 제품 실행을 차단합니다") from exc

    def _verify_backups(self):
        for name, expected in self.manifest["roots"].items():
            if snapshot(self.run_dir / "before" / name) != expected:
                return False
        db = self.manifest.get("db")
        if db:
            if self.db_adapter is None:
                raise PreservationError("DB 사본이 있으므로 명시적 DB adapter가 필요합니다")
            db_dir = self.run_dir / "database"
            return (snapshot(db_dir) == db["files"]
                    and self.db_adapter.verify_backup(db_dir, db["metadata"]))
        return True

    def finalize(self):
        if self.journal is None or self.manifest is None:
            raise PreservationError("준비되지 않은 실행입니다")
        if self.journal["state"] in self.TERMINAL:
            return self.journal["result"]
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
        if acknowledge_unstarted:
            if run.journal.get("backup_complete") or run.journal.get("operations"):
                raise PreservationError("이미 준비되거나 복원이 시작된 실행은 미시작으로 확인할 수 없습니다")
            result = {"status": "unstarted_acknowledged", "run_id": run_id,
                      "backup": str(run.run_dir)}
            run._save("completed", result=result)
            return result
        run.manifest = json.loads((run.run_dir / "manifest.json").read_text(encoding="utf-8"))
        if run.manifest.get("run_id") != run_id:
            raise PreservationError("복구 manifest 실행 번호 불일치")
        run.roots = {name: _absolute(path) for name, path in run.journal["roots"].items()}
        if set(run.roots) != set(run.manifest["roots"]):
            raise PreservationError("복구 범위와 manifest 불일치")
        if run.journal["state"] in cls.TERMINAL:
            return run.journal.get("result", {"status": run.journal["state"]})
        if not run.journal.get("backup_complete"):
            raise PreservationError("불완전 사전 백업은 복원할 수 없습니다. 미시작 사실 확인이 필요합니다")
        return run.finalize()
