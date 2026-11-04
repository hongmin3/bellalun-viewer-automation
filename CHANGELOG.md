# Changelog

현재 사양은 [SPEC.md](SPEC.md), 진행 상태와 과거 검증 근거는 [progress.md](progress.md)에 둔다.

## 2026-11-04 (WU 자동화 정비)

### Added

- REQ-WU-002: 실시간 WU 체인이 단계마다 시간 상한과 Viewer 응답 없음(120초 연속)을 감시한다. 넘으면 실패 증거를 남기고 Viewer를 끝낸 뒤 그 단계 TC를 BLOCKED로 기록하고, Viewer를 다시 띄워 다음 단계를 계속한다. 단계가 끝날 때마다 `work/winupdate_checkpoint.json`에 저장하고 `run-winupdate --resume`으로 남은 단계만 이어 실행한다. 실행 중 절전을 막는다.
- REQ-WU-003: SKIP마다 판정을 막는지(`blocks_verdict`)를 적는다. WU_09 CD SKIP은 막지 않는다. USB 미확인 표시 정책(`manual`/`flag`/`current`)을 넣었고, 사용자 위임 결정으로 `manual`(USB 왕복 미확인이면 WU_09 MANUAL)을 쓴다.
- REQ-WU-004: 실행 전 점검(해상도·DPI·메모리·USB 유무·재부팅 대기·시계·작업 폴더 경로)과 `verified_environments.json` 대조를 넣었다. 미등록 환경은 WARN으로 리포트와 체크리스트 사본 L열에 남긴다. 로그인 직후 핵심 컨트롤 화면 계약이 맞지 않으면 BLOCKED로 체인을 멈춘다.
- REQ-WU-005: 실시간 실행마다 OS 빌드+UBR·KB 목록·마지막 업데이트 설치 시각을 기록하고 직전 기록과의 비교표를 '업데이트 전후' 시트와 meta에 남긴다. `run.py update-watch`는 빌드·KB가 바뀌었을 때만 `run-winupdate`를 한 번 실행하고, 예약 등록은 `--apply`가 있을 때만 한다. 사용자 결정으로 예약 작업은 등록하지 않고 필요할 때 사람이 직접 실행한다.
- REQ-WU-006: Viewer 소멸·단계 중단 때 `Evidence/failure/`에 로그 ±30초·메모리·GDI/USER 핸들·전면 창·WER 덤프 판정을 남긴다. Setting 순회는 페이지별 핸들 수를 기록한다. `tools/wu_flake_stats.py`로 여러 리포트의 판정 갈림을 센다.
- REQ-TRACE-002: WU_01~13을 `automation_scope.json`·`traceability.json`에 넣었다. `run.py list`는 WU 합계를 따로 보여 준다. `tools/wu_selfcheck.py`가 WU 매핑 일치, 예외 경로 PASS, 공유 `ctypes.windll` 원형 변경을 검사한다.
- REQ-DIST-005: `tools/release_gate.py`와 `build_distribution.py --gate-wu --gate-basic`을 넣었다. 리포트 meta에 `source_commit`·`source_dirty`를 남기고, 같은 커밋·수정 없는 소스의 결과만 통과시킨다. 통과하지 못한 빌드는 `-candidate` 이름과 표시 파일을 남긴다.

### Fixed

- REQ-WU-006: WF14 Setting 순회의 페이지별 GDI/USER 핸들이 리포트에 남지 않던 사양·코드 불일치를 고쳤다. Step 7 순회 판정의 actual에 1·2회차 핸들과 증가 요약을 싣는다.
- REQ-WU-003: `--from-regression` 변환에서 XIPL_03 알려진 결함이 있으면 WU_05가 FAIL로 나오던 문제를 고쳤다. 변환 JSON의 "Step N 미수행" 채움 행이 연쇄 중단 제외를 막았다. 후보11 기본 결과 변환이 PASS 8 / FAIL 1에서 실시간 경로와 같은 PASS 9 / FAIL 0이 됐다.
- REQ-WU-005: update-watch 예약 작업이 일반 권한으로 등록되어 `run-winupdate`의 관리자 권한 점검에서 막히던 설계를 `RunLevel Highest`로 고쳤다.

