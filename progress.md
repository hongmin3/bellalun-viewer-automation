# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: `WF_14` Step 7 "목록 전 행 열거 완주" 서브체크(9개 문제 페이지)가
  **전부 완료됐다.** 다음 목표는 나머지 TC 재검증(`run-wf04→06`/`run-wf13`/
  `run-wf15`) → `XIPL_05` 경계 검증 → 전체 회귀 1회다.

- 이번 세션(2026-09-01)에 새로 한 작업 — 문제 있던 9개 페이지를 전부 해결했다.
  **핵심 패턴: 다섯(tag_mapping/display.overlay/procedure.procedure/
  dicom.print_overlay/patient.physician)은 처음엔 "개념 불일치"나 "오탐"으로
  잘못 결론 났다가, 라이브로 컨트롤 트리를 덤프해 보니 실제로는 자동화 결함
  (뷰포트 클리핑 또는 교차 오염)이었다. 마지막 하나(qc.scheduler)만 같은 순서로
  검증했는데도 이번엔 정말로 제품 설계 차이였다.**
  - **`dicom.tag_mapping`(P0 #1)**: 뷰포트 클리핑이 근본 원인. `GetWindowRect`는
    클리핑된 행도 명목상 크기 그대로 보고해 첫 진단(행 높이 비교)은 틀렸다 —
    재진단(뷰포트 rect 대조)으로 17/17 완전 일치. `NEXT_WORK.md` 2-F절/
    `../프로젝트_상세.md` B.28.
  - **`display.overlay`(P0 #2)**: 카탈로그/Top/Bottom 세 목록이 섞여 "28"이라는
    잘못된 수치를 만들었다. `_collect_overlay()`로 8/8. 2-G절/B.29.
  - **`procedure.procedure`(P0 #3)**: Procedure 카탈로그(15)+무관한 View
    Position 약어(4)가 섞여 19. `SINGLE_LIST_CONTROL`로 15/15. 2-H절/B.30.
  - **`dicom.print_overlay`/`patient.physician`(P0 #3 마무리)**: 라벨 OCR +
    DB 조회 + 조회성 행 선택만으로(데이터 변경 없이) 대응 관계를 확정하고
    각각 6/6, 0/0 완전 일치. 부수적으로 `walk()`가 "행 0개=무조건 실패"로
    처리하던 오래된 결함도 발견·수정(`expected_count==0`일 때만 빈 목록을
    완전한 열거로 인정). 2-I절/B.31.
  - **`qc.scheduler`(P0 #1 마무리, 9/9)**: 넷과 달리 이번엔 라이브로 교차 오염
    없음을 먼저 확인한 뒤, 사양서2(SRS) 8492~8511행("일반/-d 모드에서
    Geometry Calibration(Tomo) 항목이 안 보임")과 Service Manual 3749행
    ("연결 모델이 지원 안 하는 QC 항목은 표시 안 됨")으로 **진짜 제품 설계
    차이임을 확정**했다. `ROW_COUNT_QUERIES`에서 이 페이지만 빼서(매핑 없는
    다른 페이지와 같은 처리) 정지·연속 증명만으로 판정하도록 고쳤다. 2-J절/B.32.
  - 여섯 수정 모두 `run-wf14` 단독 재실행으로 검증했다(`Reports/Result_20260831_194615.json`
    ~ `Result_20260901_022050.json`, 총 6회). 전체 판정은 매번 여전히 FAIL —
    원인은 변함없이 3-A(UPS 설정 미복원, 기존 제품 결함), **회귀 없음.**
    Step 7(c) "Setting 목록 행 상세값 복원"도 매번 PASS(달라진 항목 0). 마지막
    실행에서 "불완전 페이지": `[]` — 9개 페이지 전부 정상 판정.
  - 단위시험 119 → 144 → **146건 OK**, 정적 검사 전부 통과
    (`tests/install_package_flow.py:310` 경고는 기존 것).

- 이번 세션의 운영상 특이사항: 사용량 한도로 세션이 여러 번 자동 재개됐다(체크포인트
  방식). 첫 `run-wf14` 시도를 harness의 Bash 자동 백그라운드에 맡겼다가 **세션
  경계에서 그 프로세스 자체가 끊겨 유실됐다**(리포트도 로그도 안 남음). 이후
  `run-wf14` 6회 + 짧은 진단 스크립트 여러 회 모두 PowerShell
  `Start-Process -WindowStyle Hidden`으로 완전히 분리된 OS 프로세스로 띄워
  성공했다. **교훈: harness 자체의 백그라운드 추적에 기대지 말고, 장시간 라이브
  실행은 처음부터 OS 프로세스로 분리해라**(`NEXT_WORK.md` 6절 프롬프트에 반영).

- 진행 중 작업: 없음("목록 전 행 열거 완주" 9/9 완료, 문서·커밋 마무리 단계).

- 남은 작업(다음 세션 시작점, `NEXT_WORK.md` 6절 프롬프트 참고):
  1. 나머지 재검증 — `run-wf04→06`(close_view_study), `run-wf13`(로그인 콤보),
     `run-wf15`(Dose Overlay 전제). `run-xipl-05`/`wf07`/`xipl-04`/`wf10`/`wf14`는
     2026-08-28~09-01 확인 완료.
  2. `XIPL_05` 불합격 경계 검증(Fiber 콤보 항목 구성).
  3. 전부 끝나면 전체 회귀 1회 실행 — 시작 전에 적용한 변경·변경 전후 실행
     시간·판정 동일성·남은 위험·예상 소요 시간·Viewer/화면 준비 조건을 먼저
     보고한다.

- 변경 파일(이번 세션): `core/setting_lists.py`(`_list_viewport`/
  `_confidently_visible`/`_collect_overlay`/`SINGLE_LIST_CONTROL`/
  `_collect_multi_list`/`_collect_print_overlay` 신설, `walk()`의 빈 목록 처리
  수정, `ROW_COUNT_QUERIES`에서 `qc.scheduler` 제거, `_screen()`/`sweep()`에
  적용), `tests/test_setting_lists.py`(관련 테스트 클래스 다수 신설),
  `../프로젝트_상세.md`(B.28~B.32 신설, +렌더링 `.html`), `NEXT_WORK.md`
  (2-F~2-J절 신설, 5절 ⑦·6절 갱신), `progress.md`.

- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/3-B, 간헐 증상 3-C).
  "목록 전 행 열거 완주" 관련 문제는 이번 세션에서 전부 해결됐다. 이 세션에서
  새로 발견된 자동화 결함(`walk()`의 빈 목록 처리)은 발견·수정까지 끝났다.
