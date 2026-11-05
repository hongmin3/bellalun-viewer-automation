# Testing Guide

## 수정 후 검증 순서 (REQ-REGRESSION-002)

1. 소스에서 관련 단위시험·정적 검사와 전체 단위시험을 수행한다. Viewer·DB를 조작하는 소스 UI 회귀는 기본 절차에 넣지 않는다.
2. UI 확인이 필요한 변경이면 검증용 후보 EXE를 빌드한다. 빌드 방법과 설치판 결과의 배포 판정은 [배포 안내](distribution-guide.md)를 따른다.
3. 아래 표로 필요한 UI 범위를 고르고 실행 전에 사용자에게 묻는다. 답변을 받은 뒤 같은 EXE로 승인 범위를 수행한다.
4. 결과와 미수행 범위를 기록한다. 시험한 EXE를 다시 컴파일하지 않는다. 수정해서 새 EXE를 만들거나 재실행이 필요하면 다시 확인한다.

| 변경 영향 | 기본 UI 검증 범위 | 판단할 것 |
|---|---|---|
| 문서·주석·단위시험·제품 실행에 영향 없는 운영 도구 | UI 실행 없음 | 링크·관련 시험·CLI 입출력으로 검증 |
| 한 TC 안에서 끝나는 수정 | 해당 단독 TC | 사용하는 공용 함수와 선행 데이터에 다른 영향이 없는지 |
| WU 전용 체인·저장점·집계 | WU 전체만 | 기본기능 TC 자체나 공용 동작까지 바꿨으면 범위를 확대 |
| 기본기능의 여러 TC | 기본기능 전체만 | 같은 코드를 WU가 쓰는지 확인하고 필요하면 WU도 포함 |
| 두 묶음의 공용 UI/OCR·로그인·DB 복원·DICOM·판정/결과·실행 동작의 큰 변경, 패키징 런타임 변경, 영향 불명확 | 기본기능 전체 + 실시간 WU 전체 | 파일 수·줄 수보다 공용 동작과 예상 고장 범위로 판단 |

공용 함수의 작은 수정도 영향이 한 TC에 한정된다는 근거가 없으면 두 묶음 전체를 선택한다. 반대로 많은 문서/시험 파일을 바꿨다는 이유만으로 전체 UI 회귀를 선택하지 않는다.

### 실행 전 사용자에게 제시할 내용

> 변경한 빌드/EXE와 해시: …  
> 제안 범위와 이유: 단독 TC / 기본기능 / WU / 두 묶음 전체, …  
> 예상 시간: … (최근 해당 PC 실행 기준, 불확실하면 그렇게 표시)  
> PC 점유와 상태 변경: 마우스·키보드 점유, DB 복원·설정 변경·USB 사용 여부, …  
> 위 범위로 실행해도 될까요?

명시적 답변을 받기 전에는 제품 UI·DB 복원을 시작하지 않는다. 이미 같은 빌드·범위·계획된 실행을 승인받았다면 같은 승인을 사용한다. 새 빌드, 범위 확대, 추가 재실행·복원은 다시 묻는다. 소스 단위시험·정적 검사·읽기 전용 결과 확인은 계속할 수 있다.

실행 직전에는 기준 상태를 확인한다. 직전 실행이 중간에 강제 종료됐거나 수동 탐색으로 Viewer 설정을 바꿨다면, 그 상태를 원래 값으로 삼아 시험을 시작하지 않는다. 먼저 기준 DB 복원 또는 이전 리포트의 원래 값으로 되돌린 뒤 실행한다. 복원·원상 복구가 들어 있는 실행은 최악 소요 시간보다 짧은 시간 제한으로 감싸지 않는다. 세션과 분리해 띄우고 진행 상태를 확인한다.

### 설치판 실행 범위

`tools/run_installed_suites.py`의 `--suites`는 필수다. 다음 값 중 승인받은 것을 사용한다.

| 범위 | 인수 |
|---|---|
| 기본기능만 | `--suites run-regression` |
| WU만 | `--suites run-winupdate` |
| 두 묶음 전체 | `--suites run-regression,run-winupdate` |
| WF14 단독 예시 | `--suites run-wf14 --expected-tc TC_Basic_WorkFlow_14` |
| XIPL04 단독 예시 | `--suites run-xipl-04 --expected-tc TC_XIPL_compatibility_04` |

단독 지원 명령은 `run-wf01`~`run-wf16`, `run-xipl-01`~`run-xipl-07`이다. 단독 실행에도 대상 검사·영상·DICOM 설정 등 TC의 선행조건이 필요하다. 별도 단독 진입점이 없는 WU TC나 준비되지 않은 TC는 필요한 묶음과 이유를 제안하고 승인받는다. 임의로 DB를 복원하거나 전체 실행으로 바꾸지 않는다.

소스 UI 실행은 소스에서만 재현 가능한 문제의 진단 등 구체적인 이유가 있을 때 별도로 승인받아 사용한다. 진단 결과를 설치판 검증으로 표시하지 않는다.

## 긴 실행 전 사전 검사

소스 검증 환경은 `python -m pip install -r requirements-dev.txt`로 준비한다.
설치된 BellalunAuto에는 Python이나 시험용 의존성을 별도로 설치하지 않는다.

```powershell
python -m py_compile <변경한 파일>
python tools/check_module_attrs.py
python tools/check_self_attrs.py
python tools/check_cleanup_stop.py
python tools/check_regression_names.py
python tools/traceability.py
python tools/check_docs_sync.py
python tools/wu_selfcheck.py
python -m pytest tests -q
```

`tools/wu_selfcheck.py`는 WU 매핑(`tests/winupdate.py`)과 `automation_scope.json`·`traceability.json`의
일치, `except` 블록 안의 PASS 기록, 공유 `ctypes.windll` 함수의 `restype`·`argtypes` 변경을 검사한다.
기준선은 비어 있다(`core/ui.py`의 기존 6건은 전용 `WinDLL` 사본으로 옮겼다). 새 위반이 생기면 실패한다.

## Viewer 조작 없는 실측 명령

```powershell
python -m core.env_preflight --config config.json        # 실행 전 점검·검증된 환경 대조
python -m core.update_evidence --show                     # OS 빌드·KB 기록과 직전 기록 비교(저장 안 함)
python run.py update-watch --install-task                 # 예약 등록 명령만 출력(--apply 없으면 등록 안 함, 이 프로젝트는 예약 등록하지 않는다)
python tools/wu_flake_stats.py "Reports/Result_WindowsUpdate_*.json"   # 회차별 판정이 갈린 TC·단계
python tools/release_gate.py --wu <WU json> --basic <기본 json> --commit <SHA>
python run.py run-winupdate --from-regression <기본 json>  # 과거 결과 변환(Viewer·DB 미사용)
```

외부 문서 timestamp 등으로 실패하면 숨기지 말고 변경 관련성과 원인을 구분해 보고한다.

## UI/전체 회귀 조건

- 관리자 권한(High Integrity). 먼저 `python run.py portability-check` 결과를 본다.
- 1920×1080, 100%(96 DPI), Tesseract-OCR, SQL Server, XIPL Studio.
- 실행 중 마우스와 키보드를 점유하므로 사람이 조작하지 않는다.
- 전체 회귀는 오래 걸리고 DB baseline을 복원한다. 문서 검증 목적으로 실행하지 않는다.

## 출력 절약

성공 시 exit code와 최종 요약만 남긴다. 실패 시 `ERROR|FAILED|WARNING|Traceback` 주변만
확인하고 원인이 불충분할 때만 범위를 넓힌다. 리포트·증거 디렉터리는 전체 열람하지 않는다.

