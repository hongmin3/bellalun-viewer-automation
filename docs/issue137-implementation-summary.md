# 후속 안정화 구현과 검증 범위

2026-11-15 기준으로 제어 이슈 #137의 구현과 #138의 현황 요청을 함께 정리한다.
제품 동작의 기준은 [SPEC](../SPEC.md)이며, 이 문서는 요구사항과 구현·검증 기록을 연결한다.
현재 소스와 설치판은 **1.0.18 후보**다. 전체 실물 수용은 미완료이며 정식 릴리스가 아니다.

## 사용자가 확정한 범위

- 실행마다 원상복원을 선택한다. 선택과 무관하게 변경할 자료를 먼저 보존하고 검증한다.
- 공용 저장소에 사전·시험 후 사본을 남기고 변경 파일만 순차 복원한다.
  실제 NAS는 인증 실패로 이번 실물 수용에서 제외하고, 승인된 별도 로컬 저장소를 사용했다.
- 정상 회귀·선택한 복원·서비스 확인·최종 저장 뒤 60초 후 Auto 창을 닫는다.
  멈춤 버튼이나 다른 GUI 버튼 실행은 그 회차의 자동 닫기를 취소한다. 키보드 버튼 실행도 같다.
- 정상 완료 증명이 있는 회귀에서 복원까지 검증된 경우에만 그 실행의 생성 Image를 정리한다.
  시험 전 원본·공용 사본·과거 백업·다른 실행의 자료는 자동 삭제하지 않는다.
- 실제 수용은 납품 ZIP 해제 → Setup 업데이트 → 설치된 GUI → 기본기능·WU 전체 →
  선택 복원·결과·생성 Image 정리 → 60초 자동 닫기·취소 순서다. CLI 성공으로 대신하지 않는다.
- 새 화면 녹화·영상 편집·업로드는 제외한다. 기존 발표 원본 보존과 구분한다.
- 설치·전체 회귀 및 자동화 결함의 수정·재빌드·같은 범위 재실행은 이미 승인됐다.
  새로운 제품 설치·제거, 서버 배포, 대상 PC 확대는 구체적인 계획과 승인을 별도로 확인한다.

## 요구사항과 구현 지도

모든 행의 소스 구현은 존재한다. 아래 실물 확인 범위가 곧 전체 기능의 검증 완료를 뜻하지 않는다.
원래 후보 번호 P1–P14는 [승인 설계](superpowers/specs/2026-11-13-followup-reliability-design.md)와
[실행 계획](superpowers/plans/2026-11-13-followups.md)을 따른다.

