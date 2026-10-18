# Changelog

현재 사양은 [SPEC.md](SPEC.md), 진행 상태와 과거 검증 근거는 [progress.md](progress.md)에 둔다.

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
