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

#: 선량 Overlay 에 **숫자 값**이 찍혔는지 보는 패턴 (`28 kVp` / `32 mAs`).
#  OCR 변형에 따라 `28 k¥p` / `32 MAS` 로도 읽힌다.
DOSE_VALUE_MARKERS = {
    "Dose kVp": re.compile(r"\d\s*k[v¥y]p"),
    "Dose mAs": re.compile(r"\d\s*m[a4]s"),
}

#: 선량 Overlay 가 **값 없이 라벨만** 찍혔는지 보는 패턴 (`-- kVp` / `-- mAs`).
#  실측 크롭에서 `--k¥p` / `-- mAs` 로 읽힌다(bin150/bin110 x psm6).
DOSE_DASH_MARKERS = {
    "Dose kVp": re.compile(r"[-—–~_=]{1,3}\s*k[v¥y]p"),
    "Dose mAs": re.compile(r"[-—–~_=]{1,3}\s*m[a4]s"),
}

#: 사양서 **723쪽 SRS 03-50-10** — "영상 종류에 따라 표시 가능한 값이 다른 항목":
#
#      항목        2D  3D Raw  3D Recon  3D Sync
#      Dose kVp    O     O        X         X
#      Dose mA     O     O        X         X
#      Dose ms     O     O        X         X
#      Dose mAs    O     O        X         X
#
#  즉 선량 **값**은 2D 와 3D Raw 에만 표시된다. 3D Recon/Sync 는 라벨은 찍히고
#  값 자리에 `--` 가 들어간다(2026-08-27 실측 크롭
#  `Evidence/Flow/15_PreSendPreview/02_preview_panel2_bottom.png` — `-- kVp` /
#  `-- mAs`). **그것이 사양대로의 정상**이므로 값이 없다고 실패로 판정하지 않고,
#  거꾸로 "값이 있어야 하는 종류에 값이 있는가"를 이 표로 판정한다.
#  키는 `core/send_verify.INSTANCE_NAMES` 의 InstanceType 이다.
DOSE_VALUE_BY_INSTANCE_TYPE = {0: True, 1: True, 2: False, 3: False}
DOSE_SPEC_CITE = ("사양서 723쪽 SRS 03-50-10 — 영상 종류별 표시 가능 값 표 "
                  "(Dose kVp/mA/ms/mAs: 2D O, 3D Raw O, 3D Recon X, 3D Sync X)")

#: 패널이 3D 영상인지 알려 주는 View Position 라벨. 제품이 패널 왼쪽 위에
#  `LCC (3D-N)` / `RCC (3D-W)` 처럼 촬영 모드를 괄호로 붙여 표시한다
#  (2026-08-28 실측 — Pre-send Preview panel2 top 크롭에서 `LCC (3D-N)` 판독).
#  2D 패널에는 괄호 표기가 없다.
PANEL_3D_MARKER = re.compile(r"\(?3[do]-?[nw]\)?")


def panel_kind(reads):
    """패널 Overlay 문구로 **2D 인지 3D 인지** 판별한다.

    선량 표시 사양(`DOSE_VALUE_BY_INSTANCE_TYPE`)이 영상 종류에 따라 갈리므로,
    패널을 종류별로 나눠 판정하려면 이 구분이 필요하다. 패널 순서와 전송 대상
    순서를 짝짓는 방식은 쓰지 않는다 — Preview 는 Layout 에 따라 일부만
    보여주므로(사양서 778쪽 "기본 Layout 은 1x2") 순서 가정이 깨진다.

    반환: `"3D"` / `"2D"`
    """
    text = _recognized_text(reads).lower()
    return "3D" if PANEL_3D_MARKER.search(text.replace(" ", "")) else "2D"


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


