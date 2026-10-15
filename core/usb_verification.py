"""Pure USB Import evidence verdict; no UI, filesystem, DB, or time operations.

SRS 02-40-80 requires regenerated Study/Series/Instance UIDs and an Examined
result. The adapter must collect before/after snapshots for ONE synthetic QA
patient, identify an actually observed completion signal, inspect the imported
instance files, then explicitly search Examined again. This module never
infers that an arbitrary screen or button click means completion.

Normalized input contract (the adapter owns actual DB column names):
  before/after: {patient_id, studies: [{key, study_uid}],
    instances: [{key, study_key, series_uid, image_uid, path,
                 exists: bool, readable: bool, size: int,
                 file_identity: {study_uid, series_uid, image_uid},
                 file_identity_error?: str}], examined_count: int}
  completion: {observed: bool, signal: str, error?: str}
  examined: {patient_id, searched: bool, study_uids: [str], count?: int}
  export_inventory: [{path: str, exists: bool, readable: bool, size: int}]
  expected_studies: positive int, normally one selected Export/Import row

Examined study_uids must be correlated to actual displayed study identities by
the collector; a card count alone is insufficient. Count fields are diagnostic
metadata only. Snapshot row sequences may be lists or tuples and are normalized
internally without modifying input data.

An observed flag is a collector assertion, not a trust/security boundary.
Production collectors must only assert it for empirically verified completion
signals. The known action-only signals below are rejected even with that flag.
"""
from __future__ import annotations

