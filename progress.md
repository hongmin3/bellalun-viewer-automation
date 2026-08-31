# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: `WF_14` Step 7 "목록 전 행 열거 완주" 서브체크(9개 문제 페이지) 해결을
  이어가는 중이다. **7/9 완료.** 남은 것은 `qc.scheduler`의 남은 2행 격차 원인 확정,
  `display.overlay` 새 검증 설계, 교차 오염 2곳 + 오탐 1곳이다(`NEXT_WORK.md` 5절 ⑦).

- 이번 세션(2026-09-01)에 새로 한 작업 — **P0 #1 완료: `dicom.tag_mapping`/
  `qc.scheduler`가 fuzzy 매칭으로도 안 풀리던 원인을 라이브로 확정·수정.**
  - 두 페이지의 OCR 잡음 패턴을 `tool.predefined_text`(이미 해결됨)와 직접 비교해
    "끝에 잡음이 붙는" 패턴이 아니라 매 화면 **마지막 행에서만 단어 중간 글자가
    바뀌는**(`"Age"`→`"Aae"`) 다른 종류임을 확인했다.
  - 첫 진단(행 높이 비교로 잘린 행을 가려낸다)은 **라이브 재검증에서 곧바로 틀렸음이
    드러났다** — `core.ui` 의 `GetWindowRect` 는 클리핑된 행도 명목상 크기(35px)
    그대로 보고한다. 재진단으로 행을 감싸는 `ScrollWnd`(뷰포트) rect 와 행 rect 를
    직접 대조해, 마지막 행이 뷰포트 아래로 12px 튀어나와 있음을 확인했다(뷰포트
    bottom=460, 행 bottom=472) — 그 잘린 조각을 OCR 하며 글자가 깨진 것이었다.
  - `core/setting_lists.py`에 `_list_viewport()`/`_confidently_visible()`을 추가해
    `_screen()`이 뷰포트 밖으로 튀어나온 행을 화면에서 빼도록 고쳤다.
  - 라이브 재검증(`run-wf14` 단독, `Reports/Result_20260831_194615.json`):
    `dicom.tag_mapping` **17/17 완전 일치**(해결), `qc.scheduler` 20/23 → **21/23**
    (스크롤이 실제 바닥까지 도달 확인 — 남은 2행은 DB 직접 조회로 `display.overlay`와
    같은 개념 불일치 후보로 재분류, 원인 확정은 다음 세션 P0 #1). 전체 판정은 여전히
    FAIL(원인은 3-A UPS 제품 결함, 회귀 없음), Step 7(c) 비교 행 수 122→128행으로
    더 회복됐다.
  - 단위시험 119 → **128건 OK**, 정적 검사 전부 통과(`tests/install_package_flow.py:310`
    경고는 기존 것).
  - 상세 경위는 `NEXT_WORK.md` 2-F절, `../프로젝트_상세.md` B.28 참고.

- 이번 세션의 운영상 특이사항: 이 작업이 백그라운드 체크포인트 방식(사용량 한도로
  세션이 여러 번 자동 재개됨)으로 진행됐다. 첫 시도에서 `run-wf14`를 harness 의
  Bash 백그라운드(자동 backgrounding)로 돌렸다가 **세션 경계에서 그 백그라운드
  프로세스 자체가 끊겨 유실됐다**(리포트도 로그도 안 남음). 이후 PowerShell
  `Start-Process -WindowStyle Hidden` 으로 완전히 분리된 OS 프로세스로 재실행해
  세션이 재개될 때마다 프로세스 생존 여부/CPU 시간 변화로 진행 상황을 확인했다 —
  이 방식이 성공했다. **교훈: harness 자체의 백그라운드 추적에 기대지 말고, 장시간
  라이브 실행은 처음부터 OS 프로세스로 분리해라**(`NEXT_WORK.md` 6절 프롬프트에 반영).

- 진행 중 작업: 없음(P0 #1 완료, 문서·커밋 마무리 단계).

- 남은 작업(다음 세션 시작점, `NEXT_WORK.md` 6절 프롬프트 참고):
  1. `qc.scheduler`(21/23) 남은 2행 격차의 정체 확인 — DB Gantry 12개 코드 중 화면에
     없는 2개가 정확히 무엇인지 사양서/Service Manual로 대조.
  2. `display.overlay` 새 검증(항목별 추가/미추가 상태 비교) 설계·구현.
  3. 교차 오염 2곳(`procedure.procedure`, `dicom.print_overlay`) + 완전 오탐 1곳
     (`patient.physician`) — 아직 미착수.
  4. `WF_04→06`/`WF_13`/`WF_15` 개별 재검증.
  5. `XIPL_05` 불합격 경계 검증(Fiber 콤보 항목 구성).
  6. 전부 끝나면 전체 회귀 1회 실행.

- 변경 파일(이번 세션): `core/setting_lists.py`(`_list_viewport`/`_confidently_visible`
  신설, `_screen()`에 적용), `tests/test_setting_lists.py`(`ConfidentlyVisibleTest`/
  `ListViewportTest` 신설), `../프로젝트_상세.md`(B.28 신설, +렌더링 `.html`),
  `NEXT_WORK.md`(2-F절 신설, 5절 ⑦·6절 갱신), `progress.md`.

- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/3-B, 간헐 증상 3-C, 남은 열거
  문제는 위 "남은 작업" 1~3). 이 세션에서 새로 발견된 자동화 결함은 없다.
