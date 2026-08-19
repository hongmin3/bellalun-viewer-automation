# -*- coding: utf-8 -*-
r"""3D-Narrow / 3D-Wide 촬영 등록 및 획득 (자동화 보조 항목).

  AUTOMATION_3D_ACQUISITION_3DN  3D-Narrow 촬영 등록 및 획득
  AUTOMATION_3D_ACQUISITION_3DW  3D-Wide 촬영 등록 및 획득

**개정본 체크리스트의 TC가 아니다.** 이 흐름은 이전 체크리스트
(`지식\(TC) R-23-2346...xlsx`)의 `TC_System_compatibility_03/04`에서 왔고,
기준 문서인 `..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`에는
`TC_System_compatibility_*` 항목이 없다(`AGENTS.md` 0절 참고).

그래서 **개정본 TC ID를 붙이지 않고** `AUTOMATION_*` 보조 항목으로 보고한다.
검증 자체는 유효하므로(3D 촬영 등록과 ExposureMode 구분) 계속 수행하되, 체크리스트
결과 xlsx에는 '자동화 추가 항목'으로 덧붙는다. 개정본에서 3D 촬영은 `WF_02`
(공통 2D/3D 촬영)가 3D-N을 다루고, 3D-W는 `Performance_03`(획득시간)에만 나온다.

두 항목의 단계는 동일하고 Preset만 다르다.

  1. 3D-Narrow(또는 3D-Wide)을 등록한다.
  2. System - LCD에 등록된 스텝과 환자정보를 확인한다.
  3. 3D-Narrow(또는 3D-Wide)영상을 촬영한다.

기대 결과
  2. 뷰어에 등록한 스텝과 환자정보가 표시된다.
  3. 해당 3D 영상이 촬영된다.
  비고: "3D 촬영은 2430 패들 연결했을때 가능", 회전 범위는
        3D-N -7.5~7.5도 / 3D-W -15~15도.

자동화 범위와 한계
  - Step 1/3은 Viewer UI와 DB로 완전 자동 판정한다. 실제 X-ray 대신 Demo(F8)
    가상 촬영을 쓴다(Service Manual 5.2.3). 획득 영상의 "내용"은 선택한 Step과
    무관하므로 내용 기반 판정은 하지 않고, InstanceType/Series/Group/UID 구조로
    판정한다(운영 지침).
  - Step 2의 "System(장비) LCD 표시"와 패들/회전 각도는 실물 장비가 있어야
    확인 가능하므로 MANUAL로 남긴다. 같은 단계에서 자동 판정 가능한
    "뷰어에 등록한 스텝과 환자정보 표시"는 자동으로 검증한다.
"""

import os
import re
import time

from PIL import Image, ImageGrab, ImageOps

from core import flows, screen, viewer_processing as vp
from core.result import FAIL, TCResult


# INSTANCE_GROUP.Type / ExposureMode 로 촬영 종류가 DB에 남는다. 실측 매핑:
#   Type=0, ExposureMode=0 -> 2D
#   Type=1, ExposureMode=1 -> 3D-Narrow
#   Type=1, ExposureMode=2 -> 3D-Wide
# 1/2 매핑은 이미 검증된 WF02의 3D-N fixture(DATA_FLOW_MWL_01의 3D 그룹이
# ExposureMode=1)와 3D-W Preset으로 새로 촬영한 그룹(ExposureMode=2)을
# 대조해 확정했다. Step 카드 라벨 OCR보다 이 값이 훨씬 강한 증거다.
GROUP_TYPE_3D = 1

# 체크리스트 비고의 회전 범위. 실제 각도 측정은 장비 없이는 불가하므로
# MANUAL 노트에 그대로 실어 검증자가 확인할 근거만 남긴다.
MODES = {
    "3d": {"tc": "AUTOMATION_3D_ACQUISITION_3DN",
           "title": "3D-Narrow 촬영 등록 및 획득",
           "label": "3D-N", "rotation": "-7.5~7.5도", "exposure_mode": 1},
    "3d-w": {"tc": "AUTOMATION_3D_ACQUISITION_3DW",
             "title": "3D-Wide 촬영 등록 및 획득",
             "label": "3D-W", "rotation": "-15~15도", "exposure_mode": 2},
}


