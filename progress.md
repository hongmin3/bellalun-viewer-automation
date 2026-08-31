# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: `WF_14` Step 7 "목록 전 행 열거 완주" 서브체크(9개 문제 페이지) 해결을
  이어가는 중이다. **8/9 완료.** 남은 것은 `dicom.print_overlay`/`patient.physician`의
  대응 목록 확정(둘 다 목록 넷 중 무엇이 DB와 대응하는지 불확실)과 `qc.scheduler`의
  남은 2행 격차 원인 확정이다(`NEXT_WORK.md` 5절 ⑦).

- 이번 세션(2026-09-01)에 새로 한 작업:
  - **P0 #1 완료: `dicom.tag_mapping`/`qc.scheduler`** — 뷰포트 클리핑이 근본
    원인이었다. `GetWindowRect`는 클리핑된 행도 명목상 크기 그대로 보고해 첫
    진단(행 높이 비교)은 라이브 재검증에서 틀렸음이 드러났고, 재진단(뷰포트
    rect 대조)으로 해결했다. `dicom.tag_mapping` 17/17 완전 일치, `qc.scheduler`
    20/23 → 21/23(남은 2행은 원인 미확정). 상세: `NEXT_WORK.md` 2-F절/
    `../프로젝트_상세.md` B.28.
  - **P0 #2 완료: `display.overlay`** — "카탈로그 vs 서브셋 개념 불일치, 새 검증
    설계 필요"라던 예전 결론이 틀렸다. 실제로는 카탈로그/Top/Bottom 세 목록이
    한 패널에 섞인 교차 오염이었다(예전 "28"은 카탈로그 크기가 아니라 세 목록의
    우연한 합). `_collect_overlay()`로 Top+Bottom만 훑도록 고쳐 8/8 완전 일치.
    상세: `NEXT_WORK.md` 2-G절/`../프로젝트_상세.md` B.29.
  - **P0 #3 일부 완료: `procedure.procedure`** — `display.overlay`와 같은 종류의
    교차 오염(Procedure 카탈로그 15행 + 무관한 View Position 약어 4행이 섞여
    19행). `SINGLE_LIST_CONTROL` 매핑 + `sweep()` 라우팅으로 대상 컨트롤(id=2560)
    만 훑도록 고쳐 15/15 완전 일치. `dicom.print_overlay`(목록 넷)와
    `patient.physician`(2x2 그리드 넷)은 어떤 목록이 DB와 대응하는지 자체가
    불확실해 이번엔 **조사만 하고 보류**(추측으로 고치지 않음). 상세:
    `NEXT_WORK.md` 2-H절/`../프로젝트_상세.md` B.30.
  - 세 수정 모두 `run-wf14` 단독 재실행으로 검증했다(`Reports/Result_20260831_194615.json`,
    `Result_20260831_204935.json`, `Result_20260831_221745.json`). 전체 판정은
    세 번 다 여전히 FAIL — 원인은 변함없이 3-A(UPS 설정 미복원, 기존 제품 결함),
    **회귀 없음.** Step 7(c) "Setting 목록 행 상세값 복원"도 세 번 다 PASS(달라진
    항목 0). 비교 행 수 122→128→108→104로 변화 — 108→104 감소는 procedure.procedure
    에서 빠진 View Position 약어 4행이고, 회귀가 아니라 의미 없는 비교 대상이
    빠진 것이다(B.29/B.30 참고).
  - 단위시험 119 → 128 → 131 → **133건 OK**, 정적 검사 전부 통과
    (`tests/install_package_flow.py:310` 경고는 기존 것).

- 이번 세션의 운영상 특이사항: 사용량 한도로 세션이 여러 번 자동 재개됐다(체크포인트
  방식). 첫 `run-wf14` 시도를 harness의 Bash 자동 백그라운드에 맡겼다가 **세션
  경계에서 그 프로세스 자체가 끊겨 유실됐다**(리포트도 로그도 안 남음). 이후
  `run-wf14` 3회 + 짧은 진단 스크립트 1회 모두 PowerShell
  `Start-Process -WindowStyle Hidden`으로 완전히 분리된 OS 프로세스로 띄워
  성공했다 — 세션이 재개될 때마다 프로세스 생존 여부(`Get-CimInstance Win32_Process`)와
  Reports/ 폴더의 새 파일로 진행 상황을 확인했다. **교훈: harness 자체의 백그라운드
  추적에 기대지 말고, 장시간 라이브 실행은 처음부터 OS 프로세스로 분리해라**
  (`NEXT_WORK.md` 6절 프롬프트에 반영).

- 진행 중 작업: 없음(P0 #1·#2·#3 일부 완료, 문서·커밋 마무리 단계).

- 남은 작업(다음 세션 시작점, `NEXT_WORK.md` 6절 프롬프트 참고):
  1. `dicom.print_overlay`/`patient.physician` 대응 목록 확정 — 각 목록에 항목을
     하나씩 UI로 추가해 보며 DB 어느 테이블/컬럼이 바뀌는지 실측한다. 대응 관계가
     확정된 뒤에만 범위 제한을 건다(추측 금지).
  2. `qc.scheduler`(21/23) 남은 2행 격차의 정체 확인 — **"개념 불일치"로 성급히
     단정하지 않는다**(`display.overlay`가 그렇게 틀렸다, B.29).
  3. `WF_04→06`/`WF_13`/`WF_15` 개별 재검증.
  4. `XIPL_05` 불합격 경계 검증(Fiber 콤보 항목 구성).
  5. 전부 끝나면 전체 회귀 1회 실행.

- 변경 파일(이번 세션): `core/setting_lists.py`(`_list_viewport`/`_confidently_visible`/
  `_collect_overlay`/`SINGLE_LIST_CONTROL` 신설, `_screen()`/`sweep()`에 적용),
  `tests/test_setting_lists.py`(`ConfidentlyVisibleTest`/`ListViewportTest`/
  `CollectOverlayTest`/`SingleListControlTest` 신설), `../프로젝트_상세.md`
  (B.28~B.30 신설, +렌더링 `.html`), `NEXT_WORK.md`(2-F~2-H절 신설, 5절 ⑦·6절
  갱신), `progress.md`.

- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/3-B, 간헐 증상 3-C, 남은 열거
  문제는 위 "남은 작업" 1~2). 이 세션에서 새로 발견된 자동화 결함은 없다.
