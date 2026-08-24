# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_09 - Normal 및 Anonymous Export.

체크리스트 원문 (변경 금지) - `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`
시트 `개정 TC` row 19:

  Precondition
    TC_Basic_WorkFlow_03이 Pass이다.
    Export 저장 매체에 충분한 공간이 있다.
  Step 1. Examined 창에서 DATA_FLOW_MWL_01 검사를 선택한다.
  Step 2. Export를 실행한다.
  Step 3. Export Manager에서 Local 경로와 Normal 옵션을 선택한다.
  Step 4. Export를 완료한다.
  Step 5. 동일 검사를 다시 Export한다.
  Step 6. Export Manager에서 Anonymous 옵션과 별도 경로를 선택한다.
  Step 7. Export를 완료한다.
  Step 8. 두 결과의 객체 수와 Patient 정보 처리 결과를 확인한다.
  Expected 1. 선택한 검사가 Export 대상으로 지정된다.
  Expected 2. Export Manager가 표시된다.
  Expected 3. Normal Export 옵션이 설정된다.
  Expected 4. 지정 경로에 원본 환자 정보를 유지한 파일이 생성된다.
  Expected 5. 동일 검사가 Export 대상으로 지정된다.
  Expected 6. Anonymous Export 옵션이 설정된다.
  Expected 7. 지정 경로에 익명화된 파일이 생성된다.
  Expected 8. 두 결과의 대상 객체 수가 일치하고 Anonymous 결과의 개인정보가
              익명화된다.
  Test Data: Normal  Evidence\Export\Normal\DATA_FLOW_MWL_01
             Anonymous Evidence\Export\Anonymous\DATA_FLOW_MWL_01

판정 근거 (운영 지침 2절)
  * "Export 했다"를 버튼 클릭으로 판정하지 않는다. **경로에 생긴 DICOM 파일을
    파싱해** Patient ID / Patient Name 을 읽고 원본 DB 값과 대조한다.
  * Normal 은 원본 환자정보 **유지**, Anonymous 는 **변경**이 기대값이다.
    익명화 방식(빈 값 / 고정 문자열 / 해시)은 사양에 명시돼 있지 않으므로
    "원본과 다르다"로 판정하고 실제 값을 증거에 남긴다. 특정 문자열을 기대값으로
    박으면 제품이 방식을 바꿀 때 근거 없이 FAIL 한다.
  * Step 8의 "객체 수 일치"는 두 경로의 **DICOM 파일 수**로 대조한다.
