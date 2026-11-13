# BellalunAuto 내부 배포

BellalunAuto 설치판은 Python·Git·개발 소스 없이 기존 기본기능 및 Windows Update 자동화를 실행한다.
Viewer·제품 SQL/Server/XIPL과 시험에 필요한 외부 서버/USB는 대상 QA PC에 준비한다. 새 Setup은 OCR을 자동 준비하고 승인 Baseline·체크리스트·매뉴얼을 포함한다.
설치 성공, 프로그램 기동, 제품 시험 성공은 각각 구분하여 기록한다.

**현재 설치판은1.0.11이며1.0.13 후보 Setup·설치용 ZIP을 준비했다.** 공용 보존·차이 복원과 판정 수정의 실제 SMB/설치판 수용은 남아 있다. [최신 검증 범위](practical-preservation-validation.md)와 progress.md를 따른다. 아래1.0.3~1.0.5 기록은 역사 자료이며 현재 설치 상태를 뜻하지 않는다.

기존1.0.3·1.0.4 Setup·ZIP과 각 실행판 보관본은 해시 일치를 확인했다. 1.0.4의 승인된 업데이트·기본27 TC·실시간WU13 TC 각1회는 기본PASS19/FAIL6/MANUAL1/SKIP1·WU PASS9/FAIL1/SKIP3으로 게이트 거부다. [1.0.4 기록](reliability-2026-11-10.md), 이전1.0.3 [OCR 검증](ocr-release-validation.md), 1.0.2 [설치 준비](setup-preparation-validation.md)는 당시 범위의 근거다.

이 안내서는 설치·설정·실행 방법을 설명한다. 전달받은 패키지의 실제 검증 범위는
별도 배포 승인 기록의 실행파일 SHA256, 승인받은 범위의 시험 결과와 설치 기록으로 확인한다.
`build-info.json`은 빌드 정보를 담으며 빌드 성공만으로 설치·제품 시험 성공을 뜻하지 않는다.
아래 절차는 검증·승인된 내부 패키지를 전달받은 뒤 적용한다.

## 팀원 설치와 첫 실행

Setup은 파일 복사 뒤 OCR 실행·언어 파일과 승인 자료 SHA-256을 확인한다. OCR이 없으면 포함된 고정 설치 파일로 준비하므로 대상 PC에서 인터넷은 필요하지 않다. 정상 기존 OCR은 재사용한다. 완료 화면과 `작업/install-preparation.txt`에서 결과를 읽고, 실패하면 원인을 해결한 뒤 관리자 권한으로 `BellalunAuto prepare-install`을 다시 실행한다. 실패한 Setup 종료 코드는3이다.

빌드 PC에서는 `packaging/components.json`의 공식 고정 OCR 파일을 받아 해시를 검사한다. 오프라인 빌드는 `--ocr-installer <설치 파일>`로 지정한다. 실행 패키지는 Setup으로 만들고 필요하면 설치용 릴리즈 ZIP으로 묶는다.

신규 PC 설정에는 탐지한 제품 경로와 OCR·Baseline 경로가 저장된다. 기존 설정은 그대로 보존하며 잘못된 OCR·Baseline 경로는 PC별 설정에서 수정한다. Baseline은 설치 폴더의 승인 백업 파일4개를 준비하는 뜻이며 설치 중 사용자 DB를 복원하지 않는다. 기존 전체 회귀 통과 기록은 해당 EXE에 한정하며 새 후보의 제품 회귀는 별도다.

1. 배포 담당자가 제공한 `SHA256SUMS.txt`와 설치 파일 해시를 `Get-FileHash -Algorithm SHA256`으로 대조한다.
2. `BellalunAuto-<version>-setup.exe`를 실행하고 UAC에서 [예]를 누른다. UAC를 취소하거나 관리자 권한을 얻지 못하면 설치하지 않는다(화면 동작은 아래 실측 기록).
3. 완료 화면의 "BellalunAuto 열기"(설치를 시작한 사용자 권한) 또는 시작 메뉴에서 연다. 작업 폴더·설정 창은 뜨지 않는다.
4. 첫 실행은 이 PC의 Viewer·데이터 폴더·SQL·XIPL·OCR 위치를 찾아 저장하고 준비 점검을 바로 보인다. 서버 주소·계정은 이 PC의 기존 BellalunAuto 설정에서만 가져오고, 없으면 [PC별 설정]에서 입력한다.
5. [준비 점검]의 첫 줄이 "시험을 시작할 수 있습니다"인지 본다. 그 뒤 기본기능 전체 또는 Windows Update 전체를 실행한다.
   시험을 시작할 때 UAC로 관리자 권한을 요청한다. 취소하면 시험을 시작하지 않는다(REQ-DIST-006).
