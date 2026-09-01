# -*- coding: utf-8 -*-
r"""DICOM Send 판정의 공용 부분 — Queue / 수신 객체 / 식별 Tag 대조.

WF_04(2D) / WF_05(3D) / WF_06(All Images + Dose SR)이 공유한다. TC 별 절차는
`tests/workflow04.py` / `workflow05.py` / `workflow06.py` 에 있다.

판정 원칙 (운영 지침 2절): **Queue 상태만 보지 않는다.** 실제 수신 객체의
Patient ID / Study·Series·SOP Instance UID 를 DB 원본과 대조하고, SOP Class 로
객체 종류까지 확인한다. 로그 문구 하나로 성공을 단정하지 않는다.

`tests/send_flows.py`(삭제됨)에서 분리했다(2026-08-19). 파일명이 담당 TC 를 드러내도록
TC 함수를 번호별 모듈로 옮기면서, 인프라에 해당하는 이 부분만 core 로 내렸다.
"""
import time

from core import flows, storagescp
from core import viewer_processing as vp
from core import dicom_settings as ds
from core.result import PASS, FAIL, SKIP

# Storage 서버 Option 컨트롤 (Setting > DICOM > Storage), 2026-08-18 실측.
# Transfer Syntax 관련 상수와 조작은 WF04와 공유하려고
# `core/dicom_settings.py`로 옮겼다(`ds.STORAGE_TRANSFER_SYNTAX`,
# `ds.TRANSFER_SYNTAX_IMPLICIT`, `ds.ensure_storage_transfer_syntax`).
STORAGE_MODALITY = 2460


def received(ctx, patient_id=None):
    """수신 객체를 **DICOM 태그까지 파싱해서** 돌려준다.

    2026-08-26 Bunny(로컬 파일 폴더) 대신 원격 Storage SCP 웹 서버를 쓴다.
    서버가 주는 목록은 series 단위까지라 SOP 단위 대조에는 모자라므로,
    스터디 ZIP 을 받아 `dicomlite` 로 파싱한다(`core/storagescp.py`).
    **반환 형식은 예전 `dicomlite.scan_dir` 과 같다** — 그래서 아래 판정들은
    Bunny 를 읽던 때와 똑같이 동작한다.

    **`patient_id` 를 주면 그 환자의 스터디만 본다.** 이 서버는 여러 PC 가 함께
    쓰는 **공유 SCP** 라, 우리가 보내는 사이에 다른 시험이 보낸 객체가 섞인다 —
    2026-08-26 실측: `WF_06` 판정에 VXvue 가 보낸 `VXVUE_260826_182948` 이
    끼어들어 "DB 에 없는 UID" 로 FAIL 했다. Bunny(로컬)에는 없던 문제다.
    필터를 걸면 다운로드도 우리 스터디만 받아 더 빠르다.

    비용이 있으므로(스터디마다 ZIP 다운로드) **확정 시점에만 부른다.**
    도중 폴링은 `wait_received_stable` 이 가벼운 목록 조회로 한다.
    """
    try:
        srv = storagescp.server(ctx)
        if patient_id:
            uids = [s["study_instance_uid"] for s in srv.studies()
                    if (s.get("patient_id") or "") == patient_id]
            return srv.objects(study_uids=uids) if uids else []
        return srv.objects()
    except Exception:
        return None


def _patient_instance_count(srv, patient_id):
    """서버 목록에서 그 환자의 인스턴스 수 합계.

    **다운로드하지 않는다** — `/api/studies` 한 번이면 되므로 폴링에 쓸 만큼 싸다.
    """
    total = 0
    for study in srv.studies():
        if (study.get("patient_id") or "") == patient_id:
            total += int(study.get("instance_count") or 0)
    return total


