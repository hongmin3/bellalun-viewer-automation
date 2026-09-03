# Progress Checkpoint

## 2026-09-03 현재 상태

- **28차 전체 회귀 완료(2026-09-02 20:58~22:53, `Reports/Result_20260902_225334.json`,
  115.3분): PASS 23 / FAIL 2 / MANUAL 2. 자동화 결함 0건.** 27차에서 새로 나온
  `WF_08`(3D Print "Select Images" 창 미처리) FAIL을 고친 뒤 이 회귀로 최종 확정했다
  (`core/flows.py`의 `select_images_*` 함수, `tests/workflow08.py` 3D 패스 개편 —
  경위는 `NEXT_WORK.md` 2절 WF_08 행/2-L절, `../프로젝트_상세.md` B.34).
- 남은 FAIL 2건(`WF_14` Step 7 UPS 설정 미복원, `XIPL_03` Step 9 3D 파라미터 기본값
  복귀)은 전부 이미 알려진 **제품 결함**이라 완화하지 않는다.
- 2026-09-03: `run.py` 회귀 루프가 TC마다 `work/regression_state.json`에 진행률을
  남기게 했다(커밋 `65d44d5`) — 외부 `AI-Remote-Control`의 `background_watch.py`가
  Claude를 깨우지 않고 회귀 진행 상황을 읽게 하기 위한 Hub/Worker 연동의 첫 단계
  (경위는 `NEXT_WORK.md` 2-M절, `../프로젝트_상세.md` B.35).
- 같은 날: 위 두 항목을 반영해 `../프로젝트_상세.md`(B.34/B.35 추가, 5.1/5.2절·기준
  시점 갱신) → `render_docs.py` → `README.md`(회귀 수치·코드 규모·추적성 재실측) →
  `NEXT_WORK.md`(1/2-L/2-M/3/4/6절) → 이 문서 순으로 문서를 동기화했다.

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 진행 중 작업: 없음.
- 남은 작업(사용자 승인 후 착수):
  - P1 — `probe-preset3d`로 3D-N/3D-W Preset 컨트롤 실측, `XIPL_07`에 Default 상속
    판정 추가.
  - P2 — `run-sys3d`/`run-ui`(회귀 밖 명령)에 남은 `demo_acquire_step` 고정 대기를
    `wait_new_group`으로 전환할지 판단.
  - Hub/Worker 연동 후속 — `AI-Remote-Control`이 `work/regression_state.json`을 어떻게
    소비하는지는 이 저장소 밖이라 미확인. 그쪽과 맞춰 다음 필요 항목을 정한다.
  - 사용자 판단 대기(`NEXT_WORK.md` 5절): `Install_01`/`Install_02`는 자료가 오기
    전까지 건드리지 않음(MANUAL/SKIP 유지), `WF_13` 로그인 계정 전환 자동화 여부,
    stale 브랜치 `agent/add-next-task-handoff` 삭제 승인.
- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/3-A류 XIPL_03, 간헐 증상
  3-B/3-C — 전부 자동화 결함 아님, 28차에서 회귀 없음).