### Changed

- REQ-TRACE-002: `core/ui.py`가 공유 `ctypes.windll.user32`의 `SendInput`·`WindowFromPoint`·`GetAncestor` 서명을 바꾸던 6곳을 모듈 전용 `ctypes.WinDLL("user32")` 사본으로 옮겼다(사용자 승인). `wu_selfcheck` 검사 c의 기준선이 비었다.
- 공용 QA 서버 검증 자료 관리의 Bellalun Test Case 구역에 WU 체크리스트(R-25-782)를 등록했다.
- REQ-VERDICT-001: WU_09 사양 문장을 현재 동작(교차 확인으로 PASS/FAIL, 근거 미수집만 MANUAL)에 맞췄다. `tests/winupdate.py`의 대비용 MANUAL 분기 주석도 고쳤다.
- 문서: README의 최신 검증 결과를 후보11 최소 환경 실행과 10-21 USB 재확인으로, 배포 가이드의 검증 호스트를 Win11 Pro 26200(LTSC 실측은 후보5·6까지)으로 고쳤다. SPEC 13절에 미검증 환경 표를 두었다.

### Validation

- 단위시험 643개 통과(skip 2). 정적 검사 7종 이상 없음. Viewer 조작 없이 이 PC에서 실행 전 점검(OK 8 / WARN 2 / BLOCK 0, 검증 환경 `win11-pro-26200`), 업데이트 근거 기록·비교(26200.9818, KB 6건, 변화 없음), 예약 명령 출력(등록 안 함), 과거 결과 변환, 반복 통계를 실행했다.
- 승인된 실제 실행(커밋 `2039d56`): 체인을 WF04 진행 중에 강제 종료하고 `--resume`으로 이어 완주했다. 저장점 8단계를 재사용했고 감시자 중단은 없었다. WU 결과 PASS 9 / MANUAL 3 / FAIL 1이며 FAIL은 XIPL_04 Step 8의 1회성 실행 예외로 생긴 WU_04다(단독 재실행 PASS, 원인 미확정). WU_10 56페이지 핸들 기록에서 페이지당 증가는 없었다. 릴리스 게이트는 이 결과를 거부했다.
- REQ-DIST-005: 후보11 리포트(`56a0bc6`)는 `source_commit`이 없어 거부된다. 그 밖의 항목(실시간·체인 완료·PASS 10 / MANUAL 3·전체 회귀·알려진 결함 외 FAIL 없음)은 통과했다.

## 2026-11-04

### Changed

- REQ-TRACE-001: 사양 근거를 분권(사양서1·사양서2, 260710판)에서 서버의 통합 사양서로 옮겼다. `core/specs.py`는 `사양서(YYMMDD).pdf` 가운데 가장 늦은 판을 쓴다. `traceability.json`의 사양 인용 63건은 문구로 통합본의 쪽과 SRS를 다시 찾았고, 코드 주석·판정 문구·문서의 쪽 번호도 통합본 기준으로 바꿨다(예: Print Overlay Header 297쪽 → 787쪽).
- REQ-TRACE-001: 통합본에는 같은 문장이 SRS 없는 변경 메모와 요구사항 본문에 함께 있다. 판정 문구 인용(`specs.cite`)은 SRS ID가 붙은 쪽을 고르고, 추적성 검사는 기록된 쪽에 문장이 있으면 그 쪽을 쓴다. 실측: "설정 가능한 3D Viewposition"이 294쪽 메모와 678쪽 SRS 03-30-20에 함께 있어, 고치기 전에는 294쪽(SRS 없음)을 인용했다.

### Fixed