def clear_received(ctx, force=False):
    """수신 목록을 비운다. 이번 전송으로 도착한 것만 세기 위한 준비다.

    **이 서버는 여러 PC 가 함께 쓰고, 개별 스터디 삭제 API 가 없다**
    (`DELETE /api/studies` = 전체 삭제). 그래서 부를 때마다 **남의 수신 데이터까지
    지운다.** 판정은 환자 필터(`received(ctx, patient_id)`)로 이미 정확하므로,
    TC 마다 지울 이유가 없어졌다.

    - `config.json > dicom.clear_storage_before_send` (기본 `false`)
      → Send TC 가 전송 전에 지울지. 기본은 **지우지 않는다.**
    - `force=True` → 설정과 무관하게 지운다. **자동화가 서버 내용을 임의로
      건드리지 않는다는 2026-08-28 사용자 확정에 따라 어떤 자동 실행 경로도
      이제 `force=True` 로 부르지 않는다** — 필요하면 사람이 직접 호출한다.

    반환: 지웠으면 지우기 전 스터디 수, 지우지 않았으면 `None`.
    """
    if not force:
        wanted = (ctx.cfg.get("dicom") or {}).get(
            "clear_storage_before_send", False)
        if not wanted:
            return None
    try:
        srv = storagescp.server(ctx)
        before = len(srv.studies())
        srv.clear()
        return before
    except Exception:
        return 0


def _signature_count(signature):
    """서명 `"<건수>|<최근수신시각>"` 에서 건수만 뽑는다."""
    try:
        return int(str(signature or "0").split("|")[0])
    except (TypeError, ValueError):
        return 0


def configured_station_name(ctx):
    """전송 객체의 `StationName(0008,1010)` 기대값 — **Setting 값**이다.

    사양이 두 곳에서 못박는다(사양서2 `06. DICOM`).
      - Storage IOD 표: `Station Name (0008,1010) 3 VNAP **From Config**`
      - MWL 절: *"Worklist에 표기된 Station Name은 **MWL List에서만 사용된다.**
        그 외의 Station Name은 **Setting > General > DICOM에 설정된 Station
        Name**을 사용한다."*

    그래서 **MWL 오더에 넣은 Station Name 이 전송 객체에 실리면 사양 위반**이고,
    기대값은 `CONFIGURATION.DICOM_COMMON.StationName` 이다. Type 3 / VNAP 이라
    설정이 비어 있으면 값이 없는 것이 정상이다.
    """
    row = ctx.db.one("CONFIGURATION",
                     "SELECT TOP 1 StationName FROM DICOM_COMMON") or {}
    return (row.get("StationName") or "").strip()


def queue_keys(ctx):
    return {int(r["Key"]) for r in ctx.db.query(
        "DATA", "SELECT [Key] FROM DICOM_STORAGE_QUEUE")}


def db_instance_uids(ctx, patient_id):
    rows = ctx.db.query(
        "DATA",
        "SELECT i.ImageInstanceUID FROM INSTANCE i "
        "JOIN STUDY s ON s.[Key] = i.StudyKey "
        "JOIN PATIENT p ON p.[Key] = s.PatientKey "
        "WHERE p.PatientID = @pid AND i.ImageInstanceUID IS NOT NULL",
        {"pid": patient_id})
    return {r["ImageInstanceUID"] for r in rows}


def db_identity(ctx, patient_id):
    """원본 검사의 식별 Tag를 DB에서 읽는다.

    개정본 Step 5는 **Patient ID / Study Instance UID / Series Instance UID /
    SOP Instance UID 네 개**를 비교하라고 한다. 이전 구현은 SOP Instance UID와
    Patient ID만 봤다.

    반환: {"patient_id": ..., "study_uids": {...}, "series_uids": {...},
           "sop_uids": {...}, "by_type": {InstanceType: {sop_uid, ...}}}
    """
    rows = ctx.db.query(
        "DATA",
        "SELECT i.ImageInstanceUID, i.InstanceType, se.SeriesInstanceUID, "
        "s.StudyInstanceUID FROM INSTANCE i "
        "JOIN STUDY s ON s.[Key] = i.StudyKey "
        "JOIN PATIENT p ON p.[Key] = s.PatientKey "
        "LEFT JOIN SERIES se ON se.[Key] = i.SeriesKey "
        "WHERE p.PatientID = @pid AND i.ImageInstanceUID IS NOT NULL",
        {"pid": patient_id})
    by_type = {}
    for row in rows:
        by_type.setdefault(int(row["InstanceType"]), set()).add(
            row["ImageInstanceUID"])
    return {
        "patient_id": patient_id,
        "study_uids": {r["StudyInstanceUID"] for r in rows if r.get("StudyInstanceUID")},
        "series_uids": {r["SeriesInstanceUID"] for r in rows if r.get("SeriesInstanceUID")},
        "sop_uids": {r["ImageInstanceUID"] for r in rows},
        "by_type": by_type,
    }


