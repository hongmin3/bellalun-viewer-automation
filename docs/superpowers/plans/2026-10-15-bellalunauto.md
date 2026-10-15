# BellalunAuto Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 팀원이 Python·Git·소스 없이 설치하고 기본기능/WU 전체 자동화를 실행할 수 있는 BellalunAuto를 만들고 설치된 EXE로 검증한다.

**Architecture:** 기존 `run.py`와 TC 엔진을 보존하며 얇은 배포 진입점, 작업 경로/설정 계층, 감시 프로세스, 한국어 Tk 실행 화면을 더한다. Nuitka standalone 결과를 Inno Setup 설치 프로그램으로 묶는다. 실행 자료는 허용 목록으로 별도 로컬 입력을 받아 내부 산출물에만 넣는다.

**Tech Stack:** Windows x64, CPython 3.12, Nuitka, tkinter, Inno Setup, 기존 requirements.txt.

**Spec:** `SPEC.md`의 REQ-DIST-*와 REQ-WU-*; 사용자가 실행을 지시한 바탕 화면 텍스트 문서의 1~8절.

## Global Constraints

- 자체 .py/.pyc·단위시험·개인 설정·현재 DB/환자 자료·기존 결과는 배포하지 않는다.
- 비공개 원문·승인 Baseline은 공개 Git에 넣지 않는다. 내부 설치 패키지는 로컬에만 둔다.
- 기존 TC 순서·기대값·제품 결함 판정을 유지한다. 제외 3건 외 WU 10건 PASS가 최종 목표다.
- 기존 dirty tree를 보존한다. 실행 중 기존 엔진 파일을 고치지 않는다.
- 기존 config.json을 변경하지 않는다. 로컬 .config-session.json은 공개 대상에서 제외했다.
- 관리자 권한 전환 시 절대 config/workspace 경로를 자식 인수로 전달한다.
- 소스 실행 전체 회귀 → EXE 빌드 → 설치 EXE로 기본기능/WU 전체 회귀 → 최종 판별 순서다.

## Review Focus

- 다른 관리자 계정의 UAC와 한글·공백 경로에서도 선택한 작업 폴더가 유지되어야 한다.
- GUI/CLI/다른 작업 폴더/다른 작업 폴더 설정으로 실행해도 제품 조작이 겹치지 않아야 한다.
- 감시 프로세스의 자식은 자기 EXE의 명시적 worker 모드를 한 번만 실행해야 한다.
- 소스 없는 설치 위치에서 동적 TC import와 근거 자료 읽기가 가능해야 한다.
- USB 기존 검사 검색만으로 PASS가 되지 않으며 TC9 오류가 TC10을 막지 않아야 한다.

### Task 1: 실행 경로와 설정

Files: `bellalunauto/runtime.py`, `tests/test_distribution_runtime.py`.

Interfaces:
- `Layout`: `resource_dir`, `workspace`, `config_path` (절대 pathlib.Path).
- `resolve_layout(config_path=None, workspace=None, resource_dir=None, preferences_dir=None) -> Layout`.
- `load_config(layout) -> dict`, `save_config(layout, config)`, `remember_workspace(workspace, preferences_dir=None)`.
- `child_command(arguments, executable=None, compiled=None) -> list[str]`: 소스 모드는 Python+BellalunAuto.py, 컴파일 모드는 자체 EXE.
- `RunLock` context manager: Windows 전역 제품 조작 잠금. `AlreadyRunning` 예외. 포터블/작업 폴더가 달라도 공유.

- [ ] 한글·공백·CWD 변경·명시 config·설정 보존·자식 명령·중복 실행 테스트를 먼저 작성하고 실패를 확인한다.
- [ ] 원자적 JSON 저장과 최소한의 경로/잠금을 구현하고 테스트를 통과시킨다.
- [ ] 변경 파일을 별도 리뷰하고 결과를 ledger에 남긴다.

### Task 2: 얇은 한국어 GUI

Files: `bellalunauto/gui.py`, `tests/test_distribution_gui.py`.

Interfaces:
- `launch(layout) -> int`, Task 1의 Layout/child_command/load_config/save_config 사용.
- 실행 명령은 `--workspace <absolute> --config <absolute> run-regression|run-winupdate|selfcheck|portability-check`.
- `run-regression`/`run-winupdate`는 진입점의 외부 감시를 통과한다. GUI가 엔진을 직접 호출하지 않는다.

