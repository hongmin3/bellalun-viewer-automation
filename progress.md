# Progress Checkpoint

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 현재 목표: 2026-08-28 미검증 자동화 변경을 문서화하고 다음 검증 세션으로 인계
- 완료한 작업: `WF_10`의 `HC` 매핑 Procedure를 비기본 `Mammography (Rt)`로 변경; `cold_start`에 주 모니터 밖 Viewer 안전 중단 추가; 로그인 전용 `_login_check.py` 추가; 관련 운영 문서 갱신
- 진행 중 작업: 없음
- 남은 작업: `run-wf10` 매핑·Step 실측, 주 모니터 밖/안 `cold_start` 검증, `WF_04→06`·`WF_13`·`WF_15` 개별 재검증 후 전체 회귀 재실행
- 중요한 설계 결정: 기본 Procedure 대체로 생길 수 있는 거짓 PASS를 막기 위해 비기본 Procedure를 사용; 다중 모니터/DPI 환경에서 Viewer 창을 강제 이동하지 않고 안전 중단
- 변경 파일: `core/flows.py`, `tests/workflow10.py`, `_login_check.py`, `README.md`, `NEXT_WORK.md`, `progress.md`, `../프로젝트_상세.md` 및 렌더링 산출물
- 알려진 문제: 2026-08-28 15:16경 시작한 전체 회귀는 세션 만료 후 사용자 요청으로 `WF_14` 부근에서 종료되어 완료 결과로 사용할 수 없음
- 다음 세션에서 시작할 작업: 정적 검사 후 `run-wf10`과 `cold_start`를 좁게 검증하고, `NEXT_WORK.md` P0 순서대로 개별 TC를 확인
