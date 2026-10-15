# BellalunAuto 내부 배포

BellalunAuto 설치판은 Python·Git·개발 소스 없이 기존 기본기능 및 Windows Update 자동화를 실행한다.
Viewer·SQL Server·Tesseract OCR과 시험에 필요한 외부 서버/USB는 대상 QA PC에 별도로 준비한다.
설치 성공, 프로그램 기동, 제품 시험 성공은 각각 구분하여 기록한다.

2026-10-15 기준 실행·설정·진단과 내부 빌드 계층을 구현했다. 중간 단위시험과 USB 단독 실측을
수행했으며 최종 동일 EXE의 두 전체 실행, 설치 수명주기와 개발 도구 없는 환경 검증은 미완료다.
아래 설치 절차는 검증·승인된 내부 패키지를 전달받은 뒤 적용한다.

## 팀원 설치와 첫 실행

1. 배포 담당자가 제공한 `SHA256SUMS.txt`와 설치 파일 해시를 `Get-FileHash -Algorithm SHA256`으로 대조한다.
2. `BellalunAuto-<version>-setup.exe`를 실행한다. 관리자가 설치하며 드라이브와 설치 폴더를 선택할 수 있다.
3. 시작 메뉴의 BellalunAuto에서 설치 폴더 밖 쓰기 가능한 작업 폴더를 선택한다.
4. 설정에서 대상 PC의 Viewer/SQL/서버/OCR 경로와 값을 입력한다. 예시값은 대상 환경의 값으로 바꾼다.
5. 자체진단·환경 점검 후 기본기능 전체 또는 Windows Update 전체를 실행한다.
6. 작업 폴더의 Reports/Evidence에서 결과와 증거를 확인한다. FAIL/MANUAL/SKIP을 PASS로 해석하지 않는다.

설치 후 새 CMD/PowerShell의 `BellalunAuto --version`과 Win+R의 `BellalunAuto`를 사용할 수 있다.
기존 셸은 다시 열어 PATH 변경을 받는다. 기존 PATH의 같은 항목은 대소문자·인용부호·마지막 구분자를
정규화하여 중복 추가하지 않는다. 다른 PATH 항목의 순서와 문자열은 보존한다.
업데이트는 같은 AppId로 수행한다. 제거는 설치 프로그램이 추가했다고 기록한 PATH 토큰만 제거하며,
외부 작업 폴더의 설정·결과·증거를 지우지 않는다. 설치 직후 제품 시험은 자동 실행하지 않는다.

포터블 사용자는 ZIP을 전용 폴더에 풀고 `BellalunAuto.exe`를 실행한다.
포터블 실행은 PATH/App Paths를 등록하지 않는다. 다른 설치/포터블 실행과의 제품 조작 잠금은 공유한다.
작업 폴더를 프로그램 폴더 안에 두지 않는다.

## 빌드 환경과 명령

Windows x64 CPython **3.12.10**, Nuitka **4.3**, Inno Setup **6.7.3**을 사용한다.
지원 대상 OS는 Windows 10/11 x64이며 설치 프로그램은 최소 Windows 10을 요구한다.
현재 개발·검증 호스트는 Windows 11 IoT Enterprise LTSC(26100)이다.
Windows 10은 별도 호스트 검증이 아직 없으며 지원 대상과 실제 검증 범위를 구분한다.
Python 의존성 전체는 `packaging/requirements-build.txt`에서 고정한다.
Nuitka는 지정된 MinGW64를 사용하며 `--assume-yes-for-downloads`로 해당 컴파일 도구를 준비한다.
빌드 담당자가 사전에 도구를 설치한다. 스크립트는 Python 패키지나 Inno Setup을 자동 설치하지 않는다.

