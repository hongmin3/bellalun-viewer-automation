# Progress Checkpoint

## 2026-09-02 WF_08 3D Print(Select Images 창) 결함 수정 완료

- 27차 전체 회귀(00:22~02:18, 116.1분, PASS22/FAIL3/MANUAL2)에서 XIPL_05 수정 외에
  예상 밖의 `TC_Basic_WorkFlow_08`(2D/3D Film Print) FAIL을 발견했다. 3D(Narrow/Wide)
  검사를 Print > Selected로 열면 Film 창 대신 "Select Images" 창이 먼저 뜨는데,
  기존 코드가 이 창을 전혀 다루지 않아 3D 인쇄가 항상 "Film window did not open"으로
  실패했다.
- 사용자가 알려준 Select Images 동작(좌=View Position 목록, 중=Raw/Recon/Syn 라디오로
  전환되는 프레임 목록, 우=전송 목록, 휴지통=삭제)을 사양서1 SRS 02-40-60·Operation
  Manual 10.1.2와 라이브 컨트롤 트리 조사로 교차 확인했다.
- `core/flows.py`에 `select_images_window/add/delete_last/clear/confirm` 신설.
  `tests/workflow08.py`가 3D 패스마다 Raw/Recon/Syn 각 1장씩 실제로 인쇄되게 하고,
  휴지통 삭제·3칸 pane 구분(서로 다른 영상 증명)·Print Overlay Header까지 검증하도록
  개편했다.
- 라이브 재검증 중 버그 3개를 더 찾아 고쳤다:
  1. 삭제가 "최근 추가한 항목"이 아니라 "가장 먼저 추가한 항목"을 지우던 방향 오류.
  2. 전송 목록에 이전 세션 항목이 남아 있으면 같은 프레임 재선택 시 제품이 "This item
     already exists."로 막던 문제 — 매번 비우고 시작하도록(`select_images_clear`) 수정.
  3. **가장 컸던 버그**: `ui.dialog()`가 진짜 "이미 있음" 경고가 아니라 **Select
     Images 창 자체**를 오탐지했다(창도 작은 `#32770`이라 열려만 있어도 "떠 있는
     대화상자"로 잡힘). 그래서 정상적으로 추가됐는데도 매번 "중복"으로 오판해
     재시도만 반복하다 프레임을 전부 소진하고 FAIL — `run-wf08` 단독 재현으로 확정.
     전송 목록 개수가 실제로 늘었는지로만 성공을 판정하도록 고쳤다.
- 검증: `py_compile` 통과, 정적 검사 4종 통과, 단위시험 150건 통과, `run-wf08` 라이브
  전 Step PASS(3D-N/3D-W 모두 Raw+Recon+Syn 3장 인쇄, 3칸 pane distinct 확인, Header
  Overlay 확인, Print SCP 픽셀 유사도 0.97~0.98).
- 변경 파일: `core/flows.py`(Select Images 함수 신설), `tests/workflow08.py`(3D 패스
  개편), `progress.md`, `NEXT_WORK.md`. (`Temp/probe_*.py`는 조사용 1회성 스크립트로
  커밋 대상 아님.)
- 남은 작업: 이 수정을 반영한 전체 회귀 1회로 최종 확인(직전 27차는 수정 전 코드로
  돈 것이라 WF_08 FAIL이 남아 있음 — 이번 수정 반영판으로 다시 돌리면 PASS 23 /
  FAIL 2(3-A UPS, XIPL_03 제품 결함) / MANUAL 2 예상).

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 진행 중 작업: 없음.
- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A, 간헐 증상 3-B/3-C — 전부
  자동화 결함 아님, 회귀 없음).