def _text_lines(image):
    """밝은 글자의 수평 띠를 분리한다. 값이나 기대 문구로 영역을 고르지 않는다."""
    gray = image.convert('L')
    # 세로로 이어진 밝은 유방 영상/장식은 글자 줄이 아니다. 해당 열을
    # 투영에서 제외해야 왼쪽 영상이 오른쪽 텍스트의 모든 줄을 연결하지 않는다.
    from PIL import ImageDraw
    projection = gray.point(lambda value: 255 if value >= 180 else 0)
    draw = ImageDraw.Draw(projection)
    for x in range(gray.width):
        count = projection.crop((x,0,x+1,gray.height)).histogram()[255]
        if count > gray.height * .6:
            draw.line((x,0,x,gray.height),fill=0)
    runs, start = [], None
    for y in range(gray.height + 1):
        ink = y < gray.height and sum(projection.crop(
            (0, y, gray.width, y + 1)).histogram()[180:]) >= 3
        if ink and start is None:
            start = y
        elif not ink and start is not None:
            if 4 <= y - start <= 32:
                runs.append((max(0, start-4), min(gray.height, y+4)))
            start = None
    lines = []
    for top, bottom in runs[:12]:
        bounds = projection.crop((0,top,image.width,bottom)).getbbox()
        if bounds:
            lines.append(image.crop((max(0,bounds[0]-4),top,
                                     min(image.width,bounds[2]+4),bottom)))
    return lines


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
        # 긴 환자 ID가 오른쪽 60% 크롭 경계에 걸리는 경우와 작은 글자의
        # 다중 행 분할 실패를 보완한다. 원래 판독과 기대값은 그대로 유지한다.
        line_region = image.crop((0, 0, width, int(height*.32))) if tag == 'top' else crop
        for index, line in enumerate(_text_lines(line_region), 1):
            line.save(f"{stem}_{tag}_line{index}.png")
            for key, text in uitext.read_overlay_text(
                    line, tesseract_exe, scales=scales, psms=(7,),
                    variants=('auto', 'invert')).items():
                reads[f"{tag}_line{index}_{key}"] = text
    return reads


def _recognized_text(reads):
    return ' '.join(text for text in reads.values()
                    if not text.lstrip().lower().startswith('<ocr err'))


def hits(reads, study=None, markers=OVERLAY_MARKERS):
    """읽은 Overlay 문구에서 기대 항목이 보이는지.

    `study` 를 주면 `PatientID` / `PatientBirthDate` 를 함께 대조한다.
    `_pid_match` 에는 완전일치인지 접두사 일치인지를 남긴다 — 접두사로만 통과하는
    상태를 정상으로 굳히지 않기 위해서다.
    """
    raw = _recognized_text(reads).lower()
    joined = norm(raw)
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


def dose_state(reads):
    """선량 Overlay 가 **값으로** 찍혔는지 `--` 로 찍혔는지 항목별로 가른다.

    반환: `{"Dose kVp": "value"|"dash"|"none", "Dose mAs": ...}`

    왜 필요한가 — `hits()` 의 `OVERLAY_MARKERS` 는 라벨(`kVp`/`mAs`)만 보므로
    `28 kVp` 와 `-- kVp` 를 구분하지 못한다. 그런데 사양서 723쪽 SRS 03-50-10 이
    **영상 종류마다 표시 가능한 값이 다르다**고 정하므로(위
    `DOSE_VALUE_BY_INSTANCE_TYPE`), 그 사양을 판정하려면 둘을 갈라야 한다.

    `value` 를 `dash` 보다 우선한다. 여러 전처리 x psm 결과를 합쳐 보기 때문에
    한 변형이 숫자를 잡음으로 잘못 읽는 것보다 **하나라도 숫자를 읽었으면 값이
    찍힌 것**으로 보는 편이 안전하다 — 값이 있는데 `dash` 로 판정하면 사양을
    지킨 제품을 결함으로 만든다.
    """
    observations = {key: text for key, text in reads.items()
                    if not key.startswith("top_")}
    return {label: _dose_observation(observations, label)[0] for label in DOSE_VALUE_MARKERS}


