# Bellalun Viewer 자동화 — AI 작업 인덱스

Codex CLI용 저장소 인덱스다. Claude는 `CLAUDE.md`를 통해 이 파일을 읽는다. 사람용 설명은 `README.md`에 둔다.

## 새 세션 시작

1. 이전 작업을 잇는 경우 전체 탐색보다 `progress.md`를 먼저 읽는다.
2. 이 파일에서 관련 경로를 찾고 필요한 `docs/` 문서만 읽는다.
3. 제품/자동화 현재 상태가 필요할 때만 `NEXT_WORK.md`의 관련 절을 읽는다.
4. 코드 작업이면 대상 TC의 기준 문서와 관련 함수부터 확인한다.

## 목적과 경계

- Windows용 Bellalun Viewer의 QA 체크리스트를 실제 UI로 수행하고 PASS/FAIL 근거를 남기는 Python 자동화다.
- 상위 `Bellalun Viewer/`는 프로젝트 루트, 이 `auto/`가 Git 저장소다.
- 유일한 TC 기준은 `../Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`의 `개정 TC` 시트다.
- `../지식/`의 비슷한 TC 파일은 번호 매핑이 다를 수 있어 판정 기준으로 대체하지 않는다.
- 제품 근거는 `../지식/`의 Operation/Service Manual, DICOM Conformance Statement, 사양서다.
- `verify-install-package`는 체크리스트 회귀 밖의 독립 설치 패키지 점검이다.

## 주요 진입점과 구조

| 경로 | 역할 |
|---|---|
| `run.py` | CLI, 환경 gate, 개별 TC 및 회귀 진입점 |
| `core/` | UI/OCR, DB, DICOM, 결과·증거 재사용 계층 |
| `tests/` | TC 시나리오와 판정; `workflowNN.py`는 기본 Workflow 번호와 대응 |
| `tools/` | 정적 검사, 추적성, 문서·회귀 운영 도구 |
| `automation_scope.json` | TC별 자동화 등급·범위·제약의 데이터 원본 |
| `traceability.json` | 사양과 TC 간 추적성 데이터 원본 |
| `config.example.json` | 로컬 `config.json` 템플릿 |
| `NEXT_WORK.md` | 제품/자동화의 현재 상태와 우선순위 |
| `progress.md` | 여러 AI 세션에 걸친 작업 checkpoint |

구조와 데이터 흐름은 필요할 때 `docs/architecture.md`를 읽는다.

## 실행과 검증

```powershell
python -m pip install -r requirements.txt
Copy-Item config.example.json config.json   # 로컬 값 입력; 커밋 금지
python run.py portability-check
python run.py list
python tools/run_regression.py              # 전체 회귀 권장 진입점
python run.py --help                        # 개별 명령 확인
```

코드 검증 순서와 외부 환경 제약은 필요할 때 `docs/testing-guide.md`를 읽는다.
문서만 바꾼 경우 실제 Viewer/UI 회귀 대신 링크·명령·diff를 검증한다.

## 절대 변경하거나 훼손하지 말 것

- 요청 범위 밖의 기능 코드, 판정 기준, 자동화 Workflow, 회귀 순서.
- `../지식/`, `../Baseline/`, 기준 체크리스트와 프로젝트 루트의 근거 자산.
- `config.json`, 자격증명, 토큰, 환자·DICOM·런타임 데이터.
- `Reports/`, `Evidence/`, `Log/`, `Cache/`, `Temp/`, `work/`의 생성물.
- 공개 Git 이력; force-push나 이력 재작성 금지.
- `../프로젝트_상세.html` 직접 편집 금지. 원본은 `../프로젝트_상세.md`이며 `tools/render_docs.py`로 생성한다.

DB 상태 변경과 UI 입력은 명시적 기능/테스트 요청에만 수행한다. 조회처럼 보이는 UI도 즉시 저장할 수 있다.

## 코딩 및 판정 규칙

- 한국어 문서를 기본으로 하고 제품 용어·식별자는 원문을 유지한다.
- Evidence의 한국어 표기는 `증거`로 통일하되 영문 식별자·폴더명은 바꾸지 않는다.
- TC ID로 절차를 추측하지 말고 기준 체크리스트의 Step/Expected Result를 확인한다.
- 관찰한 동작으로 정상 기준을 역산하지 않는다. 사양·매뉴얼 근거를 판정 `note`에 남긴다.
- UI 선택은 Control ID, 표시 텍스트/OCR, 창 기준 상대 좌표를 우선하며 클릭 전 문구를 확인한다.
- PASS는 로그 한 줄에만 의존하지 않고 가능하면 DB·파일·UI 재진입으로 교차 확인한다.
- DB 직접 변경으로 제품 UI 동작을 모사하지 않는다. 제품 상태 변경은 UI, DB는 주로 검증에 쓴다.
- 불확실한 UI·기대 결과·파괴적 동작은 추측하지 말고 조회 근거를 확인한 뒤 필요하면 질문한다.
- 상세 구현 규칙과 반복 실수는 필요할 때 `docs/project-rules.md`를 읽는다.

