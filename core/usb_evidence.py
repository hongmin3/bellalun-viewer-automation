"""USB 되읽기 전후 DB와 실제 Examined 카드의 독립 관찰 수집.

Import 완료 신호나 PASS를 추측하지 않는다. observe_examined만 UI 입력을 하며,
호출자는 다른 제품 실행이 없는 독점 실행 구간에서 명시적으로 호출해야 한다.
이 모듈을 import하거나 나머지 함수를 호출하는 것만으로 UI를 조작하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET

from core import imginfo


class ObservationError(RuntimeError):
    """독립 관찰을 확보하지 못해 식별자를 단정할 수 없음."""


@dataclass(frozen=True)
class LogCursor:
    path: Path
    offset: int
    identity: tuple[int, int]
    anchor_offset: int
    anchor: bytes
    captured_at: datetime


def _identity(stat) -> tuple[int, int]:
    return stat.st_dev, stat.st_ino


def log_cursor(data_dir, *, now=None) -> LogCursor:
    """카드 클릭 직전 오늘 Viewer UTF-16LE 로그의 정확한 바이트 경계 저장.

    파일 부재·미완성 줄은 과거 로그로 대체하지 않고 수집 실패로 처리한다.
    마지막 바이트 anchor와 파일 identity로 교체/잘림/덮어쓰기를 감지한다.
    """
    captured = now if now is not None else datetime.now()
    captured = captured.replace(microsecond=(captured.microsecond // 1000) * 1000)
    path = Path(data_dir) / "Log" / "Viewer" / captured.strftime("%Y_%m_%d.log")
    try:
        with path.open("rb") as stream:
            stat = os.fstat(stream.fileno())
            offset = stat.st_size
            stream.seek(max(0, offset - 128))
            anchor = stream.read(offset - max(0, offset - 128))
    except OSError as error:
        raise ObservationError("Viewer 로그 시작 위치를 읽지 못했습니다.") from error
    if offset % 2 or (offset > 2 and not anchor.endswith(b"\n\x00")):
        raise ObservationError("Viewer 로그의 마지막 줄 기록이 끝나지 않았습니다.")
    return LogCursor(path, offset, _identity(stat), max(0, offset - 128), anchor, captured)


_CLICK = re.compile(
    r"^\[(?P<timestamp>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]"
    r"\s+\[User Action\]\s+\[UI\]\s+"
    r"\[Study list item Click\. \(Study Key: (?P<key>[1-9]\d*)\)\]"
    r"\s+\[CFrameExamined::OnNotify\]\s*$"
)


def _fresh_lines(cursor: LogCursor, max_bytes: int) -> list[str]:
    try:
        with cursor.path.open("rb") as stream:
            stat = os.fstat(stream.fileno())
            if _identity(stat) != cursor.identity or stat.st_size < cursor.offset:
                raise ObservationError("Viewer 로그가 교체되거나 잘렸습니다. 선택 관찰을 다시 시작하세요.")
            stream.seek(cursor.anchor_offset)
            if stream.read(len(cursor.anchor)) != cursor.anchor:
                raise ObservationError("Viewer 로그의 시작 위치 이전 내용이 바뀌었습니다.")
            stream.seek(cursor.offset)
            tail = stream.read(max_bytes + 1)
            if len(tail) > max_bytes:
                raise ObservationError("선택 관찰 로그가 읽기 한도를 넘었습니다.")
            if _identity(cursor.path.stat()) != cursor.identity:
                raise ObservationError("선택 관찰 도중 Viewer 로그가 교체되었습니다.")
    except OSError as error:
        raise ObservationError("선택 관찰 로그를 읽지 못했습니다.") from error
    try:
        # A writer may be in the middle of a UTF-16 code unit or line; poll it.
        text = tail[:len(tail) - len(tail) % 2].decode("utf-16le")
    except UnicodeError as error:
        raise ObservationError("Viewer 선택 로그의 UTF-16LE 형식을 확인하지 못했습니다.") from error
    return [line.rstrip("\r\n") for line in text.splitlines(keepends=True) if line.endswith("\n")]


def selected_study_key(cursor: LogCursor, *, timeout=3.0, poll=0.1, max_bytes=65536) -> int:
    """새 정확한 클릭 이벤트 한 건의 Study Key만 반환한다.

    이전 바이트·이전 시각·다른 로그 source·중복/여러 클릭은 근거가 될 수 없다.
    같은 Key가 두 번 기록되어도 어느 클릭인지 불명확하므로 거부한다.
    """
    deadline = time.monotonic() + max(0, timeout)
    while True:
        clicks = []
        for line in _fresh_lines(cursor, max_bytes):
            match = _CLICK.fullmatch(line)
            if not match:
                continue
            timestamp = datetime.strptime(match["timestamp"], "%Y/%m/%d %H:%M:%S.%f")
            if timestamp >= cursor.captured_at:
                clicks.append(int(match["key"]))
        if len(clicks) > 1:
            raise ObservationError("새 카드 클릭 로그가 여러 건이라 선택한 검사를 특정할 수 없습니다.")
        if clicks:
            return clicks[0]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ObservationError("카드 선택 이후의 새 Study Key 로그를 확인하지 못했습니다.")
        time.sleep(min(max(0.01, poll), remaining))


_STUDIES_SQL = (
    "SELECT s.[Key] AS [key],s.StudyInstanceUID AS study_uid,p.PatientID AS patient_id "
    "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
    "WHERE p.PatientID=@pid ORDER BY s.[Key]"
)
_INSTANCES_SQL = (
    "SELECT i.[Key] AS [key],i.StudyKey AS study_key,"
    "se.SeriesInstanceUID AS series_uid,i.ImageInstanceUID AS image_uid,"
    "s.StudyInstanceUID AS study_uid,p.PatientID AS patient_id "
    "FROM INSTANCE i JOIN STUDY s ON s.[Key]=i.StudyKey "
    "JOIN PATIENT p ON p.[Key]=s.PatientKey "
    "LEFT JOIN SERIES se ON se.[Key]=i.SeriesKey AND se.StudyKey=s.[Key] "
    "WHERE p.PatientID=@pid ORDER BY i.[Key]"
)
_SELECTED_SQL = (
    "SELECT s.[Key] AS [key],s.StudyInstanceUID AS study_uid,p.PatientID AS patient_id "
    "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
    "WHERE s.[Key]=@key AND p.PatientID=@pid"
)


def patient_snapshot(db, data_dir, patient_id: str) -> dict:
    """실제 환자 범위 Study/Series/Instance UID와 파일 열기 결과를 수집한다.

    SELECT만 사용한다. 실제 파일을 찾고 1 byte를 읽어 비어있지 않음을 확인하고,
    IMG 꼬리 XML의 Study/Series/Instance.InstanceUID를 DB와 독립적으로 읽는다.
    DB 자체의 UID/파일이 누락되면 값을 만들어 채우지 않고 그대로 남긴다.
    """
    if not isinstance(patient_id, str) or not patient_id.strip():
        raise ObservationError("스냅샷의 시험 Patient ID가 필요합니다.")
    params = {"pid": patient_id}
    studies = [dict(row) for row in db.query("DATA", _STUDIES_SQL, params)]
    instances = [dict(row) for row in db.query("DATA", _INSTANCES_SQL, params)]
    if any(row.get("patient_id") != patient_id for row in studies + instances):
        raise ObservationError("DB 스냅샷에 다른 환자 기록이 섞여 있습니다.")
    for instance in instances:
        try:
            path = imginfo.instance_image_path(data_dir, int(instance["study_key"]), int(instance["key"]))
        except (TypeError, ValueError, KeyError) as error:
            raise ObservationError("DB 영상 키를 실제 파일과 연결하지 못했습니다.") from error
        instance.update(path=str(path) if path else "", exists=False, readable=False, size=0,
                        file_identity={}, file_identity_error="IMG 파일을 찾지 못했습니다.")
        if not path:
            continue
        try:
            stat = Path(path).stat()
            instance["exists"] = Path(path).is_file()
            instance["size"] = stat.st_size
            with Path(path).open("rb") as stream:
                instance["readable"] = bool(stream.read(1)) and stat.st_size > 0
            instance["file_identity_error"] = "IMG 파일이 비어 있거나 읽을 수 없습니다."
            if instance["readable"]:
                metadata = imginfo.sections(path)
                identity = {field: metadata.get(section, {}).get("InstanceUID")
                            for field, section in (("study_uid", "study"), ("series_uid", "series"),
                                                   ("image_uid", "instance"))}
                instance["file_identity"] = identity
                instance["file_identity_error"] = (None if all(isinstance(uid, str) and uid.strip()
                                                               for uid in identity.values())
                                                    else "IMG XML의 Study/Series/Instance UID가 누락되었습니다.")
        except (OSError, imginfo.ImgInfoError, ET.ParseError, TypeError, ValueError) as error:
            # File flags are actual observations; the verifier rejects them.
            instance["file_identity_error"] = type(error).__name__ + ": " + str(error)
    return {"patient_id": patient_id, "studies": studies, "instances": instances}


def observe_examined(ui, db, data_dir, patient_id: str) -> dict:
    """Examined를 재검색하고 각 실제 카드의 새 클릭 Key로 DB UID를 조회한다.

    이 함수는 UI 입력을 한다. 기존 실행이 끝난 뒤 독점 실행에서만 호출한다.
    기대 UID나 DB 정렬 순서를 입력받지 않으며 카드 수는 진단 정보로만 쓴다.
    View로 열지 않고 Examined의 검색과 선택 동작만 수행한다.
    """
    from core.flows import examined_search
    if not isinstance(patient_id, str) or not patient_id.strip():
        raise ObservationError("Examined 재검색의 시험 Patient ID가 필요합니다.")
    cards = examined_search(ui, patient_id)
    observations = []
    seen = set()
    for index, card in enumerate(cards):
        cursor = log_cursor(data_dir)
        ui.click(card, settle=0.2)
        key = selected_study_key(cursor)
        row = db.one("DATA", _SELECTED_SQL, {"key": key, "pid": patient_id})
        if (not row or row.get("patient_id") != patient_id or row.get("key") != key
                or not isinstance(row.get("study_uid"), str) or not row["study_uid"].strip()):
            raise ObservationError("실제 클릭한 카드의 Study Key를 대상 환자의 DB UID와 연결하지 못했습니다.")
        if key in seen:
            raise ObservationError("서로 다른 카드에서 동일 Study Key가 관찰되어 식별할 수 없습니다.")
        seen.add(key)
        observations.append({"card_index": index, "card_rect": list(card.rect),
                             "study_key": key, "study_uid": row["study_uid"],
                             "log_path": str(cursor.path), "log_offset": cursor.offset,
                             "source": "CFrameExamined::OnNotify: Study list item Click"})
    return {"patient_id": patient_id, "searched": True,
            "study_uids": [item["study_uid"] for item in observations],
            "count": len(cards), "observations": observations}