def dose_expected(instance_type):
    """이 InstanceType 의 영상에 선량 **값**이 표시되어야 하는가(사양)."""
    return DOSE_VALUE_BY_INSTANCE_TYPE.get(int(instance_type), False)


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


#: 항목 라벨이 화면에 찍히는 글자(OCR 판독 대조표의 기대 텍스트).
LABEL_TEXT = {"Dose kVp": "kVp", "Dose mAs": "mAs"}


def panel_crop(evidence_dir, prefix, index, tag):
    """`read_all`이 저장한 패널 크롭 경로(`<prefix><index>_<tag>.png`)."""
    return os.path.join(evidence_dir, f"{prefix}{index}_{tag}.png")


def _region_reads(panel_reads, tag):
    return {key: text for key, text in (panel_reads or {}).items()
            if key.startswith(tag + "_")}


def _panel_for(marks, label):
    """`label`을 찾은 첫 패널 번호. 어느 패널에서도 못 찾았으면 1번 패널."""
    names = sorted(marks or {}, key=lambda name: int(re.sub(r"\D", "", name) or 0))
    for name in names:
        if (marks.get(name) or {}).get(label):
            return name
    return names[0] if names else None


#: 환자 정보 칸의 글자 차이 표시 설명. 판정(`norm`)과 같은 비교 규칙을 사람에게 알린다.
COMPARE_RULE = "DB 값. 판정은 대소문자·공백·기호를 빼고 O와 0을 같게 보고 비교한다"


def reading_rows(marks, reads, labels, evidence_dir, prefix, tag, expected_text,
                 miss_outcome, notes=None, compare_labels=()):
    """항목(라벨)별 OCR 판독 대조표 줄(REQ-REPORT-002).

    결과는 판정 코드가 쓴 `labels_seen`을 그대로 옮긴다. 보였으면 일치, 못 찾았으면 `miss_outcome`이다
    (판정이 FAIL이면 `mismatch`, MANUAL이면 `unread`). 패널이 하나도 없으면 읽지 못한 것이라 `unread`다.
    칸 캡처는 그 항목을 찾은 패널(못 찾았으면 1번 패널)의 `tag` 크롭이다.
    `compare_labels`의 항목은 기대 텍스트가 DB에서 확정한 값이라 글자 차이 기록(`compare`)을 붙인다.
    판정에 쓴 판독이 없으면 그 칸 판독 원문에서 가장 비슷한 구절과 대조한다.
    """
    from core import reading_evidence
    seen = labels_seen(marks, labels)
    rows = []
    for label in labels:
        panel = _panel_for(marks, label)
        region = _region_reads((reads or {}).get(panel), tag) if panel else {}
        outcome = "match" if seen.get(label) else (miss_outcome if marks else "unread")
        pattern = OVERLAY_MARKERS.get(label)
        read = ""
        if seen.get(label):
            want = norm(expected_text.get(label))
            read = next((text for text in region.values()
                         if (pattern and (pattern.search(text.lower())
                                          or pattern.search(text.lower().replace(" ", ""))))
                         or (want and want in norm(text))
                         or (label == "Patient ID" and want and want[:PID_PREFIX] in norm(text))), "")
        image = (panel_crop(evidence_dir, prefix, int(re.sub(r"\D", "", panel)), tag)
                 if panel else None)
        note = (notes or {}).get(label, "")
        if not marks:
            note = " ".join(part for part in (note, "영상 패널을 찾지 못했다.") if part)
        elif not seen.get(label):
            note = " ".join(part for part in (note, "어느 패널의 OCR 판독문에서도 찾지 못했다.") if part)
        compare = (reading_evidence.compare(expected_text.get(label), read, region.items(), COMPARE_RULE)
                   if label in compare_labels else None)
        rows.append(reading_evidence.row(
            f"{label} ({panel or '패널 없음'})", expected_text.get(label, label), outcome, read=read,
            reads=reading_evidence.ocr_reads(region), image=image, note=note, compare=compare))
    return rows