6. 설치 폴더 아래 `작업`(기본 `C:\Program Files\BellalunAuto\작업`)의 Reports/Evidence/Log에서 결과를 확인한다. 리포트 맨 위 "결론 — 한눈에 보기"를 먼저 읽는다. FAIL/MANUAL/SKIP을 PASS로 해석하지 않는다.

설치 후 새 CMD/PowerShell의 `BellalunAuto --version`과 Win+R의 `BellalunAuto`를 사용할 수 있다.
기존 셸은 다시 열어 PATH 변경을 받는다. 기존 PATH의 같은 항목은 대소문자·인용부호·마지막 구분자를
정규화하여 중복 추가하지 않는다. 다른 PATH 항목의 순서와 문자열은 보존한다.
업데이트는 같은 AppId로 같은 위치에 수행하고, 설치 폴더의 `resources`는 새 판으로 통째로 바꾼다. 제거는 설치 프로그램이 추가했다고 기록한 PATH 토큰만 제거하며,
`작업` 폴더의 설정·결과·증거를 지우지 않는다. Setup은 `작업` 폴더에만 Users 수정 권한을 준다. 설치 직후 제품 시험은 자동 실행하지 않는다.

포터블 ZIP은 생성·배포하지 않는다. 팀원은 Setup을 사용한다. 2026-11-09 요청부터 Setup·build-info·체크섬·후보 표식·사용 안내를 묶는 설치용 릴리즈 ZIP을 지원한다.

```powershell
python tools/release_zip.py --release release/1.0.3 --output <새 폴더>/BellalunAuto-1.0.3-release.zip
```

입력 폴더는 Setup 빌더가 만든 버전별 폴더다. 추가 파일·변조·누락·기존 ZIP 덮어쓰기를 거부한다.
후보 표시를 보존하고 ZIP CRC·내부 모든 파일 SHA-256을 검사한다. ZIP은 사내 자료를 포함하므로 공개 Release에 올리지 않는다.
OCR 환경 지문과 실패 해결은 [OCR 안내](ocr-portability.md)를 따른다.

## 빌드 환경과 명령

후보8의 WF_02 조기 판정은 [촬영 대기 조사](wf02-acquisition-investigation.md)에서 원인과 미확정 범위를 구분했다. 수정 후보는 새 그룹의 Raw/Recon/Syn 완료 대기를 사용한다. 후보9의 두 전체에서는 WU_09 제품 충돌로 게이트가 거부됐으나, 이후 소스173eb3c 설치판의 WU 전체는 PASS10/SKIP3·WU 게이트14개 통과였다. 기본기능 전체의 새 실행은 수행하지 않았다. 상세는 [WU 검증](wu-installed-validation.md)과 [이전 WU_09 조사](wu09-export-crash-investigation.md)를 따른다.

Windows x64 CPython **3.12.10**, Nuitka **4.3**, Inno Setup **6.7.3**을 사용한다.
지원 대상 OS는 Windows 10/11 x64이며 설치 프로그램은 최소 Windows 10을 요구한다.
최근 후보(후보8·10·11)의 빌드와 전체 실행 호스트는 Windows 11 Pro(빌드 26200)이다.
Windows 11 IoT Enterprise LTSC(26100) 실측은 후보5·6까지이며 후보7 이후는 LTSC에서 실행하지 않았다.
Windows 10은 별도 호스트 검증이 아직 없으며 지원 대상과 실제 검증 범위를 구분한다.
검증된 호스트 목록은 `verified_environments.json`이고, 실시간 WU 실행 전 점검이 실행 PC와 대조해
미등록 환경을 WARN으로 리포트에 남긴다(판정은 막지 않는다).
Python 의존성 전체는 `packaging/requirements-build.txt`에서 고정한다.
Nuitka는 지정된 MinGW64를 사용하며 `--assume-yes-for-downloads`로 해당 컴파일 도구를 준비한다.
빌드 담당자가 사전에 도구를 설치한다. 스크립트는 Python 패키지나 Inno Setup을 자동 설치하지 않는다.