| 범위 | 제공하는 기능 | 요구사항 | 주요 구현·시험 | 검증 범위와 남은 확인 |
|---|---|---|---|---|
| P1–P2 | DB·파일 사전 보존, 실행별 선택 복원, 볼륨별 용량·메모리 점검 | REQ-FOLLOWUP-001 | `core/run_preservation.py`, `core/resource_budget.py`; `tests/test_run_preservation.py`, `tests/test_resource_budget.py` | 합성 실패 시험과 실제 로컬 파일·4DB 복원 확인. 과거 사전 사본 없는 자료 복원은 미확인 유지 |
| P3 | 저장 실패 직전까지 수행한 결과·부분 리포트 보존, 불완전 체인 차단 | REQ-FOLLOWUP-001 | `run.py`, `core/wu_chain.py`; `tests/test_checkpoint_partial_report.py` | 저장 실패 주입 시험. 부분 결과를 정상 완주로 채택하지 않음 |
| P4 | GUI가 닫혀도 감독 프로세스가 최종 실행 기록 저장 | REQ-FOLLOWUP-001 | `bellalunauto/runs.py`; `tests/test_qa_runs.py` | 감독·최종 저장 경계 시험. 복원·저장 전 완료 처리 금지 |
| P5 | 실행 번호·소스·제품·설정·자료 지문과 재사용 단계 기록 | REQ-FOLLOWUP-001 | `core/source_identity.py`; `tests/test_source_identity_followup.py` | 신원 직렬화·미확인 신원·표시 사본 배제 시험 |
| P6 | 다른 지문·복원 세대의 저장점 재개 거부 | REQ-FOLLOWUP-001 | `core/execution_session.py`, `core/wu_chain.py`; `tests/test_execution_session.py` | 지문 불일치 및 중단 재개 시험 |
| P7 | 새 경고·실패 단계의 증거 연결과 입력 차단 원인 유지 | REQ-FOLLOWUP-002, REQ-VERDICT-003 | `core/failure_evidence.py`, `core/flows.py`; `tests/test_environment_failure_gate.py`, `tests/test_focus_recovery.py` | 입력 차단·로그인 예외 시험. 실제 가림과 성별 판독의 인과관계는 미확정 |
| P8–P9 | 실행 전 동의 화면에서 진단·해결 안내, 미설정과 연결 실패 구분 | REQ-FOLLOWUP-002 | `bellalunauto/qa_dialogs.py`; `tests/test_qa_dialogs.py` | 대화상자 시험과 설치판 준비·동의 화면 확인 |
| P10 | 실제 설치 구성 수집과 승인 Release Note 기준 대조 | REQ-FOLLOWUP-002 | `core/release_note_baseline.py`; `tests/test_release_note_baseline.py` | 추출·구성 조회 확인. 승인 DB 버전 기준 및 실제 제품 패키지 대조 미완료 |
| P11 | 검증된 설치·Upgrade·Uninstall 프로필, 사전 보존과 재부팅 후 재개 | REQ-FOLLOWUP-002 | `core/product_lifecycle.py`; `tests/test_product_lifecycle.py` | 합성 실행·차단 경계 시험. 실제 제품 설치·제거 수용 미수행 |
| P12 | UI 호출·탐색 비용 계측과 공통 경로 정리 | REQ-FOLLOWUP-002 | `core/performance.py`; `tests/test_performance_followup.py` | 계측 시험. 실제 속도 개선 수치는 미확인 |
| P13 | 자동화 범위 원본으로 문서 수치 생성·대조 | REQ-FOLLOWUP-002 | `tools/scope_summary.py`, `automation_scope.json` | `python tools/scope_summary.py --check`로 검증 |
| P14 | 고정 원격 묶음, 인증 전송·해시 캐시, PC 잠금·진행·취소·결과 회수 | REQ-FOLLOWUP-002 | `remote/coordinator.py`; `tests/test_remote_execution.py` | 로컬 통신·모의 WinRM·Windows 파일 회수 시험. 실제 서버 배포·대상 Windows·공유 VHD 잠금 수용 미수행 |
| 완료 창 | 정상 마무리 후 60초 자동 닫기와 회차별 취소 | REQ-FOLLOWUP-003 | `bellalunauto/auto_close.py`; `tests/test_auto_close.py`, `tests/test_qa_runs.py` | 설치판1.0.17의 자동 닫기·멈춤 확인. 설치판1.0.20에서 자동 닫기와 다른 GUI 버튼(버전)·키보드 버튼 취소 확인 |
| 공용 보존 | 저장소 신원·로컬 journal·차이 복원·정리 재개·미완료 마무리 차단 | REQ-FOLLOWUP-004 | `core/preservation_storage.py`, `core/atomic_metadata.py`, `tools/recover_preservation.py`; `tests/test_shared_preservation.py`, `tests/test_atomic_metadata.py`, `tests/test_image_cleanup.py`, `tests/test_recover_preservation_cli.py` | 합성 파일과 실제 로컬 복원·정리 확인. 실제 SMB·긴 UNC 통합 수용은 제외·미검증 |
| 판정 수정 | WF14 UPS Import 예외와 XIPL03 기본값·실제 적용값 구분 | REQ-TCUP-005 | `tests/workflow14.py`, `tests/xipl_flows.py`; `tests/test_workflow14_evidence.py`, `tests/test_xipl_post_recon.py` | 1.0.17 기본 회귀에서 WF14·XIPL03·XIPL06 PASS. 과거 원시 FAIL은 보존 |

## 이슈 진행 중 보완한 결함

| 후보 | 변경과 근거 | 변경 커밋 |
|---|---|---|
| 1.0.13 | 공용 보존·차이 복원·Image 정리, WF14 UPS 기대값과 XIPL03 적용값 판정 수정 | `5e76ceb` |
| 1.0.14 | QC_SCHEDULE의 실제 두 열로 전체 행을 정렬. 중단 복구 재확인 뒤 pending 해제하되 원래 실패와 생성 이미지는 유지 | `7c7731f`, `978906a` |
| 1.0.15 | XIPL 저장·재시작 경계, 소유 창 안의 파일명 입력과 Parameter 적용 확인 보완 | `3275be1` |
| 1.0.16 | 마우스 적중 대상 검증과 입력 차단 시 후속 체인 중지 | `769c5e3` |
| 1.0.17 | journal·실행 기록의 Windows 메타데이터 교체 충돌을 오류5·32·33에 한해 2초 예산으로 재시도 | `f2854f7` |
| 1.0.18 | 로그인 재시도 소진 시 마지막 ForegroundError를 원래 타입으로 전달해 불완전 실행의 정상 완료 처리 차단 | `a87d94f` |

