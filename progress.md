# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: `WF_14` Step 7 "목록 전 행 열거 완주" 서브체크(9개 문제 페이지) 해결을
  이어가는 중이다. **7/9 완료.** 남은 것은 `qc.scheduler`의 남은 2행 격차 원인 확정,
  교차 오염 2곳(`procedure.procedure`/`dicom.print_overlay`) + 완전 오탐 1곳
  (`patient.physician`)이다(`NEXT_WORK.md` 5절 ⑦).

- 이번 세션(2026-09-01)에 새로 한 작업:
  - **P0 #1 완료: `dicom.tag_mapping`/`qc.scheduler`가 fuzzy 매칭으로도 안 풀리던
    원인을 라이브로 확정·수정.** 두 페이지의 OCR 잡음이 "끝에 잡음이 붙는" 게
    아니라 매 화면 마지막 행에서만 단어 **중간** 글자가 바뀌는 다른 종류였다.
    첫 진단(행 높이 비교)은 라이브 재검증에서 곧바로 틀렸음이 드러났다 —
    `GetWindowRect`는 클리핑된 행도 명목상 크기 그대로 보고한다. 재진단으로 행을
    감싸는 `ScrollWnd`(뷰포트) rect와 행 rect를 직접 대조해 마지막 행이 뷰포트
    밖으로 12px 튀어나온 것을 확인했다. `_list_viewport()`/`_confidently_visible()`
    추가. 라이브 검증: `dicom.tag_mapping` **17/17 완전 일치**, `qc.scheduler`
    20/23 → **21/23**(남은 2행은 원인 미확정으로 남김). 상세: `NEXT_WORK.md` 2-F절,
    `../프로젝트_상세.md` B.28.
  - **P0 #2 완료: `display.overlay` — "설계 차이"라던 예전 결론이 틀렸음을 확인,
    실제로는 교차 오염이었다.** 이 페이지엔 독립된 목록이 셋(카탈로그/Top/Bottom)
    있고, `visible_rows()`가 셋을 안 가리고 섞어 "28"을 만들었다(카탈로그 화면표시분
    20 + Top 6 + Bottom 2 = 28 — 카탈로그 진짜 크기가 아니라 우연의 합, Service
    Manual의 진짜 카탈로그는 34개). `procedure.procedure`/`dicom.print_overlay`와
    같은 교차 오염 버그였다. `_collect_overlay()`를 추가해 Top/Bottom 컨트롤만
    `ui.by_id()`로 직접 찾아 훑도록 고쳤다(카탈로그 제외, 기존 `collect()` 재사용).
    라이브 검증: `display.overlay` **8/8 완전 일치**(불완전 목록에서 빠짐). 상세:
    `NEXT_WORK.md` 2-G절, `../프로젝트_상세.md` B.29.
  - 두 수정 모두 `run-wf14` 단독 재실행으로 검증했다(`Reports/Result_20260831_194615.json`,
    `Reports/Result_20260831_204935.json`). 전체 판정은 두 번 다 여전히 FAIL — 원인은
    변함없이 3-A(UPS 설정이 Export/Import로 복원 안 되는 기존 제품 결함), **회귀 없음.**
    Step 7(c) "Setting 목록 행 상세값 복원"도 두 번 다 PASS(달라진 항목 0). 비교 행
    수는 122→128→108로 변했는데, 128→108 감소는 회귀가 아니라 `display.overlay`
    카탈로그의 의미 없는 20행이 비교에서 빠진 것이다(B.29 참고).
  - 단위시험 119 → 128 → **131건 OK**, 정적 검사 전부 통과(`tests/install_package_flow.py:310`
    경고는 기존 것).

- 이번 세션의 운영상 특이사항: 사용량 한도로 세션이 여러 번 자동 재개됐다(체크포인트
  방식). 첫 `run-wf14` 시도를 harness의 Bash 자동 백그라운드에 맡겼다가 **세션 경계에서
  그 프로세스 자체가 끊겨 유실됐다**(리포트도 로그도 안 남음). 이후 두 번의 `run-wf14`
  모두 PowerShell `Start-Process -WindowStyle Hidden`으로 완전히 분리된 OS 프로세스로
  띄워 성공했다 — 세션이 재개될 때마다 프로세스 생존 여부(`Get-CimInstance Win32_Process`)와
  Reports/ 폴더의 새 파일로 진행 상황을 확인했다. **교훈: harness 자체의 백그라운드
  추적에 기대지 말고, 장시간 라이브 실행은 처음부터 OS 프로세스로 분리해라**
  (`NEXT_WORK.md` 6절 프롬프트에 반영).

- 진행 중 작업: 없음(P0 #1·#2 완료, 문서·커밋 마무리 단계).

- 남은 작업(다음 세션 시작점, `NEXT_WORK.md` 6절 프롬프트 참고):
  1. `qc.scheduler`(21/23) 남은 2행 격차의 정체 확인 — **"개념 불일치"로 성급히
     단정하지 않는다**(`display.overlay`가 그렇게 틀렸다, B.29). 라이브로 컨트롤
     트리부터 덤프해 진짜 원인을 확인한다.
  2. 교차 오염 2곳(`procedure.procedure`, `dicom.print_overlay`) — `display.overlay`와
     같은 해법(`ui.by_id()`로 대상 컨트롤 직접 지정)이 통하는지 확인. 완전 오탐 1곳
     (`patient.physician`)도 함께.
  3. `WF_04→06`/`WF_13`/`WF_15` 개별 재검증.
  4. `XIPL_05` 불합격 경계 검증(Fiber 콤보 항목 구성).
  5. 전부 끝나면 전체 회귀 1회 실행.

- 변경 파일(이번 세션): `core/setting_lists.py`(`_list_viewport`/`_confidently_visible`/
  `_collect_overlay` 신설, `_screen()`/`sweep()`에 적용), `tests/test_setting_lists.py`
  (`ConfidentlyVisibleTest`/`ListViewportTest`/`CollectOverlayTest` 신설),
  `../프로젝트_상세.md`(B.28·B.29 신설, +렌더링 `.html`), `NEXT_WORK.md`(2-F·2-G절
  신설, 5절 ⑦·6절 갱신), `progress.md`.

- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/3-B, 간헐 증상 3-C, 남은 열거
  문제는 위 "남은 작업" 1~2). 이 세션에서 새로 발견된 자동화 결함은 없다.
