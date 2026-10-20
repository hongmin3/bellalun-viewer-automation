# 다른 PC·Windows 11 LTSC 호환성 검증 (2026-10-18)

이 문서는 "어느 PC, 어느 경로, Windows 11 LTSC에서도 기본기능 자동화와 Windows Update 체크리스트가
동작하는가"를 이 PC에서 확인할 수 있는 범위까지 검증한 기록이다. 확인하지 못한 항목은 마지막 절에 따로 둔다.

## 검증 대상

| 항목 | 값 |
|---|---|
| 설치판 | BellalunAuto 1.0.0 후보9, 소스 `f8d97e5`, EXE SHA256 `761c59af450168f69dcece70c53b7c1998a18cec922758b470bc3688f609bc81` |
| 이 PC | Windows 11 Pro 26200(25H2), 한국어 UI, 관리자 계정, Python·Git 설치됨 |
| 비교 근거 PC | Windows 11 IoT Enterprise LTSC 26100(24H2), 영어 UI (2026-10-15 원래 PC 실측) |

## 1. LTSC 실측 근거 (원래 PC)

원래 PC의 OS는 `Microsoft Windows 11 IoT Enterprise LTSC 10.0.26100`이었다.
같은 엔진의 이전 설치판(후보5·후보6)으로 다음을 실제로 수행했다.

| 실행 | 결과 |
|---|---|
| 후보5 설치판 기본기능 전체 | 27 TC: PASS 23 / FAIL 2 / MANUAL 2 |
| 후보6 설치판 기본기능 전체 | 27 TC: PASS 23 / FAIL 2 / MANUAL 2 |
| 후보5 설치판 실시간 WU 전체 | 끝까지 완료. PASS 9 / FAIL 1 / MANUAL 3 (FAIL은 이후 고친 WU10 판정) |

후보6 이후 바뀐 코드(최전면 확보, WF09 판정 범위, 경로 따옴표, 자체진단 항목)는 OS 에디션에 따라 달라지는 부분이 아니다.
LTSC 2024와 이 PC는 같은 Windows 11 24H2 서비스 기반(26100/26200)이다.

## 2. 코드 감사 (LTSC에 없을 수 있는 구성요소)

- OS 판별은 Caption에 `Windows 11`/`Windows 10`이 있는지만 본다. `Windows 11 IoT Enterprise LTSC`도 Win11로 판별된다.
- 외부 실행 의존은 `powershell`(Windows PowerShell 5.1), `net`, `sc`, `taskkill`, .NET Framework `System.Data.SqlClient`뿐이다.
  모두 LTSC를 포함한 Windows 10/11 모든 에디션의 기본 구성요소다.
- 스토어 앱, Windows Terminal, winget, Edge, 사진 앱 등 LTSC에서 빠지는 구성요소를 쓰지 않는다.

## 3. 배포 파일 DLL 의존성 전수 점검

`work/pe_audit.py`(pefile)로 배포 폴더의 PE 파일 31개 전부의 import와 지연 로드 import를 분류했다.

| 분류 | 건수 |
|---|---|
| 배포 폴더 안의 DLL | 59 |
| Windows 기본 DLL(21종: kernel32, user32, advapi32, ws2_32 등) | 73 |
| UCRT·코어 API Set(api-ms-win-crt-*, api-ms-win-core-path) | 133 |
| 해결되지 않는 DLL | 0 |

PE 파일은 모두 x64다. VC 런타임(vcruntime140, vcruntime140_1)은 배포 폴더에 있고 UCRT는 Windows 10부터 OS 구성요소다.

## 4. 경계 조건 시험 (후보9 설치판, 제품 조작 없음)

`work/edge_cases.py`로 수행했다. 개발 도구 없는 환경(`clean_environment`)은 PATH를 Windows 기본값만 두고
Python·Git·Node 변수를 빼며, PYTHONHOME/PYTHONPATH를 없는 경로로 채운다.