- REQ-TRACE-001: Send Preview "기본 Layout 1x2" 인용이 Export 경로 규칙 쪽(분권 132쪽)을 가리키던 잘못을 고쳤다. 실제 문장은 통합본 778쪽에 있다.

### Added

- REQ-KNOW-001: `python run.py sync-knowledge`를 추가했다. 상위 `지식` 폴더를 검증 자료 관리 서버의 Bellalun Viewer 자료 화면과 같게 맞춘다. 바뀐 문서만 받아 크기(SSH는 SHA-256도)를 확인한 뒤 넣고, 같은 문서의 옛 판은 `_이전판/<날짜>/`로 옮긴다. 서버에 없는 로컬 자료는 그대로 둔다. `--install-task --apply`로 평일 11:00 예약 작업을 등록한다.

### Validation

- REQ-KNOW-001: 이 PC에서 실제로 맞췄다. 서버 13건 가운데 새 판 4건(통합 사양서 261030, QC Manual, QA 지침, Skill 지침)을 넣고 9건은 내용이 같아 그대로 두었다. 13건 모두 서버 기록의 SHA-256과 같다. 다시 돌리면 13건 모두 그대로였고, 예약 작업으로 한 번 실행한 결과도 종료 코드 0이었다.

## 2026-10-21

### Validation

- REQ-WU-001: 이전과 다른 USB(FAT32 14.6GB)를 연결하고 후보11 최소 환경 실시간 WU 전체를 다시 수행했다. PASS 10 / FAIL 0 / MANUAL 3이며 WU_09의 USB Export와 Import 되읽기가 Import 완료 신호까지 확인되어 PASS다. USB의 기존 폴더는 그대로 남았다.
- REQ-DIST-004, REQ-WU-001: 후보11(`56a0bc6`, EXE SHA256 `2eb31efe…36f3`)을 개발 도구를 뺀 최소 환경과 `&`·괄호·작은따옴표·`#`·한글이 든 작업 폴더에서 실행했다. 기본기능 전체는 27 TC 중 PASS 23 / FAIL 2 / MANUAL 2이며 FAIL은 기존 제품 결함 WF14 UPS·XIPL03이다. 실시간 WU 전체는 끝까지 수행되어 PASS 10 / MANUAL 3으로 목표를 달성했다. USB가 분리되어 있어 WU_09의 USB 왕복 단계는 SKIP으로 남았다.

## 2026-10-20

### Fixed

- REQ-WU-001: WU_09에서 Export Manager가 늦게 열리면 그 창이 남아 WU_10·WU_11의 Viewer 로그인까지 실패하던 문제를 고쳤다. Export Manager 창 대기를 20초에서 60초로 늘리고, Viewer를 새로 띄우기 전에 남은 Export Manager를 닫는다. 실측: 후보10 실시간 WU에서 WF09 Export 뒤 창이 20초를 넘겨 20:15:41에 열렸고, 이어진 두 TC가 `최전면 창이 Viewer가 아닙니다: 'Export Manager'`로 FAIL했다. 같은 실행의 기본기능 WF09는 PASS였다.
- REQ-DIST-001: 작업 폴더 경로에 `%`가 있으면 Viewer의 Setting Export 저장이 거부되어 WF14가 300초 뒤 FAIL하던 문제를 막았다. 제품을 조작하는 실행은 시작 전에 거부하고 해결 방법을 알리며, 자체진단에 "작업 폴더 경로 문자" 항목을 더했다. 실측: 후보10 최소 환경 실행에서 작업 폴더 `...O'Brien %TEMP% #한글` 아래 `WF14_Baseline_Settings.vms`를 Windows 저장 대화상자가 "파일 이름이 올바르지 않습니다"로 거부했다. `&`·괄호·작은따옴표·`#`·한글은 같은 실행에서 문제가 없었다.
- REQ-DIST-004: BellalunAuto가 `XIPL_PATH` 없는 환경에서 Viewer를 띄우면 Viewer가 E2100을 기록하고 PC 전원을 끄던 문제를 막았다. Viewer·XIPL Studio는 실행 환경에 없는 등록 환경 변수를 레지스트리에서 보충해 띄우고, 그래도 `XIPL_PATH`가 맞지 않으면 Viewer를 띄우지 않고 해결 방법을 알린다. 자체진단에 "XIPL 설치 경로(XIPL_PATH)" 항목을 더했다. 실측: 2026-10-18 후보9 최소 환경 실행 1분 뒤 Viewer 로그에 `XIPL is not installed. [E2100]`이 남고 System 이벤트 1074(`VIEWER.exe`, 전원 끄기)가 기록됐다. 기존 XIPL 점검은 9784 포트만 봐서 21/21 PASS였다.