## 버전별 실제 확인 결과

| 대상 | 확인 결과 | 해석 |
|---|---|---|
| 1.0.17 기본 전체 | 36행 PASS25/MANUAL1/SKIP10/FAIL0 | 원래 수동·제외 항목을 자동 PASS로 합산하지 않음 |
| 1.0.17 WU 전체 | 13행 PASS10/SKIP3/FAIL0 | 두 실행에서 복원·서비스·생성 Image 정리와 약60초 자동 닫기 확인 |
| 1.0.17 멈춤 버튼 | 58초 카운트다운에서 취소, 75초 뒤 창 유지 | 다른 버튼·키보드 취소 완료로 확대하지 않음 |
| 1.0.18 빌드·설치 | 납품 ZIP·runtime1,010개 대조, 기존 작업1,838파일·설정 보존 | 무인 업데이트 확인. 설치 마법사 화면 수용은 미확인 |
| 1.0.18 기본 재실행 | run683의34행 PASS8/MANUAL1/FAIL15/SKIP10, 비정상 종료 | 입력 차단과 WF01 성별 UI 판독 None. 전체 수용 실패·미완료 유지 |
| 1.0.18 WF01 진단 | run684의 Viewer 진입에서 PC 정리 창 적중으로 중단 | 성별 판독에 미도달. 성별 오류까지 같은 원인이라고 확정하지 않음 |
| 1.0.20 기본 전체 | 36행 PASS25/MANUAL1/SKIP10/FAIL0, WF01 성별 판독·XIPL06 PASS | 복원·서비스·생성 Image 정리와 60초 자동 닫기 확인 |
| 1.0.20 WU 전체 2회 | 각 13행 PASS10/SKIP3/FAIL0 | 1회차 끝에 '버전' 버튼, 2회차 끝에 키보드(Tab·Space) 실행으로 자동 닫기 취소 확인 |

1.0.18 진단 뒤 파일·4DB·서비스 복구와 pending 해제를 확인했다.
원시 보고서·로그·복구 영수증·화면 증거는 로컬 Git 제외 작업 자료에 보존한다.
버전별 상세 실행 번호·SHA256·이전 시험 결과는 [진행 기록](../progress.md)과
[실물 검증 기록](practical-preservation-validation.md)을 따른다.

## 이후 작업과 완료 조건

1. PC 정리 창의 가림을 해소하고, WF01의 실제 MWL 화면·성별 읽기를 먼저 진단한다.
   창이 가려진 상태에서 전체 회귀를 반복하지 않는다. 다른 프로젝트 파일·프로세스는 변경하지 않는다.
2. 같은 설치판의 기본기능·WU 전체와 다른 버튼·키보드 자동 닫기 취소를 검증한다.
   코드 수정이 필요하면 단위시험·새 빌드·설치 후 승인된 범위로 다시 검증한다.
3. 보고서·실행 신원·정상 체인·파일/DB 복원·서비스·생성 Image 정리·자동 닫기 증거를 함께 확인한다.
   1.0.17의 성공과 소스 시험을 1.0.18의 전체 수용으로 대신하지 않는다.
4. NAS 인증, P10 승인 설치 기준, P11 실제 제품 수명주기, P14 Windows 원격 환경은 별도 잔여다.
   앞선 사용자 답변에서 정보가 없었던 내용을 반복 질문하지 않는다. 실제로 그 단계에 착수할 때
   로컬·사내 자료를 먼저 조사하고 필요한 선택만 쉬운 말로 묻는다.
5. 정식 릴리스는 위 실제 수용과 로컬 게이트를 모두 확인한 뒤 판정한다.
   기존 이슈 종료는 잔여 작업을 새 이슈로 옮기는 관리 처리이며 전체 제품 수용 완료 선언이 아니다.

## 현재 추가 결정

기존 승인과 제외 범위를 유지한 문서 정리에 새 제품 사양 결정은 필요하지 않다.
실제 SMB 수용·제품 설치/제거·원격 서버 배포는 미확정 환경 입력을 추측하지 않고 후속 작업으로 남긴다.
