# Progress Checkpoint

## 2026-09-03 현재 상태

- **28차 전체 회귀 완료(2026-09-02 20:58~22:53, `Reports/Result_20260902_225334.json`,
  115.3분): PASS 23 / FAIL 2 / MANUAL 2. 자동화 결함 0건.** 남은 FAIL 2건(`WF_14`
  UPS 설정 미복원, `XIPL_03` 3D 파라미터 기본값 복귀)은 전부 이미 알려진 **제품
  결함**이라 완화하지 않는다.
- 2026-09-03: 회귀 진행률을 `work/regression_state.json`에 남기는 Hub/Worker
  연동 착수(커밋 `65d44d5`). `AI-Remote-Control`은 `hongmin3/AI-Remote-Control`
  (GitHub, private, Issue 기반 원격 실행)로 위치를 확인했다 — 이 세션 자체가 그
  Issue(#24)로 디스패치된 것이었다. `background_watch.py`의 실제 소비 로직은
  아직 안 봤다.
- 2026-09-03(이어짐): **P1/P2 완료.**
  - `TC_XIPL_compatibility_07`에 "새 3D Preset이 그 시점 General Default를
    물려받는가" 보강 체크 추가(`probe-preset3d`로 3D-N/3D-W Preset 컨트롤
    ID 실측 → `core/flows.py` 상수화 → `tests/xipl_flows.py`에 add/delete/검증
    헬퍼 신설). `run-xipl-07` 라이브 재검증 Step 1~9 전부 PASS + 새 체크도
    PASS. `automation_scope.json`의 gap 해소로 정정.
  - `run-sys3d`/`run-ui`에 남은 `demo_acquire_step`/`demo_acquire` 고정 대기를
    상태 기반(`wait_new_group`/DB 행 수 대기)으로 전환. 라이브 재검증 판정 동일.
  - `TC_Basic_WorkFlow_13`(계정 권한별 Setting 노출)은 **이미 2026-08-20에
    완전 자동화돼 있었음**을 발견 — docstring/`--help`만 stale이라 문서만
    정정. `run-wf13` 재확인 PASS(56/56).
  - stale 브랜치 `agent/add-next-task-handoff`는 이미 존재하지 않음 확인(지울
    대상 없음).
- 문서 동기화: `../프로젝트_상세.md`(B.34~B.36 추가) → `render_docs.py` →
  `README.md` → `NEXT_WORK.md`(1/2-L~2-N/4/5/6절) → 이 문서 순으로 갱신했다.

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 진행 중 작업: 없음. 개별 TC 검증(P0~P2)은 전부 끝났다.
- 다음 단계: **전체 회귀(`run-regression`)를 사용자에게 물어본 뒤에만 수행**
  (2026-09-03 사용자 명시 요청). 그 전까지 대기.
- 남은 작업(사용자 자료 대기):
  - `Install_01`/`Install_02`는 사용자가 자료(Release Note, OS Build 목록)를
    줄 때까지 건드리지 않음(MANUAL/SKIP 유지).
  - Hub/Worker 연동 후속 — `AI-Remote-Control` 저장소의 `background_watch.py`
    실제 소비 로직 확인, 다음 필요 항목 설계.
- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/XIPL_03, 간헐 증상
  3-B/3-C — 전부 자동화 결함 아님, 회귀 없음).
