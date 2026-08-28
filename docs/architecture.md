# Architecture

필요한 구조만 빠르게 찾기 위한 문서다. 사용자용 설명은 `../README.md`를 본다.

## 저장소 경계

- 상위 프로젝트 루트: 기준 체크리스트, 사양·매뉴얼, DB baseline, 사내 운영 문서.
- `auto/` Git 저장소: 실행 코드, TC 시나리오, 검증 도구, 공개 가능한 문서.
- 상위 자산은 입력/근거이며 저장소 안으로 이동하거나 복제하지 않는다.

## 실행 흐름

`run.py` 명령 → 환경/권한 gate → `tests/` TC 시나리오 → `core/` UI·DB·DICOM 기능
→ 결과 판정 및 `Evidence/`/`Reports/` 생성.

전체 회귀는 기준 DB 복원과 사전 설정을 포함하므로 명령 순서를 임의로 바꾸지 않는다.
Python 프로세스 외부 종료 감시가 필요한 권장 진입점은 `tools/run_regression.py`다.

## 책임 구분

- `run.py`: 명령 등록, dispatch, 전체 회귀 orchestration.
- `tests/workflowNN.py`: 기본 Workflow TC 절차와 Step 판정.
- `tests/xipl_flows.py`, `dataflow.py`, `settings.py`, `install*.py`: 기능군별 TC 흐름.
- `core/ui.py`, `uitext.py`, `screen.py`: Win32 UI, 텍스트/OCR, 화면 증거.
- `core/db.py`, `dbreset.py`: SQL 조회와 회귀 기준 복원.
- `core/mwl.py`, `storagescp.py`, `printscp.py`, `dicomlite.py`: DICOM 연동.
- `core/result.py`: Step 결과와 리포트용 판정 데이터.
- `automation_scope.json`: 자동화 등급·제약·해제 조건의 단일 데이터 원본.
- `traceability.json`: 사양 인용과 TC 연결의 단일 데이터 원본.

모듈 탐색은 전체 읽기보다 `rg "<TC ID|함수|명령>" run.py tests core`로 시작한다.