| 시험 | 조건 | 결과 |
|---|---|---|
| E1 | 최소 환경, 특수문자 CWD·작업 폴더(`검증 & 테스트 (1) O'Brien %TEMP% #한글`) | `--version` exit 0, 자체진단 21/21, portability-check 21/21 |
| E2 | 포터블 ZIP을 같은 특수문자 경로에 풀어 실행, stdin 파이프 | `--version` exit 0, 자체진단 21/21 |
| E3 | 없는 Viewer·Tesseract 경로, 없는 SQL 인스턴스 | 해당 3개 항목만 FAIL과 한국어 해결 방법, 비정상 종료 없음 |
| E4 | 120자를 넘는 작업 폴더 | "작업 폴더 경로 길이" 항목만 FAIL |
| E5 | 일반 사용자 권한(`runas /trustlevel:0x20000`) | 관리자 권한 항목만 FAIL, 나머지 20 PASS |

실행 중 BellalunAuto 프로세스가 불러온 모듈은 모두 설치 폴더 또는 `C:\WINDOWS\SYSTEM32`였다.
PC에 설치된 Python·Git의 DLL은 불러오지 않았다.

## 5. 이번 점검에서 고친 결함

| 결함 | 증상 | 수정 |
|---|---|---|
| 경로의 작은따옴표 | 기준 DB RESTORE/BACKUP과 PowerShell 버전·서명 조회가 문법 오류 | `b0c1e9d`. 실측 확인 |
| 긴 작업 폴더 경로 | LongPathsEnabled=0(기본값)에서 Viewer Export 증거가 260자를 넘어 실행 중간 실패 가능 | `f8d97e5` 자체진단 항목 추가 |

## 6. 최소 환경 전체 실행 (후보9)

후보9로 `tools/run_installed_suites.py --clean-env`를 2026-10-18 13:54에 시작했지만 약 1분 뒤 PC가 꺼져 실행이 끝나지 않았다.

| 근거 | 내용 |
|---|---|
| Viewer 로그 13:55:24 | `Failed to initialize XIPL. XIPL is not installed. [E2100]` |
| System 이벤트 1074 13:55:34 | `VIEWER.exe`가 컴퓨터 전원 끄기를 시작함 |
| `VIEWER.exe` 문자열 | `XIPL_PATH`, `%s\SERVER_X64`, `%s\XIPL.KEEPALIVE.exe` |

최소 환경은 PATH와 일부 변수만 남겼고, XIPL 설치가 등록한 시스템 환경 변수 `XIPL_PATH`도 빠졌다.
Viewer는 이 값으로 XIPL을 찾으므로 초기화에 실패하고 PC를 껐다. 기존 자체진단은 XIPL을 9784 포트로만 봐서 21/21 PASS였다.

개발 도구 없는 실제 PC에도 `XIPL_PATH`는 있다. 그러나 오래된 셸·예약 작업처럼 줄어든 환경에서 BellalunAuto가
시작되면 같은 일이 생길 수 있어 2026-10-20에 제품 쪽을 고쳤다(CHANGELOG 2026-10-20).
Viewer·XIPL Studio는 빠진 등록 환경 변수를 레지스트리에서 보충해 띄우고, 그래도 `XIPL_PATH`가 맞지 않으면
Viewer를 띄우지 않는다. 최소 환경 시험 도구는 이 변수를 계속 빼서 보충 동작을 함께 검증한다.
수정판의 최소 환경 전체 실행 결과는 [진행 상태](../progress.md)에 기록한다.

## 7. 이 PC에서 검증할 수 없는 것

| 항목 | 이유 | 대체 근거 |
|---|---|---|
| Python·Git이 없는 실제 PC/VM | 이 PC에는 개발 도구가 있다 | 최소 환경 실행, 로드 모듈·DLL 의존성 점검 |
| Windows 11 LTSC 위에서의 후보9 실행 | 이 PC는 Pro 에디션 | 원래 PC(LTSC)의 후보5·6 전체 실행과 에디션 무관 코드 감사 |
| Windows 10 | 별도 OS 필요 | DLL 의존성은 Windows 10 기본 구성으로 해결됨 |
| 다른 관리자 계정·UAC 승인 화면 | 계정 생성은 PC 전체 변경, UAC 보안 화면은 자동 조작 불가 | 일반 권한 자체진단(E5) |
| 화면 배율 100% 외·1920×1080 외 | 배율 변경은 로그아웃 필요 | 자체진단이 두 항목을 FAIL로 안내 |
| 한글 사용자 계정 이름 | 계정 생성 필요 | 한글·특수문자 작업/설치 경로 시험 |

실제 LTSC PC에서는 같은 설치 파일로 `selfcheck` 후 `tools/run_installed_suites.py`로 두 전체 실행을 한 번 수행해 확인한다.