def wait_received_stable(ctx, patient_id=None, wait=60, settle_rounds=3,
                         poll=2.0):
    """수신 개수가 **더 늘지 않을 때까지** 기다린 뒤 목록을 확정한다.

    이전 구현은 UID가 하나라도 보이면 즉시 break 해서, 실제로 여러 건이 도착해도
    판정에는 1건으로 기록됐다(2026-08-19 실측: SCP 로그에 C-STORE 5건인데 판정은
    전부 '수신 1건'). 그러면 "몇 개가 왔는가"를 요구하는 개정본 Expected를
    검증할 수 없다 - Selected(1개)와 All(전체)의 차이가 시험 대상이다.

    개수가 `settle_rounds`회 연속 같으면 확정한다.

    2026-08-26: 폴링을 **서버 서명**(`/api/studies/signature`, `"건수|최근수신시각"`)
    으로 바꿨다. 예전에는 회차마다 수신 파일을 전부 파싱했지만, 원격 서버에서는
    그것이 매번 ZIP 다운로드가 되어 비싸다. 서명이 `settle_rounds` 회 연속 같으면
    **그때 한 번만** 내려받아 파싱한다. 판정 의미는 그대로다 — 건수가 0 인 동안은
    안정으로 세지 않으므로, 아무것도 도착하지 않았는데 조기 확정하지 않는다.
    """
    srv = None
    try:
        srv = storagescp.server(ctx)
    except Exception:
        pass
    if srv is None:
        return []

    end = time.time() + wait
    last, stable = None, 0
    while time.time() < end:
        try:
            # 환자를 지정하면 **그 환자의 인스턴스 수**로 본다. 서명은 서버 전체
            # 기준이라, 공유 SCP 에서 다른 PC 가 보내는 동안 계속 바뀌어 안정을
            # 못 찾는다(2026-08-26).
            key = (_patient_instance_count(srv, patient_id) if patient_id
                   else srv.signature())
        except Exception:
            key = None
        settled = (key > 0 if patient_id
                   else bool(key) and _signature_count(key) > 0)
        if settled and key == last:
            stable += 1
            if stable >= settle_rounds:
                break
        else:
            stable = 0
        last = key
        time.sleep(poll)
    return received(ctx, patient_id) or []


