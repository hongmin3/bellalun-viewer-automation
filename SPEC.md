# Bellalun Viewer 자동화 사양서

<!-- spec-template: v1 -->

| 항목 | 값 |
|---|---|
| Document Version | 1.0.0 |
| Project Version | 기존 작업 트리 기준, 제품 릴리스 변경 없음 |
| Last Updated | 2026-09-22 |
| Status | current |
| Owner | Bellalun Viewer 자동화 유지보수 담당자 |

기존 [README.md](README.md), [구조 문서](docs/architecture.md), `automation_scope.json`,
`traceability.json`과 테스트에 근거한 최소 현재 사양이다.
이번 SPEC/readiness 도입은 관리 체계 변경이며 제품 기능·실행 동작을 추가하거나 변경하지 않는다.
현재 제품 작업의 우선순위와 남은 결정은 `NEXT_WORK.md`에 둔다.
사양과 구현이 다르면 `SPEC / CODE MISMATCH`로 보고한다.

## 1. 목적

Bellalun Viewer의 기준 QA 체크리스트를 실제 UI로 수행하고 검증 가능한 PASS/FAIL 근거를 남긴다.
성공 조건은 체크리스트의 대상·의미를 유지하면서 자동화 한계와 실제 제품 결함을 구분해 보고하는 것이다.

## 2. 프로젝트 범위

### 포함

- 기본기능 체크리스트의 Workflow와 기능군별 시나리오 및 문서화된 회귀.
- 기존 기본기능/XIPL 결과를 이용하는 Windows Update 전용 흐름과 리포트.
- TC별 자동화 범위·사양 근거 추적성, 판정 및 생성 증거.

### 제외

- 비슷한 이름의 다른 체크리스트로 TC 번호/절차를 대체하는 작업.
- 근거가 없는 PASS, 미확정 Release Note/OS 기준값의 추정, WU_09 완료의 미검증 승격.
- 이번 도입 중의 Viewer 실행·DB 복원·설정 변경 및 비공개 원본의 공개 저장소 편입.
- 회귀 밖 독립 설치 패키지 점검을 기본 회귀에 임의 편입하는 작업.

## 3. 시스템 구성

`run.py`가 명령·환경 gate·회귀를 연결한다. TC 시나리오는 tests에,
UI/OCR·DB·DICOM·판정·보고 공용 계층은 core에 있다.
`core/result.py`가 판정과 공통 리포트 데이터를 담당하고
`core/winupdate_report.py`가 Windows Update 체크리스트 출력을 담당한다.
`automation_scope.json`과 `traceability.json`은 각각 범위와 근거 연결의 데이터 원본이다.
비공개 체크리스트·지식·Baseline은 auto Git 저장소 밖 자산이다.

## 4. 전체 동작 흐름

1. 기준 체크리스트와 범위에 맞는 명령을 선택하고 실행 환경/권한을 확인한다.
2. 선택한 흐름의 선행조건과 문서화된 회귀 순서를 따른다.
3. 제품 UI 동작을 수행하고 화면·DB·파일·수신 결과 등 근거를 관찰한다.
4. 기대 결과와 대조해 TC/Step 상태와 이유·증거를 기록한다.
5. 기본기능 또는 Windows Update 문맥에 맞는 제목·원본 문서·판정 리포트를 생성한다.

## 5. 기능 요구사항

### REQ-REGRESSION-001

#### 목적
체크리스트 근거가 있는 Workflow만 실행하고 PASS/FAIL/MANUAL/SKIP 의미를 보존한다.
#### 입력
CLI 명령, 기준 체크리스트, `automation_scope.json`의 TC 등급·사유.
#### 선행 조건
선택한 시험에 필요한 권한·화면·제품·외부 연동 환경을 갖춘다.
#### 동작
기본기능 회귀는 개정 체크리스트의 TC를 따른다. Windows Update는 전용 체크리스트와
기존 자동화의 명시된 매핑을 사용한다. 자동 판정 불가·수동·제외 항목의 이유를 보존한다.
#### 기대 결과
수행한 범위와 판정 상태가 일치하며 단일 TC 결과를 전체 회귀 완료로 보고하지 않는다.
#### 예외 처리
환경/전제 미충족은 기존 BLOCKED 또는 해당 흐름의 MANUAL/SKIP으로 구분해 보고하고
임의의 성공이나 새 TC로 대체하지 않는다.
#### 관련 구현
`run.py`, `automation_scope.json`, `core/automation_health.py`, `tests/winupdate.py`.
#### 관련 테스트
TEST-REGRESSION-001, `tests/test_automation_health.py`, `tests/test_result_reports.py`.

