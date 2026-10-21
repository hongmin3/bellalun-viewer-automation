# 다른 PC·Windows 11 LTSC 호환성 검증 (2026-10-18~21)

이 문서는 "어느 PC, 어느 경로, Windows 11 LTSC에서도 기본기능 자동화와 Windows Update 체크리스트가
동작하는가"를 이 PC에서 확인할 수 있는 범위까지 검증한 기록이다. 확인하지 못한 항목은 마지막 절에 따로 둔다.

## 검증 대상

| 항목 | 값 |
|---|---|
| 설치판 | BellalunAuto 1.0.0 후보11, 소스 `56a0bc6`, EXE SHA256 `2eb31efe2bc19a9ce92086f283f8e1e82e0bf9e92d852e7bf408648f9bb736f3` |
| 이전 판 | 후보9 `f8d97e5`(최소 환경 실행 중 PC 꺼짐), 후보10 `20bf2f7`(최소 환경 실행 결함 2건 발견) |
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

## 4. 경계 조건 시험 (후보11 설치판, 제품 조작 없음)

`work/edge_cases.py`로 수행했다. 개발 도구 없는 환경(`clean_environment`)은 PATH를 Windows 기본값만 두고
Python·Git·Node 변수를 빼며, PYTHONHOME/PYTHONPATH를 없는 경로로 채운다.

| 시험 | 조건 | 결과 |
|---|---|---|
| E1 | 최소 환경, 특수문자 CWD·작업 폴더(`검증 & 테스트 (1) O'Brien #한글`) | `--version` exit 0, 자체진단 23/23, portability-check 23/23 |
| E2 | 포터블 ZIP을 같은 특수문자 경로에 풀어 실행, stdin 파이프 | `--version` exit 0, 자체진단 23/23 |
| E3 | 없는 Viewer·Tesseract 경로, 없는 SQL 인스턴스 | 해당 3개 항목만 FAIL과 한국어 해결 방법, 비정상 종료 없음 |
| E4 | 120자를 넘는 작업 폴더 | "작업 폴더 경로 길이" 항목만 FAIL |
| E5 | 일반 사용자 권한(`runas /trustlevel:0x20000`) | 관리자 권한 항목만 FAIL, 나머지 22 PASS |
| E6 | 작업 폴더 경로에 `%` (`검증 %TEMP% 폴더`) | 자체진단은 "작업 폴더 경로 문자"만 FAIL, `run-regression`은 UI 조작 전에 exit 2로 거부 |

실행 중 BellalunAuto 프로세스가 불러온 모듈은 모두 설치 폴더 또는 `C:\WINDOWS\SYSTEM32`였다.
PC에 설치된 Python·Git의 DLL은 불러오지 않았다.

## 5. 이번 점검에서 고친 결함

| 결함 | 증상 | 수정 |
|---|---|---|
| 경로의 작은따옴표 | 기준 DB RESTORE/BACKUP과 PowerShell 버전·서명 조회가 문법 오류 | `b0c1e9d`. 실측 확인 |
| 긴 작업 폴더 경로 | LongPathsEnabled=0(기본값)에서 Viewer Export 증거가 260자를 넘어 실행 중간 실패 가능 | `f8d97e5` 자체진단 항목 추가 |
| 실행 환경의 `XIPL_PATH` 누락 | Viewer가 E2100 뒤 PC 전원을 끔(후보9) | `20bf2f7` 등록 환경 변수 보충, 없으면 Viewer 기동 차단, 자체진단 항목 |
| 작업 폴더 경로의 `%` | Windows 저장 대화상자가 `%TEMP%`를 바꿔 읽어 WF14 Export 거부(후보10) | `83a07da` 실행 전 거부, 자체진단 항목 |
| 늦게 열린 Export Manager | WU_09 실패 뒤 남은 창이 WU_10·WU_11 로그인을 막음(후보10) | `56a0bc6` 대기 60초, Viewer 재기동 전 정리 |

## 6. 최소 환경 전체 실행

모두 `tools/run_installed_suites.py --clean-env`로 수행했다. 설치·작업 폴더 밖 실행 폴더에서, 설치 파일 1004개를
build-info와 대조한 뒤 실행했다. USB는 세 실행 모두 분리 상태였다.

