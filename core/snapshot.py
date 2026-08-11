# -*- coding: utf-8 -*-
"""DB 상태 스냅샷과 델타 비교.

상태 코드(StudyStatus, StatusRejected, DICOM_STORAGE_QUEUE.State 등)의 절대 의미가
제품 문서에서 확정되지 않았으므로, 이 프레임워크는 코드값을 단정하지 않는다.
대신 조작 전(pre)/후(post) 스냅샷을 떠서 '무엇이 어떻게 바뀌었는가'로 판정한다.
이 방식은 코드 의미가 바뀌어도 깨지지 않고, 오판정 위험이 낮다.
"""

import json
import os
from datetime import datetime

# 스냅샷 대상 쿼리. key는 스냅샷 섹션 이름.
SNAPSHOT_QUERIES = {
    # --- 데이터 ---
    "patient": ("DATA",
                "SELECT [Key],PatientID,PatientName,PatientBirthDate,PatientSex "
                "FROM PATIENT ORDER BY [Key]"),
    "study": ("DATA",
              "SELECT [Key],PatientKey,StudyType,StudyStatus,StudyDate,StudyTime,"
              "StudyInstanceUID,StudyID,AccessionNumber,HospitalCode,ProcedureKey,"
              "RejectType,RejectReason,RejectUserID,[Lock] FROM STUDY ORDER BY [Key]"),
    "series": ("DATA", "SELECT [Key],StudyKey,SeriesNumber,SeriesInstanceUID "
                       "FROM SERIES ORDER BY [Key]"),
    "instance": ("DATA",
                 "SELECT [Key],StudyKey,SeriesKey,GroupKey,InstanceType,InstanceNumber,"
                 "ImageInstanceUID FROM INSTANCE ORDER BY [Key]"),
    "instance_group": ("DATA",
                       "SELECT [Key],StudyKey,SeriesKey,Type,ExposureMode,StatusSent,"
                       "StatusCommitment,StatusPrint,StatusExported,StatusRejected,"
                       "RejectType,RejectReason,RejectUserID,RejectDate,RejectTime "
                       "FROM INSTANCE_GROUP ORDER BY [Key]"),
    "storage_queue": ("DATA",
                      "SELECT [Key],StorageKey,State,CommitmentState,PatientID,"
                      "TransactionUID,ClassUID,InstanceUID,DataType,InstanceKey,"
                      "InstanceGroupKey FROM DICOM_STORAGE_QUEUE ORDER BY [Key]"),
    "print_queue": ("DATA", "SELECT * FROM DICOM_PRINT_QUEUE"),
    "export_queue": ("DATA",
                     "SELECT [Key],State,PatientID,InstanceKey,StudyKey,DataType "
                     "FROM EXPORT_QUEUE ORDER BY [Key]"),
    "dose_info": ("DATA",
                  "SELECT GroupKey,FrameIndex,DoseKVP,DoseMA,DoseMS,DoseMAS,"
                  "EntranceDose,AGDACR,AGDEUREF FROM DOSE_INFO ORDER BY GroupKey,FrameIndex"),
    "qc_study": ("DATA", "SELECT [Key],Type,Status,StudyDate,Result,ImageCount,Deleted "
                         "FROM QC_STUDY ORDER BY [Key]"),

    # --- 설정 ---
    "system_common": ("CONFIGURATION", "SELECT * FROM SYSTEM_COMMON"),
    "display_common": ("CONFIGURATION", "SELECT * FROM DISPLAY_COMMON"),
    "study_common": ("CONFIGURATION", "SELECT * FROM STUDY_COMMON"),
    "tool_common": ("CONFIGURATION", "SELECT * FROM TOOL_COMMON"),
    "device_common": ("CONFIGURATION", "SELECT * FROM DEVICE_COMMON"),
    "qc_common": ("CONFIGURATION", "SELECT * FROM QC_COMMON"),
    "registration_common": ("CONFIGURATION", "SELECT * FROM REGISTRATION_COMMON"),
    "overlay": ("CONFIGURATION", "SELECT * FROM OVERLAY"),
    "overlay_item": ("CONFIGURATION",
                     "SELECT FieldID,Position,[Order] FROM OVERLAY_ITEM "
                     "ORDER BY Position,[Order]"),
    "print_overlay": ("CONFIGURATION", "SELECT * FROM PRINT_OVERLAY"),
    "print_overlay_item": ("CONFIGURATION",
                           "SELECT PrintOverlayKey,Position,FieldID,[Order] "
                           "FROM PRINT_OVERLAY_ITEM ORDER BY PrintOverlayKey,Position,[Order]"),
    "dicom_common": ("CONFIGURATION", "SELECT * FROM DICOM_COMMON"),
    "dicom_storage": ("CONFIGURATION", "SELECT * FROM DICOM_STORAGE ORDER BY [Key]"),
    "dicom_mwl": ("CONFIGURATION", "SELECT * FROM DICOM_MWL ORDER BY [Key]"),
    "dicom_mpps": ("CONFIGURATION", "SELECT * FROM DICOM_MPPS"),
    "dicom_print": ("CONFIGURATION", "SELECT * FROM DICOM_PRINT"),
    "dicom_print_dicom": ("CONFIGURATION", "SELECT * FROM DICOM_PRINT_DICOM"),
    "dicom_mapping": ("CONFIGURATION", "SELECT * FROM DICOM_MAPPING"),
    "dicom_qr": ("CONFIGURATION", "SELECT * FROM DICOM_QR"),
    "export_cfg": ("CONFIGURATION", "SELECT * FROM EXPORT"),
    "layout": ("CONFIGURATION", "SELECT * FROM LAYOUT ORDER BY [Key]"),
    "layout_info": ("CONFIGURATION", "SELECT * FROM LAYOUT_INFO"),
    "lut": ("CONFIGURATION", "SELECT * FROM LUT ORDER BY [Key]"),
    "lut_item": ("CONFIGURATION", "SELECT * FROM LUT_ITEM"),
    "reject_reason": ("CONFIGURATION", "SELECT * FROM REJECT_REASON ORDER BY [Key]"),
    "predefined_text_item": ("CONFIGURATION", "SELECT * FROM PREDEFINED_TEXT_ITEM"),
    "new_patient_input_field": ("CONFIGURATION", "SELECT * FROM NEW_PATIENT_INPUT_FIELD"),
    "status_bar_item": ("CONFIGURATION", "SELECT * FROM STATUS_BAR_ITEM"),
    "qc_schedule": ("CONFIGURATION", "SELECT * FROM QC_SCHEDULE ORDER BY [Key]"),

    # --- 계정 / 프로시저 ---
    "account": ("ACCOUNT", "SELECT [Key],System,[Group],ID,Name FROM ACCOUNT ORDER BY [Key]"),
    "patient_list_column": ("ACCOUNT", "SELECT * FROM PATIENT_LIST_COLUMN"),
    "examined_list_column": ("ACCOUNT", "SELECT * FROM EXAMINED_LIST_COLUMN"),
    "tool_button": ("ACCOUNT", "SELECT * FROM TOOL_BUTTON"),
    "hospital_code": ("PROCEDURE",
                      "SELECT [Key],Code,Description,MappingKey,MappingType "
                      "FROM HOSPITAL_CODE ORDER BY [Key]"),
    "procedure_common": ("PROCEDURE", "SELECT * FROM PROCEDURE_COMMON"),
    "procedure_info": ("PROCEDURE", "SELECT [Key],Name,[Default],Code,Description "
                                    "FROM PROCEDURE_INFO ORDER BY [Key]"),
    "procedure_items": ("PROCEDURE", "SELECT * FROM PROCEDURE_ITEMS"),
    "view_position_preset": ("PROCEDURE", "SELECT * FROM VIEW_POSITION_PRESET ORDER BY [Key]"),
}