```powershell
python -m pip install -r packaging/requirements-build.txt
python tools/build_distribution.py --assets "D:\사내 배포 자료\approved-assets.json" --output "D:\사내 배포 결과\v1" --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

빌드 PC 준비 예시는 다음과 같다(2026-10-17 두 번째 PC에서 확인).
Inno Setup은 관리자 설치 없이 사용자 범위로 설치할 수 있다. Python 패키지는 Git 제외 가상환경에 둔다.

```powershell
winget install --id JRSoftware.InnoSetup --version 6.7.3 --exact --silent --override "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CURRENTUSER"
python -m venv work\buildenv
work\buildenv\Scripts\python.exe -m pip install -r packaging/requirements-build.txt
work\buildenv\Scripts\python.exe tools/build_distribution.py --assets <승인 manifest> --output <빈 폴더> --iscc "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
```

### 릴리스 게이트 (REQ-DIST-005)

소스에서는 단위시험·정적 검사만 수행하고 검증용 후보를 빌드한다. 소스의 기본기능·WU UI 전체 실행을 빌드의 선행조건으로 요구하지 않는다.

```powershell
python tools/build_distribution.py --assets <승인 manifest> --output <빈 폴더> --iscc <ISCC.exe>
```

설치 뒤 [변경 영향별 검증 기준](testing-guide.md)에 따라 사용자에게 UI 범위를 승인받고 해당 EXE로 한 번 수행한다. 아래 `--scope`는 `both`, `basic`, `wu`, `tc` 중 승인받은 범위다. 단독 TC는 `--expected-tc <ID>`도 지정한다.

```powershell
python tools/release_gate.py --installed-verification <verification.json> --scope wu --commit <빌드 SHA> --output <새 배포 승인 기록.json>
```

설치판 게이트는 다음을 모두 만족해야 통과한다.

- EXE·설치 파일·build-info가 시험 때와 같고 컴파일·소스 시험을 생략하지 않았다. 선택한 실행이 완료됐으며 새 리포트의 해시·명령이 기록과 같다.
- 선택한 리포트의 `source_commit`이 빌드 커밋과 같고 `source_dirty`가 `false`, 출처가 `build-info`다. 소스 실행 결과를 설치판 결과로 받지 않는다.
- WU를 선택했으면 실시간 실행(`live`)이고 `chain_completed`가 참이며 PASS 10 / SKIP 3(사람이 직접 하는 WU_01·12·13)이다.
- 기본기능을 선택했으면 전체 회귀이며 `KNOWN_DEFECT_EXCLUDE` 밖의 FAIL·BLOCKED가 없다. 단독 TC는 지정 TC를 모두 수행했는지와 같은 FAIL·BLOCKED·사람 전용 SKIP 기준을 확인한다.

선택하지 않은 묶음의 리포트는 요구하지 않는다. 시험 범위·미수행 범위와 선택 이유를 승인 기록과 함께 전달한다. 통과한 EXE·설치 파일을 다시 빌드하거나 build-info를 고치지 않는다. 후보 파일명은 그대로 두고 `--output`으로 만든 배포 판정 기록을 함께 전달한다. `build-info.release_gate`는 빌드 당시의 상태이며 최종 설치판 검증은 별도 기록으로 확인한다.

설치판 검증 전 산출물 이름에는 `-candidate`가 붙고
`게이트-미통과-후보.txt`와 build-info의 `release_gate`에 사유가 남는다.

기존 `tools/release_gate.py --wu <WU json> --basic <기본 json> --commit <SHA>` 및 빌드의 `--gate-wu --gate-basic`은 과거 전체 회귀 기록 호환용이다. 이 경로를 새 작업의 필수 선행조건으로 사용하지 않는다.

> **참고** 2026-11-04 전의 리포트에는 `source_commit`이 없어 게이트가 거부한다. 후보11 결과도 이 사유 하나로 거부된다.

저장소가 한글 경로(예: `C:\자동화\...`) 아래에 있어도 빌드할 수 있다.

`--output`은 비어 있거나 아직 없는 전용 폴더여야 한다. 빌드 실패 후에는 기존 폴더를 재사용하지 않고
새 폴더를 지정한다. 로컬 내부 산출물 경로를 공개 Git 대상에서 제외한다.
프로그램은 경로를 인수 배열로 전달하므로 공백/한글과 다른 드라이브 경로를 지원한다.

소스 정적 검사 네 개와 `python -m pytest tests -q`를 먼저 실행한다.
원본 소스를 읽는 검사는 빌드 환경에서 수행하고 설치판 자체진단에서는 수행하지 않는다.
정적 검사 실패 시 빌드를 중단한다. Nuitka는 자체 `run`, `core`, `bellalunauto`와 실제 `tests/*.py`
TC 시나리오를 명시적으로 포함하며 `tests.test_*` 단위시험만 제외한다.
attach 모드와 Windows GUI 실행 파일(PE subsystem 2)을 사용해 탐색기·바로가기 실행에서 콘솔을 새로 만들지 않는다. 기존 콘솔에서 CLI로 호출하면 해당 콘솔을 사용한다. 빌드 시 실제 PE 헤더도 확인한다.
PowerShell은 GUI 실행 파일의 종료를 자동으로 기다리지 않을 수 있으므로 CLI는 파이프로 호출한다.

```powershell
& 'C:\Program Files\BellalunAuto\BellalunAuto.exe' --version | Out-Default
$LASTEXITCODE
```

파일로 결과를 받거나 명시적으로 기다릴 때는 `Start-Process -Wait -PassThru`와 출력 리다이렉션을 사용한다. 설치판 검증 도구와 프로그램 내부 worker 호출은 기존처럼 파이프를 수집하고 프로세스 종료를 기다린다. 준비 점검·DB·서비스 명령·환경 수집의 콘솔 자식은 `CREATE_NO_WINDOW`로 실행한다. 실제 첫 GUI 표시는 다른 자동화가 화면을 쓰지 않을 때 별도로 확인한다.
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

최종 배포 파일은 `release/<version>/`에 둔다. 같은 버전 폴더가 비어 있지 않으면 컴파일 전에 중단하므로 다음 배포는 버전을 올린다. 컴파일·검증에 쓰는 `--output`은 이 폴더와 구분한다. 현재 파일은 [설치 준비 검증](setup-preparation-validation.md)을 따른다.

빌드 출력은 다음과 같다. Setup·외부build-info·SHA256SUMS와 후보 표식만 `release/<version>/`로 옮긴다. standalone 폴더와 중간파일은 `--output`에 남는다.

- `BellalunAuto-<version>/`: 검사한 동일 standalone 배포 폴더.
- `BellalunAuto-<version>-setup.exe`: 동일 폴더를 담은 설치 프로그램.
- `build-info.json`: 버전, 소스 commit/dirty 여부, 도구/전이 의존성 버전, 자료 버전/호환성,
  생략 내역, 파일 목록·크기·SHA256. 배포 폴더 안에도 동일 내용을 둔다.
  실제 MinGW64 GCC의 절대 경로·`--version`·target·실행 파일 SHA256, Nuitka/SCons 보고서의
  원본 경로와 SHA256, 애플리케이션 EXE 해시도 기록한다. 보고서 원문은 배포 폴더에 넣지 않는다.
  Tcl/Tk는 8.6.15이며 init/tk 스크립트와 DLL/`_tkinter.pyd` 존재·버전·해시를 확인한다.
- `SHA256SUMS.txt`: 설치 프로그램과 외부 build-info의 SHA256.
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

### 첫 사용자 QA 흐름과 인수표

새 QA 흐름의 설치·업데이트·제거·자료 보존, Windows 10/11/LTSC와 계정별 실제 확인 범위는 [설치판 인수표](installation-acceptance.md)에 기록한다. 과거 후보의 실측과 현재 후보의 결과를 구분하고, 아직 실행하지 않은 조건은 미완료로 둔다.

화면의 자동화 선택 항목은 "기본기능 체크리스트 자동화 수행"과 "Windows Update 체크리스트 자동화 수행"이다. 선택한 체크리스트만 수행한다. 시작 전 대상 Viewer·SQL·Baseline, 바뀌는 것과 복구 정책을 확인하고 "위 변경에 동의합니다"를 직접 체크한다. 취소하면 시험을 시작하지 않는다. 이후 UAC는 실행 권한 요청이며 변경 동의를 대신하지 않는다.

실행 번호별 `작업\Runs\<run_id>\run.json`에 계획·동의·진행·상태·이번 보고서 연결이 남는다. 자동 실행이 끝나면 결론과 다음 행동을 확인하고 [수동 검토]에서 PASS 아닌 TC의 검토 결과·의견·결함 번호를 기록한다. 검토자 이름과 모든 대상 검토가 있어야 검수 완료로 기록한다. 자동 판정과 원본 보고서는 그대로 둔다.

[공유 ZIP]에서는 스크린샷·DICOM·Viewer 로그의 공유 범위를 고른다. 설정·비밀번호는 제외하고, 선택한 보고서와 검토 기록·증거를 상대 링크와 manifest로 묶는다. 다른 PC의 한글·공백 경로에서 인터넷 없이 링크가 열리는 실제 인수는 단위시험과 별도로 확인한다. 준비 실패는 [준비 점검]의 행별 해결 방법과 설정 화면 열기를 이용하고, 사람이 수정한 뒤 [다시 점검]한다. 기존 환경 gate는 유지된다.

후보6 당시에는 소스 `76d218a1978e6df84457ee0544bd47a77258c7e1`·dirty=false에서 팀 설정 포함 WMI 빌드(종료0)를 마쳤다. 전체 단위시험 776 passed/4 skipped/265 subtests, 정적7종·readiness와 독립 검토를 확인했다. 실제 GUI PE2/attach이며 콘솔 없는 부모에서 버전·공유 ZIP 출력과 정상0/누락·변조·추가 각각1, PowerShell 파이프 대기를 확인했다. Windows 11 Pro 같은 High 관리자 계정에서 후보4→후보6 무창 업데이트 후 설치 EXE 해시, Users 수정 권한, 두 공용 바로가기, 기존 통제 파일 보존을 확인했다. 전체 해시와 미완료 조건은 인수표를 따른다. 후보6의 해당 기록 시점에는 Explorer GUI·첫 자동 설정·UAC 취소·제품 회귀가 미확인이었다. 이후 후보7~9 결과와 구분한다.

후보6은 바로가기 실행의 준비 점검이 `OSError`로 실패했다. 이를 고친 후보7은 소스 `ee43d7df7b8f69a3ca8a80654d07e0f086925211`·dirty=false에서 팀 설정 포함 WMI 빌드(종료0)를 마쳤다. 소스 전체 단위시험 782 passed/2 skipped/265 subtests, 정적7종·readiness와 독립 검토를 확인했다. 후보6→후보7 무창 업데이트 후 Explorer 실행의 준비 점검 23행 표시를 확인했다. 이 PC의 TCP 표 이상으로 XIPL 9784 gate가 FAIL이라 제품 회귀는 아직 실행하지 않았다. 배포 게이트는 미통과다.

이후 gate 조건은 유지하고 측정 방법만 바꾼 후보8(소스 `7d5b1fa9d75816fe7f7d6112922cd7b6f1059a0f`·dirty=false, 팀 설정 포함 WMI 빌드 종료0)을 설치해 두 전체를 한 번 실행했다. 기본기능 PASS 22/FAIL 3/MANUAL 1/SKIP 1, WU PASS 10/SKIP 3이다. 배포 게이트는 기본기능 `WF_02` 3D-W 픽스처 단계 FAIL 1건으로 거부됐다. 상세는 인수표.

후보9는 소스 `44052ec`·dirty=false로 빌드·업데이트했다. compile/tests 생략 없이798개 시험을 통과했고 설치파일1007개 불일치0·작업파일325개 해시 보존·준비23행·새 콘솔0을 확인했다. 설치판 기본기능 PASS23/FAIL2/MANUAL1/SKIP1(122.9분), WU PASS9/FAIL1/SKIP3(106.4분)이다. WF_02는 통과했고 기존 기본기능 허용 결함 외의 실패는 WU_09 제품 프로세스 충돌1건이다. 게이트는26개 중25개 통과·거부1건이다. 새 공유ZIP은 각 실행 보존본에서 보고서8개·PNG117개를 선택해 파일125개와 상대링크123개를 오프라인 검증했다. DICOM 제외, 다른PC·브라우저 표시는 미확인이다. 추가 실환경 진단은 승인 대기이며 배포 통과로 표시하지 않는다.

과거 후보4는 소스 `f00005a473098d5fa0b7eb7fc5c980e5717bea3c`·dirty=false에서 빌드했으며 팀 공통 설정을 포함했다. Windows 11 Pro `10.0.26200` 64-bit의 같은 High 관리자 계정에서 이전 `955dd11` 설치판(1.0.1)을 후보4(1.0.1)로 무창 업데이트하고 같은 판을 무창 재설치해 성공 로그를 확인했다. 설치 EXE 해시, 두 공용 바로가기의 대상·작업 경로, Users 수정 ACL, 통제 파일 1개의 해시 보존을 확인했다. 실제 config·보고서 보존과 다른 계정 쓰기는 확인하지 않았다.

설치판 CLI의 `--version`과 실제 공유 ZIP `verify-share`는 종료 0, ZIP 누락·변조·추가 대조군은 각각 종료 1이었다. 이전 전체 보고서 JSON·HTML·TXT·CSV와 스크린샷·로그로 자료 121개를 묶어 같은 PC의 한글·공백 경로에 추출했고, 별도 Edge 프로필의 DNS 차단 조건에서 보고서와 증거 링크의 실제 표시를 확인했다(DICOM 제외). 후보8 새 결과로 만든 ZIP(자료 109개)도 같은 PC 다른 경로에서 파일 대조·상대 링크·대조군 검증을 통과했다. 다른 PC·새 결과의 브라우저 표시·공유 GUI는 미검증이다. 동명 증거 파일 충돌 수정 후 공유 단위시험 12개도 통과했다. 후보의 전체 해시·로컬 결과 기록·조건별 미완료 범위는 위 인수표에 있다.

UAC 직접 선택·설치 완료 후 열기·사람 검수·다른 OS/계정·제거 인수는 미완료다. 후보9의 두 전체 게이트는 당시 WU_09 충돌로 거부됐고, 이전173eb3c 설치판의 WU 범위 게이트는 통과했다. 기본기능 전체의 새 실행은 미수행이다. `#80`·`#84`는 사용자 명시로 닫았고, 과거 회귀는 Issue #85에서 승인받아 실행했다.

안전 단위시험은 자료 경계를 검증하며 제품을 조작하지 않는다.
별도 기록에 설치·재설치·업데이트·제거, 다른 드라이브/한글/공백/CWD,
새 CMD/PowerShell/Win+R, 사용자 자료 보존, Python/Git/소스 없는 PC 또는 VM의 실제 수행 범위를 남긴다.
최종 동일 EXE로 승인받은 범위를 수행하고 TC별 결과·미수행 범위와 해시를 기록한다. 큰 공용 변경 또는 영향 불명확이면 기본기능·WU 전체다.
이 실행은 `tools/run_installed_suites.py`로 한다. 설치 파일이 build-info와 같은지 먼저 대조하고,
설치·작업 폴더 밖의 실행 폴더에서 선택한 명령만 수행한다. 실행마다 새 Reports/Evidence/Log를 복사해
해시를 다시 대조하고 결과를 `verification.json`에 남긴다.

```powershell
python tools/run_installed_suites.py --exe "<설치 폴더>\BellalunAuto.exe" --build-info "<설치 폴더>\build-info.json" --workspace "<작업 폴더>" --out "<빈 실행 기록 폴더>" --suites run-winupdate
```
WU_01/12/13은 기존 수동 범위로 구분하고 나머지 열 건의 PASS 여부를 명시한다.
빌드·설치·기동만으로 제품 시험 검증 완료라고 기록하지 않는다.

설계 근거: [Nuitka standalone 및 동적 import](https://nuitka.net/user-documentation/use-cases.html),
[Nuitka Windows 콘솔/MinGW64](https://nuitka.net/user-documentation/user-manual.html),
[Inno Setup 64비트 아키텍처](https://jrsoftware.org/ishelp/topic_setup_architecturesallowed.htm),
[Inno Setup Registry](https://jrsoftware.org/ishelp/topic_registrysection.htm).
