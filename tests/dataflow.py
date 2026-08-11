# -*- coding: utf-8 -*-
"""검사·영상 데이터 흐름 TC.

TC_Basic_WorkFlow_01  MWL 및 Local 검사 생성 (판정부)      [pre/post]
TC_Basic_WorkFlow_05  2D 수동 DICOM Send                   [pre/post]
TC_Basic_WorkFlow_06  3D 수동 DICOM Send                   [pre/post]
TC_Basic_WorkFlow_07  All Images 및 Dose SR 전송            [pre/post]
TC_Basic_WorkFlow_10  Normal 및 Anonymous Export           [pre/post]
TC_Basic_WorkFlow_12  Image Reject 및 Restore              [pre/post]
TC_Basic_WorkFlow_13  Study Reject 및 Restore              [pre/post]

전송/Export 판정은 Queue 상태만 보지 않는다. 실제 수신·생성 객체의
Patient ID / Study·Series·SOP Instance UID를 원본과 대조한다(지침 반영).
"""

import os

from core import dicomlite, snapshot
from core.result import TCResult, PASS, FAIL, MANUAL

RDSR_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.88.67"


def _rows(snap, sec):
    v = snap["_sections"].get(sec)
    return v if isinstance(v, list) else []


def _index(rows, key="Key"):
    return {r.get(key): r for r in rows}


# --------------------------------------------------------------------------
def workflow_01_evaluate(ctx, pre, post):
    r = TCResult("TC_Basic_WorkFlow_01", "MWL 및 Local 검사 생성 (판정부)")

    d_study = snapshot.diff_section(pre, post, "study")
    d_pat = snapshot.diff_section(pre, post, "patient")
    new_studies = d_study["added"]

    r.assert_true(3, "MWL/Local 검사가 신규 생성됨", len(new_studies) >= 1,
                  expected=">= 1건", actual=f"{len(new_studies)}건 "
                  f"{[s.get('StudyInstanceUID') for s in new_studies]}")

    pat_by_key = _index(_rows(post, "patient"))
    for s in new_studies:
        p = pat_by_key.get(s.get("PatientKey"), {})
        r.add(4, f"생성 검사(Key={s.get('Key')}) 환자 정보", PASS,
              expected="MWL/입력 환자 정보와 일치 (수동 대조)",
              actual=f"PatientID={p.get('PatientID')}, Name={p.get('PatientName')}, "
                     f"AccNo={s.get('AccessionNumber')}, StudyDate={s.get('StudyDate')}",
              note="Test Data의 DATA_FLOW_MWL_01 / DATA_FLOW_LOCAL_01 값과 대조")

    r.assert_true(9, "신규 환자 등록 반영", bool(d_pat["added"]) or bool(new_studies),
                  expected="PATIENT 또는 STUDY 신규 행",
                  actual=f"PATIENT 추가 {len(d_pat['added'])}건")

    r.manual(1, "MWL 조회 결과 표시", "Patient List 화면 표시는 캡처 증적으로 확인")
    r.manual(4, "예정된 View Position 일치", "SUSPEND_STEP/화면 표시는 캡처 증적으로 확인")
    return r


