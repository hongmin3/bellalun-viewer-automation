# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: 자동화 구조 리팩터링과 실행 속도 개선(이번 세션 핵심) + `WF_10`/주 모니터 안전장치/NEXT_WORK P0 개별 검증
- 완료한 작업(이번 세션):
  - 정적 검사 전부 통과 확인 — `py_compile`, `check_module_attrs`(기존 `install_package_flow.py:310` 경고는 범위 밖, 무수정), `check_self_attrs`, `check_cleanup_stop`, `check_regression_names`, `traceability`(TC 37건/인용 73건 전부 일치), 단위시험 89건 전부 PASS(각 코드 변경 단위마다 재확인)
  - `portability-check` 통과 확인 — 관리자 권한 True, 1920x1080/100% DPI, DB 서비스 RUNNING
  - **병목 실측**: 26차 전체 회귀 리포트(96.3분/27 TC)의 TC별·Step별 `duration_seconds`를 분석해 실제 병목 순위를 확보(추측이 아니라 실측 로그 기반). `NEXT_WORK.md`의 "WF_01/WF_02에 settle=14 고정 대기가 남아있다"는 서술이 구식임을 확인 — WF_02는 이미 상태 기반 폴링으로 전환돼 있었고, 회귀에 실제로 남아 있던 고정 대기는 `WF_07`과 `XIPL_04` 뿐이었다.
  - **`core/flows.py`에 공용 상태 대기 헬퍼 추가**: `instance_type_counts(db, study_key)` / `wait_instance_types(db, study_key, required, timeout, poll)`. `tests/workflow02.py`와 `tests/system_compat.py`가 각자 들고 있던 동일한 `_instance_counts`/`_wait_types` 구현(SQL·폴링 로직 100% 동일)을 이 공용 함수 위임으로 교체 — **동작 변경 없는 기계적 중복 제거**(diff로 로직 동일성 확인, `system_compat.py`의 이제 안 쓰는 `import time` 제거). 위험이 없어 별도 라이브 검증 없이 정적 검사·단위시험만으로 커밋.
  - **`WF_07`/`XIPL_04`의 고정 대기 → 상태 기반 대기 전환**: `core/viewer_processing.wait_new_group`(이미 존재, 단위시험 있음, `TC_XIPL_compatibility_07`이 이미 실사용 중이며 2026-08-24 실측으로 검증된 함수 — 2D 2.8~2.9초/3D-N 29.5초/3D-W 39.7초)을 재사용해 두 곳에 적용했다.
    - `tests/xipl_flows.py::compatibility_04`: 기본 등록 Step을 비우는 루프를 XIPL_07이 쓰는 `_acquire_pre_registered_steps(ctx, ui, study_key)` 그대로 재사용하도록 바꾸고, PRESET_FLOW_A/B 촬영도 `demo_acquire_step(..., settle=0)` + `vp.wait_new_group(..., required_types=vp.INSTANCE_TYPES_2D)`로 바꿈. 대기 결과(`wait_a`/`wait_b`)를 Step 6/7 판정의 `actual`에 추가해 교차 확인 근거를 강화.
    - `tests/workflow07.py` Step 4: `demo_acquire_step(ui, 1)`(고정 14초) + 자체 60초 폴링 루프를, `demo_acquire_step(..., settle=0)` + `viewer_processing.wait_new_group(..., required_types=INSTANCE_TYPES_2D, timeout=60)`로 교체. 최종 판정에 쓰는 DB 조회(`SELECT COUNT(*) ... WHERE StudyKey=@k`)는 그대로 유지해 판정 로직 자체는 손대지 않음.
  - `../프로젝트_상세.md`의 관련 절(6.4 "아직 남은 성능 항목", 13.1 남은 문제 표 8번)을 위 실측·변경 내용으로 정정하고 `python tools/render_docs.py`로 `.html` 재생성. `NEXT_WORK.md` 3절 #4, 4절 우선순위를 동기화(P0에 `run-wf07`/`run-xipl-04` 재검증 추가, `run-xipl-04`는 2026-08-28 확인 완료였지만 이번 변경으로 재검증 필요 명시).
  - `run.py run-wf10` 실행 시도 2회 → 코드 실행 전에 환경 차단(Windows 잠금 화면)으로 실패(아래 알려진 문제).