| 실행 | 결과 | 판단 |
|---|---|---|
| 후보9 (10-18 13:54) | 약 1분 뒤 PC가 꺼져 중단 | Viewer 로그 `XIPL is not installed. [E2100]`, System 이벤트 1074(`VIEWER.exe` 전원 끄기). 최소 환경이 `XIPL_PATH`까지 지웠다 |
| 후보10 기본기능 (10-20 17:28~19:16) | 27 TC: PASS 23 / FAIL 2 / MANUAL 2 | WF14는 작업 폴더의 `%TEMP%` 때문에 Export 거부, XIPL03은 기존 제품 결함 |
| 후보10 실시간 WU (19:16~20:20) | 13 TC: PASS 7 / FAIL 3 / MANUAL 3 | WU_09 Export Manager 20초 초과, 남은 창 때문에 WU_10·WU_11 로그인 실패 |
| 후보11 기본기능 (10-20 21:17~23:22) | 27 TC: PASS 23 / FAIL 2 / MANUAL 2 | FAIL은 기존 제품 결함 WF14 UPS·XIPL03뿐이며 후보8과 같다 |
| 후보11 실시간 WU (23:22~10-21 01:03) | live, chain_completed=true. 13 TC: PASS 10 / MANUAL 3 | WU 목표 충족. WU_09의 USB 왕복 단계는 `이동식 드라이브 없음`으로 SKIP |
| 후보11 실시간 WU, USB 연결 (10-21 18:27~20:16) | live, chain_completed=true. 13 TC: PASS 10 / MANUAL 3, SKIP은 CD 1건 | 이전과 다른 USB(`VXVUE1`, FAT32 14.6GB)로 WU_09 USB Export·Import 되읽기 PASS |

후보11 실행의 작업 폴더는 `C:\BellalunAuto 작업 공간\후보11 검증 & 테스트 (1) O'Brien #한글`이다.
Viewer는 최소 환경에서도 E2100 없이 기동했고 전원 끄기 이벤트는 없었다.

| 근거 파일(후보11) | SHA256 |
|---|---|
| `Result_20261020_232159.json` (기본) | `b608ef2249d5c25b52dc12fc66c298fc48183a72a76d3017cccd66a11dab4862` |
| `Result_WindowsUpdate_20261021_010312.json` (WU) | `1ea800a4147aab2c563c55e0a583f889820ade893bbda9f36484395ee21dabda` |
| `verification.json` (실행 기록) | `cb8dc03a60de87f95cb2fe67b8a6f1bf094baf01603cd2fead685ef4f2f083a7` |
| `Result_WindowsUpdate_20261021_201620.json` (USB 연결 WU) | `d9bdd4a692ec799feec6278ba943824dd51a5c9e1866a2da86b6d5f4e971058a` |
| `verification.json` (USB 연결 WU 실행 기록) | `2265ff6eb7c91a06149b46d72919de74edd52bca43eea485bb90c3cea98c67fd` |

실행 기록은 `C:\BellalunAuto 실행 기록\후보11-cleanenv-20261020_211748`이다(사내 PC 로컬, Git 제외).
보존본 해시 대조는 기본 288개, WU 245개 모두 일치했다. USB 연결 WU 실행 기록은 `C:\BellalunAuto 실행 기록\후보11-usb-wu-20261021_182716`이고 보존본 247개가 일치했다.

> **참고** USB가 `D:`로 잡히면 제품의 UPSHandler(V1.0.2.2)가 Viewer 기동과 함께 `D:\BellalunData\Log\UPSHandler`에 로그를 쓴다. 자동화의 데이터 폴더(`C:\BellalunData`)와 무관한 제품 동작이다. 자동화는 USB에 `BellalunWU09`만 만들고, 기존 폴더는 건드리지 않았다.

## 7. 이 PC에서 검증할 수 없는 것

| 항목 | 이유 | 대체 근거 |
|---|---|---|
| Python·Git이 없는 실제 PC/VM | 이 PC에는 개발 도구가 있다 | 최소 환경 실행, 로드 모듈·DLL 의존성 점검 |
| Windows 11 LTSC 위에서의 후보11 실행 | 이 PC는 Pro 에디션 | 원래 PC(LTSC)의 후보5·6 전체 실행과 에디션 무관 코드 감사 |
| Windows 10 | 별도 OS 필요 | DLL 의존성은 Windows 10 기본 구성으로 해결됨 |
| 다른 관리자 계정·UAC 승인 화면 | 계정 생성은 PC 전체 변경, UAC 보안 화면은 자동 조작 불가 | 일반 권한 자체진단(E5) |
| 화면 배율 100% 외·1920×1080 외 | 배율 변경은 로그아웃 필요 | 자체진단이 두 항목을 FAIL로 안내 |
| 한글 사용자 계정 이름 | 계정 생성 필요 | 한글·특수문자 작업/설치 경로 시험 |

실제 LTSC PC에서는 같은 설치 파일로 `selfcheck` 후 `tools/run_installed_suites.py`로 두 전체 실행을 한 번 수행해 확인한다.