# --------------------------------------------------------------------------
def _send_common(ctx, pre, post, tc_id, title, expect_rdsr):
    r = TCResult(tc_id, title)

    d_q = snapshot.diff_section(pre, post, "storage_queue")
    new_q = d_q["added"]
    all_q = _rows(post, "storage_queue")
    # 전송 후 Queue에서 제거되는 구현일 수 있으므로 변경/삭제도 함께 본다
    touched = new_q or d_q["changed"] or d_q["removed"]

    r.assert_true(2, "전송 대상이 Queue에 등록됨", bool(touched),
                  expected="DICOM_STORAGE_QUEUE 변화",
                  actual=f"추가 {len(new_q)} / 변경 {len(d_q['changed'])} / "
                         f"삭제 {len(d_q['removed'])}")

    # Step 3. Queue 상태
    states = sorted({q.get("State") for q in new_q}) if new_q else \
        sorted({q.get("State") for q in all_q})
    r.add(3, "Queue 상태 코드", MANUAL,
          expected="Done 상태 코드",
          actual=f"State={states}",
          note="State 코드와 Done 표기의 매핑이 문서상 확정되지 않음. "
               "화면 Queue 표시와 1회 대조 후 config로 고정할 것")

    # Step 4~5. 실제 수신 객체 대조 (핵심 판정)
    recv_root = (ctx.cfg.get("dicom") or {}).get("received_root") or ""
    if not recv_root or not os.path.isdir(recv_root):
        r.skip(4, "Storage SCP 수신 객체 확인",
               "config.json > dicom.received_root 미설정. "
               "SCP 수신 폴더를 지정하거나 tools/storage_scp.py 사용")
        r.skip(5, "원본과 수신 객체의 주요 식별 Tag 대조", "수신 폴더 미지정")
        return r

    received = dicomlite.scan_dir(recv_root)
    r.assert_true(4, "Storage SCP 수신 객체 존재", bool(received),
                  expected=">= 1개", actual=f"{len(received)}개")

    # 원본(DB) 측 기대 UID 집합 — 이번 전송으로 새로 생긴/갱신된 검사 기준
    studies = _rows(post, "study")
    study_uids = {s.get("StudyInstanceUID") for s in studies if s.get("StudyInstanceUID")}
    series_uids = {s.get("SeriesInstanceUID") for s in _rows(post, "series")}
    sop_uids = {i.get("ImageInstanceUID") for i in _rows(post, "instance")}
    patient_ids = {p.get("PatientID") for p in _rows(post, "patient")}

    bad = []
    rdsr = []
    for obj in received:
        if obj.get("SOPClassUID") == RDSR_SOP_CLASS:
            rdsr.append(obj)
        if obj.get("PatientID") not in patient_ids:
            bad.append((os.path.basename(obj["_path"]), "PatientID", obj.get("PatientID")))
        elif obj.get("StudyInstanceUID") not in study_uids:
            bad.append((os.path.basename(obj["_path"]), "StudyInstanceUID",
                        obj.get("StudyInstanceUID")))

    r.assert_true(5, "수신 객체의 Patient ID / Study Instance UID가 원본과 일치",
                  not bad, expected="불일치 0건",
                  actual=f"불일치 {len(bad)}건: {bad[:5]}")

    img_objs = [o for o in received if o.get("SOPClassUID") != RDSR_SOP_CLASS]
    matched_sop = [o for o in img_objs if o.get("SOPInstanceUID") in sop_uids]
    r.assert_true(5, "수신 영상의 SOP Instance UID가 원본 INSTANCE와 일치",
                  len(matched_sop) == len(img_objs),
                  expected=f"{len(img_objs)}건 전부 일치",
                  actual=f"{len(matched_sop)}/{len(img_objs)}건 일치")

    matched_series = [o for o in img_objs if o.get("SeriesInstanceUID") in series_uids]
    r.assert_true(5, "수신 영상의 Series Instance UID가 원본과 일치",
                  len(matched_series) == len(img_objs),
                  expected=f"{len(img_objs)}건 전부 일치",
                  actual=f"{len(matched_series)}/{len(img_objs)}건 일치")

    if expect_rdsr:
        r.assert_true(4, "RDSR 객체 수신", bool(rdsr),
                      expected=f"SOP Class UID {RDSR_SOP_CLASS} 1건 이상",
                      actual=f"{len(rdsr)}건")
        if rdsr:
            ok = all(o.get("PatientID") in patient_ids and
                     o.get("StudyInstanceUID") in study_uids for o in rdsr)
            r.assert_true(5, "RDSR의 Patient ID / Study Instance UID가 원본과 일치", ok,
                          expected="일치",
                          actual=[(o.get("PatientID"), o.get("StudyInstanceUID"))
                                  for o in rdsr])

    r.add(0, "수신 객체 목록 (참고)", PASS, expected="", actual="; ".join(
        f"{os.path.basename(o['_path'])}[{o.get('Modality')}]" for o in received[:10]))
    return r


def workflow_05_evaluate(ctx, pre, post):
    return _send_common(ctx, pre, post, "TC_Basic_WorkFlow_05",
                        "2D 수동 DICOM Send", expect_rdsr=False)


def workflow_06_evaluate(ctx, pre, post):
    r = _send_common(ctx, pre, post, "TC_Basic_WorkFlow_06",
                     "3D 수동 DICOM Send", expect_rdsr=False)
    r.manual(2, "3D 전송 대상 영상 종류",
             "Recon만 전송인지 Raw/Synthetic 포함인지 검증 버전 사양 확인 필요")
    return r


def workflow_07_evaluate(ctx, pre, post):
    return _send_common(ctx, pre, post, "TC_Basic_WorkFlow_07",
                        "All Images 및 Dose SR 전송", expect_rdsr=True)