# 설정 비교(TC_Basic_WorkFlow_15, Install_07)에서 제외할 항목.
# 세션마다 자연히 바뀌는 값이라 설정 유지 판정에 쓰면 오판정이 난다.
VOLATILE_FIELDS = {
    ("system_common", "LastLoginID"),
}

CONFIG_SECTIONS = [k for k, (db, _) in SNAPSHOT_QUERIES.items()
                   if db in ("CONFIGURATION", "PROCEDURE")] + [
    "account", "patient_list_column", "examined_list_column", "tool_button"]


def take(db, sections=None):
    """스냅샷을 뜬다. sections=None이면 전체."""
    names = sections or list(SNAPSHOT_QUERIES.keys())
    specs = [{"name": n, "db": SNAPSHOT_QUERIES[n][0], "sql": SNAPSHOT_QUERIES[n][1]}
             for n in names]
    result = db.query_many(specs)
    return {"_taken": datetime.now().isoformat(timespec="seconds"),
            "_sections": {n: result.get(n, {"_error": "조회 결과 없음"}) for n in names}}


def save(snap, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1, default=str)
    return path


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _key_of(section, row):
    for k in ("Key", "FieldID", "GroupKey"):
        if k in row:
            return f"{k}={row[k]}"
    return json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)


def diff_section(pre, post, section, ignore=()):
    """한 섹션의 행 단위 델타를 반환한다."""
    a = pre.get("_sections", {}).get(section) or []
    b = post.get("_sections", {}).get(section) or []
    if isinstance(a, dict) or isinstance(b, dict):
        return {"added": [], "removed": [], "changed": [], "_error": True}

    ai = {_key_of(section, r): r for r in a}
    bi = {_key_of(section, r): r for r in b}
    added = [bi[k] for k in bi if k not in ai]
    removed = [ai[k] for k in ai if k not in bi]
    changed = []
    for k in ai:
        if k not in bi:
            continue
        fields = {}
        for col in ai[k]:
            if col in ignore or (section, col) in VOLATILE_FIELDS:
                continue
            if str(ai[k].get(col)) != str(bi[k].get(col)):
                fields[col] = {"pre": ai[k].get(col), "post": bi[k].get(col)}
        if fields:
            changed.append({"row": k, "fields": fields})
    return {"added": added, "removed": removed, "changed": changed}


def diff(pre, post, sections=None):
    names = sections or sorted(set(pre.get("_sections", {})) | set(post.get("_sections", {})))
    out = {}
    for name in names:
        d = diff_section(pre, post, name)
        if d.get("added") or d.get("removed") or d.get("changed"):
            out[name] = d
    return out


def config_identical(pre, post):
    """설정 섹션이 완전히 동일한지와 차이 내역을 반환한다."""
    d = diff(pre, post, CONFIG_SECTIONS)
    return (not d), d