def _ocr_text(bbox, whitelist, psm=7, invert=True):
    import pytesseract
    if os.path.exists(vp.TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = vp.TESSERACT_EXE
    crop = ImageGrab.grab(bbox=bbox, all_screens=True).convert("L")
    crop = ImageOps.autocontrast(crop)
    if invert:
        crop = ImageOps.invert(crop)
    crop = crop.resize((crop.width * 4, crop.height * 4),
                       Image.Resampling.LANCZOS)
    text = pytesseract.image_to_string(
        crop, config=f"--psm {psm} -c tessedit_char_whitelist={whitelist}")
    return re.sub(r"\s+", " ", text).strip()


def _step_card_label(card):
    """Procedure 썸네일 카드 상단 이름 띠를 읽는다 (예: 'LCC (3D-W)')."""
    l, t, r, b = card.rect
    return _ocr_text((l + 2, t + 2, r - 2, t + 28),
                     "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()- ")


def _label_matches(card_label, mode_label):
    """카드 라벨이 해당 3D 종류인지 관용적으로 판정한다.

    라벨 띠는 글자가 작아 '3'이 'G'/'B'로 오독된다(실측: 'LCC(3D-N)' ->
    'LCCGD-N)', 'LCC(3D-W)' -> 'LCCBD-W)'). 반면 3D-N/3D-W를 가르는 마지막
    글자는 안정적으로 읽힌다. 그래서 '3'까지 요구하지 않고 'DN'/'DW'만 본다.
    2D 카드는 접미사 자체가 없어 이 검사와 충돌하지 않으며, 3D 종류의
    최종 확정은 DB의 INSTANCE_GROUP.ExposureMode로 별도 판정한다.
    """
    key = re.sub(r"[^A-Z0-9]", "", (card_label or "").upper())
    return mode_label.replace("3", "").replace("-", "") in key


def _header_text(ui):
    """Viewer 상단 환자 정보 영역(이름/ID)을 읽는다."""
    win = ui.main_window()
    l, t, r, b = win.rect
    return _ocr_text((l + 10, t + 10, l + 1300, t + 62),
                     "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                     "0123456789_/()- ", psm=7, invert=False)


def _capture(ctx, ui, name, result):
    path = os.path.join(ctx.evidence_root, "Flow", "09_System3D", name)
    screen.grab(ui.main_window().rect, path=path)
    result.attach(path)
    return path


def _instance_counts(ctx, study_key):
    rows = ctx.db.query(
        "DATA", "SELECT InstanceType,COUNT(*) AS Cnt FROM INSTANCE "
        "WHERE StudyKey=@study GROUP BY InstanceType ORDER BY InstanceType",
        {"study": study_key})
    return {int(row["InstanceType"]): int(row["Cnt"]) for row in rows}


def _wait_types(ctx, study_key, required, timeout=90):
    end = time.time() + timeout
    counts = _instance_counts(ctx, study_key)
    while time.time() < end and any(counts.get(t, 0) < n
                                    for t, n in required.items()):
        time.sleep(2)
        counts = _instance_counts(ctx, study_key)
    return counts


def _acquired_3d_rows(ctx, study_key, group_key):
    return ctx.db.query(
        "DATA", "SELECT [Key],InstanceType,SeriesKey,GroupKey,ImageInstanceUID "
        "FROM INSTANCE WHERE StudyKey=@study AND GroupKey=@grp "
        "ORDER BY InstanceType", {"study": study_key, "grp": group_key})


def run_mode(ctx, mode):
    spec = MODES[mode]
    r = TCResult(spec["tc"], spec["title"])
    ui = None
    completed = False
    try:
        ui, _ = flows.cold_start(ctx.cfg, ctx.db, force_restart=True)
        flows.ensure_patient_screen(ui)
        patient_id = flows.unique_patient_id(f"SYS3D_{spec['label'].replace('-', '')}")
        patient_name = f"SYS3D {spec['label']}"
        flows.fill_new_patient(ui, patient_id, patient_name, sex="F")
        flows.start_examine_from_new_patient(ui, wait=8)

        study = ctx.db.one(
            "DATA",
            "SELECT TOP 1 s.[Key],p.PatientID,p.PatientName "
            "FROM STUDY s JOIN PATIENT p ON p.[Key]=s.PatientKey "
            "WHERE p.PatientID=@pid ORDER BY s.[Key] DESC",
            {"pid": patient_id})
        if not study:
            raise RuntimeError(f"검사 생성 실패: PatientID={patient_id}")

        # --- Step 1: 3D Preset 등록 -----------------------------------
        before = len(flows.step_items(ui))
        after = vp.add_view_position(ui, mode)
        target_step = after            # 방금 추가한 카드가 목록의 마지막
        card = flows.select_step(ui, target_step)
        card_label = _step_card_label(card)
        label_ok = _label_matches(card_label, spec["label"])
        _capture(ctx, ui, f"01_registered_{spec['label']}.png", r)
        r.assert_true(
            1, f"{spec['label']} View Position 등록",
            after == before + 1 and label_ok,
            expected=f"Procedure + / Preset({spec['label']}) / LCC / OK 후 "
                     f"Step {before}->{before + 1}, 카드 이름에 "
                     f"{spec['label']} 표시",
            actual={"steps_before": before, "steps_after": after,
                    "card_label": card_label})

        # --- Step 2: 등록 스텝/환자정보 표시 ---------------------------
        header = _header_text(ui)
        header_key = re.sub(r"[^A-Z0-9]", "", header.upper())
        header_ok = (re.sub(r"[^A-Z0-9]", "", patient_id.upper()) in header_key)
        r.assert_true(
            2, "뷰어에 등록한 스텝과 환자정보 표시",
            label_ok and header_ok,
            expected=f"선택 Step 카드에 {spec['label']}, 상단에 "
                     f"Patient ID {patient_id} 표시",
            actual={"card_label": card_label, "header": header,
                    "db": study})
        r.manual(
            2, "System(장비) LCD 스텝/환자정보 표시",
            "장비 LCD 표시는 실물 System 연결이 필요해 자동 판정 대상이 아니다. "
            f"3D 촬영은 2430 패들 연결 시 가능하며 Step 회전 범위는 "
            f"{spec['rotation']}(체크리스트 비고)이다.",
            expected=f"LCD에 등록 Step({spec['label']})과 환자정보 표시",
            actual="실물 장비 확인 필요")

        # --- Step 3: 해당 3D 영상 촬영 --------------------------------
        # Demo(F8)는 선택된 Step 1개만 촬영한다. select_step은 카드가 패널
        # 밖으로 잘려 있으면 스크롤해서 실제로 선택되도록 보장한다.
        info = flows.demo_acquire_step(ui, target_step, settle=20)
        if info.get("skipped"):
            raise RuntimeError(f"Ready 상태가 아니어서 촬영하지 않았습니다: {info}")
        counts = _wait_types(ctx, study["Key"], {1: 1, 2: 1, 3: 1})
        groups = ctx.db.query(
            "DATA", "SELECT [Key],Type,ExposureMode FROM INSTANCE_GROUP "
            "WHERE StudyKey=@study ORDER BY [Key] DESC",
            {"study": study["Key"]})
        group = groups[0] if groups else {}
        rows = _acquired_3d_rows(ctx, study["Key"],
                                 group["Key"]) if group else []
        types = sorted(int(x["InstanceType"]) for x in rows)
        uids = [str(x.get("ImageInstanceUID") or "") for x in rows]
        same_series_group = (bool(rows)
                             and len({x["SeriesKey"] for x in rows}) == 1
                             and len({x["GroupKey"] for x in rows}) == 1)
        # 3D 종류(Narrow/Wide)까지 DB로 확정한다. 이것이 없으면 3D-W TC가
        # 3D-N 촬영으로도 통과해 버린다.
        mode_ok = (int(group.get("Type", -1)) == GROUP_TYPE_3D
                   and int(group.get("ExposureMode", -1)) == spec["exposure_mode"])
        _capture(ctx, ui, f"02_acquired_{spec['label']}.png", r)
        r.assert_true(
            3, f"{spec['label']} 영상 촬영",
            types == [1, 2, 3] and same_series_group and mode_ok
            and all(uids) and len(set(uids)) == len(uids),
            expected=("동일 Series/Group에 InstanceType 1(Raw)/2(Recon)/3(Syn) "
                      "각 1건, Image Instance UID 발급·유일, "
                      f"INSTANCE_GROUP.Type={GROUP_TYPE_3D} 및 "
                      f"ExposureMode={spec['exposure_mode']}({spec['label']})"),
            actual={"acquire": info, "instance_types": counts,
                    "group": group, "group_rows": rows,
                    "same_series_group": same_series_group,
                    "mode_ok": mode_ok},
            note="실제 X-ray 대신 Demo(F8) 가상 촬영. 획득 영상의 내용은 "
                 "Step과 무관하므로 DB 구조/ExposureMode로만 판정한다.")
        completed = True
    except Exception as exc:
        r.add(0, f"{spec['tc']} 실행", FAIL, actual=str(exc))
    finally:
        if ui is not None:
            try:
                cancel = [c for c in ui.by_id(1102) if c.visible
                          and c.rect[2] - c.rect[0] >= 80]
                if cancel:
                    ui.click(cancel[0], settle=1)
                if ui.by_id(flows.EXAMINE["close"]):
                    flows.close_examine(
                        ui, option="close" if completed else "suspend", wait=8)
            except Exception:
                pass
    return r


def system_compatibility_03(ctx):
    return run_mode(ctx, "3d")


def system_compatibility_04(ctx):
    return run_mode(ctx, "3d-w")


def run(ctx):
    return [system_compatibility_03(ctx), system_compatibility_04(ctx)]