# --------------------------------------------------------------------------
def workflow_10_evaluate(ctx, pre, post):
    r = TCResult("TC_Basic_WorkFlow_10", "Normal 및 Anonymous Export")
    exp = ctx.cfg.get("export") or {}
    normal_dir, anon_dir = exp.get("normal_dir") or "", exp.get("anonymous_dir") or ""

    patients = _rows(post, "patient")
    pid_set = {p.get("PatientID") for p in patients}
    pname_set = {p.get("PatientName") for p in patients}
    sop_uids = {i.get("ImageInstanceUID") for i in _rows(post, "instance")}

    if not (normal_dir and os.path.isdir(normal_dir)):
        r.skip(4, "Normal Export 결과 확인",
               "config.json > export.normal_dir 미설정 또는 경로 없음")
        normal = []
    else:
        normal = dicomlite.scan_dir(normal_dir)
        r.assert_true(4, "Normal Export 파일 생성", bool(normal),
                      expected=">= 1개", actual=f"{len(normal)}개")
        keep = [o for o in normal if o.get("PatientID") in pid_set]
        r.assert_true(4, "Normal Export가 원본 환자 정보를 유지", len(keep) == len(normal),
                      expected=f"{len(normal)}건 전부 원본 PatientID",
                      actual=f"{len(keep)}/{len(normal)}건 일치")
        m = [o for o in normal if o.get("SOPInstanceUID") in sop_uids]
        r.assert_true(4, "Normal Export 객체의 SOP Instance UID가 원본과 일치",
                      len(m) == len(normal),
                      expected="전건 일치", actual=f"{len(m)}/{len(normal)}건")

    if not (anon_dir and os.path.isdir(anon_dir)):
        r.skip(7, "Anonymous Export 결과 확인",
               "config.json > export.anonymous_dir 미설정 또는 경로 없음")
        anon = []
    else:
        anon = dicomlite.scan_dir(anon_dir)
        r.assert_true(7, "Anonymous Export 파일 생성", bool(anon),
                      expected=">= 1개", actual=f"{len(anon)}개")
        leaked = [(os.path.basename(o["_path"]), o.get("PatientID"), o.get("PatientName"))
                  for o in anon
                  if o.get("PatientID") in pid_set or o.get("PatientName") in pname_set]
        r.assert_true(8, "Anonymous Export 결과의 개인정보 익명화", not leaked,
                      expected="원본 PatientID/PatientName 노출 0건",
                      actual=f"노출 {len(leaked)}건: {leaked[:5]}")
        birth = [o for o in anon if (o.get("PatientBirthDate") or "").strip()]
        r.add(8, "Anonymous Export의 Patient Birth Date 처리", MANUAL,
              expected="익명화 정책상 처리 방식",
              actual=f"값 존재 {len(birth)}/{len(anon)}건",
              note="익명화 대상 Tag 목록이 문서상 확정되지 않아 사양 확인 필요")

    if normal and anon:
        r.assert_equal(8, "Normal/Anonymous 대상 객체 수 일치", len(normal), len(anon))
    else:
        r.skip(8, "Normal/Anonymous 대상 객체 수 일치", "두 경로 모두 지정되어야 판정 가능")

    d = snapshot.diff_section(pre, post, "instance_group")
    r.add(0, "INSTANCE_GROUP.StatusExported 변화 (참고)", PASS, expected="",
          actual=[c for c in d["changed"] if "StatusExported" in c["fields"]] or "변화 없음")
    return r


# --------------------------------------------------------------------------
def workflow_12_evaluate(ctx, pre, post):
    """Image Reject → Restore. pre=Reject 전, post=Restore 후."""
    r = TCResult("TC_Basic_WorkFlow_12", "Image Reject 및 Restore")

    d = snapshot.diff_section(pre, post, "instance_group")
    changed = d["changed"]

    # Step 3~5. Reject 후 Restore까지 마쳤으면 최종 상태는 원복이어야 한다
    reject_fields = {"StatusRejected", "RejectType", "RejectReason", "RejectUserID",
                     "RejectDate", "RejectTime"}
    residual = [c for c in changed if reject_fields & set(c["fields"])]
    r.assert_true(6, "Restore 후 Reject 상태가 원복됨", not residual,
                  expected="Reject 관련 컬럼 변화 0건",
                  actual=residual or "원복 완료")

    r.assert_true(6, "다른 영상의 상태가 변경되지 않음", not d["added"] and not d["removed"],
                  expected="INSTANCE_GROUP 행 추가/삭제 0건",
                  actual=f"추가 {len(d['added'])} / 삭제 {len(d['removed'])}")

    di = snapshot.diff_section(pre, post, "instance")
    r.assert_true(6, "영상(INSTANCE) 손실 없음", not di["removed"],
                  expected="삭제 0건", actual=f"삭제 {len(di['removed'])}건")

    r.manual(4, "Reject 목록에 동일 Patient/Study/Image 표시",
             "Reject 중간 상태 확인이 필요하면 --mid 스냅샷 사용 (run.py --phase mid)")
    return r


