# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: `WF_14` Step 7 "목록 전 행 열거 완주" 서브체크(9개 문제 페이지) 해결을
  이어가는 중이다. **8/9 완료 — 남은 것은 `qc.scheduler`(21/23) 하나뿐이다.**

- 이번 세션(2026-09-01)에 새로 한 작업 — 문제 있던 9개 페이지 중 8개를 완전히
  해결했다. **핵심 패턴: 넷(display.overlay/procedure.procedure/dicom.print_overlay/
  patient.physician) 다 처음엔 "개념 불일치"나 "오탐"으로 잘못 결론 났다가, 라이브로
  컨트롤 트리를 덤프해 보니 실제로는 같은 종류의 교차 오염(화면에 목적이 다른 목록
  여러 개가 있는데 `visible_rows()`가 구분 없이 다 줍는 문제)이었다.**
  - **`dicom.tag_mapping`/`qc.scheduler`(P0 #1)**: 뷰포트 클리핑이 근본 원인.
    `GetWindowRect`는 클리핑된 행도 명목상 크기 그대로 보고해 첫 진단(행 높이
    비교)은 틀렸다 — 재진단(뷰포트 rect 대조)으로 해결. `dicom.tag_mapping`
    17/17 완전 일치, `qc.scheduler`는 20/23 → 21/23(남은 2행 원인 미확정).
    상세: `NEXT_WORK.md` 2-F절/`../프로젝트_상세.md` B.28.
  - **`display.overlay`(P0 #2)**: 카탈로그/Top/Bottom 세 목록이 섞여 "28"이라는
    잘못된 수치를 만들었다. `_collect_overlay()`로 8/8 완전 일치. 2-G절/B.29.
  - **`procedure.procedure`(P0 #3)**: Procedure 카탈로그(15행)+무관한 View
    Position 약어(4행)가 섞여 19행. `SINGLE_LIST_CONTROL` 매핑으로 15/15 완전
    일치. 2-H절/B.30.
  - **`dicom.print_overlay`/`patient.physician`(P0 #3 마무리)**: 처음엔 "구조가
    복잡해 대응 관계 불명"으로 보류했으나, 라벨 OCR + DB 조회 + 조회성 행 선택만으로
    (데이터 변경 없이) 확정했다. `patient.physician`은 그리드 넷 중 "Performing
    Physician Order"(MWL 역할 매핑)만 걸리고 있었고 진짜 대상 셋(Referring/Reading/
    Performing Physician)은 합쳐서 0=DB(0)와 일치. `dicom.print_overlay`는 Overlay
    이름 목록에서 행을 선택해야 Position 목록 셋이 채워짐을 확인, 선택 후 6=DB(6)와
    일치. `_collect_multi_list()`/`_collect_print_overlay()` 신설로 각각 0/0, 6/6
    완전 일치. **부수적으로 `walk()`가 "행 0개=무조건 실패"로 처리하던 오래된
    결함도 발견**(진짜 DB 0행 페이지가 처음 나오며 드러남) — `expected_count==0`일
    때만 빈 목록을 완전한 열거로 인정하도록 고쳤다. 상세: `NEXT_WORK.md` 2-I절/
    `../프로젝트_상세.md` B.31.
  - 다섯 수정 모두 `run-wf14` 단독 재실행으로 검증했다(`Reports/Result_20260831_194615.json`
    ~ `Result_20260901_010617.json`, 총 5회). 전체 판정은 매번 여전히 FAIL — 원인은
    변함없이 3-A(UPS 설정 미복원, 기존 제품 결함), **회귀 없음.** Step 7(c) "Setting
    목록 행 상세값 복원"도 매번 PASS(달라진 항목 0). 비교 행 수 122→128→108→104→89로
    점점 줄었는데, 이는 회귀가 아니라 의미 없는 비교 대상(카탈로그·엉뚱한 그리드 등)이
    빠진 것이다(B.29~B.31 참고).
  - 단위시험 119 → 128 → 131 → 133 → 140 → **144건 OK**, 정적 검사 전부 통과
    (`tests/install_package_flow.py:310` 경고는 기존 것).

- 이번 세션의 운영상 특이사항: 사용량 한도로 세션이 여러 번 자동 재개됐다(체크포인트
  방식). 첫 `run-wf14` 시도를 harness의 Bash 자동 백그라운드에 맡겼다가 **세션
  경계에서 그 프로세스 자체가 끊겨 유실됐다**(리포트도 로그도 안 남음). 이후
  `run-wf14` 5회 + 짧은 진단 스크립트 여러 회 모두 PowerShell
  `Start-Process -WindowStyle Hidden`으로 완전히 분리된 OS 프로세스로 띄워
  성공했다 — 세션이 재개될 때마다 프로세스 생존 여부(`Get-CimInstance Win32_Process`)와
  Reports/ 폴더의 새 파일로 진행 상황을 확인했다. **교훈: harness 자체의 백그라운드
  추적에 기대지 말고, 장시간 라이브 실행은 처음부터 OS 프로세스로 분리해라**
  (`NEXT_WORK.md` 6절 프롬프트에 반영).

- 진행 중 작업: 없음(P0 #1~#3 완료, 문서·커밋 마무리 단계).

- 남은 작업(다음 세션 시작점, `NEXT_WORK.md` 6절 프롬프트 참고):
  1. `qc.scheduler`(21/23) 남은 2행 격차의 정체 확인 — **넷이나 "개념 불일치/오탐"
     으로 잘못 단정했던 전례가 있으니(B.29~B.31) 추측하지 않는다.** 라이브로 컨트롤
     트리부터 덤프해 무관한 목록이 섞였는지부터 의심한다. 이게 끝나면 "목록 전 행
     열거 완주" 서브체크가 9개 페이지 전부 완료된다.
  2. `WF_04→06`/`WF_13`/`WF_15` 개별 재검증.
  3. `XIPL_05` 불합격 경계 검증(Fiber 콤보 항목 구성).
  4. 전부 끝나면 전체 회귀 1회 실행.

- 변경 파일(이번 세션): `core/setting_lists.py`(`_list_viewport`/`_confidently_visible`/
  `_collect_overlay`/`SINGLE_LIST_CONTROL`/`_collect_multi_list`/`_collect_print_overlay`
  신설, `walk()`의 빈 목록 처리 수정, `_screen()`/`sweep()`에 적용),
  `tests/test_setting_lists.py`(`ConfidentlyVisibleTest`/`ListViewportTest`/
  `CollectOverlayTest`/`SingleListControlTest`/`CollectMultiListTest`/
  `CollectPrintOverlayTest`/`WalkEmptyListTest`/`SweepRoutesPhysicianAndPrintOverlayTest`
  신설), `../프로젝트_상세.md`(B.28~B.31 신설, +렌더링 `.html`), `NEXT_WORK.md`
  (2-F~2-I절 신설, 5절 ⑦·6절 갱신), `progress.md`.

- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/3-B, 간헐 증상 3-C, 남은 열거
  문제는 위 "남은 작업" 1). 이 세션에서 새로 발견된 자동화 결함은 없다(`walk()`의
  빈 목록 결함은 이 세션에서 발견·수정까지 끝났다).