#: 선량 칸의 기대 텍스트. 영상 종류마다 사양(`DOSE_VALUE_BY_INSTANCE_TYPE`)이 정한 표시가 다르다.
DOSE_EXPECTED_TEXT = {"2D": "<숫자> {unit} (값 표시)", "3D": "-- {unit} (값 미표시)"}


def _dose_observation(reads, label):
    """한 판독에서 값 또는 대시와 단위가 함께 읽힌 경우만 근거로 쓴다."""
    for state, marker in (("value", DOSE_VALUE_MARKERS[label]), ("dash", DOSE_DASH_MARKERS[label])):
        for text in reads.values():
            low = text.lower()
            if not low.lstrip().startswith("<ocr err") and (marker.search(low) or marker.search(low.replace(" ", ""))):
                return state, text
    return "none", ""


def dose_reading_rows(reads, kinds, evidence_dir, prefix):
    """WF_15 선량 Overlay 판정을 패널·항목별 판독 대조표 줄로 옮긴다(REQ-REPORT-002).

    결과는 판정 코드와 같은 규칙이다. 2D는 값, 3D(Recon)는 `--`가 사양대로의 일치다.
    반대로 찍혔으면 불일치, 값도 `--`도 읽지 못했으면 판독 불가다.
    칸 캡처는 `read_panel`이 저장한 패널 아래 크롭이다.
    """
    from core import reading_evidence
    rows = []
    names = sorted(reads or {}, key=lambda name: int(re.sub(r"\D", "", name) or 0))
    for name in names:
        panel_reads = reads.get(name) or {}
        kind = (kinds or {}).get(name) or panel_kind(panel_reads)
        region = _region_reads(panel_reads, "bottom")
        image = panel_crop(evidence_dir, prefix, int(re.sub(r"\D", "", name) or 0), "bottom")
        for label in DOSE_VALUE_MARKERS:
            unit = LABEL_TEXT[label]
            want = "value" if kind == "2D" else "dash"
            got, observed = _dose_observation(region, label)
            outcome = ("unread" if got == "none"
                       else "match" if got == want else "mismatch")
            note = f"패널 종류 {kind}(View Position 표기로 판별). {DOSE_SPEC_CITE}."
            if got == "none":
                note += " 값도 `--`도 읽지 못했다."
            rows.append(reading_evidence.row(
                f"{label} ({name}, {kind})", DOSE_EXPECTED_TEXT[kind].format(unit=unit), outcome,
                read=observed, reads=reading_evidence.ocr_reads(region),
                image=image, note=note))
    return rows


def comparison_reading_rows(preview_any, view_any, view_marks, view_reads, labels, evidence_dir, prefix):
    """WF_15 Step 4의 Preview·View 항목 관찰 비교를 판독 대조표 줄로 옮긴다(REQ-REPORT-002).

    판정과 같이 두 화면의 관찰 결과(보임·안 보임)가 같으면 일치, 다르면 불일치다.
    칸 캡처는 View 화면에서 그 항목을 찾은 패널(못 찾았으면 1번 패널)의 크롭이다.
    선량 항목은 아래, 환자 정보는 위 크롭이다.
    """
    from core import reading_evidence

    def seen(flag):
        return "보임" if flag else "안 보임"

    rows = []
    for label in labels:
        tag = "top" if label in PATIENT_MARKERS else "bottom"
        panel = _panel_for(view_marks, label)
        region = _region_reads((view_reads or {}).get(panel), tag) if panel else {}
        image = (panel_crop(evidence_dir, prefix, int(re.sub(r"\D", "", panel)), tag)
                 if panel else None)
        same = bool(preview_any.get(label)) == bool(view_any.get(label))
        rows.append(reading_evidence.row(
            f"{label} ({panel or '패널 없음'})", f"Preview와 같음 (Preview: {seen(preview_any.get(label))})",
            "match" if same else "mismatch", read=f"View: {seen(view_any.get(label))}",
            reads=reading_evidence.ocr_reads(region), image=image,
            note="" if panel else "View 화면에서 영상 패널을 찾지 못했다."))
    return rows