"""

import os

from core import dicomlite, export_manager as em, flows
from core import viewer_processing as vp
from core.result import TCResult, PASS, FAIL, MANUAL

# 익명 처리 대상과 기대값 - **사양서1 134쪽 명문**.
#
#   "익명 처리되는 환자 정보: Patient ID, Patient Name, Accession Number,
#    Other Patient ID, Other Patient Name, Birth Date, Age"
#   "익명 처리되는 병원 정보: Institution Name, Institution Address,
#    Institutional Department Name, Referring Physician Name,
#    Performing Physician Name, Operator Name"
#   "Anonymous 체크 시, **Patient ID 및 Patient Name은 Unknown으로 표시**"
#
# 처음에는 "익명화 방식이 사양에 명시돼 있지 않다"고 보고 '원본과 다르다'로만
# 판정했다. `core.specs`로 사양서를 검색해 보니 대상 태그와 기대값이 모두
# 적혀 있었다(2026-08-19). 사양이 값을 정해 두었으므로 **그 값으로 판정**한다.
ANONYMOUS_VALUE = "Unknown"
ANONYMIZED_PATIENT_TAGS = ("PatientID", "PatientName", "PatientBirthDate")

# Export 경로 규칙 - 사양서1 132쪽.
#   일반   : 선택한 경로\[Patient ID]_[Patient Name]\[Study Date]_[Study Time]_[Study Key]
#   익명화 : 선택한 경로\Unknown_Unknown\Anonymous_[StudyKey]
ANONYMOUS_DIR_MARKERS = ("Unknown_Unknown", "Anonymous_")


def _export_dir(ctx, kind, patient_id):
    """체크리스트 Test Data가 지정한 증거 경로를 만든다."""
    path = os.path.join(ctx.evidence_root, "Export", kind, patient_id)
    os.makedirs(path, exist_ok=True)
    return path


def _clear_dir(path):
    removed = 0
    for dirpath, _, files in os.walk(path):
        for name in files:
            try:
                os.remove(os.path.join(dirpath, name))
                removed += 1
            except OSError:
                pass
    return removed


def _scan(path):
    """경로의 DICOM 파일을 파싱한다. 반환: (객체 리스트, 파일 수)."""
    if not os.path.isdir(path):
        return [], 0
    count = sum(len(files) for _, _, files in os.walk(path))
    return dicomlite.scan_dir(path), count


def _open_export_manager(ctx, ui, r, step, patient_id):
    """Examined에서 대상 검사를 선택하고 Export를 실행한다."""
    from tests.workflow03 import _open_examined
    if [c for c in ui.by_id(flows.EXAMINE["close"]) if c.visible]:
        flows.close_examine(
            ui, option="suspend", wait=10,
            tesseract_exe=(ctx.cfg.get("xipl") or {}).get("tesseract_exe"))
    flows.ensure_patient_screen(ui, wait=3)
    _open_examined(ui)
    picked = vp.click_viewer_text(ui, "MWL", settle=1.5)
    button = [c for c in ui.by_id(2191) if c.visible]
    r.assert_true(
        step, "Examined 창에서 대상 검사 선택 후 Export 실행",
        bool(picked) and bool(button),
        expected=f"{patient_id} 검사 선택 후 Export(2191) 실행",
        actual={"card_selected": picked, "export_button": bool(button)},
        note="개정본 Expected 1. Export 진입점은 Examined 툴바의 2191이다(실측).")
    if not (picked and button):
        return None
    ui.click(button[0], settle=3)
    manager = em.attach()
    r.assert_true(
        step + 1, "Export Manager 표시", bool(manager.pid),
        expected="EXPORT.MANAGER 프로세스와 창 생성",
        actual={"pid": manager.pid},
        note="개정본 Expected 2. Viewer와 별도 최상위 프로세스다.")
    return manager


def _run_one(ctx, ui, r, patient_id, kind, anonymous, step_setup, step_done):
    """Export 1회를 수행하고 결과를 파싱해 돌려준다."""
    target = _export_dir(ctx, kind, patient_id)
    _clear_dir(target)
    manager = _open_export_manager(ctx, ui, r, step_setup - 1, patient_id)
    if manager is None:
        return None
    try:
        path = em.set_path(manager, target)
        state = em.set_anonymous(manager, enabled=anonymous)
        r.assert_true(
            step_setup, f"Export Manager에서 경로와 {kind} 옵션 선택",
            os.path.normcase(path) == os.path.normcase(target)
            and state.get("final") is anonymous,
            expected={"path": target, "anonymous": anonymous},
            actual={"path": path, "anonymous": state},
            note=f"경로 Edit({em.PATH_EDIT})과 Anonymous 옵션({em.ANONYMOUS})을 "
                 "실제로 설정하고 되읽어 확인한다. 토글이므로 누르기 전 상태를 "
                 "먼저 본다(운영 지침 11절).")
        outcome = em.export(manager, wait=180)
    finally:
        try:
            em.cancel(em.ViewerUi(em.PROCESS), timeout=10)
        except Exception:
            pass

    objects, files = _scan(target)
    r.assert_true(
        step_done, f"{kind} Export 완료 및 지정 경로에 파일 생성",
        bool(outcome.get("files")) and files > 0,
        expected="지정 경로에 DICOM 파일 생성",
        actual={"path": target, "files_created": len(outcome.get("files") or []),
                "files_on_disk": files, "parsed_objects": len(objects),
                "done_confirmed": outcome.get("done_confirmed")},
        note="버튼 클릭이 아니라 경로에 실제로 생긴 파일로 판정한다"
             "(운영 지침 2절).")
    return {"path": target, "objects": objects, "files": files,
            "outcome": outcome}


def workflow_09(ctx):
    r = TCResult("TC_Basic_WorkFlow_09", "Normal 및 Anonymous Export")
    patient_id = (ctx.cfg.get("xipl") or {}).get(
        "test_patient_id", "DATA_FLOW_MWL_01")
    try:
        session = vp.open_test_study(ctx)
        ui = session["ui"]
        origin = ctx.db.one(
            "DATA",
            "SELECT TOP 1 p.PatientID, p.PatientName, p.PatientBirthDate "
            "FROM PATIENT p WHERE p.PatientID=@pid", {"pid": patient_id}) or {}

        normal = _run_one(ctx, ui, r, patient_id, "Normal", False,
                          step_setup=3, step_done=4)
        if normal is None:
            return r
        anon = _run_one(ctx, ui, r, patient_id, "Anonymous", True,
                        step_setup=6, step_done=7)
        if anon is None:
            return r

        # --- Step 4 보강: Normal 은 원본 환자정보를 유지해야 한다 ----------
        normal_ids = {o.get("PatientID") for o in normal["objects"]
                      if o.get("PatientID")}
        r.assert_true(
            4, "Normal Export 결과가 원본 환자 정보를 유지",
            bool(normal_ids) and normal_ids == {origin.get("PatientID")},
            expected=f"Export 파일의 Patient ID = {origin.get('PatientID')!r}",
            actual={"patient_ids": sorted(normal_ids),
                    "db": {k: origin.get(k) for k in ANONYMIZED_PATIENT_TAGS}},
            note="개정본 Expected 4. 생성된 DICOM 파일을 파싱해 DATA.PATIENT와 "
                 "대조한다.")

        # --- Step 7 보강: Anonymous 는 개인정보가 바뀌어야 한다 ------------
        anon_ids = {o.get("PatientID") for o in anon["objects"]
                    if o.get("PatientID") is not None}
        anon_names = {str(o.get("PatientName") or "").rstrip("^")
                      for o in anon["objects"] if o.get("PatientName") is not None}
        still_original = anon_ids & {origin.get("PatientID")}
        if anon["objects"]:
            # 사양서1 134쪽: "Anonymous 체크 시, Patient ID 및 Patient Name은
            # Unknown으로 표시". 사양이 값을 정했으므로 그 값으로 판정한다.
            ids_ok = anon_ids == {ANONYMOUS_VALUE}
            names_ok = anon_names == {ANONYMOUS_VALUE}
            r.assert_true(
                7, "Anonymous Export 결과의 개인정보 익명화",
                ids_ok and names_ok and not still_original,
                expected={"PatientID": ANONYMOUS_VALUE,
                          "PatientName": ANONYMOUS_VALUE},
                actual={"patient_ids": sorted(x for x in anon_ids if x),
                        "patient_names": sorted(x for x in anon_names if x),
                        "still_original": sorted(still_original),
                        "origin": {k: origin.get(k)
                                   for k in ANONYMIZED_PATIENT_TAGS}},
                note="개정본 Expected 7. 근거: 사양서1 134쪽 'Anonymous 체크 시, "
                     "Patient ID 및 Patient Name은 Unknown으로 표시'. 같은 쪽에 "
                     "익명 처리 대상(Patient ID/Name, Accession Number, Other "
                     "Patient ID/Name, Birth Date, Age)과 병원 정보 목록도 있다. "
                     "Patient Name의 DICOM 구분자(^)는 비교 전에 제거한다.")
            # 사양서1 132쪽의 경로 규칙도 함께 확인한다(참고 판정).
            dirs = [d for d, _, _ in os.walk(anon["path"])]
            matched = [d for d in dirs
                       if any(m in os.path.basename(d)
                              for m in ANONYMOUS_DIR_MARKERS)]
            r.add(7, "[참고] Anonymous Export 폴더 구조", PASS if matched else MANUAL,
                  expected=r"선택한 경로\Unknown_Unknown\Anonymous_[StudyKey]",
                  actual={"matched_dirs": [os.path.basename(d) for d in matched],
                          "all_dirs": [os.path.basename(d) for d in dirs][:8]},
                  note="근거: 사양서1 132쪽 Export 경로 규칙. 폴더 규칙은 개정본 "
                       "Expected에 없어 참고로만 기록한다.")
        else:
            r.manual(7, "Anonymous Export 결과의 개인정보 익명화",
                     "Anonymous 경로의 파일을 파싱하지 못했다. 파일은 생성됐는지 "
                     "Step 7의 files_on_disk 를 확인할 것.",
                     expected="익명화된 DICOM 파일", actual="파싱 객체 0건")

        # --- Step 8: 두 결과의 객체 수 일치 --------------------------------
        r.assert_equal(
            8, "Normal과 Anonymous 결과의 대상 객체 수 일치",
            normal["files"], anon["files"],
            note="개정본 Expected 8. 같은 검사를 두 번 내보냈으므로 파일 수가 "
                 "같아야 한다. 개인정보 처리 결과는 Step 4/7이 판정한다.")
    except Exception as exc:
        r.abort(0, "TC_Basic_WorkFlow_09 실행", exc)
    return r


def run(ctx):
    return [workflow_09(ctx)]