### REQ-TRACE-001

#### 목적
자동 검증과 체크리스트/사양 근거 사이 연결을 유지한다.
#### 입력
TC ID, 기준 체크리스트, 사양 문서·인용·쪽·Step 근거.
#### 선행 조건
사양 검증 시 권한 있는 환경에 원본 자료가 존재한다.
#### 동작
`traceability.json`에 TC·모듈·명령과 사양 근거를 연결하고 `automation_scope.json`에
자동화 범위·제약을 유지한다. 근거가 없는 항목은 미확정 이유를 드러낸다.
리포트에도 해당 기준 수행 절차와 기대 결과를 전달한다.
#### 기대 결과
검토자가 어떤 체크리스트/사양을 판정 근거로 삼았는지 추적할 수 있다.
#### 예외 처리
원본 부재나 근거 미정인 항목에 임의의 인용·쪽·정상 기준을 만들지 않는다.
#### 관련 구현
`traceability.json`, `automation_scope.json`, `tools/traceability.py`, `core/result.py`.
#### 관련 테스트
TEST-TRACE-001, `tests/test_result_reports.py`.

### REQ-VERDICT-001

#### 목적
PASS는 조작 성공 자체가 아닌 제품 화면 또는 저장·전송된 결과의 근거로 결정한다.
#### 입력
TC expected result와 화면·DB·파일·수신 결과 등 actual evidence.
#### 선행 조건
근거를 읽을 수 있고 해당 TC의 기대 결과와 대조할 수 있어야 한다.
#### 동작
클릭/입력 성공만으로 통과하지 않는다. 필요한 값·화면 변화·영속화/수신 결과를 확인한다.
실제 제품 결함은 FAIL로 유지하고 자동화 한계는 이유를 포함해 구분한다.
#### 기대 결과
검증하지 못한 동작은 PASS가 되지 않으며 증거로 결과를 재검토할 수 있다.
#### 예외 처리
주 모니터 밖 창을 재사용할 때 조작 전에 중단한다. 근거 부족을 숨기지 않는다.
WU_09는 되읽기 완료 신호와 교차 확인이 검증되기 전에는 MANUAL을 유지한다.
#### 관련 구현
`core/result.py`, `core/flows.py`, `tests/winupdate.py`, `core/usb_media.py`.
#### 관련 테스트
TEST-VERDICT-001, `tests/test_primary_monitor_guard.py`, `tests/test_result_reports.py`.

### REQ-REPORT-001

#### 목적
기본기능과 Windows Update 리포트가 각각의 제목·기준 문서·판정 이유를 보존한다.
#### 입력
TC/Step 결과, report title/source document/source sheet 메타데이터, expected/actual/note.
#### 선행 조건
선택한 실행 흐름의 리포트 문맥이 제공된다.
#### 동작
공통 HTML/TXT/CSV/JSON 리포트에 실행 환경·명령·TC 판정과 사유를 전달한다.
Windows Update는 기본기능 제목으로 오표기하지 않는다. 체크리스트 결과에서
Fail/Manual의 이유를 전용 Comment에 쓰고 기존 수기 공용 Comment를 덮어쓰지 않는다.
#### 기대 결과
두 리포트의 기준 문서와 판정 이유가 혼동되지 않고 실패/미검증 사유를 읽을 수 있다.
#### 예외 처리
BLOCKED는 별도 판정과 해제 조건·이번 실행으로 입증하지 못한 내용을 유지한다.
Windows Update의 원문 Step 접이식 설명이 비어 있는 기존 한계를 새로 채워졌다고 주장하지 않는다.
#### 관련 구현
`core/result.py`, `core/winupdate_report.py`, `run.py`, `tests/winupdate.py`.
#### 관련 테스트
TEST-REPORT-001, `tests/test_result_reports.py`.

## 6. 비기능 요구사항

### NFR-BOUNDARY-001

