# -*- coding: utf-8 -*-
r"""영상 위 Image Overlay 를 읽고 기대 항목이 표시되는지 확인하는 공용 기능.

`tests/workflow15.py`(Pre-send Preview / View 화면)가 2026-08-20~21 에 만든
크롭·OCR·판정 코드를 옮겨 왔다. 2026-08-21 에 `TC_Basic_WorkFlow_03` Step 5
("2D 영상에 추가한 Image Overlay 항목 표시 확인")를 자동화하면서 **같은 판정을
두 곳에서 따로 구현하지 않기 위해** 공용화했다. OCR 경로가 하나여야 한쪽만
고쳐 다른 쪽이 조용히 낡는 일이 없다.

판정 원칙 — **값이 아니라 항목(라벨)이 표시되는가**로 본다.
  개정본 `WF_03` Expected 5 는 "설정한 Image Overlay 항목이 표시된다" 다.
  이 PC 는 실제 X-ray 대신 Demo(F8) 가상 촬영을 쓰므로 선량 값이 들어오지 않고
  `-- kVp` / `-- mAs` 로 찍힌다(2026-08-20 실측). "모든 패널에 숫자가 있어야
  한다"고 요구하면 **정상 동작을 실패로 판정한다.** 그래서 라벨 표시로 판정하고,
  숫자 값을 읽었는지는 관측으로 남긴다.

환자 정보(ID·생년월일)는 상수를 박지 않고 **DB 값과 대조**한다.
"""

from __future__ import annotations

import os
import re

from PIL import ImageGrab

from core import flows, uitext

#: 영상 패널 컨트롤. Pre-send Preview 창 / View 화면 / Examine 화면이 **같은
#  컨트롤 ID(203, UIInstanceManager)** 를 쓴다(2026-08-21 실측).
INSTANCE_PANEL = flows.PRE_SEND_PREVIEW["instance_panel"]

#: `WF_03` 이 Image Overlay 로 Bottom 에 추가하는 항목의 화면 문구 패턴.
#  OCR 은 `kVp` 의 V 를 `¥`/`Y` 로, `mAs` 의 A 를 `4` 로 자주 읽는다.
OVERLAY_MARKERS = {
    "Dose kVp": re.compile(r"k[v¥y]p"),
    "Dose mAs": re.compile(r"m[a4]s"),
}

#: 환자 정보 Overlay 항목. 값은 DB 에서 가져와 대조한다.
PATIENT_MARKERS = ("Patient ID", "Birth Date")

#: 패널을 여러 배율로 읽어 하나라도 맞으면 인정한다. 한 배율에 의존하면 흔들린다
#  (`WF_08` 이 같은 이유로 12/8/5 배율을 쓴다). 배율마다 전처리 4종 x psm 2종을
#  함께 시도한다(`core/uitext.read_overlay_text`).
OCR_SCALES = (6, 4)

#: 환자 ID 접두사 비교 길이. `DATA_FLOW_MWL_01` 에서 OCR 이 `MWL` 을 `MYL` /
#  `M¥WL` 로 읽어도 `datafl0w` 까지는 안정적으로 읽힌다. 다른 시험 환자
#  (`DATA_XIPL_...`)와 겹치지 않는 길이다.
PID_PREFIX = 8


def norm(value):
    """비교용 정규화. `O`/`0` 혼동까지 흡수한다."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower()).replace("o", "0")


def panels(ui, min_size=200):
    """현재 화면의 영상 패널을 왼쪽부터 돌려준다.

    같은 hwnd 가 여러 번 열거될 수 있어 중복을 제거한다. `min_size` 로 작은
    썸네일/버튼을 걸러 낸다.
    """
    hits = {c.hwnd: c for c in ui.controls(max_depth=8)
            if c.visible and c.ctrl_id == INSTANCE_PANEL
            and c.rect[2] - c.rect[0] > min_size
            and c.rect[3] - c.rect[1] > min_size}
    return sorted(hits.values(), key=lambda c: c.rect[0])


def read_panel(control, path, tesseract_exe, scales=OCR_SCALES):
    """영상 패널을 캡처해 Overlay 문구를 읽는다.

    Overlay 는 패널의 **위(환자정보)와 아래(선량)** 에 나뉘어 찍힌다. 한 곳만
    읽으면 Bottom 항목을 놓친다 — Print Overlay 에서 같은 실수를 했다.

    크롭 원본도 함께 저장한다. 운영 지침: **OCR 실패는 캡처 이미지를 먼저 본다.**
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    image = ImageGrab.grab(bbox=control.rect, all_screens=True)
    image.save(path)
    width, height = image.size
    reads = {}
    stem = os.path.splitext(path)[0]
    for tag, box in (("top", (int(width * .40), 0, width, int(height * .32))),
                     ("bottom", (int(width * .50), int(height * .84),
                                 width, height))):
        crop = image.crop(box)
        crop.save(f"{stem}_{tag}.png")
        for key, text in uitext.read_overlay_text(
                crop, tesseract_exe, scales=scales).items():
            reads[f"{tag}_{key}"] = text
    return reads


def hits(reads, study=None, markers=OVERLAY_MARKERS):
    """읽은 Overlay 문구에서 기대 항목이 보이는지.

    `study` 를 주면 `PatientID` / `PatientBirthDate` 를 함께 대조한다.
    `_pid_match` 에는 완전일치인지 접두사 일치인지를 남긴다 — 접두사로만 통과하는
    상태를 정상으로 굳히지 않기 위해서다.
    """
    joined = norm(" ".join(reads.values()))
    raw = " ".join(reads.values()).lower()
    found = {label: bool(rx.search(raw.replace(" ", "")) or rx.search(raw))
             for label, rx in markers.items()}
    if study is None:
        return found
    pid = norm(study.get("PatientID"))
    found["Patient ID"] = bool(pid) and (pid in joined
                                         or pid[:PID_PREFIX] in joined)
    found["_pid_match"] = ("exact" if pid and pid in joined
                           else "prefix" if pid and pid[:PID_PREFIX] in joined
                           else "none")
    found["Birth Date"] = norm(study.get("PatientBirthDate")) in joined
    return found


def read_all(ui, evidence_dir, prefix, tesseract_exe, study=None,
             attach=None, scales=OCR_SCALES):
    """보이는 모든 패널을 읽어 `(판정, 원문, 패널목록)` 을 돌려준다.

    `attach` 에 `TCResult.attach` 를 넘기면 크롭 증거를 리포트에 붙인다.
    """
    found_panels = panels(ui)
    reads, marks = {}, {}
    for index, panel in enumerate(found_panels, start=1):
        path = os.path.join(evidence_dir, f"{prefix}{index}.png")
        panel_reads = read_panel(panel, path, tesseract_exe, scales=scales)
        reads[f"panel{index}"] = panel_reads
        marks[f"panel{index}"] = hits(panel_reads, study)
        if attach is not None:
            attach(path)
    return marks, reads, found_panels


def labels_seen(marks, labels):
    """항목별로 **한 패널 이상에서** 보였는지."""
    return {label: any(v.get(label) for v in marks.values()) for label in labels}
