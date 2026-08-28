# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: 자동화 구조 리팩터링과 실행 속도 개선(이번 세션 핵심) + `WF_10`/주 모니터 안전장치/NEXT_WORK P0 개별 검증
- 완료한 작업(이번 세션):
  - 정적 검사 전부 통과 확인 — `py_compile`, `check_module_attrs`(기존 `install_package_flow.py:310` 경고는 범위 밖, 무수정), `check_self_attrs`, `check_cleanup_stop`, `check_regression_names`, `traceability`(TC 37건/인용 73건 전부 일치), 단위시험 89건 전부 PASS
  - `portability-check` 통과 확인 — 관리자 권한 True, 1920x1080/100% DPI, DB 서비스 RUNNING
  - **병목 실측**: 최근 26차 전체 회귀 리포트(`Reports/Result_20260826_202818.json`, 96.3분/27 TC)의 TC별·Step별 `duration_seconds`를 분석해 실제 병목 순위를 확보함(추측이 아니라 실측 로그 기반).
    - TC 총시간 순위(내림차순): WF_14 1068s(FAIL, 조사 대상) > WF_03 500s > XIPL_07 424s > WF_13 348s > WF_02 324s > XIPL_04 319s > WF_09 269s > WF_10 231s > WF_07 210s > XIPL_05 206s ...
    - `flows.demo_acquire_step(settle=14)` 기본값(고정 14초 `time.sleep`)이 실제로 남아있는 곳은 **`tests/workflow07.py:230`(WF_07, 회귀 포함)과 `tests/xipl_flows.py:1181/1185/1187`(XIPL_04, 회귀 포함)**이다. `tests/system_compat.py:207`(`run-sys3d`, 명시적 settle=20)과 `tests/ui_flows.py:206`(`run-ui`/`run-auto`)은 **회귀에 포함되지 않는 별도 명령**이다.
    - `tests/workflow02.py`(WF_02)는 이미 `demo_acquire_step(..., settle=0)` + DB 폴링(`_wait_types`, 2초 간격, 상태 기반)으로 리팩터링되어 있었다 — `NEXT_WORK.md`의 "WF_01/WF_02에 settle=14가 남아있다"는 서술은 **더 이상 사실이 아니다(구식)**. WF_02의 남은 소요시간(Step 5 3D 생성 26초 등)은 고정 대기가 아니라 제품 3D 재구성 자체의 실측 처리 시간으로 보인다.
    - `tests/workflow07.py:230`은 F8 촬영 직후 자체 DB 폴링(최대 60초, 2초 간격, INSTANCE COUNT)으로 완료를 재확인하므로, 그 앞의 고정 14초 sleep은 이 호출부에서는 이론상 중복이다(폴링이 실제 완료 시점을 어차피 다시 확인함). 단, `demo_acquire_step`은 `core/flows.py`의 공용 함수라 다른 호출부(`xipl_flows.py`)는 후속 DB 폴링 없이 고정 sleep에만 의존하고 있어, 공용 함수의 기본값을 바꾸면 그쪽은 안전망이 없다 — **콜사이트별 안전성이 다르므로 공용 함수 시그니처를 신중히 설계해야 함**.
  - `run-wf10` 1회 실행 시도 → 코드 실행 전에 환경 차단으로 실패(아래 알려진 문제).
- 진행 중 작업: 없음(환경 차단으로 대기)
- 남은 작업: (환경 정상화 후) `demo_acquire_step`을 상태 신호 기반 대기로 전환(DB 접근이 필요한 구조 변경 — 함수가 현재 `ui`만 받고 `db`/`ctx`를 받지 않음, 콜사이트별 안전성 확인 필요) → `run-wf07`/`run-xipl-04` 변경 전후 시간 비교 → `run-wf10` 매핑·Step 실측 → 주 모니터 밖/안 `cold_start` 검증 → `WF_04→06`·`WF_13`·`WF_15`·`XIPL_05` 개별 재검증 → 전체 회귀 재실행
- 중요한 설계 결정: (이전 세션 결정 유지) 비기본 Procedure로 거짓 PASS 방지; Viewer 창 강제 이동 대신 안전 중단. (이번 세션) sleep 값을 추측으로 줄이지 않고, 실측 데이터로 확인된 안전한 콜사이트부터 상태 기반 대기로 전환하는 방향으로 설계 — 아직 코드 변경 없음(검증 수단이 없어 보류)
- 변경 파일: 없음(이번 세션은 조사·측정만 수행, 코드/문서 변경 없음). 이전 세션 변경분(`core/flows.py`, `tests/workflow10.py`, `_login_check.py` 등)은 그대로 미검증 상태.
- 알려진 문제: **작업 PC의 Windows 세션이 잠금 화면 상태**(foreground window: "Windows 기본 잠금 화면", pid 17064) — `run-wf10` 실행 시 "비밀번호 입력 전에 Viewer 를 최전면으로 올리지 못했습니다(가린 창: Windows 기본 잠금 화면)"로 즉시 중단됨. 이 세션에서는 화면 잠금 해제를 시도하지 않았다(자격증명 필요, 범위 밖). **화면 잠금이 해제되기 전까지 모든 UI 자동화(WF_10 검증, 주 모니터 안전장치 검증, NEXT_WORK P0 재검증, 리팩터링 변경 후 실측)가 차단된다.**
- 다음 세션(또는 화면 잠금 해제 후)에서 시작할 작업: 먼저 foreground window가 잠금 화면이 아닌지 확인 → `_login_check.py`로 로그인 스모크 확인 → `run-wf10` 실행 → 위 "남은 작업" 순서대로 진행