- 진행 중 작업: 없음(환경 차단으로 라이브 검증 대기)
- 남은 작업(화면 잠금 해제 후 최우선 순서):
  1. `run-wf07`, `run-xipl-04`를 실행해 이번에 바꾼 `wait_new_group` 전환의 판정 동일성(특히 XIPL_04는 2026-08-28에 이미 PASS였던 TC라 회귀 확인 필수)과 실제 단축 시간을 확인한다.
  2. `_login_check.py`로 로그인 스모크 확인 → `run-wf10` 매핑·Step 실측(DB `HOSPITAL_CODE.MappingKey`/`STUDY.ProcedureKey`/`PROCEDURE_ITEMS` 교차 확인).
  3. 주 모니터 밖/안 `cold_start` 안전장치 검증.
  4. `WF_04→06`·`WF_13`·`WF_15`·`XIPL_05` 개별 재검증.
  5. 남은 고정 대기(`run-sys3d`, `run-ui`/`run-auto` — 회귀 밖 명령, P2)는 위 항목들 이후 필요시 처리.
  6. 전체 회귀 재실행(위 개별 검증이 모두 끝난 뒤).
- 중요한 설계 결정:
  - (이전 세션 결정 유지) 비기본 Procedure로 거짓 PASS 방지; Viewer 창 강제 이동 대신 안전 중단.
  - (이번 세션) sleep 값을 추측으로 줄이지 않는다. 순수 기계적 중복 제거(동작 불변)는 정적 검사+단위시험만으로 커밋했고, 실제 대기 방식을 바꾸는 변경(`wait_new_group` 도입)은 **이미 다른 TC(XIPL_07)에서 실측·라이브 검증된 동일 함수를 재사용**하는 방식으로만 진행했다 — 새로 발명한 대기 로직이 아니다. 그래도 최종 라이브 재검증은 화면 잠금 때문에 아직 못 했으므로 "완료"로 간주하지 않는다.
- 변경 파일: `core/flows.py`(공용 헬퍼 추가), `tests/workflow02.py`, `tests/system_compat.py`(중복 제거 위임), `tests/xipl_flows.py`, `tests/workflow07.py`(`wait_new_group` 전환), `../프로젝트_상세.md`(+렌더링 `.html`), `NEXT_WORK.md`. 이전 세션 변경분(`core/flows.py`의 주 모니터 안전장치, `tests/workflow10.py`, `_login_check.py`)은 그대로 미검증 상태 유지.
- 알려진 문제: **작업 PC의 Windows 세션이 잠금 화면 상태**(foreground window: "Windows 기본 잠금 화면") — `run-wf10` 실행 시 "비밀번호 입력 전에 Viewer 를 최전면으로 올리지 못했습니다"로 즉시 중단됨. 화면 잠금 해제는 자격증명이 필요한 동작이라 시도하지 않았다. 한 번은 포그라운드 창이 순간적으로 비어(hwnd=0) 잠금 해제로 오인했으나 3초 간격 재확인 결과 계속 잠금 상태였다 — `OpenInputDesktop` 데스크톱 이름("Default")은 잠금 중에도 그대로라 신뢰할 수 없고, 포그라운드 창 타이틀만 판단 기준으로 쓴다. **화면 잠금이 해제되기 전까지 모든 UI 자동화가 차단된다.**
- 다음 세션(또는 화면 잠금 해제 후)에서 시작할 작업: 포그라운드 창 타이틀로 잠금 해제를 확인 → 위 "남은 작업" 1번(`run-wf07`/`run-xipl-04` 재검증)부터 순서대로 진행
