# BellalunAuto P1~P14 실행 계획

사용자 승인: 2026-11-13 P1~P14 전부, 실행마다 복원 여부 선택, GUI 완료 60초 자동 닫기와 모든 버튼 취소.
설계: ../specs/2026-11-13-followup-reliability-design.md
기준: f247d21. 기존 AGENTS.md 줄끝 변경 보존. 공용 실행 변경은 기본기능+WU EXE 수용 대상이며 제품 실행 승인은 별도 확인한다.

## 계약
- plan.restore_after: bool. 실행마다 동의 화면에서 선택하며 자동으로 이전 선택을 재사용하지 않는다.
- plan.execution_fingerprint: config/제품/Baseline/소스 지문. Checkpoint 생성/load에 execution_fingerprint 키워드로 전달한다.
- 실행 최종 상태는 리포트 및 선택한 복원 완료 뒤 기록한다. GUI 자동 닫기는 completed만 대상이다.
- 부분 리포트 meta.chain_completed=false, checkpoint_save_failed를 포함하며 릴리스/완주 탐색에서 제외한다.
- 백업 API는 RunPreservation.prepare/finalize. DB 어댑터와 볼륨별 자원 예산은 공통 실행 진입점에서 연결한다.

## 순서와 파일
1. GUI 자동 닫기/P4/P8/P9: gui.py, auto_close.py, runs.py, qa_dialogs.py. tests/test_auto_close 및 기존 GUI/실행/대화 시험. 60초 경계·취소·키보드 invoke·늦은 콜백·정상/비정상 구분 RED→GREEN.
2. P5/P6: source_identity/result/automation_health/wu_chain/runplan. unknown 신원·표시 사본 제외·직렬화·지문 불일치 재개 거부 시험. run.py 실제 호출은 루트 통합.
3. P1/P2: run_preservation/resource_budget/env_preflight. 파일 사본·추가/삭제/내용변경·링크·중단 복구·부족 용량 시험. 공통 진입점에 DB 어댑터와 실행별 정책 연결.
4. P3: run.py 체인 예외 처리와 app.py 감독 최종 기록. 저장 실패 직전 단계 결과를 메모리에 넣고 부분 리포트/정리. 실제 체인 실패 주입 시험.
5. P7: 제품/환경 모달 증거를 보존하는 원인 기록과 실행 중단 보호. 제품 기대값 완화 금지.
6. P10/P11: Install01 실제 구성 수집, 승인 기준 파일 검증; 제품 lifecycle 명령은 검증된 실행 프로필과 사전 백업/복구·사람 승인 없으면 차단. 모의 프로세스/임시 데이터로 실행 계약 시험.
7. P12/P13: 실제 호출 시간 계측·중복 탐색 개선, automation_scope 기반 문서 합계 동기화.
8. P14: 고정 묶음 manifest·대화형 Windows 작업·PC별 실행 잠금·회수·취소와 검증. 서버 입력 미확정은 계획 검증/차단 상태로 보고하고 배포 완료로 주장하지 않는다.
9. 통합 전체 pytest/정적·추적성·문서 게이트, cleanup/readiness/workspace. 독립 코드 검토. EXE 수용 준비 후 실물 승인 확인. 확인된 변경만 관련 문서와 커밋·일반 push.

## 중요한 경계
시험 원본/개인 config/사내 원문/자격증명을 공개 저장소에 넣지 않는다. 기존 GUI 프로세스와 생성물을 조작하지 않는다. 실제 설치/제거/서버 배포는 검증된 구체 계획과 승인 없이는 실행하지 않는다. 사전 사본 없는 과거 QC/Dose SR은 복원 미확인 유지한다.