def ensure_transfer_syntax(ctx, ui, r):
    """Storage Transfer Syntax를 사양이 선언한 값으로 맞추고 판정을 기록한다.

    실제 조작은 `core.dicom_settings.ensure_storage_transfer_syntax`가 한다
    (WF04와 공유 — 근거와 호출 시점 주의사항은 그 함수 주석 참고).

    **검사를 열기 전에 호출해야 한다.** 검사 진행 중에 Setting을 드나들면
    Examine 화면의 영상 선택이 풀려 Send 버튼이 비활성이 되고, 전송 범위
    대화상자가 아예 뜨지 않는다(2026-08-18 회귀에서 Step 2/5가 이렇게 실패했다).
    """
    # **설정된 활성 Storage SCP 가 하나인지 먼저 확인한다.** 이 저장소의 Send 판정은
    # "수신 객체가 정확히 N건"을 쓰는데, 활성 Storage 가 둘 이상이면 같은 영상이
    # 여러 SCP 로 나가 그 판정이 조용히 틀린다.
    #
    # 이 항목은 시험 대상이 아니라 **전제(setup)** 다. 이전 구현은 어긋난 상태를
    # FAIL 로 드러내기만 해서, 활성 행이 둘로 보이는 순간 WF05/WF06/WF15 가 전제
    # 단계에서 멈추고 정작 검증해야 할 전송 판정을 하나도 수행하지 못했다.
    # 그래서 **맞춰 놓고 그것을 확인**하되, 무엇을 복구했는지 actual/note 에 남겨
    # 감사할 수 있게 한다. **복구가 실패하면 그대로 FAIL 이다.**
    #
    # 복구도 조회도 `core/db.py` 의 조회 전용 원칙을 지킨다 — 상태 변경은
    # `ds.repair_storage_use` 가 Setting 화면의 Use 체크박스 클릭으로만 한다.
    #
    # 대상 이름은 `config.json > dicom.servers_to_register` 의 Storage 항목이다
    # (`dicom.storage_scp` 에는 Bunny 실행 정보만 있고 서버 등록 이름은 없다).
    target_name = next(
        (str(x.get("name")) for x in
         (ctx.cfg.get("dicom") or {}).get("servers_to_register", [])
         if x.get("kind") == "Storage"), "")

    active = ds.active_storage_rows(ctx.db)
    repair = None
    if len(active) != 1:
        repair = ds.repair_storage_use(ctx, ui, target_name)
        active = ds.active_storage_rows(ctx.db)
    job_copies = ds.storage_job_copies(ctx.db)
    r.add(1, "[전제] 활성 Storage SCP 가 하나",
          PASS if len(active) == 1 else FAIL,
          expected=(f"DICOM_STORAGE 에서 Use=1 AND "
                    f"SCPUseType={ds.STORAGE_SCP_USE_TYPE} 인 행 1개"),
          actual={"count": len(active), "rows": [dict(x) for x in active],
                  "job_copies": [dict(x) for x in job_copies],
                  "repair": repair},
          note="Use=1 인 **설정된** Storage SCP 가 둘 이상이면 같은 영상이 여러 SCP "
               "로 전송되어 '수신 객체가 정확히 N건' 판정이 틀린다. 그래서 전송 전에 "
               "이 전제를 확인한다.\n"
               "**`SCPUseType` 을 걸러야 한다 (2026-08-21 실측).** 제품은 전송을 "
               "큐에 넣을 때 그 시점의 Storage 설정을 **작업용 사본 행**으로 복제하고"
               "(`SCPUseType=1`) 원본을 `DICOM_STORAGE_QUEUE.OriginalStorageKey` 로 "
               "가리킨다. 사본도 `Use=1` 이라 예전 쿼리는 Send 한 번마다 '활성 SCP 가 "
               "하나 늘었다'고 오판정했다 — 실제로 `WF_05`/`WF_06`/`WF_15` 가 이 "
               "때문에 전제에서 멈췄다. `Setting > DICOM > Storage` 목록은 "
               "`SCPUseType=0` 행만 보여 주고, Storage Group / Storage Commitment / "
               "Query·Retrieve / MPPS 목록은 비어 있다(전부 실측). **제품 결함이 "
               "아니고 자동화 상태 누수도 아니다.** 사본은 actual.job_copies 에 "
               "관측으로 남긴다.\n"
               "설정 행이 그래도 여럿이면 UI(Storage 페이지의 Use 체크박스)로 하나만 "
               "남기고 DB 로 다시 확인한다 — 복구 내용은 actual.repair 에 남고, "
               "복구까지 실패하면 FAIL 이다(DB 쓰기는 하지 않는다). "
               + ("**이번 실행에서 복구했다.** " if repair else "")
               + "수동 해결: `python run.py reset-environment` 후 "
                 "`setup-dicom` 1회.")

    tess = (ctx.cfg.get("xipl") or {}).get("tesseract_exe")
    outcome = ds.ensure_storage_transfer_syntax(ctx, ui, tesseract_exe=tess)
    r.add(1, "Storage 서버 등록 및 Transfer Syntax 확인",
          PASS if outcome["ok"] else FAIL,
          expected=f"TransferSyntax={ds.TRANSFER_SYNTAX_IMPLICIT} (Implicit VR LE)",
          actual=outcome,
          note="DICOM Conformance Statement V1.3W1 Proposed Presentation Context "
               "Table이 네트워크 Storage SCU에 선언한 값. 제품 기본값인 JPEG 2000 "
               "Lossless(1.2.840.10008.1.2.4.90)는 conformant SCP가 Presentation "
               "Context를 거절해 전송이 실패한다(Bunny 로그 실측). "
               "CONFIGURATION.DICOM_STORAGE로 대조. 2026-08-21부터 `setup-dicom`이 "
               "서버 등록 Update와 같은 시점에 이 값을 확정하므로, 회귀에서는 이 "
               "항목이 UI를 건드리지 않고 통과하는 것이 정상이다(changed=False).")
    # 전송이 시작되면 작업 사본 행이 늘어나므로 **여기서도 설정 행만** 센다.
    return outcome["ok"] and len(ds.active_storage_rows(ctx.db)) == 1


