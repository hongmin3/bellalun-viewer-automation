"""마무리된 실행의 보존본을 최근 N회만 남기고 정리한다(REQ-FOLLOWUP-004).

실행이 끝날 때 호출한다. 마무리된 실행(journal state가 completed/verified이고 마무리·정리 대기가 없는 것)만
세고, 가장 최근 `keep`개를 남긴다. 더 오래된 실행은 다음을 지운다.

- 작업 폴더 `preservation/<실행>` (사전 사본·시험 후 보관본·journal)
- 그 실행이 보존 범위 폴더 옆에 만든 격리 사본 `.<이름>.bellalun-<실행>-<번호|quarantine|stage>`
- 공용 저장소 모드면 `<저장소>/<실행>` 공용 사본

마무리되지 않은 실행은 세지도 지우지도 않는다. 실행 폴더는 먼저 `preservation` 밖의
`.preservation-pruning/`으로 옮긴 뒤 지운다. 지우다 멈춰도 `preservation`에 반쯤 남은 폴더가
다음 실행 시작을 막지 않고, 남은 것은 다음 정리 때 이어서 지운다.
"""
import json
import os
import re
import shutil
import stat
from pathlib import Path

from core.run_preservation import PreservationError, RunPreservation, _check_path

DEFAULT_KEEP_RUNS = 3
PRUNING_DIR = ".preservation-pruning"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")


def keep_runs_from_options(options):
    """설정 `preservation.keep_runs`. 없으면 3, 0이면 정리하지 않는다. 잘못된 값은 기본값."""
    value = (options or {}).get("keep_runs", DEFAULT_KEEP_RUNS)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return DEFAULT_KEEP_RUNS
    return value


def _read_journal(directory):
    try:
        return json.loads(_check_path(directory / "journal.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, PreservationError):
        return None


def _finished(directory, journal):
    """다음 실행을 막지 않는 마무리된 실행인가(RunPreservation.pending과 같은 기준)."""
    if journal is None or journal.get("run_id") != directory.name:
        return False
    if _check_path(directory / "image-cleanup-pending.json").exists():
        return False
    return (journal.get("state") in RunPreservation.TERMINAL
            and not journal.get("execution_finalization_pending"))


def _holding_dirs(journal, run_id):
    """journal의 보존 범위 폴더 옆에 이 실행이 남긴 격리 사본 폴더."""
    found = []
    for root in (journal.get("roots") or {}).values():
        try:
            root = Path(root)
            parent = _check_path(root.parent)
        except (OSError, ValueError, TypeError, PreservationError):
            continue
        pattern = re.compile(r"\." + re.escape(root.name) + r"\.bellalun-" + re.escape(run_id)
                             + r"-(\d+|quarantine|stage)(\.bellalun-copying)?$")
        try:
            entries = list(parent.iterdir())
        except OSError:
            continue
        for entry in entries:
            if pattern.fullmatch(entry.name):
                found.append(entry)
    return found


def _shared_copy(journal, run_id):
    storage = journal.get("storage") or {}
    if storage.get("mode") != "shared_delta" or not storage.get("path"):
        return None
    store = Path(storage["path"])
    copy = store / run_id
    # 저장소 표시 파일이 있는 저장소 안의 그 실행 폴더만 지운다
    if not (store / ".bellalun-preservation-store.json").exists():
        return None
    return copy


def _remove(path):
    """링크를 따라가지 않고 지운다. 반환: 지우지 못했으면 오류 종류, 지웠으면 None."""
    def _writable(function, target, _info):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    try:
        path = _check_path(path)
        if not os.path.lexists(path):
            return None
        if path.is_symlink() or (path.is_file()):
            path.unlink()
        else:
            shutil.rmtree(path, onerror=_writable)
        return None if not os.path.lexists(path) else "still_exists"
    except (OSError, ValueError, PreservationError) as error:
        return type(error).__name__


def _size(path):
    total = 0
    for current, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                pass
    return total


def _purge(staged, journal, run_id):
    """옮겨 둔 실행 폴더와 그 실행의 격리·공용 사본을 지운다. 반환: (지운 바이트, 실패 목록)."""
    removed, failed = 0, []
    targets = _holding_dirs(journal, run_id) if journal else []
    shared = _shared_copy(journal, run_id) if journal else None
    if shared is not None:
        targets.append(shared)
    targets.append(staged)  # journal이 든 폴더는 마지막에 지운다(실패하면 다음에 다시 찾을 수 있게)
    for target in targets:
        size = _size(target) if os.path.isdir(target) else 0
        error = _remove(target)
        if error:
            failed.append({"run_id": run_id, "role": "run" if target == staged else "copy", "error": error})
        else:
            removed += size
    return removed, failed


def prune_old_runs(workspace, keep=DEFAULT_KEEP_RUNS, current_run_id=None):
    """마무리된 실행 중 최근 keep개만 남긴다. 시험 판정에 영향을 주지 않도록 예외를 던지지 않는다."""
    summary = {"status": "skipped", "keep": keep, "kept": [], "removed": [], "failed": [], "bytes_removed": 0}
    if not keep:
        summary["reason"] = "disabled_by_config"
        return summary
    try:
        workspace = Path(workspace)
        parent = _check_path(workspace / "preservation")
        staging = _check_path(workspace / PRUNING_DIR)
        # 지난번에 지우다 남은 것부터 마저 지운다
        if staging.exists():
            for leftover in sorted(staging.iterdir()):
                journal = _read_journal(leftover)
                removed, failed = _purge(leftover, journal, leftover.name)
                summary["bytes_removed"] += removed
                summary["failed"] += failed
                if not failed:
                    summary["removed"].append(leftover.name)
        if not parent.exists():
            summary["status"] = "completed"
            return summary
        finished = []
        for directory in parent.iterdir():
            if not directory.is_dir() or not _RUN_ID.fullmatch(directory.name):
                continue
            journal = _read_journal(directory)
            if _finished(directory, journal):
                finished.append((directory, journal))
        # 실행 번호는 `날짜-시각-…`이라 이름순이 시간순이다. 이번 실행은 항상 남긴다.
        finished.sort(key=lambda item: item[0].name, reverse=True)
        kept = [d.name for d, _ in finished[:keep]]
        if current_run_id and current_run_id not in kept and any(d.name == current_run_id for d, _ in finished):
            kept = [current_run_id] + kept[:keep - 1]
        summary["kept"] = kept
        for directory, journal in finished:
            if directory.name in kept:
                continue
            staging.mkdir(exist_ok=True)
            staged = _check_path(staging / directory.name)
            if staged.exists():
                summary["failed"].append({"run_id": directory.name, "role": "run", "error": "staging_exists"})
                continue
            try:
                os.replace(directory, staged)  # 같은 볼륨 안의 이름 바꾸기
            except OSError as error:
                summary["failed"].append({"run_id": directory.name, "role": "run", "error": type(error).__name__})
                continue
            removed, failed = _purge(staged, journal, directory.name)
            summary["bytes_removed"] += removed
            summary["failed"] += failed
            if not failed:
                summary["removed"].append(directory.name)
        if staging.exists() and not any(staging.iterdir()):
            staging.rmdir()
        summary["status"] = "partial" if summary["failed"] else "completed"
    except (OSError, ValueError, PreservationError) as error:
        summary.update(status="error", error_type=type(error).__name__)
    return summary