비공개 지식, Baseline DB 자료, 실제 자격증명·설정, 환자/DICOM 및 생성 증거는 공개 커밋에 포함하지 않는다.
공개 auto 저장소에는 코드·검사 도구·템플릿·공개 가능한 문서만 둔다.
TEST-BOUNDARY-001로 경계를 확인한다.

## 7. 데이터 사양

`automation_scope.json`은 TC ID/등급/사유/coverage를,
`traceability.json`은 기준 체크리스트·문서 인용과 TC/Step 연결을 담는다.
TC 결과는 Step별 상태·expected/actual/note·증거와 TC verdict를 구분한다.
Reports/Evidence/work 등은 실행 산출물이며 기준 원본을 대체하지 않는다.
기본기능 기준은 개정 체크리스트의 개정 TC 시트, Windows Update 기준은 해당 전용 Checklist 시트다.

## 8. Configuration 사양

`config.example.json`은 공개 템플릿이고 `config.json`은 로컬 환경값이다.
Release Note·OS Build 기대값은 승인된 입력으로만 채운다.
권한·화면/DPI·OCR·DB·제품 경로 등 환경 조건은 README와 기존 portability 검사 경로를 따른다.
현재 설정·기본 회귀 순서·baseline 복원 동작은 이번 도입에서 변경하지 않는다.

## 9. 오류 처리 정책

- 환경 gate 실패를 무시하고 UI 입력을 계속하지 않는다.
- 기대/실제 불일치는 FAIL, 자료/자동화 한계는 근거가 있는 MANUAL,
  미수행은 해당 흐름의 SKIP으로 남긴다. BLOCKED는 해제 조건과 미검증 범위를 보존한다.
- 실제 재현된 실패만 해당 실행의 이슈로 보고하며 알려진 제품 결함을 자동화 성공으로 숨기지 않는다.
- 종료되지 않은 실행·중간 상태 파일을 전체 회귀 완료로 간주하지 않는다.
- USB Import는 목록 표시/행 선택과 실제 되읽기 완료를 구분한다.

## 10. 보안 요구사항

NFR-BOUNDARY-001에 따라 상위 비공개 원본을 auto 저장소로 이동·복제하지 않는다.
실제 설정과 토큰·계정·환자 데이터의 값을 SPEC·로그·공개 커밋에 쓰지 않는다.
Baseline/제품 DB 변경 및 UI 입력은 명시된 실제 검증 작업에서만 수행한다.

## 11. 테스트 사양

아래 테스트 파일은 제품 시나리오와 구분한 안전한 단위 검증 대상이다.
이번 문서 작업은 readiness와 문서 연결만 검증하며 새 제품 회귀 결과를 주장하지 않는다.

### TEST-REGRESSION-001

- 검증 대상: REQ-REGRESSION-001.
- 선행 조건: 임시 리포트/상태 파일, 제품 미실행.
- 절차: `tests/test_automation_health.py`와 `tests/test_result_reports.py`로
  전체 회귀와 단일 TC 구분, TC 진행 상태, verdict를 검증한다.
- Expected Result: 단일/오래된 실행을 새 전체 회귀로 오인하지 않고 TC별 판정을 보존한다.
  체크리스트 흐름 전체는 별도 실제 실행 근거가 필요하다.

### TEST-TRACE-001

- 검증 대상: REQ-TRACE-001.
- 선행 조건: 리포트 단위 검사에는 합성 체크리스트, 원문 검증에는 권한 있는 원본 환경.
- 절차: `tests/test_result_reports.py`에서 기준 절차·expected 전달을 검증한다.
  원문 환경에서는 `python tools/traceability.py`로 인용·쪽·모듈·명령·Step 연결을 대조한다.
- Expected Result: 기준과 TC 연결을 따라갈 수 있고 원본 부재/미확정 근거를 정상 검증으로 숨기지 않는다.
  이번 도입에서는 비공개 원본 검증을 실행하지 않는다.

### TEST-VERDICT-001

- 검증 대상: REQ-VERDICT-001.
- 선행 조건: mock 창/화면과 합성 결과.
- 절차: `tests/test_primary_monitor_guard.py`로 주 모니터 밖 기존 창 재사용 시 첫 클릭 전에
  중단되는지, `tests/test_result_reports.py`로 BLOCKED와 미검증 이유가 보존되는지 검증한다.