QUEUE_STATE_DONE = 7          # DICOM_STORAGE_QUEUE.State (2026-08-18 실측)

# Queue 행이 영상인지 Dose SR 인지 가른다 (2026-08-20 실측).
#   영상 : DataType 이 1 이 아니고 InstanceKey / InstanceUID 가 실제 값
#   RDSR : DataType = 1, InstanceKey = -1, InstanceUID = NULL
# 이 환경(Demo F8 가상 촬영)에서는 RDSR 행이 **항상 State=3 으로 남는다** — 여러
# 실행에서 반복 확인했다(Key 32/35/38). RDSR 생성 조건이 성립하지 않기 때문이고
# 제품 결함이 아니다(WF_06 과 같은 판단).
QUEUE_DATATYPE_DOSE_SR = 1


def is_dose_sr_row(row):
    """Queue 행이 Dose SR 인가."""
    return (int(row.get("DataType") or 0) == QUEUE_DATATYPE_DOSE_SR
            and not row.get("InstanceUID"))

# DICOM Conformance Statement V1.3W1 Proposed Presentation Context Table
SOP_CLASS_MG = "1.2.840.10008.5.1.4.1.1.1.2"      # Digital Mammography X-Ray Image
SOP_CLASS_DBT = "1.2.840.10008.5.1.4.1.1.13.1.3"  # Breast tomosynthesis Image
SOP_CLASS_RDSR = "1.2.840.10008.5.1.4.1.1.88.67"  # X-Ray Radiation Dose SR


def wait_queue_registered(ctx, before, wait=30, poll=1.0):
    """이번 전송이 **Queue 에 올라올 때까지** 기다리고 새 Key 를 돌려준다.

    Send 를 누른 직후에는 아직 Queue 행이 없을 수 있다. 바로 조회하면 빈 목록이
    되어 "전송이 등록되지 않았다" 로 오판한다.
    """
    end = time.time() + wait
    added = []
    while True:
        added = sorted(queue_keys(ctx) - before)
        if added or time.time() >= end:
            return added
        time.sleep(poll)


def wait_queue_settled(ctx, keys, wait=60, poll=1.5):
    """Queue 항목이 **전부 Done 이 될 때까지** 기다린 뒤 상태를 확정한다.

    수신 객체가 다 도착해도 **Queue 의 `State` 갱신은 조금 늦을 수 있다.**
    2026-08-26 회귀에서 `WF_05`/`WF_06` 이 이렇게 FAIL 했다 — 3건 중 둘은
    `State=7`(Done)인데 마지막 하나가 아직 `State=1` 인 채로 판정됐다.
    **수신 객체 자체는 정상**이었고, 픽스처에 3D-W 를 넣어 전송 객체가 늘면서
    드러난 것이다.

    고정 대기를 늘리는 대신 **상태를 보고 기다린다**(운영 지침 1절). 다 끝나면
    즉시 빠져나오므로 정상 회차가 느려지지 않고, 끝내 안 끝나면 그 상태 그대로
    돌려주어 **무엇이 안 끝났는지 판정에 남는다.**
    """
    if not keys:
        return {}
    wanted = set(keys)
    end = time.time() + wait
    states = {}
    while True:
        states = {int(row["Key"]): int(row["State"]) for row in ctx.db.query(
            "DATA", "SELECT [Key],State FROM DICOM_STORAGE_QUEUE")}
        if all(states.get(k) == QUEUE_STATE_DONE for k in wanted):
            return states
        if time.time() >= end:
            return states
        time.sleep(poll)