## 2026-10-18

### Added

- REQ-DIST-004: 자체진단에 "작업 폴더 경로 길이" 항목을 추가했다. Viewer가 쓰는 Export 증거의 상대 경로가 최대 117자이고 LongPathsEnabled 기본값은 0이라, 작업 폴더가 120자를 넘으면 시험 중간에 실패하기 전에 짧은 경로를 고르라고 안내한다.
- REQ-DIST-004: `tools/run_installed_suites.py --clean-env`를 추가했다. PATH를 Windows 기본값만 두고 Python·Git·Node 관련 변수를 빼며, PYTHONHOME/PYTHONPATH는 없는 경로로 채워 개발 도구 없는 PC를 흉내 낸다.

### Fixed

- REQ-DIST-001, REQ-REGRESSION-001: 경로에 작은따옴표(`'`)가 있으면 기준 DB BACKUP/RESTORE 문장과 PowerShell 버전·서명 조회가 문법 오류로 실패하던 문제를 고쳤다. 같은 파일의 FILELISTONLY·MOVE 절처럼 값을 이스케이프한다. 실측: 고치기 전 형태는 `Incorrect syntax near 'Brien'`으로 실패했고, 고친 형태의 `RESTORE VERIFYONLY`와 Viewer 버전 읽기는 `O'Brien 한글` 경로에서 성공했다.

## 2026-10-17

### Added

- REQ-DIST-004: 설치판 EXE로 기본기능 전체와 실시간 WU 전체를 차례로 실행하는 `tools/run_installed_suites.py`를 추가했다. 설치 파일과 `build-info.json`의 크기·SHA256을 먼저 대조하고, 설치·작업 폴더 밖 실행 폴더에서 실행한다. 실행마다 새 Reports/Evidence/Log를 복사해 해시를 다시 대조하고, 새 전체 리포트 여부와 WU 목표(기존 수동 3건 외 10건 PASS)를 판정 기준 변경 없이 기록한다.

### Validation

- REQ-DIST-004, REQ-WU-001: 최종 설치판 후보8(`516632c`, EXE SHA256 `585213b4…704b`)을 한글·공백이 있는 다른 드라이브에 설치해 실행했다. 기본기능 전체는 27 TC 중 PASS 23 / FAIL 2 / MANUAL 2이며, FAIL은 기존 제품 결함 WF14 UPS·XIPL_03 값 복귀다. 실시간 WU 전체는 끝까지 수행되어 PASS 10 / MANUAL 3으로 목표를 달성했다. WU_09는 실제 USB로 Export·Import 되읽기를, WU_10은 56페이지와 24회 전환을 수행했다.
- REQ-DIST-003, REQ-DIST-004: 후보8 산출물 독립 감사 12항목을 통과했다. 같은 AppId 업데이트, 제거, 기본 경로 재설치에서 PATH 중복이 없었고 작업 폴더 파일을 모두 보존했다. 새 셸·설치 폴더 밖 CWD·stdin 종류를 바꾼 자체진단 20항목과 App Paths 실행이 통과했다. 개발 도구 없는 PC/VM, Windows 10, 다른 관리자 계정 UAC는 검증하지 않았다.
- REQ-WU-001: 후보7(`f5e40fa`)은 기본 PASS 23 / FAIL 2 / MANUAL 2, 실시간 WU PASS 9 / FAIL 1 / MANUAL 3이었다. 후보6을 멈춘 기동 실패는 다시 나지 않았고, WU_09 FAIL은 아래 판정 범위 결함이었다.

