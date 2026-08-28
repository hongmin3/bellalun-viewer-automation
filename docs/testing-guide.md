# Testing Guide

## 변경 규모별 검증

- 문서만 변경: 링크·경로·명령 존재 여부, Markdown 구조, `git diff`를 확인한다.
- 단일 Python 파일: 해당 파일 `py_compile`, 관련 정적 검사와 단위 시험을 실행한다.
- 회귀 dispatch/공용 UI/결과 계층: 아래 사전 검사 전체 후 준비된 환경에서 관련 TC를 실행한다.
- 전체 회귀: 관리자 권한과 외부 시스템이 준비된 전용 세션에서만 실행한다.

## 긴 실행 전 사전 검사

```powershell
python -m py_compile <변경한 파일>
python tools/check_module_attrs.py
python tools/check_self_attrs.py
python tools/check_cleanup_stop.py
python tools/check_regression_names.py
python tools/traceability.py
python tools/check_docs_sync.py
python -m unittest discover -s tests -p "test_*.py"
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