def send_and_verify(ctx, ui, r, patient_id, scope="selected",
                     expect_count=None, expect_types=None, wait=90,
                     step_queue=3, step_receive=4, step_tags=5, sender=None):
    """전송 1회를 수행하고 개정본 Step 3~5를 각각 판정한다.

    개정본 `TC_Basic_WorkFlow_04`의 Expected는 세 가지를 따로 요구한다.
      Step 3. Queue 상태가 Done으로 표시된다.
      Step 4. Storage SCP에 **2D 객체 1개**가 수신된다(개수까지 명시).
      Step 5. 원본과 수신 객체의 **Patient ID / Study·Series·SOP Instance UID**가
              일치한다(네 개 태그).
    한 판정으로 묶으면 어디가 틀렸는지 리포트에서 구분되지 않으므로 나눈다.

    `expect_count`가 주어지면 **정확히 그 개수**를 요구한다. 이전 구현은 ">=1건"만
    봐서 Selected와 All의 차이를 검증하지 못했다.
    """
    # 초기화를 **끈 경우에도 개수 판정이 정확**하도록, 전송 전 우리 환자의 객체를
    # 기록해 두고 아래에서 **새로 생긴 것만** 센다. 지운 경우에는 이 집합이 비어
    # 있어 아무 영향이 없다(2026-08-27: 공유 SCP 라 전체 삭제를 줄이려고 넣었다).
    cleared = clear_received(ctx)
    before_uids = set()
    if cleared is None:
        before_uids = {o.get("SOPInstanceUID")
                       for o in (received(ctx, patient_id) or [])
                       if o.get("SOPInstanceUID")}
    before_queue = queue_keys(ctx)
    try:
        # `sender` 를 주면 그 경로로 보낸다. **Dose SR 을 보는 TC 는 반드시
        # `flows.send_examined_study`(Examined 모드)를 넘겨야 한다** — 사양서1 이
        # "Examine/View 모드에서 Send 를 클릭했을 때는 Dose SR 을 전송하지 않는다"
        # 고 못박기 때문이다(`send_examined_study` 주석의 인용 참고).
        sent = (sender(scope) if sender
                else flows.send_current_study(ui, scope=scope))
    except Exception as exc:
        r.add(step_queue, f"전송 범위 '{scope}' 선택 후 전송", FAIL,
              expected=f"Send 후 범위 대화상자에서 '{scope}' 선택", actual=str(exc))
        return None

    # **전송이 끝난 뒤에 수신을 센다.** 순서가 중요하다 — 2026-08-26 실측:
    # 수신 안정을 먼저 보니 `received_objects=1` 로 확정됐는데, 같은 회차에서
    # 곧바로 다시 조회하면 4건이었다. 전송이 아직 진행 중인데 서명이 잠깐
    # 멈춘 것을 "안정" 으로 본 것이다. Queue 가 전부 Done 이면 제품이 보낼 것을
    # 다 보낸 것이므로, 그때 수신을 세면 조급하게 끊기지 않는다.
    new_queue = wait_queue_registered(ctx, before_queue)
    states = wait_queue_settled(ctx, new_queue, wait=max(30, int(wait)))
    arrived = wait_received_stable(ctx, patient_id, wait=wait)
    # 초기화를 껐다면 이전 회차 객체가 섞여 있다. 이번 전송분만 남긴다.
    # `expect_count`가 없는 WF_06은 같은 검사를 같은 SOP Instance UID로
    # 재전송한다. 공유 SCP가 기존 파일을 갱신하면 UID 집합은 늘지 않으므로 이를
    # 무조건 `before_uids`로 빼면 Queue가 모두 Done이어도 수신 0건으로 오판한다
    # (2026-09-01 라이브 재현). 정확한 신규 개수를 검증하는 WF_04/WF_05만
    # 전송 전 UID를 제외하고, WF_06은 Queue Done으로 이번 전송을 확인한 뒤 현재
    # 수신 객체 자체의 태그와 RDSR을 판정한다.
    objects = ([o for o in arrived
                if o.get("SOPInstanceUID") not in before_uids]
               if before_uids and expect_count is not None else arrived)

    identity = db_identity(ctx, patient_id)
    if expect_count is None:
        # WF_06의 고정 Patient ID에는 공유 SCP에 과거 실행 Study도 누적된다.
        # 이번 로컬 DB에 존재하는 Study만 판정해야 과거 영상/RDSR이 현재 전송의
        # 식별 Tag 비교에 섞이지 않는다. Queue Done은 위에서 별도로 확인한다.
        objects = [o for o in objects
                   if o.get("StudyInstanceUID") in identity["study_uids"]]

    # --- Step 3: Queue 등록과 Done 상태 --------------------------------
    added_states = {k: states.get(k) for k in new_queue}
    done = [k for k, v in added_states.items() if v == QUEUE_STATE_DONE]
    r.assert_true(
        step_queue, "DICOM 창 Queue 모드에서 전송 상태 확인",
        bool(new_queue) and len(done) == len(new_queue),
        expected=f"이번 전송 항목이 Queue에 등록되고 전부 State={QUEUE_STATE_DONE}"
                 "(Done)",
        actual={"scope": sent, "queue_added": new_queue,
                "states": added_states, "done": done},
        note="DATA.DICOM_STORAGE_QUEUE.State로 대조. 개정본 Expected 3.")

    # --- Step 4: 수신 객체 개수 ----------------------------------------
    detail = {
        "received_objects": len(objects),
        "received_patient_ids": sorted({o.get("PatientID") for o in objects}),
        "received_modalities": sorted({o.get("Modality") for o in objects}),
        "received_sop_classes": sorted({o.get("SOPClassUID") for o in objects}),
    }
    if expect_count is None:
        count_ok = bool(objects)
        count_expected = "수신 객체 >=1건"
    else:
        count_ok = len(objects) == expect_count
        count_expected = f"수신 객체 정확히 {expect_count}건"
    r.assert_true(
        step_receive, "Storage SCP에서 수신 객체 확인", count_ok,
        expected=count_expected, actual=detail,
        note="Queue 상태가 아니라 **실제 수신 파일**을 파싱해 센다. 개수가 더 늘지 "
             "않고 안정될 때까지 기다린 뒤 확정한다(운영 지침 2절).")

    # --- Step 5: 식별 Tag 4개 비교 -------------------------------------
    #
    # **Dose SR(RDSR)은 영상 UID 대조에서 뺀다.** 영상이 아니라 제품이 검사 단위로
    # 만드는 보고서라 `DATA.INSTANCE` 에 행이 없다 — 사양서1: *"Dose SR 에서 사용
    # 시, 내부적으로 영상의 Instance UID 마지막에 '.1.1' 을 붙이기 때문에"*.
    # 그대로 대조하면 Study UID + '.1.1' 이 "DB 에 없는 UID" 로 잡혀 FAIL 한다
    # (2026-08-27 실측). RDSR 자체는 호출부(WF_06)가 Patient ID / Study UID 로
    # 따로 판정한다 — 개정본 WF_06 Step 5 가 그렇게 요구한다.
    image_objects = [o for o in objects
                     if o.get("SOPClassUID") != SOP_CLASS_RDSR]
    dose_sr_objects = [o for o in objects
                       if o.get("SOPClassUID") == SOP_CLASS_RDSR]
    got = {
        "PatientID": {o.get("PatientID") for o in image_objects if o.get("PatientID")},
        "StudyInstanceUID": {o.get("StudyInstanceUID") for o in image_objects
                             if o.get("StudyInstanceUID")},
        "SeriesInstanceUID": {o.get("SeriesInstanceUID") for o in image_objects
                              if o.get("SeriesInstanceUID")},
        "SOPInstanceUID": {o.get("SOPInstanceUID") for o in image_objects
                           if o.get("SOPInstanceUID")},
    }
    mismatch = {
        "PatientID": sorted(got["PatientID"] - {identity["patient_id"]}),
        "StudyInstanceUID": sorted(got["StudyInstanceUID"] - identity["study_uids"]),
        "SeriesInstanceUID": sorted(got["SeriesInstanceUID"] - identity["series_uids"]),
        "SOPInstanceUID": sorted(got["SOPInstanceUID"] - identity["sop_uids"]),
    }
    tags_ok = bool(image_objects) and not any(mismatch.values())
    r.assert_true(
        step_tags, "원본과 수신 객체의 식별 Tag 비교", tags_ok,
        expected=f"Patient ID / Study·Series·SOP Instance UID 4개가 모두 "
                 f"{patient_id}의 DB 값과 일치 (영상 객체 기준, Dose SR 제외)",
        actual={"received": {k: sorted(v) for k, v in got.items()},
                "not_in_db": mismatch,
                "dose_sr_excluded": len(dose_sr_objects)},
        note="DATA의 PATIENT/STUDY/SERIES/INSTANCE와 대조. 개정본 Expected 5가 "
             "요구하는 네 개 태그 전부를 본다.")

    # --- Step 5-b: Station Name (사양: From Config) ----------------------
    #
    # 2026-08-26 추가. 사용자가 "MWL 로 만든 환자의 station 값이 잘 send 되는지"
    # 확인하고 싶어 했는데, **사양은 그렇지 않다고 정한다** — MWL 의 Station Name
    # 은 MWL List 표시에만 쓰이고, 전송 객체에는 Setting 값이 실린다
    # (`configured_station_name` 주석의 사양 인용). 그래서 판정을
    # "Setting 값과 같은가" 로 세운다. MWL 값이 여기 나오면 그것이 결함이다.
    station_expected = configured_station_name(ctx)
    station_received = sorted({(o.get("StationName") or "").strip()
                               for o in objects})
    detail["received_station_names"] = station_received
    detail["configured_station_name"] = station_expected
    if not station_expected:
        r.add(step_tags, "수신 객체의 Station Name", SKIP,
              expected="Setting > General > DICOM 의 Station Name",
              actual=f"설정값이 비어 있어 대조 대상이 없다 "
                     f"(수신값: {station_received})",
              note="사양서2 `Station Name (0008,1010) 3 VNAP From Config` — "
                   "Type 3/VNAP 이라 설정이 비면 값이 없는 것이 정상이다. "
                   "실제로 확인하려면 Setting > General > DICOM 에 값을 넣는다.")
    else:
        r.assert_true(
            step_tags, "수신 객체의 Station Name",
            bool(objects) and station_received == [station_expected],
            expected=station_expected, actual=station_received,
            note="사양서2 `Station Name (0008,1010) 3 VNAP From Config`, "
                 "그리고 MWL 절 \"Worklist에 표기된 Station Name은 MWL List에서만 "
                 "사용된다. 그 외의 Station Name은 Setting > General > DICOM에 "
                 "설정된 Station Name을 사용한다\". **MWL 오더의 값이 여기 나오면 "
                 "사양 위반이다.**")

    detail.update({"queue_added": new_queue, "tag_mismatch": mismatch})
    if expect_types is not None:
        detail["instance_types_in_db"] = {
            k: len(v) for k, v in sorted(identity["by_type"].items())}
    return detail