- [ ] 실행 명령과 설정 검증을 화면 없이 테스트하고 실패를 확인한다.
- [ ] 두 모드 실행, 자체진단, 환경 점검, 설정, 로그/진행, 결과 열기, 버전을 제공한다.
- [ ] 처음 실행의 작업 폴더 선택과 설정 입력, 실행 중 중복 버튼 방지, 종료 시 자식 정리를 구현한다.
- [ ] GUI 실기 실행과 별도 리뷰를 수행한다.

### Task 3: 빌드와 설치

Files: `packaging/`, `tools/build_distribution.py`, `tests/test_distribution_build.py`, `docs/distribution-guide.md`.

Interfaces:
- 프로그램 진입점 `BellalunAuto.py`, 버전 `bellalunauto.__version__`.
- `python tools/build_distribution.py --assets <approved-assets.json> --output <local-dir> --iscc <ISCC.exe>`.
- 입력 manifest는 대상 상대 경로, 원본 절대 경로, SHA256, 자료 버전/Viewer·SQL 호환성을 기록한다.
- 배포 리소스: `resources/config.example.json`, `resources/automation_scope.json`, `resources/traceability.json`, `resources/assets/`.
- 출력은 `BellalunAuto-<version>-setup.exe`, 같은 빌드 portable.zip, build-info.json, SHA256SUMS.txt.

- [ ] 허용 목록/경로 탈출/소스·설정·민감자료 차단/해시 불일치 테스트를 작성하고 실패를 확인한다.
- [ ] Nuitka standalone, 자체 모듈 컴파일, 동적 import 명시 포함, 고정 도구 버전과 빌드 보고서를 구현한다.
- [ ] Inno Setup의 시작 메뉴·선택적 바탕화면·PATH·App Paths·제거 시 보존을 구현한다.
- [ ] 실제 빌드·파일 검사·로컬 설치/재설치/제거 검증을 수행한다. 내부 산출물은 공개 업로드하지 않는다.

### Task 4: 엔진 연결과 USB 완료 검증

Files: `BellalunAuto.py`, `bellalunauto/__init__.py`, `bellalunauto/app.py`, `run.py`, `tools/run_regression.py`, `core/specs.py`, `tests/winupdate.py`, `core/usb_media.py`, 관련 테스트.

- [ ] 소스 전체 회귀 완료/결과를 보존한 뒤 엔진을 변경한다.
- [ ] version/selfcheck/CLI 전달/worker 재귀 차단/감시 종료 코드를 먼저 테스트한다.
- [ ] config와 작업 폴더를 분리하고 읽기 전용 자료의 경로를 연결한다.
- [ ] 자체진단은 제품/DB/설정 변경 없이 누락과 해결 방법을 표시한다.
- [ ] TC 원문을 확인한다. USB 완료 신호와 전후 DB/영상 식별자 및 Examined 재검색을 함께 관찰한다.
- [ ] 기존 검사만 존재·완료 시간초과·실패 팝업·USB 부재·예외·TC10 정리/전수순회 테스트를 먼저 작성한다.
- [ ] 실측 근거로만 TC9 판정을 고친다. TC10 전수 순회와 빠른 탭 전환을 유지한다.

### Task 5: 최종 검증과 인계

- [ ] 정적 검사·전체 단위시험·readiness·SPEC HTML을 확인한다.
- [ ] 설치 EXE를 개발 폴더 밖 한글/공백 경로에서 version/selfcheck/환경 점검/GUI/CLI로 실행한다.
- [ ] 새 CMD·PowerShell 명령 검색, 설치/업데이트/제거와 설정·결과 보존을 확인한다.
- [ ] Python·Git·소스 없는 PC/VM 검증을 가능한 환경에서 수행하고 실제 범위를 명시한다.
- [ ] 동일한 최종 EXE로 기본기능 전체와 실시간 WU 전체를 순서대로 수행한다.
- [ ] WU 제외 3건의 ID와 기존 상태를 명시하고 나머지 10건이 PASS인지 판별한다. 실패를 SKIP으로 바꾸지 않는다.
- [ ] 새 컨텍스트 리뷰 후 필요한 수정은 재검증·재빌드·동일 EXE 전체 실행으로 확인한다.
- [ ] 문서/CHANGELOG/progress 갱신, 공개 diff 검사, 관련 파일만 커밋·푸시한다.
- [ ] 터미널에 설치 위치·해시·commit·검증 환경·TC별 결과·미완료 조건을 자세히 남긴다.