import ntpath


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _key(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return str(value)
    if _text(value):
        return value
    return None


def _records(snapshot, field, patient_id):
    rows = snapshot.get(field)
    if not isinstance(rows, (list, tuple)):
        return None
    if any(not isinstance(row, dict) or row.get('patient_id', patient_id) != patient_id
           or _key(row.get('key')) is None for row in rows):
        return None
    if len({_key(row['key']) for row in rows}) != len(rows):
        return None
    return list(rows)


def verify_import_evidence(before, after, completion, examined, *, export_inventory, expected_studies=1):
    """Return {ok, reason, study_keys, image_keys, study_uids, image_uids}.

    This verifies a complete independent evidence bundle. File flags and
    completion observations are supplied by the collector, never fabricated
    here. A file timestamp/content change on existing UID records is inadequate.
    """
    result = {'ok': False, 'reason': '', 'study_keys': [], 'image_keys': [],
              'study_uids': [], 'image_uids': []}

    def rejected(reason):
        return dict(result, reason=reason)

    if type(expected_studies) is not int or expected_studies <= 0:
        return rejected('선택한 Import 기대 검사 건수가 올바르지 않습니다.')
    if not isinstance(export_inventory, (list, tuple)) or not export_inventory:
        return rejected('되읽기 대상 Export IMG 목록이 없습니다.')
    export_paths = set()
    for image in export_inventory:
        if (not isinstance(image, dict) or not _text(image.get('path'))
                or ntpath.splitext(image['path'])[1].casefold() != '.img'
                or image.get('exists') is not True or image.get('readable') is not True
                or type(image.get('size')) is not int or image['size'] <= 0):
            return rejected('Export IMG 파일의 존재·읽기 가능·내용 크기를 확인하지 못했습니다.')
        path = ntpath.normcase(ntpath.normpath(image['path']))
        if path in export_paths:
            return rejected('Export IMG 목록에 동일한 파일 경로가 중복되었습니다.')
        export_paths.add(path)
    if not isinstance(before, dict) or not isinstance(after, dict):
        return rejected('Import 전후 환자 범위 스냅샷이 없습니다.')
    patient_id = before.get('patient_id')
    if not _text(patient_id) or after.get('patient_id') != patient_id:
        return rejected('전후 스냅샷의 대상 환자가 일치하지 않습니다.')
    if (not isinstance(completion, dict) or completion.get('observed') is not True
            or not _text(completion.get('signal')) or completion.get('error')):
        return rejected('실제로 관찰한 Import 완료 신호가 없거나 오류가 있습니다.')
    signal = completion['signal'].casefold()
    if any(action in signal for action in ('click', 'manually-closed', 'duplicate-popup-dismissed')):
        return rejected('클릭·수동 닫기·중복 팝업 처리는 완료 신호가 아닙니다.')
    studies_before = _records(before, 'studies', patient_id)
    studies_after = _records(after, 'studies', patient_id)
    instances_before = _records(before, 'instances', patient_id)
    instances_after = _records(after, 'instances', patient_id)
    if any(rows is None for rows in (studies_before, studies_after, instances_before, instances_after)):
        return rejected('환자 범위 DB 식별자 기록이 누락되었거나 잘못되었습니다.')
    if any(not _text(row.get('study_uid')) for row in studies_before + studies_after):
        return rejected('Study UID가 누락되었습니다.')
    if any(not _text(row.get('image_uid')) or not _text(row.get('series_uid'))
           for row in instances_before + instances_after):
        return rejected('Series/Instance UID가 누락되었습니다.')
    if len({row['study_uid'] for row in studies_after}) != len(studies_after):
        return rejected('서로 다른 검사 키에 동일한 Study UID가 연결되어 있습니다.')
    if len({row['image_uid'] for row in instances_after}) != len(instances_after):
        return rejected('서로 다른 영상 키에 동일한 Instance UID가 연결되어 있습니다.')
    all_study_keys = {_key(row['key']) for row in studies_after}
    series_studies = {}
    for row in instances_after:
        study_key = _key(row.get('study_key'))
        if study_key not in all_study_keys:
            return rejected('영상의 검사 키가 스냅샷 검사와 연결되지 않습니다.')
        previous_study = series_studies.setdefault(row['series_uid'], study_key)
        if previous_study != study_key:
            return rejected('동일한 Series UID가 서로 다른 검사에 연결되어 있습니다.')
    old_study_uids = {row['study_uid'] for row in studies_before}
    old_series_uids = {row['series_uid'] for row in instances_before}
    old_image_uids = {row['image_uid'] for row in instances_before}
    new_studies = [row for row in studies_after if row['study_uid'] not in old_study_uids]
    if not new_studies:
        return rejected('Import 이후 새로 생성된 Study UID가 없습니다.')
    if len(new_studies) != expected_studies:
        return rejected(f'신규 Import 검사 건수가 선택한 기대 건수와 다릅니다(기대 {expected_studies}, 실제 {len(new_studies)}).')
    study_keys = {_key(row['key']) for row in new_studies}
    images = [row for row in instances_after if _key(row.get('study_key')) in study_keys]
    if not images or {_key(row.get('study_key')) for row in images} != study_keys:
        return rejected('새 검사에 연결된 영상이 없습니다.')
    if len(images) != len(export_paths):
        return rejected(f'신규 Import 영상 건수가 Export IMG 건수와 다릅니다(Export {len(export_paths)}, Import {len(images)}).')
    if any(row['image_uid'] in old_image_uids or row['series_uid'] in old_series_uids for row in images):
        return rejected('Import 영상의 Series/Instance UID 재생성이 확인되지 않았습니다.')
    if any(not _text(row.get('path')) or row.get('exists') is not True
           or row.get('readable') is not True or type(row.get('size')) is not int
           or row['size'] <= 0 for row in images):
        return rejected('Import 영상 파일의 존재·읽기 가능·내용 크기를 확인하지 못했습니다.')
    linked_study_uids = {_key(row['key']): row['study_uid'] for row in new_studies}
    for image in images:
        identity = image.get('file_identity')
        if (not isinstance(identity, dict) or image.get('file_identity_error')
                or any(not _text(identity.get(field)) for field in ('study_uid', 'series_uid', 'image_uid'))):
            return rejected('Import IMG XML에서 독립적인 Study/Series/Instance UID를 읽지 못했습니다.')
        if (identity['study_uid'] != linked_study_uids[_key(image['study_key'])]
                or identity['series_uid'] != image['series_uid']
                or identity['image_uid'] != image['image_uid']):
            return rejected('Import IMG XML의 Study/Series/Instance UID가 연결된 DB 기록과 일치하지 않습니다.')
    if (not isinstance(examined, dict) or examined.get('patient_id') != patient_id
            or examined.get('searched') is not True):
        return rejected('대상 환자의 Examined 재검색 근거가 없습니다.')
    new_study_uids = {row['study_uid'] for row in new_studies}
    found_uids = examined.get('study_uids')
    uid_match = (isinstance(found_uids, (list, tuple, set))
                 and all(isinstance(uid, str) for uid in found_uids)
                 and new_study_uids.issubset(set(found_uids)))
    if not uid_match:
        return rejected('Examined에서 신규 검사 UID와 연결되는 표시 결과를 확인하지 못했습니다.')
    return dict(result, ok=True, reason='완료 신호·신규 UID·IMG XML 식별자·Examined 재검색이 일치합니다.',
                study_keys=sorted((row['key'] for row in new_studies), key=str),
                image_keys=sorted((row['key'] for row in images), key=str),
                study_uids=sorted(new_study_uids), image_uids=sorted({row['image_uid'] for row in images}))
