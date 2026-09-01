# Progress Checkpoint

## 2026-09-01 Codex 인계 완료

- Claude 세션 한도 직전 실행한 `setup-dicom -> run-wf06 -> run-wf15` 결과를 복구했다.
  `WF_15`는 PASS였고, `WF_06`은 Queue 4건이 모두 Done인데도 공유 Storage SCP의
  기존 SOP UID를 전부 제외해 수신 0건으로 오판했다.
- `core/send_verify.py`에서 정확한 신규 개수를 요구하는 WF_04/WF_05만 전송 전 UID를
  제외하고, WF_06은 Queue Done을 이번 전송 근거로 삼아 현재 로컬 DB에 존재하는
  Study의 수신 영상/RDSR만 판정하도록 수정했다.
- `tests/workflow06.py`와 `tests/workflow15.py`의 RDSR 판정도 현재 로컬 Study로
  범위를 좁혀, 고정 Patient ID로 누적된 과거 실행 결과가 섞이지 않게 했다.
- 검증: `py_compile` 통과, 단위시험 150건 통과, `run-wf06` 라이브 PASS
  (영상 3건 + RDSR 1건, Queue 4건 Done, 식별 Tag 불일치 0건).
- 다음 작업: `XIPL_05` 경계 검증 후 전체 회귀 1회.

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: `WF_14` Step 7 "목록 전 행 열거 완주" 서브체크(9개 문제 페이지)는
  **전부 완료됐다.** 이어서 나머지 TC 재검증을 시도하던 중 `setup-dicom`의 별개
  결함을 하나 더 발견·수정했다. 다음 목표는 `run-wf01→wf02→wf03`으로 선행 데이터를
  만든 뒤 `run-wf04→06`/`run-wf13`/`run-wf15` 재검증 → `XIPL_05` 경계 검증 →
  전체 회귀 1회다.

- 이번 세션(2026-09-01)에 새로 한 작업:
  - **"목록 전 행 열거 완주" 9개 페이지 전부 해결.** 다섯(tag_mapping/
    display.overlay/procedure.procedure/dicom.print_overlay/patient.physician)은
    처음엔 "개념 불일치/오탐"으로 잘못 결론 났다가 라이브 컨트롤 트리 조사로
    실제 자동화 결함(뷰포트 클리핑 또는 교차 오염)임이 드러났다. 마지막
    하나(qc.scheduler)는 같은 순서로 검증했는데도 이번엔 진짜 제품 설계
    차이(사양서2·Service Manual로 확정)였다. 상세: `NEXT_WORK.md` 2-F~2-J절,
    `../프로젝트_상세.md` B.28~B.32.
  - **`run-wf04→06`/`run-wf13`/`run-wf15` 재검증을 시도하다가 별개 결함 발견·수정.**
    `setup-dicom` 실행 중 "Storage Use 단일 선택" FAIL 관찰 — 이미 꺼 둔
    `BUNNY_TEST` Storage 항목이 실수로 다시 켜졌다. 원인: `core/dicom_settings.py`
    `_sync_use()`가 Storage 목록을 DB와 맞출 때 `SCPUseType` 필터 없이 읽어서,
    전송 작업 사본 행(늘 `Use=1`)이 설정 행의 진짜 상태를 덮어써 "이미 켜져
    있다"로 오판, 화면 체크박스를 반대로 클릭했다(같은 파일에 이미 같은 필터를
    쓰는 곳이 셋 있었는데 이 함수만 빠짐). 필터 추가로 고쳤고, 고치기 전
    정확한 버그 재현 조건에서 재실행해 FAIL→PASS로 바뀌는 것을 라이브로
    확인했다. 상세: `NEXT_WORK.md` 2-K절/`../프로젝트_상세.md` B.33.
  - **`run-wf04`/`run-wf06`/`run-wf15`가 FAIL한 진짜 원인도 확정(자동화 결함
    아님).** `PatientID=DATA_FLOW_MWL_01` 검사를 못 찾아 FAIL했는데, `WF_04`
    체크리스트 Precondition에 "TC_Basic_WorkFlow_03~04가 Pass이다"라고 명시돼
    있다 — 이 데이터는 `WF_03`(선행 체인)이 촬영으로 미리 만들어 둬야 하는데
    이번엔 그 체인 없이 단독 실행해서 없었던 것이다. `run-wf13`은 이런 선행
    데이터가 필요 없어 정상 PASS했다(계정 추가·권한검증·재로그인·원복 전부 정상).
  - 단위시험 119 → 146 → **150건 OK**(`tests/test_dicom_settings.py` 신설
    포함), 정적 검사 전부 통과(`tests/install_package_flow.py:310` 경고는
    기존 것).

- 이번 세션의 운영상 특이사항: 사용량 한도로 세션이 여러 번 자동 재개됐다(체크포인트
  방식). 장시간 라이브 실행은 전부 `Start-Process -WindowStyle Hidden`으로 세션과
  분리된 OS 프로세스로 띄워 안정적으로 진행했다(harness 자체 백그라운드는 세션
  경계에서 한 번 유실된 전례가 있어 그 뒤로 계속 이 방식을 썼다).

- 진행 중 작업: 없음.

- 남은 작업(다음 세션 시작점, `NEXT_WORK.md` 6절 프롬프트 참고):
  1. `run-wf01→wf02→wf03`을 먼저 실행해 `DATA_FLOW_MWL_01` 환자·2D 영상
     (`IMG_FLOW_2D_01`)을 만든 뒤, `run-wf04→run-wf06`(close_view_study 연쇄),
     `run-wf15`(Dose Overlay 전제)를 재검증한다. `run-wf13`은 2026-09-01에
     이미 PASS 확인됐다(재확인만 필요하면 단독 실행 가능, 선행 데이터 불필요).
  2. `XIPL_05` 불합격 경계 검증(Fiber 콤보 항목 구성).
  3. 전부 끝나면 전체 회귀 1회 실행 — 시작 전에 적용한 변경·변경 전후 실행
     시간·판정 동일성·남은 위험·예상 소요 시간·Viewer/화면 준비 조건을 먼저
     보고한다.

- 변경 파일(이번 세션): `core/setting_lists.py`(목록 열거 관련 다수 함수 신설/
  수정 — 2-F~2-J절 참고), `core/dicom_settings.py`(`_sync_use()`에 `SCPUseType`
  필터 추가), `tests/test_setting_lists.py`(관련 테스트 다수 신설),
  `tests/test_dicom_settings.py`(신설), `../프로젝트_상세.md`(B.28~B.33 신설,
  +렌더링 `.html`), `NEXT_WORK.md`(2-F~2-K절 신설, 5절 ⑦·6절 갱신), `progress.md`.

- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/3-B, 간헐 증상 3-C).
  "목록 전 행 열거 완주"·`setup-dicom` Storage 관련 문제는 이번 세션에서 전부
  해결됐다. `run-wf04/06/15`의 FAIL은 자동화 결함이 아니라 선행 데이터 미준비가
  원인임이 확정됐다(위 "남은 작업" 1 참고).