# INSTANCE.InstanceType (이 저장소 전반에서 쓰는 값)
INSTANCE_2D = 0
INSTANCE_RAW = 1
INSTANCE_RECON = 2
INSTANCE_SYN = 3
INSTANCE_NAMES = {0: "2D", 1: "Raw", 2: "Recon", 3: "Syn"}

# 3D 검사에서 **네트워크로 실제 전송되는** InstanceType.
#
# 근거 1 (사양서 명문) - `(사양서) Bellalun Viewer 사양서1` **125쪽**,
#   SRS 06-30-30(Storage) 문맥:
#     "3D 영상은 Recon 영상이 전송된다. Recon 영상이 없을 경우 영상은 전송되지
#      않는다."
#   체크리스트 WF_05 Test Data가 "Recon 영상만 전송 여부는 검증 버전 사양 추가
#   확인 필요"라고 남긴 의문의 답이 이 문장이다. `core.specs`로 사양서를 검색해
#   찾았다(2026-08-19).
#
# 근거 2 (DICOM 선언) - DICOM Conformance Statement V1.3W1 "Proposed Presentation
#   Context Table": 네트워크 Storage SCU가 선언한 Abstract Syntax는 Digital
#   Mammography X-Ray Image Storage **- For Presentation**, Breast tomosynthesis
#   Image Storage, X-Ray Radiation Dose SR Storage 세 가지다.
#   **For Processing(1.2.840.10008.5.1.4.1.1.1.1)은 문서 전체에 선언돼 있지 않다**
#   (grep 0건). Raw(투영영상)는 For Processing 계열이라 전송 대상이 아니다.
#
# 근거 3 (실측) - 2026-08-19: All Images 전송 후 수신 객체를 SOP Instance UID로
#   DB와 대조하니, DB에 InstanceType 0/1/2/3이 각 1건인데 수신은 **2D(0)와
#   Recon(2)** 두 건이었다. 수신 SOP Class는 ...1.1.1.2 와 ...13.1.3 두 종뿐이다.
#
# 세 근거가 일치한다. 3D 중 전송되는 것은 **Recon만**이다.
SENDABLE_3D_TYPES = (INSTANCE_RECON,)