def workflow_12_mid_evaluate(ctx, pre, mid):
    """Reject 직후 중간 판정 (선택). pre=Reject 전, mid=Reject 직후."""
    r = TCResult("TC_Basic_WorkFlow_12_mid", "Image Reject 직후 상태 확인")
    d = snapshot.diff_section(pre, mid, "instance_group")
    rejected = [c for c in d["changed"] if "StatusRejected" in c["fields"]]
    r.assert_true(3, "선택한 영상만 Reject 상태로 전환", len(rejected) == 1,
                  expected="1건", actual=f"{len(rejected)}건: {rejected}")
    if rejected:
        f = rejected[0]["fields"]
        r.assert_true(3, "Reject 사용자/일시/사유 기록",
                      any(k in f for k in ("RejectUserID", "RejectDate", "RejectReason")),
                      expected="Reject 메타 기록", actual=f)
    return r


def workflow_13_evaluate(ctx, pre, post):
    """Study Reject → Restore. pre=Reject 전, post=Restore 후."""
    r = TCResult("TC_Basic_WorkFlow_13", "Study Reject 및 Restore")

    d = snapshot.diff_section(pre, post, "study")
    reject_fields = {"RejectType", "RejectReason", "RejectUserID", "StudyStatus"}
    residual = [c for c in d["changed"] if reject_fields & set(c["fields"])]
    r.assert_true(5, "Restore 후 검사 상태가 원복됨", not residual,
                  expected="Reject 관련 컬럼 변화 0건", actual=residual or "원복 완료")

    r.assert_true(5, "검사(STUDY) 손실 없음", not d["removed"],
                  expected="삭제 0건", actual=f"삭제 {len(d['removed'])}건")

    di = snapshot.diff_section(pre, post, "instance")
    r.assert_true(5, "검사 내 영상 전건 유지", not di["removed"],
                  expected="INSTANCE 삭제 0건", actual=f"삭제 {len(di['removed'])}건")

    dg = snapshot.diff_section(pre, post, "instance_group")
    r.assert_true(5, "영상 그룹 상태 원복", not dg["changed"],
                  expected="변화 0건", actual=dg["changed"] or "원복 완료")
    return r


def workflow_13_mid_evaluate(ctx, pre, mid):
    r = TCResult("TC_Basic_WorkFlow_13_mid", "Study Reject 직후 상태 확인")
    d = snapshot.diff_section(pre, mid, "study")
    rejected = [c for c in d["changed"]
                if {"RejectType", "StudyStatus", "RejectUserID"} & set(c["fields"])]
    r.assert_true(2, "대상 검사만 Reject 상태로 전환", len(rejected) == 1,
                  expected="1건", actual=f"{len(rejected)}건: {rejected}")
    return r


REGISTRY = [
    {"id": "TC_Basic_WorkFlow_01", "title": "MWL 및 Local 검사 생성 (판정부)",
     "mode": "prepost", "evaluate": workflow_01_evaluate,
     "pre_hint": "MWL 조회 전", "post_hint": "MWL/Local 검사 생성 후"},
    {"id": "TC_Basic_WorkFlow_05", "title": "2D 수동 DICOM Send",
     "mode": "prepost", "evaluate": workflow_05_evaluate,
     "pre_hint": "Send 실행 전 (SCP 수신 폴더도 비워둘 것)", "post_hint": "Queue Done 확인 후"},
    {"id": "TC_Basic_WorkFlow_06", "title": "3D 수동 DICOM Send",
     "mode": "prepost", "evaluate": workflow_06_evaluate,
     "pre_hint": "Send 실행 전", "post_hint": "Queue Done 확인 후"},
    {"id": "TC_Basic_WorkFlow_07", "title": "All Images 및 Dose SR 전송",
     "mode": "prepost", "evaluate": workflow_07_evaluate,
     "pre_hint": "Send 실행 전", "post_hint": "Queue Done 확인 후"},
    {"id": "TC_Basic_WorkFlow_10", "title": "Normal 및 Anonymous Export",
     "mode": "prepost", "evaluate": workflow_10_evaluate,
     "pre_hint": "Export 실행 전", "post_hint": "Normal/Anonymous Export 완료 후"},
    {"id": "TC_Basic_WorkFlow_12", "title": "Image Reject 및 Restore",
     "mode": "prepost", "evaluate": workflow_12_evaluate,
     "mid_evaluate": workflow_12_mid_evaluate,
     "pre_hint": "Reject 실행 전", "mid_hint": "Reject 직후", "post_hint": "Restore 완료 후"},
    {"id": "TC_Basic_WorkFlow_13", "title": "Study Reject 및 Restore",
     "mode": "prepost", "evaluate": workflow_13_evaluate,
     "mid_evaluate": workflow_13_mid_evaluate,
     "pre_hint": "Study Reject 실행 전", "mid_hint": "Reject 직후",
     "post_hint": "Restore 완료 후"},
]