- Expected Result: 잘못된 창에서의 조작이 성공으로 둔갑하지 않고 검증 한계가 남는다.
  각 제품 기능의 성공 증명은 TC별 실물/저장 결과로 별도 확인한다.

### TEST-REPORT-001

- 검증 대상: REQ-REPORT-001.
- 선행 조건: 임시 디렉터리와 합성 TC 결과.
- 절차: `tests/test_result_reports.py`로 네 형식의 공통 문맥·판정 이유·원문 연결을 검증한다.
  기본기능/WU 메타데이터 비교에서는 각 제목·source document·source sheet와 Fail/Manual 이유를 대조한다.
- Expected Result: 기본기능/WU 문맥이 섞이지 않고 기존 수기 Comment가 보존된다.
  기존 공통 단위 테스트만으로 WU XLSX/제목 조합 전체가 검증됐다고 주장하지 않는다.

### TEST-BOUNDARY-001

- 검증 대상: NFR-BOUNDARY-001.
- 선행 조건: auto Git 루트에서 읽기 전용 검사.
- 절차: `git status --short`, `git ls-files`와 `git check-ignore config.json`으로
  비공개 원본/Baseline/설정/생성물의 커밋 제외 경계를 경로 수준에서 검토한다.
- Expected Result: 민감값은 출력하지 않고 공개 대상에 비공개 자산이 들어가지 않음을 확인한다.

## 12. 요구사항 추적성

| Requirement | Implementation | Test | Status |
|---|---|---|---|
| REQ-REGRESSION-001 | `run.py`, `automation_scope.json`, `core/automation_health.py`, `tests/winupdate.py` | TEST-REGRESSION-001; `tests/test_automation_health.py`, `tests/test_result_reports.py` | implemented |
| REQ-TRACE-001 | `traceability.json`, `automation_scope.json`, `tools/traceability.py`, `core/result.py` | TEST-TRACE-001; `tests/test_result_reports.py` | implemented |
| REQ-VERDICT-001 | `core/result.py`, `core/flows.py`, `core/usb_media.py`, `tests/winupdate.py` | TEST-VERDICT-001; `tests/test_primary_monitor_guard.py`, `tests/test_result_reports.py` | implemented |
| REQ-REPORT-001 | `core/result.py`, `core/winupdate_report.py`, `run.py`, `tests/winupdate.py` | TEST-REPORT-001; `tests/test_result_reports.py` | implemented |
| NFR-BOUNDARY-001 | `.gitignore`, `config.example.json` | TEST-BOUNDARY-001 | implemented |

implemented는 기존 문서·테스트와 구현 경로의 연결을 뜻한다.
이번 readiness 검사만으로 실제 제품 검증을 verified로 올리지 않는다.

## 13. 미확정 사항

- 확인 필요 — WU_09 중복 데이터 선택 이후 Import 완료 신호와 Examined 재검색 교차 확인.
  근거: `progress.md`의 2026-09-09 기록과 `NEXT_WORK.md` 5절 ⑨.
  영향: 목록 1행 표시 성공만으로 PASS로 올리지 않고 완료 검증 전 MANUAL 유지.
  담당: 자동화 유지보수 담당자, 실제 실행 시점/범위 결정은 사용자.
- 확인 필요 — Install_01/02의 승인 Release Note와 OS Build 기준 자료.
  근거: `automation_scope.json` 및 `NEXT_WORK.md`.
  영향: 기준값 없는 검증은 기존 MANUAL/SKIP으로 남긴다. 담당: 사용자/제품 QA 담당자.
- 확인 필요 — WU 리포트의 원문 Step 설명을 공통 접이식 영역에 채울지 여부.
  근거: `progress.md`의 2026-09-08 기록.
  영향: 현재 expected/actual/note는 유지하며 원문 영역의 기존 빈 상태를 완료로 바꾸지 않는다.
  결정 담당: 사용자와 자동화 유지보수 담당자.

## 14. 향후 개선 후보

Hub/Worker 진행률 소비 측 확인과 기존 우선순위는 `NEXT_WORK.md`를 따른다.
이번 도입에서 새로운 TC·판정 완화·제품 개선을 구현하지 않는다.