## Context Efficiency / READ-ONCE

- 작업과 관련 없는 파일이나 전체 저장소를 무조건 탐색하지 않는다.
- 사용자가 지정한 파일·함수·클래스를 우선하고 필요한 범위부터 읽는다.
- 대용량 파일은 전체보다 `rg` 검색 후 관련 함수·클래스·라인 범위를 읽는다.
- 처음 읽은 정보는 유지하며 특별한 이유 없이 같은 파일을 반복 조회하지 않는다.
- 수정 후 전체 파일 재조회보다 `git diff -- <path>`를 우선한다.
- 단순 수정 때문에 전체를 재분석하거나 기존 문서 내용을 사용자에게 반복하지 않는다.
- 상세 지식은 링크된 문서가 현재 작업에 필요할 때만 읽는다.

## 명령 출력 최소화

- 정상 로그 전체 대신 ERROR/FAILED/WARNING과 요약을 우선한다.
- 긴 출력은 `Select-String`, `rg`, `Select-Object -First/-Last`로 제한한다.
- 테스트 성공 시 최종 건수·성공 여부만, 실패 시 원인 주변 로그만 확인한다.
- `git log` 전체나 디렉터리 내 모든 파일 내용을 출력하지 않는다. 필요한 commit/경로만 제한한다.
- 대량 생성물의 내용 대신 파일 수·크기·최신 항목 등 메타데이터를 우선한다.

## 기본 탐색 제외

직접 관련되지 않으면 읽거나 검색하지 않는다:

`.git/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, `.venv/`, `venv/`,
`Evidence/`, `Reports/`, `Log/`, `Cache/`, `Temp/`, `work/`, `*.log`, `*.dcm`, `*.bak`,
`../Baseline/`, 생성된 `../프로젝트_상세.html`.

이는 AI 탐색 규칙이며 Git 무시 규칙과 별개다. 실제 커밋 제외는 `.gitignore`를 따른다.

## Plan First와 세션 범위

- 여러 파일이나 복잡한 변경 전 대상 파일, 목적, 범위, 영향, 테스트 방법을 정리한다.
- 단순 수정에는 별도 계획 문서를 만들지 않는다.
- 한 세션은 가능하면 기능 개발·버그 수정·리팩터링·테스트·문서화 중 하나에 집중한다.
- 서로 관련 없는 대규모 작업을 한 세션에서 함께 수행하지 않는다.

## Checkpoint 규칙

- 장시간 작업 또는 대규모 변경 후 `progress.md`를 간결하게 업데이트한다.
- 완료 이력을 누적하지 말고 현재 목표·완료·진행 중·남은 작업·결정·변경 파일·문제·다음 시작점만 유지한다.
- 새 세션에서 이전 작업을 이을 때 전체 재분석 전에 `progress.md`를 확인한다.
- 장기 상태는 `NEXT_WORK.md`, 세션 간 작업 인계는 `progress.md`에 둔다.

## MCP / 외부 AI 도구

- 프로젝트 MCP 설정은 현재 확인되지 않았다. 새 프로젝트 전용 MCP는 목적과 범위를 문서화한다.
- 사용자 로컬 권한 파일 `../.claude/settings.local.json`은 저장소 설정이 아니며 임의 수정·공유하지 않는다.
- 점검 결과와 전역/프로젝트 배치 기준은 필요할 때 `docs/ai-tooling.md`를 읽는다.

## 문서 지도

- `README.md`: 사람용 프로젝트 소개와 실행 개요.
- `docs/architecture.md`: 경계, 계층, 핵심 Workflow와 데이터 원본.
- `docs/testing-guide.md`: 변경 규모별 검증과 긴 실행 전 검사.
- `docs/project-rules.md`: 제품 근거, UI/DB/판정 관련 영구 주의사항.
- `docs/ai-tooling.md`: Claude/Codex 탐색 제외와 MCP/외부 도구 점검.
- `NEXT_WORK.md`: 현재 제품·자동화 상태와 후속 우선순위.
- `../프로젝트_상세.md`: 사내 운영 상세; 관련 작업에서만 필요한 절을 읽는다.