### Fixed

- REQ-REGRESSION-001, REQ-WU-001: WF_09 Step 8 보강 판정(3D-N·3D-W가 각각 Export)이 기대 Recon을 환자 전체에서 모으던 문제를 고쳤다. Export는 선택한 검사 하나만 내보내는데, WU 체인은 XIPL 묶음이 WF_09보다 먼저 같은 환자에 Recon 검사를 더 만든다. 후보7 실시간 WU에서 Export한 검사의 Recon 2건은 모두 들어 있었지만 다른 검사의 Recon 2건을 누락으로 세어 WU_09가 FAIL했다. 기대 집합을 Export한 검사로 한정하고, 판정 기준(두 Recon이 모두 Export되어야 함)은 유지한다.
- REQ-DIST-003: 저장소가 한글 경로(`C:\자동화\...`) 아래에 있으면 빌드가 컴파일 성공 뒤 `Nuitka 컴파일 보고서 XML 오류`로 멈추던 문제를 고쳤다. Nuitka 보고서는 `encoding='utf8'`을 선언하는데 XML 해석기가 이 이름을 1바이트 인코딩으로 다뤄 한글 경로를 읽지 못했다. 보고서를 UTF-8로 직접 읽어 해석한다.
- REQ-REGRESSION-001: 다른 프로그램의 콘솔 창이 최전면을 쥐면 로그인 직전 Viewer를 올리지 못해 `DICOM_Server_Setup`이 바로 FAIL하던 문제를 고쳤다. 후보6 실시간 WU 조기 종료와 같은 모양(PW 빈칸 로그인 화면, 약 10초)을 콘솔 창으로 재현했다. 기존 단계가 실패하고 다른 프로그램이 가리고 있을 때만 `SwitchToThisWindow`와 배정되지 않은 가상키를 차례로 쓴다. 로그인 중 최전면 확보 실패는 키를 보내기 전에 멈춘 것이므로 정해진 횟수 안에서 다시 시도하고, 가린 창 이름을 기동 기록에 남긴다.

## 2026-10-15

### Added

- REQ-DIST-001, REQ-DIST-002: BellalunAuto의 한국어 실행·설정 화면, 작업 폴더 분리, 읽기 전용 자체진단, 기존 CLI 연결을 구현했다. 자기 EXE의 worker 감시, PC 공통 제품 잠금, UAC 경로 전달, 중지·비정상 종료 정리와 비공개 로그 처리를 포함한다.
- REQ-DIST-003: 승인 자료 manifest·해시 검사, Nuitka standalone·Inno Setup 빌드, 포터블 ZIP과 빌드 정보 생성을 구현했다. 사내 원문·Baseline·설치 산출물은 공개 배포 대상에서 제외한다.
- REQ-WU-001: USB Import 완료 메시지, 환자 범위 전후 DB UID, 실제 영상 파일과 Examined 클릭 로그를 연결하는 판정을 구현했다. 단독 실측에서 Imported 1 / Skipped 0, 신규 검사 1건·영상 3건, 파일 XML UID와 재검색 결과의 일치를 확인했다. 연결된 전체 흐름과 최종 설치판 검증은 별도로 수행한다.

### Fixed

