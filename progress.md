# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: `NEXT_WORK.md` P0 #1(`wait_new_group` 전환 라이브 재검증)을 **다른 PC에서**
  끝내고, 나머지 P0 개별 검증으로 넘어간다.

- 실행 환경(이번 세션에 바뀐 것): 이식성 시험을 겸해 **다른 PC**로 옮겨 수행했다
  (`HOST=ADMIN`, 프로필 `C:\Users\ksj74`, Python 3.12.10). 이전 PC를 막던
  **화면 잠금·원인 불명 로그인 실패는 이 PC에서 재현되지 않았다.**
  `portability-check` PASS(관리자 True / 1920x1080 / 96DPI / 필수 경로 4종 /
  `MSSQL$BELLALUN` RUNNING), `EnumWindows`에 잠금 화면 창 없음, DICOM 서버
  5개 포트(11116/5003/5000/8000/11113) 모두 도달, `cold_start` 로그인 정상.

- 완료한 작업(이번 세션):
  - **P0 #1 라이브 재검증 완료.** 26차 회귀와 **판정이 동일**하고 바뀐 구간만 빨라졌다.
    - `WF_07`: PASS 11/11 (`Reports/Result_20260831_085640.json`).
      Step 4 **23.1초 → 12.9초 (−10.2초)**.
    - `TC_XIPL_compatibility_04`: 전 Step PASS (`Reports/Result_20260831_085032.json`).
      Step 6 **144.7초 → 99.1초 (−45.6초)**. `wait_new_group` 실측 대기 2.8초로
      2026-08-24 실측치(2.8~2.9초)와 일치.
  - **전환이 드러낸 결함 1건을 고쳤다.** `XIPL_04`가 Step 5 직후
    `View Position dialog did not open`으로 재현성 있게 실패했다. 원인은
    `core/viewer_processing.add_view_position`에 2026-08-24부터 있던 재시도(촬영 직후
    `+` 클릭이 삼켜지는 증상)가 **같은 클릭을 재시도 없이 하던
    `tests/xipl_flows._add_view_position_by_alias`** 에는 없었던 것이다. 고정 대기 14초가
    우연히 가려 주고 있었다. 재시도를
    `core/viewer_processing.open_view_position_dialog`로 뽑아 두 콜사이트가 같은 것을
    쓰도록 합쳤고, 재실행에서 두 TC 모두 PASS를 확인했다.
  - 이식성 관찰: `reset-environment`가 복원하는 기준 스냅샷에 **DICOM 서버 등록이 없다**
    (`DICOM_STORAGE` 0행). 전체 회귀는 복원 직후 `DICOM_Server_Setup`이 이 전제를
    만들지만 **TC 단독 실행에는 그 단계가 없어** 복원 직후 `run-wf07`이
    `{'storage': None}`으로 FAIL 했다 — `setup-storage` 선행이 필요하다. `README.md`
    "다른 PC로 옮길 때"에 반영했다. DB 데이터 파일이 없는 PC에서도 `.bak`의
    `WITH MOVE` 복원이 정상 동작했다.
  - 문서 갱신: `../프로젝트_상세.md`(6.4절 실측 표 + "클릭이 삼켜짐" 교훈, 13.1 표 8·13번)
    → `tools/render_docs.py` 재생성 → `README.md`(단독 실행 전제) → `NEXT_WORK.md`
    (1절/2-C절 신설/3절 #4·#12/4절 P0/5절 ⑥/6절 프롬프트).

- 진행 중 작업: 없음.

- 남은 작업(다음 세션 시작점):
  1. **사용자 결정 먼저** — `NEXT_WORK.md` 5절 ⑥ `close_examine` no-dialog 경로를
     고칠지. 공용 코드라 결정 없이 바꾸지 않았다.
  2. `WF_14` 간헐 진입 실패 재현율 — `reset-environment` 후 `run-wf14` 연속 3회(3-C).
  3. `run-wf10` 비기본 Procedure 매핑 실측(DB `HOSPITAL_CODE.MappingKey` /
     `STUDY.ProcedureKey` / `PROCEDURE_ITEMS` 교차 확인).
  4. 주 모니터 **밖**에서 `cold_start` 안전 중단 확인(안쪽 정상 로그인은 이번에 확인됨).
  5. `WF_04→06`·`WF_13`·`WF_15`·`XIPL_05` 개별 재검증.
  6. 전체 회귀 재실행(위가 모두 끝난 뒤).

- 중요한 설계 결정:
  - **DB 행 도착은 "다음 UI 조작을 받을 준비"까지 보장하지 않는다.** 고정 대기를 상태
    기반 대기로 바꿀 때는 대기 직후의 첫 UI 조작이 재시도를 갖고 있는지 함께 봐야 한다
    — 이번에 `XIPL_04`가 정확히 그 이유로 실패했다.
  - 재시도 공용화는 **진짜 같은 클릭·같은 실패 모드**일 때만 했다(`+` 버튼 1171 두
    콜사이트). `close_examine`은 팝업 없이 정상 종료되는 경로가 따로 있어 합치지 않았다.
  - `close_examine`을 추측으로 고치지 않았다. 판별 수단을 실측해 보니 **Close(2204)는
    Examine이 아닌 화면에서도 `visible=True`** 라 쓸 수 없고, 상태 배너(2202)는 커스텀
    드로잉이라 OCR이 필요하다. 재현율 1/3인 상태에서 공용 종료 로직을 바꾸는 대신
    근거와 선택지를 `NEXT_WORK.md` 5절 ⑥에 남겼다.

- 변경 파일: `core/viewer_processing.py`(`open_view_position_dialog` 신설,
  `add_view_position`이 위임), `tests/xipl_flows.py`(`_add_view_position_by_alias`가
  공용 함수 사용), `../프로젝트_상세.md`(+렌더링 `.html`), `README.md`, `NEXT_WORK.md`,
  `progress.md`.

- 알려진 문제:
  - **`WF_07` Step 5(검사 종료)가 1회 실패했다 — 재실행 2회는 PASS(재현율 1/3).** 증거
    캡처(`Evidence/Flow/07_Emergency/04_closed.png`)에 Close 버튼 위 툴팁
    ("Send & Close")만 뜨고 검사는 Examine에 남아 `STUDY.StudyStatus=1`이 유지됐다 —
    `+` 클릭과 같은 "클릭이 삼켜짐" 계열이다. 고정 대기를 걷어내 Close 클릭이 약 10초
    앞당겨지면서 확률이 올라간 것으로 본다(단정 아님). → `NEXT_WORK.md` 5절 ⑥.
  - 이 PC에는 UPS 장치가 없어 Viewer 상태바에 `Failed to communication with UPS.`가
    상시 표시된다. TC 판정에는 영향이 없었다.
  - `WF_07` Step 7(전송 영상 수신 확인)이 7.6초 → 40.2초로 늘었다(네트워크·Storage SCP
    응답 차이로 보임, 판정은 PASS 동일).
  - 이전 PC의 화면 잠금 문제(`NEXT_WORK.md` 3-D)는 **해소가 아니라 PC를 옮겨 회피**한
    것이다. 그 PC로 돌아가면 다시 유효하다.
