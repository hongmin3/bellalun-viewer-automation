"""SQLite 실행 상태와 PC별 영속 잠금. 원격 종료를 확인하지 못하면 잠금을 유지한다."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from remote.bundles import BundleError, check_local, create_bundle, unpack_bundle


class RemoteError(RuntimeError):
    pass


class RemoteBlocked(RemoteError):
    """원격 제품 프로세스 시작 전 확인된 준비 차단."""


class Coordinator:
    ACTIVE = ("queued", "running", "cancelling", "uncertain")

    def __init__(self, root, pcs, profiles, executor):
        self.root = check_local(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.pcs, self.profiles, self.executor = pcs, profiles, executor
        if hasattr(executor, "configure_state_root"):
            executor.configure_state_root(self.root / "interlocks")
        self.db = self.root / "jobs.sqlite3"
        self.mutex = threading.RLock()
        self.events = {}
        with self._connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, pc TEXT NOT NULL, status TEXT NOT NULL, record TEXT NOT NULL)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS active_pc ON jobs(pc) WHERE status IN ('queued','running','cancelling','uncertain')")
            for job_id, record in conn.execute("SELECT id,record FROM jobs WHERE status IN ('queued','running','cancelling')").fetchall():
                data = json.loads(record)
                data["status"] = "uncertain"
                data["reason"] = "서버 재시작: 원격 종료를 확인하기 전 PC 잠금 유지"
                conn.execute("UPDATE jobs SET status='uncertain',record=? WHERE id=?", (json.dumps(data), job_id))

    def _connection(self):
        return sqlite3.connect(self.db, timeout=20)

    def _job_dir(self, job_id):
        if not re.fullmatch(r"[0-9a-f]{32}", job_id or ""):
            raise RemoteError("유효하지 않은 실행 ID")
        return self.root / "jobs" / job_id

    def add_bundle(self, package, identity):
        with self.mutex:
            path = self.root / "bundles" / identity if re.fullmatch("[0-9a-f]{64}", identity or "") else None
            if path is None:
                raise BundleError("유효하지 않은 묶음 ID")
            if path.exists():
                if (path / "package.zip").read_bytes() != package:
                    raise BundleError("같은 ID의 다른 압축 묶음을 덮어쓰지 않습니다")
                return {"bundle_id": identity}
            unpack_bundle(package, path, identity)
            (path / "package.zip").write_bytes(package)
            return {"bundle_id": identity}

    def submit(self, pc_id, profile_id, bundle_id, restore_after=False):
        if type(restore_after) is not bool:
            raise RemoteError("복원 선택은 bool이어야 합니다")
        if pc_id not in self.pcs or profile_id not in self.profiles:
            raise RemoteError("등록된 PC와 허용 profile이 필요합니다")
        if not re.fullmatch("[0-9a-f]{64}", bundle_id or ""):
            raise RemoteError("묶음 ID가 필요합니다")
        self.executor.validate(self.pcs[pc_id], self.profiles[profile_id])
        package = self.root / "bundles" / bundle_id / "package.zip"
        if not package.is_file():
            raise RemoteError("검증된 코드 묶음이 없습니다")
        job_id = uuid.uuid4().hex
        record = {"id": job_id, "pc_id": pc_id, "profile_id": profile_id, "bundle_id": bundle_id,
                  "restore_after": restore_after, "status": "queued", "created": time.time()}
        with self.mutex, self._connection() as conn:
            try:
                conn.execute("INSERT INTO jobs VALUES(?,?,?,?)", (job_id, pc_id, "queued", json.dumps(record)))
            except sqlite3.IntegrityError as exc:
                raise RemoteError("이 PC는 실행/복구 확인 중입니다") from exc
            directory = self._job_dir(job_id)
            (directory / "results").mkdir(parents=True)
            (directory / "request.json").write_text(json.dumps(record), encoding="utf-8")
            self.events[job_id] = threading.Event()
        threading.Thread(target=self._run, args=(job_id, package), daemon=True).start()
        return record

    def get(self, job_id):
        self._job_dir(job_id)
        with self._connection() as conn:
            row = conn.execute("SELECT record FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise RemoteError("실행 기록이 없습니다")
        return json.loads(row[0])

    def list(self):
        with self._connection() as conn:
            return [json.loads(row[0]) for row in conn.execute("SELECT record FROM jobs ORDER BY rowid DESC LIMIT 100")]

    def _update(self, job_id, **changes):
        with self.mutex, self._connection() as conn:
            record = json.loads(conn.execute("SELECT record FROM jobs WHERE id=?", (job_id,)).fetchone()[0])
            record.update(changes)
            conn.execute("UPDATE jobs SET status=?,record=? WHERE id=?", (record["status"], json.dumps(record), job_id))
        return record

    def _log(self, job_id, message):
        with self.mutex:
            with (self._job_dir(job_id) / "events.log").open("a", encoding="utf-8") as stream:
                stream.write(str(message).replace("\r", " ") + "\n")

    def logs(self, job_id):
        self.get(job_id)
        path = self._job_dir(job_id) / "events.log"
        return path.read_text(encoding="utf-8")[-1024 * 1024:] if path.exists() else ""

    def cancel(self, job_id):
        with self.mutex:
            record = self.get(job_id)
            if record["status"] not in self.ACTIVE:
                return record
            if job_id not in self.events:
                # 재시작 뒤 실제 task 중지를 확인할 수 있는 adapter만 잠금을 풀 수 있다.
                stopped = self.executor.cancel_existing(record, self.pcs[record["pc_id"]])
                return self._update(job_id, status="cancelled" if stopped else "uncertain")
            self.events[job_id].set()
            return self._update(job_id, status="cancelling")

    def _run(self, job_id, package):
        try:
            record = self._update(job_id, status="running")
            package_bytes = package.read_bytes()
            # 저장소 파일이 업로드 뒤 바뀌었어도 고정 manifest 신원으로 재검증한다.
            unpack_bundle(package_bytes, self._job_dir(job_id) / "validated-code", record["bundle_id"])
            outcome = self.executor.execute(record, self.pcs[record["pc_id"]], self.profiles[record["profile_id"]],
                                            package_bytes, self._job_dir(job_id) / "results", self.events[job_id],
                                            lambda line: self._log(job_id, line))
            status = outcome.get("status")
            if status == "cancelled" and not outcome.get("stopped_verified"):
                status = "uncertain"
            if status == "error" and not outcome.get("stopped_verified"):
                status = "uncertain"
            if status not in ("completed", "cancelled", "blocked", "abnormal", "error", "uncertain"):
                status = "uncertain"
            if status in ("completed", "abnormal", "blocked", "cancelled"):
                output = self._job_dir(job_id) / "results"
                files = [p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()]
                if not files and status == "completed":
                    status = "error"
                    outcome = {"reason": "실행 종료 후 결과가 없습니다"}
                elif files:
                    result_package, identity = create_bundle(output, files, code_only=False)
                    (self._job_dir(job_id) / "results.zip").write_bytes(result_package)
                    outcome["result_bundle_id"] = identity
            self._update(job_id, **{**outcome, "status": status, "finished": time.time()})
        except (RemoteBlocked, BundleError) as exc:
            self._log(job_id, "실행 전 차단: " + type(exc).__name__)
            self._update(job_id, status="blocked", error_type=type(exc).__name__)
        except Exception as exc:
            # exception 문자열에는 원격 stderr/자격증명이 있을 수 있다. 종류만 기록한다.
            self._log(job_id, "원격 확인 실패: " + type(exc).__name__)
            self._update(job_id, status="uncertain", error_type=type(exc).__name__)
        finally:
            with self.mutex:
                self.events.pop(job_id, None)

    def results(self, job_id):
        record = self.get(job_id)
        if not record.get("result_bundle_id"):
            raise RemoteError("검증된 수집 결과가 없습니다")
        return (self._job_dir(job_id) / "results.zip").read_bytes(), record["result_bundle_id"]