- REQ-REGRESSION-001: 예약일 옵션은 실제 Scheduled Study DateTime 행의 체크박스를 찾아 저장하고 되읽는다. 목록에서는 Scheduled 헤더에 해당하는 열만 OCR로 읽어 생년월일을 예약일로 사용하는 오류를 막는다.
- REQ-DIST-001, REQ-DIST-004: 선택한 OCR 실행 경로를 공통 OCR 호출에 연결하고 XIPL 기동 준비 대기를 보강했다. 설치 자료·승인 Baseline을 출력으로 덮어쓰지 않도록 경로·링크 검사를 추가하고, 명시한 승인 자료 경로를 보존한다.
- REQ-REGRESSION-001: DB가 미등록 상태일 때 Baseline 복원의 물리 파일명을 제품 표준 `{DB}.mdf` / `{DB}.ldf`로 지정한다. 기존 등록 경로는 유지한다. WF14의 DB 전수 대조는 중단 전에 전후 스냅샷과 전체 필드 차이를 남긴다.
- REQ-DIST-002, REQ-WU-001: 과거 회귀 변환과 실시간 실행을 구분하고, 새 live 전체 완료 메타데이터 없이 완료로 판단하지 않는다. USB 부재·실패·미완료와 설정 순회 실패의 판정도 보존한다.
- REQ-WU-001: Export 성공 문구·증거·단일 버튼을 확인하고 프로세스 종료를 별도 대기한다. 실제 Export OK ID 800을 확인했으며 부분 Import는 영상 수 비교로 거절한다. 늦게 뜨는 중복 환자 팝업도 제한 시간 안에서 처리한다.
- REQ-DIST-003: Inno Setup 6.7.3에서 사용할 수 없는 PATH 분할 함수를 명시적 토큰 분할로 교체하고 실제 설치 스크립트 컴파일 회귀 검사를 추가했다.
- REQ-DIST-002: Nuitka standalone에서 `sys.executable`이 존재하지 않는 `python.exe`를 반환하는 경우를 재현했다. Windows 실제 EXE 경로로 자식 작업을 실행하며 소스 실행과 명시한 실행 경로는 유지한다.
- REQ-DIST-002: 실제 리포트 생성 함수가 붙이는 `Result_` 접두사를 WU 완료 탐색에 반영했다. 리포트 생성 함수를 직접 사용하는 통합 시험으로 새 live 전체 결과만 인정하는지 확인한다.
- REQ-DIST-004: XIPL 저장 영상의 한글 경로 OCR 실패를 영상 바이트의 stdin 전달로 보완했다. 이 수정 이후 새 정식 빌드와 설치 EXE 전체 재시험이 필요하다.
- REQ-REGRESSION-001, REQ-DIST-004: XIPL 준비 시 새 클릭 로그의 StudyKey가 조회한 DB 검사 키와 일치해야 View를 허용한다. 오래된 정렬에서 영상이 없는 검사를 여는 오류를 막는다.
- REQ-REPORT-001: 개별 XIPL_01/02/03/06의 준비 실패를 `stop=False`로 FAIL 리포트에 남긴다. 원래 TC·InstanceType·Step 기준을 유지하며 실패 기록 중 재예외로 리포트가 사라지는 문제를 막는다.
- REQ-WU-001: 설정값이 없는 버튼 전용 화면을 빈 화면으로 오인하던 WU10 판정을 수정했다. 설정값 비교는 유지하고, 별도로 현재 패널의 안정화·실제 하위 콘텐츠를 확인한다. 숨김·패널 밖·장식만 있는 화면은 통과시키지 않으며 56페이지와 24회 탭 전환을 유지한다.

### Validation