```powershell
python -m pip install -r packaging/requirements-build.txt
python tools/build_distribution.py --assets "D:\사내 배포 자료\approved-assets.json" --output "D:\사내 배포 결과\v1" --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

`--output`은 비어 있거나 아직 없는 전용 폴더여야 한다. 빌드 실패 후에는 기존 폴더를 재사용하지 않고
새 폴더를 지정한다. 로컬 내부 산출물 경로를 공개 Git 대상에서 제외한다.
프로그램은 경로를 인수 배열로 전달하므로 공백/한글과 다른 드라이브 경로를 지원한다.

소스 정적 검사 네 개와 `python -m pytest tests -q`를 먼저 실행한다.
원본 소스를 읽는 검사는 빌드 환경에서 수행하고 설치판 자체진단에서는 수행하지 않는다.
정적 검사 실패 시 빌드를 중단한다. Nuitka는 자체 `run`, `core`, `bellalunauto`와 실제 `tests/*.py`
TC 시나리오를 명시적으로 포함하며 `tests.test_*` 단위시험만 제외한다.
hide 모드는 기존 콘솔을 사용하고 새로 생성된 콘솔은 숨긴다. PE console subsystem을 사용하므로
새 PowerShell의 직접 실행·출력 리다이렉션·종료코드 대기가 동작한다. 빌드 시 실제 PE 헤더도 확인한다.
탐색기 실행에서 콘솔이 잠깐 보일 가능성은 Nuitka의 알려진 Windows 제한이며 실제 실행을 별도 확인한다.
컴파일 작업 수는 `--jobs=2`로 고정한다.

개발 진단용 `--skip-tests` 및 `--skip-compile --compiled-dir <standalone-folder>`는 생략 내역을
`build-info.json`에 남긴다. 소스 정적 검사와 자료·배포 경계 검사는 생략하지 않는다.
컴파일 재사용 시 `--compilation-report <nuitka-report.xml>`과 `--scons-report <scons-report.txt>`도
원래 컴파일의 파일로 지정해야 한다. Nuitka 버전·standalone 성공 여부와 실제 GCC 실행 파일을 검증한다.
기존 컴파일 재사용은 해당 바이너리와 현재 commit이 일치한다는 증거를 제공하지 않는다.
최종 배포는 두 옵션을 사용하지 않고 새로 빌드한다.

## 승인 자료 manifest

`packaging/assets-manifest.example.json`은 구조 설명용 불완전 템플릿이다.
실제 manifest는 공개 저장소 밖 로컬 파일로 작성한다.

- `schema_version`: `1`.
- `asset_version`: 전체 승인 자료 버전.
- `compatibility.viewer`, `compatibility.sql`: 허용 Viewer/SQL 버전 문자열 배열. 실제 제품 호환 승인 근거를 사용한다.
- `files`: 각 항목의 `source` 절대 파일 경로, `destination` assets 기준 상대 경로,
  `sha256` 파일 해시, `kind`, `version`을 지정한다. Baseline 외에는 `role`도 지정한다.

kind는 `checklist`(xlsx), `baseline`(bak), `knowledge` 또는 `manual`(pdf/docx)이다.
필수 role은 checklist의 `basic-checklist`, `windows-update-checklist`,
knowledge의 `specification1`, `specification2`, manual의 `operation-manual`,
`service-manual`, `dicom-conformance`이며 각 role을 한 번씩 포함한다.
체크리스트 두 개, 승인 시험 Baseline 네 개, 필수 사양 두 개와 매뉴얼 세 개를 포함한다.
Baseline 목적 경로는 아래 네 개만 허용한다.

```text
Baseline/DATA.bak
Baseline/ACCOUNT.bak
Baseline/CONFIGURATION.bak
Baseline/PROCEDURE.bak
```

체크리스트는 `checklists/Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`와
`checklists/Windows Update 호환성 검증 Checklist_Bellalun Viewer_R-25-782.xlsx`에 놓는다.
필수 사양·Operation/Service/DICOM 매뉴얼은 `지식/` 아래에 둔다.
장비 자체의 VDMS 문서 등 자동화에 필요 없는 원문은 포함하지 않는다.

파일별 manifest 예시는 다음과 같다. 해시는 승인한 실제 파일에서 계산한다.

```json
{
  "source": "D:/approved-assets/Baseline/DATA.bak",
  "destination": "Baseline/DATA.bak",
  "sha256": "64자리 파일 SHA256",
  "kind": "baseline",
  "version": "승인 자료 버전"
}
```

절대/상위 탈출/ADS/Windows 장치명 목적 경로, 링크/정션 원본, 대소문자 중복 목적지,
해시 불일치, 자체 코드, 개인 config, 환자/DICOM/현재 DB와 기존 결과·증거는 거부한다.
허용 목록은 담당자가 승인한 파일을 특정하기 위한 것이다. 백업 이름을 바꾸거나 해시를 계산한 사실만으로
시험용 익명 데이터 승인이 성립하지 않는다. 자료 버전과 호환성은 승인자가 확인한다.

## 산출물과 경계

배포 폴더에는 컴파일된 `BellalunAuto.exe`와 필요한 런타임, 중립화한
`resources/config.example.json`, scope/traceability, `resources/assets/`,
원본 절대 경로를 제거한 `resources/assets-manifest.json`, 사용 안내와 제3자 라이선스가 들어간다.
자체 Python 소스/바이트코드, 단위시험, Git, 디버그 심볼, 컴파일 중간파일,
현재 개인 설정·DB·환자자료·결과·증거를 포함하지 않는다.
명시된 제3자 패키지 디렉터리의 해당 패키지 자료와 라이선스는 허용한다.

빌드 출력은 다음과 같다.

- `BellalunAuto-<version>/`: 검사한 동일 standalone 배포 폴더.
- `BellalunAuto-<version>-portable.zip`: 동일 폴더를 담은 포터블 ZIP.
- `BellalunAuto-<version>-setup.exe`: 동일 폴더를 담은 설치 프로그램.
- `build-info.json`: 버전, 소스 commit/dirty 여부, 도구/전이 의존성 버전, 자료 버전/호환성,
  생략 내역, 파일 목록·크기·SHA256. 배포 폴더 안에도 동일 내용을 둔다.
  실제 MinGW64 GCC의 절대 경로·`--version`·target·실행 파일 SHA256, Nuitka/SCons 보고서의
  원본 경로와 SHA256, 애플리케이션 EXE 해시도 기록한다. 보고서 원문은 배포 폴더에 넣지 않는다.
  Tcl/Tk는 8.6.15이며 init/tk 스크립트와 DLL/`_tkinter.pyd` 존재·버전·해시를 확인한다.
- `SHA256SUMS.txt`: 설치 프로그램, ZIP, 외부 build-info의 SHA256.
- `compile/`, `compile.log`, `installer.log`: 빌드 담당자용 중간 산출물이며 배포하지 않는다.

build-info의 파일 목록은 자기 자신의 순환 해시를 제외한다. 외부 build-info의 해시는 SHA256SUMS에 기록한다.
Tcl/Tk 8.6.15, OpenSSL 3.0.16, zlib 1.3.1의 공식 태그에서 가져온 라이선스 원문은
`packaging/licenses/`에 공개 자료로 보관한다. OpenSSL에는 LICENSE와 AUTHORS 및 해당 태그 README의
저작권 고지를 포함한다(해당 태그에는 NOTICE 파일이 없다).
해당 폴더의 provenance.json에 출처 URL·버전·SHA256을 기록하고 검증 후 배포 라이선스 폴더로 복사한다.
사용자 입력 라이선스 파일이나 Tcl/Tk 소스 전체를 추가로 요구하지 않는다.
소스 commit이 같아도 dirty가 true면 검토한 수정 내용과 별도 검증 근거를 함께 남긴다.
내부 자료가 포함된 모든 산출물·manifest·중간 폴더는 공개 Git/Release에 올리지 않는다.

## 실제 배포 승인 기록

안전 단위시험은 자료 경계를 검증하며 제품을 조작하지 않는다.
별도 기록에 설치·재설치·업데이트·제거, 다른 드라이브/한글/공백/CWD,
새 CMD/PowerShell/Win+R, 사용자 자료 보존, Python/Git/소스 없는 PC 또는 VM의 실제 수행 범위를 남긴다.
최종 동일 EXE로 기본기능 전체와 실시간 WU 전체를 각각 수행하고 TC별 결과와 해시를 기록한다.
WU_01/12/13은 기존 수동 범위로 구분하고 나머지 열 건의 PASS 여부를 명시한다.
빌드·설치·기동만으로 제품 시험 검증 완료라고 기록하지 않는다.

설계 근거: [Nuitka standalone 및 동적 import](https://nuitka.net/user-documentation/use-cases.html),
[Nuitka Windows 콘솔/MinGW64](https://nuitka.net/user-documentation/user-manual.html),
[Inno Setup 64비트 아키텍처](https://jrsoftware.org/ishelp/topic_setup_architecturesallowed.htm),
[Inno Setup Registry](https://jrsoftware.org/ishelp/topic_registrysection.htm).