- REQ-DIST-004, REQ-WU-001: 후보5(`6065490`) 동일 설치 EXE의 기본 전체는 PASS 23 / FAIL 2 / MANUAL 2, 실시간 WU 전체는 PASS 9 / FAIL 1 / MANUAL 3으로 완료했다. 기본 FAIL은 기존 UPS 복원·XIPL_03 값 유지 문제이며, WU10은 정상 버튼 화면 2개의 빈 설정값 목록을 오판했다. 보존본은 기본 300파일·WU 310파일 모두 크기·SHA256 검증을 통과했다. 수정본은 전체 단위시험 424개·하위 사례 238개와 독립 리뷰를 통과했으며 새 설치 EXE의 두 전체 재검증은 진행한다.
- REQ-DIST-004, REQ-WU-001: 보완 후 단위시험 415개와 하위 사례 215개, 정적 검사와 독립 리뷰를 통과했다. WF01 예약일 helper의 실제 Off→On 저장과 Patient MWL 날짜 ROI 수집, 한글 작업 폴더에서 XIPL_01/06 실제 재시험도 PASS다. 새 설치 EXE의 두 전체 시험은 별도로 수행한다.
- REQ-REGRESSION-001: WF14 단독 재시험에서 DB 38개 영역, 전후 56개 페이지와 목록 89행·849항목 복원을 확인했다. 기존 UPS 미복원만 FAIL이며 원복 정리는 PASS다. 기존 WU11 기준에 따른 조회 전용 매핑은 PASS이며 실제 live 전체를 대체하지 않는다.
- REQ-DIST-003, REQ-DIST-004: 후보4(`8d0cdcd`)의 실제 ZIP 바이트·승인 자산·라이선스·기본 설정 독립 감사 31항목, 한글·공백이 있는 다른 드라이브의 설치·교체·재설치·제거 보존 7단계, guardian 3사례, GUI 기동 경로와 자체진단 20항목을 통과했다.
- REQ-DIST-004: 후보4 설치 기본 전체는 2026-10-15 05:56~07:58(현지 America/Los_Angeles), 새 `Result_20261015_075809.json`에서 27 TC 중 PASS 20 / FAIL 5 / MANUAL 2로 완료했다. FAIL은 기존 제품 결함 WF14 UPS·XIPL_03 2건과 WF01 DOB 열 선택·XIPL_01/06 한글 경로 OCR 자동화 오류 3건이다. WU 시작 전에 Evidence·새 리포트·로그 281파일의 일관된 snapshot을 보존했다.
- REQ-DIST-004: 후보4 WU는 07:58 시작했으나 확인된 작업 자식을 중단하고 guardian 정리 후 08:06:39 `abnormal_exit` 73으로 끝났다. WU 전체 완료나 최종 전달 성공으로 판정하지 않는다. 수정 후 재빌드한 동일 EXE로 두 전체를 재수행한다. 개발 도구 없는 PC/VM·다른 관리자 계정 UAC·Windows 10 실검증은 미완료이며 동일 호스트 reduced PATH 검사로 대체하지 않는다.

## 2026-09-29

### Changed

- 공통 SPEC workflow를 v8로 올리고 `SPEC.md` 1절에 프로젝트 전체 흐름을 보여 주는 "한눈에 보기" 흐름도를 더했다. `docs/SPEC.html` 1절에 그림으로 보인다. 제품 동작은 바뀌지 않았다.
- 공통 SPEC workflow를 v7로 올렸다(키트 관리 블록과 `.project-check/` 검사기·렌더러 교체). 이 프로젝트는 단일 파일 `SPEC.md`를 그대로 쓴다. 제품 동작은 바뀌지 않았다.
- 프로젝트 폴더가 `C:\자동화\Bellalun Viewer` → `C:\자동화\projects\Bellalun Viewer`로 옮겨졌다. 저장소 안 경로는 모두 상대 경로라 코드는 바뀌지 않았다.

## 2026-09-22

### Changed

- 자동화 Workspace의 SPEC/readiness workflow를 도입하고 현재 요구사항과 구현·테스트 연결을 문서화했다.
- 기존 진행 문서의 고유 운영 사실과 미완료 제품 작업을 보존했다.
- 이번 변경은 governance-only(관리 체계 도입)이며 기존 런타임 동작을 유지한다.
  제품 기능을 추가하거나 변경하지 않았으며 새 제품 검증·배포 완료를 의미하지 않는다.
